# OCR Annotation Tool (Viewer)

This app loads image/JSON pairs from `cut_images/`, lets you edit annotation rows in a table, draw/select bboxes on the image, and analyze `contribuable` clusters.

## Run

From the workspace root:

```powershell
& .\ocr-test\Scripts\python.exe .\viewer\server.py --port 8015
```

Open: `http://127.0.0.1:8015`

---

## What each button does

### Top toolbar

- **Document** (`pairSelect`)
  - Selects the current image/JSON pair.

- **`-` / `+`** (`zoomOutBtn` / `zoomInBtn`)
  - Zooms the image viewer out/in.

- **Add row** (`addRowBtn`)
  - Appends one empty row.

- **Rows to add** (`addRowsCountInput`) + **Add rows** (`addRowsBatchBtn`)
  - Appends multiple empty rows (up to 1000 at once).

- **Delete row** (`deleteRowBtn`)
  - Deletes the currently selected row.

- **Fill sequence** (`fillSeriesBtn`)
  - Numeric fill down from two consecutive seed cells in the same column.

- **Fill sequence with `<IDEM>`** (`fillIdemBtn`)
  - Fills a selected range (or below a seed) with `<IDEM>`.

- **Fill sequence with `<EMPTY>`** (`fillEmptyBtn`)
  - Fills a selected range (or below a seed) with `<EMPTY>`.

- **Batch value** (`batchValueInput`) + **Apply to selected range** (`applyRangeBtn`)
  - Applies the input value to the currently selected range in one column.

- **Integers → lettres** (`convertIntWordsBtn`)
  - Converts integer values in selected range to French words.
  - Prompts target column name and creates it if missing.

- **Draw bbox** (`drawBboxBtn`)
  - Toggles draw mode for bbox on selected row.

- **Batch draw bbox** (`batchDrawBboxChk`)
  - After drawing a bbox, auto-advances to next row.

- **Save JSON** (`saveBtn`)
  - Saves current annotations to selected JSON.

- **Save badge** (`saveModeBadge`)
  - Indicates save mode (`server`, `local fallback`, `unknown`).

### Annotations panel header

- **Show/Hide column settings** (`columnTypesBtn`)
  - Opens a scrollable panel to configure each column behavior:
    - `none`
    - `sequence`
    - `autocomplete`
    - `both`

### Cluster panel header

- **Expand / Reduce** (`toggleClustersBtn`)
  - Collapses/expands clustering panel (collapsed by default).

- **Cluster zoom `-` / `+`** (`clusterZoomOutBtn` / `clusterZoomInBtn`)
  - Zooms sunburst chart only.

- **Chart / List** (`clusterChartModeBtn` / `clusterListModeBtn`)
  - Switches cluster visualization mode.

- **Refresh clusters** (`refreshClustersBtn`)
  - Reloads clustering data.

---

## How to use (quick workflow)

1. Select a **Document**.
2. Click a table row/cell to select the active row.
3. Edit cell values directly.
4. Draw bboxes (optional): select row → click **Draw bbox** → drag on image.
5. Use batch helpers as needed:
   - Shift+click for range
   - **Batch value** + **Apply to selected range**
   - **Fill sequence** / `<IDEM>` / `<EMPTY>`
   - **Integers → lettres**
6. Click **Save JSON**.

---

## Keyboard and mouse shortcuts

- **Shift + Arrow keys** in a cell: navigate to adjacent table cell.
- **Shift + click** in same column: select range.
- **Mouse wheel** over image: zoom at cursor.
- **Click + drag** on image (outside draw mode): pan image.
- **Click bbox**: select row and zoom bbox to fit viewer width.

---

## Cluster behavior

- Data source: all JSON files in `cut_images/`.
- Groups by `numeroListe` and entries by `contribuable`.
- Includes source details (`json`, `rowNumber`) and `adresseContribuable` in list mode.
- `numeroListe` cleaning:
  - removes markdown strikeout segments like `~~720~~`
  - trims leading/trailing whitespace

---

## Data expectations

- Annotation JSON files must be arrays of objects.
- `bbox` format:

```json
{
  "x": 10,
  "y": 20,
  "width": 120,
  "height": 40
}
```

Cluster endpoint: `/api/contribuable-clusters`