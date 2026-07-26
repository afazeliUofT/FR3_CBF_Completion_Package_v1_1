# Environment

Recommended baseline:

- Python 3.11
- NumPy, pandas, SciPy, Matplotlib, PyYAML, pytest from `requirements-core.txt`
- Optional: CVXPY, Skyfield/SGP4, rasterio from `requirements-full.txt`

For an offline machine with the dependencies already installed:

```bash
python -m pip install -e . --no-build-isolation --no-deps
```

When installing inside an existing validated TensorFlow/Sionna environment, always use
`--no-deps` so this small package does not replace the environment's tested versions.

For final paper runs, export an exact environment record (`python -m pip freeze`, Python version, operating system, solver versions, CPU/GPU, and cluster job configuration) into the result directory.
