# Viewer Documentation

The `viewer/` app is a lightweight web UI and API server to:

- annotate table rows with bounding boxes,
- review and verify page classes,
- annotate cover-page metadata,
- prepare command lines for data import and preprocessing scripts.

All pages are served by `viewer/server.py`.

## Server Launch

Run from repository root (`D:\Code\ocr`):

```powershell
# Activate virtual environment (example)
& .\ocr-test\Scripts\Activate.ps1

# Start server on default host/port
python .\viewer\server.py
```

Default URL: `http://127.0.0.1:8000`

You can override bind settings:

```powershell
python .\viewer\server.py --host 0.0.0.0 --port 8080
```

Main routes:

- `http://127.0.0.1:8000/index.html` (Table annotation)
- `http://127.0.0.1:8000/page-classification.html`
- `http://127.0.0.1:8000/cover-annotator.html`
- `http://127.0.0.1:8000/ner-and-clustering.html`
- `http://127.0.0.1:8000/projects-settings.html`
- `http://127.0.0.1:8000/iiif-command.html`
- `http://127.0.0.1:8000/iiif-arkotheque-command.html`
- `http://127.0.0.1:8000/classif-command.html`
- `http://127.0.0.1:8000/local-pretreatement-command.html`

## Page-By-Page Guide

### 1) Table Annotation (`index.html`)

Purpose:

- edit row-based OCR annotations stored in sidecar JSON files,
- draw/edit `bbox` on page images,
- use clustering/histogram tools for QA.

Data source:

- loads elements from `/api/elements` (or IIIF manifest for `iiif` subprojects),
- saves row JSON with `/api/save/<json-file>`,
- uses `/api/column-settings`, `/api/contribuable-clusters`, `/api/autocomplete-fields`.

### 2) Page Classification (`page-classification.html`)

Purpose:

- review class predictions and assign `verify_class` for each page.

Data source:

- pages from `/api/elements` (or `/data/elements.json` fallback),
- predictions from `/data/classification.json`.

### 3) Cover Annotation (`cover-annotator.html`)

Purpose:

- annotate cover pages (`ets_couv`) into `covers.json`, with per-field text + bbox.

Dynamic form fields:

- each subproject can declare a `coversettings` path in `projects-settings.json`,
- the page loads this file via `/api/cover-settings` and builds the form dynamically.

### 4) NER and Clustering (`ner-and-clustering.html`)

Purpose:

- review and tune NER extraction,
- create and inspect clustering profiles for selected fields.

### 5) CLI Command Helpers

Purpose:

- build ready-to-run commands for each script in `viewer/cli/`.

Available pages:

- `iiif-command.html`: command builder for `viewer/cli/iiif.py`.
- `iiif-arkotheque-command.html`: command builder for `viewer/cli/iiif-arkotheque.py`.
- `classif-command.html`: command builder for `viewer/cli/classif.py`.
- `local-pretreatement-command.html`: command builder for `viewer/cli/local-pretreatement.py`.

Shared behavior:

- `Build command` updates the preview.
- `Copy command` copies the generated command to clipboard.
- pages generate commands only and do not execute scripts.

### 6) Projects Settings Editor (`projects-settings.html`)

Purpose:

- edit `viewer/projects-settings.json` from the browser,
- add/remove projects,
- add/remove subprojects inside each project.

## Command Line Scripts

Scripts live in `viewer/cli/`.

### `viewer/server.py`

Runs the local HTTP server for all viewer pages and command helpers.

```powershell
python .\viewer\server.py [--host 127.0.0.1] [--port 8000]
```

### `viewer/cli/local-pretreatement.py`

Prepares local images for annotation.

```powershell
python .\viewer\cli\local-pretreatement.py <folder_path> <save_dir> [--create-json-and-elements]
```

### `viewer/cli/iiif.py`

Builds local annotation files from a Ligeo IIIF manifest URL.

```powershell
python .\viewer\cli\iiif.py <manifest_url> [--output-dir .] [--items-output items.json] [--elements-output elements.json] [--manifest-output manifest.json]
```

### `viewer/cli/iiif-arkotheque.py`

Builds local annotation files by iterating Arkotheque `info.json` indices.

```powershell
python .\viewer\cli\iiif-arkotheque.py <info_url> <image_count> [--output-dir .] [--items-output items.json] [--elements-output elements.json] [--infos-output infos.json]
```

### `viewer/cli/classif.py`

Batch classifies page images with a YOLO classification model.

```powershell
python .\viewer\cli\classif.py [--elements-path <elements.json>] [--output-path <classification.json>] [--model-path <best.pt>] [--limit 100] [--iiif-width 800] [--device auto]
```

Detailed options and examples for each script are documented in `viewer/cli/README.md`.

## Data Files

Expected per subproject folder (for example `cut_images/<project>/<subproject>/`):

- `elements.json`: list of `{name, image, json}` entries (optional `class`).
- `<page>.json`: annotation rows array.
- `classification.json`: predicted/verified classes by `name`.
- `covers.json`: cover metadata entries for pages classified as `ets_couv`.

`bbox` shape used by annotation rows and cover fields:

```json
{
  "x": 10,
  "y": 20,
  "width": 120,
  "height": 40
}
```