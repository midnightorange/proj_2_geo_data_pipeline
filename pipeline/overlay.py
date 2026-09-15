# -*- coding: utf-8 -*-
"""F2b 叠加分析：缓冲 + 空间连接，统计各片区各类 POI 数量。"""
import os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box, Point
from . import common


def _ensure_zone_id(gdf):
    if "zone_id" not in gdf.columns:
        gdf = gdf.copy()
        gdf["zone_id"] = [f"z{i}" for i in range(len(gdf))]
    return gdf


def _make_grid(poi_wgs, grid_size):
    utm = common.to_utm(poi_wgs)
    minx, miny, maxx, maxy = utm.total_bounds
    cols = max(1, int(np.ceil((maxx - minx) / grid_size)))
    rows = max(1, int(np.ceil((maxy - miny) / grid_size)))
    cells = []
    for i in range(rows):
        for j in range(cols):
            x0 = minx + j * grid_size
            y0 = miny + i * grid_size
            x1 = min(x0 + grid_size, maxx)
            y1 = min(y0 + grid_size, maxy)
            cells.append({"zone_id": f"grid_{i}_{j}",
                          "geometry": box(x0, y0, x1, y1)})
    return gpd.GeoDataFrame(cells, crs=utm.crs)


def run(cfg):
    """产出 zones.gpkg 与 overlay_stats.csv，返回摘要。"""
    poi = gpd.read_file(cfg["poi_clean_gpkg"])

    if cfg.get("zone"):
        zones = gpd.read_file(cfg["zone"])
        zones = _ensure_zone_id(zones)
        if zones.crs is None:
            zones = zones.set_crs(epsg=4326)
        # 若为点要素，先缓冲
        if all(zones.geom_type == "Point"):
            z_utm = common.to_utm(zones)
            z_utm["geometry"] = z_utm.geometry.buffer(cfg.get("radius", 500))
            zones = z_utm.to_crs(epsg=4326)
        source = os.path.basename(cfg["zone"])
    else:
        zones = _make_grid(poi, cfg.get("grid_size", 2000))
        source = f"自动网格 {cfg.get('grid_size', 2000)}m"

    # 计算面积（投影系，km²）
    zones_utm = common.to_utm(zones)
    zones = zones.to_crs(epsg=4326)
    zones["area_km2"] = zones_utm.geometry.area / 1e6
    zones.to_file(cfg["zones_gpkg"], driver="GPKG")

    # 空间连接：POI 是否落在片区内
    poi_utm = common.to_utm(poi)
    z_utm = common.to_utm(zones[["zone_id", "geometry"]])

    joined = gpd.sjoin(poi_utm, z_utm, predicate="within", how="inner")
    if joined.empty:
        counts = pd.DataFrame(columns=["zone_id", "type", "count"])
    else:
        counts = (joined.groupby(["zone_id", "type"]).size()
                  .reset_index(name="count"))
    counts.to_csv(cfg["overlay_stats_csv"], index=False, encoding="utf-8-sig")

    return {
        "zone_source": source,
        "zone_count": int(len(zones)),
        "matched_poi": int(len(joined)) if not joined.empty else 0,
    }
