# 多源地理空间数据自动化分析管线

一条命令把「原始 POI 数据」变成「图文决策报告」：清洗 → 核密度 → 空间叠加 → 片区统计 → 自动报告。

## 快速开始

```powershell
cd d:\My_Code\proj_2_data_analysis\geo-data-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) 下载公开数据（成都武侯区：行政区边界 + OSM POI）
python scripts\download_data.py --adcode 510107 --name wuhou

# 2) 一条命令出报告
python run.py --input data\raw\poi_wuhou.csv --zone data\raw\admin_wuhou.geojson --output output\report_wuhou.html
```

打开 `output\report_wuhou.html` 即可查看报告，浏览器可直接打印为 PDF。

## 常用参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--input` | 输入数据（csv / shp / geojson） | 必填 |
| `--output` | 报告输出路径 | `output/report.html` |
| `--zone` | 片区边界（shp/geojson），缺省自动网格 | — |
| `--radius` | 核密度带宽 / 缓冲半径（米） | `500` |
| `--grid-size` | 自动网格边长（米） | `2000` |
| `--lq` | 区位商阈值 | `1.0` |
| `--min-samples` | 样本不足判定阈值 | `10` |
| `--step` | 从该步起执行（clean/kde/overlay/zonal/viz/report） | `clean` |
| `--coord` | 输入坐标类型（wgs84/gcj02） | `wgs84` |
| `--force` | 强制重跑 | — |

改参数重跑：`--radius 800 --lq 1.2`，无需改代码；中间产物已落盘，`--step zonal` 只跑后半段。

## 目录结构

```
geo-data-pipeline/
├── run.py               # CLI 主入口
├── config.yaml          # 默认参数
├── requirements.txt
├── pipeline/            # 五步串行管线
│   ├── common.py        # 加载 / 坐标转换 / UTM 投影 / 配色
│   ├── clean.py         # F1 清洗
│   ├── kde.py           # F2a 核密度
│   ├── overlay.py       # F2b 叠加
│   ├── zonal.py         # F2c 片区统计 + LQ
│   ├── viz.py           # 制图
│   └── report.py        # F3 自动报告
├── templates/report.html
├── scripts/download_data.py
├── data/raw/            # 原始数据（只读）
├── data/intermediate/   # 中间产物（断点续跑）
└── output/              # 报告与图
```

## 数据来源

- 行政区边界：阿里云 DataV 地图选择器（`geo.datav.aliyun.com/areas_v3/bound/{adcode}.json`），GCJ-02 坐标，脚本内已转为 WGS-84。
- POI 数据：OpenStreetMap Overpass API（`overpass-api.de`），WGS-84 坐标，`amenity / shop / tourism / leisure / office / building / landuse` 等标签映射为功能区大类（商业 / 科教 / 住宅 / 公共服务 / 工业）。

## 坐标规范

- 存储统一 WGS-84（EPSG:4326）；
- 面积、距离、缓冲统一投影到 UTM（按质心经度自动选带）；
- 输入若为 GCJ-02，可用 `--coord gcj02` 自动反算回 WGS-84。
