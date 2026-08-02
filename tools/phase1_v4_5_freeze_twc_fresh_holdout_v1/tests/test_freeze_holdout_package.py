from __future__ import annotations
import hashlib,json,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def test_freeze_audit(tmp_path:Path)->None:
 c=subprocess.run([sys.executable,str(ROOT/'scripts/audit_and_freeze_v45.py'),'--package-root',str(ROOT),'--output-dir',str(tmp_path)],capture_output=True,text=True)
 assert c.returncode==0,c.stdout+c.stderr
 assert 'V45_FREEZE_DECISION=PASS_STOP_ALGORITHM_TUNING' in c.stdout
 v=json.loads((tmp_path/'V45_FREEZE_VERDICT.json').read_text())
 assert v['v45_marginal_intervals_closed_over_v44']==4
 assert v['automatic_extra_seed_or_algorithm_tuning_authorized'] is False

def test_job_package_binding_and_scope(tmp_path:Path)->None:
 contract=json.loads((ROOT/'config/FREEZE_HOLDOUT_CONTRACT.json').read_text())
 zpath=ROOT/'immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip'
 assert sha(zpath)==contract['job_package_sha256']
 with zipfile.ZipFile(zpath) as z:
  assert z.testzip() is None; z.extractall(tmp_path)
 job=json.loads((tmp_path/'JOB_PACKAGE_CONTRACT.json').read_text())
 assert job['campaign_seed_list']==list(range(44030,44060))
 assert job['primary_method']=='candidate_v4_5_companion_aware_protected_subband_scheduling'
 assert job['rorqual_resource_template']['time_limit']=='00:10:00'
 assert job['rorqual_resource_template']['memory_gib']==16

def test_native_authorization_guard(tmp_path:Path)->None:
 zpath=ROOT/'immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip'; job=tmp_path/'job'; job.mkdir()
 with zipfile.ZipFile(zpath) as z: z.extractall(job)
 token=tmp_path/'token.json'
 c=subprocess.run([sys.executable,str(ROOT/'scripts/issue_fresh_holdout_authorization.py'),'--job-package-root',str(job),'--authorization-contract',str(ROOT/'config/FREEZE_HOLDOUT_CONTRACT.json'),'--output',str(token),'--expiry-days','2','--authorization-package-sha256','a'*64],capture_output=True,text=True)
 assert c.returncode==0,c.stdout+c.stderr
 v=json.loads(token.read_text())
 assert v['allowed_seeds']==list(range(44030,44060))
 assert v['automatic_extra_seed_or_algorithm_tuning_authorized'] is False
 assert token.stat().st_mode & 0o777 == 0o600

def _seed(run:Path,seed:int)->None:
 r=run/'results'/f'seed_{seed}'; result=r/'result'; channel=r/'channel'; result.mkdir(parents=True); channel.mkdir()
 pa={'candidate_hard_gates':{'long_violation_seconds':0,'short_violation_seconds':0,'strict_local_scope_gate':'PASS','strict_post_mode_selected_power_gate':'PASS','q0_envelope_deployable_actions':0,'network_wide_shutdown_intervals':0}}
 audit={'campaign_seed':seed,'candidate_hard_gates_pass':True,'scientific_exit_code':0,'pass_audits':[pa]*5}
 (result/'SEED_RESULT.json').write_text(json.dumps(audit)+'\n'); (result/'RESULT_FILE_MANIFEST.json').write_text('{}\n'); (result/'CELL_SUMMARY.csv').write_text('method_id,pass_slot\ncandidate_v4_5_companion_aware_protected_subband_scheduling,0\n'); (result/'PRIMARY_PAIRED_EFFECTS.csv').write_text('pass_slot,candidate_minus_static_final_pf\n0,1\n'); (channel/'CHANNEL_RECORD.json').write_text(json.dumps({'campaign_seed':seed})+'\n')
 zp=r/f'FR3_PHASE1_SEED_{seed}_RETURN.zip'
 with zipfile.ZipFile(zp,'w') as z:z.writestr(f'FR3_PHASE1_SEED_{seed}_RETURN/SEED_RETURN_METADATA.json','{}\n')
 Path(str(zp)+'.sha256').write_text(f'{sha(zp)}  {zp.name}\n')

def test_synthetic_holdout_packaging_and_audit(tmp_path:Path)->None:
 run=tmp_path/'run'; run.mkdir(); job=tmp_path/'job'; job.mkdir(); out=tmp_path/'out'; out.mkdir()
 with zipfile.ZipFile(ROOT/'immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip') as z:z.extractall(job)
 for seed in range(44030,44060): _seed(run,seed)
 merged=run/'merged'; merged.mkdir()
 audit={'status':'PASS_FRESH_V4_5_HOLDOUT_SAFETY_UTILITY_AND_ZERO_FLOOR_FAILURE','valid_holdout_result':True,'primary_superiority_met':True,'floor_zero':True,'primary_bootstrap':{'point_estimate':.3,'lower_95':.2,'upper_95':.4},'next_gate':'FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_LIMITATION_SECTION','seed_count':30,'safety_gates_pass':True,'floor_metrics':{'floor_violation_user_seconds':0},'scheduling_summary':{'failure_intervals':0}}
 (merged/'PHASE1_MERGED_AUDIT.json').write_text(json.dumps(audit)+'\n')
 meta=tmp_path/'token_meta.json'; meta.write_text(json.dumps({'authorization_token_sha256':'b'*64})+'\n')
 c=subprocess.run([sys.executable,str(ROOT/'scripts/package_fresh_holdout_return.py'),'--run-root',str(run),'--job-package-root',str(job),'--authorization-contract',str(ROOT/'config/FREEZE_HOLDOUT_CONTRACT.json'),'--authorization-token-metadata',str(meta),'--authorization-package-sha256','c'*64,'--array-job-id','100','--merge-job-id','101','--finalizer-job-id','102','--output-dir',str(out)],capture_output=True,text=True)
 assert c.returncode==0,c.stdout+c.stderr
 zp=out/'FR3_RORQUAL_V4_5_FRESH_HOLDOUT_100.zip'
 a=subprocess.run([sys.executable,str(ROOT/'scripts/audit_fresh_holdout_return.py'),'--return-zip',str(zp),'--twc-output-dir',str(tmp_path/'paper')],capture_output=True,text=True)
 assert a.returncode==0,a.stdout+a.stderr
 assert 'HOLDOUT_SEED_RETURN_COUNT=30' in a.stdout
 assert (tmp_path/'paper/generated_holdout_results.tex').is_file()

def test_claim_boundary_and_no_token()->None:
 text=(ROOT/'twc_draft/FR3_TWC_v4_5_manuscript_start.tex').read_text()
 assert 'feasibility-conditioned' in text
 assert 'does not claim hardware calibration or regulatory compliance' in text
 forbidden=[]
 for p in ROOT.rglob('*.json'):
  try:v=json.loads(p.read_text())
  except Exception:continue
  if 'TOKEN' in p.name.upper() and v.get('execution_authorized') is True: forbidden.append(p)
 assert not forbidden


def test_synthetic_feasibility_conditioned_holdout_is_valid(tmp_path:Path)->None:
    run=tmp_path/'run'; run.mkdir(); job=tmp_path/'job'; job.mkdir(); out=tmp_path/'out'; out.mkdir()
    with zipfile.ZipFile(ROOT/'immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip') as z:z.extractall(job)
    for seed in range(44030,44060):
        _seed(run,seed)
        audit_path=run/'results'/f'seed_{seed}'/'result'/'SEED_RESULT.json'
        audit=json.loads(audit_path.read_text()); audit['candidate_hard_gates_pass']=False; audit['scientific_exit_code']=42
        audit_path.write_text(json.dumps(audit)+'\n')
    merged=run/'merged'; merged.mkdir()
    audit={'status':'PASS_FRESH_V4_5_HOLDOUT_SAFETY_AND_UTILITY_FEASIBILITY_CONDITIONED_FLOOR','valid_holdout_result':True,'primary_superiority_met':True,'floor_zero':False,'primary_bootstrap':{'point_estimate':.25,'lower_95':.1,'upper_95':.4},'next_gate':'FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_LIMITATION_SECTION','seed_count':30,'safety_gates_pass':True,'floor_metrics':{'floor_violation_user_seconds':100},'scheduling_summary':{'failure_intervals':10}}
    (merged/'PHASE1_MERGED_AUDIT.json').write_text(json.dumps(audit)+'\n')
    meta=tmp_path/'token_meta.json'; meta.write_text(json.dumps({'authorization_token_sha256':'b'*64})+'\n')
    c=subprocess.run([sys.executable,str(ROOT/'scripts/package_fresh_holdout_return.py'),'--run-root',str(run),'--job-package-root',str(job),'--authorization-contract',str(ROOT/'config/FREEZE_HOLDOUT_CONTRACT.json'),'--authorization-token-metadata',str(meta),'--authorization-package-sha256','c'*64,'--array-job-id','200','--merge-job-id','201','--finalizer-job-id','202','--output-dir',str(out)],capture_output=True,text=True)
    assert c.returncode==0,c.stdout+c.stderr
    zp=out/'FR3_RORQUAL_V4_5_FRESH_HOLDOUT_200.zip'
    a=subprocess.run([sys.executable,str(ROOT/'scripts/audit_fresh_holdout_return.py'),'--return-zip',str(zp)],capture_output=True,text=True)
    assert a.returncode==0,a.stdout+a.stderr
    assert 'HOLDOUT_FLOOR_ZERO=False' in a.stdout
    assert 'HOLDOUT_VALID_RESULT=True' in a.stdout
