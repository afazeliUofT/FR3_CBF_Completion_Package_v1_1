from __future__ import annotations
import ast, json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def test_config():
    c=json.loads((ROOT/"config/eess_dual_criterion_audit_v1.json").read_text())
    assert c["criteria"]["long_term"]["p452_time_percentage"]==20.0
    assert c["criteria"]["long_term"]["threshold_dbw_per_10mhz"]==-150.0
    assert c["criteria"]["short_term"]["p452_time_percentage"]==0.005
    assert c["criteria"]["short_term"]["threshold_dbw_per_10mhz"]==-133.0
    assert c["criteria"]["both_required"] is True
def test_db_factors():
    assert np.isclose(10*np.log10(10**(3/10)),3.0)
    assert np.isclose(10*np.log10(0.9),-0.4575749056067512)
def test_sources_parse():
    for rel in [
        "scripts/40_0_run_eess_dual_criterion_audit.py",
        "scripts/40_1_validate_eess_dual_criterion_audit.py",
        "scripts/40_2_sync_eess_dual_criterion_status.py",
        "scripts/40_3_build_eess_dual_criterion_review_bundle.py",
        "tests/test_eess_dual_criterion_audit.py",
    ]:
        p=ROOT/rel; ast.parse(p.read_text(),filename=str(p))
