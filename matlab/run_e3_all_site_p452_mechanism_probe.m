function run_e3_all_site_p452_mechanism_probe(work_dir, output_dir, probe_gain_dbi)
% Numerical mechanism-isolation audit.
% A very large positive P.452 horizon gain increases the troposcatter
% aperture-to-medium coupling loss and numerically suppresses the
% troposcatter branch without changing the LoS/diffraction/anomalous branch.

arguments
    work_dir (1,1) string
    output_dir (1,1) string
    probe_gain_dbi (1,1) double = 100.0
end

profiles = readtable(fullfile(work_dir, "p452_all_site_profiles.csv"), ...
    "VariableNamingRule", "preserve");
sites = readtable(fullfile(work_dir, "p452_all_site_site_parameters.csv"), ...
    "VariableNamingRule", "preserve");
params = jsondecode(fileread(fullfile(work_dir, "p452_all_site_parameters.json")));
baseline = readtable(fullfile(work_dir, "p452_all_site_basic_loss.csv"), ...
    "VariableNamingRule", "preserve");

assert(exist("tl_p452", "file") == 2);
assert(height(baseline) == params.expected_output_row_count);
if ~isfolder(output_dir)
    mkdir(output_dir);
end

out_path = fullfile(output_dir, "p452_troposcatter_suppressed_probe.csv");
audit_path = fullfile(output_dir, "P452_MECHANISM_PROBE_MATLAB_AUDIT.json");
if isfile(out_path); delete(out_path); end
if isfile(audit_path); delete(audit_path); end

n_rows = height(baseline);
site_col = strings(n_rows, 1);
coast_col = nan(n_rows, 1);
pol_col = nan(n_rows, 1);
pol_label_col = strings(n_rows, 1);
p_col = nan(n_rows, 1);
baseline_col = nan(n_rows, 1);
suppressed_col = nan(n_rows, 1);
delta_col = nan(n_rows, 1);

for row_index = 1:n_rows
    site_id = string(baseline.site_id(row_index));
    site_row = sites(string(sites.site_id) == site_id, :);
    assert(height(site_row) == 1);
    profile = profiles(string(profiles.site_id) == site_id, :);
    profile = sortrows(profile, "sample_index");

    d = profile.distance_km.';
    h = profile.terrain_m_asl.';
    g = profile.clutter_plus_terrain_m_asl.';
    zone = profile.radio_climatic_zone.';

    p_value = baseline.time_percentage(row_index);
    pol_value = baseline.polarization_code(row_index);
    coast_value = baseline.coast_distance_km(row_index);

    suppressed = tl_p452( ...
        params.frequency_ghz, p_value, d, h, g, zone, ...
        site_row.htg_m, site_row.hrg_m, ...
        site_row.tx_longitude_deg, site_row.tx_latitude_deg, ...
        site_row.rx_longitude_deg, site_row.rx_latitude_deg, ...
        probe_gain_dbi, probe_gain_dbi, pol_value, ...
        coast_value, coast_value, ...
        params.pressure_hpa, params.temperature_c);

    site_col(row_index) = site_id;
    coast_col(row_index) = coast_value;
    pol_col(row_index) = pol_value;
    pol_label_col(row_index) = string(baseline.polarization_label(row_index));
    p_col(row_index) = p_value;
    baseline_col(row_index) = baseline.basic_transmission_loss_db(row_index);
    suppressed_col(row_index) = suppressed;
    delta_col(row_index) = suppressed - baseline_col(row_index);
end

assert(all(isfinite(suppressed_col)));
assert(all(delta_col >= -1e-8));

probe = table( ...
    site_col, coast_col, pol_col, pol_label_col, p_col, ...
    baseline_col, suppressed_col, delta_col, ...
    'VariableNames', { ...
        'site_id', 'coast_distance_km', 'polarization_code', ...
        'polarization_label', 'time_percentage', ...
        'baseline_basic_loss_db', ...
        'troposcatter_suppressed_basic_loss_db', ...
        'troposcatter_contribution_delta_db'});

assert(height(probe) == n_rows);
writetable(probe, out_path);

audit = struct();
audit.created_utc = char(datetime( ...
    "now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"));
audit.status = "PASS";
audit.claim_boundary = "NUMERICAL_MECHANISM_ISOLATION_AUDIT";
audit.matlab_release = version("-release");
audit.p452_reference_commit = params.p452_reference_commit;
audit.row_count = n_rows;
audit.probe_horizon_gain_dbi = probe_gain_dbi;
audit.maximum_troposcatter_contribution_delta_db = max(delta_col);
audit.minimum_troposcatter_contribution_delta_db = min(delta_col);

fid = fopen(audit_path, "w");
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "%s\n", jsonencode(audit, PrettyPrint=true));

fprintf("E3 P.452 MECHANISM-ISOLATION MATLAB PROBE: PASS\n");
fprintf("Rows: %d\n", n_rows);
fprintf("Probe horizon gain: %.3f dBi / %.3f dBi\n", ...
    probe_gain_dbi, probe_gain_dbi);
fprintf("Troposcatter contribution delta range: %.12g to %.12g dB\n", ...
    min(delta_col), max(delta_col));
end
