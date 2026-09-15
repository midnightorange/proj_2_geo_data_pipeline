# -*- coding: utf-8 -*-
"""下载公开数据：DataV 行政区边界（GCJ-02） + OSM POI（WGS-84）。

用法：
    python scripts/download_data.py --adcode 510107 --name wuhou

产出（data/raw/）：
    admin_<name>.geojson   行政区边界（已转为 WGS-84）
    poi_<name>.csv         带 type/lon/lat 的 POI 点（WGS-84，type 为功能区大类）
"""
import os
import sys
import json
import argparse
import time

import requests
import pandas as pd
import geopandas as gpd
from shapely.ops import transform as shp_transform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import common

USER_AGENT = "geo-data-pipeline/0.1 (portfolio demo)"


# ---------------------------------------------------------------------------
# OSM 标签 -> 功能区大类
# ---------------------------------------------------------------------------
_EDU = {"school", "university", "college", "kindergarten", "childcare",
        "library", "research_institute", "driving_school", "language_school",
        "music_school", "training"}
_PUBLIC = {"hospital", "clinic", "doctors", "dentist", "veterinary", "police",
           "fire_station", "post_office", "townhall", "community_centre",
           "place_of_worship", "courthouse", "prison", "social_facility",
           "nursing_home", "recycling", "public_building", "embassy",
           "government"}
_RETAIL = {"restaurant", "cafe", "fast_food", "food_court", "bar", "pub",
           "biergarten", "ice_cream", "nightclub", "marketplace", "bank",
           "atm", "bureau_de_change", "cinema", "theatre", "casino",
           "pharmacy", "fuel", "charging_station", "car_wash"}
_HOTEL = {"hotel", "motel", "guest_house", "hostel", "apartment", "chalet"}
_RES_BUILDING = {"residential", "apartments", "house", "detached", "terrace",
                 "dormitory", "bungalow", "semidetached_house"}


def osm_to_category(tags):
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    tourism = tags.get("tourism")
    leisure = tags.get("leisure")
    office = tags.get("office")
    building = tags.get("building")
    landuse = tags.get("landuse")

    if landuse in {"industrial", "quarry", "port"} or tags.get("man_made") in {"works", "factory"}:
        return "工业"
    if landuse == "residential" or building in _RES_BUILDING:
        return "住宅"
    if amenity in _EDU or office in {"educational_institution", "research"}:
        return "科教"
    if amenity in _PUBLIC or office == "government":
        return "公共服务"
    if tourism in _HOTEL or shop or amenity in _RETAIL or leisure:
        return "商业"
    if tourism:
        return "公共服务"
    return None


# ---------------------------------------------------------------------------
# 下载函数
# ---------------------------------------------------------------------------
def download_boundary(adcode, out_path):
    url = f"https://geo.datav.aliyun.com/areas_v3/bound/{adcode}.json"
    r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    fc = r.json()
    gdf = gpd.GeoDataFrame.from_features(fc["features"], crs="EPSG:4326")

    # DataV 坐标为 GCJ-02，转为 WGS-84
    def _conv(x, y, z=None):
        nx, ny = common.gcj02_to_wgs84(x, y)
        return (nx, ny) if z is None else (nx, ny, z)
    gdf["geometry"] = gdf["geometry"].apply(lambda g: shp_transform(_conv, g))
    gdf.to_file(out_path, driver="GeoJSON")
    return gdf


def download_poi(gdf, out_csv):
    minx, miny, maxx, maxy = gdf.total_bounds
    # Overpass bbox 顺序：south, west, north, east
    bbox = f"{miny},{minx},{maxy},{maxx}"
    query = f"""
[out:json][timeout:120];
(
  node["amenity"]({bbox});
  node["shop"]({bbox});
  node["tourism"]({bbox});
  node["leisure"]({bbox});
  node["office"]({bbox});
  node["building"~"residential|apartments|house|detached|terrace|dormitory|bungalow|semidetached_house"]({bbox});
  way["landuse"~"residential|industrial|commercial|quarry|port"]({bbox});
);
out tags center;
"""
    url = "https://overpass-api.de/api/interpreter"
    for attempt in range(3):
        try:
            r = requests.post(url, data={"data": query},
                              headers={"User-Agent": USER_AGENT}, timeout=180)
            r.raise_for_status()
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  Overpass 重试 {attempt + 1}：{e}")
            time.sleep(3)

    data = r.json()
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        cat = osm_to_category(tags)
        if cat is None:
            continue
        if el["type"] == "node":
            lon, lat = el.get("lon"), el.get("lat")
        else:
            c = el.get("center", {})
            lon, lat = c.get("lon"), c.get("lat")
        if lon is None or lat is None:
            continue
        rows.append({"type": cat, "lon": lon, "lat": lat,
                     "name": tags.get("name", "")})

    df = pd.DataFrame(rows, columns=["type", "lon", "lat", "name"])
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return df


def main():
    p = argparse.ArgumentParser(description="下载公开地理数据")
    p.add_argument("--adcode", default="510107", help="DataV 行政区 adcode（默认成都武侯区）")
    p.add_argument("--name", default="wuhou", help="输出文件名前缀")
    p.add_argument("--out", default=None, help="输出目录（默认 data/raw）")
    args = p.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(root, "data", "raw")
    os.makedirs(out_dir, exist_ok=True)

    boundary_path = os.path.join(out_dir, f"admin_{args.name}.geojson")
    poi_path = os.path.join(out_dir, f"poi_{args.name}.csv")

    print(f"[1/2] 下载行政区边界（adcode={args.adcode}）…")
    gdf = download_boundary(args.adcode, boundary_path)
    print(f"      已保存：{boundary_path}（{len(gdf)} 个要素）")

    print("[2/2] 下载 OSM POI …")
    df = download_poi(gdf, poi_path)
    print(f"      已保存：{poi_path}（{len(df)} 条 POI）")
    if len(df):
        print(df["type"].value_counts().to_string())

    print("完成。")


if __name__ == "__main__":
    main()
