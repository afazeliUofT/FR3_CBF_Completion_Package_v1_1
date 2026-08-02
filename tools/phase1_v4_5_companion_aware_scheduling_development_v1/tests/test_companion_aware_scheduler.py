from __future__ import annotations
import numpy as np
from fr3_cbf import protected_subband_scheduler as old
from fr3_cbf import companion_aware_scheduler as new


def _problem():
    gain=np.zeros((2,1,2),dtype=float)
    gain[0,0,0]=10.0; gain[0,0,1]=10.0
    gain[1,0,0]=10.0; gain[1,0,1]=10.0
    common=dict(
        gain_user_sector_stream=gain,
        baseline_stream_scale=np.array([[0.2,0.2]]),
        other_weighted_rate=np.zeros(2),
        active_user=np.array([True,True]),
        eligible_user=np.array([True,True]),
        floors=np.array([1.5,1.5]),
        serving_bs=np.array([0,0]),
        serving_stream=np.array([0,1]),
        protected_noise_w=1.0,
        protected_weight=1.0,
        long_kappa_second_sector=np.zeros((1,1)),
        short_kappa_second_sector=np.zeros((1,1)),
        leakage_sector_stream=np.zeros((1,2)),
        long_allowance_second=np.ones(1),
        short_allowance_second=np.ones(1),
        coupling_uplift_db=0.0,
        actual_stream_power=np.ones((1,2)),
        violating_users=[0],
    )
    return common


def test_companion_singleton_completion_closes_synthetic_gap():
    old_out=old.schedule_interval(**_problem())
    new_out=new.schedule_interval(**_problem())
    assert not old_out.feasible
    assert new_out.feasible
    labels={r['label'] for r in new_out.schedule_records}
    assert any('singleton_s1' in label for label in labels)
    assert new_out.floor_violation_count==0


def test_companion_modes_include_all_active_stream_singletons():
    common=_problem()
    modes,critical=new.generate_schedule_modes(
        gain_user_sector_stream=common['gain_user_sector_stream'],
        baseline_stream_scale=common['baseline_stream_scale'],
        active_user=common['active_user'],
        serving_bs=common['serving_bs'],
        serving_stream=common['serving_stream'],
        violating_users=[0],
        guard_sector_limit=0,
    )
    labels={m.label for m in modes}
    assert critical==(0,)
    assert any('singleton_s0' in label for label in labels)
    assert any('singleton_s1' in label for label in labels)


def test_observed_residual_mode_bound_is_supported():
    assert new.MAX_MODE_COUNT >= 625
    assert len(list(new._candidate_guard_subsets(range(8),4))) == 162
    assert all(len(v)<=4 for v in new._candidate_guard_subsets(range(8),4))


def test_candidate_module_binds_companion_scheduler_constants():
    from fr3_cbf import candidate_v4_5_companion_aware_campaign as candidate
    assert candidate.companion_scheduler.SLOTS_PER_SECOND == 2000
    assert candidate.companion_scheduler.MAX_DEPLOYABLE_GUARD_SECTORS == 4


def test_release_wiring_and_fair_resource_contract(package_root):
    pack=(package_root/'scripts/package_v45_companion_aware_return.py').read_text(encoding='utf-8')
    remote=(package_root/'wrappers/REMOTE_ORCHESTRATE_V45_COMPANION_AWARE_DEVELOPMENT.sh').read_text(encoding='utf-8')
    local=(package_root/'wrappers/RUN_V45_COMPANION_AWARE_DEVELOPMENT_FROM_WSL.sh').read_text(encoding='utf-8')
    assert 'FR3_RORQUAL_V4_5_COMPANION_AWARE_DEVELOPMENT_' in pack
    assert 'V45_COMPANION_AWARE_DEVELOPMENT_SUMMARY.json' in pack
    assert 'candidate_v4_5_companion_aware_campaign.py' in pack
    assert 'CERTIFIED_V44_COMPANION_MODE_GAP_AUDIT.json' in pack
    assert 'FR3_RORQUAL_V4_5_COMPANION_AWARE_DEVELOPMENT_18154672.zip' not in remote
    assert 'FR3_RORQUAL_V4_4_SCHEDULING_INFRA_REPAIR_R1_18154672.zip' in remote
    assert '--package-root "$PACKAGE_ROOT"' in remote
    assert '--time=00:06:00' in remote
    assert 'WORKER_WALLTIME=00:06:00' in remote
    assert 'WORKER_WALLTIME=00:06:00' in local



def test_v45_complete_return_packaging_and_verification(package_root, tmp_path):
    import json, subprocess, sys
    run=tmp_path/'run'; out=tmp_path/'out'; (run/'merged').mkdir(parents=True); out.mkdir()
    seeds=[44001,44007,44008,44013,44017,44018,44024,44025,44026,44027,44028]
    for seed in seeds:
        result=run/'tasks'/f'seed_{seed}'/'result'; result.mkdir(parents=True)
        (result/'V45_COMPANION_AWARE_SEED_RESULT.json').write_text(json.dumps({'campaign_seed':seed,'status':'PASS'})+'\n')
        (result/'CELL_SUMMARY.csv').write_text('method_id,pass_slot\ncandidate_v4_5_companion_aware_protected_subband_scheduling,0\n')
    summary={
        'status':'PASS_V4_5_COMPANION_AWARE_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT',
        'next_repair_decision':'FREEZE_V4_5_BEGIN_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_IN_PARALLEL',
        'next_gate':'FREEZE_V4_5_START_13_PAGE_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_44030_44059_IN_PARALLEL',
    }
    (run/'merged'/'V45_COMPANION_AWARE_DEVELOPMENT_SUMMARY.json').write_text(json.dumps(summary)+'\n')
    pack=subprocess.run([sys.executable,str(package_root/'scripts/package_v45_companion_aware_return.py'),'--run-root',str(run),'--package-root',str(package_root),'--array-job-id','999','--merge-job-id','1000','--output-dir',str(out)],capture_output=True,text=True)
    assert pack.returncode==0, pack.stdout+pack.stderr
    archive=next(out.glob('*.zip')); digest=next(line.split('=',1)[1] for line in pack.stdout.splitlines() if line.startswith('REMOTE_RETURN_ZIP_SHA256='))
    verify_json=tmp_path/'verify.json'
    verify=subprocess.run([sys.executable,str(package_root/'scripts/verify_v45_companion_aware_return.py'),'--return-zip',str(archive),'--expected-sha256',digest,'--output-json',str(verify_json)],capture_output=True,text=True)
    assert verify.returncode==0, verify.stdout+verify.stderr
    record=json.loads(verify_json.read_text())
    assert record['return_completeness']=='COMPLETE'
    assert record['failed_seed_return_count']==11
    assert record['scientific_pass'] is True
