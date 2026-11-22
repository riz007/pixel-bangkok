"""Run FLUX.2 [klein] 4B edits (optionally with a style LoRA) for a list of windows.

Runs inside the mflux tool environment, not the pipeline's:
    build/.tools/mflux-main/bin/python flux2_worker.py jobs.jsonl --prompt-file p.txt \
        --lora x.safetensors

Each line of jobs.jsonl is {"input": path, "output": path, "seed": int,
"strength": optional float (img2img start from the input; omit for a pure reference edit)}.
Jobs whose output exists are skipped. One JSON line is printed per finished job.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2KleinEdit

CACHE_LIMIT_BYTES = 2 * 1024**3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs")
    parser.add_argument("--quantize", type=int, default=8)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--steps", type=int, default=4)
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
    model = Flux2KleinEdit(
        quantize=args.quantize,
        model_config=ModelConfig.flux2_klein_4b(),
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
            guidance=1.0,
            image_paths=[job["input"]],
            image_strength=job.get("strength"),
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
