"""Data-quality checks shared by generation tests and the loader."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

@dataclass
class ValidationResult:
    accepted: pd.DataFrame
    quarantined: pd.DataFrame
    report: dict

def validate_orders(orders: pd.DataFrame, suppliers: pd.DataFrame, products: pd.DataFrame, regions: pd.DataFrame) -> ValidationResult:
    work=orders.copy(); reasons=[[] for _ in range(len(work))]
    def mark(mask, reason):
        for i in work.index[mask]: reasons[work.index.get_loc(i)].append(reason)
    mark(work.order_id.isna() | work.unit_cost.isna() | work.supplier_id.isna(), "null_required_field")
    mark(work.order_id.duplicated(keep="first"), "duplicate_order_id")
    mark(work.quantity.le(0) | work.unit_cost.lt(0) | work.shipping_cost.lt(0) | work.defective_units.lt(0), "negative_or_invalid_numeric")
    od=pd.to_datetime(work.order_date,errors="coerce"); dd=pd.to_datetime(work.delivered_date,errors="coerce"); mark(dd < od, "delivered_before_order")
    mark(~work.supplier_id.isin(set(suppliers.supplier_id.dropna())), "unknown_supplier"); mark(~work.product_id.isin(set(products.product_id)), "unknown_product"); mark(~work.region_id.isin(set(regions.region_id)), "unknown_region")
    mark(work.quantity.gt(10000) | work.unit_cost.gt(100000), "outlier_sane_range")
    reason=pd.Series([";".join(x) for x in reasons],index=work.index); bad=reason.ne(""); quarantined=work.loc[bad].copy(); quarantined["reason"]=reason[bad]; accepted=work.loc[~bad].copy()
    counts={r:int(reason.str.contains(r,regex=False).sum()) for r in ["null_required_field","duplicate_order_id","negative_or_invalid_numeric","delivered_before_order","unknown_supplier","unknown_product","unknown_region","outlier_sane_range"]}
    return ValidationResult(accepted,quarantined,{"rows":len(work),"accepted":len(accepted),"quarantined":len(quarantined),"checks":counts})

