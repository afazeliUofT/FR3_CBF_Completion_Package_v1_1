#!/usr/bin/env bash
#SBATCH --account=def-rsadve_cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --job-name=fr3-floor-v4-2
#SBATCH --output=/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/logs/floor-v4-2-%j.out
#SBATCH --error=/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/logs/floor-v4-2-%j.err

set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/pycache"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
"/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python" -m pip freeze --all > "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/pip_freeze_exact.txt"
"/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python" - <<'PY' > "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/python_environment.txt"
import platform,numpy,pandas,scipy
print('python='+platform.python_version())
print('numpy='+numpy.__version__)
print('pandas='+pandas.__version__)
print('scipy='+scipy.__version__)
PY
if "/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv/bin/python" "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/payload/scripts/run_seed43999_floor_feasibility_candidate_v4_2.py"   --package-root "/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008/package_rorqual_smoke"   --channel-root "/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008/run/results/seed_43999/channel"   --candidate-source "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/payload/src/fr3_cbf/floor_feasibility_repair.py"   --output-root "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/summary"   --expected-channel-record-sha256 "bf55f7a071bc00fdc9e73075bcf2b3f9da3bd07843e3795e134d4bdb3c4fa0d9"   --expected-frequency-array-sha256 "c4ac7fb56da5d3f8182836e2a99ab2ef1dd7b17bf76332abbc198d1ae6b6a093"   --source-commit "9acc9bed8b53ca9b358f774bd87218e676156b16"   --grid-time-limit-s 45   > "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/scientific_stdout.txt" 2> "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/scientific_stderr.txt"
then
  scientific_exit=0
else
  scientific_exit=$?
fi
printf '%s\n' "$scientific_exit" > "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/scientific_exit_code.txt"
cat "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/scientific_stdout.txt"
cat "/home/rsadve1/links/scratch/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_20260801_192858/run/scientific_stderr.txt" >&2
exit "$scientific_exit"
