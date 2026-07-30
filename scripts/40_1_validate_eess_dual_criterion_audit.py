#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="config/eess_dual_criterion_audit_v1.json")
    a=p.parse_args()
    cfg=json.loads((ROOT/a.config).read_text())
    ev=ROOT/cfg["paths"]["evidence"]
    audit=json.loads((ev/"EESS_DUAL_CRITERION_AUDIT.json").read_text())
    gate=json.loads((ev/"EESS_DUAL_CRITERION_GATE_DECISION.json").read_text())
    ts=pd.read_csv(ev/"EESS_DUAL_CRITERION_TIME_SERIES.csv")
    sec=pd.read_csv(ev/"P452_PERCENTILE_SECTOR_DELTAS.csv")
    assert audit["status"]=="PASS_EESS_DUAL_CRITERION_DIAGNOSIS"
    assert gate["status"]=="PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED"
    assert gate["paper_result"] is False
    assert gate["new_p452_matlab_run_required"] is False
    assert gate["new_nibi_channel_generation_required"] is False
    assert gate["local_controller_rerun_required"] is True
    assert gate["recommended_provisional_action_grid_max_db"]==70
    assert len(ts)==587 and len(sec)==57
    assert sec["p0005_minus_p20_coupling_db"].min()>1.6
    assert sec["p0005_minus_p20_coupling_db"].max()<3.2
    cases=audit["case_results"]
    assert cases["short_p0005_multiple"]["historical_policy_exceedance_samples"]==587
    assert cases["long_p20_multiple"]["historical_policy_exceedance_samples"]==587
    assert cases["long_p20_multiple"]["samples_above_60db"]>0
    assert cases["short_p0005_single"]["samples_above_60db"]==0
    print("EESS DUAL-CRITERION STRICT VALIDATION: PASS")
    print(json.dumps(gate,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
