# OpsLens

Phase 1 foundation for a synthetic procurement analytics product.

## Local setup (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
docker compose up -d
python backend\data\generate_data.py --output-dir generated
python backend\scripts\load_data.py --input-dir generated --quarantine-dir quarantine
pytest
```

Install the PostgreSQL driver explicitly with:

```powershell
python -m pip install "psycopg[binary]" sqlalchemy
```

For local PostgreSQL, use Docker Compose:

```powershell
docker compose up -d
python backend\scripts\load_data.py --input-dir generated --quarantine-dir quarantine --database-url $env:DATABASE_URL
python backend\scripts\check_counts.py
```

For external PostgreSQL such as Neon, set `DATABASE_URL` in the local `.env` or PowerShell environment. The loader accepts either `postgresql://...` or `postgresql+psycopg://...` and uses psycopg v3. Then run the same loader and count commands.

The generator defaults to a deterministic 12-month window ending `2026-09`. Use `--end-month YYYY-MM` to select another fixed window. Generated files are on-demand artifacts and are not committed.

## Dataset and assumptions

The dataset is entirely synthetic. It uses a fixed seed, fictional suppliers/products, monthly purchase orders, and weekly inventory snapshots. The five planted findings are recorded in `backend/data/anomalies_ground_truth.json`.

## Validation and loading

`quarantined` means a recoverable row-level quality issue: the row is excluded from loading, retained with a non-empty `reason` column, and counted. Duplicate order IDs keep the first row and quarantine later rows. `rejected` means the input file or batch cannot be safely parsed or structurally validated; it is not partially loaded.

## Method notes

Phase 1 only establishes generation, validation, and loading. Later phases will add analytics, API, dashboard, and assistant layers.
