#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-s44052-assemble-r2
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/slurm/%x-%j.out
#SBATCH --error=/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/slurm/%x-%j.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/activate'
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PHASE1_AUTHORIZATION_FILE='/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/private/SEED44052_R2_AUTHORIZATION.json'
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
mkdir -p '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052'
if '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_20260803_073355/source_extract/FR3_CBF_v1_1_Candidate_v4_5_Holdout_Completion_R2_PassParallel_DropIn_v1_2026-08-02/scripts/assemble_seed44052.py'   --job-package-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/job_package'   --seed-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052'   --pass-output-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/pass_outputs'   --completion-contract '/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_20260803_073355/source_extract/FR3_CBF_v1_1_Candidate_v4_5_Holdout_Completion_R2_PassParallel_DropIn_v1_2026-08-02/config/HOLDOUT_COMPLETION_R2_CONTRACT.json'   --authorization-file '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/private/SEED44052_R2_AUTHORIZATION.json'   > '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/worker_stdout.log'   2> '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/worker_stderr.log'; then
  ASSEMBLY_RC=0
else
  ASSEMBLY_RC=$?
fi
VALIDATOR_RC=99
SCIENTIFIC_RC=99
MERGE_RC=99
AUDIT_RC=99
if [[ "$ASSEMBLY_RC" -eq 0 ]]; then
  if '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/repair_job_package/validate_seed_result.py'     --result-dir '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/result'     --package-contract '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/repair_job_package/JOB_PACKAGE_CONTRACT.json'     > '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/repaired_validator_stdout.log'     2> '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/repaired_validator_stderr.log'; then
    VALIDATOR_RC=0
  else
    VALIDATOR_RC=$?
  fi
  SCIENTIFIC_RC="$('/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' - '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/result/SEED_RESULT.json' <<'PY_SCI'
import json,sys
print(int(json.load(open(sys.argv[1],encoding='utf-8'))['scientific_exit_code']))
PY_SCI
)"
  PACKAGE_ID="$('/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' - '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/job_package/JOB_PACKAGE_CONTRACT.json' <<'PY_ID'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['package_id'])
PY_ID
)"
  '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/job_package/package_seed_result.py'     --seed-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052'     --seed 44052     --package-id "$PACKAGE_ID"     --worker-exit-code "$SCIENTIFIC_RC"     --validator-exit-code "$VALIDATOR_RC"
fi
if [[ "$ASSEMBLY_RC" -eq 0 && "$VALIDATOR_RC" -eq 0 ]]; then
  rm -rf '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/merged'
  if '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/repair_job_package/merge_phase1_results.py'       --seed-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results'       --package-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/repair_job_package'       --output-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/merged'; then
    MERGE_RC=0
  else
    MERGE_RC=$?
  fi
  if [[ -f '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/merged/PHASE1_MERGED_AUDIT.json' ]]; then
    if '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_20260803_073355/source_extract/FR3_CBF_v1_1_Candidate_v4_5_Holdout_Completion_R2_PassParallel_DropIn_v1_2026-08-02/scripts/audit_completed_holdout.py'       --merged-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/merged'       --seed44052-result-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052/result'       --output-json '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/HOLDOUT_COMPLETION_AUDIT.json'       --output-tex '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/holdout_key_results.tex'; then
      AUDIT_RC=0
    else
      AUDIT_RC=$?
    fi
  fi
fi
if [[ ! -f '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/HOLDOUT_COMPLETION_AUDIT.json' ]]; then
  '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' - '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/HOLDOUT_COMPLETION_AUDIT.json'     "$ASSEMBLY_RC" "$VALIDATOR_RC" "$MERGE_RC" "$AUDIT_RC" <<'PY_INCOMPLETE'
import json,sys
value={
  'schema_version':1,
  'status':'INCOMPLETE_HOLDOUT_COMPLETION_R2_REVIEW_REQUIRED',
  'assembly_exit_code':int(sys.argv[2]),
  'validator_exit_code':int(sys.argv[3]),
  'merge_exit_code':int(sys.argv[4]),
  'audit_exit_code':int(sys.argv[5]),
  'automatic_extra_seeds_authorized':False,
  'automatic_algorithm_tuning_authorized':False,
  'next_gate':'REVIEW_ONLY_FAILED_PASS_WITHOUT_NEW_SEEDS_OR_ALGORITHM_TUNING',
}
json.dump(value,open(sys.argv[1],'w'),indent=2,sort_keys=True)
open(sys.argv[1],'a').write('\n')
PY_INCOMPLETE
  printf '%% Holdout completion R2 incomplete.\n' > '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/holdout_key_results.tex'
fi
printf '%s\n'   "SEED44052_PASS_PARALLEL_ASSEMBLY_EXIT_CODE=$ASSEMBLY_RC"   "SEED44052_REPAIRED_VALIDATOR_EXIT_CODE=$VALIDATOR_RC"   "SEED44052_SCIENTIFIC_EXIT_CODE=$SCIENTIFIC_RC"   "HOLDOUT_COMPLETION_MERGE_EXIT_CODE=$MERGE_RC"   "HOLDOUT_COMPLETION_AUDIT_EXIT_CODE=$AUDIT_RC"
if [[ "$ASSEMBLY_RC" -ne 0 ]]; then exit "$ASSEMBLY_RC"; fi
if [[ "$VALIDATOR_RC" -ne 0 ]]; then exit "$VALIDATOR_RC"; fi
if [[ "$MERGE_RC" -ne 0 ]]; then exit "$MERGE_RC"; fi
exit "$AUDIT_RC"
