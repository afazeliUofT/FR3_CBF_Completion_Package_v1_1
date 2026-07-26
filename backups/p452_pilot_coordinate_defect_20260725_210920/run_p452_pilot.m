function run_p452_pilot(pilot_dir)
%RUN_P452_PILOT Run the frozen project-specific P.452 pipeline pilot.
%
% This script must be executed from the validated P.452 v18 MATLAB folder,
% or with that folder on the MATLAB path. The pilot is not paper evidence.
%
% For a TAFL co-channel dual-polarization record, the frozen parameters
% contain P.452 polarization codes [1 2].  This runner evaluates horizontal
% and vertical separately and exports both branches.  It does not aggregate
% their powers or silently select one branch.

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

p_values = double(params.time_percentages(:).');
pol_codes = double(params.p452_polarization_codes(:).');
pol_labels = string(params.p452_polarization_labels(:).');
assert(numel(pol_codes) == numel(pol_labels), ...
    'P.452 polarization code/label counts do not match');
assert(~isempty(pol_codes), 'No P.452 polarization branch was supplied');
assert(all(ismember(pol_codes, [1 2])), ...
    'P.452 polarization codes must be 1 (H) or 2 (V)');
assert(numel(unique(pol_codes)) == numel(pol_codes), ...
    'P.452 polarization codes must be unique');

n_p = numel(p_values);
n_pol = numel(pol_codes);
n_rows = n_p * n_pol;
result_p = nan(n_rows, 1);
result_pol_code = nan(n_rows, 1);
result_pol_label = strings(n_rows, 1);
result_lb = nan(n_rows, 1);
result_gain = nan(n_rows, 1);

row_index = 0;
for pol_index = 1:n_pol
    for p_index = 1:n_p
        row_index = row_index + 1;
        result_p(row_index) = p_values(p_index);
        result_pol_code(row_index) = pol_codes(pol_index);
        result_pol_label(row_index) = pol_labels(pol_index);
        result_lb(row_index) = tl_p452( ...
            params.frequency_ghz, ...
            p_values(p_index), ...
            d, h, g, zone, ...
            params.htg_m, params.hrg_m, ...
            params.tx_longitude_deg, params.tx_latitude_deg, ...
            params.rx_longitude_deg, params.rx_latitude_deg, ...
            params.tx_horizon_gain_dbi, params.rx_horizon_gain_dbi, ...
            pol_codes(pol_index), ...
            params.dct_km, params.dcr_km, ...
            params.pressure_hpa, params.temperature_c);
        result_gain(row_index) = 10.^(-result_lb(row_index)/10);
    end
end

results = table( ...
    result_pol_code, result_pol_label, result_p, result_lb, result_gain, ...
    'VariableNames', { ...
        'polarization_code','polarization_label','time_percentage', ...
        'basic_transmission_loss_db','path_gain_linear'});
results_path = fullfile(pilot_dir, 'p452_pilot_results.csv');
writetable(results, results_path);

export_p = double(params.export_time_percentage);
export_mask = abs(result_p - export_p) < 1e-12;
assert(sum(export_mask) == n_pol, ...
    'Expected one export row per polarization branch');
export_results = results(export_mask, :);
[~, export_order] = sort(export_results.polarization_code);
export_results = export_results(export_order, :);
assert(all(export_results.polarization_code.' == sort(pol_codes)), ...
    'Export polarization branches do not match frozen parameters');

implementation_version = sprintf( ...
    'ITU-R P.452-18 reference v18.0 commit %s; MATLAB %s', ...
    params.p452_reference_commit, version('-release'));

provenance_note = strings(n_pol, 1);
for pol_index = 1:n_pol
    provenance_note(pol_index) = string(sprintf( ...
        ['PIPELINE_PILOT_ONLY_NOT_PAPER_EVIDENCE; link_id=%s; p=%.12g%%; ' ...
         'TAFL_polarization=%s(%s); P452_pol=%s/%d; ' ...
         'dual_branch_power_aggregation=none; Gt=Gr=0dBi; g=h; zone=2; ' ...
         'dct=dcr=5km after manual inland/coast review; profile_sha256=%s'], ...
        params.link_id, export_p, ...
        params.tafl_tx_polarization_code, params.tafl_polarization_description, ...
        export_results.polarization_label(pol_index), ...
        export_results.polarization_code(pol_index), ...
        params.pilot_profile_sha256));
end

coupling = table( ...
    zeros(n_pol, 1), ...
    repmat(string(params.link_id), n_pol, 1), ...
    "PILOT_FIXED_LINK_TX_ENDPOINT_" + export_results.polarization_label, ...
    "PILOT_" + export_results.polarization_label, ...
    repmat(params.frequency_ghz, n_pol, 1), ...
    ones(n_pol, 1), ...
    export_results.path_gain_linear, ...
    ones(n_pol, 1), ...
    false(n_pol, 1), ...
    repmat("none_documented", n_pol, 1), ...
    repmat(string(implementation_version), n_pol, 1), ...
    provenance_note, ...
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
matlab_audit.tafl_polarization_code = params.tafl_tx_polarization_code;
matlab_audit.tafl_polarization_description = params.tafl_polarization_description;
matlab_audit.p452_polarization_codes = pol_codes;
matlab_audit.p452_polarization_labels = cellstr(pol_labels);
matlab_audit.polarization_aggregation = params.polarization_aggregation;
matlab_audit.result_polarization_codes = result_pol_code.';
matlab_audit.result_polarization_labels = cellstr(result_pol_label.');
matlab_audit.result_time_percentages = result_p.';
matlab_audit.basic_transmission_loss_db = result_lb.';
matlab_audit.path_gain_linear = result_gain.';
matlab_audit.export_time_percentage = export_p;
matlab_audit.export_polarization_codes = export_results.polarization_code.';
matlab_audit.export_polarization_labels = cellstr(export_results.polarization_label.');
matlab_audit.export_basic_transmission_loss_db = export_results.basic_transmission_loss_db.';
matlab_audit.export_path_gain_linear = export_results.path_gain_linear.';
matlab_audit.claim_boundary = [ ...
    'Pipeline audit only; not a cellular-to-incumbent paper result. ' ...
    'Dual-polarization branches are exported separately; no branch powers are aggregated.' ...
];

fid = fopen(fullfile(pilot_dir, 'P452_PILOT_MATLAB_AUDIT.json'), 'w');
assert(fid >= 0, 'Could not open MATLAB audit output');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(matlab_audit, PrettyPrint=true));

fprintf('P.452 PILOT MATLAB RUN: PASS\n');
fprintf('Link: %s\n', params.link_id);
fprintf('Profile points: %d\n', height(profile));
fprintf('Distance: %.6f km\n', d(end));
fprintf('TAFL polarization: %s (%s)\n', ...
    params.tafl_tx_polarization_code, params.tafl_polarization_description);
fprintf('Export p: %.12g %%\n', export_p);
for pol_index = 1:n_pol
    fprintf('Export %s/pol=%d Lb: %.9f dB\n', ...
        export_results.polarization_label(pol_index), ...
        export_results.polarization_code(pol_index), ...
        export_results.basic_transmission_loss_db(pol_index));
    fprintf('Export %s/pol=%d path gain: %.12e\n', ...
        export_results.polarization_label(pol_index), ...
        export_results.polarization_code(pol_index), ...
        export_results.path_gain_linear(pol_index));
end
fprintf('Dual-branch power aggregation: NONE (pipeline audit)\n');
end
