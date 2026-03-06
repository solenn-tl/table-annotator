import json
import argparse
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
import requests
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAIRS_PATH = PROJECT_ROOT / "cut_images/alpes-maritimes/aiglun/3P31/pairs.json"
OUTPUT_PATH = PROJECT_ROOT / "cut_images/alpes-maritimes/aiglun/3P31/classification.json"
MODEL_PATH = PROJECT_ROOT / "models/classification/best.pt"
REQUEST_TIMEOUT = (10, 20)
MAX_RETRIES = 2


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
        "--limit",
        type=int,
        default=None,
        help="Optional number of pairs to process (useful for quick testing).",
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

    model = YOLO(str(MODEL_PATH))
    class_names = get_class_names(model)
    with PAIRS_PATH.open("r", encoding="utf-8") as f:
        pairs = json.load(f)
    if args.limit is not None:
        pairs = pairs[: max(args.limit, 0)]

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

        for pair in pairs:
            name = pair.get("name")
            image_url = pair.get("image")
            if not isinstance(name, str) or not isinstance(image_url, str):
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

        if inference_files:
            predict_device = None if args.device == "auto" else args.device
            results = model(inference_files, stream=False, device=predict_device)
            for name, result in zip(inference_names, results):
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

    if failures:
        output.append({"_download_failures": failures})

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Classified images: {len(output) - (1 if failures else 0)}")
    print(f"Device: {args.device}")
    if failures:
        print(f"Download failures: {len(failures)}")
    print(f"Output file: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()