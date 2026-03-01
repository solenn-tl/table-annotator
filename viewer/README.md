# OCR Annotation Tool

This viewer loads page/annotation pairs from `cut_images/`, displays the page image, and lets you edit annotations stored in JSON arrays.

## Run

From the workspace root:

```powershell
& .\ocr-test\Scripts\python.exe .\viewer\server.py --port 8015
```

Open `http://127.0.0.1:8015`.

## Features

- Display each page with its associated JSON annotations.
- Edit annotations directly in an HTML table.
- Save changes to the original JSON using `/api/save/<file>.json`.
  - The server creates a backup file in `cut_images/` named `OLD<stem>.json` (or timestamped if needed).
- Draw bounding boxes into the `bbox` property of the selected row.
- Add a new row.
- Delete the selected row.
- Reorder rows with drag and drop.
- Generate numeric sequences in a column: focus 2 successive cells (e.g. `1`, `2`) then click `Fill sequence`.
- Autocomplete while typing using previous values from the same column.
- Display contribuable clusters grouped by `numeroListe` across all `cut_images/*.json` files (Sunburst chart).

## Notes

- JSON files must be arrays of objects.
- `bbox` is expected as:

```json
{
  "x": 10,
  "y": 20,
  "width": 120,
  "height": 40
}
```

- Click a table row to select it before deleting or drawing a bbox.
- Cluster data is available from `/api/contribuable-clusters`.

How to use

## Batch update cell values
* Click a first cell in a column (sets anchor).
* Shift+click another cell in the same column.
* Enter the value in the dedicated fill.

## Integers to letterse same column (selects range).
* Select your document in the dropdown.
* In the source numeric column (example: Class. chiffres), click one cell, then Shift+click another cell in the same column to select a range.
* Click Integers → lettres.
* In the prompt, confirm or edit the target column name (example: Class. lettres).
* The app writes converted values into that target column (creates it automatically if missing), then click Save JSON.