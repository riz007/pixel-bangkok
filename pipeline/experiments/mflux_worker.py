"""Run Qwen-Image 2.1 Turbo edits for a list of windows with the model loaded once.

Runs inside the mflux tool environment, not the pipeline's:
    ~/.local/share/uv/tools/mflux/bin/python mflux_worker.py jobs.jsonl --quantize 4

Each line of jobs.jsonl is {"input": path, "output": path, "seed": int, "strength": float,
"mask": optional path (white = repaint, black = keep)}.
Jobs whose output exists are skipped. One JSON line is printed per finished job.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
from mflux.models.common.resolution.config_resolution import ConfigResolution
from mflux.models.qwen21.variants.edit.qwen_image_21_edit import QwenImage21Edit

MODEL = "qwen-image-2.1-turbo"
CACHE_LIMIT_BYTES = 2 * 1024**3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs")
    parser.add_argument("--quantize", type=int, default=4)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--lora", action="append", default=[], help="LoRA adapter .safetensors")
    parser.add_argument("--lora-scale", type=float, default=1.0)
    args = parser.parse_args()
    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    jobs = [json.loads(line) for line in Path(args.jobs).read_text().splitlines() if line.strip()]
    pending = [job for job in jobs if not Path(job["output"]).exists()]
    if not pending:
        return 0
    started = time.monotonic()
    mx.set_cache_limit(CACHE_LIMIT_BYTES)
    config = ConfigResolution.resolve_restricted(
        MODEL, "qwen-image-2.1", model_path=None, extra_keys=(MODEL,), base_model=None
    )
    model = QwenImage21Edit(
        quantize=args.quantize,
        model_path=None,
        model_config=config,
        compute_precision=None,
        small_text_encoder=True,
        lora_paths=args.lora or None,
        lora_scales=[args.lora_scale] * len(args.lora) if args.lora else None,
    )
    print(
        json.dumps({"event": "loaded", "seconds": round(time.monotonic() - started, 1)}), flush=True
    )
    for job in pending:
        began = time.monotonic()
        image = model.generate_image(
            seed=int(job["seed"]),
            prompt=prompt,
            num_inference_steps=args.steps,
            width=args.size,
            height=args.size,
            image_paths=[job["input"]],
            mask_image=job.get("mask"),
            output_resolution=args.size,
            strength=float(job["strength"]),
        )
        output = Path(job["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        image.image.save(output)
        del image
        mx.clear_cache()
        print(
            json.dumps(
                {
                    "event": "done",
                    "output": str(output),
                    "seconds": round(time.monotonic() - began, 1),
                    "peak_gb": round(mx.get_peak_memory() / 1024**3, 1),
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
