import io

import pytest
from shapely.geometry import shape

from pixel_bangkok.heights import derive_height
from pixel_bangkok.normalise import normalise
from pixel_bangkok.pixelart import apply_pixel_art, unique_colors
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.render import composite, parse_color, render_layers


@pytest.fixture
def scene(raw_osm, area, bounds, render_config):
    layers, _ = normalise(raw_osm, area, render_config)
    world = {}
    for name, features in layers.items():
        world[name] = []
        for item in features:
            properties = dict(item["properties"])
            if name == "buildings":
                derived = derive_height(
                    properties["source_height"], properties["source_levels"], 3.0, 6.0
                )
                properties["render_height_m"] = derived.render_height_m
                properties["roof_shape"] = "spire" if properties["is_tower"] else "flat"
            geometry = bounds.geometry_to_world(shape(item["geometry"]))
            world[name].append((geometry, properties))
    return world


def _render(bounds, render_config, scene):
    layers = render_layers(bounds, render_config, scene)
    return composite(layers, parse_color(render_config.palette["background"]))


def _png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_render_is_deterministic(bounds, render_config, scene):
    assert _png(_render(bounds, render_config, scene)) == _png(
        _render(bounds, render_config, scene)
    )


def test_image_size_matches_projection(bounds, render_config, scene):
    projection = IsoProjection.create(bounds, render_config)
    image = _render(bounds, render_config, scene)
    assert image.size == (projection.native_width, projection.native_height)


def test_features_land_where_the_projection_says(bounds, render_config, scene):
    projection = IsoProjection.create(bounds, render_config)
    image = _render(bounds, render_config, scene)
    palette = {name: parse_color(value)[:3] for name, value in render_config.palette.items()}

    def pixel(x, y, z=0.0):
        px, py = projection.world_to_native(x, y, z)
        return image.getpixel((round(px), round(py)))

    assert pixel(50, 50, 12) == palette["building_roof"]
    assert pixel(95, 45, 6) == palette["temple_roof"]
    assert pixel(15, 85) == palette["water"]
    assert pixel(100, 10) == palette["road"]
    assert pixel(165, 45) == palette["green"]
    assert pixel(100, 60) == palette["terrain"]
    assert image.getpixel((0, 0)) == palette["background"]


def test_pixel_art_keeps_geometry_and_limited_palette(bounds, render_config, scene):
    image = _render(bounds, render_config, scene)
    master = apply_pixel_art(image, render_config)
    scale = render_config.upscale
    assert master.size == (image.width * scale, image.height * scale)
    assert unique_colors(master) <= 2 * len(render_config.palette)
    projection = IsoProjection.create(bounds, render_config)
    px, py = projection.world_to_master(50, 50, 12)
    roof = parse_color(render_config.palette["building_roof"])[:3]
    assert master.getpixel((round(px), round(py))) == roof
    assert _png(apply_pixel_art(image, render_config)) == _png(master)
