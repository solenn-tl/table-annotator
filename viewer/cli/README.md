# Viewer CLI tools

This folder contains command-line scripts used by the viewer workflow, plus HTML command builders that help prepare commands for your specific case.

## Quick start

From repository root:

```powershell
& .\ocr-test\Scripts\Activate.ps1
```

Then run scripts with:

```powershell
python .\viewer\cli\<script>.py ...
```

## HTML command builders

These pages generate commands only. They do not execute scripts.

- Ligeo IIIF import: `http://127.0.0.1:8000/iiif-command.html`
- Arkotheque IIIF import: `http://127.0.0.1:8000/iiif-arkotheque-command.html`
- Classification: `http://127.0.0.1:8000/classif-command.html`
- Local pretreatement: `http://127.0.0.1:8000/local-pretreatement-command.html`

You can also open them directly as static files under `viewer/cli/` if needed.

## Tools

### 1) `iiif.py`

Fetches a Ligeo IIIF manifest and creates annotation-ready files.

Creates:
- `items.json`
- `elements.json`
- Empty sidecar annotation files (`[]`) referenced by `elements.json`
- Optional manifest dump

Usage:

```powershell
python .\viewer\cli\iiif.py <manifest_url> [--output-dir .] [--items-output items.json] [--elements-output elements.json] [--manifest-output manifest.json]
```

Examples:

```powershell
python .\viewer\cli\iiif.py "https://archives06.fr/.../manifest.json"
python .\viewer\cli\iiif.py "https://archives06.fr/.../manifest.json" --output-dir .\cut_images\alpes-maritimes\aiglun\3P31
python .\viewer\cli\iiif.py "https://archives06.fr/.../manifest.json" --output-dir .\viewer\out --items-output items-aiglun.json --elements-output elements-aiglun.json --manifest-output manifest-aiglun.json
```

Main options:
- `--output-dir`: output folder
- `--items-output`: items JSON filename/path
- `--elements-output`: elements JSON filename/path
- `--manifest-output`: optional raw manifest JSON filename/path

### 2) `iiif-arkotheque.py`

Fetches Arkotheque `info.json` documents by index and builds the same annotation-ready structure.

Creates:
- `items.json`
- `elements.json`
- Empty sidecar annotation files (`[]`)
- Optional `infos.json` (raw fetched infos)

Usage:

```powershell
python .\viewer\cli\iiif-arkotheque.py <info_url> <image_count> [--output-dir .] [--items-output items.json] [--elements-output elements.json] [--infos-output infos.json]
```

Examples:

```powershell
python .\viewer\cli\iiif-arkotheque.py "https://www.archinoe.net/.../viewer/image/12345/0/info.json" 42 --output-dir .\cut_images\yvelines\versailles
python .\viewer\cli\iiif-arkotheque.py "https://www.archinoe.net/.../viewer/image/12345/0/info.json" 42 --output-dir .\cut_images\yvelines\versailles --infos-output infos.json --label-collection "Versailles" --commune "Versailles"
```

Main options:
- `--output-dir`: output folder
- `--items-output`: items JSON filename/path
- `--elements-output`: elements JSON filename/path
- `--infos-output`: optional full infos dump
- Optional metadata overrides: `--label-collection`, `--collection-cote`, `--commune`, `--date`, `--type`, `--attribution`

### 3) `classif.py`

Downloads images referenced in `elements.json` and runs YOLO classification.

Creates:
- `classification.json` containing `predicted_class`, `predicted_prob`, and ranked classes
- Optional failure block if image downloads fail

Usage:

```powershell
python .\viewer\cli\classif.py [--elements-path <elements.json>] [--output-path <classification.json>] [--model-path <best.pt>] [--limit 100] [--iiif-width 800] [--device auto]
```

Examples:

```powershell
python .\viewer\cli\classif.py --elements-path .\cut_images\alpes-maritimes\aiglun\3P31\elements.json --output-path .\cut_images\alpes-maritimes\aiglun\3P31\classification.json --model-path .\models\classification\best.pt --iiif-width 800 --device auto
python .\viewer\cli\classif.py --elements-path .\cut_images\alpes-maritimes\belvedere\3P145\elements.json --output-path .\cut_images\alpes-maritimes\belvedere\3P145\classification.json --limit 50 --device cpu
```

Main options:
- `--elements-path`: input elements file (defaults to a sample path in the script)
- `--output-path`: output classification file (defaults to a sample path in the script)
- `--model-path`: YOLO weights path (default `models/classification/best.pt`)
- `--limit`: classify only first N entries
- `--iiif-width`: request resized IIIF images; `0` means full size
- `--device`: `auto`, `cpu`, `cuda`, `cuda:0`, `cuda:1`

### 4) `local-pretreatement.py`

Prepares local image folders for annotation.

Behavior:
- Recursively scans source folder image files
- Splits landscape images into `_left` and `_right`
- Copies portrait images unchanged
- Optional creation of missing sidecar JSON files and `elements.json`

Usage:

```powershell
python .\viewer\cli\local-pretreatement.py <folder_path> <save_dir> [--create-json-and-elements]
```

Examples:

```powershell
python .\viewer\cli\local-pretreatement.py .\images .\cut_images
python .\viewer\cli\local-pretreatement.py .\images\finistere\ouessant .\cut_images\finistere\ouessant --create-json-and-elements
```

Main option:
- `--create-json-and-elements`: create missing sidecar JSON files and generate `elements.json`

## Typical workflow

1. Import or prepare pages (`iiif.py`, `iiif-arkotheque.py`, or `local-pretreatement.py`).
2. Run `classif.py` to prefill page classes.
3. Launch viewer server and verify/edit classes and annotations.
