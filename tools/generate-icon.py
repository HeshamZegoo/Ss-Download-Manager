from pathlib import Path
import cairosvg
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
svg = ROOT / "ssdm" / "assets" / "SsDownloadManager.svg"
png = ROOT / "ssdm" / "assets" / "SsDownloadManager.png"
ico = ROOT / "dist" / "SsDownloadManager.ico"
png.parent.mkdir(parents=True, exist_ok=True)
ico.parent.mkdir(parents=True, exist_ok=True)
cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=512, output_height=512)
image = Image.open(png).convert("RGBA")
image.save(ico, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(f"Generated {png} and {ico}")
