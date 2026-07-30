#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",default="config/eess_dual_criterion_audit_v1.json")
    args=ap.parse_args(); cfg=json.loads((ROOT/args.config).read_text())
    ev=ROOT/cfg["paths"]["evidence"]; out=ROOT/cfg["paths"]["review_bundle"]
    files=[p for p in sorted(ev.rglob("*")) if p.is_file() and p!=out and not p.name.endswith(".zip.sha256")]
    for p in [ROOT/args.config,ROOT/"scripts/40_0_run_eess_dual_criterion_audit.py",ROOT/"scripts/40_1_validate_eess_dual_criterion_audit.py",ROOT/"PROJECT_STATUS.md",ROOT/"NEXT_IMMEDIATE_STEP.md"]:
        if not p.is_file(): raise FileNotFoundError(p)
        files.append(p)
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists(): out.unlink()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)): z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(out) as z:
        bad=z.testzip()
        if bad: raise RuntimeError(bad)
    Path(str(out)+".sha256").write_text(f"{sha(out)}  {out.name}\n",encoding="utf-8")
    print("EESS DUAL-CRITERION REVIEW BUNDLE: PASS")
    print("Review bundle:",out)
    print("Review bundle SHA-256:",sha(out))
    return 0
if __name__=="__main__": raise SystemExit(main())
