import json
from pathlib import Path

import numpy as np

from fr3_cbf.bundle import validate_bundle


def test_small_bundle(tmp_path: Path):
    b, u, m, t, k, l = 1, 1, 2, 1, 1, 1
    path = tmp_path / "bundle.npz"
    np.savez(
        path,
        channels=np.ones((b, u, m), complex),
        nominal_beamformers=np.ones((b, t, m, k), complex),
        coupling=np.eye(m, dtype=complex).reshape(l, b, t, m, m),
        thresholds=np.ones(l),
        tone_weights=np.ones(t),
        noise_power=np.array(1.0),
        users_per_bs=np.array(1),
        metadata_json=np.array(json.dumps({"test": True})),
    )
    result = validate_bundle(path)
    assert result["channels_shape"] == [1, 1, 2]
