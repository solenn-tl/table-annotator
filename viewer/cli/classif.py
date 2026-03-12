import json
import argparse
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
import requests
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ELEMENTS_PATH = PROJECT_ROOT / "cut_images/alpes-maritimes/aiglun/3P31/elements.json"
OUTPUT_PATH = PROJECT_ROOT / "cut_images/alpes-maritimes/aiglun/3P31/classification.json"
MODEL_PATH = PROJECT_ROOT / "models/classification/best.pt"
REQUEST_TIMEOUT = (10, 20)
MAX_RETRIES = 2


def render_progress(current: int, total: int, label: str = "Progress") -> None:
    """
    For a given current and total, render a progress bar in the console with an optional label.
    The progress bar is 32 characters wide and shows the percentage completed.
    """
    safe_total = max(int(total), 1)
    safe_current = max(0, min(int(current), safe_total))
    ratio = safe_current / safe_total
    bar_width = 32
    filled = int(bar_width * ratio)
    bar = f"{'#' * filled}{'-' * (bar_width - filled)}"
    percent = int(ratio * 100)
    sys.stdout.write(f"\r{label}: [{bar}] {safe_current}/{safe_total} ({percent}%)")
    sys.stdout.flush()
    if safe_current >= safe_total:
        sys.stdout.write("\n")
        sys.stdout.flush()


def resolve_input_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def resolve_output_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def build_headers(image_url: str) -> dict[str, str]:
    parsed = urlparse(image_url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9;fr-FR,fr;q=0.8",
        "Referer": referer,
        "Connection": "keep-alive",
    }


def is_decodable_image(data: bytes) -> bool:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image is not None


def download_image(session: requests.Session, image_url: str) -> bytes:
    last_error: Exception | None = None
    for _ in range(MAX_RETRIES + 1):
        try:
            response = session.get(
                image_url,
                headers=build_headers(image_url),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("image/"):
                raise ValueError(f"Unexpected Content-Type: {content_type}")
            if not is_decodable_image(response.content):
                raise ValueError("Downloaded bytes are not a decodable image")
            return response.content
        except Exception as error:
            last_error = error

    assert last_error is not None
    raise last_error


def with_iiif_width(image_url: str, width: int | None) -> str:
    if not width or width <= 0:
        return image_url
    marker = "/full/full/0/default"
    if marker in image_url:
        return image_url.replace(marker, f"/full/{width},/0/default")
    return image_url


def get_class_names(model: YOLO) -> list[str]:
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        return [str(names[idx]) for idx in sorted(names.keys())]
    if isinstance(names, list):
        return [str(name) for name in names]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Download IIIF images and run YOLO classification.")
    parser.add_argument(
        "--elements-path",
        type=str,
        default=None,
        help=f"Path to elements.json (default: {ELEMENTS_PATH})",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help=f"Path to classification output JSON (default: {OUTPUT_PATH})",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=str(MODEL_PATH),
        help=f"Path to YOLO model weights (default: {MODEL_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of elements to process (useful for quick testing).",
    )
    parser.add_argument(
        "--iiif-width",
        type=int,
        default=800,
        help="Request IIIF images at this max width (default: 800). Use 0 to keep full size.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda", "cuda:0", "cuda:1"],
        help="Inference device: auto, cpu, cuda, cuda:0, or cuda:1 (default: auto).",
    )
    args = parser.parse_args()

    elements_path = resolve_input_path(args.elements_path)
    output_path = resolve_output_path(args.output_path)
    model_path = resolve_input_path(args.model_path)

    model = YOLO(str(model_path))
    class_names = get_class_names(model)
    with elements_path.open("r", encoding="utf-8") as f:
        elements = json.load(f)
    if args.limit is not None:
        elements = elements[: max(args.limit, 0)]

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "image/*,*/*;q=0.8",
        }
    )

    output: list[dict] = []
    failures: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="ocr_classif_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        inference_files: list[str] = []
        inference_names: list[str] = []

        total_elements = len(elements)
        if total_elements > 0:
            render_progress(0, total_elements, label="Downloading")

        for index, pair in enumerate(elements, start=1):
            name = pair.get("name")
            image_url = pair.get("image")
            if not isinstance(name, str) or not isinstance(image_url, str):
                render_progress(index, total_elements, label="Downloading")
                continue
            requested_url = with_iiif_width(image_url, args.iiif_width)

            try:
                image_bytes = download_image(session, requested_url)
                file_path = tmp_path / f"{name}.jpg"
                file_path.write_bytes(image_bytes)
                inference_files.append(str(file_path))
                inference_names.append(name)
            except Exception as error:
                failures.append(
                    {
                        "name": name,
                        "image": image_url,
                        "requested_image": requested_url,
                        "error": str(error),
                    }
                )
            finally:
                render_progress(index, total_elements, label="Downloading")

        if inference_files:
            predict_device = None if args.device == "auto" else args.device
            results = model(inference_files, stream=False, device=predict_device)
            total_results = len(inference_names)
            render_progress(0, total_results, label="Predicting")
            for index, (name, result) in enumerate(zip(inference_names, results), start=1):
                probs = result.probs.data.tolist() if result.probs is not None else []
                class_probs = []
                for idx, prob in enumerate(probs):
                    class_name = class_names[idx] if idx < len(class_names) else f"class_{idx}"
                    class_probs.append({"class": class_name, "prob": prob})

                top_classes = sorted(class_probs, key=lambda item: item["prob"], reverse=True)
                predicted_class = top_classes[0]["class"] if top_classes else None
                predicted_prob = top_classes[0]["prob"] if top_classes else None
                output.append(
                    {
                        "name": name,
                        "predicted_class": predicted_class,
                        "predicted_prob": predicted_prob,
                        "top_classes": top_classes,
                    }
                )
                render_progress(index, total_results, label="Predicting")

    if failures:
        output.append({"_download_failures": failures})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Classified images: {len(output) - (1 if failures else 0)}")
    print(f"Device: {args.device}")
    if failures:
        print(f"Download failures: {len(failures)}")
    print(f"Pairs file: {elements_path}")
    print(f"Model file: {model_path}")
    print(f"Output file: {output_path}")


if __name__ == "__main__":
    main()