from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ssdm" / "assets"
PNG = ASSETS / "SsDownloadManager.png"
ICO = ROOT / "dist" / "SsDownloadManager.ico"
ASSETS.mkdir(parents=True, exist_ok=True)
ICO.parent.mkdir(parents=True, exist_ok=True)

size = 512
im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
pixels = im.load()
for y in range(size):
    for x in range(size):
        t = (x + y) / (2 * size)
        shade = int(10 + 18 * (1 - t))
        pixels[x, y] = (shade, shade, shade + 2, 255)

mask = Image.new("L", (size, size), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle((12, 12, 500, 500), radius=82, fill=255)
im.putalpha(mask)
draw = ImageDraw.Draw(im)
draw.rounded_rectangle((13, 13, 499, 499), radius=82, outline=(224, 231, 241, 255), width=7)
draw.arc((62, 54, 450, 442), 195, 340, fill=(220, 226, 236, 235), width=12)
for y, x1, x2 in [(115, 65, 205), (140, 48, 150), (390, 60, 130)]:
    draw.line((x1, y, x2, y), fill=(190, 199, 211, 180), width=6)

font_path = Path("C:/Windows/Fonts/arialbd.ttf")
if not font_path.exists():
    font_path = Path("C:/Windows/Fonts/Arial.ttf")
def font(sz):
    try:
        return ImageFont.truetype(str(font_path), sz)
    except OSError:
        return ImageFont.load_default()

# Large chrome SS lettering with a dark offset for depth.
ss_font = font(178)
draw.text((50, 102), "SS", font=ss_font, fill=(5, 5, 7, 255), stroke_width=8, stroke_fill=(5, 5, 7, 255))
draw.text((44, 94), "SS", font=ss_font, fill=(235, 239, 246, 255), stroke_width=2, stroke_fill=(125, 134, 148, 255))

# Download arrow and tray.
draw.line((344, 220, 344, 322), fill=(235, 239, 246, 255), width=24)
draw.polygon([(296, 292), (344, 342), (392, 292)], fill=(226, 232, 241, 255))
draw.rounded_rectangle((288, 350, 400, 388), radius=15, outline=(228, 234, 243, 255), width=15)
draw.line((62, 414, 450, 414), fill=(170, 180, 194, 190), width=3)

title_font = font(33)
title = "Ss Download Manager"
bbox = draw.textbbox((0, 0), title, font=title_font)
while bbox[2] - bbox[0] > 440:
    title_font = font(title_font.size - 1)
    bbox = draw.textbbox((0, 0), title, font=title_font)
draw.text(((size - (bbox[2] - bbox[0])) / 2, 432), title, font=title_font,
          fill=(239, 242, 248, 255), stroke_width=1, stroke_fill=(70, 77, 88, 255))

# Subtle highlight and final export.
im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=3))
im.save(PNG, optimize=True)
im.save(ICO, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Generated {PNG} and {ICO}")
