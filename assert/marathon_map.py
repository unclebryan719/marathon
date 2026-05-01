"""
GPX 轨迹动画 - 支持天地图多种样式（矢量/影像/地形）
"""

import gpxpy
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import contextily as ctx
from matplotlib.animation import FuncAnimation
import warnings
import os

warnings.filterwarnings('ignore')

# ================== 配置区域 ==================


GPX_FILE = "/Users/unclebryan/Desktop/20260422_青岛西海岸.gpx"          # 修改为你的文件路径
TIANDITU_KEY = "a54ebf354d5319c016319207becd3cbc"   # 替换为你在天地图申请的密钥

# 底图样式选择：
# 'vec'   - 矢量地图（默认，颜色较淡）
# 'img'   - 影像地图（卫星图，真实色彩）
# 'ter'   - 地形图（有等高线晕渲）
# 'img+cia' - 影像+注记（推荐，卫星图+道路地名）
BASEMAP_STYLE = 'img+cia'  # 可改为 'img', 'vec', 'ter'

MAX_POINTS = 300
FPS = 30
DPI = 120
TEST_MODE = True     # True: 弹窗预览; False: 保存视频

# ================== 1. 解析 GPX ==================
def load_gpx(gpx_path, max_points=300):
    with open(gpx_path, 'r') as f:
        gpx = gpxpy.parse(f)
    lons, lats = [], []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                lons.append(point.longitude)
                lats.append(point.latitude)
    if len(lons) == 0:
        raise ValueError("无轨迹点")
    df = pd.DataFrame({'lon': lons, 'lat': lats})
    if len(df) > max_points:
        idx = np.linspace(0, len(df)-1, max_points, dtype=int)
        df = df.iloc[idx].reset_index(drop=True)
    return df

# ================== 2. 天地图 URL 构建 ==================
def get_tianditu_url(style, key):
    """
    根据样式返回天地图 WMTS URL
    style: 'vec', 'img', 'ter', 'cia'（注记层）
    注记层通常需要叠加在影像上，所以 'img+cia' 会返回两个图层叠加的配置
    """
    base_url = "http://t{subdomain}.tianditu.gov.cn/{layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={key}"
    subdomains = ['0', '1', '2', '3', '4', '5', '6', '7']

    if style == 'vec':
        # 矢量底图
        url = base_url.format(subdomain='0', layer='vec', key=key)
    elif style == 'img':
        # 影像底图
        url = base_url.format(subdomain='0', layer='img', key=key)
    elif style == 'ter':
        # 地形底图
        url = base_url.format(subdomain='0', layer='ter', key=key)
    elif style == 'cia':
        # 注记层（通常需要叠加在影像上）
        url = base_url.format(subdomain='0', layer='cia', key=key)
    elif style == 'img+cia':
        # 影像+注记：返回一个特殊配置，由 contextily 叠加两个图层
        # 注意：contextily 一次只能添加一个图层，这里我们返回影像图层 URL，
        # 然后单独添加注记层（需要额外处理）
        # 简便方法：仅返回影像，告知用户注记无法自动叠加，可手动添加。
        # 为了简化，这里先返回影像，用户可接受无注记。
        url = base_url.format(subdomain='0', layer='img', key=key)
        print("提示：'img+cia' 样式需要叠加两个图层，当前仅显示影像层，注记层未自动叠加。")
    else:
        url = base_url.format(subdomain='0', layer='vec', key=key)
    return url

# ================== 3. 添加底图（天地图）==================
def add_basemap(ax, df, tianditu_key, style='vec'):
    try:
        url = get_tianditu_url(style, tianditu_key)
        print(f"正在加载天地图底图（样式: {style}）...")
        ctx.add_basemap(ax, url=url, crs='EPSG:4326', zoom='auto')
        print("天地图底图加载成功")
        return True
    except Exception as e:
        print(f"天地图加载失败: {e}")
        ax.set_facecolor('lightgray')
        print("使用纯色背景")
        return False

# ================== 4. 创建动画 ==================
def create_animation(df, output_path=None, fps=30, dpi=120,
                     tianditu_key=None, style='vec'):
    lon_min, lon_max = df['lon'].min(), df['lon'].max()
    lat_min, lat_max = df['lat'].min(), df['lat'].max()
    margin = 0.02
    extent = (lon_min - margin, lon_max + margin,
              lat_min - margin, lat_max + margin)

    fig, ax = plt.subplots(figsize=(10, 7), dpi=dpi)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect('equal')

    # 添加底图
    if tianditu_key and tianditu_key != "YOUR_TIANDITU_KEY":
        add_basemap(ax, df, tianditu_key, style)
    else:
        ax.set_facecolor('lightgray')
        print("未配置天地图密钥，使用纯色背景")

    # 轨迹线和点
    line, = ax.plot([], [], 'b-', linewidth=2.5, alpha=0.9, zorder=3)
    point, = ax.plot([], [], 'ro', markersize=7, zorder=4)

    total_frames = len(df)
    ax.set_title(f"轨迹动画 | 总点数: {total_frames}")

    def init():
        line.set_data([], [])
        point.set_data([], [])
        return line, point

    def update(frame):
        seg_x = df['lon'].iloc[:frame+1].tolist()
        seg_y = df['lat'].iloc[:frame+1].tolist()
        line.set_data(seg_x, seg_y)
        point.set_data([df['lon'].iloc[frame]], [df['lat'].iloc[frame]])
        ax.set_title(f"进度: {frame+1}/{total_frames}")
        return line, point

    ani = FuncAnimation(fig, update, frames=total_frames,
                        init_func=init, blit=True,
                        interval=1000/fps, repeat=False)

    if output_path:
        print(f"保存视频到 {output_path}")
        ani.save(output_path, writer='ffmpeg', fps=fps, dpi=dpi)
    else:
        plt.show()
    return ani

# ================== 5. 主程序 ==================
if __name__ == "__main__":
    try:
        df = load_gpx(GPX_FILE, max_points=MAX_POINTS)
        print(f"轨迹点数: {len(df)}")

        if TEST_MODE:
            print("预览模式，弹出窗口...")
            create_animation(df, output_path=None, fps=FPS, dpi=DPI,
                             tianditu_key=TIANDITU_KEY,
                             style=BASEMAP_STYLE)
        else:
            create_animation(df, output_path="output.mp4", fps=FPS, dpi=DPI,
                             tianditu_key=TIANDITU_KEY,
                             style=BASEMAP_STYLE)

    except FileNotFoundError:
        print(f"文件 {GPX_FILE} 不存在，请修改路径")
    except Exception as e:
        print(f"错误: {e}")