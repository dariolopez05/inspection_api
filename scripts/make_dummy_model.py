"""Genera un .h5 SIN entrenar para validar el pipeline de Fase 3.
Sustituir por un modelo real con misma entrada (224,224,3) y salida sigmoid."""

from tensorflow import keras
from tensorflow.keras import layers

model = keras.Sequential(
    [
        keras.Input(shape=(224, 224, 3)),
        layers.Conv2D(8, 3, activation="relu"),
        layers.GlobalAveragePooling2D(),
        layers.Dense(1, activation="sigmoid"),
    ]
)
model.compile(optimizer="adam", loss="binary_crossentropy")
model.save("models/damage_classifier.h5")
print("Modelo dummy guardado en models/damage_classifier.h5")
