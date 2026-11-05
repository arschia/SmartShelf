from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

base = Path(__file__).resolve().parent.parent / "ai" / "evaluation" / "sample_dataset"
for sub in ["PROD-001", "PROD-002", "PROD-003", "unknown"]:
    (base / sub).mkdir(parents=True, exist_ok=True)

# 1. Unknown random images
for i in range(5):
    img = Image.new("RGB", (250, 250), color=(int(np.random.randint(0, 255)), int(np.random.randint(0, 255)), int(np.random.randint(0, 255))))
    d = ImageDraw.Draw(img)
    d.polygon([(20, 20), (180, 50), (100, 200)], fill=(int(np.random.randint(0, 255)), int(np.random.randint(0, 255)), int(np.random.randint(0, 255))))
    img.save(base / "unknown" / f"unknown_{i+1}.jpg")

# 2. Known products images
products_map = {
    "PROD-001": (180, 100, 50),
    "PROD-002": (50, 150, 240),
    "PROD-003": (220, 180, 60),
}
for sku, color in products_map.items():
    for i in range(5):
        jitter = np.random.randint(-15, 15, 3)
        c = tuple(int(np.clip(color[k] + jitter[k], 0, 255)) for k in range(3))
        img = Image.new("RGB", (250, 250), color=c)
        d = ImageDraw.Draw(img)
        d.rectangle([50, 50, 200, 200], outline=(255, 255, 255), width=3)
        img.save(base / sku / f"{sku}_test_{i+1}.jpg")

print(f"Sample dataset ready at: {base}")
