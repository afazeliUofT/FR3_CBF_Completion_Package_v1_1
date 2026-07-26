function run_p452_pilot(pilot_dir)
%RUN_P452_PILOT Run the frozen project-specific P.452 pipeline pilot.
%
% This script must be executed from the validated P.452 v18 MATLAB folder,
% or with that folder on the MATLAB path. The pilot is not paper evidence.

arguments
    pilot_dir (1,1) string
end

profile_path = fullfile(pilot_dir, "p452_pilot_profile.csv");
parameters_path = fullfile(pilot_dir, "p452_pilot_parameters.json");
prep_audit_path = fullfile(pilot_dir, "P452_PILOT_PREP_AUDIT.json");

assert(isfile(profile_path), "Missing pilot profile: %s", profile_path);
assert(isfile(parameters_path), "Missing pilot parameters: %s", parameters_path);
assert(isfile(prep_audit_path), "Missing pilot prep audit: %s", prep_audit_path);
assert(exist('tl_p452','file') == 2, "tl_p452 is not on the MATLAB path");

prep_audit = jsondecode(fileread(prep_audit_path));
assert(strcmp(prep_audit.status, 'MATLAB_READY_FROZEN'), ...
    "Pilot inputs are not frozen; run Python preparation with --confirm after review");

params = jsondecode(fileread(parameters_path));
profile = readtable(profile_path, 'VariableNamingRule', 'preserve');

d = profile.distance_km.';
h = profile.terrain_m_asl.';
g = profile.clutter_plus_terrain_m_asl.';
zone = profile.radio_climatic_zone.';

assert(numel(d) >= 4, 'P.452 requires at least four profile points');
assert(abs(d(1)) < 1e-12, 'First distance must be zero');
assert(all(diff(d) > 0), 'Profile distance must be strictly increasing');
assert(all(isfinite(h)) && all(isfinite(g)), 'Profile heights must be finite');
assert(all(zone == 2), 'Pilot v1 is limited to an all-inland path');
assert(all(abs(g-h) < 1e-12), 'Pilot v1 requires no distributed clutter (g=h)');

p_values = params.time_percentages(:).';
Lb = nan(size(p_values));
for index = 1:numel(p_values)
    Lb(index) = tl_p452( ...
        params.frequency_ghz, ...
        p_values(index), ...
        d, h, g, zone, ...
        params.htg_m, params.hrg_m, ...
        params.tx_longitude_deg, params.tx_latitude_deg, ...
        params.rx_longitude_deg, params.rx_latitude_deg, ...
        params.tx_horizon_gain_dbi, params.rx_horizon_gain_dbi, ...
        params.polarization_code, ...
        params.dct_km, params.dcr_km, ...
        params.pressure_hpa, params.temperature_c);
end

path_gain = 10.^(-Lb/10);
results = table(p_values(:), Lb(:), path_gain(:), ...
    'VariableNames', {'time_percentage','basic_transmission_loss_db','path_gain_linear'});
results_path = fullfile(pilot_dir, 'p452_pilot_results.csv');
writetable(results, results_path);

export_index = find(abs(p_values - params.export_time_percentage) < 1e-12);
assert(numel(export_index) == 1, 'Export time percentage is not unique');
implementation_version = sprintf( ...
    'ITU-R P.452-18 reference v18.0 commit %s; MATLAB %s', ...
    params.p452_reference_commit, version('-release'));
provenance_note = sprintf( ...
    ['PIPELINE_PILOT_ONLY_NOT_PAPER_EVIDENCE; link_id=%s; p=%.12g%%; ' ...
     'Gt=Gr=0dBi; g=h; zone=2; dct=dcr=5km after manual inland/coast review; ' ...
     'profile_sha256=%s'], ...
    params.link_id, params.export_time_percentage, params.pilot_profile_sha256);

coupling = table( ...
    0, ...
    string(params.link_id), ...
    "PILOT_FIXED_LINK_TX_ENDPOINT", ...
    "PILOT", ...
    params.frequency_ghz, ...
    1.0, ...
    path_gain(export_index), ...
    1.0, ...
    false, ...
    "none_documented", ...
    string(implementation_version), ...
    string(provenance_note), ...
    'VariableNames', { ...
        'time_index','incumbent_id','sector_id','tone_group','frequency_ghz', ...
        'spectral_overlap_fraction','path_gain_linear','receiver_gain_linear', ...
        'element_gain_accounted','clutter_treatment','implementation_version', ...
        'provenance_note'});

coupling_path = fullfile(pilot_dir, 'p452_pilot_coupling.csv');
writetable(coupling, coupling_path);

matlab_audit = struct();
matlab_audit.created_utc = char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
matlab_audit.matlab_release = version('-release');
matlab_audit.matlab_version = version;
matlab_audit.p452_reference_commit = params.p452_reference_commit;
matlab_audit.link_id = params.link_id;
matlab_audit.profile_point_count = height(profile);
matlab_audit.path_distance_km = d(end);
matlab_audit.time_percentages = p_values;
matlab_audit.basic_transmission_loss_db = Lb;
matlab_audit.export_time_percentage = params.export_time_percentage;
matlab_audit.export_basic_transmission_loss_db = Lb(export_index);
matlab_audit.export_path_gain_linear = path_gain(export_index);
matlab_audit.claim_boundary = 'Pipeline audit only; not a cellular-to-incumbent paper result.';

fid = fopen(fullfile(pilot_dir, 'P452_PILOT_MATLAB_AUDIT.json'), 'w');
assert(fid >= 0, 'Could not open MATLAB audit output');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(matlab_audit, PrettyPrint=true));

fprintf('P.452 PILOT MATLAB RUN: PASS\n');
fprintf('Link: %s\n', params.link_id);
fprintf('Profile points: %d\n', height(profile));
fprintf('Distance: %.6f km\n', d(end));
fprintf('Export p: %.12g %%\n', params.export_time_percentage);
fprintf('Export Lb: %.9f dB\n', Lb(export_index));
fprintf('Export path gain: %.12e\n', path_gain(export_index));
end
