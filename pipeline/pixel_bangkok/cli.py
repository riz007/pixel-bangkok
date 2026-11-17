from __future__ import annotations

import argparse
import logging
import sys

from . import extract, heights, normalise, pixelart, publish, render, tile, trees
from .config import ConfigError, Paths, load_area_config, load_render_config

STAGES = ("extract", "normalise", "enrich", "render", "style", "tile", "publish")


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
    elif stage == "render":
        render.run(area, config, paths.processed_dir, paths.build_dir)
    elif stage == "style":
        pixelart.run(config, paths.build_dir)
    elif stage == "tile":
        tile.run(area, config, paths.raw_dir, paths.processed_dir, paths.build_dir)
    elif stage == "publish":
        publish.run(area, config, paths.build_dir, paths.curated_dir, paths.publish_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pixel Bangkok asset pipeline")
    parser.add_argument("stage", choices=(*STAGES, "all"))
    parser.add_argument("--area", default="wat-arun", help="area id in config/areas/")
    parser.add_argument("--force", action="store_true", help="re-download the raw extract")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stages = STAGES if args.stage == "all" else (args.stage,)
    try:
        for stage in stages:
            run_stage(stage, args.area, args.force)
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as exc:
        logging.getLogger("pixel_bangkok").error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
