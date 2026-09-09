# Daily Operational Capacity Dashboard

A FastAPI dashboard that stores and displays daily Timely Cycle operational-capacity snapshots for the pipeline points in the supplied `Capacity Summary.xlsm` tracker.

## What it does

- Shows the same pipeline/segment groups used in the workbook.
- Stores Gas Day, Operating Capacity, Scheduled Quantity, Operationally Available Capacity, direction, and source.
- Refreshes automatically at **6:00 AM America/New_York** every day.
- Keeps history in SQLite so you can compare changes by day.
- Provides a manual **Refresh now** endpoint at `/admin/refresh`.
- Uses public informational-posting pages; the collector first tries direct HTML/table parsing and then a Chromium browser fallback for sites that require navigation/cookies.
- Seeds the database with the cached snapshot found in the uploaded workbook, so the dashboard has data on first launch.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Deploy

The included `Dockerfile` works on Render, Railway, Fly.io, Azure Container Apps, or another Docker host. `render.yaml` includes a persistent disk because the SQLite history should survive redeploys.

## Important production note

Pipeline informational-posting sites do not expose one consistent API. The collector is intentionally defensive, but public page layouts can change. The first live refresh should be reviewed against the official Timely report. If a pipeline changes its page structure, edit only `app/collectors.py`; the database/dashboard do not need to change.

## Schedule

The app uses APScheduler with the `America/New_York` timezone, so the 6:00 AM refresh follows daylight saving time automatically.

## September 9, 2026 dashboard revisions

- Removed Mountain Valley Pipeline (MVP) from the configured pipelines and seed data.
- Williams Ohio Valley is displayed as one combined section across TCO, EGT, TETCO, and NEXUS, with the source pipeline shown on each row.
- EQM Statler through Valley Chapel uses the same shared/merged capacity concept as the workbook: one group Operating Capacity and one group Open/OAC value across the seven meters. The shared OAC is calculated as group operating capacity less the sum of scheduled quantities for the group.
- Added a Total row to every section. Shared EQM capacity/OAC is counted once in totals.
- Added prior-day Open/OAC and day-over-day Open change. Increases display with a green up arrow; decreases display with a red down arrow.
- Added a Target Date field. Stored snapshots can be viewed by gas day, and the dashboard compares the selected date with the most recent stored day before it.
- Seed data now includes September 8 and September 9, 2026 so the day-over-day comparison is populated immediately. Future 6:00 AM ET runs continue building history in SQLite.
