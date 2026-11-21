from __future__ import annotations

import argparse
import logging
import sys

from . import (
    ai_repaint,
    extract,
    heights,
    lora_data,
    motion,
    normalise,
    pixelart,
    pois,
    publish,
    render,
    tile,
    trees,
)
from .config import ConfigError, Paths, load_area_config, load_render_config

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


AI_STAGES = ("ai-plan", "ai-run", "ai-compose", "ai-dataset", "ai-cycle")


def run_ai_stage(stage: str, area_id: str, limit: int, focus: str | None) -> None:
    area = load_area_config(area_id)
    config = load_render_config()
    paths = Paths.for_area(area.id)
    if stage == "ai-plan":
        point = (
            tuple(float(value) for value in focus.split(","))
            if focus
            else ai_repaint.default_focus(area)
        )
        ai_repaint.plan(area, config, paths.build_dir, point)  # type: ignore[arg-type]
    elif stage == "ai-run":
        ai_repaint.run(paths.build_dir, limit)
    elif stage == "ai-compose":
        ai_repaint.compose(config, paths.build_dir, area)
    elif stage == "ai-dataset":
        lora_data.build(config, paths.build_dir)
    elif stage == "ai-cycle":
        ai_repaint.run(paths.build_dir, limit)
        ai_repaint.compose(config, paths.build_dir, area)


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
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stages = STAGES if args.stage == "all" else (args.stage,)
    try:
        if args.stage in AI_STAGES:
            run_ai_stage(args.stage, args.area, args.limit, args.focus)
            return 0
        for stage in stages:
            run_stage(stage, args.area, args.force)
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as exc:
        logging.getLogger("pixel_bangkok").error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
