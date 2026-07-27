#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='config/e3_first_sector_p452.yaml')
    ap.add_argument('--reviewer', required=True)
    ap.add_argument('--confirm-terrain-reviewed', action='store_true')
    args = ap.parse_args()

    if not args.confirm_terrain_reviewed:
        raise SystemExit('FAIL: --confirm-terrain-reviewed is required after visual review of the corrected Site-18 terrain PDF')
    reviewer = args.reviewer.strip()
    if len(reviewer) < 2:
        raise SystemExit('FAIL: reviewer name is empty')

    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8'))
    inp = {k: ROOT / v for k, v in cfg['inputs'].items()}
    out_dir = ROOT / cfg['outputs']['work_dir']
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [str(p.relative_to(ROOT)) for p in inp.values() if not p.is_file()]
    if missing:
        raise SystemExit('FAIL: missing inputs:\n' + '\n'.join('  - ' + x for x in missing))

    selected = json.loads(inp['selected_sector_json'].read_text(encoding='utf-8'))
    terrain_audit = json.loads(inp['terrain_audit_json'].read_text(encoding='utf-8'))
    correction = json.loads(inp['protected_window_correction_json'].read_text(encoding='utf-8'))
    selection_audit = json.loads(inp['protected_window_selection_audit_json'].read_text(encoding='utf-8'))
    station = pd.read_csv(inp['earth_station_csv'])
    sites = pd.read_csv(inp['bs_sites_csv'])
    sectors = pd.read_csv(inp['bs_sectors_csv'])
    terrain_summary = pd.read_csv(inp['terrain_summary_csv'])
    profile = pd.read_csv(inp['terrain_profile_csv_gz'])
    link = pd.read_csv(inp['first_sector_link_csv'])
    track = pd.read_csv(inp['selected_pass_track_csv'])
    pattern_params = pd.read_csv(inp['pattern_parameters_csv'])
    protected_summary = pd.read_csv(inp['protected_off_axis_summary_csv'])

    exp = cfg['expected']
    assert selected['sector_id'] == exp['sector_id']
    assert selected['site_id'] == exp['site_id']
    assert selected['station_id'] == exp['station_id']
    assert selected['supersedes_sector_id'] == exp['superseded_sector_id']
    assert int(selected['protected_window_sample_count']) == int(exp['protected_window_sample_count'])
    assert math.isclose(float(selected['minimum_elevation_deg']), float(exp['minimum_elevation_deg']), abs_tol=1e-12)
    assert selection_audit['status'] == 'PASS'
    assert correction['corrected_site_winner'] == exp['site_id']

    if len(station) != 1 or len(terrain_summary) != 1 or len(link) != 1:
        raise ValueError('Expected one station, one terrain-summary row, and one link row')
    if len(sites) != 19 or len(sectors) != 57:
        raise ValueError('Expected frozen 19-site/57-sector layout')
    if len(profile) != int(exp['profile_sample_count']):
        raise ValueError(f"Expected {exp['profile_sample_count']} terrain samples; found {len(profile)}")
    row = terrain_summary.iloc[0]
    if int(row['qc_flag_count']) != 0 or int(terrain_audit['links_with_qc_flags']) != 0:
        raise ValueError('Corrected Site-18 terrain still has unresolved QC flags')
    distance_km = float(row['distance_km_wgs84'])
    if not (float(exp['distance_km_min']) <= distance_km <= float(exp['distance_km_max'])):
        raise ValueError(f'Unexpected path distance: {distance_km} km')
    if not math.isclose(float(row['tx_implied_antenna_height_agl_m']), float(exp['tx_height_agl_m']), abs_tol=1e-9):
        raise ValueError('TX AGL mismatch')
    if not math.isclose(float(row['rx_implied_antenna_height_agl_m']), float(exp['rx_height_agl_m']), abs_tol=1e-9):
        raise ValueError('RX AGL mismatch')

    distances_m = pd.to_numeric(profile['distance_from_tx_m'], errors='coerce').to_numpy(float)
    elevations = pd.to_numeric(profile['elevation_m_asl'], errors='coerce').to_numpy(float)
    lons = pd.to_numeric(profile['longitude_deg'], errors='coerce').to_numpy(float)
    lats = pd.to_numeric(profile['latitude_deg'], errors='coerce').to_numpy(float)
    if not (np.isfinite(distances_m).all() and np.isfinite(elevations).all() and np.isfinite(lons).all() and np.isfinite(lats).all()):
        raise ValueError('Profile contains non-finite values')
    if abs(distances_m[0]) > 1e-9 or np.any(np.diff(distances_m) <= 0):
        raise ValueError('Profile distance must start at zero and increase strictly')
    if not (np.all((-180 <= lons) & (lons <= 180)) and np.all((-90 <= lats) & (lats <= 90))):
        raise ValueError('Profile coordinates are outside signed WGS-84 ranges')

    st = station.iloc[0]
    site = sites.loc[sites['site_id'].astype(str) == exp['site_id']]
    sector = sectors.loc[sectors['sector_id'].astype(str) == exp['sector_id']]
    if len(site) != 1 or len(sector) != 1:
        raise ValueError('Selected site/sector is not unique')
    site = site.iloc[0]
    sector = sector.iloc[0]
    tol = 1e-8
    checks = [
        (lons[0], float(site['longitude_deg']), 'profile TX longitude'),
        (lats[0], float(site['latitude_deg']), 'profile TX latitude'),
        (lons[-1], float(st['longitude_deg']), 'profile RX longitude'),
        (lats[-1], float(st['latitude_deg']), 'profile RX latitude'),
    ]
    for got, expected, label in checks:
        if abs(got - expected) > tol:
            raise ValueError(f'{label} mismatch: {got} vs {expected}')

    min_el = float(exp['minimum_elevation_deg'])
    protected = track.loc[pd.to_numeric(track['elevation_deg'], errors='coerce') >= min_el].copy()
    if len(protected) != int(exp['protected_window_sample_count']):
        raise ValueError(f'Protected track count mismatch: {len(protected)}')
    if str(protected.iloc[0]['time_utc']) != selected['protected_window_start_utc'] or str(protected.iloc[-1]['time_utc']) != selected['protected_window_end_utc']:
        raise ValueError('Protected track start/end does not match selected-sector record')

    nominal = pattern_params.loc[
        (np.isclose(pattern_params['aperture_efficiency'], float(cfg['earth_station_gain_reference']['nominal_efficiency'])))
        & (pattern_params['pattern_type'].astype(str) == cfg['earth_station_gain_reference']['nominal_pattern_type'])
    ]
    if len(nominal) != 1:
        raise ValueError('Nominal earth-station pattern parameter row is not unique')

    protected_site = protected_summary.loc[protected_summary['site_id'].astype(str) == exp['site_id']]
    if protected_site.empty:
        raise ValueError('Selected site missing from protected off-axis summary')
    p0 = protected_site.iloc[0]
    min_col = (
        'minimum_off_axis_deg_during_protected_window'
        if 'minimum_off_axis_deg_during_protected_window' in protected_site.columns
        else 'minimum_off_axis_deg_during_selected_track'
    )
    max_col = (
        'maximum_reference_gain_dbi_during_protected_window'
        if 'maximum_reference_gain_dbi_during_protected_window' in protected_site.columns
        else 'maximum_reference_gain_dbi_during_selected_track'
    )
    if min_col not in protected_site.columns or max_col not in protected_site.columns:
        raise ValueError(
            'Protected off-axis summary lacks supported minimum/gain columns: '
            f'{protected_site.columns.tolist()}'
        )
    if abs(float(p0[min_col]) - float(selected['minimum_earth_station_off_axis_deg'])) > 1e-8:
        raise ValueError('Protected off-axis minimum mismatch')
    if abs(float(p0[max_col]) - float(selected['maximum_reference_earth_station_gain_dbi'])) > 1e-8:
        raise ValueError('Protected earth-station gain maximum mismatch')

    commit = inp['p452_reference_commit_file'].read_text(encoding='utf-8').strip()
    if commit != str(exp['p452_reference_commit']):
        raise ValueError(f'P.452 commit mismatch: {commit}')
    provenance_text = inp['p452_reference_provenance_file'].read_text(encoding='utf-8', errors='replace')
    if '17 out of 17' not in provenance_text and '17/17' not in provenance_text:
        raise ValueError('P.452 provenance does not record 17/17 validation')
    if 'R2026a' not in provenance_text and '2026a' not in provenance_text:
        raise ValueError('P.452 provenance does not identify MATLAB R2026a')

    # Remove known stale generated outputs before writing new inputs.
    stale = [
        'p452_basic_loss.csv', 'p452_coupling_export.csv', 'P452_FIRST_SECTOR_MATLAB_AUDIT.json',
        'earth_station_gain_timeseries.csv', 'bs_gain_accounting.csv', 'gain_accounting_timeseries.csv.gz',
        'conditional_threshold_summary.csv', 'FIRST_SECTOR_P452_AUDIT.json', 'FIRST_SECTOR_P452_AUDIT.md',
        'FIRST_SECTOR_P452_VALIDATION.json', 'FIRST_SECTOR_P452_VALIDATION.md'
    ]
    for name in stale:
        path = out_dir / name
        if path.exists():
            path.unlink()

    p452_profile = pd.DataFrame({
        'sample_index': profile['sample_index'].astype(int),
        'distance_km': distances_m / 1000.0,
        'terrain_m_asl': elevations,
        'clutter_plus_terrain_m_asl': elevations,
        'radio_climatic_zone': int(cfg['propagation']['climatic_zone_code']),
        'longitude_deg': lons,
        'latitude_deg': lats,
    })
    profile_out = out_dir / 'p452_profile.csv'
    p452_profile.to_csv(profile_out, index=False)

    terrain_decision = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'ACCEPTED_FOR_FIRST_SECTOR_P452_ACCOUNTING_AUDIT',
        'reviewer': reviewer,
        'sector_id': exp['sector_id'],
        'site_id': exp['site_id'],
        'profile_sample_count': len(profile),
        'distance_km': distance_km,
        'qc_flag_count': 0,
        'review_confirmation': 'Visual review confirmed by explicit command-line flag.',
        'claim_boundary': cfg['claim_boundary'],
        'terrain_review_pdf_sha256': sha256_file(inp['terrain_review_pdf']),
        'next_gate': 'RUN_VALIDATED_P452_AND_GAIN_ACCOUNTING',
    }
    write_json(out_dir / 'FIRST_SECTOR_TERRAIN_DECISION.json', terrain_decision)

    params = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'claim_boundary': cfg['claim_boundary'],
        'sector_id': exp['sector_id'],
        'site_id': exp['site_id'],
        'station_id': exp['station_id'],
        'frequency_ghz': float(cfg['propagation']['frequency_ghz']),
        'time_percentages': [float(x) for x in cfg['propagation']['time_percentages']],
        'p452_polarization_codes': [int(x) for x in cfg['propagation']['polarization_codes']],
        'p452_polarization_labels': [str(x) for x in cfg['propagation']['polarization_labels']],
        'coast_distance_scenarios_km': [float(x) for x in cfg['propagation']['coast_distance_scenarios_km']],
        'nominal_coast_distance_km': float(cfg['propagation']['nominal_coast_distance_km']),
        'pressure_hpa': float(cfg['propagation']['pressure_hpa']),
        'temperature_c': float(cfg['propagation']['temperature_c']),
        'htg_m': float(row['tx_implied_antenna_height_agl_m']),
        'hrg_m': float(row['rx_implied_antenna_height_agl_m']),
        'tx_longitude_deg': float(lons[0]),
        'tx_latitude_deg': float(lats[0]),
        'rx_longitude_deg': float(lons[-1]),
        'rx_latitude_deg': float(lats[-1]),
        'tx_horizon_gain_dbi': float(cfg['propagation']['terminal_horizon_gain_tx_dbi']),
        'rx_horizon_gain_dbi': float(cfg['propagation']['terminal_horizon_gain_rx_dbi']),
        'climatic_zone_code': int(cfg['propagation']['climatic_zone_code']),
        'clutter_mode': cfg['propagation']['clutter_mode'],
        'coordinate_convention': cfg['propagation']['coordinate_convention'],
        'p452_reference_commit': commit,
        'expected_matlab_release': str(exp['matlab_release']),
        'profile_sha256': sha256_file(profile_out),
        'config_sha256': sha256_file(cfg_path),
        'selected_sector_sha256': sha256_file(inp['selected_sector_json']),
        'terrain_summary_sha256': sha256_file(inp['terrain_summary_csv']),
        'zero_terminal_gains_inside_p452': True,
        'no_separate_p2108_baseline': True,
        'coast_distance_status': cfg['propagation']['coast_distance_status'],
    }
    write_json(out_dir / 'p452_parameters.json', params)

    input_hashes = {str(p.relative_to(ROOT)): sha256_file(p) for p in inp.values()}
    prep = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'MATLAB_READY_FROZEN',
        'claim_boundary': cfg['claim_boundary'],
        'reviewer': reviewer,
        'sector_id': exp['sector_id'],
        'profile_sample_count': len(profile),
        'distance_km': distance_km,
        'protected_window_sample_count': len(protected),
        'p452_output_row_count_expected': len(cfg['propagation']['time_percentages']) * len(cfg['propagation']['polarization_codes']) * len(cfg['propagation']['coast_distance_scenarios_km']),
        'input_sha256': input_hashes,
        'generated_sha256': {
            'p452_profile.csv': sha256_file(profile_out),
            'p452_parameters.json': sha256_file(out_dir / 'p452_parameters.json'),
            'FIRST_SECTOR_TERRAIN_DECISION.json': sha256_file(out_dir / 'FIRST_SECTOR_TERRAIN_DECISION.json'),
        },
        'next_gate': 'MATLAB_P452_BASIC_LOSS',
    }
    write_json(out_dir / 'FIRST_SECTOR_P452_PREP_AUDIT.json', prep)

    print('FIRST-SECTOR P.452 INPUT PREPARATION: PASS')
    print('Sector:', exp['sector_id'])
    print('Site:', exp['site_id'])
    print('Station:', exp['station_id'])
    print('Profile samples:', len(profile))
    print(f'Distance: {distance_km:.9f} km')
    print('TX/RX AGL:', params['htg_m'], params['hrg_m'])
    print('Protected track samples:', len(protected))
    print('Time percentages:', params['time_percentages'])
    print('Coast-distance scenarios (km):', params['coast_distance_scenarios_km'])
    print('Polarization branches:', list(zip(params['p452_polarization_labels'], params['p452_polarization_codes'])))
    print('P.452 terminal horizon gains inside model: 0 dBi / 0 dBi')
    print('Baseline clutter: g=h; separate P.2108 loss: 0 dB')
    print('Expected MATLAB output rows:', prep['p452_output_row_count_expected'])
    print('Output directory:', out_dir)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
