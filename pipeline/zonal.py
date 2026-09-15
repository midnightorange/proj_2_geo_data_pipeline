# -*- coding: utf-8 -*-
"""F2c 片区统计：聚合 / 密度 / 占比 / 区位商 LQ，识别主导功能。"""
import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from . import common


def _apply_mapping(dominant, mapping):
    if not mapping:
        return dominant
    return mapping.get(dominant, "混合")


def run(cfg):
    """产出 zone_stats.csv，返回摘要。"""
    counts = pd.read_csv(cfg["overlay_stats_csv"])
    zones = gpd.read_file(cfg["zones_gpkg"])

    all_types = sorted(counts["type"].unique())
    pivot = counts.pivot_table(index="zone_id", columns="type",
                               values="count", fill_value=0)
    # 确保所有片区（含空片区）都有记录
    pivot = pivot.reindex(zones["zone_id"].tolist(), fill_value=0)
    pivot = pivot.fillna(0)

    total_per_type = pivot.sum()
    global_total = float(total_per_type.sum())
    global_share = (total_per_type / global_total).to_dict() if global_total > 0 else {}

    mapping = cfg.get("type_to_function") or {}
    min_samples = int(cfg.get("min_samples", 10))
    lq_threshold = float(cfg.get("lq", 1.0))

    rows = []
    for zid in zones["zone_id"]:
        area = float(zones.loc[zones["zone_id"] == zid, "area_km2"].iloc[0])
        c = pivot.loc[zid]
        total = int(c.sum())
        row = {"zone_id": zid, "area_km2": round(area, 4), "total": total}

        if total == 0:
            row["dominant_type"] = ""
            row["lq"] = 0.0
            row["label"] = "无数据"
        elif total < min_samples:
            row["dominant_type"] = ""
            row["lq"] = 0.0
            row["label"] = "样本不足"
        else:
            lqs = {}
            for t in all_types:
                g = global_share.get(t, 0.0)
                if g > 0:
                    lqs[t] = (c[t] / total) / g
            dom = max(lqs, key=lqs.get)
            lq = float(lqs[dom])
            row["dominant_type"] = dom
            row["lq"] = round(lq, 3)
            label = dom if lq >= lq_threshold else "混合"
            row["label"] = _apply_mapping(label, mapping)

        # 各类计数 / 密度 / 占比 / LQ
        for t in all_types:
            cnt = int(c.get(t, 0))
            row[f"{t}_count"] = cnt
            row[f"{t}_density"] = round(cnt / area, 3) if area > 0 else 0.0
            row[f"{t}_share"] = round(cnt / total, 4) if total > 0 else 0.0
            g = global_share.get(t, 0.0)
            row[f"{t}_lq"] = round((cnt / total) / g, 3) if (total > 0 and g > 0) else 0.0

        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(cfg["zone_stats_csv"], index=False, encoding="utf-8-sig")

    label_counts = df["label"].value_counts().to_dict()
    return {
        "zone_count": int(len(df)),
        "poi_total": int(global_total),
        "types": all_types,
        "global_share": global_share,
        "label_counts": {str(k): int(v) for k, v in label_counts.items()},
    }
