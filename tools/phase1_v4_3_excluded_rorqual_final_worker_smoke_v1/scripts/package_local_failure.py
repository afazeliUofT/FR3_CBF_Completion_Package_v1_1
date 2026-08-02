#!/usr/bin/env python3
"""Package local WSL preflight/orchestration evidence after an unexpected failure."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--local-return', required=True)
    p.add_argument('--exit-code', required=True, type=int)
    p.add_argument('--command', required=True)
    args=p.parse_args()
    local=Path(args.local_return).expanduser().resolve(); local.mkdir(parents=True,exist_ok=True)
    output=local/'FR3_V4_3_RORQUAL_FINAL_WORKER_SMOKE_LOCAL_FAILURE.zip'
    with tempfile.TemporaryDirectory(prefix='fr3-local-failure-') as t:
        temp=Path(t); payload=temp/'FR3_V4_3_RORQUAL_FINAL_WORKER_SMOKE_LOCAL_FAILURE'; payload.mkdir()
        for path in sorted(local.rglob('*')):
            if path.is_file() and path != output and not path.name.endswith('.zip.sha256'):
                rel=path.relative_to(local)
                target=payload/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(path.read_bytes())
        meta={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),'status':'LOCAL_WSL_FAILURE_RETURN_READY','exit_code':args.exit_code,'command':args.command,'full_campaign_execution_authorized':False}
        (payload/'LOCAL_FAILURE_METADATA.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        lines=[]
        for path in sorted(payload.rglob('*')):
            if path.is_file() and path.name!='LOCAL_FAILURE_MANIFEST.sha256':
                lines.append(f'{sha256_file(path)}  {path.relative_to(payload).as_posix()}')
        (payload/'LOCAL_FAILURE_MANIFEST.sha256').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(payload.rglob('*')):
                if path.is_file(): z.write(path,path.relative_to(temp).as_posix())
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None: raise RuntimeError('local failure ZIP CRC failure')
    digest=sha256_file(output)
    Path(str(output)+'.sha256').write_text(f'{digest}  {output.name}\n',encoding='utf-8')
    print(f'LOCAL_FAILURE_RETURN_ZIP={output}')
    print(f'LOCAL_FAILURE_RETURN_ZIP_SHA256={digest}')
    return 0

if __name__=='__main__': raise SystemExit(main())
