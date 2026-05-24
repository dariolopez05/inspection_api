"""Dataset SINTETICO minusculo (formas geometricas) para validar el pipeline de
entrenamiento end-to-end. NO sirve para un modelo util: sustituir por fotos reales
en data/{train,val}/{damaged,intact}/."""

import random
from pathlib import Path

from PIL import Image, ImageDraw

IMAGE_SIZE = (224, 224)
PER_CLASS = {"train": 40, "val": 10}


def make_image(damaged: bool) -> Image.Image:
    img = Image.new("RGB", IMAGE_SIZE, (200, 200, 210))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 90, 184, 150], fill=(90, 90, 100))
    if damaged:
        for _ in range(8):
            x1, y1 = random.randint(40, 184), random.randint(90, 150)
            x2, y2 = x1 + random.randint(-20, 20), y1 + random.randint(-20, 20)
            draw.line([x1, y1, x2, y2], fill=(200, 30, 30), width=2)
    return img


def main() -> None:
    for subset, count in PER_CLASS.items():
        for label, damaged in (("intact", False), ("damaged", True)):
            out = Path("data") / subset / label
            out.mkdir(parents=True, exist_ok=True)
            for i in range(count):
                make_image(damaged).save(out / f"{i}.jpg")
    print("Dataset sintetico generado en data/{train,val}/{damaged,intact}/")


if __name__ == "__main__":
    main()
