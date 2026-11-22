from __future__ import annotations

import argparse
import logging
import sys

import numpy as np
from PIL import Image, ImageFilter

from . import (
    ai_repaint,
    extract,
    heights,
    lora_data,
    motion,
    normalise,
    pixelart,
    pois,
    protected,
    publish,
    render,
    tile,
    trees,
)
from .blocks import read_region
from .config import ConfigError, Paths, load_area_config, load_render_config
from .crs import MapBounds
from .projection import IsoProjection
from .render import parse_color

STAGES = (
    "extract",
    "normalise",
    "enrich",
    "pois",
    "motion",
    "render",
    "style",
    "tile",
    "publish",
)


AI_STAGES = ("ai-plan", "ai-run", "ai-compose", "ai-dataset", "ai-cycle", "ai-rejudge")


def run_ai_stage(
    stage: str,
    area_id: str,
    limit: int,
    focus: str | None,
    engine: str = ai_repaint.DEFAULT_ENGINE,
    protect: str = "auto",
) -> None:
    area = load_area_config(area_id)
    config = load_render_config()
    paths = Paths.for_area(area.id)

    bounds = MapBounds.from_area(area)
    shapes: list[protected.Shape] | None = None

    def protected_shapes() -> list[protected.Shape]:
        """Places whose AI paint is never shown: all sensitive places with --protect all;
        none with --protect none; with auto, those the AI made unrecognisable."""
        nonlocal shapes
        if shapes is None:
            if protect == "none":
                shapes = []
            elif protect == "all":
                shapes = protected.for_area(bounds, paths.processed_dir, paths.curated_dir)
            else:
                shapes = ai_repaint.check_places(
                    config,
                    paths.build_dir,
                    area,
                    protected.places_for_area(bounds, paths.processed_dir, paths.curated_dir),
                    protected.load_overrides(paths.curated_dir),
                )
        return shapes

    background = np.array(parse_color(config.palette["background"])[:3], dtype=np.uint8)

    def ignore(box: tuple[int, int, int, int]) -> np.ndarray:
        """Pixels never shown from AI, so not judged: the blank area past the map's edge, and
        every sensitive place with --protect all. (With auto, places are judged as painted.)"""
        projection = IsoProjection.create(bounds, config)
        always = protected_shapes() if protect == "all" else []
        keep = protected.rasterize(always, projection, box) > 0.5
        drawing = np.asarray(read_region(paths.build_dir / "blocks", "master", box, "RGB"))
        blank = np.all(drawing == background, axis=-1).astype(np.float32)
        # The dithered edge mixes blank and drawn pixels; treat mostly blank areas as blank.
        near = np.asarray(
            Image.fromarray((blank * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(16)),
            dtype=np.float32,
        )
        return keep | (near > 0.3 * 255)

    def compose() -> None:
        ai_repaint.compose(config, paths.build_dir, area, protected_shapes(), ignore)

    if stage == "ai-plan":
        point = (
            tuple(float(value) for value in focus.split(","))
            if focus
            else ai_repaint.default_focus(area)
        )
        ai_repaint.plan(area, config, paths.build_dir, point)  # type: ignore[arg-type]
    elif stage == "ai-run":
        ai_repaint.run(paths.build_dir, limit, engine_name=engine, ignore=ignore)
    elif stage == "ai-rejudge":
        ai_repaint.rejudge(paths.build_dir, ignore)
    elif stage == "ai-compose":
        compose()
    elif stage == "ai-dataset":
        lora_data.build(config, paths.build_dir)
    elif stage == "ai-cycle":
        ai_repaint.run(paths.build_dir, limit, engine_name=engine, ignore=ignore)
        compose()
        tile.run(area, config, paths.raw_dir, paths.processed_dir, paths.build_dir, ai_only=True)
        publish.run(
            area,
            config,
            paths.build_dir,
            paths.curated_dir,
            paths.publish_dir,
            paths.processed_dir,
        )


def run_stage(stage: str, area_id: str, force: bool) -> None:
    area = load_area_config(area_id)
    config = load_render_config()
    paths = Paths.for_area(area.id)
    if stage == "extract":
        extract.run(area, paths.raw_dir, force=force)
    elif stage == "normalise":
        normalise.run(area, config, paths.raw_dir, paths.processed_dir)
    elif stage == "enrich":
        heights.run(area, config, paths.raw_dir, paths.processed_dir, paths.curated_dir)
        trees.run(area, config, paths.raw_dir, paths.processed_dir)
    elif stage == "pois":
        pois.run(area, paths.raw_dir, paths.processed_dir)
    elif stage == "motion":
        motion.run(area, config, paths.raw_dir, paths.processed_dir)
    elif stage == "render":
        render.run(area, config, paths.processed_dir, paths.build_dir)
    elif stage == "style":
        pixelart.run(config, paths.build_dir, area)
    elif stage == "tile":
        tile.run(area, config, paths.raw_dir, paths.processed_dir, paths.build_dir)
    elif stage == "publish":
        publish.run(
            area,
            config,
            paths.build_dir,
            paths.curated_dir,
            paths.publish_dir,
            paths.processed_dir,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pixel Bangkok asset pipeline")
    parser.add_argument("stage", choices=(*STAGES, "all", *AI_STAGES))
    parser.add_argument("--area", default="wat-arun", help="area id in config/areas/")
    parser.add_argument("--force", action="store_true", help="re-download the raw extract")
    parser.add_argument("--limit", type=int, default=10**9, help="ai-run: windows to process")
    parser.add_argument("--focus", help="ai-plan: lon,lat to repaint outward from")
    parser.add_argument(
        "--engine",
        choices=sorted(ai_repaint.ENGINES),
        default=ai_repaint.DEFAULT_ENGINE,
        help="ai-run/ai-cycle: AI paint engine",
    )
    parser.add_argument(
        "--protect",
        choices=protected.PROTECT_MODES,
        default="auto",
        help="AI stages: sensitive places (temples, palaces, mosques, monuments) keep the "
        "drawing: auto = only where the AI made them unrecognisable; all; none",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stages = STAGES if args.stage == "all" else (args.stage,)
    try:
        if args.stage in AI_STAGES:
            run_ai_stage(args.stage, args.area, args.limit, args.focus, args.engine, args.protect)
            return 0
        for stage in stages:
            run_stage(stage, args.area, args.force)
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as exc:
        logging.getLogger("pixel_bangkok").error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
