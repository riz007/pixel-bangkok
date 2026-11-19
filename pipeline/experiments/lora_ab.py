"""A/B a style LoRA against the base model on the same AI windows.

Runs the mflux worker twice on identical inputs, seeds and strength (no neighbour
conditioning), then judges both with the production drift gate.

    uv run --project pipeline python pipeline/experiments/lora_ab.py inner-bangkok <adapter>
Writes build/<area>/ai/ab/{base,lora}/<id>.png and ab/report.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from pixel_bangkok import ai_repaint

PER_GROUP = 6


def main() -> int:
    area, adapter = sys.argv[1], Path(sys.argv[2]).resolve()
    ai_dir = Path("build") / area / "ai"
    state = json.loads((ai_dir / "state.json").read_text())["windows"]
    windows = ai_dir / "windows"
    with_input = {k: v for k, v in state.items() if (windows / f"{k}.in.png").exists()}
    accepted = sorted(k for k, v in with_input.items() if v["accepted"])[:PER_GROUP]
    rejected = sorted(k for k, v in with_input.items() if not v["accepted"])[:PER_GROUP]
    chosen = accepted + rejected
    out = ai_dir / "ab"
    for variant in ("base", "lora"):
        jobs = out / f"{variant}.jsonl"
        (out / variant).mkdir(parents=True, exist_ok=True)
        jobs.write_text(
            "".join(
                json.dumps(
                    {
                        "input": str((windows / f"{k}.in.png").resolve()),
                        "output": str((out / variant / f"{k}.png").resolve()),
                        "seed": ai_repaint.SEED,
                        "strength": ai_repaint.STRENGTH,
                    }
                )
                + "\n"
                for k in chosen
            )
        )
        command = [
            str(ai_repaint.DEFAULT_MFLUX_PYTHON),
            str(Path("pipeline/experiments/mflux_worker.py").resolve()),
            str(jobs),
            "--quantize",
            str(ai_repaint.QUANTIZE),
            "--steps",
            str(ai_repaint.STEPS),
            "--prompt-file",
            str((ai_dir / "prompt.txt").resolve()),
        ]
        if variant == "lora":
            command += ["--lora", str(adapter)]
        subprocess.run(command, check=True)
    report = {"accepted_before": accepted, "rejected_before": rejected, "windows": {}}
    for k in chosen:
        with Image.open(windows / f"{k}.in.png") as reference:
            reference = reference.convert("RGB")
            row = {}
            for variant in ("base", "lora"):
                with Image.open(out / variant / f"{k}.png") as raw:
                    _, metrics = ai_repaint.judge(reference, raw)
                row[variant] = {
                    key: metrics[key]
                    for key in ("passes", "edge_recall", "unmatched_fraction", "max_local_shift_px")
                }
            report["windows"][k] = row
    for variant in ("base", "lora"):
        report[f"{variant}_passes"] = sum(r[variant]["passes"] for r in report["windows"].values())
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k.endswith("_passes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
