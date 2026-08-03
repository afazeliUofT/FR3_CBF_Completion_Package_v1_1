#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

p=argparse.ArgumentParser()
p.add_argument('--output-dir',required=True)
p.add_argument('--package-root',required=True)
p.add_argument('--log',action='append',default=[])
p.add_argument('--reason',required=True)
a=p.parse_args()
out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
name=f'FR3_V45_HOLDOUT_COMPLETION_R2_RETRIEVAL_ONLY_LOCAL_FAILURE_{stamp}'
archive=out/f'{name}.zip'
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/name; root.mkdir()
    meta={'schema_version':1,'status':'LOCAL_RETRIEVAL_ONLY_FAILURE','reason':a.reason,'remote_computation_authorized':False,'new_seed_execution_authorized':False,'created_utc':datetime.now(timezone.utc).isoformat()}
    (root/'FAILURE_METADATA.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
    for item in a.log:
        source=Path(item)
        if source.is_file(): shutil.copy2(source,root/source.name)
    pkg=Path(a.package_root)
    for rel in ('PACKAGE_VERSION.json','config/RETRIEVAL_CONTRACT.json'):
        source=pkg/rel
        if source.is_file():
            target=root/'package'/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
    lines=[]
    for source in sorted(root.rglob('*')):
        if source.is_file() and source.name!='RETURN_MANIFEST.sha256':
            lines.append(f'{digest(source)}  {source.relative_to(root).as_posix()}\n')
    (root/'RETURN_MANIFEST.sha256').write_text(''.join(lines))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zf:
        for source in sorted(root.rglob('*')):
            if source.is_file(): zf.write(source,source.relative_to(Path(td)).as_posix())
with zipfile.ZipFile(archive) as zf:
    if zf.testzip() is not None: raise RuntimeError('failure ZIP CRC error')
sha=digest(archive)
Path(str(archive)+'.sha256').write_text(f'{sha}  {archive.name}\n')
print('LOCAL_FAILURE_RETURN_PACKAGING=PASS')
print('LOCAL_FAILURE_RETURN_ZIP='+str(archive))
print('LOCAL_FAILURE_RETURN_ZIP_SHA256='+sha)
