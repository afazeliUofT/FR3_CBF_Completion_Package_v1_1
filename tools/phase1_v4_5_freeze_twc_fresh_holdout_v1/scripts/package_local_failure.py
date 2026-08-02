#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import shutil, tempfile, zipfile

def sha(path: Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); p.add_argument('--log',required=True); p.add_argument('--stage',required=True); p.add_argument('--exit-code',type=int,required=True); a=p.parse_args()
 out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'); name=f'FR3_V45_FREEZE_HOLDOUT_LOCAL_FAILURE_{stamp}'
 with tempfile.TemporaryDirectory(prefix='fr3-v45-local-failure-') as t:
  root=Path(t)/name; root.mkdir()
  meta={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),'status':'LOCAL_ORCHESTRATION_FAILURE','stage':a.stage,'exit_code':a.exit_code,'holdout_result':'UNKNOWN_OR_INCOMPLETE','automatic_extra_probes_authorized':False}
  (root/'FAILURE_METADATA.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
  log=Path(a.log)
  if log.is_file(): shutil.copy2(log,root/'LOCAL_WSL_ORCHESTRATOR.log')
  lines=[]
  for f in sorted(root.rglob('*')):
   if f.is_file() and f.name!='RETURN_MANIFEST.sha256': lines.append(f'{sha(f)}  {f.relative_to(root).as_posix()}')
  (root/'RETURN_MANIFEST.sha256').write_text('\n'.join(lines)+'\n')
  zpath=out/f'{name}.zip'
  with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
   for f in sorted(root.rglob('*')):
    if f.is_file(): z.write(f,f.relative_to(root.parent).as_posix())
  digest=sha(zpath); Path(str(zpath)+'.sha256').write_text(f'{digest}  {zpath.name}\n')
 print('LOCAL_FAILURE_RETURN_ZIP='+str(zpath)); print('LOCAL_FAILURE_RETURN_ZIP_SHA256='+digest)
 return 0
if __name__=='__main__': raise SystemExit(main())
