"""Render Rova Horizon from original geometric curves, without external artwork.

Requires Pillow. Writes an editable SVG and a 3840x2160 PNG.
"""
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = (3840, 2160)
VIEW = (1920, 1080)
# Each contour is a start point followed by cubic Bezier control/end points.
LAYERS = [
    ('distance', (114, 132, 163), (41, 73, 96), (0, 745),
     [(520, 785, 845, 660, 1170, 626), (1490, 590, 1710, 627, 1920, 546)]),
    ('mist', (92, 151, 162), (28, 76, 96), (0, 725),
     [(375, 611, 680, 697, 1030, 758), (1400, 822, 1670, 644, 1920, 652)]),
    ('sweep', (50, 128, 139), (16, 49, 69), (0, 570),
     [(360, 590, 448, 804, 938, 846), (1320, 880, 1615, 716, 1920, 779)]),
    ('foreground', (22, 70, 86), (9, 24, 40), (0, 763),
     [(260, 713, 485, 876, 792, 942), (1150, 1020, 1595, 878, 1920, 905)]),
]


def contour(start, curves, steps=192):
    points = [start]
    x0, y0 = start
    for x1, y1, x2, y2, x3, y3 in curves:
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            points.append((u**3*x0 + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
                           u**3*y0 + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3))
        x0, y0 = x3, y3
    return points


def gradient(size, top, bottom, start=0, end=1080):
    image = Image.new('RGB', size)
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        t = max(0, min(1, (y * VIEW[1] / size[1] - start) / (end - start)))
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line((0, y, size[0], y), fill=color)
    return image


def hex_color(color):
    return '#' + ''.join(f'{channel:02x}' for channel in color)


def svg():
    definitions = [
        '<linearGradient id="sky" x2="0" y2="1">'
        '<stop stop-color="#0c1c2c"/><stop offset=".55" stop-color="#263e58"/>'
        '<stop offset="1" stop-color="#a2a0b5"/></linearGradient>',
        '<radialGradient id="haze" cx=".77" cy=".57" r=".58">'
        '<stop stop-color="#b4a2bd" stop-opacity=".24"/>'
        '<stop offset="1" stop-color="#b4a2bd" stop-opacity="0"/></radialGradient>',
    ]
    paths = []
    for name, top, bottom, start, curves in LAYERS:
        definitions.append(
            f'<linearGradient id="{name}" gradientUnits="userSpaceOnUse" '
            f'x1="0" y1="{start[1]}" x2="0" y2="1080">'
            f'<stop stop-color="{hex_color(top)}"/>'
            f'<stop offset="1" stop-color="{hex_color(bottom)}"/></linearGradient>')
        d = f'M {start[0]} {start[1]} ' + ' '.join(
            'C ' + ' '.join(str(value) for value in curve) for curve in curves)
        paths.append(f'<path d="{d} L 1920 1080 L 0 1080 Z" fill="url(#{name})"/>')
    description = escape('Original geometric wallpaper created for RovaOS. '
                         'Editable curves and gradients; no third-party image assets.')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" '
        'viewBox="0 0 1920 1080">\n'
        '<title>Rova Horizon</title>\n'
        f'<desc>{description}</desc>\n'
        '<defs>' + ''.join(definitions) + '</defs>\n'
        '<rect width="1920" height="1080" fill="url(#sky)"/>\n'
        '<rect width="1920" height="1080" fill="url(#haze)"/>\n'
        + '\n'.join(paths) + '\n</svg>\n')


def render():
    # Render the sky at reduced resolution for a smooth, elliptical horizon glow.
    small = (960, 540)
    sky = Image.new('RGB', small)
    pixels = sky.load()
    stops = [(0, (12, 28, 44)), (.55, (38, 62, 88)), (1, (162, 160, 181))]
    for y in range(small[1]):
        v = y / (small[1] - 1)
        a, b = (stops[0], stops[1]) if v <= .55 else (stops[1], stops[2])
        t = (v - a[0]) / (b[0] - a[0])
        base = tuple(c + (d - c) * t for c, d in zip(a[1], b[1]))
        for x in range(small[0]):
            u = x / (small[0] - 1)
            radius = (((u - .77) / .58)**2 + ((v - .57) / (1.78 * .58))**2)**.5
            alpha = .24 * max(0, 1 - radius)
            pixels[x, y] = tuple(round(c * (1 - alpha) + d * alpha)
                                 for c, d in zip(base, (180, 162, 189)))
    image = sky.resize(SIZE, Image.Resampling.BICUBIC)
    scale = SIZE[0] / VIEW[0]
    for _, top, bottom, start, curves in LAYERS:
        points = contour(start, curves) + [(1920, 1080), (0, 1080)]
        mask = Image.new('L', SIZE)
        ImageDraw.Draw(mask).polygon([(round(x*scale), round(y*scale)) for x, y in points], fill=255)
        image.paste(gradient(SIZE, top, bottom, start[1]), (0, 0), mask)
    return image


if __name__ == '__main__':
    destination = ROOT/'assets/wallpapers'
    (destination/'rova-horizon.svg').write_text(svg(), encoding='utf-8')
    render().save(destination/'rova-horizon.png', optimize=True)
    print('Created Rova Horizon: editable SVG and 3840x2160 PNG.')
