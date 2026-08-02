#!/usr/bin/env python3
"""Verify a returned fresh-v4.5 holdout ZIP and print paper-facing gates."""
from __future__ import annotations
import argparse, hashlib, json, tempfile, zipfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def verify_sidecar(archive: Path) -> None:
    sidecar=Path(str(archive)+'.sha256')
    parts=sidecar.read_text(encoding='utf-8').split()
    if len(parts)!=2 or parts[1]!=archive.name or parts[0]!=sha256_file(archive):
        raise ValueError('return sidecar mismatch or not basename-only')


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--return-zip',required=True); p.add_argument('--twc-output-dir')
    args=p.parse_args(); archive=Path(args.return_zip).resolve(); verify_sidecar(archive)
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad is not None: raise ValueError(f'ZIP CRC failure: {bad}')
        roots={Path(n).parts[0] for n in z.namelist() if n and not n.endswith('/')}
        if len(roots)!=1: raise ValueError('return must have one root')
        root_name=next(iter(roots))
        with tempfile.TemporaryDirectory(prefix='fr3-v45-holdout-audit-') as tmp:
            z.extractall(tmp); root=Path(tmp)/root_name
            manifest=root/'RETURN_MANIFEST.sha256'
            for raw in manifest.read_text(encoding='utf-8').splitlines():
                if not raw.strip(): continue
                digest,rel=raw.split(maxsplit=1); rel=rel.lstrip(' *'); path=root/rel
                if not path.is_file() or sha256_file(path)!=digest:
                    raise ValueError(f'return manifest mismatch: {rel}')
            metadata=json.loads((root/'HOLDOUT_RETURN_METADATA.json').read_text(encoding='utf-8'))
            index=json.loads((root/'SEED_COMPLETION_INDEX.json').read_text(encoding='utf-8'))
            if len(index)!=30: raise ValueError('holdout index does not contain 30 seeds')
            nested=sorted((root/'seed_returns').glob('FR3_PHASE1_SEED_*_RETURN.zip'))
            for seed_zip in nested:
                verify_sidecar(seed_zip)
                with zipfile.ZipFile(seed_zip) as sz:
                    if sz.testzip() is not None: raise ValueError(f'seed return CRC failure: {seed_zip.name}')
            merged=root/'merged'/'PHASE1_MERGED_AUDIT.json'
            audit=json.loads(merged.read_text(encoding='utf-8')) if merged.is_file() else {}
            if args.twc_output_dir and audit:
                out=Path(args.twc_output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
                primary=audit.get('primary_bootstrap',{})
                floor=audit.get('floor_metrics',{})
                sched=audit.get('scheduling_summary',{})
                text=(
                    '\\subsection{Fresh holdout}\n'
                    f"The frozen candidate-v4.5 holdout used {audit.get('seed_count')} fresh seeds. "
                    f"The candidate-minus-safe-static final PF effect was {primary.get('point_estimate',float('nan')):.4f}, "
                    f"with a seed-cluster bootstrap 95\\% confidence interval "
                    f"[{primary.get('lower_95',float('nan')):.4f},{primary.get('upper_95',float('nan')):.4f}]. "
                    f"Long- and short-horizon EESS safety passed: {str(audit.get('safety_gates_pass')).lower()}. "
                    f"The holdout contained {floor.get('floor_violation_user_seconds','NA')} floor-violation user-seconds "
                    f"and {sched.get('failure_intervals','NA')} bounded-action scheduling-infeasible intervals.\n"
                )
                (out/'generated_holdout_results.tex').write_text(text,encoding='utf-8')
                (out/'HOLDOUT_PAPER_RESULT.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n',encoding='utf-8')

    print('HOLDOUT_RETURN_SHA256_GATE=PASS')
    print('HOLDOUT_RETURN_ZIP_CRC=PASS')
    print('HOLDOUT_RETURN_MANIFEST=PASS')
    print(f"HOLDOUT_RETURN_STATUS={metadata['status']}")
    print(f"HOLDOUT_SCIENTIFIC_EXIT_CODE={metadata['scientific_exit_code']}")
    print(f"HOLDOUT_SEED_RETURN_COUNT={metadata['seed_return_count']}")
    print(f"HOLDOUT_SEED_SAFETY_PASS_COUNT={metadata['seed_safety_pass_count']}")
    print(f"HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT={metadata['seed_zero_floor_pass_count']}")
    print(f"HOLDOUT_VALID_RESULT={metadata['valid_holdout_result']}")
    print(f"HOLDOUT_PRIMARY_SUPERIORITY_MET={metadata['primary_superiority_met']}")
    print(f"HOLDOUT_FLOOR_ZERO={metadata['floor_zero']}")
    print(f"PRIMARY_POINT_ESTIMATE={metadata['primary_point_estimate']}")
    print(f"PRIMARY_LOWER_95={metadata['primary_lower_95']}")
    print(f"PRIMARY_UPPER_95={metadata['primary_upper_95']}")
    print('AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO')
    print('NEXT_GATE='+metadata['next_gate'])
    return int(metadata['scientific_exit_code'])

if __name__=='__main__': raise SystemExit(main())
