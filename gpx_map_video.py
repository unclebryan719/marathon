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
默认已关闭经纬度刻度（干净地图）；要刻度请加 --show-lonlat-axis。

示例：
  .venv/bin/python gpx_map_video.py --gpx route.gpx --out map_route.mp4
  .venv/bin/python gpx_map_video.py --gpx route.gpx --provider esri --basemap-style imagery
  试跑：--test（默认截断前 5 km，且未写 --duration/--fps/--map-zoom 时会自动用短时长、低帧率、zoom=15 加速）
  只测前若干公里：--test-first-km 5 或仅 --test-first-km（默认 5 km），不必加 --test；与 --max-route-km 同时写时以后者为准
  或手写：--max-route-km 2 --duration 10 --fps 12
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from datetime import datetime

import gpxpy
import matplotlib

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np


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

    # 半透明已跑过路线（全轨迹）
    ax.plot(
        plot_lon,
        plot_lat,
        color="#3388ff",
        linewidth=3,
        alpha=0.35,
        solid_capstyle="round",
        zorder=2,
    )
    line, = ax.plot([], [], color="#e53935", linewidth=3.5, solid_capstyle="round", zorder=3)
    head, = ax.plot([], [], "o", color="#ff7043", markeredgecolor="white", markeredgewidth=1.2, markersize=9, zorder=4)

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
    print("完成")


if __name__ == "__main__":
    main()
