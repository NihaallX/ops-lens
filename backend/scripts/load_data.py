"""Validate generated CSVs and optionally load them into PostgreSQL."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from app.analytics.validation import validate_orders

def load(input_dir: Path, quarantine_dir: Path, database_url: str | None = None) -> dict:
    try:
        names=["purchase_orders","suppliers","products","regions","inventory_snapshots"]
        frames={n:pd.read_csv(input_dir/f"{n}.csv") for n in names}
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise RuntimeError(f"rejected input batch: {exc}") from exc
    result=validate_orders(frames["purchase_orders"],frames["suppliers"],frames["products"],frames["regions"]); quarantine_dir.mkdir(parents=True,exist_ok=True); result.quarantined.to_csv(quarantine_dir/"purchase_orders.csv",index=False); (quarantine_dir/"validation_report.json").write_text(json.dumps(result.report,indent=2),encoding="utf-8")
    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
        engine=create_engine(database_url)
        schema=Path(__file__).parents[1]/"sql"/"schema.sql"
        with engine.begin() as connection:
            connection.exec_driver_sql(schema.read_text(encoding="utf-8"))
            connection.exec_driver_sql("TRUNCATE TABLE purchase_orders, inventory_snapshots, suppliers, regions, products CASCADE")
        for column in ["order_date", "promised_date", "delivered_date"]:
            result.accepted[column] = pd.to_datetime(result.accepted[column]).dt.date
        frames["inventory_snapshots"]["snapshot_date"] = pd.to_datetime(frames["inventory_snapshots"]["snapshot_date"]).dt.date
        frames["suppliers"].to_sql("suppliers",engine,if_exists="append",index=False)
        frames["regions"].to_sql("regions",engine,if_exists="append",index=False)
        frames["products"].to_sql("products",engine,if_exists="append",index=False)
        result.accepted.to_sql("purchase_orders",engine,if_exists="append",index=False)
        frames["inventory_snapshots"].to_sql("inventory_snapshots",engine,if_exists="append",index=False)
        result.report["loaded_to_database"]=True
    return result.report

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--input-dir",type=Path,default=Path("generated")); p.add_argument("--quarantine-dir",type=Path,default=Path("quarantine")); p.add_argument("--database-url"); a=p.parse_args(); print(json.dumps(load(a.input_dir,a.quarantine_dir,a.database_url),indent=2))
