# -*- coding: utf-8 -*-
"""CLI 主入口：一条命令跑通 清洗 → 核密度 → 叠加 → 片区统计 → 制图 → 报告。"""
import os
import sys
import argparse

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import common, clean, kde, overlay, zonal, viz, report

DEFAULTS = {
    "radius": 500,
    "lq": 1.0,
    "crs": None,
    "coord": "wgs84",
    "grid_size": 2000,
    "min_samples": 10,
    "bbox": None,
}

STEPS = ["clean", "kde", "overlay", "zonal", "viz", "report"]


def _build_cfg(args):
    cfg = common.parse_config(args, DEFAULTS)
    workdir = os.path.dirname(os.path.abspath(__file__))
    intermediate = os.path.join(workdir, "data", "intermediate")
    os.makedirs(intermediate, exist_ok=True)

    cfg["workdir"] = workdir
    cfg["intermediate"] = intermediate
    cfg["poi_clean_gpkg"] = os.path.join(intermediate, "poi_clean.gpkg")
    cfg["clean_report"] = os.path.join(intermediate, "clean_report.json")
    cfg["kde_points_gpkg"] = os.path.join(intermediate, "kde_points.gpkg")
    cfg["core_areas_geojson"] = os.path.join(intermediate, "core_areas.geojson")
    cfg["zones_gpkg"] = os.path.join(intermediate, "zones.gpkg")
    cfg["overlay_stats_csv"] = os.path.join(intermediate, "overlay_stats.csv")
    cfg["zone_stats_csv"] = os.path.join(intermediate, "zone_stats.csv")
    cfg["img_dir"] = os.path.join(workdir, "output", "img")
    cfg["template_dir"] = os.path.join(workdir, "templates")

    if cfg.get("output") is None:
        cfg["output"] = os.path.join(workdir, "output", "report.html")
    cfg["name"] = os.path.splitext(os.path.basename(args.input))[0]
    return cfg


def _outputs(cfg):
    return {
        "clean": cfg["poi_clean_gpkg"],
        "kde": cfg["kde_points_gpkg"],
        "overlay": cfg["overlay_stats_csv"],
        "zonal": cfg["zone_stats_csv"],
        "viz": os.path.join(cfg["img_dir"], "zone_map.png"),
        "report": cfg["output"],
    }


def _done(cfg, step):
    return os.path.exists(_outputs(cfg)[step])


def main(argv=None):
    p = argparse.ArgumentParser(description="多源地理空间数据自动化分析管线")
    p.add_argument("--input", required=True, help="输入数据（csv / shp / geojson）")
    p.add_argument("--output", help="报告输出路径（默认 output/report.html）")
    p.add_argument("--config", help="参数配置文件（yaml / json）")
    p.add_argument("--step", default="clean", choices=STEPS,
                   help="从该步起执行（默认 clean）")
    p.add_argument("--lon", default="lon", help="经度列名")
    p.add_argument("--lat", default="lat", help="纬度列名")
    p.add_argument("--type-col", default="type", help="类型列名")
    p.add_argument("--radius", type=float, help="核密度带宽 / 缓冲半径（米）")
    p.add_argument("--zone", help="片区边界（shp/geojson），缺省自动网格")
    p.add_argument("--grid-size", type=float, dest="grid_size", help="自动网格边长（米）")
    p.add_argument("--lq", type=float, help="区位商阈值")
    p.add_argument("--min-samples", type=int, dest="min_samples", help="样本不足阈值")
    p.add_argument("--crs", help="强制输入 CRS")
    p.add_argument("--coord", choices=["wgs84", "gcj02"], help="输入坐标类型")
    p.add_argument("--bbox", help="边界框 minx,miny,maxx,maxy")
    p.add_argument("--no-viz", action="store_true", dest="no_viz", help="跳过制图")
    p.add_argument("--force", action="store_true", help="强制重跑所有步骤")
    args = p.parse_args(argv)

    cfg = _build_cfg(args)
    if not os.path.exists(args.input):
        p.error(f"输入文件不存在：{args.input}")

    start = STEPS.index(args.step)
    summaries = {}
    viz_files = {k: os.path.join(cfg["img_dir"], f) for k, f in {
        "kde_heatmap": "kde_heatmap.png",
        "zone_map": "zone_map.png",
        "zone_bar": "zone_bar.png",
        "zone_plotly": "zone_plotly.html",
    }.items()}

    for step in STEPS[start:]:
        if step == "viz" and cfg["no_viz"]:
            print("[viz] 已跳过（--no-viz）")
            continue
        if _done(cfg, step) and not cfg["force"]:
            print(f"[{step}] 中间产物已存在，跳过（--force 可强制重跑）")
            continue

        print(f"[{step}] 开始执行…")
        if step == "clean":
            summaries["clean"] = clean.run(cfg)
        elif step == "kde":
            summaries["kde"] = kde.run(cfg)
        elif step == "overlay":
            summaries["overlay"] = overlay.run(cfg)
        elif step == "zonal":
            summaries["zonal"] = zonal.run(cfg)
        elif step == "viz":
            viz_files = viz.run(cfg)
        elif step == "report":
            out = report.run(cfg, viz_files)
            print(f"[report] 已生成：{out}")
        print(f"[{step}] 完成")

    print("\n管线执行结束。")
    print(f"报告位置：{cfg['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
