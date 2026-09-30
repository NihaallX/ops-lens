import json
import pandas as pd
import os
import pytest
import tempfile
from pathlib import Path
from data.generate_data import generate
from app.analytics.validation import validate_orders
from scripts.load_data import load

def _frames(tmp_path):
    return generate(tmp_path / "data")

def test_deterministic_and_ground_truth(tmp_path):
    a=tmp_path/"a"; b=tmp_path/"b"; generate(a); generate(b)
    for name in ["purchase_orders.csv","suppliers.csv","regions.csv","products.csv","inventory_snapshots.csv","anomalies_ground_truth.json"]:
        assert (a/name).read_bytes()==(b/name).read_bytes()
    truth=json.loads((a/"anomalies_ground_truth.json").read_text()); assert len(truth)==5
    assert all(set(x)>= {"id","type","entity_ids","start_date","end_date","period_granularity","metric","direction","expected_magnitude","what","where","when","magnitude"} for x in truth)
    assert isinstance(truth[0]["expected_magnitude"], dict); assert "cleaning chemicals" in truth[2]["entity_ids"]

def test_planted_signals_and_quarantine(tmp_path):
    out=tmp_path/"data"; d=generate(out); orders=d["orders"].copy(); orders["month"]=pd.to_datetime(orders.order_date).dt.to_period("M")
    s03=orders[orders.supplier_id=="S03"].groupby("month").size(); assert s03.index.size > 0
    s03_delay=orders[orders.supplier_id=="S03"].assign(delay=(pd.to_datetime(orders.delivered_date)-pd.to_datetime(orders.promised_date)).dt.days).groupby("month").delay.mean(); assert s03_delay.iloc[-1] > s03_delay.iloc[0]
    spend=orders.assign(spend=orders.quantity*orders.unit_cost).groupby("supplier_id").spend.sum().sort_values(ascending=False); assert "S01" in spend.head(3).index
    q=pd.Period("2026-09",freq="M"); earlier=orders[(orders.supplier_id=="S01") & (orders.month<q)].unit_cost.mean(); latest=orders[(orders.supplier_id=="S01") & (orders.month>=pd.Period("2026-07",freq="M"))].unit_cost.mean(); assert latest/earlier > 1.10
    south=orders[orders.region_id=="R02"]; assert south[south.month>=pd.Period("2026-07",freq="M")].is_expedited.mean() > south[south.month<pd.Period("2026-07",freq="M")].is_expedited.mean()
    inv=d["inventory"]; west=inv[(inv.region_id=="R01") & (inv.product_id.str.match("P00"))]; assert west.units_on_hand.mean() > west.reorder_level.mean()
    s07=orders[(orders.supplier_id=="S07") & orders.product_id.isin(["P011","P012"]) & orders.month.isin([pd.Period("2026-05",freq="M"),pd.Period("2026-06",freq="M")])]; assert len(s07)>0
    result=validate_orders(orders,d["suppliers"],d["products"],d["regions"]); assert len(result.quarantined)>0; assert result.quarantined.reason.notna().all(); assert result.report["accepted"]+result.report["quarantined"]==len(orders)
    assert pd.to_datetime(orders.delivered_date).max() <= pd.Timestamp("2026-09-30")

def test_delivered_dates_do_not_exceed_window(tmp_path):
    d=_frames(tmp_path); assert pd.to_datetime(d["orders"].delivered_date).max() <= pd.Timestamp("2026-09-30")

def test_null_required_field_rule(tmp_path):
    d=_frames(tmp_path); r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["null_required_field"] == 2

def test_duplicate_order_rule_keeps_first(tmp_path):
    d=_frames(tmp_path); r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["duplicate_order_id"] == 1; assert r.accepted.order_id.duplicated().sum() == 0

def test_negative_numeric_rule(tmp_path):
    d=_frames(tmp_path); d["orders"].loc[10,"quantity"]=-1; r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["negative_or_invalid_numeric"] == 1

def test_delivered_before_order_rule(tmp_path):
    d=_frames(tmp_path); d["orders"].loc[10,"delivered_date"]="2020-01-01"; r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["delivered_before_order"] == 1

def test_unknown_foreign_key_rule(tmp_path):
    d=_frames(tmp_path); d["orders"].loc[10,"region_id"]="UNKNOWN"; r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["unknown_region"] == 1

def test_outlier_rule(tmp_path):
    d=_frames(tmp_path); d["orders"].loc[10,"quantity"]=10001; r=validate_orders(d["orders"],d["suppliers"],d["products"],d["regions"]); assert r.report["checks"]["outlier_sane_range"] == 1

def test_s03_anomaly_separately(tmp_path):
    d=_frames(tmp_path); o=d["orders"]; o["month"]=pd.to_datetime(o.order_date).dt.to_period("M"); s=o[o.supplier_id=="S03"].assign(delay=(pd.to_datetime(o[o.supplier_id=="S03"].delivered_date)-pd.to_datetime(o[o.supplier_id=="S03"].promised_date)).dt.days).groupby("month").delay.mean(); assert s.iloc[-1] > s.iloc[0]

def test_s01_anomaly_separately(tmp_path):
    d=_frames(tmp_path); o=d["orders"]; o["month"]=pd.to_datetime(o.order_date).dt.to_period("M"); spend=o.assign(spend=o.quantity*o.unit_cost).groupby("supplier_id").spend.sum().sort_values(ascending=False); earlier=o[(o.supplier_id=="S01")&(o.month<pd.Period("2026-07",freq="M"))].unit_cost.mean(); latest=o[(o.supplier_id=="S01")&(o.month>=pd.Period("2026-07",freq="M"))].unit_cost.mean(); assert "S01" in spend.head(3).index and latest/earlier > 1.10

def test_south_anomaly_separately(tmp_path):
    d=_frames(tmp_path); o=d["orders"]; o["month"]=pd.to_datetime(o.order_date).dt.to_period("M"); s=o[o.region_id=="R02"]; assert s[s.month>=pd.Period("2026-07",freq="M")].is_expedited.mean() > s[s.month<pd.Period("2026-07",freq="M")].is_expedited.mean()

def test_west_and_s07_anomalies_separately(tmp_path):
    d=_frames(tmp_path); i=d["inventory"]; assert i[(i.region_id=="R01")&i.product_id.str.match("P00")].units_on_hand.mean() >  i[(i.region_id=="R01")&i.product_id.str.match("P00")].reorder_level.mean(); o=d["orders"]; o["month"]=pd.to_datetime(o.order_date).dt.to_period("M"); x=o[(o.supplier_id=="S07")&o.product_id.isin(["P011","P012"])]; assert len(x[x.month.isin([pd.Period("2026-05",freq="M"),pd.Period("2026-06",freq="M")])]) > 0

def test_loader_counts_and_quarantine_file(tmp_path):
    out=tmp_path/"input"; _frames(tmp_path); # generator writes to data; use that output explicitly
    out=tmp_path/"data"; report=load(out,tmp_path/"quarantine"); assert report["accepted"]==7997 and report["quarantined"]==3; q=pd.read_csv(tmp_path/"quarantine"/"purchase_orders.csv"); assert q.reason.notna().all()

@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not configured")
def test_postgres_integration():
    from sqlalchemy import create_engine, text
    with tempfile.TemporaryDirectory(dir=Path.cwd()/".test_tmp") as workspace:
        root=Path(workspace); d=_frames(root); load(root/"data",root/"quarantine",os.environ["DATABASE_URL"])
    e=create_engine(os.environ["DATABASE_URL"])
    with e.connect() as c: assert c.execute(text("select count(*) from purchase_orders")).scalar() >= 7997
