#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='config/practical_architecture_mapping_v1.json');a=p.parse_args();cfg=json.loads((ROOT/a.config).read_text());e=ROOT/cfg['paths']['evidence_dir'];r=ROOT/cfg['paths']['results_dir'];c=ROOT/cfg['paths']['campaign_candidate_dir'];out=ROOT/cfg['paths']['review_bundle'];out.parent.mkdir(parents=True,exist_ok=True);files=[]
 for root in (e,r,c):
  files.extend(path for path in root.rglob('*') if path.is_file() and path!=out)
 for path in [ROOT/'config/practical_architecture_mapping_v1.json',ROOT/'src/fr3_cbf/practical_architecture_mapping.py',ROOT/'scripts/44_0_run_practical_architecture_mapping.py',ROOT/'docs/PRACTICAL_64T64R_ARCHITECTURE_MAPPING.md',ROOT/'docs/PHASE1_CAMPAIGN_REVIEW_PROTOCOL.md',ROOT/'source_inputs/practical_architecture_mapping_v1/ARCHITECTURE_SOURCE_RECORDS.json',ROOT/'source_inputs/practical_architecture_mapping_v1/SIONNA_8X8_DUAL_PORT_ORDER.csv',ROOT/'PROJECT_STATUS.md',ROOT/'NEXT_IMMEDIATE_STEP.md']:
  if not path.is_file():raise FileNotFoundError(path)
  files.append(path)
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as z:
  for path in sorted(set(files)):z.write(path,path.relative_to(ROOT).as_posix())
 with zipfile.ZipFile(out) as z:
  bad=z.testzip();
  if bad:raise RuntimeError(bad)
 Path(str(out)+'.sha256').write_text(f"{sha(out)}  {out.name}\n");print('PRACTICAL ARCHITECTURE/PHASE1 REVIEW BUNDLE: PASS');print('Review bundle:',out);print('Review bundle SHA-256:',sha(out));return 0
if __name__=='__main__':raise SystemExit(main())
