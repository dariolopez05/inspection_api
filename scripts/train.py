"""Entrenamiento por transfer learning (MobileNetV2) del clasificador de danos.

Dataset esperado:
    data/train/{damaged,intact}/*.jpg
    data/val/{damaged,intact}/*.jpg

Convencion: sigmoid = P(danado). Fijamos damaged=1 con class_names.
El modelo espera entrada [0,1] (igual que el backend) y reescala a [-1,1] para MobileNetV2.

Dos fases: (1) backbone congelado, (2) fine-tuning de las ultimas capas con LR bajo.
Incluye data augmentation, EarlyStopping + ModelCheckpoint (guarda la mejor epoca) y
reporte precision/recall/F1 + matriz de confusion. Exporta models/damage_classifier.h5.
Epocas/capas configurables por env: EPOCHS_HEAD, EPOCHS_FINETUNE, FINE_TUNE_AT.
"""

import os
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

DATA_DIR = Path("data")
IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS_HEAD = int(os.getenv("EPOCHS_HEAD", "15"))
EPOCHS_FINETUNE = int(os.getenv("EPOCHS_FINETUNE", "0"))  # empiricamente degrada este dataset; activar con env
FINE_TUNE_AT = int(os.getenv("FINE_TUNE_AT", "100"))
CLASS_NAMES = ["intact", "damaged"]  # intact=0, damaged=1 -> sigmoid = P(danado)
OUTPUT = "models/damage_classifier.h5"
AUTOTUNE = tf.data.AUTOTUNE

augmenter = keras.Sequential(
    [
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.05),
        layers.RandomBrightness(0.1, value_range=(0, 255)),
    ],
    name="augment",
)


def make_dataset(subset: str, *, shuffle: bool, augment: bool) -> tf.data.Dataset:
    ds = keras.utils.image_dataset_from_directory(
        DATA_DIR / subset,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        image_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=shuffle,
    )
    if augment:
        ds = ds.map(lambda x, y: (augmenter(x, training=True), y), num_parallel_calls=AUTOTUNE)
    return ds.map(lambda x, y: (x / 255.0, y), num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)


def build_model() -> tuple[keras.Model, keras.Model]:
    base = MobileNetV2(input_shape=(*IMAGE_SIZE, 3), include_top=False, weights="imagenet")
    base.trainable = False
    inputs = keras.Input(shape=(*IMAGE_SIZE, 3))
    x = layers.Rescaling(2.0, offset=-1.0)(inputs)  # [0,1] -> [-1,1]
    x = base(x, training=False)  # BatchNorm siempre en modo inferencia
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(inputs, outputs), base


def compile_model(model: keras.Model, lr: float) -> None:
    model.compile(
        optimizer=keras.optimizers.Adam(lr),
        loss="binary_crossentropy",
        metrics=[
            keras.metrics.BinaryAccuracy(name="accuracy"),
            keras.metrics.Precision(name="precision"),
            keras.metrics.Recall(name="recall"),
        ],
    )


def report(model: keras.Model, val_ds: tf.data.Dataset) -> None:
    y_true = np.concatenate([y.numpy() for _, y in val_ds]).ravel().astype(int)
    y_prob = model.predict(val_ds, verbose=0).ravel()
    y_pred = (y_prob >= 0.5).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print("\n=== Matriz de confusion (positivo = danado) ===")
    print("                 pred_intacto  pred_danado")
    print(f"real_intacto         {tn:5d}        {fp:5d}")
    print(f"real_danado          {fn:5d}        {tp:5d}")
    print(f"\nprecision={precision:.4f}  recall={recall:.4f}  f1={f1:.4f}")
    print(f"(recall = % de danos detectados; FN={fn} danos NO detectados)")


def main() -> None:
    Path("models").mkdir(exist_ok=True)
    train_ds = make_dataset("train", shuffle=True, augment=True)
    val_ds = make_dataset("val", shuffle=False, augment=False)

    model, base = build_model()

    print(">>> Fase 1: backbone congelado (LR 1e-3)")
    compile_model(model, 1e-3)
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS_HEAD,
        callbacks=[
            EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True),
            ModelCheckpoint(OUTPUT, monitor="val_loss", save_best_only=True),
        ],
    )
    best_val_loss = min(history.history["val_loss"])

    if EPOCHS_FINETUNE > 0:
        print(f">>> Fase 2: fine-tuning desde capa {FINE_TUNE_AT} (LR 1e-5)")
        base.trainable = True
        for layer in base.layers[:FINE_TUNE_AT]:
            layer.trainable = False
        compile_model(model, 1e-5)
        model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=EPOCHS_FINETUNE,
            callbacks=[
                EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True),
                # solo sobreescribe si la fase 2 mejora el val_loss de la fase 1
                ModelCheckpoint(
                    OUTPUT,
                    monitor="val_loss",
                    save_best_only=True,
                    initial_value_threshold=best_val_loss,
                ),
            ],
        )

    best = keras.models.load_model(OUTPUT)  # mejor de ambas fases
    report(best, val_ds)
    print(f"\nMejor modelo (val_loss minimo) guardado en {OUTPUT}")


if __name__ == "__main__":
    main()
