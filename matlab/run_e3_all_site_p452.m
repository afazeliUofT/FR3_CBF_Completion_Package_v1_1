function run_e3_all_site_p452(work_dir)
%RUN_E3_ALL_SITE_P452 Site-level P.452 basic-loss audit for 19 unique paths.
% No direct-path BS or earth-station antenna gain is included here.

arguments
    work_dir (1,1) string
end

profiles_path = fullfile(work_dir, "p452_all_site_profiles.csv");
sites_path = fullfile(work_dir, "p452_all_site_site_parameters.csv");
params_path = fullfile(work_dir, "p452_all_site_parameters.json");
prep_path = fullfile(work_dir, "ALL_SITE_P452_PREP_AUDIT.json");

assert(isfile(profiles_path));
assert(isfile(sites_path));
assert(isfile(params_path));
assert(isfile(prep_path));
assert(exist("tl_p452", "file") == 2, "tl_p452 is not on the MATLAB path");

profiles = readtable(profiles_path, "VariableNamingRule", "preserve");
sites = readtable(sites_path, "VariableNamingRule", "preserve");
params = jsondecode(fileread(params_path));
prep = jsondecode(fileread(prep_path));

assert(strcmp(prep.status, "MATLAB_READY_FROZEN"));
assert(strcmp(string(params.expected_matlab_release), string(version("-release"))));
assert(params.site_count == height(sites));

for name = ["p452_all_site_basic_loss.csv", ...
            "p452_all_site_coupling_export.csv", ...
            "P452_ALL_SITE_MATLAB_AUDIT.json"]
    path = fullfile(work_dir, name);
    if isfile(path)
        delete(path);
    end
end

p_values = double(params.time_percentages(:).');
pol_codes = double(params.polarization_codes(:).');
pol_labels = string(params.polarization_labels(:).');
coasts = double(params.coast_distance_scenarios_km(:).');

n_rows = height(sites) * numel(p_values) * numel(pol_codes) * numel(coasts);
site_col = strings(n_rows, 1);
distance_col = nan(n_rows, 1);
coast_col = nan(n_rows, 1);
pol_col = nan(n_rows, 1);
pol_label_col = strings(n_rows, 1);
p_col = nan(n_rows, 1);
loss_col = nan(n_rows, 1);
gain_col = nan(n_rows, 1);

row_index = 0;

for site_index = 1:height(sites)
    site_id = string(sites.site_id(site_index));
    mask = string(profiles.site_id) == site_id;
    profile = profiles(mask, :);
    profile = sortrows(profile, "sample_index");

    d = profile.distance_km.';
    h = profile.terrain_m_asl.';
    g = profile.clutter_plus_terrain_m_asl.';
    zone = profile.radio_climatic_zone.';

    assert(abs(d(1)) < 1e-12);
    assert(all(diff(d) > 0));
    assert(all(abs(g - h) < 1e-12));

    for coast_index = 1:numel(coasts)
        for pol_index = 1:numel(pol_codes)
            for time_index = 1:numel(p_values)
                row_index = row_index + 1;
                site_col(row_index) = site_id;
                distance_col(row_index) = d(end);
                coast_col(row_index) = coasts(coast_index);
                pol_col(row_index) = pol_codes(pol_index);
                pol_label_col(row_index) = pol_labels(pol_index);
                p_col(row_index) = p_values(time_index);

                loss_col(row_index) = tl_p452( ...
                    params.frequency_ghz, ...
                    p_values(time_index), ...
                    d, h, g, zone, ...
                    sites.htg_m(site_index), ...
                    sites.hrg_m(site_index), ...
                    sites.tx_longitude_deg(site_index), ...
                    sites.tx_latitude_deg(site_index), ...
                    sites.rx_longitude_deg(site_index), ...
                    sites.rx_latitude_deg(site_index), ...
                    0.0, 0.0, ...
                    pol_codes(pol_index), ...
                    coasts(coast_index), ...
                    coasts(coast_index), ...
                    params.pressure_hpa, ...
                    params.temperature_c);

                gain_col(row_index) = 10.^(-loss_col(row_index) / 10);
            end
        end
    end
end

assert(row_index == n_rows);
assert(isequal(size(site_col), [n_rows, 1]));
assert(isequal(size(distance_col), [n_rows, 1]));
assert(isequal(size(coast_col), [n_rows, 1]));
assert(isequal(size(pol_col), [n_rows, 1]));
assert(isequal(size(pol_label_col), [n_rows, 1]));
assert(isequal(size(p_col), [n_rows, 1]));
assert(isequal(size(loss_col), [n_rows, 1]));
assert(isequal(size(gain_col), [n_rows, 1]));
fprintf("MATLAB RESULT COLUMN-SHAPE PREFLIGHT: PASS\n");

results = table( ...
    site_col, distance_col, coast_col, pol_col, pol_label_col, ...
    p_col, loss_col, gain_col, ...
    'VariableNames', { ...
        'site_id', 'distance_km', 'coast_distance_km', ...
        'polarization_code', 'polarization_label', 'time_percentage', ...
        'basic_transmission_loss_db', 'path_gain_linear'});

assert(height(results) == n_rows);
assert(width(results) == 8);
fprintf("MATLAB RESULTS TABLE CONSTRUCTION: PASS\n");

results_path = fullfile(work_dir, "p452_all_site_basic_loss.csv");
writetable(results, results_path);

implementation_version = sprintf( ...
    "ITU-R P.452-18 reference v18.0 commit %s; MATLAB %s", ...
    params.p452_reference_commit, version("-release"));

rows = height(results);
coupling = table( ...
    zeros(rows, 1), ...
    repmat(string(params.station_id), rows, 1), ...
    "SITE_PROP_" + results.site_id, ...
    "P452_p" + string(results.time_percentage) ...
        + "_coast" + string(results.coast_distance_km) ...
        + "_" + results.polarization_label, ...
    repmat(params.frequency_ghz, rows, 1), ...
    ones(rows, 1), ...
    results.path_gain_linear, ...
    ones(rows, 1), ...
    false(rows, 1), ...
    repmat("none_documented", rows, 1), ...
    repmat(string(implementation_version), rows, 1), ...
    repmat( ...
        "ALL_SITE_BASIC_LOSS_AUDIT_NOT_PAPER_RESULT; " ...
        + "Gt=Gr=0dBi; g=h; no separate P2108; " ...
        + "site-level propagation only; no direct antenna gain included", ...
        rows, 1), ...
    'VariableNames', { ...
        'time_index', 'incumbent_id', 'sector_id', 'tone_group', ...
        'frequency_ghz', 'spectral_overlap_fraction', ...
        'path_gain_linear', 'receiver_gain_linear', ...
        'element_gain_accounted', 'clutter_treatment', ...
        'implementation_version', 'provenance_note'});

assert(height(coupling) == rows);
assert(width(coupling) == 12);
fprintf("MATLAB COUPLING TABLE CONSTRUCTION: PASS\n");
writetable(coupling, fullfile(work_dir, "p452_all_site_coupling_export.csv"));

audit = struct();
audit.created_utc = char(datetime( ...
    "now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"));
audit.status = "PASS";
audit.claim_boundary = params.claim_boundary;
audit.matlab_release = version("-release");
audit.matlab_version = version;
audit.p452_reference_commit = params.p452_reference_commit;
audit.site_count = height(sites);
audit.profile_sample_count = height(profiles);
audit.row_count = rows;
audit.minimum_basic_loss_db = min(results.basic_transmission_loss_db);
audit.maximum_basic_loss_db = max(results.basic_transmission_loss_db);
audit.zero_terminal_horizon_gains_inside_p452 = true;
audit.clutter_mode = params.clutter_mode;
audit.separate_p2108_loss_db = 0.0;
audit.time_percentages = p_values;
audit.polarization_codes = pol_codes;
audit.coast_distance_scenarios_km = coasts;

fid = fopen(fullfile(work_dir, "P452_ALL_SITE_MATLAB_AUDIT.json"), "w");
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "%s\n", jsonencode(audit, PrettyPrint=true));

fprintf("E3 ALL-SITE P.452 MATLAB RUN: PASS\n");
fprintf("Sites: %d\n", height(sites));
fprintf("Profile samples: %d\n", height(profiles));
fprintf("Rows: %d\n", rows);
fprintf("Basic loss range: %.9f to %.9f dB\n", ...
    min(results.basic_transmission_loss_db), ...
    max(results.basic_transmission_loss_db));
fprintf("Terminal horizon gains inside P.452: 0 dBi / 0 dBi\n");
fprintf("Separate P.2108 baseline loss: 0 dB\n");
end
