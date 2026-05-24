"""Reorganiza el dataset anujms (data/raw/{training,validation}/{00-damage,01-whole})
al layout que espera train.py: data/{train,val}/{damaged,intact}/.
Limpia los destinos antes de copiar (elimina datos sinteticos previos)."""

import shutil
from pathlib import Path

RAW = Path("data/raw")
EXTS = {".jpg", ".jpeg", ".png"}
MAPPING = {
    ("training", "00-damage"): ("train", "damaged"),
    ("training", "01-whole"): ("train", "intact"),
    ("validation", "00-damage"): ("val", "damaged"),
    ("validation", "01-whole"): ("val", "intact"),
}


def main() -> None:
    for (src_split, src_cls), (dst_split, dst_cls) in MAPPING.items():
        src = RAW / src_split / src_cls
        dst = Path("data") / dst_split / dst_cls
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in src.iterdir():
            if f.suffix.lower() in EXTS:
                shutil.copy2(f, dst / f.name)
                count += 1
        print(f"{src} -> {dst}: {count} imagenes")


if __name__ == "__main__":
    main()
