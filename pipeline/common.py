# -*- coding: utf-8 -*-
"""共享基建：数据加载、坐标转换、UTM 投影、配色与配置合并。"""
import os
import math
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# 功能大类配色（与项目1保持一致）
COLOR_MAP = {
    "商业": "#e53935",
    "住宅": "#fb8c00",
    "科教": "#1e88e5",
    "公共服务": "#43a047",
    "工业": "#795548",
    "混合": "#8e24aa",
    "样本不足": "#9e9e9e",
    "无数据": "#eeeeee",
}


# ---------------------------------------------------------------------------
# 坐标转换：WGS-84 <-> GCJ-02（国测局加密）
# ---------------------------------------------------------------------------
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lon, lat):
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x, y):
    ret = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
           + 0.2 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = (300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon, lat):
    """单个点 WGS-84 -> GCJ-02。非中国范围返回原值。"""
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lon + dlon, lat + dlat


def wgs84_to_gcj02_vec(lons, lats):
    lons, lats = np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)
    out_lon, out_lat = np.empty_like(lons), np.empty_like(lats)
    for i in range(len(lons)):
        out_lon[i], out_lat[i] = wgs84_to_gcj02(lons[i], lats[i])
    return out_lon, out_lat


def gcj02_to_wgs84(lon, lat):
    """GCJ-02 -> WGS-84，迭代逼近（偏移量小，收敛快）。"""
    if _out_of_china(lon, lat):
        return lon, lat
    w_lon, w_lat = lon, lat
    for _ in range(3):
        g_lon, g_lat = wgs84_to_gcj02(w_lon, w_lat)
        w_lon -= g_lon - lon
        w_lat -= g_lat - lat
    return w_lon, w_lat


def gcj02_to_wgs84_vec(lons, lats):
    lons, lats = np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)
    out_lon, out_lat = np.empty_like(lons), np.empty_like(lats)
    for i in range(len(lons)):
        out_lon[i], out_lat[i] = gcj02_to_wgs84(lons[i], lats[i])
    return out_lon, out_lat


# ---------------------------------------------------------------------------
# 投影
# ---------------------------------------------------------------------------
def utm_epsg(lon):
    """按经度返回北半球 WGS84 UTM EPSG。"""
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return 32600 + zone


def to_utm(gdf):
    """投影到 UTM（按几何范围中心经度自动选带），用于面积/距离/缓冲计算。"""
    gdf = gdf.copy()
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    minx, miny, maxx, maxy = gdf.total_bounds
    lon = (minx + maxx) / 2.0
    return gdf.to_crs(epsg=utm_epsg(lon))


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def _pick_col(df, candidates, default=None):
    for c in candidates:
        if c in df.columns:
            return c
    return default


def load_input(path, lon_col="lon", lat_col="lat", type_col="type",
               crs=None, coord="wgs84"):
    """读 CSV / GeoJSON / Shapefile 为 GeoDataFrame，统一返回 WGS-84。

    - CSV：按 lon/lat 列构造点；
    - 空间文件：直接读取，若指定 crs 则强制指定；
    - coord='gcj02' 时把 GCJ-02 坐标反算回 WGS-84。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        lon_col = _pick_col(df, [lon_col, "lon", "lng", "longitude", "经度", "x"], lon_col)
        lat_col = _pick_col(df, [lat_col, "lat", "latitude", "纬度", "y"], lat_col)
        if lon_col is None or lat_col is None:
            raise ValueError("无法从 CSV 定位经纬度列，请用 --lon/--lat 指定")
        df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
        df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        geometry = [Point(x, y) if pd.notna(x) and pd.notna(y) else None
                    for x, y in zip(df[lon_col], df[lat_col])]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    else:
        gdf = gpd.read_file(path)
        if crs is not None:
            gdf = gdf.set_crs(crs)
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)

    if coord == "gcj02":
        lons = gdf.geometry.x.to_numpy()
        lats = gdf.geometry.y.to_numpy()
        w_lon, w_lat = gcj02_to_wgs84_vec(lons, lats)
        gdf = gdf.copy()
        gdf["geometry"] = [Point(x, y) for x, y in zip(w_lon, w_lat)]
        gdf = gdf.set_crs(epsg=4326)

    return gdf


# ---------------------------------------------------------------------------
# 配置合并
# ---------------------------------------------------------------------------
def parse_config(args, defaults):
    """CLI 参数与 config.yaml（若有）合并，args 优先。"""
    import yaml
    cfg = dict(defaults)
    cfg_path = getattr(args, "config", None)
    if cfg_path and os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            cfg.update(data)
    # CLI 显式参数覆盖配置（None 不覆盖）
    for key in ("radius", "lq", "crs", "coord", "grid_size", "min_samples", "bbox"):
        val = getattr(args, key, None)
        if val is not None:
            cfg[key] = val
    cfg["input"] = args.input
    cfg["output"] = args.output
    cfg["zone"] = getattr(args, "zone", None)
    cfg["no_viz"] = getattr(args, "no_viz", False)
    cfg["force"] = getattr(args, "force", False)
    cfg["lon"] = args.lon
    cfg["lat"] = args.lat
    cfg["type_col"] = getattr(args, "type_col", "type")
    return cfg
