#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd, yaml
ROOT=Path(__file__).resolve().parents[1]

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default='config/e3_first_sector_p452.yaml'); args=ap.parse_args()
    cfg=yaml.safe_load((ROOT/args.config).read_text(encoding='utf-8'))
    d=ROOT/cfg['outputs']['work_dir']
    profile=pd.read_csv(d/'p452_profile.csv'); params=json.loads((d/'p452_parameters.json').read_text()); audit=json.loads((d/'FIRST_SECTOR_P452_PREP_AUDIT.json').read_text())
    assert audit['status']=='MATLAB_READY_FROZEN'
    assert len(profile)==int(cfg['expected']['profile_sample_count'])
    assert abs(float(profile.iloc[0].distance_km))<1e-12
    assert np.all(np.diff(profile.distance_km.to_numpy(float))>0)
    assert np.allclose(profile.clutter_plus_terrain_m_asl,profile.terrain_m_asl,rtol=0,atol=1e-12)
    assert set(profile.radio_climatic_zone.astype(int))=={int(cfg['propagation']['climatic_zone_code'])}
    assert params['zero_terminal_gains_inside_p452'] is True
    assert params['no_separate_p2108_baseline'] is True
    stale=[d/'p452_basic_loss.csv',d/'P452_FIRST_SECTOR_MATLAB_AUDIT.json']
    present=[str(p) for p in stale if p.exists()]
    if present: raise ValueError('Stale MATLAB outputs exist before run: '+str(present))
    print('FIRST-SECTOR P.452 PRE-MATLAB PREFLIGHT: PASS')
    print('Profile points:',len(profile)); print('Distance (km):',profile.distance_km.iloc[-1]); print('Expected MATLAB rows:',audit['p452_output_row_count_expected'])
    print('Signed TX lon/lat:',params['tx_longitude_deg'],params['tx_latitude_deg']); print('Signed RX lon/lat:',params['rx_longitude_deg'],params['rx_latitude_deg'])
    print('P.452 commit:',params['p452_reference_commit']); print('Expected MATLAB release:',params['expected_matlab_release'])
    return 0
if __name__=='__main__': raise SystemExit(main())
