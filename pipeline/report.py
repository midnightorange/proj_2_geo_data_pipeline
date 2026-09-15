# -*- coding: utf-8 -*-
"""F3 自动报告：jinja2 模板 + 图 + 结论文字。"""
import os
import json
import base64
import datetime
import pandas as pd
from jinja2 import Environment, FileSystemLoader


def _img_data_uri(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _build_conclusions(stats):
    """由统计结果自动拼装结论段落。"""
    if len(stats) == 0:
        return ["数据为空，无法生成结论。"]

    count_cols = [c for c in stats.columns if c.endswith("_count")]
    totals = {c[:-6]: int(stats[c].sum()) for c in count_cols}
    total_poi = int(stats["total"].sum())
    n_types = len(totals)
    top_type = max(totals, key=totals.get) if totals else "未知"
    top_count = totals.get(top_type, 0)

    label_counts = stats["label"].value_counts().to_dict()
    zone_count = int(len(stats))

    # 最高 LQ 片区
    lq_rows = stats[stats["lq"] > 0]
    max_lq = None
    if len(lq_rows) > 0:
        idx = lq_rows["lq"].idxmax()
        max_lq = lq_rows.loc[idx]

    lines = [
        f"本次分析共覆盖 {zone_count} 个空间单元、{total_poi} 条 POI 记录，"
        f"涵盖 {n_types} 类功能类型。",
    ]
    if top_type:
        lines.append(
            f"从总量看，「{top_type}」类 POI 数量最多（{top_count} 条），"
            f"占全样本主导地位。"
        )
    if label_counts:
        parts = "、".join(f"{k} {v} 个" for k, v in sorted(label_counts.items(), key=lambda x: -x[1]))
        lines.append(f"功能区识别结果分布为：{parts}。")
    if max_lq is not None:
        lines.append(
            f"其中片区 {max_lq['zone_id']} 的「{max_lq['dominant_type']}」区位商 "
            f"LQ={max_lq['lq']}，显著高于全市平均水平，呈明显空间聚集。"
        )
    return lines


def run(cfg, viz_files):
    """渲染报告 HTML，返回输出路径。"""
    clean_report = {}
    if os.path.exists(cfg["clean_report"]):
        with open(cfg["clean_report"], encoding="utf-8") as f:
            clean_report = json.load(f)

    stats = pd.read_csv(cfg["zone_stats_csv"])
    conclusions = _build_conclusions(stats)

    images = {k: _img_data_uri(v) for k, v in viz_files.items()
              if v.endswith(".png") and os.path.exists(v)}

    plotly_html = ""
    if os.path.exists(viz_files.get("zone_plotly", "")):
        with open(viz_files["zone_plotly"], encoding="utf-8") as f:
            plotly_html = f.read()

    type_counts = clean_report.get("type_counts", {})
    clean_table = [
        {"type": k, "count": int(v)} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
    ]

    ctx = {
        "title": cfg.get("name", "地理空间数据分析报告"),
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input": clean_report.get("input", os.path.basename(cfg["input"])),
        "clean_report": clean_report,
        "clean_table": clean_table,
        "conclusions": conclusions,
        "images": images,
        "plotly_html": plotly_html,
    }

    env = Environment(loader=FileSystemLoader(cfg["template_dir"]))
    tpl = env.get_template("report.html")
    html = tpl.render(**ctx)

    out_path = cfg["output"]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
