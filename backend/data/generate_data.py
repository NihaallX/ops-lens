"""Generate deterministic synthetic OpsLens data."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

REGIONS = [("R01", "West"), ("R02", "South"), ("R03", "North"), ("R04", "East"), ("R05", "Central")]
CATEGORIES = ["cleaning chemicals", "water treatment", "dispensing equipment", "packaging", "safety supplies"]

def month_range(end_month: str) -> pd.DatetimeIndex:
    end = pd.Period(end_month, freq="M")
    return pd.period_range(end=end, periods=12, freq="M").to_timestamp()

def generate(output_dir: Path, seed: int = 202609, row_count: int = 8000, end_month: str = "2026-09") -> dict:
    rng = np.random.default_rng(seed); months = month_range(end_month); output_dir.mkdir(parents=True, exist_ok=True)
    suppliers = pd.DataFrame({"supplier_id": [f"S{i:02d}" for i in range(1,11)], "name": [f"Supplier {i:02d}" for i in range(1,11)], "country": ["India"]*10, "tier": ["strategic","preferred","standard","preferred","standard","standard","preferred","standard","strategic","standard"], "payment_terms_days": [30,45,30,60,30,45,60,30,45,30]})
    regions = pd.DataFrame(REGIONS, columns=["region_id","name"])
    products = pd.DataFrame([{"product_id": f"P{i:03d}", "name": f"Product {i:03d}", "category": CATEGORIES[(i-1)//10], "unit_cost_baseline": round(20 + i*1.7,2)} for i in range(1,51)])
    dates = pd.to_datetime(rng.choice(months, row_count)) + pd.to_timedelta(rng.integers(0,27,row_count), unit="D")
    sid = rng.choice(suppliers.supplier_id, row_count, p=[.18,.12,.10,.10,.09,.08,.12,.08,.08,.05]); pid = rng.choice(products.product_id, row_count); rid = rng.choice(regions.region_id, row_count)
    idx = pd.Series(dates).dt.to_period("M").apply(lambda p: months.get_loc(p.to_timestamp())).to_numpy(); base = products.set_index("product_id").loc[pid,"unit_cost_baseline"].to_numpy()
    expedited = rng.random(row_count) < .12; unit = base * rng.normal(1, .035, row_count); shipping = rng.normal(80,18,row_count) + expedited*90
    s01 = sid == "S01"; unit[s01 & (idx >= 9)] *= 1.15; south = rid == "R02"; expedited[south & (idx >= 9)] = rng.random(np.sum(south & (idx >= 9))) < .65; shipping[south & (idx >= 9)] *= 2.4
    delay = rng.normal(1.5,2.2,row_count); s03 = sid == "S03"; delay[s03] += np.maximum(idx[s03]-5,0)*1.5; promised = pd.to_datetime(dates) + pd.to_timedelta(12, unit="D"); delivered = promised + pd.to_timedelta(np.maximum(delay,0).round().astype(int), unit="D")
    defects = rng.binomial(np.maximum(1,rng.integers(30,300,row_count)), .012); s07 = sid == "S07"; two = np.isin(pid,["P011","P012"]); defects[s07 & two & np.isin(idx,[7,8])] += rng.integers(8,25,np.sum(s07 & two & np.isin(idx,[7,8])))
    qty = rng.integers(30,300,row_count); defects = np.minimum(defects, qty)
    window_end = months[-1].to_period("M").end_time.normalize()
    delivered = pd.Series(delivered).clip(upper=window_end).dt.date
    orders = pd.DataFrame({"order_id":[f"O{i:05d}" for i in range(row_count)],"order_date":pd.to_datetime(dates).date,"promised_date":promised.date,"delivered_date":delivered,"supplier_id":sid,"product_id":pid,"region_id":rid,"quantity":qty,"unit_cost":np.round(unit,2),"shipping_cost":np.round(np.maximum(shipping,1),2),"is_expedited":expedited,"defective_units":defects})
    west = (rid=="R01") & np.isin(pid,["P001","P002","P003","P004","P005","P006","P007","P008","P009","P010"]); qty_w = np.where(west, 900, 220)
    inv=[]
    for m in months:
        for r,n in REGIONS:
            for p in products.itertuples():
                over = r=="R01" and p.category=="cleaning chemicals"; inv.append({"snapshot_id":f"I{len(inv):06d}","snapshot_date":m.date(),"region_id":r,"product_id":p.product_id,"units_on_hand":int((1100 if over else 180)+rng.integers(-20,20)),"reorder_level":200})
    inventory=pd.DataFrame(inv)
    orders.loc[5,"unit_cost"] = np.nan; orders.loc[6,"supplier_id"] = np.nan; orders.loc[7,"order_id"] = orders.loc[0,"order_id"]
    orders.to_csv(output_dir/"purchase_orders.csv", index=False); suppliers.to_csv(output_dir/"suppliers.csv",index=False); regions.to_csv(output_dir/"regions.csv",index=False); products.to_csv(output_dir/"products.csv",index=False); inventory.to_csv(output_dir/"inventory_snapshots.csv",index=False)
    latest_start, latest_end = months[9].date().isoformat(), window_end.date().isoformat(); m8,m9=months[7].date().isoformat(),months[8].to_period("M").end_time.date().isoformat()
    orders["month"] = pd.to_datetime(orders.order_date).dt.to_period("M")
    delay_days = (pd.to_datetime(orders.delivered_date)-pd.to_datetime(orders.promised_date)).dt.days
    s03 = orders.supplier_id.eq("S03")
    s03_start = float(delay_days[s03 & orders.month.eq(months[5].to_period("M"))].mean()); s03_end = float(delay_days[s03 & orders.month.eq(months[-1].to_period("M"))].mean())
    south = orders.region_id.eq("R02"); south_before = float(orders.loc[south & (orders.month < months[9].to_period("M")),"shipping_cost"].mean()); south_latest = float(orders.loc[south & (orders.month >= months[9].to_period("M")),"shipping_cost"].mean())
    s07 = orders.supplier_id.eq("S07") & orders.product_id.isin(["P011","P012"]); rates = orders.defective_units / orders.quantity; s07_base=float(rates[s07 & orders.month.isin(months[:7].to_period("M"))].mean()); s07_cluster=float(rates[s07 & orders.month.isin(months[7:9].to_period("M"))].mean())
    s01 = orders.supplier_id.eq("S01"); s01_base=float(orders.loc[s01 & (orders.month < months[9].to_period("M")),"unit_cost"].mean()); s01_latest=float(orders.loc[s01 & (orders.month >= months[9].to_period("M")),"unit_cost"].mean())
    truth=[{"id":"supplier_s03_delay","type":"delivery_delay","entity_ids":["S03"],"start_date":months[5].date().isoformat(),"end_date":latest_end,"period_granularity":"month","metric":"avg_delay_days","direction":"up","expected_magnitude":{"start_avg_delay_days":round(s03_start,2),"end_avg_delay_days":round(s03_end,2)},"what":"S03 delivery delays worsen progressively","where":"supplier S03","when":f"{months[5].date()} to {latest_end}","magnitude":f"average delay rises from {s03_start:.2f} to {s03_end:.2f} days"},{"id":"south_expedited_spike","type":"shipping_cost","entity_ids":["R02"],"start_date":latest_start,"end_date":latest_end,"period_granularity":"month","metric":"expedited_shipping_cost","direction":"up","expected_magnitude":{"earlier_avg_shipping_cost":round(south_before,2),"latest_avg_shipping_cost":round(south_latest,2)},"what":"South expedited shipping costs spike","where":"South region","when":f"{latest_start} to {latest_end}","magnitude":f"average shipping cost rises from {south_before:.2f} to {south_latest:.2f}"},{"id":"west_overstock","type":"inventory_overstock","entity_ids":["R01","cleaning chemicals"],"category":"cleaning chemicals","start_date":months[0].date().isoformat(),"end_date":latest_end,"period_granularity":"month","metric":"units_on_hand","direction":"up","expected_magnitude":{"average_units_on_hand":1100,"reorder_level":200},"what":"West overstock in cleaning chemicals","where":"West region, cleaning chemicals","when":f"{months[0].date()} to {latest_end}","magnitude":"inventory exceeds reorder level"},{"id":"s07_defects","type":"defect_rate","entity_ids":["S07","P011","P012"],"start_date":m8,"end_date":m9,"period_granularity":"month","metric":"defect_rate","direction":"up","expected_magnitude":{"baseline_rate":round(s07_base,4),"cluster_rate":round(s07_cluster,4)},"what":"S07 defect rate cluster","where":"S07 on P011 and P012","when":f"{m8} to {m9}","magnitude":f"defect rate rises from {s07_base:.4f} to {s07_cluster:.4f}"},{"id":"s01_cost_inflation","type":"unit_cost","entity_ids":["S01"],"start_date":latest_start,"end_date":latest_end,"period_granularity":"month","metric":"unit_cost_vs_baseline","direction":"up","expected_magnitude":{"earlier_avg_unit_cost":round(s01_base,2),"latest_avg_unit_cost":round(s01_latest,2),"increase_ratio":round(s01_latest/s01_base,4)},"what":"S01 unit-cost inflation","where":"supplier S01","when":f"{latest_start} to {latest_end}","magnitude":f"average unit cost rises from {s01_base:.2f} to {s01_latest:.2f}"}]
    (output_dir/"anomalies_ground_truth.json").write_text(json.dumps(truth,indent=2),encoding="utf-8"); return {"orders":orders,"suppliers":suppliers,"regions":regions,"products":products,"inventory":inventory,"truth":truth}

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--seed",type=int,default=202609); p.add_argument("--row-count",type=int,default=8000); p.add_argument("--end-month",default="2026-09"); p.add_argument("--output-dir",type=Path,default=Path("generated")); a=p.parse_args(); generate(a.output_dir,a.seed,a.row_count,a.end_month)
