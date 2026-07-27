function run_e3_first_sector_p452(work_dir)
% One-sector P.452 basic-loss audit. No antenna gain is included inside P.452.
arguments
    work_dir (1,1) string
end
profile_path=fullfile(work_dir,"p452_profile.csv"); params_path=fullfile(work_dir,"p452_parameters.json"); audit_path=fullfile(work_dir,"FIRST_SECTOR_P452_PREP_AUDIT.json");
assert(isfile(profile_path)); assert(isfile(params_path)); assert(isfile(audit_path)); assert(exist('tl_p452','file')==2,'tl_p452 is not on MATLAB path');
prep=jsondecode(fileread(audit_path)); assert(strcmp(prep.status,'MATLAB_READY_FROZEN'));
params=jsondecode(fileread(params_path)); profile=readtable(profile_path,'VariableNamingRule','preserve');
assert(strcmp(string(params.expected_matlab_release),string(version('-release'))),'Unexpected MATLAB release');
assert(strcmp(string(params.coordinate_convention),"longitude_degrees_east_signed_-180_to_180"));
coords=[params.tx_longitude_deg params.tx_latitude_deg params.rx_longitude_deg params.rx_latitude_deg]; assert(all(isfinite(coords))); assert(all(coords([1 3])>=-180 & coords([1 3])<=180)); assert(all(coords([2 4])>=-90 & coords([2 4])<=90));
assert(abs(profile.distance_km(1))<1e-12); assert(all(diff(profile.distance_km)>0)); assert(all(profile.radio_climatic_zone==params.climatic_zone_code)); assert(all(abs(profile.clutter_plus_terrain_m_asl-profile.terrain_m_asl)<1e-12));
% Delete stale outputs before any propagation calculation.
for name=["p452_basic_loss.csv","p452_coupling_export.csv","P452_FIRST_SECTOR_MATLAB_AUDIT.json"]
    path=fullfile(work_dir,name); if isfile(path); delete(path); end
end
pvals=double(params.time_percentages(:).'); pols=double(params.p452_polarization_codes(:).'); labels=string(params.p452_polarization_labels(:).'); coasts=double(params.coast_distance_scenarios_km(:).');
d=profile.distance_km.'; h=profile.terrain_m_asl.'; g=profile.clutter_plus_terrain_m_asl.'; zone=profile.radio_climatic_zone.';
n=numel(pvals)*numel(pols)*numel(coasts); coast_col=nan(n,1); pol_col=nan(n,1); pol_label=strings(n,1); p_col=nan(n,1); lb_col=nan(n,1); gain_col=nan(n,1); row=0;
for ci=1:numel(coasts)
 for pi=1:numel(pols)
  for ti=1:numel(pvals)
   row=row+1; coast_col(row)=coasts(ci); pol_col(row)=pols(pi); pol_label(row)=labels(pi); p_col(row)=pvals(ti);
   lb_col(row)=tl_p452(params.frequency_ghz,pvals(ti),d,h,g,zone,params.htg_m,params.hrg_m,params.tx_longitude_deg,params.tx_latitude_deg,params.rx_longitude_deg,params.rx_latitude_deg,0.0,0.0,pols(pi),coasts(ci),coasts(ci),params.pressure_hpa,params.temperature_c);
   gain_col(row)=10.^(-lb_col(row)/10);
  end
 end
end
results=table(coast_col,pol_col,pol_label,p_col,lb_col,gain_col,'VariableNames',{'coast_distance_km','polarization_code','polarization_label','time_percentage','basic_transmission_loss_db','path_gain_linear'});
writetable(results,fullfile(work_dir,'p452_basic_loss.csv'));
impl=sprintf('ITU-R P.452-18 reference v18.0 commit %s; MATLAB %s',params.p452_reference_commit,version('-release'));
rows=height(results); coupling=table(zeros(rows,1),repmat(string(params.station_id),rows,1),repmat(string(params.sector_id),rows,1),"P452_p"+string(results.time_percentage)+"_coast"+string(results.coast_distance_km)+"_"+results.polarization_label,repmat(params.frequency_ghz,rows,1),ones(rows,1),results.path_gain_linear,ones(rows,1),false(rows,1),repmat("none_documented",rows,1),repmat(string(impl),rows,1),repmat("ONE_SECTOR_ACCOUNTING_AUDIT_NOT_PAPER_RESULT; Gt=Gr=0dBi; g=h; no separate P2108; coast-distance sensitivity; no antenna gain included",rows,1),'VariableNames',{'time_index','incumbent_id','sector_id','tone_group','frequency_ghz','spectral_overlap_fraction','path_gain_linear','receiver_gain_linear','element_gain_accounted','clutter_treatment','implementation_version','provenance_note'});
writetable(coupling,fullfile(work_dir,'p452_coupling_export.csv'));
a=struct(); a.created_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX')); a.status='PASS'; a.claim_boundary=params.claim_boundary; a.matlab_release=version('-release'); a.matlab_version=version; a.p452_reference_commit=params.p452_reference_commit; a.sector_id=params.sector_id; a.profile_point_count=height(profile); a.distance_km=d(end); a.time_percentages=pvals; a.polarization_codes=pols; a.coast_distance_scenarios_km=coasts; a.row_count=height(results); a.minimum_basic_loss_db=min(results.basic_transmission_loss_db); a.maximum_basic_loss_db=max(results.basic_transmission_loss_db); a.zero_terminal_horizon_gains_inside_p452=true; a.clutter_mode=params.clutter_mode; a.separate_p2108_loss_db=0.0;
fid=fopen(fullfile(work_dir,'P452_FIRST_SECTOR_MATLAB_AUDIT.json'),'w'); assert(fid>=0); c=onCleanup(@() fclose(fid)); fprintf(fid,'%s\n',jsonencode(a,PrettyPrint=true));
fprintf('FIRST-SECTOR P.452 MATLAB RUN: PASS\n'); fprintf('Sector: %s\n',params.sector_id); fprintf('Profile points: %d\n',height(profile)); fprintf('Distance: %.9f km\n',d(end)); fprintf('Rows: %d\n',height(results)); fprintf('Time percentages: '); fprintf('%.12g ',pvals); fprintf('\n'); fprintf('Coast scenarios (km): '); fprintf('%.12g ',coasts); fprintf('\n'); fprintf('Polarizations: '); fprintf('%s ',labels); fprintf('\n'); fprintf('Basic loss range: %.9f to %.9f dB\n',min(results.basic_transmission_loss_db),max(results.basic_transmission_loss_db)); fprintf('Terminal horizon gains inside P.452: 0 dBi / 0 dBi\n'); fprintf('Separate P.2108 baseline loss: 0 dB\n');
end
