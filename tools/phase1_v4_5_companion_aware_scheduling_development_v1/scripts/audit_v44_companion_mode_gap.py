#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, io, json, zipfile
from pathlib import Path
from collections import Counter

EXPECTED_RETURN_SHA = "b3ebce19ade5379313f76d4e5d4ddb265b1c983cf4f9d83e3e79035657ae113c"
EXPECTED_DIAG_SHA = "4d8181b7b328d12dad0070e2e531bb4661e87e8aaf1c6a8e59184bf66ae0e62e"
SEEDS = [44001,44007,44008,44017,44024,44025,44028]

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--v44-return-zip',type=Path,required=True)
    p.add_argument('--diagnosis-zip',type=Path,required=True)
    p.add_argument('--output-json',type=Path,required=True)
    a=p.parse_args()
    if digest(a.v44_return_zip)!=EXPECTED_RETURN_SHA: raise RuntimeError('v4.4 return SHA mismatch')
    if digest(a.diagnosis_zip)!=EXPECTED_DIAG_SHA: raise RuntimeError('diagnosis SHA mismatch')
    usermap={}
    with zipfile.ZipFile(a.diagnosis_zip) as zd:
        rd=zd.namelist()[0].split('/')[0]
        for seed in SEEDS:
            arr=json.loads(zd.read(f'{rd}/seed_diagnostics/seed_{seed}/INTERVAL_FEASIBILITY_DIAGNOSIS.json'))
            for rec in arr:
                for u in rec['users']:
                    usermap[(seed,int(u['user_index']))]=(int(u['serving_sector']),int(u['serving_stream']))
    residual=0; omitted_intervals=0; omitted_total=0; max_modes=0; critical_counts=Counter(); stream_counts=Counter()
    with zipfile.ZipFile(a.v44_return_zip) as z:
        r=z.namelist()[0].split('/')[0]
        summary=json.loads(z.read(f'{r}/merged/V44_SCHEDULING_DEVELOPMENT_SUMMARY.json'))
        if int(summary['scheduling_failure_interval_count'])!=523: raise RuntimeError('certified residual count mismatch')
        for seed in SEEDS:
            passes=json.loads(z.read(f'{r}/seed_results/seed_{seed}/result/PASS_AUDITS.json'))
            for pa in passes:
                phases=pa['phase_records']
                for rec in pa['candidate_interval_records']:
                    if rec['chosen_action_class']!='NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND': continue
                    residual += 1
                    phase=next(v for v in phases if v['start_interval']<=rec['interval_index']<v['stop_interval_exclusive'])
                    n=int(phase['active_streams_per_sector'])
                    targets=Counter(usermap[(seed,int(u))][0] for u in rec['pre_repair_violating_users'])
                    omitted=sum(max(0,n-count) for count in targets.values())
                    omitted_total += omitted
                    omitted_intervals += int(omitted>0)
                    critical_counts[len(targets)] += 1
                    stream_counts[n] += 1
                    max_modes=max(max_modes,(n+3)**len(targets))
    record={
        'schema_version':1,
        'status':'PASS_CERTIFIED_V44_COMPANION_MODE_GAP_AUDIT',
        'certified_v44_residual_intervals':residual,
        'residual_intervals_with_omitted_companion_singletons':omitted_intervals,
        'omitted_companion_singleton_count_sum':omitted_total,
        'active_stream_count_distribution':dict(sorted(stream_counts.items())),
        'critical_sector_count_distribution':dict(sorted(critical_counts.items())),
        'maximum_companion_completed_mode_count':max_modes,
        'scientific_inference':'The v4.4 continuous-infeasibility results certify only its target-only mode library; every residual interval omitted at least one active companion singleton.',
        'next_test':'COMPANION_AWARE_FIXED_ASSOCIATION_SCHEDULING_BEFORE_REASSIGNMENT_OR_ADMISSION',
    }
    if not (residual==omitted_intervals==523 and max_modes<=625): raise RuntimeError(record)
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    print('CERTIFIED_V44_COMPANION_MODE_GAP_AUDIT=PASS')
    print(f'CERTIFIED_V44_RESIDUAL_INTERVALS={residual}')
    print(f'RESIDUAL_INTERVALS_WITH_OMITTED_COMPANION_SINGLETONS={omitted_intervals}')
    print(f'MAXIMUM_COMPANION_COMPLETED_MODE_COUNT={max_modes}')
    return 0
if __name__=='__main__': raise SystemExit(main())
