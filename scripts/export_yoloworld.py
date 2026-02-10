"""One-time export script: YOLO-World v2s with custom household vocabulary -> ONNX.

Usage:
    uv pip install ultralytics
    python scripts/export_yoloworld.py

Produces ~/.cache/flot_inventory/models/yoloworld_v2s.onnx (~49MB).
Requires pkg_resources monkey-patch for Python 3.13+ (CLIP compatibility).
"""

import importlib
import shutil
import sys
import types
from pathlib import Path

# --- Monkey-patch pkg_resources for Python 3.13+ / setuptools 82+ ---
# CLIP does `from pkg_resources import packaging` which no longer exists.
# Provide a shim that delegates to the real `packaging` package.
try:
    importlib.import_module("pkg_resources")
except (ModuleNotFoundError, ImportError):
    import packaging  # the standalone packaging lib is always available

    mod = types.ModuleType("pkg_resources")
    mod.__path__ = []
    mod.packaging = packaging
    sys.modules["pkg_resources"] = mod

CACHE_DIR = Path.home() / ".cache" / "flot_inventory" / "models"

# Household vocabulary - baked into the ONNX at export time
HOUSEHOLD_VOCABULARY = [
    # Furniture
    "chair", "couch", "sofa", "table", "desk", "bed", "shelf", "bookshelf",
    "cabinet", "dresser", "nightstand", "bench", "stool", "ottoman", "recliner",
    "wardrobe", "tv stand", "coffee table", "dining table", "end table",
    # Electronics
    "tv", "monitor", "laptop", "keyboard", "mouse", "speaker", "headphones",
    "remote", "phone", "tablet", "game console", "router", "camera",
    # Kitchen
    "refrigerator", "microwave", "oven", "toaster", "blender", "kettle",
    "coffee maker", "dishwasher", "pot", "pan", "plate", "bowl", "cup", "mug",
    "glass", "bottle", "cutting board", "knife block",
    # Decor & lighting
    "lamp", "floor lamp", "desk lamp", "chandelier", "candle", "vase",
    "picture frame", "painting", "mirror", "clock", "plant", "potted plant",
    "rug", "curtain", "pillow", "blanket", "figurine", "sculpture",
    # Musical instruments
    "piano", "guitar", "violin", "drum", "keyboard instrument",
    # Books & media
    "book", "bookshelf", "magazine", "vinyl record",
    # Appliances
    "washing machine", "dryer", "vacuum", "iron", "fan", "heater",
    "air conditioner", "humidifier",
    # Storage & misc
    "box", "basket", "bag", "suitcase", "backpack", "shoe", "toy",
    "teddy bear", "board game", "bicycle", "umbrella", "toolbox",
]


def export():
    from ultralytics import YOLO

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / "yoloworld_v2s.onnx"

    print("Loading yolov8s-worldv2.pt ...")
    model = YOLO("yolov8s-worldv2.pt")

    # Deduplicate vocabulary while preserving order
    seen = set()
    vocab = []
    for item in HOUSEHOLD_VOCABULARY:
        low = item.lower()
        if low not in seen:
            seen.add(low)
            vocab.append(item)

    print(f"Setting {len(vocab)} custom classes ...")
    model.set_classes(vocab)

    print("Exporting to ONNX ...")
    out_path = model.export(format="onnx", imgsz=640, simplify=True)

    # ultralytics saves next to the .pt file; move to cache dir
    out_path = Path(out_path)
    if out_path != dest:
        shutil.move(str(out_path), str(dest))

    print(f"Saved: {dest}")
    print(f"Vocabulary ({len(vocab)} classes):")
    for i, name in enumerate(vocab):
        print(f"  [{i:3d}] {name}")


if __name__ == "__main__":
    export()
