PYTHON ?= python

.PHONY: validate smoke test s1 sensitivity e1 e2 e3 calibration all readiness manifest beam runtime clean
validate:
	$(PYTHON) scripts/00_validate_package.py
smoke:
	$(PYTHON) scripts/01_run_smoke_test.py
test:
	$(PYTHON) -m pytest
s1:
	$(PYTHON) scripts/04_run_s1_adequacy.py --config config/s1_adequacy.yaml
sensitivity:
	$(PYTHON) scripts/04b_run_s1_sensitivity.py --config config/s1_adequacy.yaml
e1:
	$(PYTHON) scripts/10_run_e1_static_fs.py --config config/e1_static_fs.yaml
e2:
	$(PYTHON) scripts/11_run_e2_dynamic_fs.py --config config/e2_dynamic_fs.yaml
e3:
	$(PYTHON) scripts/12_run_e3_tracking_eess.py --config config/e3_tracking_eess.yaml
calibration:
	$(PYTHON) scripts/07_run_calibration.py --config config/calibration.yaml
all:
	$(PYTHON) scripts/13_run_all_experiments.py
readiness:
	$(PYTHON) scripts/15_check_submission_readiness.py
manifest:
	$(PYTHON) scripts/14_generate_manifest.py
beam:
	$(PYTHON) scripts/18_run_beam_space_filter.py --bundle data/demo/experiment_bundle_template.npz
runtime:
	$(PYTHON) scripts/16_benchmark_runtime.py --mode demo
clean:
	find results -mindepth 1 -maxdepth 1 ! -name .gitkeep ! -name README_DEMO_ONLY.md -exec rm -rf {} +
	rm -rf logs/* .pytest_cache
	touch results/.gitkeep logs/.gitkeep
