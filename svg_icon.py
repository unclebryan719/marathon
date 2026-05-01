import svgwrite


def combine_svg_icons(icon_files, positions, output_svg):
    """
    icon_files: 列表，SVG 文件路径
    positions: 列表，每个图标的位置和大小，例如 (x, y, width, height)
    output_svg: 输出的 SVG 文件名
    """
    # 计算画布大小（根据所有图标的边界）
    max_x = max(pos[0] + pos[2] for pos in positions)
    max_y = max(pos[1] + pos[3] for pos in positions)

    dwg = svgwrite.Drawing(output_svg, size=(max_x, max_y))
    dwg.viewbox(width=max_x, height=max_y)

    for icon_path, (x, y, w, h) in zip(icon_files, positions):
        # 将外部 SVG 作为 symbol 嵌入，或直接使用 <image> 方式
        # 推荐方法：先读取 SVG 内容，用 use 标签引用
        dwg.add(dwg.image(href=icon_path, insert=(x, y), size=(w, h)))

    dwg.save()


# 使用示例
icons = ["water.svg", "heart-pulse-solid-full.svg"]
positions = [(10, 10, 100, 100), (120, 10, 100, 100), (230, 10, 100, 100)]
combine_svg_icons(icons, positions, "output.svg")