# Viewer Documentation

The `viewer/` app is a lightweight web UI and API server to:

- annotate table rows with bounding boxes,
- review and verify page classes,
- annotate cover-page metadata,
- generate helper commands for IIIF imports.

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
- `http://127.0.0.1:8000/iiif-command.html`
- `http://127.0.0.1:8000/projects-settings.html`

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

Top toolbar highlights:

- `Document`: choose active image/JSON pair.
- `Add row`, `Add rows`, `Delete row`.
- `Fill with numeric sequence`: extrapolates from 2 consecutive numeric seed cells.
- Batch tools: `Set batch <IDEM>`, `Set batch <EMPTY>`, `Clear batch value`, `Apply to selected range`.
- `Integers -> lettres`: converts integer range values into French words.
- `Draw bbox`, `Edit bbox corners`, `Normalize bbox width`, `Batch draw bbox`.
- `Save JSON` with save mode badge (`server`, `local`, `unknown`).

Editing and navigation:

- `Shift+click` in same column creates a vertical range.
- `Shift+Arrow` moves focus to adjacent cell.
- Drag rows (unless row reorder is locked).
- Mouse wheel zooms image at cursor.
- Click-drag on image pans viewport (outside draw mode).
- Clicking a bbox selects the matching row and zooms to it.

Panels:

- Column settings panel: per-column mode `none`, `sequence`, `autocomplete`, `both`.
- `Contribuable clusters by numeroListe`: chart/list, zoom, collapse, refresh.
- `Cluster by custom field`: fuzzy grouping via normalized Levenshtein threshold.
- `Histogram by custom field`: distribution view for selected field.

Classification-aware filtering:

- if `classification.json` exists, this page filters to rows with class `ets_tab_p1`.

### 2) Page Classification (`page-classification.html`)

Purpose:

- review class predictions and assign `verify_class` for each page.

Data source:

- pages from `/api/elements` (or `/data/elements.json` fallback),
- predictions from `/data/classification.json`.

What you do:

- choose `Project` and `Subproject`,
- inspect card thumbnails and predicted class/probability,
- add new class labels directly from the page (`Add class`) when starting from scratch,
- set `Verified class` dropdown per card,
- click `Save verified classes`.

What is saved:

- writes/updates `classification.json` through `/api/save/classification.json`,
- stores `verify_class` by page `name`, preserving existing rows and fields.

Notes:

- if backend is unreachable, status hints to launch `server.py` and open via HTTP.
- remote IIIF image thumbs are proxied through `/api/image-proxy`.

### 3) Cover Annotation (`cover-annotator.html`)

Purpose:

- annotate cover pages (`ets_couv`) into `covers.json`, with per-field text + bbox.

Dynamic form fields:

- each subproject can declare a `coversettings` path in `projects-settings.json`.
- the page loads this file via `/api/cover-settings` and builds the form dynamically.
- fallback: if the file is missing/invalid, default cadastre fields are used.

Example subproject setting:

```json
{
  "name": "Ouessant",
  "path": "./../cut_images/finistere/ouessant",
  "coversettings": "cover-settings/cover-settings-cadastre.json"
}
```

Example cover settings file:

```json
{
  "fields": [
    "commune",
    "departement",
    "arrondissement",
    "canton",
    "sectionLettre",
    "sectionTitre",
    "intituleRegistre"
  ]
}
```

How pages are selected:

- loads `elements.json`,
- reads `classification.json`,
- keeps only pages whose resolved class is `ets_couv`.

Fields:

- `commune`
- `departement`
- `arrondissement`
- `canton`
- `sectionLettre`
- `sectionTitre`
- `intituleRegistre`

BBox workflow:

- select active field,
- drag on image to draw bbox,
- color-coded rectangles per field,
- `Clear active field bbox` removes current field bbox.

Save behavior:

- primary: POST to `/api/save/covers.json`,
- fallback: downloads `covers.json` in browser if server save is unavailable.

### 4) IIIF Command Helper (`iiif-command.html`)

Purpose:

- build a ready-to-run command for `viewer/iiif.py`.

Inputs:

- manifest URL,
- output directory,
- output filenames for `items.json`, `elements.json`, and optional manifest copy.

Actions:

- `Build command`: updates preview.
- `Copy command`: copies CLI command to clipboard.

This page does not run the import itself; it generates the command to execute in terminal.

### 5) Projects Settings Editor (`projects-settings.html`)

Purpose:

- edit `viewer/projects-settings.json` from the browser,
- add/remove projects,
- add/remove subprojects inside each project.

Capabilities:

- form fields for `name`, `type`, `documents`, `path`, `settings`, `coversettings`, `manifest`.
- live JSON preview of the payload to save.
- `Save projects-settings.json` persists through `POST /api/projects-settings`.

## Command Line Scripts

### `viewer/server.py`

Runs the local HTTP server for all viewer pages.

```powershell
python .\viewer\server.py [--host 127.0.0.1] [--port 8000]
```

### `viewer/cli.py`

Prepares local images for annotation.

Behavior:

- scans source folder recursively for image files,
- splits landscape images into `_left` and `_right`,
- copies portrait images unchanged,
- optionally creates missing sidecar JSON files and `elements.json`.

Usage:

```powershell
python .\viewer\cli.py <folder_path> <save_dir> [--create-json-and-elements]
```

Example:

```powershell
python .\viewer\cli.py .\images .\cut_images --create-json-and-elements
```

### `viewer/iiif.py`

Builds local manifest files from a IIIF manifest URL.

Outputs:

- `items.json` (canvas metadata),
- `elements.json` (annotation elements),
- empty `[]` annotation JSON files for every pair,
- optional raw manifest dump.

Usage:

```powershell
python .\viewer\iiif.py <manifest_url> [--output-dir .] [--items-output items.json] [--elements-output elements.json] [--manifest-output manifest.json]
```

Examples:

```powershell
python .\viewer\iiif.py "https://archives06.fr/.../manifest.json"
python .\viewer\iiif.py "https://archives06.fr/.../manifest.json" --output-dir .\cut_images\alpes-maritimes\aiglun\3P31
python .\viewer\iiif.py "https://archives06.fr/.../manifest.json" --output-dir .\viewer\out --elements-output my-elements.json --manifest-output manifest.json
```

### `viewer/classif.py`

Batch classifies page images with a YOLO classification model.

Current script defaults:

- reads elements from `cut_images/alpes-maritimes/aiglun/3P31/elements.json`,
- writes results to `cut_images/alpes-maritimes/aiglun/3P31/classification.json`,
- uses model `models/classification/best.pt`.

Options:

- `--elements-path`: path to input `elements.json`.
- `--output-path`: path to output `classification.json`.
- `--model-path`: path to YOLO weights (default: `models/classification/best.pt`).
- `--limit`: process first N elements only.
- `--iiif-width`: request resized IIIF images (default `800`, `0` keeps full size).
- `--device`: `auto`, `cpu`, `cuda`, `cuda:0`, `cuda:1`.

Usage:

```powershell
python .\viewer\classif.py [--elements-path <elements.json>] [--output-path <classification.json>] [--model-path <best.pt>] [--limit 100] [--iiif-width 800] [--device auto]
```

Example for another subproject:

```powershell
python .\viewer\classif.py --elements-path .\cut_images\alpes-maritimes\belvedere\3P145\elements.json --output-path .\cut_images\alpes-maritimes\belvedere\3P145\classification.json --model-path .\models\classification\best.pt --iiif-width 800 --device auto
```

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