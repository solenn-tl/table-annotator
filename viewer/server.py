from __future__ import annotations

import argparse
from collections import defaultdict
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parent
CUT_IMAGES_DIR = ROOT_DIR.parent / "cut_images"
NER_SETTINGS_DIR = ROOT_DIR / "ner-settings"
PROJECTS_SETTINGS_PATH = ROOT_DIR / "projects-settings.json"
LEGACY_PROJECTS_SETTINGS_PATH = ROOT_DIR / "projects-settings.json"
COLUMN_SETTINGS_DIR = ROOT_DIR / "column-settings"
COLUMN_SETTINGS_PATH = ROOT_DIR / "column-settings.json"
LEGACY_COLUMN_SETTINGS_PATH = ROOT_DIR.parent / "column-settings.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
ALLOWED_COLUMN_TYPES = {"none", "sequence", "autocomplete", "both"}
ALLOWED_IMAGE_FORMATS = {"single", "double"}
ALLOWED_SUBPROJECT_TYPES = {"local", "iiif"}
DEFAULT_IMAGE_FORMAT = "double"


def normalize_field_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def as_non_empty_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text if text else None


def clean_numero_liste(value: object) -> str | None:
    text = as_non_empty_text(value)
    if text is None:
        return None

    without_strike = re.sub(r"~~.*?~~", "", text)
    cleaned = without_strike.strip()
    return cleaned if cleaned else None


def get_row_field_value(row: dict[str, object], normalized_field: str) -> object | None:
    for key, value in row.items():
        if isinstance(key, str) and normalize_field_name(key) == normalized_field:
            return value
    return None


def numero_liste_sort_key(value: str) -> tuple[int, object]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value.casefold())


def build_elements(cut_images_dir: Path = CUT_IMAGES_DIR) -> list[dict[str, str]]:
    elements: list[dict[str, str]] = []

    if not cut_images_dir.exists():
        return elements

    json_by_stem = {path.stem: path for path in cut_images_dir.glob("*.json")}

    for image_path in sorted(cut_images_dir.iterdir()):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        json_path = json_by_stem.get(image_path.stem)
        if not json_path:
            continue

        elements.append(
            {
                "name": image_path.stem,
                "image": image_path.name,
                "json": json_path.name,
            }
        )

    return elements


def sanitize_pair_base_name(value: object) -> str:
    text = str(value or "")
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", text)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "iiif_page"


def extract_iiif_label(canvas: object, fallback_index: int) -> str:
    if not isinstance(canvas, dict):
        return f"page_{fallback_index + 1}"

    label = canvas.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()

    if isinstance(label, dict):
        for key in ("none", "fr", "en"):
            values = label.get(key)
            if isinstance(values, list):
                for item in values:
                    text = as_non_empty_text(item)
                    if text:
                        return text

    return f"page_{fallback_index + 1}"


def extract_iiif_canvas_image_url(canvas: object) -> str | None:
    if not isinstance(canvas, dict):
        return None

    annotation_pages = canvas.get("items")
    if isinstance(annotation_pages, list) and annotation_pages:
        first_page = annotation_pages[0]
        if isinstance(first_page, dict):
            annotations = first_page.get("items")
            if isinstance(annotations, list) and annotations:
                first_annotation = annotations[0]
                if isinstance(first_annotation, dict):
                    body = first_annotation.get("body")
                    if isinstance(body, str):
                        return as_non_empty_text(body)

                    if isinstance(body, dict):
                        return as_non_empty_text(body.get("id"))

    images = canvas.get("images")
    if isinstance(images, list) and images:
        first_image = images[0]
        if isinstance(first_image, dict):
            resource = first_image.get("resource")
            if isinstance(resource, str):
                return as_non_empty_text(resource)
            if isinstance(resource, dict):
                return as_non_empty_text(resource.get("@id")) or as_non_empty_text(resource.get("id"))

    return None


def extract_iiif_service_base_url(canvas: object) -> str | None:
    if not isinstance(canvas, dict):
        return None

    annotation_pages = canvas.get("items")
    if isinstance(annotation_pages, list) and annotation_pages:
        first_page = annotation_pages[0]
        if isinstance(first_page, dict):
            annotations = first_page.get("items")
            if isinstance(annotations, list) and annotations:
                first_annotation = annotations[0]
                if isinstance(first_annotation, dict):
                    body = first_annotation.get("body")
                    if isinstance(body, dict):
                        services = body.get("service")
                        if isinstance(services, list) and services:
                            first_service = services[0]
                            if isinstance(first_service, dict):
                                return as_non_empty_text(first_service.get("id")) or as_non_empty_text(first_service.get("@id"))
                        if isinstance(services, dict):
                            return as_non_empty_text(services.get("id")) or as_non_empty_text(services.get("@id"))

    images = canvas.get("images")
    if isinstance(images, list) and images:
        first_image = images[0]
        if isinstance(first_image, dict):
            resource = first_image.get("resource")
            if isinstance(resource, dict):
                service = resource.get("service")
                if isinstance(service, dict):
                    return as_non_empty_text(service.get("@id")) or as_non_empty_text(service.get("id"))
                if isinstance(service, list) and service:
                    first_service = service[0]
                    if isinstance(first_service, dict):
                        return as_non_empty_text(first_service.get("@id")) or as_non_empty_text(first_service.get("id"))

    return None


def build_iiif_region_url(image_url: str, region: str) -> str:
    match = re.match(r"^(.*?/)(full|pct:[^/]+)(/[^?#]*)(\?[^#]*)?(#.*)?$", image_url, re.IGNORECASE)
    if not match:
        return image_url

    prefix = match.group(1) or ""
    suffix = match.group(3) or ""
    query = match.group(4) or ""
    fragment = match.group(5) or ""
    return f"{prefix}{region}{suffix}{query}{fragment}"


def join_iiif_image_url(base_url: str, image_name: str, suffix: str) -> str:
    left = base_url.rstrip("/")
    middle = image_name.strip().strip("/")
    right = suffix.strip()
    if right and not right.startswith("/"):
        right = f"/{right}"

    base_without_query = re.split(r"[?#]", left, maxsplit=1)[0]
    base_has_image_filename = bool(re.search(r"\.[A-Za-z0-9]{2,5}$", base_without_query))

    if middle and (left.endswith(f"/{middle}") or base_has_image_filename):
        middle = ""

    if middle:
        return f"{left}/{middle}{right}"
    return f"{left}{right}"


def get_nested_value(payload: object, path: str) -> object | None:
    current = payload
    parts = [segment for segment in re.split(r"[/.]", path) if segment]
    if not parts:
        return None

    for segment in parts:
        if isinstance(current, dict):
            if segment in current:
                current = current[segment]
                continue
            return None

        if isinstance(current, list):
            if re.fullmatch(r"\d+", segment):
                index = int(segment)
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
                continue

            if current and isinstance(current[0], dict) and segment in current[0]:
                current = current[0][segment]
                continue

            return None

        return None

    return current


def get_manifest_canvases(manifest: object) -> list[object]:
    if not isinstance(manifest, dict):
        return []

    items = manifest.get("items")
    if isinstance(items, list):
        return items

    sequences = manifest.get("sequences")
    if isinstance(sequences, list) and sequences:
        first_sequence = sequences[0]
        if isinstance(first_sequence, dict):
            canvases = first_sequence.get("canvases")
            if isinstance(canvases, list):
                return canvases

    return []


def sync_elements_manifest(cut_images_dir: Path, elements: list[dict[str, str]]) -> None:
    cache_path = cut_images_dir / "elements.json"

    existing_elements: list[dict[str, str]] | None = None
    try:
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                existing_elements = payload
    except (OSError, json.JSONDecodeError):
        existing_elements = None

    if existing_elements == elements:
        return

    cut_images_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(elements, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def ensure_pair_json_files(cut_images_dir: Path, elements: list[dict[str, str]]) -> int:
    cut_images_dir.mkdir(parents=True, exist_ok=True)
    created_count = 0

    for pair in elements:
        json_name = pair.get("json") if isinstance(pair, dict) else None
        json_text = as_non_empty_text(json_name)
        if json_text is None:
            continue

        target = (cut_images_dir / json_text).resolve()
        if target.parent != cut_images_dir.resolve():
            continue

        if target.exists():
            continue

        target.write_text("[]\n", encoding="utf-8")
        created_count += 1

    return created_count


def load_elements_manifest(cut_images_dir: Path) -> list[dict[str, object]]:
    manifest_path = cut_images_dir / "elements.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                normalized: list[dict[str, object]] = []
                for entry in payload:
                    if isinstance(entry, dict):
                        normalized.append(dict(entry))
                return normalized
        except (OSError, json.JSONDecodeError):
            pass

    generated = build_elements(cut_images_dir)
    return [dict(item) for item in generated]


def save_elements_manifest(cut_images_dir: Path, elements: list[dict[str, object]]) -> Path:
    cut_images_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cut_images_dir / "elements.json"
    manifest_path.write_text(
        json.dumps(elements, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def resolve_model_path(model_path_text: str) -> Path:
    model_path = Path(model_path_text)
    if model_path.is_absolute():
        return model_path
    return (ROOT_DIR.parent / model_path).resolve()


def extract_top_class_name(result: object, model: object) -> str | None:
    probs = getattr(result, "probs", None)
    if probs is None:
        return None

    top1 = getattr(probs, "top1", None)
    if top1 is None:
        return None

    try:
        top_index = int(top1)
    except (TypeError, ValueError):
        return None

    names = getattr(result, "names", None)
    if not names:
        names = getattr(model, "names", None)

    if isinstance(names, dict):
        label = names.get(top_index)
        return str(label) if label is not None else str(top_index)

    if isinstance(names, list) and 0 <= top_index < len(names):
        return str(names[top_index])

    return str(top_index)


def classify_elements_with_yolo(
    cut_images_dir: Path,
    pair_names: list[str] | None,
    model_path_text: str,
    confidence: float,
) -> dict[str, object]:
    try:
        from ultralytics import YOLO
    except Exception as error:
        raise RuntimeError(f"Ultralytics is not available: {error}") from error

    model_path = resolve_model_path(model_path_text)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    elements = load_elements_manifest(cut_images_dir)
    selected_names = {
        text
        for text in (as_non_empty_text(name) for name in (pair_names or []))
        if text is not None
    }

    if selected_names:
        target_elements = [
            pair for pair in elements
            if as_non_empty_text(pair.get("name")) in selected_names
        ]
    else:
        target_elements = elements

    model = YOLO(str(model_path))
    classified_count = 0
    failed: list[dict[str, str]] = []

    for pair in target_elements:
        pair_name = as_non_empty_text(pair.get("name")) or "(unknown)"
        image_value = as_non_empty_text(pair.get("image"))
        if image_value is None:
            failed.append({"name": pair_name, "error": "Missing image path"})
            continue

        image_source: str
        if re.match(r"^https?://", image_value, re.IGNORECASE):
            image_source = image_value
        else:
            image_path = (cut_images_dir / image_value).resolve()
            if not image_path.exists():
                failed.append({"name": pair_name, "error": f"Image not found: {image_path.name}"})
                continue
            image_source = str(image_path)

        try:
            results = model.predict(source=image_source, conf=confidence, verbose=False)
        except Exception as error:
            failed.append({"name": pair_name, "error": str(error)})
            continue

        if not results:
            failed.append({"name": pair_name, "error": "No prediction result"})
            continue

        class_name = extract_top_class_name(results[0], model)
        if class_name is None:
            failed.append({"name": pair_name, "error": "No class probability output"})
            continue

        pair["class"] = class_name
        classified_count += 1

    manifest_path = save_elements_manifest(cut_images_dir, elements)
    return {
        "ok": True,
        "classified": classified_count,
        "failed": failed,
        "totalSelected": len(target_elements),
        "elementsPath": str(manifest_path),
        "modelPath": str(model_path),
    }


def build_iiif_elements(
    manifest_url: str,
    image_name_path: str | None = None,
    image_url_path: str | None = None,
    image_suffix: str | None = None,
) -> list[dict[str, str]]:
    request = Request(
        manifest_url,
        headers={
            "User-Agent": "ocr-viewer/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=25) as response:
        raw_payload = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        content_type = response.headers.get("Content-Type", "")

    raw_text = raw_payload.decode(charset, errors="replace").lstrip("\ufeff").strip()
    if not raw_text:
        raise ValueError(f"Empty response body for IIIF manifest URL: {manifest_url}")

    try:
        manifest = json.loads(raw_text)
    except json.JSONDecodeError as error:
        snippet = raw_text[:200].replace("\n", " ")
        raise ValueError(
            f"Invalid JSON from IIIF manifest URL {manifest_url}. "
            f"Content-Type={content_type!r}. Body starts with: {snippet!r}"
        ) from error

    canvases = get_manifest_canvases(manifest)
    if not canvases:
        return []

    elements: list[dict[str, str]] = []

    for index, canvas in enumerate(canvases):
        label = extract_iiif_label(canvas, index)
        canvas_id = canvas.get("id") if isinstance(canvas, dict) else None
        canvas_id_text = str(canvas_id).strip() if isinstance(canvas_id, str) else ""
        id_tail = canvas_id_text.split("/")[-1] if canvas_id_text else ""
        custom_name = None
        if image_name_path and isinstance(canvas, dict):
            nested_value = get_nested_value(canvas, image_name_path)
            nested_text = as_non_empty_text(nested_value)
            if nested_text:
                custom_name = nested_text

        base_name_source = custom_name or id_tail or label
        base_name = sanitize_pair_base_name(base_name_source)
        if not custom_name:
            base_name = sanitize_pair_base_name(f"{index + 1:04d}_{base_name}")

        image_url = None
        if image_url_path and isinstance(canvas, dict):
            image_url_value = get_nested_value(canvas, image_url_path)
            base_url_text = as_non_empty_text(image_url_value)
            if base_url_text:
                image_url = join_iiif_image_url(base_url_text, custom_name or "", image_suffix or "")

        if not image_url:
            service_base = extract_iiif_service_base_url(canvas)
            if service_base and (custom_name or image_suffix):
                image_url = join_iiif_image_url(service_base, custom_name or "", image_suffix or "")

        if not image_url:
            image_url = extract_iiif_canvas_image_url(canvas)

        if not image_url:
            continue

        width = canvas.get("width") if isinstance(canvas, dict) else None
        height = canvas.get("height") if isinstance(canvas, dict) else None
        is_landscape = isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > height

        if is_landscape:
            left_url = build_iiif_region_url(image_url, "pct:0,0,50,100")
            right_url = build_iiif_region_url(image_url, "pct:50,0,50,100")

            elements.append({
                "name": f"{base_name}_left",
                "image": left_url,
                "json": f"{base_name}_left.json",
            })
            elements.append({
                "name": f"{base_name}_right",
                "image": right_url,
                "json": f"{base_name}_right.json",
            })
            continue

        elements.append({
            "name": base_name,
            "image": image_url,
            "json": f"{base_name}.json",
        })

    return elements


def list_ner_settings_files() -> list[str]:
    if not NER_SETTINGS_DIR.exists() or not NER_SETTINGS_DIR.is_dir():
        return []

    files: list[str] = []
    for path in sorted(NER_SETTINGS_DIR.glob("*.json")):
        if path.is_file():
            files.append(path.name)

    return files


def list_ner_cluster_profile_files(cut_images_dir: Path) -> list[str]:
    if not cut_images_dir.exists() or not cut_images_dir.is_dir():
        return []

    files: list[str] = []
    for path in sorted(cut_images_dir.glob("ner-clusters--*.json")):
        if path.is_file():
            files.append(path.name)

    return files


def normalize_projects_settings(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []

    normalized_projects: list[dict[str, object]] = []

    for project in payload:
        if not isinstance(project, dict):
            continue

        project_name = as_non_empty_text(project.get("name"))
        if not project_name:
            continue

        raw_subprojects = project.get("subprojects")
        if not isinstance(raw_subprojects, list):
            raw_subprojects = []

        subprojects: list[dict[str, object]] = []
        for subproject in raw_subprojects:
            if not isinstance(subproject, dict):
                continue

            subproject_name = as_non_empty_text(subproject.get("name"))
            if not subproject_name:
                continue

            raw_type = as_non_empty_text(subproject.get("type"))
            subproject_type = (raw_type or "local").lower()
            if subproject_type not in ALLOWED_SUBPROJECT_TYPES:
                continue

            entry: dict[str, object] = {
                "name": subproject_name,
                "type": subproject_type,
            }

            documents = as_non_empty_text(subproject.get("documents"))
            if documents:
                entry["documents"] = documents

            path_value = as_non_empty_text(subproject.get("path"))
            if path_value:
                entry["path"] = path_value

            manifest_value = as_non_empty_text(subproject.get("manifest"))
            if manifest_value:
                entry["manifest"] = manifest_value

            settings_value = as_non_empty_text(subproject.get("settings"))
            if settings_value:
                entry["settings"] = settings_value

            cover_settings_value = as_non_empty_text(subproject.get("coversettings"))
            if cover_settings_value is None:
                cover_settings_value = as_non_empty_text(subproject.get("cover-settings"))
            if cover_settings_value is None:
                cover_settings_value = as_non_empty_text(subproject.get("coverSettings"))
            if cover_settings_value:
                entry["coversettings"] = cover_settings_value

            image_name_path = as_non_empty_text(subproject.get("img-name-path-in-manifest"))
            if image_name_path:
                entry["img-name-path-in-manifest"] = image_name_path

            image_url_path = as_non_empty_text(subproject.get("img-url"))
            if image_url_path is None:
                image_url_path = as_non_empty_text(subproject.get("img-url:"))
            if image_url_path:
                entry["img-url"] = image_url_path

            image_suffix = as_non_empty_text(subproject.get("img-suffixe"))
            if image_suffix:
                entry["img-suffixe"] = image_suffix

            subprojects.append(entry)

        normalized_projects.append({
            "name": project_name,
            "subprojects": subprojects,
        })

    return normalized_projects


def load_projects_settings() -> dict[str, object]:
    settings_path = PROJECTS_SETTINGS_PATH
    if not settings_path.exists() and LEGACY_PROJECTS_SETTINGS_PATH.exists():
        settings_path = LEGACY_PROJECTS_SETTINGS_PATH

    if not settings_path.exists():
        return {"projects": []}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "projects": [],
            "error": "Invalid projects settings JSON",
            "details": str(error),
            "path": settings_path.name,
        }

    return {
        "projects": normalize_projects_settings(payload),
        "path": settings_path.name,
    }


def save_projects_settings(payload: object) -> dict[str, object]:
    normalized = normalize_projects_settings(payload)
    target_path = PROJECTS_SETTINGS_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "projects": len(normalized),
        "path": str(target_path),
    }


def resolve_scoped_directory(raw_dir: str | None) -> Path | None:
    if raw_dir is None:
        return CUT_IMAGES_DIR.resolve()

    normalized = raw_dir.strip().replace("\\", "/")
    if not normalized:
        return CUT_IMAGES_DIR.resolve()

    if normalized.startswith("/") or re.match(r"^[a-zA-Z]:", normalized):
        return None

    workspace_root = ROOT_DIR.parent.resolve()

    candidate_paths = [
        (ROOT_DIR / normalized).resolve(),
        (workspace_root / normalized).resolve(),
    ]

    for resolved in candidate_paths:
        if workspace_root not in resolved.parents and resolved != workspace_root:
            continue
        return resolved

    return None


def resolve_column_settings_path_for_subproject(scoped_dir: Path) -> Path:
    default_candidates = [
        COLUMN_SETTINGS_DIR / "column-settings.json",
        COLUMN_SETTINGS_PATH,
        LEGACY_COLUMN_SETTINGS_PATH,
    ]

    projects_payload = load_projects_settings()
    projects = projects_payload.get("projects")
    if isinstance(projects, list):
        scoped_resolved = scoped_dir.resolve()
        for project in projects:
            if not isinstance(project, dict):
                continue

            subprojects = project.get("subprojects")
            if not isinstance(subprojects, list):
                continue

            for subproject in subprojects:
                if not isinstance(subproject, dict):
                    continue

                subproject_path = as_non_empty_text(subproject.get("path"))
                if not subproject_path:
                    continue

                subproject_dir = resolve_scoped_directory(subproject_path)
                if subproject_dir is None or subproject_dir.resolve() != scoped_resolved:
                    continue

                settings_value = as_non_empty_text(subproject.get("settings"))
                if settings_value:
                    settings_path = Path(settings_value)
                    if settings_path.is_absolute():
                        return settings_path

                    if settings_value.startswith("./") or settings_value.startswith("../"):
                        return (ROOT_DIR / settings_path).resolve()

                    if "/" in settings_value or "\\" in settings_value:
                        return (ROOT_DIR / settings_path).resolve()

                    return (COLUMN_SETTINGS_DIR / settings_path).resolve()

    for candidate in default_candidates:
        if candidate.exists():
            return candidate

    return default_candidates[0]


def resolve_cover_settings_path_for_subproject(scoped_dir: Path) -> Path | None:
    projects_payload = load_projects_settings()
    projects = projects_payload.get("projects")
    if not isinstance(projects, list):
        return None

    scoped_resolved = scoped_dir.resolve()
    for project in projects:
        if not isinstance(project, dict):
            continue

        subprojects = project.get("subprojects")
        if not isinstance(subprojects, list):
            continue

        for subproject in subprojects:
            if not isinstance(subproject, dict):
                continue

            subproject_path = as_non_empty_text(subproject.get("path"))
            if not subproject_path:
                continue

            subproject_dir = resolve_scoped_directory(subproject_path)
            if subproject_dir is None or subproject_dir.resolve() != scoped_resolved:
                continue

            settings_value = as_non_empty_text(subproject.get("coversettings"))
            if not settings_value:
                return None

            settings_path = Path(settings_value)
            if settings_path.is_absolute():
                return settings_path

            if settings_value.startswith("./") or settings_value.startswith("../"):
                return (ROOT_DIR / settings_path).resolve()

            return (ROOT_DIR / settings_path).resolve()

    return None


def load_cover_settings_with_source(scoped_dir: Path) -> dict[str, object]:
    settings_path = resolve_cover_settings_path_for_subproject(scoped_dir)
    if settings_path is None:
        return {
            "ok": True,
            "settingsPath": None,
            "coverSettings": None,
        }

    workspace_root = ROOT_DIR.parent.resolve()
    resolved = settings_path.resolve()
    if workspace_root not in resolved.parents and resolved != workspace_root:
        return {
            "ok": False,
            "settingsPath": str(resolved),
            "error": "Cover settings path is outside workspace",
        }

    if not resolved.exists() or not resolved.is_file():
        return {
            "ok": False,
            "settingsPath": str(resolved),
            "error": "Cover settings file not found",
        }

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "settingsPath": str(resolved),
            "error": f"Invalid cover settings JSON: {error}",
        }

    return {
        "ok": True,
        "settingsPath": str(resolved),
        "coverSettings": payload,
    }


def get_query_first(parsed_query: str, key: str) -> str | None:
    query = parse_qs(parsed_query)
    values = query.get(key)
    if not values:
        return None
    value = values[0]
    return value if isinstance(value, str) else None


def load_column_settings(scoped_dir: Path | None = None) -> dict[str, object]:
    effective_dir = scoped_dir or CUT_IMAGES_DIR
    settings_path = resolve_column_settings_path_for_subproject(effective_dir)

    if not settings_path.exists():
        return {"imageFormat": DEFAULT_IMAGE_FORMAT, "columnTypes": {}}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"imageFormat": DEFAULT_IMAGE_FORMAT, "columnTypes": {}}

    if not isinstance(payload, dict):
        return {"imageFormat": DEFAULT_IMAGE_FORMAT, "columnTypes": {}}

    raw_image_format = payload.get("imageFormat", DEFAULT_IMAGE_FORMAT)
    image_format = (
        raw_image_format
        if isinstance(raw_image_format, str) and raw_image_format in ALLOWED_IMAGE_FORMATS
        else DEFAULT_IMAGE_FORMAT
    )

    raw_column_types = payload.get("columnTypes", {})
    if not isinstance(raw_column_types, dict):
        return {"imageFormat": image_format, "columnTypes": {}}

    normalized: dict[str, str] = {}
    for key, value in raw_column_types.items():
        if isinstance(key, str) and isinstance(value, str) and value in ALLOWED_COLUMN_TYPES:
            normalized[key] = value

    return {"imageFormat": image_format, "columnTypes": normalized}


def load_column_settings_with_source(scoped_dir: Path | None = None) -> dict[str, object]:
    effective_dir = scoped_dir or CUT_IMAGES_DIR
    settings_path = resolve_column_settings_path_for_subproject(effective_dir)
    payload = load_column_settings(effective_dir)
    return {
        **payload,
        "settingsPath": str(settings_path),
    }


def build_contribuable_clusters(cut_images_dir: Path = CUT_IMAGES_DIR) -> dict[str, object]:
    grouped: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    scanned_files = 0
    used_files = 0
    row_count = 0
    matched_rows = 0

    if not cut_images_dir.exists():
        return {
            "scannedFiles": 0,
            "usedFiles": 0,
            "rows": 0,
            "matchedRows": 0,
            "groups": [],
        }

    for json_path in sorted(cut_images_dir.glob("*.json")):
        scanned_files += 1

        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, list):
            continue

        file_used = False

        for row_number, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                continue

            row_count += 1

            numero_liste_raw = get_row_field_value(row, "numeroliste")
            contribuable_raw = get_row_field_value(row, "contribuable")
            adresse_contribuable_raw = get_row_field_value(row, "adressecontribuable")

            numero_liste = clean_numero_liste(numero_liste_raw)
            contribuable = as_non_empty_text(contribuable_raw)
            adresse_contribuable = as_non_empty_text(adresse_contribuable_raw)

            if not numero_liste or not contribuable:
                continue

            contributors = grouped[numero_liste]
            contributor_entry = contributors.get(contribuable)
            if not contributor_entry:
                contributor_entry = {"count": 0, "sources": [], "adresseContribuable": []}
                contributors[contribuable] = contributor_entry

            contributor_entry["count"] = int(contributor_entry["count"]) + 1
            addresses = contributor_entry.get("adresseContribuable")
            if isinstance(addresses, list) and adresse_contribuable and adresse_contribuable not in addresses:
                addresses.append(adresse_contribuable)
            sources = contributor_entry["sources"]
            if isinstance(sources, list):
                sources.append({
                    "json": json_path.name,
                    "rowNumber": row_number,
                })
            matched_rows += 1
            file_used = True

        if file_used:
            used_files += 1

    groups = []
    total_contribuables = 0

    for numero_liste in sorted(grouped.keys(), key=numero_liste_sort_key):
        contributors = grouped[numero_liste]
        sorted_contributors = sorted(
            contributors.items(),
            key=lambda item: (-int(item[1].get("count", 0)), item[0].casefold()),
        )

        total = sum(int(data.get("count", 0)) for _, data in sorted_contributors)
        total_contribuables += len(sorted_contributors)

        groups.append(
            {
                "numeroListe": numero_liste,
                "total": total,
                "contributors": [
                    {
                        "contribuable": name,
                        "count": int(data.get("count", 0)),
                        "sources": data.get("sources", []),
                        "adresseContribuable": data.get("adresseContribuable", []),
                    }
                    for name, data in sorted_contributors
                ],
            }
        )

    return {
        "scannedFiles": scanned_files,
        "usedFiles": used_files,
        "rows": row_count,
        "matchedRows": matched_rows,
        "totalGroups": len(groups),
        "totalContribuables": total_contribuables,
        "groups": groups,
    }


def build_autocomplete_fields(cut_images_dir: Path = CUT_IMAGES_DIR) -> dict[str, object]:
    scanned_files = 0
    used_files = 0
    row_count = 0
    matched_values = 0
    value_sets: dict[str, set[str]] = defaultdict(set)

    if not cut_images_dir.exists():
        return {
            "scannedFiles": 0,
            "usedFiles": 0,
            "rows": 0,
            "matchedValues": 0,
            "fields": {},
        }

    for json_path in sorted(cut_images_dir.glob("*.json")):
        scanned_files += 1

        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, list):
            continue

        file_used = False

        for row in payload:
            if not isinstance(row, dict):
                continue

            row_count += 1

            for key, value in row.items():
                if not isinstance(key, str) or key == "rowIndex":
                    continue

                if isinstance(value, (dict, list)):
                    continue

                text = as_non_empty_text(value)
                if text is None:
                    continue

                bucket = value_sets[key]
                if text in bucket:
                    continue

                bucket.add(text)
                matched_values += 1
                file_used = True

        if file_used:
            used_files += 1

    fields = {
        key: sorted(values, key=lambda item: item.casefold())
        for key, values in value_sets.items()
    }

    return {
        "scannedFiles": scanned_files,
        "usedFiles": used_files,
        "rows": row_count,
        "matchedValues": matched_values,
        "fields": fields,
    }


def validate_column_settings_payload(payload: object) -> tuple[bool, str, dict[str, object]]:
    if not isinstance(payload, dict):
        return False, "Payload must be a JSON object", {
            "imageFormat": DEFAULT_IMAGE_FORMAT,
            "columnTypes": {},
        }

    image_format = payload.get("imageFormat", DEFAULT_IMAGE_FORMAT)
    if not isinstance(image_format, str) or image_format not in ALLOWED_IMAGE_FORMATS:
        return False, "imageFormat must be one of: single, double", {
            "imageFormat": DEFAULT_IMAGE_FORMAT,
            "columnTypes": {},
        }

    column_types = payload.get("columnTypes")
    if column_types is None:
        column_types = {}

    if not isinstance(column_types, dict):
        return False, "columnTypes must be an object", {
            "imageFormat": image_format,
            "columnTypes": {},
        }

    normalized: dict[str, str] = {}
    for key, value in column_types.items():
        if not isinstance(key, str):
            return False, "columnTypes keys must be strings", {
                "imageFormat": image_format,
                "columnTypes": {},
            }
        if not isinstance(value, str) or value not in ALLOWED_COLUMN_TYPES:
            return False, f"Invalid type for column '{key}'", {
                "imageFormat": image_format,
                "columnTypes": {},
            }
        normalized[key] = value

    return True, "", {"imageFormat": image_format, "columnTypes": normalized}


class ViewerHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return

        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/projects-settings":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return

            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400, "Invalid JSON payload")
                return

            if not isinstance(payload, list):
                self.send_error(400, "Payload must be a JSON array")
                return

            try:
                result = save_projects_settings(payload)
            except OSError:
                self.send_error(500, "Could not save projects settings")
                return

            self._send_json(result)
            return

        scoped_dir = resolve_scoped_directory(get_query_first(parsed.query, "dir"))

        if scoped_dir is None:
            self.send_error(400, "Invalid dir parameter")
            return

        if route == "/api/column-settings":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return

            raw_body = self.rfile.read(content_length)

            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400, "Invalid JSON payload")
                return

            ok, error_message, normalized_payload = validate_column_settings_payload(payload)
            if not ok:
                self.send_error(400, error_message)
                return

            settings_path = resolve_column_settings_path_for_subproject(scoped_dir)

            try:
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                settings_path.write_text(
                    json.dumps(normalized_payload, ensure_ascii=False, indent=4) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                self.send_error(500, "Could not save column settings")
                return

            self._send_json({"ok": True, "saved": str(settings_path), "settingsPath": str(settings_path)})
            return

        if route == "/api/classify-elements":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return

            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400, "Invalid JSON payload")
                return

            if not isinstance(payload, dict):
                self.send_error(400, "Payload must be a JSON object")
                return

            raw_pair_names = payload.get("pairNames")
            pair_names: list[str] | None = None
            if raw_pair_names is not None:
                if not isinstance(raw_pair_names, list):
                    self.send_error(400, "pairNames must be an array")
                    return
                pair_names = [str(item) for item in raw_pair_names if item is not None]

            model_path_text = as_non_empty_text(payload.get("modelPath")) or "models/classification/best.pt"

            raw_confidence = payload.get("confidence", 0.25)
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                self.send_error(400, "confidence must be a number")
                return

            confidence = max(0.0, min(1.0, confidence))

            try:
                result = classify_elements_with_yolo(scoped_dir, pair_names, model_path_text, confidence)
            except Exception as error:
                self.send_error(500, f"Classification failed: {error}")
                return

            self._send_json(result)
            return

        if not route.startswith("/api/save/"):
            self.send_error(404, "Not found")
            return

        filename = unquote(route[len("/api/save/") :]).lstrip("/")
        target_path = (scoped_dir / filename).resolve()
        cut_images_root = scoped_dir.resolve()

        if target_path.parent != cut_images_root:
            self.send_error(403, "Forbidden")
            return

        if target_path.suffix.lower() != ".json":
            self.send_error(400, "Only JSON files can be saved")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return

        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON payload")
            return

        if not isinstance(payload, (list, dict)):
            self.send_error(400, "Payload must be a JSON array or object")
            return

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )
        except OSError:
            self.send_error(500, "Could not save JSON file")
            return
        self._send_json({"ok": True, "saved": target_path.name})

    def do_PUT(self) -> None:
        self.do_POST()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        scoped_dir = resolve_scoped_directory(get_query_first(parsed.query, "dir"))

        if scoped_dir is None:
            self.send_error(400, "Invalid dir parameter")
            return

        if route in {"/", "/index.html"}:
            self._send_file(ROOT_DIR / "index.html")
            return

        if route in {"/column-settings", "/column-settings.html"}:
            self._send_file(ROOT_DIR / "column-settings.html")
            return

        if route in {"/page-classification", "/page-classification.html"}:
            self._send_file(ROOT_DIR / "page-classification.html")
            return

        if route in {"/cover-annotator", "/cover-annotator.html"}:
            self._send_file(ROOT_DIR / "cover-annotator.html")
            return

        if route in {"/iiif-command", "/iiif-command.html"}:
            self._send_file(ROOT_DIR / "iiif-command.html")
            return

        if route in {"/projects-settings", "/projects-settings.html"}:
            self._send_file(ROOT_DIR / "projects-settings.html")
            return

        if route in {"/ner-and-clustering", "/ner-and-clustering.html"}:
            self._send_file(ROOT_DIR / "ner-and-clustering.html")
            return

        if route == "/column-settings.json":
            self._send_json(load_column_settings(scoped_dir))
            return

        if route == "/projects-settings.json":
            if PROJECTS_SETTINGS_PATH.exists():
                self._send_file(PROJECTS_SETTINGS_PATH)
                return
            if LEGACY_PROJECTS_SETTINGS_PATH.exists():
                self._send_file(LEGACY_PROJECTS_SETTINGS_PATH)
                return
            self.send_error(404, "projects-settings.json not found")
            return

        if route == "/projects-settings.json":
            if LEGACY_PROJECTS_SETTINGS_PATH.exists():
                self._send_file(LEGACY_PROJECTS_SETTINGS_PATH)
                return
            if PROJECTS_SETTINGS_PATH.exists():
                self._send_file(PROJECTS_SETTINGS_PATH)
                return
            self.send_error(404, "projects-settings.json not found")
            return

        if route == "/api/elements":
            self._send_json(load_elements_manifest(scoped_dir))
            return

        if route == "/api/iiif-elements":
            manifest_url = get_query_first(parsed.query, "manifest")
            manifest_text = as_non_empty_text(manifest_url)
            if manifest_text is None:
                self.send_error(400, "Missing manifest query parameter")
                return

            image_name_path = as_non_empty_text(get_query_first(parsed.query, "imgNamePath"))
            image_url_path = as_non_empty_text(get_query_first(parsed.query, "imgUrlPath"))
            image_suffix = as_non_empty_text(get_query_first(parsed.query, "imgSuffix"))

            try:
                elements = build_iiif_elements(manifest_text, image_name_path, image_url_path, image_suffix)
                if scoped_dir is not None:
                    try:
                        sync_elements_manifest(scoped_dir, elements)
                        ensure_pair_json_files(scoped_dir, elements)
                    except OSError:
                        pass
                self._send_json(elements)
            except Exception as error:
                self.send_error(502, f"Could not load IIIF manifest: {error}")
            return

        if route == "/api/projects-settings":
            self._send_json(load_projects_settings())
            return

        if route == "/api/column-settings":
            self._send_json(load_column_settings_with_source(scoped_dir))
            return

        if route == "/api/contribuable-clusters":
            self._send_json(build_contribuable_clusters(scoped_dir))
            return

        if route == "/api/autocomplete-fields":
            self._send_json(build_autocomplete_fields(scoped_dir))
            return

        if route == "/api/cover-settings":
            payload = load_cover_settings_with_source(scoped_dir)
            self._send_json(payload, status=200 if payload.get("ok") else 404)
            return

        if route == "/api/ner-settings":
            self._send_json({"files": list_ner_settings_files()})
            return

        if route == "/api/ner-cluster-files":
            self._send_json({"files": list_ner_cluster_profile_files(scoped_dir)})
            return

        if route == "/api/image-proxy":
            image_url = as_non_empty_text(get_query_first(parsed.query, "url"))
            if image_url is None:
                self.send_error(400, "Missing url query parameter")
                return

            if not re.match(r"^https?://", image_url, re.IGNORECASE):
                self.send_error(400, "Only http(s) URLs are allowed")
                return

            try:
                request = Request(
                    image_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                        "Referer": "https://archives06.fr/",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                with urlopen(request, timeout=25) as response:
                    content = response.read()
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
            except Exception as error:
                self.send_error(502, f"Could not fetch remote image: {error}")
                return

            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if route.startswith("/data/"):
            relative = unquote(route[len("/data/") :]).lstrip("/")
            file_path = (scoped_dir / relative).resolve()

            if file_path.parent != scoped_dir.resolve():
                self.send_error(403, "Forbidden")
                return

            self._send_file(file_path)
            return

        if route.startswith("/ner-settings/"):
            relative = unquote(route[len("/ner-settings/") :]).lstrip("/")
            file_path = (NER_SETTINGS_DIR / relative).resolve()

            if file_path.parent != NER_SETTINGS_DIR.resolve():
                self.send_error(403, "Forbidden")
                return

            self._send_file(file_path)
            return

        self.send_error(404, "Not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR side-by-side viewer")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"Viewer running on http://{args.host}:{args.port}")
    print(f"Reading files from {CUT_IMAGES_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
