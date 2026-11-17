import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "ai_repaint_trial.py"
spec = importlib.util.spec_from_file_location("ai_repaint_trial", SCRIPT)
trial = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trial
spec.loader.exec_module(trial)


def _scene() -> Image.Image:
    image = Image.new("RGB", (256, 256), (217, 201, 163))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 60, 110, 120), fill=(230, 220, 203), outline=(42, 36, 48))
    draw.rectangle((150, 30, 200, 180), fill=(217, 119, 60), outline=(42, 36, 48))
    draw.polygon([(0, 200), (256, 150), (256, 256), (0, 256)], fill=(63, 127, 166))
    return image


def test_identical_images_have_no_drift():
    metrics = trial.drift(_scene(), _scene())
    assert (metrics["shift_x_px"], metrics["shift_y_px"]) == (0, 0)
    assert metrics["edge_recall"] == 1.0
    assert metrics["edge_precision"] == 1.0
    assert metrics["mean_abs_change"] == 0.0
    assert metrics["max_local_shift_px"] == 0
    assert metrics["passes"] is True


def test_shifted_image_is_detected():
    shifted = ImageChops.offset(_scene(), 7, -4)
    metrics = trial.drift(_scene(), shifted)
    assert (metrics["shift_x_px"], metrics["shift_y_px"]) == (-7, 4)
    assert metrics["edge_recall"] < 0.6
    assert metrics["max_local_shift_px"] == 7
    assert metrics["passes"] is False


def test_missing_building_lowers_recall():
    altered = _scene()
    ImageDraw.Draw(altered).rectangle((150, 30, 200, 180), fill=(217, 201, 163))
    metrics = trial.drift(_scene(), altered)
    assert metrics["edge_recall"] < 0.8
    assert metrics["mean_abs_change"] > 0
