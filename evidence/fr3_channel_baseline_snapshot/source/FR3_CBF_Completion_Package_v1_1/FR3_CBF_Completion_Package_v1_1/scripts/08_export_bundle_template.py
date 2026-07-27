from __future__ import annotations

import json

import numpy as np

from _bootstrap import ROOT


def main() -> int:
    rng = np.random.default_rng(808)
    b, u, m, t, k, ell = 3, 4, 8, 2, 4, 2
    channels = (rng.normal(size=(b, u, m)) + 1j * rng.normal(size=(b, u, m))) / np.sqrt(2 * m)
    beams = (rng.normal(size=(b, t, m, k)) + 1j * rng.normal(size=(b, t, m, k))) / np.sqrt(2 * m * k)
    coupling = np.empty((ell, b, t, m, m), dtype=np.complex128)
    for l in range(ell):
        for bi in range(b):
            for ti in range(t):
                a = (rng.normal(size=m) + 1j * rng.normal(size=m)) / np.sqrt(2 * m)
                coupling[l, bi, ti] = 0.08 * np.outer(a, a.conj()) + 1e-4 * np.eye(m)
    thresholds = np.ones(ell, dtype=float)
    tone_weights = np.full(t, 1.0 / t)
    metadata = {
        "evidence_level": "DEMO_TEMPLATE",
        "units": "linear power; coupling maps beam power to protected-receiver watts",
        "receiver": "single-antenna MISO reference only",
    }
    out = ROOT / "data/demo/experiment_bundle_template.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        channels=channels,
        nominal_beamformers=beams,
        coupling=coupling,
        thresholds=thresholds,
        tone_weights=tone_weights,
        noise_power=np.array(1e-3),
        users_per_bs=np.array(k),
        metadata_json=np.array(json.dumps(metadata)),
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
