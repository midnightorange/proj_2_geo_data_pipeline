# -*- coding: utf-8 -*-
"""制图：matplotlib 静态图（含地图底图）+ plotly 交互图。"""
import os
import io
import math
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
import requests
from . import common

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

USER_AGENT = "geo-data-pipeline/0.1 (portfolio demo)"
# ArcGIS World Street Map（Web Mercator，WGS-84 底图，无需 API Key）
TILE_TPL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}")
ATTRIBUTION = "© Esri © OpenStreetMap contributors"


def _color(label):
    return common.COLOR_MAP.get(label, "#8e24aa")


# ---------------------------------------------------------------------------
# 地图底图（Web Mercator 瓦片下载 + 拼接）
# ---------------------------------------------------------------------------
def _deg2num(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = (lon + 180.0) / 360.0 * n
    ytile = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return xtile, ytile


def _num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon = xtile / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ytile / n))))
    return lat, lon


def _fetch_tile(z, x, y):
    url = TILE_TPL.format(z=z, y=y, x=x)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def _pick_zoom(bounds, max_tiles=24):
    minx, miny, maxx, maxy = bounds
    for zoom in range(17, 8, -1):
        x0, y0 = _deg2num(maxy, minx, zoom)
        x1, y1 = _deg2num(miny, maxx, zoom)
        cols = int(math.floor(x1)) - int(math.floor(x0)) + 1
        rows = int(math.floor(y1)) - int(math.floor(y0)) + 1
        if cols * rows <= max_tiles:
            return zoom
    return 9


def _add_basemap(ax, bounds):
    """在 WGS84 坐标轴上叠加地图底图；网络失败时静默跳过。"""
    try:
        minx, miny, maxx, maxy = bounds
        zoom = _pick_zoom(bounds)
        x0f, y0f = _deg2num(maxy, minx, zoom)
        x1f, y1f = _deg2num(miny, maxx, zoom)
        x0, y0 = int(math.floor(x0f)), int(math.floor(y0f))
        x1, y1 = int(math.floor(x1f)), int(math.floor(y1f))
        cols = x1 - x0 + 1
        rows = y1 - y0 + 1
        if cols * rows > 64:
            return

        canvas = Image.new("RGB", (cols * 256, rows * 256))
        for i in range(cols):
            for j in range(rows):
                canvas.paste(_fetch_tile(zoom, x0 + i, y0 + j), (i * 256, j * 256))

        top = _num2deg(x0, y0, zoom)[0]
        left = _num2deg(x0, y0, zoom)[1]
        bottom = _num2deg(x0, y0 + rows, zoom)[0]
        right = _num2deg(x0 + cols, y0, zoom)[1]

        ax.imshow(canvas, extent=(left, right, bottom, top), aspect="auto",
                  zorder=0, interpolation="bilinear")
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.text(0.01, 0.01, ATTRIBUTION, transform=ax.transAxes,
                fontsize=7, color="#555555", ha="left", va="bottom", zorder=5)
    except Exception:  # noqa: BLE001
        # 底图不可用时不阻断出图
        pass


# ---------------------------------------------------------------------------
# 各图
# ---------------------------------------------------------------------------
def _kde_heatmap(kde_gpkg, out_png):
    gdf = gpd.read_file(kde_gpkg)
    if len(gdf) == 0:
        return
    fig, ax = plt.subplots(figsize=(10, 8), dpi=120)
    _add_basemap(ax, gdf.total_bounds)
    sc = ax.scatter(gdf.geometry.x, gdf.geometry.y, c=gdf["density_norm"],
                    cmap="inferno", s=10, marker="s", linewidths=0, alpha=0.55,
                    zorder=3)
    fig.colorbar(sc, ax=ax, label="归一化密度", shrink=0.8)
    ax.set_title("POI 核密度热力场")
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def _zone_map(zones_gpkg, zone_stats_csv, out_png):
    zones = gpd.read_file(zones_gpkg)
    stats = pd.read_csv(zone_stats_csv)
    gdf = zones.merge(stats, on="zone_id", how="left")
    gdf["label"] = gdf["label"].fillna("无数据")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=120)
    _add_basemap(ax, gdf.total_bounds)
    for label, grp in gdf.groupby("label"):
        grp.plot(ax=ax, color=_color(label), edgecolor="white", linewidth=0.5,
                 alpha=0.65, label=label, zorder=3)
    ax.set_title("片区主导功能识别")
    ax.set_axis_off()
    ax.legend(loc="lower right", fontsize=8, frameon=True)
    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def _zone_bar(zone_stats_csv, out_png):
    stats = pd.read_csv(zone_stats_csv)
    count_cols = [c for c in stats.columns if c.endswith("_count")]
    totals = {c[:-6]: float(stats[c].sum()) for c in count_cols}
    if not totals:
        return
    names = list(totals.keys())
    values = list(totals.values())
    order = np.argsort(values)[::-1]
    names = [names[i] for i in order]
    values = [values[i] for i in order]
    fig, ax = plt.subplots(figsize=(8, 5), dpi=120)
    bars = ax.bar(names, values, color=[_color(n) for n in names])
    ax.set_title("各类 POI 数量分布")
    ax.set_ylabel("POI 数量")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.bar_label(bars, padding=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def _zone_plotly(zone_stats_csv, out_html):
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except Exception:
        return
    stats = pd.read_csv(zone_stats_csv)
    count_cols = [c for c in stats.columns if c.endswith("_count")]
    totals = {c[:-6]: float(stats[c].sum()) for c in count_cols}
    if not totals:
        return
    names = list(totals.keys())
    values = list(totals.values())
    fig = go.Figure(data=[go.Bar(x=names, y=values,
                                 marker_color=[_color(n) for n in names])])
    fig.update_layout(title="各类 POI 数量（交互）",
                      xaxis_title="类型", yaxis_title="数量")
    pio.write_html(fig, out_html, include_plotlyjs="cdn", full_html=False)


def run(cfg):
    """生成全部图，返回图文件路径映射。"""
    img_dir = cfg["img_dir"]
    os.makedirs(img_dir, exist_ok=True)
    files = {}

    kde_png = os.path.join(img_dir, "kde_heatmap.png")
    _kde_heatmap(cfg["kde_points_gpkg"], kde_png)
    files["kde_heatmap"] = kde_png

    zone_map = os.path.join(img_dir, "zone_map.png")
    _zone_map(cfg["zones_gpkg"], cfg["zone_stats_csv"], zone_map)
    files["zone_map"] = zone_map

    zone_bar = os.path.join(img_dir, "zone_bar.png")
    _zone_bar(cfg["zone_stats_csv"], zone_bar)
    files["zone_bar"] = zone_bar

    plotly_html = os.path.join(img_dir, "zone_plotly.html")
    _zone_plotly(cfg["zone_stats_csv"], plotly_html)
    files["zone_plotly"] = plotly_html

    return files
