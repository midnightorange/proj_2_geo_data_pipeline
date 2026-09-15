# -*- coding: utf-8 -*-
"""F2a 核密度估计：生成 POI 密度场与高密度核心区。"""
import os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from . import common


def run(cfg):
    """产出 kde_points.gpkg 与 core_areas.geojson，返回摘要。"""
    gdf = gpd.read_file(cfg["poi_clean_gpkg"])
    if len(gdf) < 3:
        summary = {"n": int(len(gdf)), "skipped": True, "reason": "样本点不足 3 个"}
        _write_empty(cfg)
        return summary

    utm = common.to_utm(gdf)
    x = utm.geometry.x.to_numpy()
    y = utm.geometry.y.to_numpy()

    from scipy.stats import gaussian_kde
    # 默认 Silverman/Scott 带宽；--radius 主要作用于缓冲/网格填充
    kde = gaussian_kde(np.vstack([x, y]))

    # 规则网格采样
    radius = cfg.get("radius") or 500
    pad = max(radius, 500)
    xmin, ymin, xmax, ymax = x.min() - pad, y.min() - pad, x.max() + pad, y.max() + pad
    nx = ny = 120
    xs = np.linspace(xmin, xmax, nx)
    ys = np.linspace(ymin, ymax, ny)
    xx, yy = np.meshgrid(xs, ys)
    positions = np.vstack([xx.ravel(), yy.ravel()])
    dens = kde(positions).reshape(xx.shape)
    dens = dens / dens.max() if dens.max() > 0 else dens

    # 转回 WGS-84 点
    grid_utm = gpd.GeoDataFrame(geometry=[Point(a, b) for a, b in zip(xx.ravel(), yy.ravel())],
                                crs=utm.crs)
    grid_wgs = grid_utm.to_crs(epsg=4326)
    grid_wgs["density"] = dens.ravel()
    grid_wgs["density_norm"] = dens.ravel()

    grid_wgs.to_file(cfg["kde_points_gpkg"], driver="GPKG")

    # 高密度核心区（>= 90 分位），缓冲后合并
    thr = float(np.quantile(dens.ravel(), 0.9))
    core = grid_wgs[grid_wgs["density"] >= thr].copy()
    cell = float(xs[1] - xs[0]) / 2.0
    core_utm = common.to_utm(core)
    polys = [p.buffer(cell) for p in core_utm.geometry]
    merged = unary_union(polys)
    if merged.is_empty:
        core_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    else:
        if merged.geom_type == "Polygon":
            merged = [merged]
        else:
            merged = list(merged.geoms)
        core_gdf = gpd.GeoDataFrame(geometry=merged, crs=core_utm.crs).to_crs(epsg=4326)
    core_gdf.to_file(cfg["core_areas_geojson"], driver="GeoJSON")

    return {
        "n": int(len(gdf)),
        "skipped": False,
        "bandwidth": getattr(kde, "factor", None),
        "threshold_90pct": float(thr),
        "core_area_count": int(len(core_gdf)),
        "grid": [nx, ny],
    }


def _write_empty(cfg):
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    empty.to_file(cfg["kde_points_gpkg"], driver="GPKG")
    empty.to_file(cfg["core_areas_geojson"], driver="GeoJSON")
