from __future__ import annotations
import ast,json
from pathlib import Path
import numpy as np
from fr3_cbf.practical_architecture_mapping import port_groups
ROOT=Path(__file__).resolve().parents[1]
def test_group_counts_and_partition():
 for rf,size in [(128,1),(64,2),(32,4)]:
  groups=port_groups(rf);assert len(groups)==rf;assert all(len(g)==size for g in groups);assert sorted(i for g in groups for i in g)==list(range(128))
def test_config_is_execution_blocked():
 cfg=json.loads((ROOT/'config/practical_architecture_mapping_v1.json').read_text());assert cfg['phase1_review_candidate']['campaign_execution_authorized'] is False;assert cfg['phase1_review_candidate']['protected_passes_currently_available']==1
def test_stage_sources_parse():
 for rel in ['src/fr3_cbf/practical_architecture_mapping.py','scripts/44_0_run_practical_architecture_mapping.py','scripts/44_1_validate_practical_architecture_mapping.py','scripts/44_2_build_phase1_campaign_candidate.py','scripts/44_3_sync_practical_architecture_status.py','scripts/44_4_build_practical_architecture_review_bundle.py']:
  path=ROOT/rel;ast.parse(path.read_text(),filename=str(path))
