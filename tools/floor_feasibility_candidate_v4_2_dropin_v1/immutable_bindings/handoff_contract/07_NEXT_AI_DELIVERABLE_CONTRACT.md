
# Required Deliverable Contract for the Next AI

The next AI must not merely provide prose advice. It must produce the following.

## 1. Scientific review

A concise but rigorous status section that:

- reads the packaged source evidence;
- distinguishes source facts, inference, and assumptions;
- determines the exact root cause of the material floor failures;
- states whether the current floor is feasible;
- identifies the scientifically best repair;
- preserves the incumbent hard constraint and practical distributed design.

## 2. One downloadable repair package

The response must provide:

- exactly one primary `.zip` package;
- its `.sha256` sidecar;
- source files, tests, docs, manifests, wrappers, and review schema;
- no compiled caches;
- immutable source bindings;
- exact local and cluster paths;
- Git staging/push logic;
- success and failure diagnostic packaging.

The package should be independently reviewable and should not silently modify
the immutable phase-1 package. Use a new version/candidate when scientific code
changes.

## 3. One full WSL drop-in

The response must contain one copy-paste block that:

- locates the downloaded ZIP in Windows Downloads;
- selects the newest matching filename safely;
- verifies the expected SHA-256;
- tests and extracts the ZIP;
- verifies its internal manifest;
- activates the correct local `.venv`;
- runs all local checks and diagnostics;
- chooses local CPU versus Rorqual explicitly;
- if Rorqual is required, connects through local WSL, uses
  `/home/rsadve1/links/scratch`, prepares/reuses the correct venv, submits only
  the authorized job, polls it, collects `sacct`, retrieves success or failure
  bundles, and opens the Windows return folder;
- commits and pushes generated review evidence;
- prints all final hashes, commit, job ID, status, and next gate.

Do not split commands into multiple independently copied windows unless a
cluster-side command must genuinely be entered separately. Prefer one local WSL
orchestrator.

## 4. Error-proofing requirements

- `set -Eeuo pipefail`;
- capture expected nonzero exits through `if` conditions;
- never let an `ERR` trap prevent diagnostic retrieval;
- portable checksum sidecars using basenames;
- no hidden use of HOME for heavy cluster data;
- exact source/config hash verification;
- explicit local/remote path echoes;
- no background promises;
- failure must return a compact diagnostic ZIP;
- do not rerun expensive channel generation when a preserved channel can be
  reused.

## 5. Scientific gates

The next AI must not authorize the 30-seed campaign until the material
floor-feasibility blocker is resolved and independently smoke-tested.

It must not:

- weaken the floor by changing tolerance;
- redefine coverage-limited users after seeing outcomes without a preregistered
  policy;
- use sum rate as the primary metric;
- reintroduce centralized WMMSE;
- claim calibration or regulatory compliance;
- treat the excluded seed as confirmatory evidence.
