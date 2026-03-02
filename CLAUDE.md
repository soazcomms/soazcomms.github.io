# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Dark Sky Network (DSN)** monitors night sky brightness across Southern Arizona using SQM (Sky Quality Meter) and TESS units at 17+ sensor sites. This is a scientific data pipeline: raw sensor files → processed CSVs → InfluxDB → Grafana dashboards → web UI.

> This code is a work in progress.

## Running Key Scripts

```bash
# Process a raw SQM/TESS data file (core step)
python DSN_V03.py <DataFile>

# Query InfluxDB and export CSV
python DSN_generate_csv.py --label <LABEL> --from <ISO_DATE> --to <ISO_DATE>

# Generate histograms, heatmaps, jellyfish plots from local CSVs
python DSN_generate_analysis.py --input_dir <DIR> --label <LABEL> --from <ISO_DATE> --to <ISO_DATE>

# Full pipeline: download Box data, quality filters, monthly medians, maps
python DSN_production_v2.py

# Generate Grafana dashboard JSONs from template
python DSN_generate_dashboards.py

# Sync Box.com data (runs outside GitHub)
./DSN_sync_box.sh
```

No test framework exists. Validation happens through GitHub Actions workflow runs and data quality filters applied during processing.

### Local Testing

`DSN_V03.py` checks the `TESTING` environment variable to relocate `DSNsites.csv`:

```bash
export TESTING=1
export DSNdata=/path/to/dir/   # must contain DSNsites.csv
python DSN_V03.py <DataFile>
```

## Data Pipeline (6 Steps)

1. **Ingest**: Raw `.dat` files uploaded to `DSNdata/NEW` (manual or via Raspberry Pi)
2. **Process**: `DSN_V03.py` calculates chi-squared, moon altitude, LST, luminance per file; writes `.csv` to `DSNdata/INFLUX` and `DSNdata/BOX`
3. **Store**: CSVs pushed to InfluxDB (AWS); tagged by site label for Grafana routing
4. **Cleanup**: Processed `.dat` files deleted from `DSNdata/NEW`
5. **Archive**: `DSNdata/BOX` files uploaded to Box.com `DSNdata/ARCHIVE`, then deleted locally
6. **Log**: All operations logged to `DSNdata/RUN_LOG`

## File Naming Convention

Raw files: `DSNnnn-U_SiteName_yy-sss.dat`
- `nnn` = site sequence number
- `U` = unit type (`S`=SQM, `T`=TESS)
- `yy` = year, `sss` = sequence number per year

Processed CSV: `DSNnnn-U_SiteName_yy.csv`

## Architecture

| Component | Role |
|---|---|
| `DSN_V03.py` | Core processor: reads raw files, applies astronomical calculations |
| `DSN_generate_analysis.py` | Generates histograms, heatmaps, jellyfish plots from exported CSVs |
| `DSN_production_v2.py` | Full analysis pipeline: download Box data, quality filters, monthly medians, maps |
| `DSN_generate_csv.py` | InfluxDB query → CSV export |
| `DSN_generate_dashboards.py` | Generates per-site Grafana dashboard JSON from `DSN_template.json` |
| `Worker/` | Cloudflare Workers (`index.js`, `worker.js`) — receive web UI button clicks, dispatch GitHub `workflow_dispatch` events |
| `generated_dashboards/` | 40+ auto-generated Grafana dashboard JSON files (one per site) |
| `.github/workflows/` | GitHub Actions: weekly processing, monthly TESS pull, on-demand analysis/CSV export |
| `DSNweb.v04.html`, `DSNmap.v04.html` | Main web UIs (hosted on GitHub Pages) |

### Sensor Formats Handled by `DSN_V03.py`

| Sensor value in `DSNsites.csv` | Source | Notes |
|---|---|---|
| `SQM` | Standard SQM unit | columns: UT, Tloc, Etempc, volt, SQM, irec |
| `SQM1` | Sugarloaf / Bonita (Excel) | `.xlsx` format; also filters on RH and temperature |
| `SQM2` | NOIRLab / Gilinsky | columns: UT, Tloc, Etempc, counts, freq, SQM |
| `SQM3` | Hannes Groller Box format | columns: UT, Tloc, SQM, Etempc |
| `SQM4` | Standard SQM (alternate) | same columns as SQM |
| `TESS` | Stars4All TESS units | columns: UT, Tloc, tamb, tsky, SQM |

## Data Quality Filters (DSN_production_v2.py)

```python
MOON_ALT_MAX = -10.0      # Moon must be below -10° altitude
CLOUD_CHISQ_MAX = 0.009   # Reject cloudy readings (chi-squared threshold)
GALACTIC_LAT_MIN = 20.0   # |galactic latitude| > 20° (avoid galactic plane)
```

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `DSN-process_data.V02.yml` | Weekly (Wed 08:00 UTC) | Core: process NEW files, upload to InfluxDB |
| `DSN-get-SQM.yml` | Weekly | Download SQM data from Google Drive |
| `DSN-get-TESS.yml` | Monthly | Download TESS data from Stars4All network |
| `DSN_analysis.yml` | Manual dispatch | Generate histograms, heatmaps, jellyfish plots |
| `DSN_csv_download.yml` | Manual dispatch | Export CSV within a time range |
| `DSN_generate-dashboard.yml` | Manual dispatch | Regenerate Grafana dashboard JSONs |

## InfluxDB Data Model

- **Measurement name**: site label with dash removed — `DSN019-S_MtLemmon` → `DSN019S_MtLemmon`
- **Fields stored**: `SQM`, `lum`, `chisquared`, `moonalt` (and `LST` in some versions)
- Flux queries filter by `_measurement` using this name pattern

## External Services

- **InfluxDB** (AWS): time-series storage; CSVs are uploaded then deleted from local
- **Grafana**: dashboard visualization, one dashboard per sensor site
- **Box.com**: long-term archive; configured via `box_config.json` (OAuth); uses `rclone` remote `uasqm`
- **Cloudflare Workers**: webhook API; reads `OWNER`, `REPO`, `WORKFLOW`, `GITHUB_TOKEN` from Worker env vars
- **Stars4All**: source for TESS sensor data
- **GitHub Pages**: hosts the HTML web interfaces

### GitHub Actions Secrets Required

| Secret | Used by |
|---|---|
| `INFLUX_TOKEN1` | InfluxDB writes and queries |
| `BOX_CONFIG` | Box.com OAuth config (JSON) |

## Key Dependencies

Python: `numpy`, `pandas`, `astropy`, `plotly` (see `requirements.txt`)
Node.js: `wrangler` (Cloudflare Workers; see `wrangler.toml`)

## File Reference Document

`DSN_file_list.docx` is an annotated Word document listing every `.py`, `.yml`, `.sh`, and `.html` file in the repository with a one- or two-sentence description of each. To regenerate it after adding or renaming files:

```bash
python3 make_file_list.py
```

This overwrites `DSN_file_list.docx` in place.

## Notes

- Many files have versioned names (`_v01`, `_v02`, `V02`, etc.) and backups (`.py~`, `.yml~`); the `OLD/` directory contains deprecated scripts. The root directory is intentionally cluttered — the canonical production scripts are those listed in the Architecture table.
- Site metadata (coordinates, labels) is in `DSNsites.csv`. Columns: `long, lat, el, sensor, ihead, dark, bright, Site` where `ihead` is the number of header lines in raw data files and `dark`/`bright` are expected SQM range endpoints.
- Grafana dashboard template is `DSN_template.json`; `DSN_generate_dashboards.py` rewrites it per site label
- Observation times for a "night" run 17:30 MST through 07:00 MST the next morning (UTC offsets applied in `DSN_generate_csv.py:iso_range`)
