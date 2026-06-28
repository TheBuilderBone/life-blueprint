# Utility Flex Funding Tool

Analyzes your monthly utility bills, detects seasonal patterns and outliers,
and tells you the right amount to fund your flex account each month.

## Files

| File | Purpose |
|------|---------|
| `bills.csv` | **Your data.** Edit this freely. One row per bill. |
| `analyze.py` | Runs all analysis, prints the report, saves charts. |
| `charts/` | PNG charts, one per utility. Overwritten on each run. |

---

## How to add a new bill

**Option A — command line (recommended):**

```bash
python utilities/analyze.py add Water 2026-07 15.00
```

Format: `add <Utility> <YYYY-MM> <amount> [optional notes]`

Utilities must be one of: `Water`, `Power`, `Internet`, `Trash`

This adds the row, sorts it into place, and re-runs the full analysis automatically.

**Option B — edit the CSV directly:**

Open `bills.csv` in any text editor or spreadsheet app, add a row at the bottom:

```
Water,2026-07,15.00,,
```

Then run:

```bash
python utilities/analyze.py
```

---

## How to exclude an outlier

If a bill is inflated (e.g., water during a leak), exclude it without deleting:

```bash
python utilities/analyze.py exclude Water 2026-04
```

Run the same command again to toggle it back to included.

Or edit `bills.csv` directly: put `true` in the `exclude` column for that row.

---

## CSV format

```
utility,date,amount,exclude,notes
Water,2025-06,11.25,,
Water,2026-04,43.25,true,Possible leak
```

- `utility`: Water | Power | Internet | Trash
- `date`: YYYY-MM (year and month only)
- `amount`: Your share of the bill (already divided if split)
- `exclude`: Leave blank (included) or `true` (excluded from averages, kept for records)
- `notes`: Optional free text

---

## How funding amounts are calculated

For each utility:

> **Recommended = avg + 1.0 × std deviation**

This targets roughly the 84th percentile of your historical bills — meaning
about 5 out of every 6 months you'll have money left over to sweep to savings,
and 1 in 6 you'll draw on the buffer.

The **buffer** is the gap between your funding target and your actual worst-case
peak. Keeping this amount parked in the flex account means even your worst
historical month can't drain the account to zero.

---

## Requirements

- Python 3.8+
- `matplotlib` for charts: `pip install matplotlib`

Charts are skipped gracefully if matplotlib is not installed; all stats still print.
