# GPX 地图轨迹动画脚本 – 参数使用说明

本文档适用于 `gpx_map_video.py`（全景/固定视图）和 `gpx_map_video_follow.py`（动态跟随视图）。所有参数均通过命令行传递。

------

## 一、基本输入输出

| 参数             | 说明                                               | 默认值 |
| :--------------- | :------------------------------------------------- | :----- |
| `--gpx PATH`     | 输入的 GPX 文件路径（必填）                        | 无     |
| `--out PATH`     | 输出 MP4 路径。默认自动生成在 `map_videos/` 目录下 | 自动   |
| `--duration SEC` | 视频时长（秒）                                     | 60     |
| `--fps N`        | 帧率                                               | 30     |
| `--dpi N`        | 渲染 DPI（影响像素密度，建议 180~300）             | 180    |

**示例**

bash

```
--gpx route.gpx --out video.mp4 --duration 45 --fps 24 --dpi 240
```



------

## 二、画布与尺寸（核心清晰度控制）

| 参数                       | 说明                                                      | 默认值 |
| :------------------------- | :-------------------------------------------------------- | :----- |
| `--fig-width INCH`         | 画布宽度（英寸）                                          | 14.0   |
| `--fig-height INCH`        | 画布高度（英寸）                                          | 11.0   |
| `--auto-fig-aspect`        | 根据轨迹包络自动调整宽高比（减轻留白）                    | 不开启 |
| `--fill-figure-aspect`     | 对称扩大经纬度范围，使地图铺满画布（消除 equal 留白）     | 不开启 |
| `--phone-portrait`         | 竖屏 9:16 模式，自动设置画布并启用 `--fill-figure-aspect` | 不开启 |
| `--phone-landscape`        | 横屏 16:9 模式，同上                                      | 不开启 |
| `--phone-short-edge-px PX` | 竖屏时视频宽度像素，横屏时视频高度像素                    | 1080   |
| `--fig-max-width INCH`     | `--auto-fig-aspect` 时的宽度上限                          | 32.0   |
| `--fig-max-height INCH`    | `--auto-fig-aspect` 时的高度上限                          | 22.0   |

**尺寸与清晰度公式**
`视频像素 = fig-width × dpi` （宽） / `fig-height × dpi` （高）
若要 1080p 竖屏（1080×1920），推荐：

bash

```
--fig-width 4.5 --fig-height 8 --dpi 240   # 1080×1920
```



**手机全屏快捷方式**

bash

```
--phone-portrait --phone-short-edge-px 1440   # 1440×2560 竖屏
--phone-landscape --phone-short-edge-px 1080  # 1920×1080 横屏
```



------

## 三、地图底图与瓦片

| 参数                         | 说明                                                         | 默认值           |
| :--------------------------- | :----------------------------------------------------------- | :--------------- |
| `--provider`                 | 瓦片服务商：`gaode`, `esri`, `osm`, `opentopo`, `cyclosm`, `carto`, `tianditu` | `gaode`          |
| `--basemap-style`            | 图层风格（见下详表）                                         | 随 provider 默认 |
| `--carto-style`              | provider=carto 时默认样式                                    | `positron`       |
| `--tianditu-key`             | 天地图 API key（也可用环境变量 `TIANDITU_KEY`）              | 无               |
| `--map-zoom ZOOM`            | 瓦片缩放级别（14~17 常用，过高会慢且字小）                   | 自动             |
| `--gaode-tile-scale 1/2`     | 高德 detail 样式时瓦片像素：1=256，2=512（更清晰）           | 1                |
| `--basemap-interpolation`    | 瓦片插值：`nearest`（锐利）、`bilinear`（平滑）              | `bilinear`       |
| `--basemap-warp-resampling`  | 重采样算法：`nearest`, `bilinear`, `cubic`, `lanczos`        | `bilinear`       |
| `--no-tile-fallback`         | 禁用自动回退其他瓦片源                                       | 不开启           |
| `--no-basemap`               | 不使用在线瓦片（灰底）                                       | 不开启           |
| `--tile-read-timeout SEC`    | 瓦片读取超时（秒）                                           | 180              |
| `--tile-connect-timeout SEC` | 连接超时                                                     | 30               |

**`--basemap-style` 有效值**

| provider | style 示例                                                   |
| :------- | :----------------------------------------------------------- |
| gaode    | `normal`（普通路网）, `detail`（路网详图 style8）, `satellite`（卫星） |
| esri     | `topo`（地形）, `street`（街道）, `imagery`（影像）          |
| carto    | `positron`（浅色）, `dark`（深色）, `voyager`                |
| tianditu | `vec`（矢量）, `img`（影像）, `ter`（地形）, `cia`（注记）   |

**示例**

bash

```
--provider esri --basemap-style imagery --map-zoom 15
--provider gaode --basemap-style detail --gaode-tile-scale 2
```



------

## 四、轨迹路线样式

| 参数                           | 说明                                   | 默认值    |
| :----------------------------- | :------------------------------------- | :-------- |
| `--route-full-color COLOR`     | 整段底轨颜色                           | `#3388ff` |
| `--route-full-width PT`        | 底轨线宽（点）                         | 3.0       |
| `--route-full-alpha A`         | 底轨透明度 0~1                         | 0.35      |
| `--route-progress-color COLOR` | 动画进展线（已跑过段）颜色             | `#e53935` |
| `--route-progress-width PT`    | 进展线宽度                             | 3.5       |
| `--min-point-spacing-m M`      | 轨迹点抽稀最小间距（米），0 表示不抽稀 | 5.0       |
| `--max-route-km KM`            | 只保留从起点起前 KM 公里               | 不限制    |
| `--test-first-km [KM]`         | 仅渲染前 KM 公里（默认 5），用于测试   | 无        |

**示例**

bash

```
--route-full-color gray --route-full-width 2 --route-full-alpha 0.2 \
--route-progress-color red --route-progress-width 4
```



------

## 五、动画与视频编码

| 参数                        | 说明                                   | 默认值   |
| :-------------------------- | :------------------------------------- | :------- |
| `--video-crf N`             | libx264 质量（越小越清晰，18~23 常用） | 18       |
| `--video-bitrate-kbps KBPS` | 固定码率（与 CRF 二选一），如 12000    | 无       |
| `--video-preset`            | 编码速度预设：`ultrafast`~`veryslow`   | `medium` |
| `--no-progress`             | 不显示编码进度条                       | 不开启   |
| `--preview`                 | 仅显示首帧预览（不输出视频）           | 不开启   |
| `--test-image`              | 仅输出一张静态测试图（不生成视频）     | 不开启   |
| `--test-image-out PATH`     | 测试图输出路径                         | 自动     |
| `--test-image-progress P`   | 测试图的进度比例 0~1                   | 0.5      |

**高质量编码**

bash

```
--video-crf 16 --video-preset slower
```



------

## 六、里程桩与标注

| 参数                                                  | 说明                                 | 默认值                  |
| :---------------------------------------------------- | :----------------------------------- | :---------------------- |
| `--km-markers`                                        | 显示里程桩（累积公里）               | 不开启                  |
| `--km-interval KM`                                    | 桩间隔（公里）                       | 1.0                     |
| `--km-include-start`                                  | 在 0 km 处也加桩                     | 不开启                  |
| `--km-format FORMAT`                                  | 标签格式，如 `{km:.1f} km`           | `{km:g} km`             |
| `--km-fontsize`, `--km-fontweight`                    | 字体大小/粗细                        | 11 / bold               |
| `--km-text-color`, `--km-bg-color`                    | 文字/背景颜色                        | `#ffffff` / `#c62828`   |
| `--km-bg-alpha`, `--km-edge-color`, `--km-edge-width` | 背景透明度/边框色/边框宽             | 0.94 / `#ffffff` / 1.35 |
| `--km-boxstyle`                                       | 标签框样式（如 `round,pad=0.4`）     | `round,pad=0.4`         |
| `--km-dot-color`, `--km-dot-size`                     | 桩点颜色/大小                        | `#ffeb3b` / 55          |
| `--km-text-offset-x`, `--km-text-offset-y`            | 标签偏移（点）                       | 0 / 16                  |
| `--km-overrides-json PATH`                            | 高级定制（单独桩样式、隐藏指定桩等） | 无                      |
| `--poi-json PATH`                                     | 景点/地标 JSON 文件                  | 无                      |
| `--poi-coords-default wgs84/gcj02`                    | POI 未声明时的坐标系                 | `wgs84`                 |
| `--route-endpoints-json PATH`                         | 起点/终点标注 JSON                   | 无                      |

**里程桩 JSON 示例**（`--km-overrides-json`）

json

```
{
  "with_interval": true,
  "show_km": [0, 5, 10, 21.0975],
  "hide_km": [1,2,3],
  "overrides": [
    {"km": 21.0975, "text": "半马", "bg": "#1565c0"}
  ]
}
```



**POI JSON 示例**

json

```
[
  {"lon": 116.30, "lat": 39.90, "text": "起点", "coords": "wgs84"},
  {"lon": 116.35, "lat": 39.92, "text": "补给点", "image": "water.png"}
]
```



------

## 七、跟随模式专用参数（`gpx_map_video_follow.py`）

| 参数                  | 说明                                      | 默认值 |
| :-------------------- | :---------------------------------------- | :----- |
| `--follow-half-km KM` | 跟拍窗口半宽度（公里）。视口总宽度≈2×该值 | 1.25   |

**重要**：跟随模式不支持 `--no-basemap`；必须联网拉取瓦片。

**减少抖动建议**

- 增大 `--follow-half-km` 至 2.5~4.0，降低 `--map-zoom` 至 13~14。
- 或修改脚本实现“一次加载全局底图 + 动态裁剪”（见前文方案）。

**示例**

bash

```
python gpx_map_video_follow.py --gpx route.gpx --follow-half-km 3.0 --map-zoom 13 --phone-landscape
```



------

## 八、视频分段与后处理

| 参数                             | 说明                              | 默认值                                 |
| :------------------------------- | :-------------------------------- | :------------------------------------- |
| `--split-video-by-km`            | 按累计公里切分主视频（需 ffmpeg） | 不开启                                 |
| `--split-video-km-step KM`       | 切分步长                          | 1.0                                    |
| `--split-video-out-dir DIR`      | 切分输出目录                      | 主视频同目录下 `主文件名_km_segments/` |
| `--split-video-name-prefix NAME` | 切分文件前缀                      | 主视频主文件名                         |

------

## 九、其他常用参数

| 参数                   | 说明                                                    |
| :--------------------- | :------------------------------------------------------ |
| `--margin-deg DEG`     | 轨迹边界外扩度数（约 0.015°≈1.7 km）                    |
| `--show-lonlat-axis`   | 显示经纬度刻度与边框（默认不显示）                      |
| `--assume-gcj02-track` | 若 GPX 已是 GCJ-02 坐标（高德导出）则启用，避免二次偏移 |
| `--test`               | 快速测试模式（自动缩短路线、时长、降低 zoom）           |

------

## 十、快速参考命令模板

### 全景高清视频（竖屏，无白边）

bash

```
python gpx_map_video.py --gpx your.gpx --phone-portrait --phone-short-edge-px 1440 \
  --margin-deg 0.02 --dpi 240 --map-zoom 15 \
  --provider gaode --basemap-style detail --gaode-tile-scale 2 \
  --video-crf 16 --km-markers --duration 60 --fps 30
```



### 4K 横屏跟随视频（与全景拼接用）

bash

```
python gpx_map_video_follow.py --gpx your.gpx \
  --fig-width 11.5 --fig-height 9.0 --dpi 240 \
  --follow-half-km 3.0 --map-zoom 13 \
  --provider esri --basemap-style imagery \
  --duration 60 --fps 30 --out follow.mp4
```



### 仅生成测试图检查布局

bash

```
python gpx_map_video.py --gpx your.gpx --test-image --test-image-progress 0.5 \
  --fig-width 4.5 --fig-height 8 --dpi 120
```



------

## 十一、常见问题速查

| 问题         | 解决办法                                                     |
| :----------- | :----------------------------------------------------------- |
| 视频有白边   | 增大 `--margin-deg`，或使用 `--fill-figure-aspect`，或手动匹配画布比例 |
| 文字模糊     | 提高 `--dpi`，使用 `--basemap-interpolation nearest`，高德 detail 加 `--gaode-tile-scale 2` |
| 跟随模式抖动 | 增大 `--follow-half-km` 并降低 `--map-zoom`，或改用“一次加载底图+动态裁剪” |
| 渲染极慢     | 降低 `--fps`、`--duration`、`--map-zoom`；避免每帧重绘底图   |
| 瓦片加载失败 | 去掉 `--no-tile-fallback`，或换用 `--provider esri`，或检查网络 |