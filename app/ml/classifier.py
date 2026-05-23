from pathlib import Path

import numpy as np
from tensorflow import keras


def load_classifier(model_path: str | Path) -> keras.Model:
    return keras.models.load_model(model_path)


def predict(model: keras.Model, tensor: np.ndarray) -> tuple[bool, float]:
    probability = float(model.predict(tensor, verbose=0)[0][0])  # sigmoid = P(danado)
    is_damaged = probability >= 0.5
    confidence = probability if is_damaged else 1.0 - probability
    return is_damaged, round(confidence, 4)
