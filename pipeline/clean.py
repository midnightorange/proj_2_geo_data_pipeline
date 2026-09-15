# -*- coding: utf-8 -*-
"""F1 数据清洗：字段规整 / 去重 / 坐标转换 / 边界过滤。"""
import os
import json
import pandas as pd
import geopandas as gpd
from . import common


def _normalize_type(series, type_col):
    """统一类型列：优先 type_col，其次常见备选列。"""
    if type_col in series.columns:
        return series[type_col].astype(str).str.strip()
    for c in ("type", "category", "amenity", "fclass", "大类", "类别"):
        if c in series.columns:
            return series[c].astype(str).str.strip()
    return pd.Series(["未分类"] * len(series), index=series.index)


def run(cfg):
    """执行清洗，产出 poi_clean.gpkg 与 clean_report.json。"""
    out_gpkg = cfg["poi_clean_gpkg"]
    report_path = cfg["clean_report"]

    gdf = common.load_input(
        cfg["input"], lon_col=cfg.get("lon", "lon"), lat_col=cfg.get("lat", "lat"),
        type_col=cfg.get("type_col", "type"), crs=cfg.get("crs"),
        coord=cfg.get("coord", "wgs84"),
    )
    before = len(gdf)

    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[gdf.geometry.is_valid].copy()
    dropped_null_geom = before - len(gdf)

    gdf["type"] = _normalize_type(gdf, cfg.get("type_col", "type"))
    gdf = gdf[["type", "geometry"]].copy()

    # 去除空类型
    gdf = gdf[gdf["type"].str.len() > 0]

    # 坐标转换到 WGS-84 已在 load_input 完成；此处按 WGS84 记录
    gdf = gdf.set_crs(epsg=4326)

    # 去重（type, lon, lat）
    gdf["lon"] = gdf.geometry.x.round(6)
    gdf["lat"] = gdf.geometry.y.round(6)
    gdf = gdf.drop_duplicates(subset=["type", "lon", "lat"]).drop(columns=["lon", "lat"])

    # 可选边界框过滤（minx, miny, maxx, maxy）
    bbox = cfg.get("bbox")
    if bbox:
        if isinstance(bbox, str):
            bbox = [float(v) for v in bbox.split(",")]
        minx, miny, maxx, maxy = bbox
        gdf = gdf.cx[minx:maxx, miny:maxy]

    after = len(gdf)

    gdf.to_file(out_gpkg, driver="GPKG")

    report = {
        "input": os.path.basename(cfg["input"]),
        "rows_before": int(before),
        "rows_after": int(after),
        "dropped_null_geom": int(dropped_null_geom),
        "dropped_duplicates": int(dropped_null_geom + before - after),
        "type_counts": gdf["type"].value_counts().to_dict(),
        "crs": "EPSG:4326",
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report
