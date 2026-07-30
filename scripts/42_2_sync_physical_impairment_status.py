#!/usr/bin/env python3
"""Update project status after the practical impairment sensitivity gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN PHYSICAL IMPAIRMENT SENSITIVITY -->"
END = "<!-- END PHYSICAL IMPAIRMENT SENSITIVITY -->"


def replace_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        return text[:start] + block + text[stop:]
    return block + "\n\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/physical_impairment_sensitivity_v1.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    audit = json.loads(
        (ROOT / cfg["paths"]["results_dir"] / "PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT.json").read_text(encoding="utf-8")
    )
    cap60 = audit["null_depth_findings"]["long_single_cap60"]
    cap67 = audit["null_depth_findings"]["long_single_cap67"]
    block = f"""{BEGIN}
## Practical null-depth and physical-impairment sensitivity

The corrected ideal-digital controller remains valid, but practical array/CSI
calibration is not yet available. In the one-seed long-term single-entry
sensitivity:

- clipping the protected-mode attenuation to 60 dB produces
  `{cap60['uncorrected_violation_seconds']}` violation seconds;
- a conservative uniform protected-tone fallback then requires
  `{cap60['minimum_uniform_protected_tone_backoff_db']:.3f}` dB backoff;
- at a 67 dB cap, the corresponding fallback is
  `{cap67['minimum_uniform_protected_tone_backoff_db']:.3f}` dB;
- assumed differential phase/gain, steering, and phase-quantization errors can
  break the near-zero-margin solution;
- these are deterministic sensitivity tests, not empirical calibration.

The multi-seed campaign is frozen as a phased design but remains unauthorized.

**Next gate:** `{cfg['next_gate']}`
{END}"""
    project = ROOT / "PROJECT_STATUS.md"
    text = project.read_text(encoding="utf-8") if project.is_file() else "# Current Project Status\n"
    project.write_text(replace_block(text, block), encoding="utf-8")
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "1. Obtain measured or source-referenced per-port complex calibration residuals, their correlation, quantization, steering/orientation error, CSI error, and achieved OTA null depth.\n"
        "2. If measurements are unavailable, freeze explicit deterministic engineering envelopes and do not claim practical compliance.\n"
        "3. Implement a null-floor-aware sector-selective protected-tone backoff fallback; uniform backoff remains only a conservative baseline.\n"
        "4. Re-run the four corrected criterion/pattern cases with the practical null-depth envelope and exact user-floor audit.\n"
        "5. Independently review the phased campaign bundle before any Nibi submission.\n",
        encoding="utf-8",
    )
    print("PHYSICAL IMPAIRMENT STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
