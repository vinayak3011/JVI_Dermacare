"""Run skin-lesion predictions with the model bundled in this repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import tensorflow as tf


CLASS_NAMES = [
    "akiec, Actinic Keratoses or intraepithelial Carcinoma (Bowen's disease)",
    "bcc, Basal Cell Carcinoma",
    "bkl, Benign Keratosis",
    "df, Dermatofibroma",
    "mel, Melanoma",
    "nv, Melanocytic Nevi",
    "vasc, Vascular skin lesion",
]

DEFAULT_MODEL = Path(__file__).parent / "final_model_kaggle_version1" / "model.json"


def load_tfjs_model(model_json: Path) -> tf.keras.Model:
    """Rebuild the Keras model and load weights from a TF.js model bundle."""
    with model_json.open(encoding="utf-8") as file:
        model_bundle: dict[str, Any] = json.load(file)

    topology = model_bundle["modelTopology"]
    model = tf.keras.models.model_from_json(
        json.dumps(topology["model_config"]),
        custom_objects={"Model": tf.keras.Model},
    )

    manifest = model_bundle["weightsManifest"]
    model_directory = model_json.parent
    weight_bytes = b"".join(
        (model_directory / shard).read_bytes()
        for group in manifest
        for shard in group["paths"]
    )

    variables = {
        getattr(variable, "path", variable.name.split(":")[0]): variable
        for variable in model.weights
    }
    offset = 0
    loaded_names: set[str] = set()
    for group in manifest:
        for weight in group["weights"]:
            shape = tuple(weight["shape"])
            count = int(np.prod(shape))
            byte_count = count * np.dtype(np.float32).itemsize
            values = np.frombuffer(
                weight_bytes[offset : offset + byte_count], dtype=np.float32
            ).reshape(shape)
            offset += byte_count

            variable_name = weight["name"]
            keras_name = variable_name.replace("/depthwise_kernel", "/kernel")
            if keras_name not in variables:
                raise ValueError(f"Model variable not found in Keras model: {variable_name}")
            variables[keras_name].assign(values)
            loaded_names.add(variable_name)

    if offset != len(weight_bytes):
        raise ValueError("The TF.js weight shards contain unexpected trailing data")
    manifest_names = {
        name.replace("/depthwise_kernel", "/kernel") for name in loaded_names
    }
    missing_names = set(variables) - manifest_names
    if missing_names:
        raise ValueError(f"Missing weights in TF.js manifest: {sorted(missing_names)}")

    return model


def predict_image(
    model: tf.keras.Model, image_path: Path, top_k: int = 3
) -> list[dict[str, float | str]]:
    """Predict the most likely lesion classes for one image."""
    with Image.open(image_path) as image:
        image = image.convert("RGB").resize((224, 224), Image.Resampling.NEAREST)
        pixels = np.asarray(image, dtype=np.float32)

    tensor = (pixels - 127.5) / 127.5
    probabilities = model.predict(tensor[None, ...], verbose=0)[0]
    indices = np.argsort(probabilities)[::-1][:top_k]
    return [
        {"class": CLASS_NAMES[index], "probability": float(probabilities[index])}
        for index in indices
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to a skin-lesion image")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help="Path to the TF.js model.json file",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Number of results to print")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error(f"Image does not exist: {args.image}")
    if not args.model.is_file():
        parser.error(f"Model does not exist: {args.model}")
    if not 1 <= args.top_k <= len(CLASS_NAMES):
        parser.error(f"--top-k must be between 1 and {len(CLASS_NAMES)}")

    model = load_tfjs_model(args.model)
    results = predict_image(model, args.image, args.top_k)
    print(json.dumps({"image": str(args.image), "predictions": results}, indent=2))


if __name__ == "__main__":
    main()