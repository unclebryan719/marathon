#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
马拉松探路视频 - 坡度着色版（实时里程显示）
支持导出距离过滤后的 GPX 文件（文件名包含公里数）
"""

import gpxpy
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import math
import numpy as np
import os
import re
from datetime import datetime
from moviepy.video.io.VideoFileClip import VideoFileClip
from gpxpy.gpx import GPX, GPXTrack, GPXTrackSegment, GPXTrackPoint

# ==================== 【配置参数】 ====================
GPX_FILE = "/Users/unclebryan/Documents/马拉松视频/4月27日/202605170730北京大兴花马/20260508_大兴区花马_修复后.gpx"

SPLIT_DISTANCE_M = 500
TEST_ONLY = False
TEST_SEGMENTS = 2

FAST_MODE = False

if FAST_MODE:
    FPS = 15
    DPI = 100
    VIDEO_DURATION = 60
    print("⚡ 快速模式 - 1分钟视频")
else:
    FPS = 30
    DPI = 200
    VIDEO_DURATION = 600
    print("🎬 高质量模式 - 10分钟视频")

CLIMB_THRESHOLD = 1.3

# ========== 【坡度计算配置】 ==========
SLOPE_WINDOW_M = 100
SLOPE_GREEN_THRESHOLD = 3.0
SLOPE_YELLOW_THRESHOLD = 5.0
MAX_SLOPE_FOR_COLOR = 15.0

# ========== 【其他配置】 ==========
POINT_FILTER_DISTANCE = 10          # 过滤冗余点的最小距离（米）
FIG_WIDTH = 16
FIG_HEIGHT = 1

width_px = int(FIG_WIDTH * DPI)
height_px = int(FIG_HEIGHT * DPI)
if width_px % 2 != 0:
    width_px += 1
if height_px % 2 != 0:
    height_px += 1
print(f"   视频尺寸: {width_px} x {height_px} 像素")

LEFT_MARGIN = 0.024
RIGHT_MARGIN = 0.98
TOP_MARGIN = 0.96
BOTTOM_MARGIN = 0.27

FONT_SIZE_INFO = 18
FONT_SIZE_LABEL = 16
FONT_SIZE_TICK = 14
FONT_SIZE_ON_POINT = 16
FONT_SIZE_EXTREME = 14

LINE_WIDTH_BG = 2.0
LINE_WIDTH_DYNAMIC = 3.0
POINT_SIZE = 8

# 数据框位置
TOTAL_BOX_X = 0.25
TOTAL_BOX_Y = 0.85
REALTIME_BOX_X = 0.75
REALTIME_BOX_Y = 0.85


# =================================================


def get_gpx_info(gpx_file):
    basename = os.path.basename(gpx_file)
    name_without_ext = os.path.splitext(basename)[0]
    date_match = re.search(r'(\d{8})', name_without_ext)
    if date_match:
        date_str = date_match.group(1)
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    else:
        formatted_date = datetime.now().strftime("%Y-%m-%d")
    if date_match:
        location = name_without_ext.replace(date_match.group(1), "").lstrip("_")
        if not location:
            location = "route"
    else:
        location = name_without_ext
    location = re.sub(r'[^\w\u4e00-\u9fff]', '_', location)
    return formatted_date, location, name_without_ext


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def calculate_slope_window(dists_km, alts_m, window_m=30):
    n = len(alts_m)
    slopes = np.zeros(n)
    dists_m = dists_km * 1000

    for i in range(n):
        start_dist = dists_m[i] - window_m / 2
        end_dist = dists_m[i] + window_m / 2
        start_idx = max(0, np.searchsorted(dists_m, start_dist))
        end_idx = min(n - 1, np.searchsorted(dists_m, end_dist))

        if end_idx > start_idx:
            window_dist = dists_m[end_idx] - dists_m[start_idx]
            window_elev = alts_m[end_idx] - alts_m[start_idx]
            if window_dist > 5:
                slopes[i] = (window_elev / window_dist) * 100
            else:
                slopes[i] = 0
        else:
            slopes[i] = 0

    slopes = np.clip(slopes, -MAX_SLOPE_FOR_COLOR, MAX_SLOPE_FOR_COLOR)
    return slopes


def get_slope_color(slope_percent):
    abs_slope = abs(slope_percent)
    if abs_slope < SLOPE_GREEN_THRESHOLD:
        return '#3fb950'
    elif abs_slope < SLOPE_YELLOW_THRESHOLD:
        return '#f0883e'
    else:
        return '#f85149'


def get_slope_alpha(slope_percent):
    abs_slope = abs(slope_percent)
    alpha = 0.3 + min(abs_slope * 0.05, 0.4)
    return max(0.3, min(0.7, alpha))


def filter_points_by_distance(lats, lons, alts, min_distance_m=8):
    if len(lats) <= 1:
        return lats, lons, alts
    filtered_lats = [lats[0]]
    filtered_lons = [lons[0]]
    filtered_alts = [alts[0]]
    for i in range(1, len(lats)):
        dist = haversine(filtered_lats[-1], filtered_lons[-1], lats[i], lons[i]) * 1000
        if dist >= min_distance_m:
            filtered_lats.append(lats[i])
            filtered_lons.append(lons[i])
            filtered_alts.append(alts[i])
    return filtered_lats, filtered_lons, filtered_alts


def export_filtered_gpx(lats, lons, alts, output_file):
    """导出过滤后的点集为 GPX 文件"""
    gpx = GPX()
    track = GPXTrack()
    segment = GPXTrackSegment()
    for lat, lon, alt in zip(lats, lons, alts):
        segment.points.append(GPXTrackPoint(latitude=lat, longitude=lon, elevation=alt))
    track.segments.append(segment)
    gpx.tracks.append(track)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(gpx.to_xml())
    print(f"   已导出过滤后的 GPX: {output_file}")


def calculate_ascent_descent_with_threshold(alts, threshold=1.2):
    ascent = 0
    descent = 0
    cumulative_ascent = [0]
    cumulative_descent = [0]
    temp_change = 0
    for i in range(1, len(alts)):
        diff = alts[i] - alts[i - 1]
        temp_change += diff
        if temp_change > threshold:
            ascent += temp_change
            temp_change = 0
        elif temp_change < -threshold:
            descent += abs(temp_change)
            temp_change = 0
        cumulative_ascent.append(ascent)
        cumulative_descent.append(descent)
    return np.array(cumulative_ascent), np.array(cumulative_descent)


def create_full_video_fast(dists, alts, slopes, ascent_arr, descent_arr,
                           total_km, total_ascent, total_descent,
                           alt_min, alt_max, output_file):
    total_frames = VIDEO_DURATION * FPS
    print(f"   生成: {VIDEO_DURATION}秒, {total_frames}帧, DPI={DPI}")

    target_points = min(len(dists), 5000)
    step = max(1, len(dists) // target_points)
    dists_sampled = dists[::step]
    alts_sampled = alts[::step]
    slopes_sampled = slopes[::step]
    ascent_sampled = ascent_arr[::step]
    descent_sampled = descent_arr[::step]
    print(f"   采样: {len(dists)} -> {len(dists_sampled)} 点")

    video_frames_km = np.linspace(0, total_km, total_frames)
    interp_alts = np.interp(video_frames_km, dists_sampled, alts_sampled)
    interp_slopes = np.interp(video_frames_km, dists_sampled, slopes_sampled)
    interp_ascent = np.interp(video_frames_km, dists_sampled, ascent_sampled)
    interp_descent = np.interp(video_frames_km, dists_sampled, descent_sampled)
    indices = [np.searchsorted(dists_sampled, km) for km in video_frames_km]

    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC']
    plt.rcParams['axes.unicode_minus'] = False

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    plt.subplots_adjust(left=LEFT_MARGIN, right=LEFT_MARGIN + 0.95, top=TOP_MARGIN, bottom=BOTTOM_MARGIN)

    ax.set_xlim(0, total_km)
    ax.set_ylim(alt_min - 8, alt_max + 18)
    ax.set_xlabel('Distance (km)', color='#8b949e', fontsize=FONT_SIZE_LABEL)
    ax.set_ylabel('Elevation (m)', color='#8b949e', fontsize=FONT_SIZE_LABEL)
    ax.tick_params(colors='#8b949e', labelsize=FONT_SIZE_TICK)
    ax.grid(True, alpha=0.2, color='#30363d', linewidth=1)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['left'].set_linewidth(1.5)

    # ========== 数据框（去掉里程数） ==========
    total_box = dict(boxstyle='round,pad=0.4', facecolor='#000000', edgecolor='#30363d', alpha=0.85, linewidth=1.5)
    realtime_box = dict(boxstyle='round,pad=0.4', facecolor='#000000', edgecolor='#f0883e', alpha=0.85, linewidth=1.5)

    # 总体数据：只显示爬升和下降
    total_text = f'↑{total_ascent:.0f} m  ↓{total_descent:.0f} m'
    total_info = ax.text(TOTAL_BOX_X, TOTAL_BOX_Y, total_text, transform=ax.transAxes,
                         color='#ffffff', fontsize=FONT_SIZE_INFO, fontweight='bold',
                         verticalalignment='top', bbox=total_box)

    # 实时数据：只显示爬升和下降 + 坡度
    realtime_info = ax.text(REALTIME_BOX_X, REALTIME_BOX_Y, '', transform=ax.transAxes,
                            color='#ffffff', fontsize=FONT_SIZE_INFO, fontweight='bold',
                            verticalalignment='top', bbox=realtime_box)

    # 背景面积图
    ax.fill_between(dists_sampled, alt_min - 5, alts_sampled,
                    alpha=0.15, color='#58a6ff')

    # 最低/最高点标注
    min_idx = np.argmin(alts)
    max_idx = np.argmax(alts)
    min_km = dists[min_idx]
    max_km = dists[max_idx]
    min_alt = alts[min_idx]
    max_alt = alts[max_idx]

    ax.scatter([min_km], [min_alt], color='#3fb950', s=40, zorder=4, marker='v')
    ax.annotate(f'{min_alt:.0f}m', xy=(min_km, min_alt),
                xytext=(min_km, min_alt + 5), textcoords='data',
                color='#ffffff', fontsize=FONT_SIZE_EXTREME,
                ha='center', va='bottom', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='#000000', edgecolor='#3fb950', alpha=0.8))

    ax.scatter([max_km], [max_alt], color='#f85149', s=40, zorder=4, marker='^')
    ax.annotate(f'{max_alt:.0f}m', xy=(max_km, max_alt),
                xytext=(max_km, max_alt + 5), textcoords='data',
                color='#ffffff', fontsize=FONT_SIZE_EXTREME,
                ha='center', va='bottom', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='#000000', edgecolor='#f85149', alpha=0.8))

    # 动态元素
    dynamic_line, = ax.plot([], [], lw=LINE_WIDTH_DYNAMIC, alpha=0.9)
    current_point, = ax.plot([], [], 'o', color='#f0883e', ms=POINT_SIZE, zorder=5)
    progress_line = ax.axvline(x=0, color='#f0883e', lw=2, alpha=0.7)

    # 显示实时里程
    km_label = ax.text(0, 0, '', color='#f0883e', fontsize=FONT_SIZE_ON_POINT,
                       fontweight='bold', ha='center', va='bottom',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='#000000',
                                 edgecolor='#f0883e', alpha=0.8))

    dynamic_fills = []

    def animate(i):
        idx = indices[i]
        current_km = video_frames_km[i]
        current_alt = interp_alts[i]
        current_slope = interp_slopes[i]
        current_ascent = interp_ascent[i]
        current_descent = interp_descent[i]

        for fill in dynamic_fills:
            fill.remove()
        dynamic_fills.clear()

        if idx > 0:
            current_dists = dists_sampled[:idx]
            current_alts = alts_sampled[:idx]

            slope_color = get_slope_color(current_slope)
            alpha_value = get_slope_alpha(current_slope)

            new_fill = ax.fill_between(current_dists, alt_min - 5, current_alts,
                                       alpha=alpha_value, color=slope_color)
            dynamic_fills.append(new_fill)

            dynamic_line.set_data(current_dists, current_alts)
            dynamic_line.set_color(slope_color)
            dynamic_line.set_linewidth(LINE_WIDTH_DYNAMIC)

            current_point.set_data([current_km], [current_alt])

            km_label.set_position((current_km, current_alt + 3))
            km_label.set_text(f'{current_km:.1f} km')

        progress_line.set_xdata([current_km, current_km])

        realtime_str = f'↑{current_ascent:.0f} m  ↓{current_descent:.0f} m  |  {current_slope:.1f}%'
        realtime_info.set_text(realtime_str)

        return [dynamic_line, current_point, progress_line, km_label, realtime_info] + dynamic_fills

    writer = animation.FFMpegWriter(
        fps=FPS,
        bitrate=3000,
        codec='libx264',
        extra_args=['-pix_fmt', 'yuv420p']
    )
    anim = animation.FuncAnimation(fig, animate, frames=total_frames, interval=1000 / FPS, blit=False)
    anim.save(output_file, writer=writer, dpi=DPI)
    plt.close()

    return output_file


def split_video_by_distance(video_path, total_km, split_km, output_dir,
                            date, location, mode_str, max_segments=None):
    clip = VideoFileClip(video_path)
    total_duration = clip.duration
    print(f"   视频总时长: {total_duration:.1f}秒")
    segments = []
    num_segments = int(np.ceil(total_km / split_km))
    if max_segments:
        num_segments = min(num_segments, max_segments)
    for i in range(num_segments):
        start_km = i * split_km
        end_km = min((i + 1) * split_km, total_km)
        start_time = (start_km / total_km) * total_duration
        end_time = (end_km / total_km) * total_duration
        sub_clip = clip.subclipped(start_time, end_time)
        if mode_str == "fast":
            mode_name = "快速"
        else:
            mode_name = "高质量"
        filename = f"{date}_{location}_{mode_name}_第{i + 1:02d}段_{start_km:.1f}-{end_km:.1f}km_分段视频.mp4"
        output_file = os.path.join(output_dir, filename)
        sub_clip.write_videofile(output_file, codec='libx264', audio=False)
        sub_clip.close()
        segments.append(output_file)
        print(f"   路段 {i + 1}: {start_km:.1f}-{end_km:.1f}km -> {filename}")
    clip.close()
    return segments


def main():
    date, location, raw_name = get_gpx_info(GPX_FILE)

    print("=" * 60)
    print("马拉松坡度分析 - 滑动窗口版（实时里程显示）")
    print(f"📍 路线: {location}")
    print(f"📅 日期: {date}")
    print(f"📏 坡度窗口: {SLOPE_WINDOW_M} 米")
    print(
        f"🎨 坡度颜色: 绿色(<{SLOPE_GREEN_THRESHOLD}%) → 橙色({SLOPE_GREEN_THRESHOLD}-{SLOPE_YELLOW_THRESHOLD}%) → 红色(>{SLOPE_YELLOW_THRESHOLD}%)")
    print("=" * 60)

    # 1. 读取 GPX
    print("\n[1/7] 读取原始 GPX...")
    with open(GPX_FILE, 'r') as f:
        gpx = gpxpy.parse(f)

    lats_raw, lons_raw, alts_raw = [], [], []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                lats_raw.append(point.latitude)
                lons_raw.append(point.longitude)
                alts_raw.append(point.elevation if point.elevation else 0)

    print(f"   原始点数: {len(lats_raw)}")

    # 2. 过滤冗余GPS点
    print("\n[2/7] 过滤冗余GPS点（里程纠正）...")
    lats_filtered, lons_filtered, alts_filtered = filter_points_by_distance(
        lats_raw, lons_raw, alts_raw, min_distance_m=POINT_FILTER_DISTANCE
    )
    print(f"   过滤后点数: {len(lats_filtered)}")
    print(f"   过滤比例: {(1 - len(lats_filtered)/len(lats_raw)) * 100:.1f}%")

    # 3. 重新计算距离（提前计算，以便在 GPX 文件名中包含总里程）
    print("\n[3/7] 重新计算距离...")
    dists_raw = [0]
    for i in range(1, len(lats_filtered)):
        dist = haversine(lats_filtered[i - 1], lons_filtered[i - 1],
                         lats_filtered[i], lons_filtered[i])
        dists_raw.append(dists_raw[-1] + dist)
    dists_raw = np.array(dists_raw)
    alts_raw = np.array(alts_filtered)
    total_km = dists_raw[-1]
    print(f"   纠正后总距离: {total_km:.2f} km")

    # 创建输出目录（用于保存过滤后的GPX和视频）
    output_dir = "elevation_segments"
    os.makedirs(output_dir, exist_ok=True)

    # 【修改】导出过滤后的 GPX 文件（文件名包含总公里数）
    filtered_gpx_filename = f"{date}_{location}_filtered_{POINT_FILTER_DISTANCE}m_{total_km:.2f}km.gpx"
    filtered_gpx_path = os.path.join(output_dir, filtered_gpx_filename)
    export_filtered_gpx(lats_filtered, lons_filtered, alts_filtered, filtered_gpx_path)

    # 4. 计算滑动窗口坡度
    print(f"\n[4/7] 计算滑动窗口坡度（窗口={SLOPE_WINDOW_M}米）...")
    slopes = calculate_slope_window(dists_raw, alts_raw, window_m=SLOPE_WINDOW_M)

    # 统计坡度分布
    abs_slopes = np.abs(slopes)
    steep_count = np.sum(abs_slopes >= SLOPE_YELLOW_THRESHOLD)
    moderate_count = np.sum((abs_slopes >= SLOPE_GREEN_THRESHOLD) & (abs_slopes < SLOPE_YELLOW_THRESHOLD))
    gentle_count = np.sum(abs_slopes < SLOPE_GREEN_THRESHOLD)
    print(f"   坡度分布: 平缓({gentle_count}点) | 中等({moderate_count}点) | 陡峭({steep_count}点)")
    print(f"   最大坡度: {np.max(abs_slopes):.1f}%")

    # 找出陡坡路段
    steep_indices = np.where(abs_slopes >= SLOPE_YELLOW_THRESHOLD)[0]
    if len(steep_indices) > 0:
        print(f"\n   📍 陡坡路段（>{SLOPE_YELLOW_THRESHOLD}%）:")
        groups = []
        current_group = [steep_indices[0]]
        for j in range(1, len(steep_indices)):
            if steep_indices[j] - steep_indices[j - 1] <= 10:
                current_group.append(steep_indices[j])
            else:
                groups.append(current_group)
                current_group = [steep_indices[j]]
        groups.append(current_group)

        for g in groups:
            if len(g) > 3:
                start_km = dists_raw[g[0]]
                end_km = dists_raw[g[-1]]
                max_slope = np.max(abs_slopes[g])
                print(
                    f"      {start_km:.2f} - {end_km:.2f} km, 长度{end_km - start_km:.2f}km, 最大坡度{max_slope:.1f}%")

    # 5. 计算累计爬升
    print("\n[5/7] 计算累计爬升/下降...")
    ascent_raw, descent_raw = calculate_ascent_descent_with_threshold(alts_raw, CLIMB_THRESHOLD)
    total_ascent = ascent_raw[-1]
    total_descent = descent_raw[-1]
    alt_min, alt_max = alts_raw.min(), alts_raw.max()
    print(f"   累计爬升: {total_ascent:.0f} m")
    print(f"   累计下降: {total_descent:.0f} m")
    print(f"   海拔范围: {alt_min:.0f} - {alt_max:.0f} m")

    # 6. 生成完整视频
    print("\n[6/7] 生成完整视频...")
    mode_str = "fast" if FAST_MODE else "high"
    mode_name = "快速" if FAST_MODE else "高质量"
    duration_min = 1 if FAST_MODE else 10

    full_video_filename = f"{date}_{location}_{mode_name}_{duration_min}min_坡度窗口{SLOPE_WINDOW_M}m_{total_km:.2f}km_完整视频.mp4"
    full_video_path = os.path.join(output_dir, full_video_filename)

    if os.path.exists(full_video_path):
        print(f"   完整视频已存在: {full_video_filename}")
    else:
        create_full_video_fast(dists_raw, alts_raw, slopes, ascent_raw, descent_raw,
                               total_km, total_ascent, total_descent,
                               alt_min, alt_max, full_video_path)
        print(f"   完整视频已保存: {full_video_filename}")

    # 7. 拆分视频
    print("\n[7/7] 拆分视频...")
    split_km = SPLIT_DISTANCE_M / 1000
    if TEST_ONLY:
        print(f"\n   🔧 测试模式: 只生成前 {TEST_SEGMENTS} 段")
        segments = split_video_by_distance(
            full_video_path, total_km, split_km, output_dir,
            date, location, mode_str,
            max_segments=TEST_SEGMENTS
        )
    else:
        segments = split_video_by_distance(
            full_video_path, total_km, split_km, output_dir,
            date, location, mode_str
        )

    print("\n" + "=" * 60)
    print("✅ 完成！")
    print("=" * 60)
    print(f"📁 输出目录: {output_dir}/")
    print(f"📄 过滤后 GPX: {filtered_gpx_filename}")
    print(f"🎬 完整视频: {full_video_filename}")
    if TEST_ONLY:
        print(f"✂️  分段视频: 前 {TEST_SEGMENTS} 段")
    else:
        print(f"✂️  分段视频: {len(segments)} 段")
    print(f"\n📊 显示内容:")
    print(f"   - 总体数据: 累计爬升/下降")
    print(f"   - 实时数据: 实时爬升/下降 + 坡度")
    print(f"   - 面积图标签: 实时里程（跟随进度条）")
    print(f"\n🎨 坡度颜色说明:")
    print(f"   - 绿色: 坡度 < {SLOPE_GREEN_THRESHOLD}% (平缓)")
    print(f"   - 橙色: 坡度 {SLOPE_GREEN_THRESHOLD}%-{SLOPE_YELLOW_THRESHOLD}% (中等)")
    print(f"   - 红色: 坡度 > {SLOPE_YELLOW_THRESHOLD}% (陡峭)")


if __name__ == "__main__":
    main()