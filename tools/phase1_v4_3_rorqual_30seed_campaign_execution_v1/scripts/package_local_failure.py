#!/usr/bin/env python3
"""Create a portable local failure bundle without cache or repository clones."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import tempfile, zipfile

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--output-dir', required=True); p.add_argument('--log', required=True); p.add_argument('--stage', required=True); p.add_argument('--exit-code', type=int, required=True); a=p.parse_args()
    out=Path(a.output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fr3-local-failure-') as t:
        root=Path(t)/'FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_LOCAL_FAILURE'; root.mkdir()
        log=Path(a.log)
        if log.is_file(): (root/'LOCAL_WSL_ORCHESTRATOR.log').write_bytes(log.read_bytes())
        (root/'FAILURE_METADATA.json').write_text(json.dumps({'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),'stage':a.stage,'exit_code':a.exit_code,'campaign_execution_result_available':False},indent=2,sort_keys=True)+'\n')
        lines=[]
        for path in sorted(root.iterdir()):
            if path.is_file(): lines.append(f'{sha256_file(path)}  {path.name}\n')
        (root/'RETURN_MANIFEST.sha256').write_text(''.join(lines))
        zpath=out/'FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_LOCAL_FAILURE.zip'
        with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(root.iterdir()): z.write(path,path.relative_to(Path(t)).as_posix())
    digest=sha256_file(zpath); Path(str(zpath)+'.sha256').write_text(f'{digest}  {zpath.name}\n')
    print(f'LOCAL_FAILURE_RETURN_ZIP={zpath}'); print(f'LOCAL_FAILURE_RETURN_ZIP_SHA256={digest}'); return 0
if __name__=='__main__': raise SystemExit(main())
