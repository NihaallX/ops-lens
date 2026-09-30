"""Print row counts for every OpsLens table using DATABASE_URL."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, text

def main() -> None:
    url=os.environ.get("DATABASE_URL")
    if not url: raise SystemExit("DATABASE_URL is required")
    if url.startswith("postgresql://"): url="postgresql+psycopg://"+url.removeprefix("postgresql://")
    engine=create_engine(url)
    for table in ["suppliers","regions","products","purchase_orders","inventory_snapshots"]:
        with engine.connect() as connection: print(f"{table}: {connection.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar_one()}")

if __name__ == "__main__": main()
