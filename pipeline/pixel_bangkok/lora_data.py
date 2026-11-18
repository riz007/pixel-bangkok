"""Training images and captions for a Pixel Bangkok style LoRA.

Self-distillation: the targets are AI windows that already passed the drift
gate (build/<area>/ai/windows/<id>.png). Each 1024 px window is cut into 512 px
crops; captions describe what the matching procedural crop contains, read
from its exact palette colours, after a trigger word.

Output: build/<area>/ai/lora-data/NNNN.png + NNNN.txt and preview_1.txt.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from .config import RenderConfig
from .render import parse_color

log = logging.getLogger(__name__)

TRIGGER = "pxbkk"
TARGET_STEPS = 400
LORA_RANK = 16
LORA_MODULES = (
    "attn.to_q",
    "attn.to_k",
    "attn.to_v",
    "attn.to_out.0",
    "img_mlp.gate_layer",
    "img_mlp.proj",
    "img_mlp.out",
)
CROP_PX = 512
MAX_BACKGROUND_FRACTION = 0.3
MIN_FEATURE_FRACTION = 0.03


def _colours(render: RenderConfig, names: list[str]) -> np.ndarray:
    return np.array([parse_color(render.palette[name])[:3] for name in names], dtype=np.uint8)


def _fraction(pixels: np.ndarray, colours: np.ndarray) -> float:
    matches = np.zeros(pixels.shape[:2], dtype=bool)
    for colour in colours:
        matches |= np.all(pixels == colour, axis=-1)
    return float(matches.mean())


def caption(procedural: Image.Image, render: RenderConfig) -> str:
    pixels = np.asarray(procedural.convert("RGB"))
    groups = {
        "the Chao Phraya river with boats": ["water", "water_light", "water_edge", "foam"],
        "Thai temples with orange tiered roofs and golden gables": [
            "temple_roof",
            "temple_roof_dark",
            "temple_trim",
        ],
        "parks and trees": ["green", "green_dark", "tree", "tree_dark", "tree_light"],
        "busy roads with lane markings": ["road", "road_major", "road_marking"],
    }
    parts = [
        label
        for label, names in groups.items()
        if _fraction(pixels, _colours(render, names)) >= MIN_FEATURE_FRACTION
    ]
    glass = render.materials.get("tower_glass")
    if glass is not None:
        tower = np.array(
            [parse_color(glass["wall_light"])[:3], parse_color(glass["wall_dark"])[:3]]
        )
        if _fraction(pixels, tower) >= MIN_FEATURE_FRACTION / 3:
            parts.append("glass high-rise towers")
    parts.append("dense shophouses and concrete buildings")
    return (
        f"{TRIGGER}, detailed isometric pixel art map of Bangkok, crisp pixel edges, limited "
        f"palette, {', '.join(parts)}"
    )


def build(render: RenderConfig, build_dir: Path, limit: int = 200) -> Path:
    ai_dir = build_dir / "ai"
    state = json.loads((ai_dir / "state.json").read_text(encoding="utf-8"))["windows"]
    accepted = sorted(
        (
            (window_id, entry)
            for window_id, entry in state.items()
            if entry["accepted"] and (ai_dir / "windows" / f"{window_id}.png").exists()
        ),
        key=lambda item: (-item[1].get("edge_recall", 0), item[0]),
    )
    output = ai_dir / "lora-data"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    background = np.array(parse_color(render.palette["background"])[:3], dtype=np.uint8)
    count = 0
    for window_id, _ in accepted:
        with Image.open(ai_dir / "windows" / f"{window_id}.png") as image:
            target = image.convert("RGB")
        with Image.open(ai_dir / "windows" / f"{window_id}.in.png") as image:
            procedural = image.convert("RGB")
        for top in range(0, target.height - CROP_PX + 1, CROP_PX):
            for left in range(0, target.width - CROP_PX + 1, CROP_PX):
                box = (left, top, left + CROP_PX, top + CROP_PX)
                source = procedural.crop(box)
                empty = float(np.all(np.asarray(source) == background, axis=-1).mean())
                if empty > MAX_BACKGROUND_FRACTION:
                    continue
                count += 1
                target.crop(box).save(output / f"{count:04d}.png")
                (output / f"{count:04d}.txt").write_text(caption(source, render), encoding="utf-8")
                if count >= limit:
                    break
            if count >= limit:
                break
        if count >= limit:
            break
    (output / "preview_1.txt").write_text(
        f"{TRIGGER}, detailed isometric pixel art map of Bangkok, crisp pixel edges, limited "
        "palette, Thai temples with orange tiered roofs, the Chao Phraya river with boats, "
        "dense shophouses and concrete buildings",
        encoding="utf-8",
    )
    log.info(
        "wrote %d LoRA training images from %d accepted windows to %s", count, len(accepted), output
    )
    write_training_config(build_dir)
    return output


def training_config(data_dir: Path, output_dir: Path, images: int) -> dict:
    """mflux-train spec for a Qwen-Image 2.1 style LoRA sized to fit 24 GB unified memory."""
    epochs = max(1, round(TARGET_STEPS / max(images, 1)))
    return {
        "model": "qwen-image-2.1",
        "data": str(data_dir),
        "seed": 20261118,
        "steps": 20,
        "quantize": 8,
        "max_resolution": CROP_PX,
        "low_ram": True,
        "gradient_checkpointing": True,
        "cache_limit_gb": 2,
        "training_loop": {"num_epochs": epochs, "batch_size": 1},
        "optimizer": {
            "name": "AdamW",
            "learning_rate": 1e-4,
            "optimizer_params": {"eps": 1e-6, "weight_decay": 0.01},
            "max_grad_norm": 1.0,
        },
        "checkpoint": {"save_frequency": 100, "output_path": str(output_dir)},
        "monitoring": {
            "preview_width": CROP_PX,
            "preview_height": CROP_PX,
            "plot_frequency": 50,
            "generate_image_frequency": 200,
        },
        "lora_layers": {
            "targets": [
                {
                    "module_path": f"transformer_blocks.{{block}}.{module}",
                    "blocks": {"start": 0, "end": 32},
                    "rank": LORA_RANK,
                    "alpha": LORA_RANK,
                }
                for module in LORA_MODULES
            ]
        },
    }


def write_training_config(build_dir: Path) -> Path:
    data_dir = build_dir / "ai" / "lora-data"
    images = len(list(data_dir.glob("[0-9]*.png")))
    if images == 0:
        raise FileNotFoundError(f"no training images in {data_dir}; run ai-dataset first")
    config = training_config(data_dir, build_dir / "ai" / "lora-train", images)
    path = build_dir / "ai" / "lora-train.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    log.info("wrote LoRA training config for %d images -> %s", images, path)
    return path
