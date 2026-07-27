from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


REQUIRED_KEYS = {
    "channels",
    "nominal_beamformers",
    "coupling",
    "thresholds",
    "tone_weights",
    "noise_power",
    "users_per_bs",
    "metadata_json",
}


def validate_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the portable Sionna/WMMSE interchange bundle.

    This checks structure, units metadata, Hermitian/PSD coupling samples, and the
    cross-array dimensions used by the included reference evaluators. It cannot prove
    that an external P.452 or cellular simulator produced numerically correct values.
    """
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        keys = set(z.files)
        missing = sorted(REQUIRED_KEYS - keys)
        if missing:
            raise ValueError(f"Bundle missing keys: {missing}")
        h = np.asarray(z["channels"])
        w = np.asarray(z["nominal_beamformers"])
        r = np.asarray(z["coupling"])
        thresholds = np.asarray(z["thresholds"], dtype=float)
        tone_weights = np.asarray(z["tone_weights"], dtype=float)
        noise_power = float(np.asarray(z["noise_power"]).item())
        users_per_bs = int(np.asarray(z["users_per_bs"]).item())

        if h.ndim not in (3, 4):
            raise ValueError(f"channels must be [B,U,M] or [H,B,U,M], got {h.shape}")
        if w.ndim not in (4, 5):
            raise ValueError(f"nominal_beamformers must be [B,T,M,K] or [H,B,T,M,K], got {w.shape}")
        if r.ndim not in (5, 6):
            raise ValueError(f"coupling must be [L,B,T,M,M] or [H,L,B,T,M,M], got {r.shape}")
        if h.ndim + 1 != w.ndim or w.ndim + 1 != r.ndim:
            raise ValueError("channels, beamformers, and coupling must either all be static or all carry the same time axis")

        if w.ndim == 4:
            b_w, t_w, m_w, k_w = w.shape
            b_h, _u_h, m_h = h.shape
            l_r, b_r, t_r, m_r1, m_r2 = r.shape
            time_len = None
        else:
            h_len, b_w, t_w, m_w, k_w = w.shape
            h_h, b_h, _u_h, m_h = h.shape
            h_r, l_r, b_r, t_r, m_r1, m_r2 = r.shape
            if h_len != h_h or h_len != h_r:
                raise ValueError("Time-axis lengths do not match")
            time_len = h_len
        if b_w != b_h or b_w != b_r:
            raise ValueError("Sector count does not match across channels/beamformers/coupling")
        if t_w != t_r:
            raise ValueError("Tone count does not match between beamformers and coupling")
        if m_w != m_h or m_w != m_r1 or m_r1 != m_r2:
            raise ValueError("Transmit-antenna dimension does not match across arrays")
        if users_per_bs != k_w:
            raise ValueError("users_per_bs must match the beamformer stream dimension in this reference contract")
        valid_threshold_shapes = {(l_r,)}
        if time_len is not None:
            valid_threshold_shapes.add((time_len, l_r))
        if thresholds.shape not in valid_threshold_shapes:
            raise ValueError(
                f"thresholds must have shape [{l_r}]"
                + (f" or [{time_len},{l_r}]" if time_len is not None else "")
                + f", got {thresholds.shape}"
            )
        if tone_weights.shape != (t_w,):
            raise ValueError(f"tone_weights must have shape [{t_w}], got {tone_weights.shape}")
        if np.any(~np.isfinite(thresholds)) or np.any(thresholds <= 0):
            raise ValueError("thresholds must be finite positive linear powers")
        if np.any(~np.isfinite(tone_weights)) or np.any(tone_weights < 0) or tone_weights.sum() <= 0:
            raise ValueError("tone_weights must be finite, nonnegative, and not all zero")
        if not np.isfinite(noise_power) or noise_power <= 0:
            raise ValueError("noise_power must be a finite positive linear power")
        if not np.all(np.isfinite(w)) or not np.all(np.isfinite(h)) or not np.all(np.isfinite(r)):
            raise ValueError("Bundle arrays contain NaN or infinite values")

        # Hermitian and PSD checks on a bounded sample. Full validation can be costly at paper scale.
        flat = r.reshape((-1, r.shape[-2], r.shape[-1]))
        sample = flat[: min(50, flat.shape[0])]
        herm_errors = [float(np.linalg.norm(a - a.conj().T)) for a in sample]
        herm_err = max(herm_errors, default=0.0)
        if herm_err > 1e-8:
            raise ValueError(f"coupling matrices are not Hermitian; max sample error={herm_err}")
        min_eigenvalue = min((float(np.linalg.eigvalsh(0.5 * (a + a.conj().T)).min()) for a in sample), default=0.0)
        if min_eigenvalue < -1e-9:
            raise ValueError(f"coupling matrices are not PSD; minimum sample eigenvalue={min_eigenvalue}")

        metadata_raw = z["metadata_json"].item()
        metadata = json.loads(str(metadata_raw))
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        return {
            "path": str(path),
            "time_length": time_len,
            "channels_shape": list(h.shape),
            "beamformers_shape": list(w.shape),
            "coupling_shape": list(r.shape),
            "thresholds_shape": list(thresholds.shape),
            "tone_weights_sum": float(tone_weights.sum()),
            "noise_power": noise_power,
            "metadata": metadata,
            "hermitian_sample_error": herm_err,
            "minimum_sample_eigenvalue": min_eigenvalue,
        }
