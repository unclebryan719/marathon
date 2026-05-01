#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import platform
from PIL import Image, ImageDraw, ImageFont
import cairosvg

# ========================== 全局默认配置 ==========================
DEFAULT_ICON_SIZE = 48
DEFAULT_FONT_SIZE = 20
DEFAULT_TEXT_COLOR = "black"
DEFAULT_TEXT_STROKE = None
DEFAULT_TEXT_SHADOW = None
DEFAULT_TEXT_GRADIENT = None
MARGIN = 20
H_SPACING = 12
V_SPACING = 12

# ======================= 预定义文本样式库 ========================
TEXT_STYLES = {
    'title': {'color': '#FFFFFF', 'stroke': {'width': 2, 'color': '#000000'}, 'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 76)}, 'gradient': None},
    'neon': {'color': '#00FFCC', 'stroke': {'width': 1, 'color': '#00FFCC'}, 'shadow': {'offset': (0, 0), 'color': '#00FFCC'}, 'gradient': None},
    'metal': {'color': None, 'stroke': {'width': 1, 'color': '#AAAAAA'}, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 51)}, 'gradient': {'colors': ['#E0E0E0', '#808080'], 'direction': 'vertical'}},
    'candy': {'color': None, 'stroke': {'width': 2, 'color': '#FFFFFF'}, 'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 25)}, 'gradient': {'colors': ['#FFB6C1', '#FF69B4'], 'direction': 'horizontal'}},
    'vintage': {'color': '#4A3B32', 'stroke': None, 'shadow': {'offset': (1, 1), 'color': '#D2B48C'}, 'gradient': None},
    'highlight': {'color': '#FFFFFF', 'stroke': {'width': 2, 'color': '#FF0000'}, 'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 127)}, 'gradient': None},
    'soft_cream': {'color': None, 'stroke': None, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 30)}, 'gradient': {'colors': ['#FDFBF7', '#F4EADB'], 'direction': 'vertical'}},
    'watercolor': {'color': None, 'stroke': {'width': 1, 'color': 'rgba(255,255,255,0.5)'}, 'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 20)}, 'gradient': {'colors': ['#C5E4FF', '#E0D4FF'], 'direction': 'horizontal'}},
    'morandi_pink': {'color': '#D9B8C4', 'stroke': None, 'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 20)}, 'gradient': None},
    'amber_glow': {'color': None, 'stroke': None, 'shadow': {'offset': (0, 2), 'color': (255, 200, 100, 50)}, 'gradient': {'colors': ['#FFE6C7', '#FFCC99'], 'direction': 'vertical'}},
    'glass': {'color': '#FFFFFF', 'stroke': {'width': 1, 'color': 'rgba(255,255,255,0.6)'}, 'shadow': {'offset': (0, 2), 'color': (200, 200, 200, 30)}, 'gradient': None},
    'macaron_mint': {'color': '#A8E6CF', 'stroke': None, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 15)}, 'gradient': None},
    'macaron_peach': {'color': '#FFD3B6', 'stroke': None, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 15)}, 'gradient': None},
    'macaron_lavender': {'color': '#C7CEE6', 'stroke': None, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 20)}, 'gradient': None},
'macaron_butter_bold': {
    'color': '#FFEAA7',
    'stroke': {'width': 1, 'color': '#FFEAA7'},
    'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 15)},
    'gradient': None
},
'highlight_bold': {
    'color': '#FFFFFF',
    'stroke': {'width': 2, 'color': '#FF0000'},
    'shadow': {'offset': (2, 2), 'color': (0, 0, 0, 127)},
    'gradient': None
},
    'macaron_butter': {'color': '#FFEAA7', 'stroke': None, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 12)}, 'gradient': None},
    'macaron_gradient': {'color': None, 'stroke': {'width': 1, 'color': 'rgba(255,255,255,0.4)'}, 'shadow': {'offset': (1, 1), 'color': (0, 0, 0, 15)}, 'gradient': {'colors': ['#FFB7B2', '#E2F0CB', '#B5E3D5'], 'direction': 'horizontal'}}
}


def _get_system_fonts():
    system = platform.system()
    if system == 'Windows':
        return ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
    elif system == 'Darwin':
        return ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]
    else:
        return ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]


def _load_font(font_size, font_path=None):
    candidates = []
    if font_path:
        candidates.append(font_path)
    candidates.extend(_get_system_fonts())
    for p in candidates:
        try:
            return ImageFont.truetype(p, font_size)
        except Exception:
            continue
    raise RuntimeError("未找到任何可用的中文字体，请通过 font_path 指定正确的字体文件路径")


def _apply_gradient(img, colors, direction='vertical'):
    w, h = img.size
    grad = Image.new('RGBA', (w, h))
    c1 = colors[0].lstrip('#')
    c2 = colors[1].lstrip('#')
    r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
    r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
    for y in range(h):
        for x in range(w):
            ratio = y / h if direction == 'vertical' else x / w
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            a = img.getpixel((x, y))[3]
            grad.putpixel((x, y), (r, g, b, a))
    img.paste(grad, (0, 0), grad)


def _render_text(text, font_size, font_path, color, stroke, shadow, gradient):
    font = _load_font(font_size, font_path)
    bbox = font.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    sw = stroke['width'] if stroke else 0
    sdx, sdy = shadow['offset'] if shadow else (0, 0)
    pad = max(sw, abs(sdx), abs(sdy)) + 2
    img = Image.new('RGBA', (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x, y = pad, pad

    if shadow:
        draw.text((x + sdx, y + sdy), text, font=font, fill=shadow.get('color', 'gray'))
    if stroke:
        sw_ = stroke['width']
        for dx in range(-sw_, sw_ + 1):
            for dy in range(-sw_, sw_ + 1):
                if dx == 0 and dy == 0:
                    continue
                if dx * dx + dy * dy <= sw_ * sw_:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke['color'])
    if color is not None:
        draw.text((x, y), text, font=font, fill=color)
    else:
        draw.text((x, y), text, font=font, fill='white')
    if gradient and 'colors' in gradient:
        _apply_gradient(img, gradient['colors'], gradient.get('direction', 'vertical'))
    return img.crop(img.getbbox())


def _load_icon(path, height):
    try:
        png_data = cairosvg.svg2png(url=path, output_height=height)
        return Image.open(io.BytesIO(png_data)).convert('RGBA')
    except Exception as e:
        print(f"加载图标失败 {path}: {e}")
        return Image.new('RGBA', (height, height), (255, 0, 0, 128))


def _parse_element(item, icons_dir, def_icon_sz, def_font_sz, text_style, font_path):
    if isinstance(item, str):
        if item.lower().endswith('.svg'):
            img = _load_icon(os.path.join(icons_dir, item), def_icon_sz)
            return {'type': 'icon', 'content': img, 'width': img.width, 'height': img.height, 'dx': 0, 'dy': 0}
        else:
            img = _render_text(item, def_font_sz, font_path,
                               text_style.get('color', DEFAULT_TEXT_COLOR),
                               text_style.get('stroke', DEFAULT_TEXT_STROKE),
                               text_style.get('shadow', DEFAULT_TEXT_SHADOW),
                               text_style.get('gradient', DEFAULT_TEXT_GRADIENT))
            return {'type': 'icon', 'content': img, 'width': img.width, 'height': img.height, 'dx': 0, 'dy': 0}
    elif isinstance(item, dict):
        if 'file' in item:
            height = item.get('height', def_icon_sz)
            img = _load_icon(os.path.join(icons_dir, item['file']), height)
            w = item.get('width', img.width)
            if w != img.width:
                img = img.resize((w, img.height), Image.Resampling.LANCZOS)
            return {
                'type': 'icon',
                'content': img,
                'width': img.width,
                'height': img.height,
                'dx': item.get('dx', 0),
                'dy': item.get('dy', 0)
            }
        elif 'text' in item:
            style = text_style.copy()
            style.update(item.get('style', {}))
            font_sz = item.get('font_size', def_font_sz)
            img = _render_text(item['text'], font_sz, font_path,
                               style.get('color', DEFAULT_TEXT_COLOR),
                               style.get('stroke', DEFAULT_TEXT_STROKE),
                               style.get('shadow', DEFAULT_TEXT_SHADOW),
                               style.get('gradient', DEFAULT_TEXT_GRADIENT))
            w = item.get('width', img.width)
            if w != img.width:
                img = img.resize((w, img.height), Image.Resampling.LANCZOS)
            return {
                'type': 'icon',
                'content': img,
                'width': img.width,
                'height': img.height,
                'dx': item.get('dx', 0),
                'dy': item.get('dy', 0)
            }
        else:
            raise ValueError(f"无效字典：缺少 'file' 或 'text' 键，内容：{item}")
    else:
        raise TypeError(f"不支持的元素类型: {type(item)}，值：{item}")


def _normalize_desc(desc):
    if not isinstance(desc, list):
        desc = [desc]
    if all(isinstance(row, list) for row in desc):
        return desc
    return [desc]


def _layout_and_render(desc, icons_dir, def_icon_sz, def_font_sz, text_style,
                       margin, h_spacing, v_spacing, font_path):
    normalized_rows = _normalize_desc(desc)
    rows_info = []

    for line in normalized_rows:
        if not line:
            continue
        if isinstance(line[0], dict):
            config = line[0]
            items = line[1:]
        else:
            config = {}
            items = line

        icon_sz = config.get('icon_size', def_icon_sz)
        font_sz = config.get('font_size', def_font_sz)
        h_sp = config.get('h_spacing', h_spacing)
        v_sp = config.get('v_spacing', v_spacing)
        border = config.get('border')
        background_color = config.get('background_color')
        row_text_style = text_style.copy()
        row_text_style.update(config.get('text_style', {}))

        elements = []
        max_height = 0
        total_width = 0
        for it in items:
            elem = _parse_element(it, icons_dir, icon_sz, font_sz, row_text_style, font_path)
            elements.append(elem)
            max_height = max(max_height, elem['height'])
            total_width += elem['width']
        if len(elements) > 1:
            total_width += (len(elements) - 1) * h_sp

        pad_x = pad_y = 0
        border_width = 0
        if border:
            border_width = border.get('width', 2)
            pad = border.get('padding', 0)
            pad_x = border_width + pad
            pad_y = border_width + pad

        rows_info.append({
            'elements': elements,
            'content_height': max_height,
            'content_width': total_width,
            'total_height': max_height + 2 * pad_y,
            'total_width': total_width + 2 * pad_x,
            'h_spacing': h_sp,
            'v_spacing': v_sp,
            'border': border,
            'border_width': border_width,
            'pad_x': pad_x,
            'pad_y': pad_y,
            'background_color': background_color
        })

    if not rows_info:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))

    canvas_width = max(r['total_width'] for r in rows_info) + 2 * margin
    canvas_height = sum(r['total_height'] for r in rows_info) + sum(r['v_spacing'] for r in rows_info[:-1]) + 2 * margin
    canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    y_offset = margin
    for row in rows_info:
        start_x = margin + (canvas_width - 2 * margin - row['total_width']) // 2
        inner_x = start_x + row['pad_x']
        inner_y = y_offset + row['pad_y']
        x = inner_x

        # 合并背景与边框：如果有背景色或有边框，直接绘制圆角矩形（填充+描边）
        if row['background_color'] or row['border']:
            rect = [start_x, y_offset, start_x + row['total_width'], y_offset + row['total_height']]
            radius = row['border'].get('radius', 0) if row['border'] else 0
            fill_color = row['background_color'] if row['background_color'] else None
            outline_color = row['border']['color'] if row['border'] else None
            outline_width = row['border']['width'] if row['border'] else 0
            if radius > 0:
                draw.rounded_rectangle(rect, radius=radius, fill=fill_color, outline=outline_color, width=outline_width)
            else:
                draw.rectangle(rect, fill=fill_color, outline=outline_color, width=outline_width)

        # 绘制行内元素
        for elem in row['elements']:
            y = inner_y + (row['content_height'] - elem['height']) // 2 + elem['dy']
            canvas.alpha_composite(elem['content'], (x + elem['dx'], y))
            x += elem['width'] + row['h_spacing']

        y_offset += row['total_height'] + row['v_spacing']

    return canvas


def generate_images(descriptions, icons_dir, output_dir,
                    default_icon_size=DEFAULT_ICON_SIZE,
                    default_font_size=DEFAULT_FONT_SIZE,
                    default_text_color=DEFAULT_TEXT_COLOR,
                    default_text_stroke=DEFAULT_TEXT_STROKE,
                    default_text_shadow=DEFAULT_TEXT_SHADOW,
                    default_text_gradient=DEFAULT_TEXT_GRADIENT,
                    margin=MARGIN, h_spacing=H_SPACING, v_spacing=V_SPACING,
                    font_path=None, text_style_name=None):
    os.makedirs(output_dir, exist_ok=True)

    if font_path is None:
        sys_fonts = _get_system_fonts()
        if sys_fonts:
            font_path = sys_fonts[0]
        else:
            raise RuntimeError("无法找到系统字体，请通过 font_path 指定字体文件路径")

    if text_style_name and text_style_name in TEXT_STYLES:
        base = TEXT_STYLES[text_style_name].copy()
        if default_text_color != DEFAULT_TEXT_COLOR:
            base['color'] = default_text_color
        if default_text_stroke != DEFAULT_TEXT_STROKE:
            base['stroke'] = default_text_stroke
        if default_text_shadow != DEFAULT_TEXT_SHADOW:
            base['shadow'] = default_text_shadow
        if default_text_gradient != DEFAULT_TEXT_GRADIENT:
            base['gradient'] = default_text_gradient
        text_style = {
            'color': base.get('color', DEFAULT_TEXT_COLOR),
            'stroke': base.get('stroke', DEFAULT_TEXT_STROKE),
            'shadow': base.get('shadow', DEFAULT_TEXT_SHADOW),
            'gradient': base.get('gradient', DEFAULT_TEXT_GRADIENT)
        }
    else:
        text_style = {
            'color': default_text_color,
            'stroke': default_text_stroke,
            'shadow': default_text_shadow,
            'gradient': default_text_gradient
        }

    generated_files = []
    for idx, desc in enumerate(descriptions):
        img = _layout_and_render(desc, icons_dir,
                                 default_icon_size, default_font_size,
                                 text_style, margin, h_spacing, v_spacing,
                                 font_path)
        out_path = os.path.join(output_dir, f'output_{idx + 1}.png')
        img.save(out_path, 'PNG')
        generated_files.append(out_path)
        print(f"已生成: {out_path}")

    return generated_files


if __name__ == '__main__':
    ICONS_DIR = './assert'
    OUTPUT_DIR = './output_images'

    pictures = [
        [
            [
                {
                    'icon_size': 30,
                    'font_size': 32,
                    'h_spacing': 10,
                    'v_spacing': 30,
                    'background_color': 'white',
                    'border': {'color': 'white', 'width': 3, 'radius': 20, 'padding': 8},
                    'text_style': TEXT_STYLES['macaron_butter_bold']
                },
                'map-pin.svg', '5km', 'clock.svg', '55分钟'
            ],
            [
                {
                    'icon_size': 60,
                    'font_size': 24,
                    'background_color': 'white',
                    'border': {'color': 'white', 'width': 3, 'radius': 20, 'padding': 8},
                },
                'drink.svg', 'water.svg'
            ]
        ]
    ]

    generate_images(pictures, ICONS_DIR, OUTPUT_DIR,
                    default_icon_size=48,
                    default_font_size=20,
                    h_spacing=12, v_spacing=12,
                    text_style_name='highlight')