from __future__ import annotations
import csv
import json
from pathlib import Path
import subprocess
import sys


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_return(root: Path) -> None:
    write_json(root / "RETURN_METADATA.json", {
        "pass_array_job_id":"18232438","assembly_job_id":"18232439","seed_rerun_list":[44052],
        "channel_regenerated":False,"gpu_requested":False,"scientific_source_files_modified":False,
        "action_library_definition_changed":False,"automatic_extra_seeds_authorized":False,
    })
    facts={
        "seed_count":30,"cell_count":1350,"primary_point_estimate":0.2504676932746432,
        "primary_lower_95":0.20132723612261208,"primary_upper_95":0.31024908237228865,
        "primary_superiority_met":True,"safety_gates_pass":True,"floor_zero":False,
        "seed_hard_gate_pass_count":17,"floor_violation_user_seconds":14741,
        "floor_violation_user_intervals":3000,"maximum_normalized_floor_shortfall":0.4,
        "floor_reduction_versus_predictive_percent":82.51,"floor_reduction_versus_static_percent":85.54,
        "long_eess_violation_seconds":0,"short_eess_violation_seconds":0,"unresolved_intervals":1000,
        "network_wide_shutdown_intervals":0,"q0_envelope_deployable_actions":0,
    }
    write_json(root / "HOLDOUT_COMPLETION_AUDIT.json", {
        "status":"PASS_COMPLETED_FRESH_V4_5_HOLDOUT_AFTER_NONSCIENTIFIC_REPAIR",
        "source_supported_facts":facts,"paper_writing_authorized":True,
        "automatic_extra_seeds_authorized":False,"automatic_algorithm_tuning_authorized":False,
        "next_gate":"FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION",
    })
    write_json(root / "merged" / "PHASE1_MERGED_AUDIT.json", {
        "seed_count":30,"cell_count":1350,"valid_holdout_result":True,"safety_gates_pass":True,
        "primary_superiority_met":True,"floor_zero":False,"seed_hard_gate_pass_count":17,
        "primary_bootstrap":{"point_estimate":0.2504676932746432,"lower_95":0.20132723612261208,"upper_95":0.31024908237228865},
    })
    write_json(root / "seed_44052" / "result" / "SEED_RESULT.json", {
        "campaign_seed":44052,"scientific_exit_code":42,"candidate_hard_gates_pass":False,
    })
    write_json(root / "seed_44052" / "result" / "IMPLEMENTATION_CAPACITY_OVERLAY.json", {
        "classification":"IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING",
        "action_library_definition_changed":False,
    })
    for i in range(5):
        p=root / "pass_outputs" / f"pass_{i}"; p.mkdir(parents=True); (p / "PASS_RESULT.json").write_text("{}\n")
    slurm_lines=[
        "18232439|fr3-v45-s44052-assemble-r2|def-rsadve_cpu|COMPLETED|0:0|00:00:18||4G|x",
        "18232438_0|fr3-v45-s44052-pass-r2|def-rsadve_cpu|COMPLETED|0:0|00:02:12||4G|x",
        "18232438_1|fr3-v45-s44052-pass-r2|def-rsadve_cpu|COMPLETED|0:0|00:02:56||4G|x",
        "18232438_2|fr3-v45-s44052-pass-r2|def-rsadve_cpu|COMPLETED|0:0|00:12:49||4G|x",
        "18232438_3|fr3-v45-s44052-pass-r2|def-rsadve_cpu|COMPLETED|0:0|00:13:42||4G|x",
        "18232438_4|fr3-v45-s44052-pass-r2|def-rsadve_cpu|COMPLETED|0:0|00:12:09||4G|x",
    ]
    (root / "slurm").mkdir(parents=True)
    (root / "slurm" / "sacct_completion_r2.txt").write_text("\n".join(slurm_lines)+"\n")
    index=root / "merged" / "PHASE1_SEED_RESULT_HASH_INDEX.csv"
    index.parent.mkdir(parents=True, exist_ok=True)
    with index.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["campaign_seed","sha256"]); w.writeheader()
        for seed in range(44030,44060): w.writerow({"campaign_seed":seed,"sha256":"0"*64})
    (root / "holdout_key_results.tex").write_text("0.2505 0.2013 0.3102\n")


def test_audit_retrieved_return(tmp_path: Path):
    root=tmp_path / "return"; root.mkdir(); build_return(root)
    package_root=Path(__file__).resolve().parents[1]
    output=tmp_path / "audit.json"
    result=subprocess.run([
        sys.executable,str(package_root / "scripts" / "audit_retrieved_return.py"),
        "--return-root",str(root),"--output-json",str(output)
    ],text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "RETRIEVED_HOLDOUT_INDEPENDENT_AUDIT=PASS" in result.stdout
    assert json.loads(output.read_text())["paper_writing_authorized"] is True


def test_contract_is_retrieval_only():
    package_root=Path(__file__).resolve().parents[1]
    contract=json.loads((package_root / "config" / "RETRIEVAL_CONTRACT.json").read_text())
    policy=contract["execution_policy"]
    assert policy["retrieval_only"] is True
    assert policy["remote_computation_authorized"] is False
    assert policy["new_seed_execution_authorized"] is False
    assert policy["single_ssh_transfer_session"] is True


def test_failure_packager(tmp_path: Path):
    package_root=Path(__file__).resolve().parents[1]
    log=tmp_path / "x.log"; log.write_text("failure\n")
    result=subprocess.run([
        sys.executable,str(package_root / "scripts" / "package_local_failure.py"),
        "--output-dir",str(tmp_path),"--package-root",str(package_root),
        "--log",str(log),"--reason","test"
    ],text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    archives=list(tmp_path.glob("FR3_V45_HOLDOUT_COMPLETION_R2_RETRIEVAL_ONLY_LOCAL_FAILURE_*.zip"))
    assert len(archives)==1
    assert Path(str(archives[0])+".sha256").is_file()
