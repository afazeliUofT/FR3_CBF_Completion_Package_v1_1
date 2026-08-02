from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _load_replay(package_root: Path):
    path = package_root / "scripts/replay_v44_scheduling_seed.py"
    spec = importlib.util.spec_from_file_location("v44_replay_infra_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def _load_merge(package_root: Path):
    path = package_root / "scripts/merge_v44_scheduling_development.py"
    spec = importlib.util.spec_from_file_location("v44_merge_infra_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_numpy_json_serialization_regression(
    package_root: Path,
    tmp_path: Path,
) -> None:
    module = _load_merge(package_root)
    output = tmp_path / "merge.json"
    module.write_json(
        output,
        {
            "array": np.asarray([1.0, 2.0]),
            "scalar": np.float64(3.5),
        },
    )
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == {"array": [1.0, 2.0], "scalar": 3.5}

def test_numpy_json_serialization_regression(
    package_root: Path,
    tmp_path: Path,
) -> None:
    module = _load_replay(package_root)
    output = tmp_path / "nested.json"
    value = [
        {
            "candidate_action_diagnostics": {
                "array": np.asarray([[1.0, 2.0], [3.0, 4.0]]),
                "float": np.float64(1.25),
                "integer": np.int64(7),
                "boolean": np.bool_(True),
            }
        }
    ]
    module.write_json(output, value)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded[0]["candidate_action_diagnostics"]["array"] == [
        [1.0, 2.0],
        [3.0, 4.0],
    ]
    assert loaded[0]["candidate_action_diagnostics"]["float"] == 1.25
    assert loaded[0]["candidate_action_diagnostics"]["integer"] == 7
    assert loaded[0]["candidate_action_diagnostics"]["boolean"] is True


def test_unknown_json_object_remains_rejected(package_root: Path) -> None:
    module = _load_replay(package_root)

    class Unsupported:
        pass

    try:
        module._json_default(Unsupported())
    except TypeError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("unsupported object was silently converted")


def test_prior_failure_and_preliminary_salvage_audit(
    package_root: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(package_root / "scripts/audit_v44_infrastructure_failure.py"),
            "--package-root",
            str(package_root),
            "--output-json",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["root_cause"] == "NUMPY_NDARRAY_JSON_SERIALIZATION"
    assert record["prior_worker_root_exception_count"] == 11
    assert record["prior_completed_trace_file_count"] == 110
    assert record["preliminary_comparator_maximum_absolute_error"] == 0.0
    assert record["v43_floor_violation_user_seconds"] == 19994
    assert record["preliminary_v44_floor_violation_user_seconds"] == 6540
    assert record["v43_unresolved_intervals"] == 1736
    assert record["preliminary_v44_unresolved_intervals"] == 523
    assert record["preliminary_hard_gate_pass_seeds"] == [
        44013,
        44018,
        44026,
        44027,
    ]
    assert record["preliminary_long_eess_violation_seconds"] == 0
    assert record["preliminary_short_eess_violation_seconds"] == 0
    assert record["preliminary_strict_local_scope"] == "PASS"
    assert record["preliminary_strict_post_mode_power"] == "PASS"
    assert record["preliminary_q0_headroom_actions"] == 0


def test_scientific_candidate_modules_are_byte_identical(
    package_root: Path,
) -> None:
    contract = json.loads(
        (
            package_root
            / "config/V44_INFRASTRUCTURE_REPAIR_CONTRACT.json"
        ).read_text(encoding="utf-8")
    )
    import hashlib

    for relative, expected in contract[
        "candidate_scientific_source_sha256"
    ].items():
        actual = hashlib.sha256(
            (package_root / relative).read_bytes()
        ).hexdigest()
        assert actual == expected
