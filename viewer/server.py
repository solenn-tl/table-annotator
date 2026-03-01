from __future__ import annotations

import argparse
from collections import defaultdict
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parent
CUT_IMAGES_DIR = ROOT_DIR.parent / "cut_images"
COLUMN_SETTINGS_PATH = ROOT_DIR / "column-settings.json"
LEGACY_COLUMN_SETTINGS_PATH = ROOT_DIR.parent / "column-settings.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
ALLOWED_COLUMN_TYPES = {"none", "sequence", "autocomplete", "both"}
ALLOWED_IMAGE_FORMATS = {"single", "double"}
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


def build_pairs() -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []

    if not CUT_IMAGES_DIR.exists():
        return pairs

    json_by_stem = {path.stem: path for path in CUT_IMAGES_DIR.glob("*.json")}

    for image_path in sorted(CUT_IMAGES_DIR.iterdir()):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        json_path = json_by_stem.get(image_path.stem)
        if not json_path:
            continue

        pairs.append(
            {
                "name": image_path.stem,
                "image": image_path.name,
                "json": json_path.name,
            }
        )

    return pairs


def load_column_settings() -> dict[str, object]:
    settings_path = COLUMN_SETTINGS_PATH
    if not settings_path.exists() and LEGACY_COLUMN_SETTINGS_PATH.exists():
        settings_path = LEGACY_COLUMN_SETTINGS_PATH

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


def build_contribuable_clusters() -> dict[str, object]:
    grouped: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    scanned_files = 0
    used_files = 0
    row_count = 0
    matched_rows = 0

    if not CUT_IMAGES_DIR.exists():
        return {
            "scannedFiles": 0,
            "usedFiles": 0,
            "rows": 0,
            "matchedRows": 0,
            "groups": [],
        }

    for json_path in sorted(CUT_IMAGES_DIR.glob("*.json")):
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


def build_autocomplete_fields() -> dict[str, object]:
    scanned_files = 0
    used_files = 0
    row_count = 0
    matched_values = 0
    value_sets: dict[str, set[str]] = defaultdict(set)

    if not CUT_IMAGES_DIR.exists():
        return {
            "scannedFiles": 0,
            "usedFiles": 0,
            "rows": 0,
            "matchedValues": 0,
            "fields": {},
        }

    for json_path in sorted(CUT_IMAGES_DIR.glob("*.json")):
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

            try:
                COLUMN_SETTINGS_PATH.write_text(
                    json.dumps(normalized_payload, ensure_ascii=False, indent=4) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                self.send_error(500, "Could not save column settings")
                return

            self._send_json({"ok": True, "saved": COLUMN_SETTINGS_PATH.name})
            return

        if not route.startswith("/api/save/"):
            self.send_error(404, "Not found")
            return

        filename = unquote(route[len("/api/save/") :]).lstrip("/")
        target_path = (CUT_IMAGES_DIR / filename).resolve()
        cut_images_root = CUT_IMAGES_DIR.resolve()

        if target_path.parent != cut_images_root:
            self.send_error(403, "Forbidden")
            return

        if target_path.suffix.lower() != ".json":
            self.send_error(400, "Only JSON files can be saved")
            return

        if not target_path.exists():
            self.send_error(404, "JSON file not found")
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

        if not isinstance(payload, list):
            self.send_error(400, "Payload must be a JSON array")
            return

        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
        self._send_json({"ok": True, "saved": target_path.name})

    def do_PUT(self) -> None:
        self.do_POST()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route in {"/", "/index.html"}:
            self._send_file(ROOT_DIR / "index.html")
            return

        if route in {"/column-settings", "/column-settings.html"}:
            self._send_file(ROOT_DIR / "column-settings.html")
            return

        if route == "/column-settings.json":
            self._send_json(load_column_settings())
            return

        if route == "/api/pairs":
            self._send_json(build_pairs())
            return

        if route == "/api/column-settings":
            self._send_json(load_column_settings())
            return

        if route == "/api/contribuable-clusters":
            self._send_json(build_contribuable_clusters())
            return

        if route == "/api/autocomplete-fields":
            self._send_json(build_autocomplete_fields())
            return

        if route.startswith("/data/"):
            relative = unquote(route[len("/data/") :]).lstrip("/")
            file_path = (CUT_IMAGES_DIR / relative).resolve()

            if file_path.parent != CUT_IMAGES_DIR.resolve():
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
