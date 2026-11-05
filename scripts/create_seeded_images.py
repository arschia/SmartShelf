from pathlib import Path
from PIL import Image, ImageDraw

p = Path(__file__).resolve().parent.parent / "frontend" / "static" / "images"
p.mkdir(parents=True, exist_ok=True)

# PROD-001 (Chocolate Milk)
img1 = Image.new("RGB", (250, 250), color=(180, 100, 50))
d1 = ImageDraw.Draw(img1)
d1.rectangle([40, 40, 210, 210], outline=(255, 255, 255), width=4)
d1.text((50, 100), "Chocolate Milk", fill=(255, 255, 255))
img1.save(p / "chocolate_milk.png")

# PROD-002 (Water)
img2 = Image.new("RGB", (250, 250), color=(50, 150, 240))
d2 = ImageDraw.Draw(img2)
d2.rectangle([40, 40, 210, 210], outline=(255, 255, 255), width=4)
d2.text((80, 100), "Mineral Water", fill=(255, 255, 255))
img2.save(p / "water.png")

# PROD-003 (Biscuit)
img3 = Image.new("RGB", (250, 250), color=(220, 180, 60))
d3 = ImageDraw.Draw(img3)
d3.rectangle([40, 40, 210, 210], outline=(255, 255, 255), width=4)
d3.text((60, 100), "Choco Biscuit", fill=(255, 255, 255))
img3.save(p / "biscuit.png")

print(f"Seeded product images saved to: {p}")
