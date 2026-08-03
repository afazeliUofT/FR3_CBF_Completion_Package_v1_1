#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-s44052-pass-r2
#SBATCH --account=def-rsadve_cpu
#SBATCH --array=0-4%5
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/slurm/%x-%A_%a.out
#SBATCH --error=/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/slurm/%x-%A_%a.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/activate'
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PHASE1_AUTHORIZATION_FILE='/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/private/SEED44052_R2_AUTHORIZATION.json'
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
PASS_SLOT="${SLURM_ARRAY_TASK_ID}"
'/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python' '/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_20260803_073355/source_extract/FR3_CBF_v1_1_Candidate_v4_5_Holdout_Completion_R2_PassParallel_DropIn_v1_2026-08-02/scripts/run_seed44052_pass.py'   --job-package-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/job_package'   --seed-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/results/seed_44052'   --pass-output-root '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/pass_outputs'   --pass-slot "$PASS_SLOT"   --completion-contract '/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_20260803_073355/source_extract/FR3_CBF_v1_1_Candidate_v4_5_Holdout_Completion_R2_PassParallel_DropIn_v1_2026-08-02/config/HOLDOUT_COMPLETION_R2_CONTRACT.json'   --authorization-file '/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813/holdout_completion_r2_pass_parallel/private/SEED44052_R2_AUTHORIZATION.json'
