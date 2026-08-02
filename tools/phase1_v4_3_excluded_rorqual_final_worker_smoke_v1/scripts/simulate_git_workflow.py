#!/usr/bin/env python3
"""Simulate normal, concurrent, and stale non-force Git publication paths."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile

BRANCH = "e3-first-sector-p452"


def git(*args: str, cwd: Path | None = None, check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def configure(repo: Path) -> None:
    git("config", "user.name", "FR3 test", cwd=repo)
    git("config", "user.email", "fr3-test@example.invalid", cwd=repo)


def write_commit(repo: Path, relative: str, content: str, message: str) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git("add", relative, cwd=repo)
    git("commit", "-m", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix="fr3-git-smoke-") as temp_name:
        temp = Path(temp_name)
        remote = temp / "remote.git"
        seed = temp / "seed"
        git("init", "--bare", str(remote))
        git("clone", str(remote), str(seed))
        configure(seed)
        git("checkout", "-b", BRANCH, cwd=seed)
        base = write_commit(seed, "README.md", "base\n", "base")
        git("push", "-u", "origin", BRANCH, cwd=seed)

        source = temp / "source"
        git("clone", "--branch", BRANCH, str(remote), str(source))
        configure(source)
        source_commit = write_commit(
            source,
            "tools/phase1_v4_3_excluded_rorqual_final_worker_smoke_v1/SOURCE.txt",
            "immutable source\n",
            "source",
        )
        git("push", "origin", f"HEAD:{BRANCH}", cwd=source)

        evidence = temp / "evidence"
        stale = temp / "stale"
        git("clone", "--branch", BRANCH, str(remote), str(evidence))
        git("clone", "--branch", BRANCH, str(remote), str(stale))
        configure(evidence)
        configure(stale)

        concurrent = temp / "concurrent"
        git("clone", "--branch", BRANCH, str(remote), str(concurrent))
        configure(concurrent)
        concurrent_commit = write_commit(
            concurrent,
            "unrelated/CONCURRENT.txt",
            "preserve me\n",
            "concurrent",
        )
        git("push", "origin", f"HEAD:{BRANCH}", cwd=concurrent)

        evidence_commit_before_rebase = write_commit(
            evidence,
            "evidence/final_worker_smoke/EVIDENCE.txt",
            "review evidence\n",
            "evidence",
        )
        first_push = git(
            "push", "origin", f"HEAD:{BRANCH}", cwd=evidence, check=False
        )
        if first_push.returncode == 0:
            raise RuntimeError("concurrent evidence push unexpectedly succeeded")
        git("fetch", "origin", BRANCH, cwd=evidence)
        git("rebase", f"origin/{BRANCH}", cwd=evidence)
        git("push", "origin", f"HEAD:{BRANCH}", cwd=evidence)
        final_commit = git("rev-parse", "HEAD", cwd=evidence).stdout.strip()

        stale_commit = write_commit(
            stale,
            "stale/STALE.txt",
            "must be rejected\n",
            "stale",
        )
        stale_push = git(
            "push", "origin", f"HEAD:{BRANCH}", cwd=stale, check=False
        )
        stale_rejected = stale_push.returncode != 0

        verifier = temp / "verify"
        git("clone", "--branch", BRANCH, str(remote), str(verifier))
        preserved = (verifier / "unrelated/CONCURRENT.txt").read_text() == "preserve me\n"
        source_present = (
            verifier
            / "tools/phase1_v4_3_excluded_rorqual_final_worker_smoke_v1/SOURCE.txt"
        ).is_file()
        evidence_present = (
            verifier / "evidence/final_worker_smoke/EVIDENCE.txt"
        ).is_file()
        final_remote = git("rev-parse", "HEAD", cwd=verifier).stdout.strip()

        checks = {
            "normal_source_push": source_present,
            "concurrent_first_push_rejected": first_push.returncode != 0,
            "concurrent_update_preserved": preserved,
            "evidence_rebase_and_push": evidence_present,
            "stale_non_force_push_rejected": stale_rejected,
            "final_remote_matches_evidence": final_remote == final_commit,
            "base_is_ancestor": git(
                "merge-base", "--is-ancestor", base, final_remote, cwd=verifier, check=False
            ).returncode
            == 0,
            "source_is_ancestor": git(
                "merge-base", "--is-ancestor", source_commit, final_remote, cwd=verifier, check=False
            ).returncode
            == 0,
            "concurrent_is_ancestor": git(
                "merge-base", "--is-ancestor", concurrent_commit, final_remote, cwd=verifier, check=False
            ).returncode
            == 0,
        }
        if not all(checks.values()):
            raise RuntimeError(f"Git simulation failed: {checks}")
        value = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS_GIT_NORMAL_CONCURRENT_AND_STALE_NON_FORCE_SIMULATION",
            "checks": checks,
            "base_commit": base,
            "source_commit": source_commit,
            "concurrent_commit": concurrent_commit,
            "evidence_commit_before_rebase": evidence_commit_before_rebase,
            "final_remote_commit": final_remote,
            "stale_commit": stale_commit,
            "newer_work_overwritten": False,
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("GIT_WORKFLOW_SIMULATION=PASS")
    print("GITHUB_NEWER_WORK_OVERWRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
