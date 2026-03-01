# Annotation Tool (Viewer)

This app loads image/JSON pairs from `cut_images/`, lets you edit table annotations, manage bbox regions on image pages, and run clustering views.

## Prepare input files

Use the CLI to split/prep images and create JSON + pairs manifest:

```bash
python viewer\cli.py images\ cut_images\ --create-json-and-pairs
```

## Current UI functions

### Top toolbar

- **Document** (`pairSelect`): select active image/JSON pair.
- **Image zoom `- / +`** (`zoomOutBtn` / `zoomInBtn`): zoom image viewport.
- **Add row** (`addRowBtn`): append one empty row.
- **Rows to add + Add rows** (`addRowsCountInput` + `addRowsBatchBtn`): append multiple rows (max 1000).
- **Delete row** (`deleteRowBtn`): delete selected row.
- **Fill with numeric sequence** (`fillSeriesBtn`): numeric fill-down from 2 consecutive seed cells in the same column.
- **Set batch `<IDEM>`** (`fillIdemBtn`): sets batch input to `<IDEM>`.
- **Set batch `<EMPTY>`** (`fillEmptyBtn`): sets batch input to `<EMPTY>`.
- **Clear batch value** (`clearBatchValueBtn`): empties the batch input.
- **Batch value + Apply to selected range** (`batchValueInput` + `applyRangeBtn`): apply a single value to selected range.
- **Integers → lettres** (`convertIntWordsBtn`): convert selected integer range into French words in target column.
- **Draw bbox** (`drawBboxBtn`): draw bbox on selected row.
- **Edit bbox corners** (`editBboxCornersBtn`): drag bbox corners directly on image.
- **Normalize bbox width** (`normalizeBboxWidthBtn`): set all bbox widths to largest existing width (height unchanged).
- **Batch draw bbox** (`batchDrawBboxChk`): after drawing, auto-select next row.
- **Save JSON** (`saveBtn`): save current annotation data.
- **Save badge** (`saveModeBadge`): `server`, `local fallback`, or `unknown`.

### Annotation panel

- **Show/Hide column settings** (`columnTypesBtn`): configure per-column behavior:
  - `none`
  - `sequence`
  - `autocomplete`
  - `both`

### `Contribuable clusters by numeroListe` panel

- **Expand / Reduce** (`toggleClustersBtn`): collapse/expand panel.
- **Chart zoom `- / +`** (`clusterZoomOutBtn` / `clusterZoomInBtn`): zoom sunburst only.
- **Chart / List** (`clusterChartModeBtn` / `clusterListModeBtn`): switch visualization mode.
- **Refresh clusters** (`refreshClustersBtn`): reload cluster data.
- **Chart pan (mouse drag)**: pan inside the chart area in chart mode.

### `Cluster by custom field` panel

- **Field** (`clusterFieldInput`): field name to analyze.
- **Threshold** (`fieldClusterThresholdInput`): normalized Levenshtein distance threshold (`0.00` to `1.00`).
- **Run clustering** (`runFieldClusterBtn`): compute fuzzy clusters for that field.
- Threshold changes update value label live and re-run clustering when a field is set.

## Quick workflow

1. Select a **Document**.
2. Select row/cell in table and edit values.
3. Draw or edit bbox if needed.
4. Use range tools (`Shift+click`, batch apply, numeric sequence, integer→letters).
5. Save with **Save JSON**.
6. Review clusters in bottom panels (fixed `numeroListe` panel + custom field panel).

## Shortcuts and interactions

- **Shift + Arrow** in a cell: move to adjacent cell.
- **Shift + click** in same column: set a range.
- **Mouse wheel** on image: zoom at cursor.
- **Click + drag** on image (non-draw mode): pan image.
- **Click bbox**: select row + fit row width in image view.
- **Edit bbox corners mode**: drag corner handles to resize selected bbox.

## Clustering details

- Main cluster panel source: all JSON files in `cut_images/`.
- Main grouping: `numeroListe` → `contribuable` with source rows and addresses.
- `numeroListe` cleanup removes markdown strikeout (`~~...~~`) and trims spaces.
- Custom field clustering uses normalized Levenshtein distance over field values.

## Data format

Annotation JSON files must be arrays of objects. `bbox` shape:

```json
{
  "x": 10,
  "y": 20,
  "width": 120,
  "height": 40
}
```

API endpoints used by viewer include:

- `/api/pairs`
- `/api/save/<json-file>`
- `/api/column-settings`
- `/api/contribuable-clusters`
- `/api/autocomplete-fields`