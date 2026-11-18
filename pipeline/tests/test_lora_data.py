import json
from pathlib import Path

from PIL import Image

from pixel_bangkok.lora_data import TRIGGER, build, caption, training_config
from pixel_bangkok.render import parse_color


def _solid(render_config, name, size=(512, 512)):
    return Image.new("RGB", size, parse_color(render_config.palette[name])[:3])


def test_caption_reflects_content(render_config):
    river = caption(_solid(render_config, "water"), render_config)
    assert river.startswith(TRIGGER)
    assert "river" in river and "temples" not in river
    temple = caption(_solid(render_config, "temple_roof"), render_config)
    assert "temples" in temple and "river" not in temple


def test_build_uses_only_accepted_windows_and_skips_background(tmp_path, render_config):
    ai = tmp_path / "ai"
    (ai / "windows").mkdir(parents=True)
    road = _solid(render_config, "road", (1024, 1024))
    half_background = road.copy()
    half_background.paste(_solid(render_config, "background", (1024, 512)), (0, 0))
    for window_id, source in (("a", road), ("b", half_background), ("c", road)):
        source.save(ai / "windows" / f"{window_id}.in.png")
        Image.new("RGB", (1024, 1024), (90, 90, 90)).save(ai / "windows" / f"{window_id}.png")
    (ai / "state.json").write_text(
        json.dumps(
            {
                "windows": {
                    "a": {"accepted": True, "edge_recall": 0.95},
                    "b": {"accepted": True, "edge_recall": 0.99},
                    "c": {"accepted": False, "edge_recall": 0.99},
                }
            }
        )
    )
    output = build(render_config, tmp_path)
    images = sorted(output.glob("[0-9]*.png"))
    assert len(images) == 4 + 2
    assert all((output / f"{image.stem}.txt").exists() for image in images)
    assert "roads" in (output / "0001.txt").read_text()
    assert (output / "preview_1.txt").exists()

    config = json.loads((tmp_path / "ai" / "lora-train.json").read_text())
    assert config["model"] == "qwen-image-2.1"
    assert config["data"] == str(output)
    assert config["quantize"] == 8 and config["gradient_checkpointing"] is True


def test_training_config_targets_every_block():
    config = training_config(Path("data"), Path("out"), images=100)
    targets = config["lora_layers"]["targets"]
    assert len(targets) == 7
    assert all(t["blocks"] == {"start": 0, "end": 32} for t in targets)
    assert config["training_loop"]["num_epochs"] == 4
