#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPX → 地图轨迹动画 MP4（MapTiler Cloud 栅格底图）。

与 gpx_map_video.py（高德等）相比：
  - 使用 MapTiler 官方 XYZ，可选 @2x 视网膜瓦片（单瓦 512×512），同样 zoom 下源像素更多，利于高 dpi / 4K。
  - 轨迹与底图均为 WGS84；在中国大陆若要与「火星坐标」路网严丝对齐，请仍用 gpx_map_video.py 高德源。

需 API Key：https://cloud.maptiler.com/  → 环境变量 MAPTILER_API_KEY 或 --maptiler-key

中文道路名 / 少英文注记（栅格瓦片无法在 URL 里改语言，须在云端改样式）：
  1. 登录 cloud.maptiler.com → Maps → 选一个基础样式（如 Streets）→ Open in Map Designer。
  2. 按 Alt+S 打开 Settings → Worldview → Language：选「简体中文」或「Local（当地语言）」；
     保存 / Publish 后会得到你自己的 map id（一串唯一名），命令行里用 --map-id 填这个 id。
  3. 数据来自 OpenStreetMap，国内小路、新路的中文名覆盖不如高德全；路网位置为 WGS84，
     与国内常用 GCJ 底图可能有数百米级偏差——若既要中文又要与国内导航路网对齐，请用 gpx_map_video.py + 高德。

示例：
  export MAPTILER_API_KEY=WJkBuKHkQCXGDv4oS48N
  .venv/bin/python gpx_map_video_maptiler.py --gpx route.gpx --preset-4k --map-id streets-v2

  .venv/bin/python gpx_map_video_maptiler.py --gpx route.gpx --dpi 240 --fig-width 16 --fig-height 9 \\
    --map-zoom-fit-output --video-bitrate 35000 --map-id outdoor-v2

  只测前 5 km：--test-first-km 5 或 --test-first-km（默认 5）；快速试跑可加 --test（默认前 5 km + 短时长/低 fps）
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

_CONTEXTILY_TILE_PATCH_INSTALLED = False


def install_contextily_tile_request_patch(
    *, connect_timeout_s: float = 30.0, read_timeout_s: float = 180.0
) -> None:
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


# MapTiler Cloud 栅格 XYZ 路径必须为 …/maps/{mapId}/256/{z}/{x}/{y}[@2x].png（见官方 Maps API），
# 缺少 /256/ 时会整批 404。
_MAPTILER_RASTER_MAP_ALIASES: dict[str, str] = {
    "outdoors": "outdoor-v2",
    "outdoor": "outdoor-v2",
    "streets": "streets-v2",
    "terrain": "terrain-v2",
    "toner": "toner-v2",
    "bright": "bright-v2",
    "winter": "winter-v2",
    "topo": "topo-v2",
}


def normalize_maptiler_map_id(map_id: str) -> str:
    stripped = map_id.strip().strip("/")
    return _MAPTILER_RASTER_MAP_ALIASES.get(stripped.lower(), stripped)


def maptiler_xyz_url(map_id: str, api_key: str, *, retina: bool) -> str:
    """MapTiler Cloud 栅格瓦片；@2x 为 512×512，与 256 瓦片同一瓦片地理范围。"""
    rid = normalize_maptiler_map_id(map_id)
    scale = "@2x" if retina else ""
    return f"https://api.maptiler.com/maps/{rid}/256/{{z}}/{{x}}/{{y}}{scale}.png?key={api_key}"


def _merged_tile_pixel_size(tiles: list, tile_edge_px: int) -> tuple[int, int]:
    if not tiles:
        return 0, 0
    xs = [t.x for t in tiles]
    ys = [t.y for t in tiles]
    tw = max(xs) - min(xs) + 1
    th = max(ys) - min(ys) + 1
    return tw * tile_edge_px, th * tile_edge_px


def map_zoom_for_lonlat_output_pixels(
    west: float,
    south: float,
    east: float,
    north: float,
    min_width_px: int,
    min_height_px: int,
    *,
    tile_edge_px: int,
    z_min: int = 3,
    z_max: int = 18,
    max_tiles: int = 480,
) -> int:
    import mercantile as mt

    if east <= west or north <= south:
        return min(14, z_max)
    best = z_min
    for z in range(z_min, z_max + 1):
        tiles = list(mt.tiles(west, south, east, north, [z]))
        if len(tiles) > max_tiles:
            break
        tw, th = _merged_tile_pixel_size(tiles, tile_edge_px)
        if tw >= min_width_px and th >= min_height_px:
            best = z
    return int(best)


def expand_wgs_viewport_to_figure_aspect(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    margin_deg: float,
    fig_width_in: float,
    fig_height_in: float,
) -> tuple[float, float, float, float]:
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
    elif r > target - eps:
        new_sy = sx / target
        d = (new_sy - sy) / 2.0
        south -= d
        north += d
    return west, east, south, north


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
    if show_axis:
        return
    ax.set_axis_off()
    for spine in ax.spines.values():
        spine.set_visible(False)
    if hasattr(fig, "set_layout_engine"):
        fig.set_layout_engine(None)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1, hspace=0, wspace=0)


def ensure_h264_even_pixel_frame(fig) -> None:
    dpi = float(fig.dpi)
    wi, hi = fig.get_size_inches()
    wpx = max(2, int(round(wi * dpi)))
    hpx = max(2, int(round(hi * dpi)))
    wpx += wpx % 2
    hpx += hpx % 2
    fig.set_size_inches(wpx / dpi, hpx / dpi, forward=True)


def make_animation_save_progress(total_frames: int):
    """matplotlib Animation.save(progress_callback=…) 终端进度条。"""
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
    return np.asarray(out_lon, dtype=float), np.asarray(out_lat, dtype=float)


def cumulative_km(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    d = np.zeros(len(lons), dtype=float)
    for i in range(1, len(lons)):
        d[i] = d[i - 1] + haversine_km(float(lats[i - 1]), float(lons[i - 1]), float(lats[i]), float(lons[i]))
    return d


def truncate_route_by_max_km(
    lons: np.ndarray, lats: np.ndarray, max_km: float | None
) -> tuple[np.ndarray, np.ndarray]:
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
    base = os.path.dirname(os.path.abspath(gpx_path))
    out_dir = os.path.join(base, "..", "map_videos") if base else "map_videos"
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    dur_tag = str(int(duration_s)) if float(duration_s).is_integer() else f"{duration_s:.1f}".rstrip("0").rstrip(".")
    return os.path.join(out_dir, f"{stem}_{dur_tag}s_maptiler.mp4")


def add_maptiler_basemap(
    ax,
    map_id: str,
    api_key: str,
    zoom: int | str | None,
    *,
    retina: bool,
    interpolation: str,
) -> None:
    import contextily as ctx

    url = maptiler_xyz_url(map_id, api_key, retina=retina)
    z = zoom if zoom is not None else "auto"
    ctx.add_basemap(ax, crs="EPSG:4326", source=url, zoom=z, interpolation=interpolation)


def try_load_maptiler(
    ax,
    map_id: str,
    api_key: str,
    zoom: int | None,
    *,
    map_zoom_fit_output: bool,
    map_zoom_max_tiles: int,
    retina: bool,
    interpolation: str,
    lons: np.ndarray,
    lats: np.ndarray,
    margin_deg: float,
    wgs_viewport: tuple[float, float, float, float] | None,
) -> bool:
    tile_px = 512 if retina else 256
    try:
        ax.clear()
        if wgs_viewport is not None:
            w, e, s, n = wgs_viewport
            ax.set_xlim(w, e)
            ax.set_ylim(s, n)
        else:
            ax.set_xlim(float(lons.min()) - margin_deg, float(lons.max()) + margin_deg)
            ax.set_ylim(float(lats.min()) - margin_deg, float(lats.max()) + margin_deg)
        ax.set_aspect("equal", adjustable="box")
        zm_use: int | str | None = zoom
        if zm_use is None and map_zoom_fit_output:
            fig = ax.figure
            wpx = max(64, int(round(fig.get_figwidth() * fig.dpi)))
            hpx = max(64, int(round(fig.get_figheight() * fig.dpi)))
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            west, east = sorted((float(xmin), float(xmax)))
            south, north = sorted((float(ymin), float(ymax)))
            zm_use = map_zoom_for_lonlat_output_pixels(
                west,
                south,
                east,
                north,
                wpx,
                hpx,
                tile_edge_px=tile_px,
                z_max=18,
                max_tiles=map_zoom_max_tiles,
            )
            print(
                f"MapTiler 推算 zoom={zm_use}（拼瓦目标 ≥ {wpx}×{hpx} px，"
                f"瓦片边长 {tile_px}px，瓦片数上限 {map_zoom_max_tiles}）"
            )
        add_maptiler_basemap(
            ax, map_id, api_key, zm_use, retina=retina, interpolation=interpolation
        )
        resolved = normalize_maptiler_map_id(map_id)
        print(f"底图已加载: MapTiler map_id={resolved!r} retina={retina}")
        return True
    except Exception as e:
        print(f"MapTiler 底图加载失败: {e}")
        msg = str(e)
        if "403" in msg or "Forbidden" in msg:
            print(
                "  提示(403): 多为「密钥无权访问该地图」或套餐限制。"
                "请在同一 MapTiler 账号下核对：① Keys 是否勾选 Maps / Tiles；② 自定义样式是否已 Publish；"
                "③ map-id 是否复制自当前账号；④ Key 是否启用了 HTTP Referer 限制（脚本请求无 Referer 会 403，需关掉或放行）。"
                "仍失败可先用内置 --map-id streets-v2 验证密钥是否正常。"
            )
        return False


def _argv_has_long_option(argv: list[str], flag: str) -> bool:
    eq = f"{flag}="
    for a in argv:
        if a == flag or a.startswith(eq):
            return True
    return False


def resolve_route_truncation_km(args: argparse.Namespace, argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv
    if _argv_has_long_option(argv, "--max-route-km"):
        return
    if not _argv_has_long_option(argv, "--test-first-km"):
        return
    if args.test_first_km is not None:
        args.max_route_km = float(args.test_first_km)


def apply_test_mode_defaults(args: argparse.Namespace) -> None:
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
    p = argparse.ArgumentParser(description="GPX → 轨迹动画 MP4（MapTiler 底图，WGS84）")
    p.add_argument("--gpx", required=True, help="输入 GPX")
    p.add_argument("--out", default=None, help="输出 MP4（默认 map_videos/…_maptiler.mp4）")
    p.add_argument("--maptiler-key", default=None, help="MapTiler API key（或环境变量 MAPTILER_API_KEY）")
    p.add_argument(
        "--map-id",
        default="streets-v2",
        help="地图 id：内置样式见 cloud.maptiler.com/maps；要中文注记请在 Map Designer 设语言后用自己的 id。"
        "简写 outdoors→outdoor-v2 等见脚本内别名",
    )
    p.add_argument(
        "--retina",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="使用 @2x 瓦片（512px/边，默认 --retina；关闭用 --no-retina）",
    )
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--dpi", type=int, default=180)
    p.add_argument("--fig-width", type=float, default=14.0)
    p.add_argument("--fig-height", type=float, default=11.0)
    p.add_argument("--fig-max-width", type=float, default=32.0)
    p.add_argument("--fig-max-height", type=float, default=22.0)
    p.add_argument("--auto-fig-aspect", action="store_true")
    p.add_argument("--fill-figure-aspect", action="store_true")
    p.add_argument("--show-lonlat-axis", action="store_true")
    p.add_argument("--map-zoom", type=int, default=None)
    p.add_argument(
        "--map-zoom-fit-output",
        action="store_true",
        help="未写 --map-zoom 时按 fig×dpi 推算 zoom（高分辨率推荐）",
    )
    p.add_argument("--map-zoom-max-tiles", type=int, default=480)
    p.add_argument("--margin-deg", type=float, default=0.015)
    p.add_argument("--min-point-spacing-m", type=float, default=8.0)
    p.add_argument("--max-route-km", type=float, default=None, metavar="KM", help="从起点起最多保留 KM 公里")
    p.add_argument(
        "--test-first-km",
        type=float,
        nargs="?",
        const=5.0,
        default=None,
        metavar="KM",
        help="测试：只渲染前 KM 公里（不必 --test）；只写 --test-first-km 时默认 5；与 --max-route-km 同时写以后者为准",
    )
    p.add_argument(
        "--test",
        action="store_true",
        help="快速试跑：未写截断公里时默认前 5 km，并压低 duration/fps/map-zoom（若未单独指定）",
    )
    p.add_argument(
        "--video-bitrate",
        type=int,
        default=12_000,
        metavar="KBPS",
        help="H.264 码率（kbps）；4K 建议 28000～45000",
    )
    p.add_argument("--basemap-interpolation", default="bilinear")
    p.add_argument(
        "--preset-4k",
        action="store_true",
        help="3840×2160：dpi=240、16×9、码率 35Mbps；未写 --map-zoom 时启用 --map-zoom-fit-output",
    )
    p.add_argument("--tile-read-timeout", type=float, default=180.0)
    p.add_argument("--tile-connect-timeout", type=float, default=30.0)
    p.add_argument("--preview", action="store_true")
    p.add_argument(
        "--no-progress",
        action="store_true",
        help="导出 MP4 时不显示编码进度条",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    resolve_route_truncation_km(args)
    argv = sys.argv
    if args.preset_4k:
        args.dpi = 240
        args.fig_width = 16.0
        args.fig_height = 9.0
        if not _argv_has_long_option(argv, "--video-bitrate"):
            args.video_bitrate = 35_000
        if args.map_zoom is None and not _argv_has_long_option(argv, "--map-zoom-fit-output"):
            args.map_zoom_fit_output = True
    apply_test_mode_defaults(args)

    key = (args.maptiler_key or os.environ.get("MAPTILER_API_KEY") or "").strip()
    if not key:
        print("错误: 请设置 MAPTILER_API_KEY 或使用 --maptiler-key", file=sys.stderr)
        sys.exit(1)

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
        print(f"路线截断: {before:.2f} km → {after:.2f} km（上限 {args.max_route_km} km）")
    dist_km = cumulative_km(lons, lats)
    total_km = float(dist_km[-1])
    total_frames = max(3, int(round(args.duration * args.fps)))
    lon_f, lat_f, prog_km = interpolate_lonlat(lons, lats, dist_km, total_frames)

    m = args.margin_deg
    lon_min, lon_max = float(lons.min()), float(lons.max())
    lat_min, lat_max = float(lats.min()), float(lats.max())

    fig_w, fig_h = args.fig_width, args.fig_height
    if args.auto_fig_aspect:
        fig_w, fig_h = figsize_matched_to_lonlat_extent(
            lon_min, lon_max, lat_min, lat_max, m, args.fig_height,
            max_width_in=args.fig_max_width, max_height_in=args.fig_max_height,
        )
        print(f"画布比例: {fig_w:.1f}×{fig_h:.1f} 英寸")
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=args.dpi)

    wgs_viewport: tuple[float, float, float, float] | None = None
    if args.fill_figure_aspect:
        wgs_viewport = expand_wgs_viewport_to_figure_aspect(
            lon_min, lon_max, lat_min, lat_max, m, fig_w, fig_h
        )

    ok = try_load_maptiler(
        ax,
        args.map_id,
        key,
        args.map_zoom,
        map_zoom_fit_output=args.map_zoom_fit_output,
        map_zoom_max_tiles=args.map_zoom_max_tiles,
        retina=args.retina,
        interpolation=args.basemap_interpolation,
        lons=lons,
        lats=lats,
        margin_deg=m,
        wgs_viewport=wgs_viewport,
    )
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

    ax.plot(
        lons, lats,
        color="#3388ff",
        linewidth=3,
        alpha=0.35,
        solid_capstyle="round",
        zorder=2,
    )
    line, = ax.plot([], [], color="#e53935", linewidth=3.5, solid_capstyle="round", zorder=3)
    head, = ax.plot(
        [], [], "o", color="#ff7043", markeredgecolor="white", markeredgewidth=1.2, markersize=9, zorder=4
    )

    if args.show_lonlat_axis:
        title = ax.set_title("", fontsize=14, pad=8)
    else:
        title = fig.text(
            0.5, 1.0, "", transform=fig.transFigure, ha="center", va="top", fontsize=14, color="0.12"
        )
        title.set_path_effects([pe.withStroke(linewidth=3.0, foreground="white")])
    apply_map_frame_cleanup(ax, fig, show_axis=args.show_lonlat_axis)

    if args.preview:
        hf = total_frames // 2
        line.set_data(lon_f[: hf + 1], lat_f[: hf + 1])
        head.set_data([lon_f[hf]], [lat_f[hf]])
        title.set_text(f"MapTiler 预览 | {total_km:.2f} km")
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
        line.set_data(lon_f[:n], lat_f[:n])
        head.set_data([lon_f[frame]], [lat_f[frame]])
        return line, head, title

    anim = animation.FuncAnimation(fig, animate, frames=total_frames, interval=1000 / args.fps, blit=False)
    writer = animation.FFMpegWriter(
        fps=args.fps,
        codec="libx264",
        bitrate=args.video_bitrate,
        extra_args=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    ensure_h264_even_pixel_frame(fig)
    print(
        f"渲染 {total_frames} 帧 → {out}（{args.duration:.1f}s @ {args.fps}fps, "
        f"dpi={args.dpi}, 码率={args.video_bitrate} kbps, retina={args.retina}）"
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
