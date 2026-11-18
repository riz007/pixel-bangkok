from PIL import Image, ImageChops, ImageDraw

from pixel_bangkok import drift as trial


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


def test_uniform_offset_is_registered_back():
    shifted = ImageChops.offset(_scene(), 3, -2)
    aligned, dx, dy = trial.register(_scene(), shifted)
    assert (dx, dy) == (-3, 2)
    metrics = trial.drift(_scene(), aligned)
    assert metrics["max_local_shift_px"] == 0
    assert metrics["passes"] is True


def test_unmatched_texture_fails_the_gate():
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(0)
    noise = Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8), "RGB")
    other = Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8), "RGB")
    metrics = trial.drift(noise, other)
    assert metrics["unmatched_fraction"] > 0.3
    assert metrics["passes"] is False
