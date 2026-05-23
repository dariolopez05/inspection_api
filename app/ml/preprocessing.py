import io

import numpy as np
from PIL import Image

IMAGE_SIZE = (224, 224)


def preprocess_image(raw: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(raw)) as img:
        rgb = img.convert("RGB").resize(IMAGE_SIZE)
        array = np.asarray(rgb, dtype=np.float32) / 255.0
    return np.expand_dims(array, axis=0)
