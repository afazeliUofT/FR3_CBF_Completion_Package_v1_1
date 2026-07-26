from __future__ import annotations

import json
from pathlib import Path

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_json


def is_real_audit(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("mode") == "real"
    except Exception:
        return False


def main() -> int:
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    add(
        "S1 real audit",
        is_real_audit(ROOT / "results/s1_adequacy/audit.json"),
        "Run real S1 with reviewed paired links and official grids.",
    )
    add(
        "S1 reviewed freeze decision",
        (ROOT / "results/s1_adequacy/regulatory_constants_candidate.yaml").exists(),
        "Freeze only after nominal and sensitivity all-link PASS.",
    )
    add("E1 real result", is_real_audit(ROOT / "results/e1_static_fs/audit.json"), "Use real Sionna/P.452 bundle.")
    add("E2 real result", is_real_audit(ROOT / "results/e2_dynamic_fs/audit.json"), "Use validated dynamic coupling.")
    add("E3 real result", is_real_audit(ROOT / "results/e3_tracking_eess/audit.json"), "Use archived TLE/station/coupling.")
    add("Calibration real result", is_real_audit(ROOT / "results/calibration/calibration_report.json"), "Use held-out real/high-fidelity residuals.")
    add(
        "Runtime benchmark",
        is_real_audit(ROOT / "results/runtime/audit.json")
        and (ROOT / "results/runtime/runtime_summary.csv").exists(),
        "Benchmark central and layered implementations at paper scale in real mode.",
    )
    add(
        "Real data provenance",
        (ROOT / "data/real/DATA_PROVENANCE.md").exists(),
        "Document sources, retrieval dates, transformations, and hashes.",
    )

    reg = load_yaml(ROOT / "config/regulatory_constants.yaml")
    open_items = [item for item in reg.get("open_items", []) if item.get("status") == "OPEN"]
    add("Regulatory/model open items closed", len(open_items) == 0, f"OPEN items: {[x.get('id') for x in open_items]}")

    ready = all(item["pass"] for item in checks)
    report = {"submission_ready": ready, "checks": checks}
    write_json(ROOT / "results/submission_readiness.json", report)
    for item in checks:
        print(("PASS" if item["pass"] else "FAIL"), "-", item["name"], "-", item["detail"])
    print("SUBMISSION READY:", ready)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
