#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 GPX 生成带地图底图的轨迹路线动画 MP4。

默认高德矢量（栅格 style7）；可选 --basemap-style detail 用 style8 详图试不同路名注记。GPX 多为 WGS84，国内底图实为 GCJ-02，已自动对齐，勿与 OSM/Esri
（WGS84）混用时出现二次偏移——若必须用国外底图请 --no-tile-fallback 并用 --assume-gcj02-track
慎用。更清晰可调高 --dpi、--map-zoom（15~17）、高德 detail 时 --gaode-tile-scale 2（512px 瓦片）。注意：**map_zoom 只影响瓦片精细度，不改变画布英寸**；画布大小由
--fig-width/--fig-height/--dpi 决定；--auto-fig-aspect 会按轨迹形状改宽高比，并受 --fig-max-width 上限约束。
静态地图类画面极易压缩，CRF 导出体积小属正常，与「地图是否锐利」基本无关；清晰度优先靠 dpi、fig 尺寸、map-zoom、瓦片 scale，以及 --basemap-interpolation nearest 减轻插值糊字。
固定 16:9 等横屏若左右留白大，可加 --fill-figure-aspect 对称扩大可视经纬范围以铺满画布。
手机全屏：竖屏用 --phone-portrait（9:16），横屏持握用 --phone-landscape（16:9）；二者都会自动 fill-figure-aspect。另可提高 --map-zoom / --dpi；栅格路名有限度，可缩短 --max-route-km 或减小 --margin-deg。
轨迹线：整段淡色底轨用 --route-full-color / --route-full-width / --route-full-alpha；随动画增长的实线用 --route-progress-color / --route-progress-width。
默认已关闭经纬度刻度（干净地图）；要刻度请加 --show-lonlat-axis。

示例：
  .venv/bin/python gpx_map_video.py --gpx route.gpx --out map_route.mp4
  .venv/bin/python gpx_map_video.py --gpx route.gpx --provider esri --basemap-style imagery
  试跑：--test（默认截断前 5 km，且未写 --duration/--fps/--map-zoom 时会自动用短时长、低帧率、zoom=15 加速）
  只出一张静态图（不写 MP4）：--test-image，可选 --test-image-out、--test-image-progress（0=起点 1=终点，默认 0.5）
  只测前若干公里：--test-first-km 5 或仅 --test-first-km（默认 5 km），不必加 --test；与 --max-route-km 同时写时以后者为准
  或手写：--max-route-km 2 --duration 10 --fps 12

完整视频导出后按公里切分：--split-video-by-km，步长 --split-video-km-step（默认 1，可与 --km-interval 一致如 0.5）；
  输出目录默认为主视频同目录下「主文件名_km_segments/」。需系统 PATH 中有 ffmpeg。

里程桩：加 --km-markers，可选 --km-interval、--km-format、颜色与圆角框等（见 --help）。
  半公里桩（如 interval=0.5）请勿用 {km:.0f} 取整，否则 1.5 与 2.0 都会显示「2 km」像重复；改用 {km:.1f} 或 {km:g}。
  某公里单独加字/图、改锚点位置：--km-overrides-json（与 --km-markers 联用），格式见下方。
景点/地标：--poi-json 指向 UTF-8 JSON 文件，格式见下方。
起点/终点：--route-endpoints-json，JSON 对象含 \"start\"、\"end\"（可只写其一）；字段与 POI 相同（text、图、text_offset、样式等），另可选 show_dot、dot_size、dot_color、dot_edgecolor、dot_edgewidth；锚在轨迹首/末点（已与底图坐标一致）。
  示例：{\"start\": {\"text\": \"起点\", \"bg\": \"#1565c0\", \"text_offset\": [0,-22]}, \"end\": {\"text\": \"终点\", \"image\": \"flag.png\", \"image_zoom\": 0.12}}

POI JSON 示例（数组；路径相对 JSON 所在目录）：
  lon/lat 默认按 WGS84；若坐标来自高德/腾讯地图界面，请加 \"coords\": \"gcj02\"，否则会二次偏移。
  [
    {"lon": 120.12, "lat": 36.05, "text": "起点", "bg": "#1565c0"},
    {"lon": 120.20, "lat": 36.08, "text": "高德抄的点", "coords": "gcj02"}
  ]
可写字段（均有默认值）：text, fontsize, color, bg, edge, boxstyle, edge_width, fontweight, ha, va，
text_alpha, bg_alpha；image, image_zoom, image_offset [dx,dy], text_offset [dx,dy]（单位：点）。

里程桩 JSON（--km-overrides-json）：(1) 仅数组；(2) 或对象，可含 overrides、show_km/only_km、hide_km/skip_km、with_interval。
  **白名单（默认）**：show_km / only_km 非空且 **未** 设 with_interval:true 时，**只画**列表中的公里，--km-interval 不参与选桩（overrides 仅作用于已选中的 km）。
  **与整公里并用**：设 **\"with_interval\": true** 时，先按 --km-interval（及 km-include-start）生成桩，再并入 overrides 里的 km，再把 show_km/only_km 中的公里并入（可用来标半公里等）；最后减 hide_km。
  仅要「整公里 + 某几个自定义桩」时，也可不写 show_km，只在 overrides 里写那些 km，会自动并入。
  hide_km / skip_km：从当前集合中去掉这些公里。
  overrides：桩覆盖数组，每条须含 \"km\"。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import gpxpy
import matplotlib

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.offsetbox import AnnotationBbox, OffsetImage


def _china_gcj_range_mask(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """GCJ 偏移在中国大陆范围内粗略成立；框外保持不变。"""
    return (
        (lons >= 72.004)
        & (lons <= 137.8347)
        & (lats >= 0.8293)
        & (lats <= 55.8271)
    )


def wgs84_to_gcj02(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    GPX/WGS84 → 高德/天地图所用 GCJ-02（与国测偏移一致）。
    若轨迹文件已是 GCJ02，请加 --assume-gcj02-track 勿再换算。
    """
    lx = np.asarray(lons, dtype=float).copy()
    ly = np.asarray(lats, dtype=float).copy()
    pi = math.pi
    ee = 0.00669342162296594323
    a = 6378245.0

    def _delta_lat_term(x: float, y: float) -> float:
        """x,y 为 wgLon-105、wgLat-35；与国测脚本 transformLat 一致。"""
        t = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        t += (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
        t += (20.0 * math.sin(y * pi) + 40.0 * math.sin(y / 3.0 * pi)) * 2.0 / 3.0
        t += (160.0 * math.sin(y / 12.0 * pi) + 320 * math.sin(y * pi / 30.0)) * 2.0 / 3.0
        return t

    def _delta_lon_term(x: float, y: float) -> float:
        """与 transformLon 一致。"""
        t = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        t += (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
        t += (20.0 * math.sin(x * pi) + 40.0 * math.sin(x / 3.0 * pi)) * 2.0 / 3.0
        t += (150.0 * math.sin(x / 12.0 * pi) + 300.0 * math.sin(x / 30.0 * pi)) * 2.0 / 3.0
        return t

    mask = _china_gcj_range_mask(lx, ly)
    for i in np.where(mask)[0]:
        wg_lon, wg_lat = float(lx[i]), float(ly[i])
        if abs(wg_lon) < 1e-8 and abs(wg_lat) < 1e-8:
            continue
        x = wg_lon - 105.0
        y = wg_lat - 35.0
        delta_lat_arc = _delta_lat_term(x, y)
        delta_lon_arc = _delta_lon_term(x, y)
        rad_lat = wg_lat / 180.0 * pi
        sin_lat = math.sin(rad_lat)
        magic = 1.0 - ee * sin_lat * sin_lat
        sqrt_magic = math.sqrt(magic)
        d_lat = (delta_lat_arc * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * pi)
        d_lon = (delta_lon_arc * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * pi)
        ly[i] = wg_lat + d_lat
        lx[i] = wg_lon + d_lon
    return lx, ly


def gcj02_to_wgs84(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    GCJ-02 → WGS84（迭代逼近逆变换）。高德/腾讯系界面复制的经纬度多为 GCJ，若在 WGS 轴（OSM 等）上标注需先转换。
    """
    wg_lon = np.asarray(lons, dtype=float).copy()
    wg_lat = np.asarray(lats, dtype=float).copy()
    mask = _china_gcj_range_mask(wg_lon, wg_lat)
    if not np.any(mask):
        return wg_lon, wg_lat
    for _ in range(8):
        mg_lon, mg_lat = wgs84_to_gcj02(wg_lon, wg_lat)
        wg_lon = np.where(mask, 2.0 * wg_lon - mg_lon, wg_lon)
        wg_lat = np.where(mask, 2.0 * wg_lat - mg_lat, wg_lat)
    return wg_lon, wg_lat


def provider_expects_gcj(provider: str) -> bool:
    return provider.lower() in ("gaode", "tianditu")


def to_display_lonlat(
    provider: str, lons: np.ndarray, lats: np.ndarray, assume_gcj02_track: bool
) -> tuple[np.ndarray, np.ndarray]:
    """
    WGS↔火星：国内底图画 GCJ02；国际标准底图画 WGPX。
    assume_gcj02_track=True 时表示 GPX 已是 GCJ02，不再做偏移（仅与高德类底图语义一致）。
    """
    lx = np.asarray(lons, dtype=float)
    ly = np.asarray(lats, dtype=float)
    if assume_gcj02_track:
        return lx.copy(), ly.copy()
    if provider_expects_gcj(provider.lower()):
        return wgs84_to_gcj02(lx, ly)
    return lx.copy(), ly.copy()


def wgs_bbox_to_display_axis_limits(
    provider: str,
    west: float,
    east: float,
    south: float,
    north: float,
    assume_gcj02_track: bool,
) -> tuple[float, float, float, float]:
    """将 WGS84 矩形四角变换到显示坐标后取 min/max，供 set_xlim/set_ylim。"""
    lo = np.asarray([west, east, west, east], dtype=float)
    la = np.asarray([south, south, north, north], dtype=float)
    px, py = to_display_lonlat(provider, lo, la, assume_gcj02_track)
    return float(px.min()), float(px.max()), float(py.min()), float(py.max())


def expand_wgs_viewport_to_figure_aspect(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    margin_deg: float,
    fig_width_in: float,
    fig_height_in: float,
) -> tuple[float, float, float, float]:
    """
    在含 margin 的 WGS 包络上对称扩大经度或纬度范围，使 (经度跨度):(纬度跨度) ≈ 画布宽:高，
    从而在 set_aspect('equal') 下铺满画布、消除左右或上下大块留白（多显示周边地图）。
    """
    west, east = lon_min - margin_deg, lon_max + margin_deg
    south, north = lat_min - margin_deg, lat_max + margin_deg
    sx = east - west
    sy = north - south
    if sx <= 0 or sy <= 0 or fig_height_in <= 0:
        return west, east, south, north
    target = fig_width_in / fig_height_in
    r = sx / sy
    eps = 1e-12
    if r < target - eps:
        new_sx = sy * target
        d = (new_sx - sx) / 2.0
        west -= d
        east += d
    elif r > target + eps:
        new_sy = sx / target
        d = (new_sy - sy) / 2.0
        south -= d
        north += d
    return west, east, south, north


_CONTEXTILY_TILE_PATCH_INSTALLED = False


def _rasterio_resampling(name: str):
    """contextily 瓦片经纬度重投影所用的 rasterio 重采样方式。"""
    from rasterio.enums import Resampling

    key = name.strip().lower()
    table = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "lanczos": Resampling.lanczos,
    }
    if key not in table:
        raise ValueError(f"未知 basemap-warp-resampling: {name!r}，可选 {sorted(table)}")
    return table[key]


def install_contextily_tile_request_patch(
    *, connect_timeout_s: float = 30.0, read_timeout_s: float = 180.0
) -> None:
    """
    contextily 内置 requests.get 无 timeout 时，urllib3 易在约 60s 读超时；
    高德 style=8 或 zoom=14 等单瓦略大/略慢时常误报失败。替换 tile._retryer 延长读超时并遇超时重试。
    """
    global _CONTEXTILY_TILE_PATCH_INSTALLED
    if _CONTEXTILY_TILE_PATCH_INSTALLED:
        return
    import io
    import time

    import requests
    from PIL import Image, UnidentifiedImageError

    import contextily.tile as tmod

    USER_AGENT = tmod.USER_AGENT
    ct = (float(connect_timeout_s), float(read_timeout_s))

    def _retryer(tile_url: str, wait: int, max_retries: int):
        request = None
        try:
            request = requests.get(
                tile_url,
                headers={"user-agent": USER_AGENT},
                timeout=ct,
            )
            request.raise_for_status()
            with io.BytesIO(request.content) as image_stream:
                image = Image.open(image_stream).convert("RGBA")
                array = np.asarray(image)
                image.close()
            return array
        except (requests.Timeout, requests.ConnectionError, TimeoutError, OSError):
            if max_retries > 0:
                time.sleep(wait if wait else 0.5)
                return _retryer(tile_url, wait, max_retries - 1)
            raise
        except (requests.HTTPError, UnidentifiedImageError):
            if request is not None and request.status_code == 404:
                raise requests.HTTPError(
                    "Tile URL resulted in a 404 error. "
                    "Double-check your tile url:\n{}".format(tile_url)
                ) from None
            if max_retries > 0:
                time.sleep(wait)
                return _retryer(tile_url, wait, max_retries - 1)
            if request is not None:
                raise requests.HTTPError(
                    "Connection reset by peer too many times. "
                    f"Last message was: {request.status_code} "
                    f"Error: {request.reason} for url: {request.url}"
                ) from None
            raise

    tmod._retryer = _retryer
    _CONTEXTILY_TILE_PATCH_INSTALLED = True


def add_basemap_to_axis(
    ax,
    prov: str,
    sty: str | None,
    tianditu_key: str | None,
    zoom: int | None,
    *,
    gaode_tile_scale: int = 1,
    basemap_interpolation: str = "bilinear",
    basemap_warp_resampling: str = "bilinear",
) -> None:
    """按当前 axes 的范围添加瓦片；axis 必须为与瓦片匹配的经纬度 CRS。"""
    import contextily as ctx

    crs = "EPSG:4326"
    z = zoom if zoom is not None else "auto"
    rs = _rasterio_resampling(basemap_warp_resampling)

    prov = prov.lower()
    if prov == "tianditu":
        if not tianditu_key:
            raise RuntimeError("需要 --tianditu-key 或环境变量 TIANDITU_KEY")
        add_tianditu_basemap(
            ax,
            sty,
            tianditu_key,
            z,
            interpolation=basemap_interpolation,
            warp_resampling=rs,
        )
        return

    src = resolve_xyz_provider_source(prov, sty, gaode_tile_scale=gaode_tile_scale)
    ctx.add_basemap(
        ax,
        crs=crs,
        source=src,
        zoom=z,
        interpolation=basemap_interpolation,
        resampling=rs,
    )


def figsize_matched_to_lonlat_extent(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    margin_deg: float,
    base_height_in: float,
    min_width_in: float = 4.0,
    max_width_in: float = 32.0,
    max_height_in: float = 22.0,
) -> tuple[float, float]:
    """
    使 fig 宽高比接近「含边距的经纬度包络」纵横比，减轻 set_aspect('equal') 时
    轨迹很扁长导致的大块留白，从而让地图在画面里更大、瓦片注记相对更易读。
    """
    sx = (lon_max - lon_min) + 2.0 * margin_deg
    sy = (lat_max - lat_min) + 2.0 * margin_deg
    if sx <= 0 or sy <= 0:
        return 12.0, base_height_in
    r = sx / sy
    w = base_height_in * r
    w = min(max(w, min_width_in), max_width_in)
    h = base_height_in
    if h > max_height_in:
        scale = max_height_in / h
        h = max_height_in
        w = min(max(w * scale, min_width_in), max_width_in)
    return w, h


def apply_map_frame_cleanup(ax, fig, *, show_axis: bool) -> None:
    """默认模式去掉经纬刻度与轴框，四边贴齐 figure（无白边）。"""
    if show_axis:
        return
    ax.set_axis_off()
    for spine in ax.spines.values():
        spine.set_visible(False)
    if hasattr(fig, "set_layout_engine"):
        fig.set_layout_engine(None)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1, hspace=0, wspace=0)


def ensure_h264_even_pixel_frame(fig) -> None:
    """
    libx264 + yuv420p 要求宽高均为偶数像素；figsize×dpi 舍入后可能出现奇数（如 2631×2200），
    FFmpeg 会报 width not divisible by 2。将画布英寸微调 1 个像素以内以对齐。
    """
    dpi = float(fig.dpi)
    wi, hi = fig.get_size_inches()
    wpx = max(2, int(round(wi * dpi)))
    hpx = max(2, int(round(hi * dpi)))
    wpx += wpx % 2
    hpx += hpx % 2
    fig.set_size_inches(wpx / dpi, hpx / dpi, forward=True)


def make_animation_save_progress(total_frames: int):
    """
    供 matplotlib.animation.Animation.save(progress_callback=…) 使用；
    在终端同一行刷新进度（约 40 次更新 + 首尾帧，避免刷屏或长期无输出）。
    """
    n = int(total_frames)

    def progress_callback(current: int, total: int | None) -> None:
        tot = int(total) if total is not None else n
        if tot <= 0:
            return
        done = min(current + 1, tot)
        step = max(1, tot // 40)
        if done not in (1, tot) and done % step != 0:
            return
        pct = (done * 100) // tot
        bar_len = 28
        filled = min(bar_len, int(round(bar_len * done / tot)))
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r编码中 [{bar}] {done}/{tot}  {pct}%", end="", flush=True)

    return progress_callback


def iter_route_km_segments(total_km: float, step_km: float) -> list[tuple[float, float]]:
    """将 [0, total_km] 按步长切为半开区间 [lo, hi) 的列表（最后一段 hi==total）。"""
    if total_km <= 0 or step_km <= 0:
        return []
    out: list[tuple[float, float]] = []
    lo = 0.0
    while lo < total_km - 1e-12:
        hi = min(float(total_km), lo + float(step_km))
        out.append((lo, hi))
        lo = hi
    return out


def km_segment_to_frame_span_excl(
    km_lo: float, km_hi: float, total_km: float, total_frames: int
) -> tuple[int, int]:
    """
    与 interpolate_lonlat 一致：prog_km 为 linspace(0, total_km, total_frames)。
    返回半开帧区间 [i0, i1)，供截取 i0..i1-1 共 i1-i0 帧（含首次到达 km_hi 的那一帧）。
    """
    n = int(total_frames)
    if n <= 0:
        return 0, 0
    if total_km <= 1e-15:
        return 0, n
    prog = np.linspace(0.0, float(total_km), n, dtype=float)
    if km_lo <= 0.0:
        i0 = 0
    else:
        i0 = int(np.searchsorted(prog, float(km_lo), side="left"))
    i0 = max(0, min(n - 1, i0))
    if km_hi >= float(total_km) - 1e-12:
        i1 = n
    else:
        j = int(np.searchsorted(prog, float(km_hi), side="left"))
        i1 = min(n, j + 1)
    if i1 <= i0:
        i1 = min(n, i0 + 1)
    return i0, i1


def split_mp4_by_route_km(
    src_mp4: str,
    *,
    total_km: float,
    total_frames: int,
    fps: int,
    step_km: float,
    out_dir: str,
    name_prefix: str,
    video_crf: int | None,
    video_bitrate_kbps: int | None,
    video_preset: str,
) -> list[str]:
    """
    用 ffmpeg 按累计公里切段（先完整渲染再切）。返回生成的文件路径列表。
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("未找到 ffmpeg，无法按公里切分视频（请安装并加入 PATH）")
    if not os.path.isfile(src_mp4):
        raise FileNotFoundError(f"待切分视频不存在: {src_mp4}")
    segs = iter_route_km_segments(total_km, step_km)
    if not segs:
        print("按公里切分: 路线长为 0 或步长无效，跳过")
        return []
    os.makedirs(out_dir, exist_ok=True)
    safe_pre = re.sub(r'[\\/:*?"<>|]+', "_", name_prefix).strip("._") or "segments"
    outs: list[str] = []
    fpsi = max(1, int(fps))
    for idx, (lo, hi) in enumerate(segs, start=1):
        i0, i1 = km_segment_to_frame_span_excl(lo, hi, total_km, total_frames)
        nfr = i1 - i0
        if nfr <= 0:
            continue
        t0 = i0 / float(fpsi)
        dur = nfr / float(fpsi)
        dst = os.path.join(out_dir, f"{safe_pre}_第{idx:02d}段_{lo:.2f}-{hi:.2f}km.mp4")
        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            os.path.abspath(src_mp4),
            "-ss",
            f"{t0:.6f}",
            "-t",
            f"{dur:.6f}",
            "-an",
        ]
        if video_bitrate_kbps is not None:
            cmd += [
                "-c:v",
                "libx264",
                "-b:v",
                f"{int(video_bitrate_kbps)}k",
                "-maxrate",
                f"{int(video_bitrate_kbps)}k",
                "-bufsize",
                f"{int(video_bitrate_kbps) * 2}k",
            ]
        else:
            crf = 18 if video_crf is None else int(video_crf)
            cmd += ["-c:v", "libx264", "-crf", str(crf)]
        cmd += [
            "-preset",
            str(video_preset),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            dst,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(f"ffmpeg 切分失败（{lo:g}-{hi:g} km）: {err or r.returncode}")
        outs.append(dst)
    print(f"按公里切分完成: {len(outs)} 个文件 → {out_dir}")
    return outs


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def load_gpx_points(path: str) -> tuple[np.ndarray, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    lats: list[float] = []
    lons: list[float] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                if pt.latitude is None or pt.longitude is None:
                    continue
                lats.append(pt.latitude)
                lons.append(pt.longitude)
    if len(lats) < 2:
        raise ValueError("GPX 中至少需要 2 个有效轨迹点")
    return np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)


def filter_by_min_spacing(
    lons: np.ndarray, lats: np.ndarray, min_distance_m: float
) -> tuple[np.ndarray, np.ndarray]:
    if min_distance_m <= 0 or len(lons) <= 1:
        return lons, lats
    out_lon = [float(lons[0])]
    out_lat = [float(lats[0])]
    for i in range(1, len(lons)):
        d_m = haversine_km(out_lat[-1], out_lon[-1], float(lats[i]), float(lons[i])) * 1000
        if d_m >= min_distance_m:
            out_lon.append(float(lons[i]))
            out_lat.append(float(lats[i]))
    return np.asarray(out_lon), np.asarray(out_lat)


def cumulative_km(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    d = np.zeros(len(lons), dtype=float)
    for i in range(1, len(lons)):
        d[i] = d[i - 1] + haversine_km(float(lats[i - 1]), float(lons[i - 1]), float(lats[i]), float(lons[i]))
    return d


def truncate_route_by_max_km(
    lons: np.ndarray, lats: np.ndarray, max_km: float | None
) -> tuple[np.ndarray, np.ndarray]:
    """保留从起点沿轨迹累计距离不超过 max_km 的部分；在切段处沿末段线性插值一个终点。"""
    if max_km is None or max_km <= 0:
        return lons, lats
    if len(lons) < 2:
        return lons, lats
    d = cumulative_km(lons, lats)
    total = float(d[-1])
    if max_km >= total - 1e-9:
        return lons, lats
    k = int(np.searchsorted(d, max_km, side="left"))
    if k <= 0:
        return lons[:1].copy(), lats[:1].copy()
    if abs(float(d[k]) - max_km) < 1e-9:
        return lons[: k + 1].copy(), lats[: k + 1].copy()
    i0, i1 = k - 1, k
    seg = float(d[i1] - d[i0])
    if seg <= 1e-15:
        return lons[: k + 1].copy(), lats[: k + 1].copy()
    t = (max_km - float(d[i0])) / seg
    t = float(np.clip(t, 0.0, 1.0))
    lo = float(lons[i0]) + t * (float(lons[i1]) - float(lons[i0]))
    la = float(lats[i0]) + t * (float(lats[i1]) - float(lats[i0]))
    new_lons = np.append(np.asarray(lons[:k], dtype=float), lo)
    new_lats = np.append(np.asarray(lats[:k], dtype=float), la)
    return new_lons, new_lats


def interpolate_lonlat(
    lons: np.ndarray, lats: np.ndarray, dist_km: np.ndarray, total_frames: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    total = float(dist_km[-1])
    if total <= 0:
        return (
            np.full(total_frames, lons[0]),
            np.full(total_frames, lats[0]),
            np.linspace(0, 0, total_frames),
        )
    tgt = np.linspace(0.0, total, total_frames, dtype=float)
    lon_i = np.interp(tgt, dist_km, lons)
    lat_i = np.interp(tgt, dist_km, lats)
    return lon_i, lat_i, tgt


def interpolate_xy_at_route_km(
    plot_lon: np.ndarray, plot_lat: np.ndarray, dist_km: np.ndarray, target_km: float
) -> tuple[float, float] | None:
    """在轨迹累计距离 target_km 处插值显示坐标。"""
    if len(plot_lon) < 2:
        return None
    tot = float(dist_km[-1])
    if target_km < -1e-9 or target_km > tot + 1e-6:
        return None
    x = float(np.interp(target_km, dist_km, plot_lon))
    y = float(np.interp(target_km, dist_km, plot_lat))
    return x, y


def _normalize_route_km_key(k: float) -> float:
    return round(float(k), 6)


def load_km_markers_file(
    path: str,
) -> tuple[dict[float, dict], list[float] | None, list[float], bool]:
    """
    解析里程桩 JSON。
    返回 (overrides, show_km 列表或 None, hide_km, merge_interval)。
    merge_interval 为 True 时与 --km-interval 合并，而非白名单替换。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    show_list: list[float] | None = None
    hide_list: list[float] = []
    raw_overrides: list = []
    merge_interval = False

    if isinstance(data, list):
        raw_overrides = data
    elif isinstance(data, dict):
        merge_interval = bool(data.get("with_interval", data.get("merge_interval", False)))
        sk = data.get("show_km", data.get("only_km"))
        if isinstance(sk, list) and len(sk) > 0:
            show_list = [float(x) for x in sk]
        hk = data.get("hide_km", data.get("skip_km"))
        if isinstance(hk, list):
            hide_list = [float(x) for x in hk]
        ro = data.get("overrides")
        if isinstance(ro, list):
            raw_overrides = ro
    else:
        raise ValueError(
            "km-overrides 须为 JSON 数组，或对象 {\"overrides\": [...], \"show_km\": [...], \"hide_km\": [...] }"
        )

    out: dict[float, dict] = {}
    for raw in raw_overrides:
        if not isinstance(raw, dict):
            print(f"跳过非对象 km-overrides 项: {raw!r}")
            continue
        if "km" not in raw:
            print(f"跳过缺 km 的 km-overrides 项: {raw!r}")
            continue
        km_key = _normalize_route_km_key(float(raw["km"]))
        merged = _merge_km_override_entry(raw, base)
        out[km_key] = merged
    return out, show_list, hide_list, merge_interval


def _merge_km_override_entry(raw: dict, json_dir: str) -> dict:
    """合并 JSON 条目：解析图片路径、offset 列表等。"""
    out = dict(raw)
    img = out.get("image")
    if isinstance(img, str) and img.strip():
        ip = img.strip()
        out["image"] = ip if os.path.isabs(ip) else os.path.normpath(os.path.join(json_dir, ip))
    else:
        out.pop("image", None)
    io = raw.get("image_offset")
    if isinstance(io, (list, tuple)) and len(io) >= 2:
        out["image_dx"], out["image_dy"] = float(io[0]), float(io[1])
    else:
        out.setdefault("image_dx", 0.0)
        out.setdefault("image_dy", 28.0)
    to = raw.get("text_offset")
    if isinstance(to, (list, tuple)) and len(to) >= 2:
        out["text_dx"], out["text_dy"] = float(to[0]), float(to[1])
    else:
        out.pop("text_dx", None)
        out.pop("text_dy", None)
    ak = raw.get("anchor_km")
    if ak is not None:
        out["anchor_km"] = float(ak)
    return out


def warn_km_marker_label_collisions(
    targets: list[float], total_km: float, fmt: str
) -> None:
    """若多桩格式化后文字相同（常见于 interval<1 仍用 :.0f），打印提示。"""
    labels: dict[str, list[float]] = {}
    for kmv in targets:
        if kmv > total_km + 1e-6:
            continue
        try:
            lab = fmt.format(km=kmv)
        except Exception:
            continue
        labels.setdefault(lab, []).append(float(kmv))
    dups = {lab: kms for lab, kms in labels.items() if len(kms) > 1}
    if not dups:
        return
    parts: list[str] = []
    for lab, kms in sorted(dups.items(), key=lambda x: min(x[1])):
        ks = ", ".join(f"{k:g}" for k in sorted(set(kms)))
        parts.append(f"「{lab}」← {ks} km")
    print(
        "提示: 多个里程桩的标签文字相同，易被看成「重复」。"
        "若 --km-interval 小于 1，请不要用 {km:.0f} 等取整格式，可改为 {km:.1f} 或 {km:g}。"
        f" 当前冲突: {'; '.join(parts)}"
    )


def add_route_km_markers(
    ax,
    plot_lon: np.ndarray,
    plot_lat: np.ndarray,
    dist_km: np.ndarray,
    total_km: float,
    args: argparse.Namespace,
    km_overrides: dict[float, dict] | None = None,
    *,
    show_km: list[float] | None = None,
    hide_km: list[float] | None = None,
    merge_interval: bool = False,
) -> None:
    """沿路线绘制里程标签。show_km 非空且 merge_interval=False 时为白名单；merge_interval=True 时与 interval 并集。"""
    interval = float(args.km_interval)
    has_extra_list = show_km is not None and len(show_km) > 0
    whitelist = has_extra_list and not merge_interval
    if interval <= 0 and not whitelist and not merge_interval:
        return
    if merge_interval:
        tset = set()
        if interval > 0:
            targets_m: list[float] = []
            if args.km_include_start:
                targets_m.append(0.0)
            k = interval
            while k <= total_km + 1e-9:
                targets_m.append(float(k))
                k += interval
            tset = {round(t, 8) for t in targets_m}
        if km_overrides:
            for kk in km_overrides.keys():
                fk = float(kk)
                if -1e-9 <= fk <= total_km + 1e-6:
                    tset.add(round(fk, 8))
        if has_extra_list:
            for x in show_km or []:
                fk = float(x)
                if -1e-9 <= fk <= total_km + 1e-6:
                    tset.add(round(fk, 8))
    elif whitelist:
        tset = set()
        for x in show_km or []:
            fk = float(x)
            if -1e-9 <= fk <= total_km + 1e-6:
                tset.add(round(fk, 8))
    else:
        targets: list[float] = []
        if args.km_include_start:
            targets.append(0.0)
        k = interval
        while k <= total_km + 1e-9:
            targets.append(float(k))
            k += interval
        tset = {round(t, 8) for t in targets}
        if km_overrides:
            for kk in km_overrides.keys():
                fk = float(kk)
                if -1e-9 <= fk <= total_km + 1e-6:
                    tset.add(round(fk, 8))
    if hide_km:
        hk = {round(float(h), 8) for h in hide_km}
        tset -= hk
    targets = sorted(tset)
    fmt = str(args.km_format)
    warn_km_marker_label_collisions(targets, total_km, fmt)
    fs = float(args.km_fontsize)
    ovr_map = km_overrides or {}
    for kmv in targets:
        if kmv > total_km + 1e-6:
            continue
        ovr = ovr_map.get(_normalize_route_km_key(kmv))
        anchor_km = float(ovr["anchor_km"]) if ovr and ovr.get("anchor_km") is not None else float(kmv)
        xy = interpolate_xy_at_route_km(plot_lon, plot_lat, dist_km, anchor_km)
        if xy is None:
            continue
        x, y = xy
        hide_dot = bool(ovr.get("hide_dot")) if ovr else False
        if not hide_dot:
            ax.scatter(
                [x],
                [y],
                s=float(args.km_dot_size),
                c=str(args.km_dot_color),
                edgecolors=str(args.km_dot_edgecolor),
                linewidths=float(args.km_dot_edgewidth),
                zorder=5,
            )
        tdx = float(ovr["text_dx"]) if ovr and ovr.get("text_dx") is not None else float(args.km_text_offset_x)
        tdy = float(ovr["text_dy"]) if ovr and ovr.get("text_dy") is not None else float(args.km_text_offset_y)
        fs_use = float(ovr["fontsize"]) if ovr and ovr.get("fontsize") is not None else fs
        col = str(ovr["color"]) if ovr and ovr.get("color") is not None else str(args.km_text_color)
        fw = str(ovr["fontweight"]) if ovr and ovr.get("fontweight") is not None else str(args.km_fontweight)
        bg = str(ovr["bg"]) if ovr and ovr.get("bg") is not None else str(args.km_bg_color)
        edge = str(ovr["edge"]) if ovr and ovr.get("edge") is not None else str(args.km_edge_color)
        ew = float(ovr["edge_width"]) if ovr and ovr.get("edge_width") is not None else float(args.km_edge_width)
        bx = str(ovr["boxstyle"]) if ovr and ovr.get("boxstyle") is not None else str(args.km_boxstyle)
        bga = float(ovr["bg_alpha"]) if ovr and ovr.get("bg_alpha") is not None else float(args.km_bg_alpha)
        img_path = ovr.get("image") if ovr else None
        has_km_image = isinstance(img_path, str) and bool(img_path) and os.path.isfile(img_path)
        if not ovr:
            text_empty = False
        elif "text" not in ovr:
            text_empty = True
        else:
            tv = ovr.get("text")
            text_empty = tv is None or str(tv).strip() == ""
        # 无字（未写 text 或 text 为空）且配图有效：图片代替标签，偏移用 text_offset；非空 text 时字用 text_offset、图用 image_offset
        if ovr and text_empty and has_km_image:
            label: str | None = None
            image_xy_pts = (tdx, tdy)
        elif ovr and not text_empty:
            label = str(ovr["text"])
            image_xy_pts = (
                float(ovr.get("image_dx", 0.0)),
                float(ovr.get("image_dy", 28.0)),
            )
        else:
            label = fmt.format(km=kmv)
            image_xy_pts = (
                float(ovr.get("image_dx", 0.0)) if ovr else 0.0,
                float(ovr.get("image_dy", 28.0)) if ovr else 28.0,
            )
        if has_km_image:
            try:
                im = plt.imread(str(img_path))
                iz = float(ovr.get("image_zoom", 0.14)) if ovr else 0.14
                imagebox = OffsetImage(im, zoom=iz)
                ab = AnnotationBbox(
                    imagebox,
                    (x, y),
                    xybox=image_xy_pts,
                    boxcoords="offset points",
                    frameon=False,
                    pad=0,
                    zorder=6,
                )
                ax.add_artist(ab)
            except Exception as e:
                print(f"里程桩图片跳过 {img_path}: {e}")
                has_km_image = False
                if ovr and text_empty:
                    label = fmt.format(km=kmv)
        if label is not None:
            ax.annotate(
                label,
                xy=(x, y),
                xytext=(tdx, tdy),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=fs_use,
                color=col,
                fontweight=fw,
                bbox=dict(
                    boxstyle=bx,
                    facecolor=bg,
                    edgecolor=edge,
                    linewidth=ew,
                    alpha=bga,
                ),
                zorder=7 if has_km_image else 6,
            )


_POI_STYLE_DEFAULTS: dict[str, object] = {
    "text": "",
    "fontsize": 12.0,
    "color": "#ffffff",
    "bg": "#37474f",
    "edge": "#ffffff",
    "boxstyle": "round,pad=0.36",
    "edge_width": 1.2,
    "fontweight": "bold",
    "ha": "center",
    "va": "center",
    "image_zoom": 0.14,
    "image_dx": 0.0,
    "image_dy": 26.0,
    "text_dx": 0.0,
    "text_dy": -20.0,
    "text_alpha": 1.0,
    "bg_alpha": 0.92,
}


def load_pois_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "pois" in data:
        data = data["pois"]
    if not isinstance(data, list):
        raise ValueError("POI 文件须为 JSON 数组，或 {\"pois\": [ ... ] }")
    return data


def _merge_poi_entry(raw: dict, json_dir: str) -> dict:
    out: dict[str, object] = dict(_POI_STYLE_DEFAULTS)
    for k, v in raw.items():
        if v is None:
            continue
        out[k] = v
    img = out.get("image")
    if isinstance(img, str) and img.strip():
        ip = img.strip()
        out["image"] = ip if os.path.isabs(ip) else os.path.normpath(os.path.join(json_dir, ip))
    else:
        out.pop("image", None)
    io = raw.get("image_offset")
    if isinstance(io, (list, tuple)) and len(io) >= 2:
        out["image_dx"], out["image_dy"] = float(io[0]), float(io[1])
    to = raw.get("text_offset")
    if isinstance(to, (list, tuple)) and len(to) >= 2:
        out["text_dx"], out["text_dy"] = float(to[0]), float(to[1])
    return out


def draw_poi_style_label(
    ax,
    x: float,
    y: float,
    p: dict,
    *,
    log_prefix: str = "标注",
    zorder_img: int = 6,
    zorder_txt: int = 7,
) -> None:
    """在轴坐标 (x,y) 绘制与 POI 一致的文字框与可选配图（合并后的 p）。"""
    img_path = p.get("image")
    has_img = isinstance(img_path, str) and os.path.isfile(img_path)
    if has_img:
        try:
            im = plt.imread(img_path)
            imagebox = OffsetImage(im, zoom=float(p["image_zoom"]))
            ab = AnnotationBbox(
                imagebox,
                (x, y),
                xybox=(float(p["image_dx"]), float(p["image_dy"])),
                boxcoords="offset points",
                frameon=False,
                pad=0,
                zorder=zorder_img,
            )
            ax.add_artist(ab)
        except Exception as e:
            print(f"{log_prefix} 图片跳过 {img_path}: {e}")
            has_img = False
    txt = str(p.get("text") or "")
    if txt:
        ax.annotate(
            txt,
            xy=(x, y),
            xytext=(float(p["text_dx"]), float(p["text_dy"])),
            textcoords="offset points",
            ha=str(p["ha"]),
            va=str(p["va"]),
            fontsize=float(p["fontsize"]),
            color=str(p["color"]),
            fontweight=str(p["fontweight"]),
            alpha=float(p["text_alpha"]),
            bbox=dict(
                boxstyle=str(p["boxstyle"]),
                facecolor=str(p["bg"]),
                edgecolor=str(p["edge"]),
                linewidth=float(p["edge_width"]),
                alpha=float(p["bg_alpha"]),
            ),
            zorder=zorder_txt,
        )


def load_route_endpoints_json(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("route-endpoints 须为 JSON 对象，含 start / end 等键")
    out: dict[str, dict] = {}
    for key in ("start", "end"):
        v = data.get(key)
        if isinstance(v, dict):
            out[key] = v
    return out


def add_route_endpoint_annotations(
    ax,
    endpoints_json_path: str,
    plot_lon: np.ndarray,
    plot_lat: np.ndarray,
) -> None:
    """在轨迹首末点绘制起点/终点（样式同 POI）；坐标已为显示用 lon/lat。"""
    if len(plot_lon) < 1:
        return
    items = load_route_endpoints_json(endpoints_json_path)
    if not items:
        return
    base = os.path.dirname(os.path.abspath(endpoints_json_path))
    zi, zt = 10, 11

    def one(role: str, ix: int) -> None:
        raw = items.get(role)
        if not raw:
            return
        x, y = float(plot_lon[ix]), float(plot_lat[ix])
        p = _merge_poi_entry(raw, base)
        if raw.get("show_dot", True):
            ax.scatter(
                [x],
                [y],
                s=float(raw.get("dot_size", 72.0)),
                c=str(raw.get("dot_color", "#2e7d32")),
                edgecolors=str(raw.get("dot_edgecolor", "#ffffff")),
                linewidths=float(raw.get("dot_edgewidth", 1.15)),
                zorder=zi - 1,
            )
        draw_poi_style_label(
            ax,
            x,
            y,
            p,
            log_prefix=f"起点终点({role})",
            zorder_img=zi,
            zorder_txt=zt,
        )

    one("start", 0)
    if len(plot_lon) >= 2:
        one("end", -1)


def _poi_input_is_gcj(raw: dict, default_mode: str) -> bool:
    mode = raw.get("coords") or raw.get("coord_system") or default_mode
    return str(mode).lower().strip() in ("gcj02", "gcj", "mars", "amap", "gaode")


def poi_lonlat_to_ax_xy(
    lon: float,
    lat: float,
    *,
    provider: str,
    input_is_gcj: bool,
) -> tuple[float, float]:
    """将 POI 的 lon/lat 转为与当前底图一致的轴坐标。"""
    prov = provider.lower()
    if provider_expects_gcj(prov):
        if input_is_gcj:
            return lon, lat
        px, py = to_display_lonlat(prov, np.asarray([lon]), np.asarray([lat]), assume_gcj02_track=False)
        return float(px[0]), float(py[0])
    if input_is_gcj:
        px, py = gcj02_to_wgs84(np.asarray([lon]), np.asarray([lat]))
        return float(px[0]), float(py[0])
    return lon, lat


def add_poi_annotations(
    ax,
    poi_json_path: str,
    provider: str,
    assume_gcj02_track: bool,
    poi_coords_default: str = "wgs84",
) -> None:
    """绘制 POI；coords 默认 wgs84，高德抄点请用 gcj02（见文件头）。GPX 的 assume_gcj02_track 不参与 POI。"""
    _ = assume_gcj02_track
    items = load_pois_json(poi_json_path)
    base = os.path.dirname(os.path.abspath(poi_json_path))
    for raw in items:
        if not isinstance(raw, dict):
            print(f"跳过非对象 POI: {raw!r}")
            continue
        if "lon" not in raw or "lat" not in raw:
            print(f"跳过缺 lon/lat 的 POI: {raw!r}")
            continue
        p = _merge_poi_entry(raw, base)
        lon = float(raw["lon"])
        lat = float(raw["lat"])
        igcj = _poi_input_is_gcj(raw, poi_coords_default)
        x, y = poi_lonlat_to_ax_xy(lon, lat, provider=provider, input_is_gcj=igcj)
        draw_poi_style_label(ax, x, y, p, log_prefix="POI")


def default_output_path(gpx_path: str, duration_s: float) -> str:
    stem = os.path.splitext(os.path.basename(gpx_path))[0]
    stem = re.sub(r"[^\w\u4e00-\u9fff]+", "_", stem).strip("_") or "route"
    ds = datetime.now().strftime("%Y-%m-%d")
    base = os.path.dirname(os.path.abspath(gpx_path))
    out_dir = os.path.join(base, "..", "map_videos") if base else "map_videos"
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    dur_tag = str(int(duration_s)) if float(duration_s).is_integer() else f"{duration_s:.1f}".rstrip("0").rstrip(".")
    return os.path.join(out_dir, f"{stem}_{dur_tag}s_地图轨迹.mp4")


def tianditu_tile_url(layer: str, key: str) -> str:
    return (
        f"http://t0.tianditu.gov.cn/{layer}_w/wmts?"
        "SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        f"&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
        "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
        f"&tk={key}"
    )


# 首选失败后依次尝试（不含天地图）；国内路线优先高德，备选 Esri/OSM 等
_FALLBACK_TILE_PROVIDERS: list[tuple[str, str | None]] = [
    ("gaode", "normal"),
    ("esri", "topo"),
    ("opentopo", None),
    ("osm", None),
    ("cyclosm", None),
    ("carto", "positron"),
]


def resolve_xyz_provider_source(
    provider: str, basemap_style: str | None, *, gaode_tile_scale: int = 1
):
    """返回 contextily XYZ 源对象（非 tianditu）。gaode_tile_scale 仅作用于高德 detail(style8) 自定义 URL（1→256px，2→512px）。"""
    import contextily as ctx

    p = provider.lower()
    s = (basemap_style or "").lower() if basemap_style else ""
    gscale = 2 if int(gaode_tile_scale) == 2 else 1

    if p == "gaode":
        if s in ("sat", "satellite", "img"):
            return ctx.providers.Gaode.Satellite
        # style=7 为 xyzservices 默认简图；style=8 为道路详图栅格，路名注记可能与简图/App 不同，可对照试
        if s in ("detail", "detailed", "style8", "8"):
            return (
                "https://webrd01.is.autonavi.com/appmaptile?"
                f"lang=zh_cn&size=1&scale={gscale}&style=8&x={{x}}&y={{y}}&z={{z}}"
            )
        return ctx.providers.Gaode.Normal
    if p == "osm":
        return ctx.providers.OpenStreetMap.Mapnik
    if p == "opentopo":
        return ctx.providers.OpenTopoMap
    if p == "cyclosm":
        return ctx.providers.CyclOSM
    if p == "esri":
        if s in ("img", "imagery", "sat", "satellite"):
            return ctx.providers.Esri.WorldImagery
        if s in ("street", "streets"):
            return ctx.providers.Esri.WorldStreetMap
        return ctx.providers.Esri.WorldTopoMap
    if p == "carto":
        m = {
            "light": ctx.providers.CartoDB.Positron,
            "positron": ctx.providers.CartoDB.Positron,
            "dark": ctx.providers.CartoDB.DarkMatter,
            "voyager": ctx.providers.CartoDB.Voyager,
        }
        return m.get(s, ctx.providers.CartoDB.Positron)
    raise ValueError(f"未知瓦片提供者: {provider}")


def add_tianditu_basemap(
    ax,
    basemap_style: str | None,
    tianditu_key: str,
    zoom: int | str | None = "auto",
    *,
    interpolation: str = "bilinear",
    warp_resampling=None,
) -> None:
    import contextily as ctx
    from rasterio.enums import Resampling

    crs = "EPSG:4326"
    z = zoom if zoom is not None else "auto"
    rs = warp_resampling if warp_resampling is not None else Resampling.bilinear
    style = (basemap_style or "vec").lower().replace("+", "_")
    kw = {"interpolation": interpolation, "resampling": rs}
    if style in ("img_cia", "imgcia"):
        ctx.add_basemap(ax, crs=crs, url=tianditu_tile_url("img", tianditu_key), zoom=z, **kw)
        ctx.add_basemap(
            ax, crs=crs, url=tianditu_tile_url("cia", tianditu_key), zoom=z, alpha=0.92, **kw
        )
        return
    layer = {"vec": "vec", "img": "img", "ter": "ter", "cia": "cia"}.get(style, "vec")
    ctx.add_basemap(ax, crs=crs, url=tianditu_tile_url(layer, tianditu_key), zoom=z, **kw)


def user_basemap_style_for(args: argparse.Namespace, provider: str) -> str | None:
    """按当前 provider 解释 --basemap-style / --carto-style。"""
    p = provider.lower()
    if p == "tianditu":
        return args.basemap_style or "vec"
    if p == "carto":
        return args.basemap_style or args.carto_style or "positron"
    if p == "gaode":
        return args.basemap_style or "normal"
    if p == "esri":
        return args.basemap_style or "topo"
    return args.basemap_style


def build_tile_attempts(args: argparse.Namespace) -> list[tuple[str, str | None]]:
    """生成 (provider, style) 尝试顺序；首开用户选择，其后为回退列表（去重）。"""
    if args.no_tile_fallback:
        return [(args.provider.lower(), user_basemap_style_for(args, args.provider))]

    seen: set[str] = set()
    out: list[tuple[str, str | None]] = []

    def add(p: str, st: str | None) -> None:
        q = p.lower()
        if q in seen:
            return
        seen.add(q)
        out.append((q, st))

    add(args.provider, user_basemap_style_for(args, args.provider))
    for fp, fst in _FALLBACK_TILE_PROVIDERS:
        add(fp, fst)
    return out


def try_load_basemap(
    ax,
    args: argparse.Namespace,
    tianditu_key: str | None,
    lons_wgs: np.ndarray,
    lats_wgs: np.ndarray,
    margin_deg: float,
    wgs_viewport: tuple[float, float, float, float] | None = None,
) -> tuple[bool, str | None, str | None]:
    """按候选图源设置轴范围（WGS/GCJ 对齐）并叠瓦片。返回是否成功。"""
    attempts = build_tile_attempts(args)
    zm = args.map_zoom
    for prov, sty in attempts:
        try:
            plons, plats = to_display_lonlat(prov, lons_wgs, lats_wgs, args.assume_gcj02_track)
            ax.clear()
            if wgs_viewport is not None:
                w, e, s, n = wgs_viewport
                x0, x1, y0, y1 = wgs_bbox_to_display_axis_limits(
                    prov, w, e, s, n, args.assume_gcj02_track
                )
                ax.set_xlim(x0, x1)
                ax.set_ylim(y0, y1)
            else:
                ax.set_xlim(float(plons.min()) - margin_deg, float(plons.max()) + margin_deg)
                ax.set_ylim(float(plats.min()) - margin_deg, float(plats.max()) + margin_deg)
            ax.set_aspect("equal", adjustable="box")
            tk = tianditu_key if prov == "tianditu" else None
            add_basemap_to_axis(
                ax,
                prov,
                sty,
                tk,
                zm,
                gaode_tile_scale=args.gaode_tile_scale,
                basemap_interpolation=args.basemap_interpolation,
                basemap_warp_resampling=args.basemap_warp_resampling,
            )
            hint = (
                "tianditu ({})".format(sty)
                if prov == "tianditu"
                else "{}{}".format(prov, f" ({sty})" if sty else "")
            )
            print(f"底图已加载: {hint}")
            return True, prov, sty
        except Exception as e:
            print(f"底图源 {prov} 不可用: {e}")
    print("所有底图源均不可用，使用灰色背景。")
    return False, None, None


def _argv_has_long_option(argv: list[str], flag: str) -> bool:
    """用户是否在命令行中显式写了该长选项（含 --opt=val）。"""
    eq = f"{flag}="
    for a in argv:
        if a == flag or a.startswith(eq):
            return True
    return False


def resolve_route_truncation_km(args: argparse.Namespace, argv: list[str] | None = None) -> None:
    """
    --test-first-km：只生成从起点起前 KM 公里。
    若命令行里已写 --max-route-km，则不覆盖（以 --max-route-km 为准）。
    """
    if argv is None:
        argv = sys.argv
    if _argv_has_long_option(argv, "--max-route-km"):
        return
    if not _argv_has_long_option(argv, "--test-first-km"):
        return
    if args.test_first_km is not None:
        args.max_route_km = float(args.test_first_km)


def apply_phone_video_layout(args: argparse.Namespace) -> None:
    """
    手机全屏画布：竖屏 9:16 或横屏 16:9；窄边像素 = phone_short_edge_px。
    与 --auto-fig-aspect 互斥；自动打开 fill-figure-aspect 减轻 equal 留白。
    """
    if not args.phone_portrait and not args.phone_landscape:
        return
    tag = "竖屏 9:16" if args.phone_portrait else "横屏 16:9"
    if args.auto_fig_aspect:
        print(f"提示: 已启用手机全屏模式（{tag}），忽略 --auto-fig-aspect")
    args.auto_fig_aspect = False
    dpi = float(args.dpi)
    se = max(320, int(args.phone_short_edge_px))
    se += se % 2
    if args.phone_portrait:
        sw = se
        sh = int(round(sw * 16.0 / 9.0))
        sh += sh % 2
    else:
        sh = se
        sw = int(round(sh * 16.0 / 9.0))
        sw += sw % 2
    args.fig_width = sw / dpi
    args.fig_height = sh / dpi
    print(f"{tag} 画布: {sw}×{sh} px（{args.fig_width:.2f}×{args.fig_height:.2f} 英寸 @ dpi={args.dpi}）")
    if not args.fill_figure_aspect:
        args.fill_figure_aspect = True
        print("提示: 已自动启用 --fill-figure-aspect（减轻 equal 留白）")


def apply_test_mode_defaults(args: argparse.Namespace) -> None:
    """
    --test：保证截断试跑路线；若未在命令行里单独指定 duration/fps/map-zoom，
    则压低默认值，避免仍渲染 60s×30fps 导致「试了跟没试一样慢」。
    """
    if not args.test:
        return
    argv = sys.argv
    if args.max_route_km is None:
        args.max_route_km = 5.0
    touched: list[str] = []
    if not _argv_has_long_option(argv, "--duration"):
        args.duration = 12.0
        touched.append("duration→12s")
    if not _argv_has_long_option(argv, "--fps"):
        args.fps = 12
        touched.append("fps→12")
    if not _argv_has_long_option(argv, "--map-zoom"):
        args.map_zoom = 15
        touched.append("map-zoom→15")
    msg = f"试跑: 路线上限 {args.max_route_km:g} km"
    if touched:
        msg += " | 未指定的项已压低: " + "，".join(touched)
    print(msg)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GPX → 地图轨迹动画 MP4")
    p.add_argument("--gpx", required=True, help="输入 GPX 文件路径")
    p.add_argument("--out", default=None, help="输出 MP4 路径（默认在 map_videos/ 下自动生成）")
    p.add_argument("--duration", type=float, default=60.0, help="视频时长（秒），默认 60")
    p.add_argument("--fps", type=int, default=30, help="帧率，默认 30")
    p.add_argument(
        "--dpi",
        type=int,
        default=180,
        help="渲染 DPI（越大单帧像素越多）；过大时手机/小窗播放整段被缩小，瓦片路名会难辨认，可配合较低 dpi 或 fig_width×dpi≈1920~2560",
    )
    p.add_argument("--fig-width", type=float, default=14.0, help="画布宽（英寸）；与 --auto-fig-aspect 联用时以 --fig-height 为基准自动改宽")
    p.add_argument("--fig-height", type=float, default=11.0, help="画布高（英寸）；想更大可同时提高本项与 --dpi")
    p.add_argument(
        "--fig-max-width",
        type=float,
        default=32.0,
        help="--auto-fig-aspect 时画布宽（英寸）上限，避免超宽屏；与 map-zoom 无关",
    )
    p.add_argument(
        "--fig-max-height",
        type=float,
        default=22.0,
        help="--auto-fig-aspect 时若按宽高比算出的高度超过此值则整体缩小，避免单帧过高",
    )
    p.add_argument(
        "--auto-fig-aspect",
        action="store_true",
        help="按轨迹包络（含 margin）自动调整 fig 宽高比，减少 equal 留白，相对放大底图与路名",
    )
    p.add_argument(
        "--fill-figure-aspect",
        action="store_true",
        help="对称扩大可视经纬范围，使包络宽高比≈画布英寸比，消除 16:9 等固定画布下 equal 产生的左右/上下大块留白（略多取周边底图）",
    )
    _phone = p.add_mutually_exclusive_group()
    _phone.add_argument(
        "--phone-portrait",
        action="store_true",
        help="竖屏全屏 9:16（窄边宽 = phone-short-edge-px）；忽略 auto-fig-aspect，并自动 fill-figure-aspect",
    )
    _phone.add_argument(
        "--phone-landscape",
        action="store_true",
        help="横屏持握全屏 16:9（窄边高 = phone-short-edge-px）；忽略 auto-fig-aspect，并自动 fill-figure-aspect",
    )
    p.add_argument(
        "--phone-short-edge-px",
        type=int,
        default=1080,
        metavar="PX",
        help="与 --phone-portrait / --phone-landscape 联用：竖屏=视频宽度像素，横屏=视频高度像素；常用 1080，可试 1440、2160",
    )
    p.add_argument(
        "--show-lonlat-axis",
        action="store_true",
        help="显示经纬度刻度与坐标轴边框（默认关闭：无底图外的度数字）",
    )
    p.add_argument(
        "--map-zoom",
        type=int,
        default=None,
        help="地图瓦片级别（约 14~17）；级别过高时部分图源单瓦注记字号偏小，若字糊可试 15~16",
    )
    p.add_argument(
        "--assume-gcj02-track",
        action="store_true",
        help="轨迹点已为 GCJ-02（如从高德导出）时使用，勿再做 WGS→GCJ（若仍用高德/天地图）。",
    )
    p.add_argument("--margin-deg", type=float, default=0.015, help="轨迹包络外扩（度），约 1.7km")
    p.add_argument(
        "--route-full-color",
        default="#3388ff",
        metavar="COLOR",
        help="整段轨迹底轨颜色（matplotlib 颜色串），默认 #3388ff",
    )
    p.add_argument(
        "--route-full-width",
        type=float,
        default=3.0,
        metavar="PT",
        help="整段轨迹底轨线宽（点），默认 3",
    )
    p.add_argument(
        "--route-full-alpha",
        type=float,
        default=0.35,
        metavar="A",
        help="整段轨迹底轨透明度 0~1，默认 0.35",
    )
    p.add_argument(
        "--route-progress-color",
        default="#e53935",
        metavar="COLOR",
        help="动画已跑过段（前景实线）颜色，默认 #e53935",
    )
    p.add_argument(
        "--route-progress-width",
        type=float,
        default=3.5,
        metavar="PT",
        help="动画已跑过段线宽（点），默认 3.5",
    )
    p.add_argument(
        "--min-point-spacing-m",
        type=float,
        default=5.0,
        help="抽稀：相邻点最小间距（米），0 表示不抽稀",
    )
    p.add_argument(
        "--max-route-km",
        type=float,
        default=None,
        metavar="KM",
        help="仅保留从起点起累计距离不超过 KM 的轨迹；要明显加速出片可配合缩短 --duration、降低 --fps",
    )
    p.add_argument(
        "--test-first-km",
        type=float,
        nargs="?",
        const=5.0,
        default=None,
        metavar="KM",
        help="测试/预览：只渲染从起点起前 KM 公里（不必加 --test）。只写 --test-first-km 无数字时默认 5；"
        "与 --max-route-km 同时出现时以 --max-route-km 为准",
    )
    p.add_argument(
        "--test",
        action="store_true",
        help="试跑：未写 --max-route-km/--test-first-km 时默认只取前 5 km；未写 --duration/--fps/--map-zoom 时自动 12s、12fps、zoom=15",
    )
    p.add_argument(
        "--provider",
        choices=("gaode", "osm", "opentopo", "cyclosm", "esri", "carto", "tianditu"),
        default="gaode",
        help="首选底图瓦片（默认 gaode）；失败时自动换其他源除非加 --no-tile-fallback",
    )
    p.add_argument(
        "--carto-style",
        choices=("positron", "voyager", "dark", "light"),
        default="positron",
        help="provider=carto 时的默认浅色/深色样式（可被 --basemap-style 覆盖）",
    )
    p.add_argument(
        "--basemap-style",
        default=None,
        help="高德: normal|detail(道路详图 style8)|satellite；Esri: topo|street|imagery；Carto: positron|voyager|dark；天地图: vec|img|ter|img+cia",
    )
    p.add_argument("--tianditu-key", default=None, help="天地图 tk（也可用环境变量 TIANDITU_KEY）")
    p.add_argument(
        "--no-tile-fallback",
        action="store_true",
        help="禁用瓦片自动回退（只用 --provider）",
    )
    p.add_argument(
        "--no-basemap",
        action="store_true",
        help="不拉取在线瓦片，仅用灰色背景（离线或网络受限时可用）",
    )
    p.add_argument(
        "--tile-read-timeout",
        type=float,
        default=180.0,
        metavar="SEC",
        help="单张瓦片 HTTP 读超时（秒）；默认 180。遇 TimeoutError(60) 多为 contextily 过短，可调大",
    )
    p.add_argument(
        "--tile-connect-timeout",
        type=float,
        default=30.0,
        metavar="SEC",
        help="单张瓦片 TCP 连接超时（秒）",
    )
    p.add_argument("--preview", action="store_true", help="仅弹出窗口预览首帧静态图（不导出视频）")
    p.add_argument(
        "--test-image",
        action="store_true",
        help="测试：只保存一张 PNG（按路线进度绘制已跑段与当前位置），不编码 MP4、不做按公里切分",
    )
    p.add_argument(
        "--test-image-out",
        default=None,
        metavar="PATH",
        help="测试图路径；默认与 --out 同主文件名加 _test.png，无 --out 则用 GPX 同目录下 轨迹名_map_test.png",
    )
    p.add_argument(
        "--test-image-progress",
        type=float,
        default=0.5,
        metavar="P",
        help="测试图路线进度比例 0~1（默认 0.5）；0 接近起点，1 为终点",
    )
    p.add_argument(
        "--no-progress",
        action="store_true",
        help="导出 MP4 时不显示逐帧编码进度条（重定向日志或 CI 时可用）",
    )
    p.add_argument(
        "--gaode-tile-scale",
        type=int,
        choices=(1, 2),
        default=1,
        help="仅高德 detail(style8) 瓦片：2 为 512px（高清），高 dpi 时路名更锐利，请求量更大",
    )
    p.add_argument(
        "--basemap-interpolation",
        default="bilinear",
        choices=("nearest", "bilinear", "bicubic", "none"),
        help="瓦片 imshow 插值：nearest 少抹糊路名但可能略锯齿；默认 bilinear（contextily 同款）",
    )
    p.add_argument(
        "--basemap-warp-resampling",
        default="bilinear",
        choices=("nearest", "bilinear", "cubic", "lanczos"),
        help="EPSG3857→经纬度重采样：默认 bilinear；可试 lanczos / cubic，或 nearest（几何略有锯齿）",
    )
    p.add_argument(
        "--video-crf",
        type=int,
        default=18,
        metavar="N",
        help="libx264 质量模式（与 --video-bitrate-kbps 二选一生效）：越小越清晰，默认 18；不写码率时用此项",
    )
    p.add_argument(
        "--video-bitrate-kbps",
        type=int,
        default=None,
        metavar="KBPS",
        help="固定平均视频码率（千比特/秒，例如 12000≈12Mbps）。指定后忽略 --video-crf。"
        " 静态地图画面极易压缩，名义码率常远高于实际占用，提码率未必增大体积或更清晰。",
    )
    p.add_argument(
        "--video-preset",
        default="medium",
        help="libx264 preset（ultrafast…veryslow）；越慢通常同等体积画质更好，默认 medium",
    )
    p.add_argument(
        "--km-markers",
        action="store_true",
        help="沿路线按间隔标注累计里程（显示坐标与轨迹一致）",
    )
    p.add_argument(
        "--km-interval",
        type=float,
        default=1.0,
        metavar="KM",
        help="里程桩间隔（公里），默认 1",
    )
    p.add_argument(
        "--km-include-start",
        action="store_true",
        help="在起点增加「0」公里桩（否则第一个桩在 km-interval）",
    )
    p.add_argument(
        "--km-format",
        default="{km:g} km",
        help="里程文字格式，占位 {km}；默认 {km:g} 会随小数显示。"
        "若 --km-interval 为 0.5 等，勿用 {km:.0f}，否则相邻半公里会与下一整公里显示同一数字。",
    )
    p.add_argument("--km-fontsize", type=float, default=11.0, help="里程标签字号")
    p.add_argument("--km-fontweight", default="bold", help="里程标签字重")
    p.add_argument("--km-text-color", default="#ffffff", help="里程标签文字颜色")
    p.add_argument("--km-bg-color", default="#c62828", help="里程标签底色")
    p.add_argument("--km-bg-alpha", type=float, default=0.94, help="里程标签底色透明度 0~1")
    p.add_argument("--km-edge-color", default="#ffffff", help="里程标签描边颜色")
    p.add_argument("--km-edge-width", type=float, default=1.35, help="里程标签框线宽")
    p.add_argument(
        "--km-boxstyle",
        default="round,pad=0.4",
        help="里程标签框样式（matplotlib boxstyle），默认圆角",
    )
    p.add_argument("--km-dot-color", default="#ffeb3b", help="里程桩圆点颜色")
    p.add_argument("--km-dot-edgecolor", default="#b71c1c", help="里程桩圆点外缘颜色")
    p.add_argument("--km-dot-edgewidth", type=float, default=0.9, help="里程桩圆点外缘线宽")
    p.add_argument("--km-dot-size", type=float, default=55.0, help="里程桩圆点面积（scatter 的 s）")
    p.add_argument(
        "--km-text-offset-y",
        type=float,
        default=16.0,
        help="标签相对轨迹点的纵向偏移（点，正值向上）",
    )
    p.add_argument(
        "--km-text-offset-x",
        type=float,
        default=0.0,
        help="标签相对轨迹点的横向偏移（点，正值向右）；单桩可再用 overrides 里 text_offset 覆盖",
    )
    p.add_argument(
        "--km-overrides-json",
        default=None,
        metavar="PATH",
        help="与 --km-markers 联用：overrides / show_km / hide_km / with_interval（与 --km-interval 合并），见文件头",
    )
    p.add_argument(
        "--poi-json",
        default=None,
        metavar="PATH",
        help="景点/地标 JSON；默认 lon/lat 为 WGS84，高德抄点请在 JSON 写 coords:gcj02 或见 --poi-coords-default",
    )
    p.add_argument(
        "--poi-coords-default",
        choices=("wgs84", "gcj02"),
        default="wgs84",
        help="POI 未写 coords 时的坐标系：gcj02 适合全部从高德复制的点",
    )
    p.add_argument(
        "--route-endpoints-json",
        default=None,
        metavar="PATH",
        help="起点/终点标注 UTF-8 JSON：对象含 start、end（可选其一），字段同 POI（text/image/样式/offset），"
        "另可选 show_dot、dot_size、dot_color 等；锚点自动取 GPX 轨迹首尾",
    )
    p.add_argument(
        "--split-video-by-km",
        action="store_true",
        help="主视频编码完成后，按累计公里用 ffmpeg 切成多段（需 PATH 中有 ffmpeg）",
    )
    p.add_argument(
        "--split-video-km-step",
        type=float,
        default=1.0,
        metavar="KM",
        help="切分步长（公里），如 1 或 0.5；与动画中 linspace 里程进度一致",
    )
    p.add_argument(
        "--split-video-out-dir",
        default=None,
        metavar="DIR",
        help="分段 MP4 输出目录；默认为主视频同目录下「主文件名_km_segments」",
    )
    p.add_argument(
        "--split-video-name-prefix",
        default=None,
        metavar="NAME",
        help="分段文件名前缀；默认与主视频主文件名相同（不含扩展名）",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    resolve_route_truncation_km(args)
    apply_test_mode_defaults(args)
    if not args.no_basemap:
        install_contextily_tile_request_patch(
            connect_timeout_s=args.tile_connect_timeout,
            read_timeout_s=args.tile_read_timeout,
        )

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    lons, lats = load_gpx_points(args.gpx)
    lons, lats = filter_by_min_spacing(lons, lats, args.min_point_spacing_m)
    if args.max_route_km is not None:
        before = float(cumulative_km(lons, lats)[-1])
        lons, lats = truncate_route_by_max_km(lons, lats, args.max_route_km)
        after = float(cumulative_km(lons, lats)[-1])
        print(f"路线截断（试跑）: 全长 {before:.2f} km → 使用 {after:.2f} km（上限 {args.max_route_km} km）")
    dist_km = cumulative_km(lons, lats)
    total_km = float(dist_km[-1])

    total_frames = max(3, int(round(args.duration * args.fps)))
    lon_f_wgs, lat_f_wgs, prog_km = interpolate_lonlat(lons, lats, dist_km, total_frames)

    m = args.margin_deg
    lon_min, lon_max = float(lons.min()), float(lons.max())
    lat_min, lat_max = float(lats.min()), float(lats.max())

    apply_phone_video_layout(args)

    fig_w, fig_h = args.fig_width, args.fig_height
    if args.auto_fig_aspect:
        fig_w, fig_h = figsize_matched_to_lonlat_extent(
            lon_min,
            lon_max,
            lat_min,
            lat_max,
            m,
            args.fig_height,
            max_width_in=args.fig_max_width,
            max_height_in=args.fig_max_height,
        )
        print(f"画布比例已按轨迹包络调整: {fig_w:.1f}×{fig_h:.1f} 英寸（减轻留白、底图相对更大）")
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=args.dpi)

    wgs_viewport: tuple[float, float, float, float] | None = None
    if args.fill_figure_aspect:
        wgs_viewport = expand_wgs_viewport_to_figure_aspect(
            lon_min, lon_max, lat_min, lat_max, m, fig_w, fig_h
        )
        vw, ve, vs, vn = wgs_viewport
        print(
            "已扩大可视范围以贴合画布比例（减轻 equal 留白）；WGS 约 "
            f"经[{vw:.5f},{ve:.5f}] 纬[{vs:.5f},{vn:.5f}]"
        )

    tianditu_tk = args.tianditu_key or os.environ.get("TIANDITU_KEY")
    loaded_prov: str | None = None

    if args.no_basemap:
        if wgs_viewport is not None:
            ax.set_xlim(wgs_viewport[0], wgs_viewport[1])
            ax.set_ylim(wgs_viewport[2], wgs_viewport[3])
        else:
            ax.set_xlim(lon_min - m, lon_max + m)
            ax.set_ylim(lat_min - m, lat_max + m)
        ax.set_aspect("equal", adjustable="box")
        ax.set_facecolor("#d0d0d0")
        plot_lon, plot_lat = lons, lats
        lon_anim, lat_anim = lon_f_wgs, lat_f_wgs
    else:
        ok, loaded_prov, _ = try_load_basemap(ax, args, tianditu_tk, lons, lats, m, wgs_viewport)
        if not ok:
            ax.clear()
            if wgs_viewport is not None:
                ax.set_xlim(wgs_viewport[0], wgs_viewport[1])
                ax.set_ylim(wgs_viewport[2], wgs_viewport[3])
            else:
                ax.set_xlim(lon_min - m, lon_max + m)
                ax.set_ylim(lat_min - m, lat_max + m)
            ax.set_aspect("equal", adjustable="box")
            ax.set_facecolor("#d0d0d0")
            plot_lon, plot_lat = lons, lats
            lon_anim, lat_anim = lon_f_wgs, lat_f_wgs
        else:
            plot_lon, plot_lat = to_display_lonlat(loaded_prov, lons, lats, args.assume_gcj02_track)
            lon_anim, lat_anim = to_display_lonlat(
                loaded_prov, lon_f_wgs, lat_f_wgs, args.assume_gcj02_track
            )

    # 无底图或加载失败时坐标轴为 WGS，POI 变换需与 osm 一致（不做 GCJ 偏移）
    loaded_prov_for_poi = loaded_prov if loaded_prov is not None else "osm"

    # 半透明整段路线（底轨）
    ax.plot(
        plot_lon,
        plot_lat,
        color=str(args.route_full_color),
        linewidth=float(args.route_full_width),
        alpha=float(args.route_full_alpha),
        solid_capstyle="round",
        zorder=2,
    )
    km_ovr: dict[float, dict] | None = None
    km_show: list[float] | None = None
    km_hide: list[float] | None = None
    km_merge_interval = False
    if args.km_overrides_json:
        if not args.km_markers:
            print("提示: 已指定 --km-overrides-json，但未加 --km-markers；覆盖项不会绘制，请同时加上 --km-markers")
        elif not os.path.isfile(args.km_overrides_json):
            raise FileNotFoundError(f"km-overrides 文件不存在: {args.km_overrides_json}")
        else:
            km_ovr, km_show, km_hide, km_merge_interval = load_km_markers_file(args.km_overrides_json)
    if args.km_markers:
        add_route_km_markers(
            ax,
            plot_lon,
            plot_lat,
            dist_km,
            total_km,
            args,
            km_overrides=km_ovr,
            show_km=km_show,
            hide_km=km_hide,
            merge_interval=km_merge_interval,
        )
    if args.poi_json:
        if not os.path.isfile(args.poi_json):
            raise FileNotFoundError(f"POI 文件不存在: {args.poi_json}")
        add_poi_annotations(
            ax,
            args.poi_json,
            loaded_prov_for_poi,
            args.assume_gcj02_track,
            poi_coords_default=args.poi_coords_default,
        )
    if args.route_endpoints_json:
        if not os.path.isfile(args.route_endpoints_json):
            raise FileNotFoundError(f"起点终点 JSON 不存在: {args.route_endpoints_json}")
        add_route_endpoint_annotations(ax, args.route_endpoints_json, plot_lon, plot_lat)

    line, = ax.plot(
        [],
        [],
        color=str(args.route_progress_color),
        linewidth=float(args.route_progress_width),
        solid_capstyle="round",
        zorder=8,
    )
    head, = ax.plot(
        [],
        [],
        "o",
        color="#ff7043",
        markeredgecolor="white",
        markeredgewidth=1.2,
        markersize=9,
        zorder=9,
    )

    if args.show_lonlat_axis:
        title = ax.set_title("", fontsize=14, pad=8)
    else:
        # 用 figure 坐标叠字，不占 subplot 上边距，才能四边 0 留白
        title = fig.text(
            0.5,
            1.0,
            "",
            transform=fig.transFigure,
            ha="center",
            va="top",
            fontsize=14,
            color="0.12",
        )
        title.set_path_effects([pe.withStroke(linewidth=3.0, foreground="white")])
    apply_map_frame_cleanup(ax, fig, show_axis=args.show_lonlat_axis)

    if args.test_image:
        prog = float(args.test_image_progress)
        prog = max(0.0, min(1.0, prog))
        idx = int(round(prog * (total_frames - 1))) if total_frames > 1 else 0
        idx = max(0, min(total_frames - 1, idx))
        npts = idx + 1
        line.set_data(lon_anim[:npts], lat_anim[:npts])
        head.set_data([lon_anim[idx]], [lat_anim[idx]])
        title.set_text(
            f"测试帧 progress={prog:.2f} | {prog_km[idx]:.2f} / {total_km:.2f} km"
        )
        if args.show_lonlat_axis:
            plt.tight_layout()
        else:
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1, hspace=0, wspace=0)
        if args.test_image_out:
            img_out = os.path.abspath(args.test_image_out)
        elif args.out:
            stem, _ = os.path.splitext(os.path.abspath(args.out))
            img_out = f"{stem}_test.png"
        else:
            gpx_dir = os.path.dirname(os.path.abspath(args.gpx)) or "."
            gpx_base = os.path.splitext(os.path.basename(args.gpx))[0]
            gpx_base = re.sub(r'[^\w\u4e00-\u9fff]+', "_", gpx_base).strip("_") or "route"
            img_out = os.path.join(gpx_dir, f"{gpx_base}_map_test.png")
        os.makedirs(os.path.dirname(img_out) or ".", exist_ok=True)
        ensure_h264_even_pixel_frame(fig)
        fig.savefig(img_out, dpi=args.dpi, pad_inches=0, facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"测试图已保存（不写视频）: {img_out}")
        return

    if args.preview:
        line.set_data(lon_anim[: total_frames // 2 + 1], lat_anim[: total_frames // 2 + 1])
        hf = total_frames // 2
        head.set_data([lon_anim[hf]], [lat_anim[hf]])
        title.set_text(f"预览 | 总长约 {total_km:.2f} km")
        if args.show_lonlat_axis:
            plt.tight_layout()
        else:
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1, hspace=0, wspace=0)
        plt.show()
        return

    out = args.out or default_output_path(args.gpx, args.duration)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    def animate(frame: int):
        n = frame + 1
        line.set_data(lon_anim[:n], lat_anim[:n])
        head.set_data([lon_anim[frame]], [lat_anim[frame]])
        km = prog_km[frame]
        # title.set_text(f"路线动画 | {km:.2f} / {total_km:.2f} km · 帧 {n}/{total_frames}")
        return line, head, title

    anim = animation.FuncAnimation(fig, animate, frames=total_frames, interval=1000 / args.fps, blit=False)
    v_extra = [
        "-preset",
        str(args.video_preset),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    if args.video_bitrate_kbps is not None:
        writer = animation.FFMpegWriter(
            fps=args.fps,
            codec="libx264",
            bitrate=int(args.video_bitrate_kbps),
            extra_args=v_extra,
        )
        enc_note = f"bitrate≈{args.video_bitrate_kbps} kbps"
    else:
        writer = animation.FFMpegWriter(
            fps=args.fps,
            codec="libx264",
            bitrate=-1,
            extra_args=v_extra + ["-crf", str(int(args.video_crf))],
        )
        enc_note = f"CRF {args.video_crf}"
    ensure_h264_even_pixel_frame(fig)
    print(
        f"渲染 {total_frames} 帧 → {out}（约 {args.duration:.1f}s @ {args.fps}fps, dpi={args.dpi}, 编码 {enc_note}）"
    )
    save_kw = {}
    if not args.no_progress:
        save_kw["progress_callback"] = make_animation_save_progress(total_frames)
    anim.save(out, writer=writer, **save_kw)
    if not args.no_progress:
        print()
    plt.close(fig)
    if args.split_video_by_km:
        step = float(args.split_video_km_step)
        if step <= 0:
            print("提示: --split-video-km-step 须为正数，已跳过按公里切分")
        else:
            out_abs = os.path.abspath(out)
            stem = os.path.splitext(os.path.basename(out_abs))[0]
            split_dir = args.split_video_out_dir
            if not split_dir:
                split_dir = os.path.join(os.path.dirname(out_abs), f"{stem}_km_segments")
            prefix = args.split_video_name_prefix or stem
            try:
                split_mp4_by_route_km(
                    out_abs,
                    total_km=total_km,
                    total_frames=total_frames,
                    fps=int(args.fps),
                    step_km=step,
                    out_dir=os.path.abspath(split_dir),
                    name_prefix=prefix,
                    video_crf=None if args.video_bitrate_kbps is not None else int(args.video_crf),
                    video_bitrate_kbps=args.video_bitrate_kbps,
                    video_preset=str(args.video_preset),
                )
            except Exception as e:
                print(f"按公里切分失败: {e}")
    print("完成")


if __name__ == "__main__":
    main()
