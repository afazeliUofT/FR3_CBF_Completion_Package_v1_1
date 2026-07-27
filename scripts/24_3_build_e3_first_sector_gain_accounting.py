#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, hashlib
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd, yaml
import matplotlib.pyplot as plt
from pyproj import Geod
ROOT=Path(__file__).resolve().parents[1]

def write_json(p,o): p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def uv(az,el):
 a=np.radians(az); e=np.radians(el); return np.stack((np.cos(e)*np.sin(a),np.cos(e)*np.cos(a),np.sin(e)),axis=-1)
def sep(az1,el1,az2,el2):
 u1=uv(np.asarray(az1,float),np.asarray(el1,float)); u2=uv(float(az2),float(el2)); return np.degrees(np.arccos(np.clip(u1@u2,-1,1)))
def sa509(phi,p,multiple):
 phi=np.asarray(phi,float); out=np.empty_like(phi); g0=p['g0_dbi']; p0=p['phi0_deg']; p1=p['phi1_deg']; p2=p['phi2_deg']
 m1=phi<p1; m2=(phi>=p1)&(phi<p2); m3=(phi>=p2)&(phi<48); m4=(phi>=48)&(phi<80); m5=(phi>=80)&(phi<120); m6=phi>=120
 out[m1]=g0-3*(phi[m1]/p0)**2; out[m2]=g0-(20 if multiple else 17); out[m3]=(29 if multiple else 32)-25*np.log10(phi[m3])
 if multiple: out[m4]=-13; out[m5]=-8; out[m6]=-13
 else: out[m4]=-10; out[m5]=-5; out[m6]=-10
 return out
def wrap_delta(a,b): return (float(a)-float(b)+180)%360-180
def element_gain(target_az,target_el,sector_az,boresight_el,gmax,hbw,vbw,amax,slav):
 dh=wrap_delta(target_az,sector_az); dv=float(target_el)-float(boresight_el)
 ah=-min(12*(dh/hbw)**2,amax); av=-min(12*(dv/vbw)**2,slav); return gmax-min(-(ah+av),amax),dh,dv,ah,av

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--config',default='config/e3_first_sector_p452.yaml'); args=ap.parse_args(); cfg=yaml.safe_load((ROOT/args.config).read_text()); inp={k:ROOT/v for k,v in cfg['inputs'].items()}; d=ROOT/cfg['outputs']['work_dir']; review=ROOT/cfg['outputs']['review_dir']; review.mkdir(parents=True,exist_ok=True)
 results=pd.read_csv(d/'p452_basic_loss.csv'); ma=json.loads((d/'P452_FIRST_SECTOR_MATLAB_AUDIT.json').read_text()); selected=json.loads(inp['selected_sector_json'].read_text()); station=pd.read_csv(inp['earth_station_csv']).iloc[0]; sites=pd.read_csv(inp['bs_sites_csv']); sectors=pd.read_csv(inp['bs_sectors_csv']); track=pd.read_csv(inp['selected_pass_track_csv']); pp=pd.read_csv(inp['pattern_parameters_csv'])
 if ma['status']!='PASS': raise ValueError('MATLAB audit did not pass')
 sector=sectors.loc[sectors.sector_id.astype(str)==cfg['expected']['sector_id']].iloc[0]; site=sites.loc[sites.site_id.astype(str)==cfg['expected']['site_id']].iloc[0]
 protected=track.loc[pd.to_numeric(track.elevation_deg,errors='coerce')>=float(cfg['expected']['minimum_elevation_deg'])].copy().reset_index(drop=True)
 if len(protected)!=int(cfg['expected']['protected_window_sample_count']): raise ValueError('Protected sample count mismatch')
 # Compute the station->site direction independently from the frozen coordinates.
 # On an ellipsoid, the reverse bearing is not exactly site_to_station+180 degrees.
 geod=Geod(ellps='WGS84')
 station_to_site_az,_,station_to_site_distance_m=geod.inv(
  float(station.longitude_deg),float(station.latitude_deg),
  float(site.longitude_deg),float(site.latitude_deg)
 )
 station_to_site_az%=360.0
 station_to_site_el=math.degrees(math.atan2(
  float(site.antenna_altitude_m_asl)-float(station.altitude_m_asl),
  station_to_site_distance_m
 ))
 off=sep(protected.azimuth_deg.to_numpy(float),protected.elevation_deg.to_numpy(float),station_to_site_az,station_to_site_el)
 gain_frames=[]
 for eff in sorted(pp.aperture_efficiency.unique()):
  for ptype,multiple in [('multiple_entry_section_1_2',True),('single_entry_section_1_1',False)]:
   row=pp.loc[(np.isclose(pp.aperture_efficiency,float(eff)))&(pp.pattern_type==ptype)].iloc[0].to_dict(); g=sa509(off,row,multiple)
   gain_frames.append(pd.DataFrame({'time_utc':protected.time_utc,'time_s':protected.time_s,'satellite_azimuth_deg':protected.azimuth_deg,'satellite_elevation_deg':protected.elevation_deg,'station_to_site_azimuth_deg':station_to_site_az,'station_to_site_elevation_deg':station_to_site_el,'earth_station_off_axis_deg':off,'earth_station_gain_dbi':g,'aperture_efficiency':float(eff),'pattern_type':ptype}))
 es=pd.concat(gain_frames,ignore_index=True); es.to_csv(d/'earth_station_gain_timeseries.csv',index=False)
 nominal_eff=float(cfg['earth_station_gain_reference']['nominal_efficiency']); nominal_mult=es.loc[(np.isclose(es.aperture_efficiency,nominal_eff))&(es.pattern_type==cfg['earth_station_gain_reference']['nominal_pattern_type'])].copy(); nominal_single=es.loc[(np.isclose(es.aperture_efficiency,nominal_eff))&(es.pattern_type==cfg['earth_station_gain_reference']['sensitivity_pattern_type'])].copy()
 if abs(nominal_mult.earth_station_off_axis_deg.min()-float(selected['minimum_earth_station_off_axis_deg']))>1e-7: raise ValueError('Independent off-axis minimum mismatch')
 if abs(nominal_mult.earth_station_gain_dbi.max()-float(selected['maximum_reference_earth_station_gain_dbi']))>1e-7: raise ValueError('Independent ES gain maximum mismatch')
 ep=cfg['bs_gain_reference']['element_pattern']; g_element,dh,dv,ah,av=element_gain(float(selected['site_to_station_azimuth_deg']),float(selected['site_to_station_elevation_deg']),float(sector.azimuth_deg),-float(sector.downtilt_deg),float(sector.element_gain_dbi),float(ep['horizontal_3db_beamwidth_deg']),float(ep['vertical_3db_beamwidth_deg']),float(ep['front_back_limit_db']),float(ep['vertical_sidelobe_limit_db']))
 n=int(sector.array_rows)*int(sector.array_cols); array_upper=10*math.log10(n)
 bs=pd.DataFrame([
  {'gain_case':'ZERO_DBI_PROPAGATION_REFERENCE','bs_gain_dbi':0.0,'status':'pure propagation accounting reference'},
  {'gain_case':'ELEMENT_PATTERN_REFERENCE','bs_gain_dbi':g_element,'status':cfg['bs_gain_reference']['model_status']},
  {'gain_case':'COHERENT_ARRAY_UPPER_ENVELOPE','bs_gain_dbi':g_element+array_upper,'status':'conservative total-power coherent upper envelope; not final composite beam gain'},
 ])
 for k,v in {'target_azimuth_deg':float(selected['site_to_station_azimuth_deg']),'target_elevation_deg':float(selected['site_to_station_elevation_deg']),'sector_azimuth_deg':float(sector.azimuth_deg),'sector_boresight_elevation_deg':-float(sector.downtilt_deg),'horizontal_offset_deg':dh,'vertical_offset_deg':dv,'horizontal_attenuation_db':ah,'vertical_attenuation_db':av,'array_element_count':n,'coherent_array_gain_upper_db':array_upper,'peak_element_gain_dbi':float(sector.element_gain_dbi)}.items(): bs[k]=v
 bs.to_csv(d/'bs_gain_accounting.csv',index=False)
 pwr_dbw_100=float(sector.conducted_power_dbm_per_100mhz)-30; bw_adj=10*math.log10(float(cfg['power_accounting']['protected_bandwidth_mhz'])/float(cfg['power_accounting']['reference_bandwidth_mhz'])); activity=float(sector.activity_factor); act_db=10*math.log10(activity) if activity>0 else -np.inf; pol_loss=float(cfg['power_accounting']['polarization_mismatch_loss_db'])
 nominal_coast=float(cfg['propagation']['nominal_coast_distance_km']); pnom=results.loc[np.isclose(results.coast_distance_km,nominal_coast)].copy()
 es_cases={'multiple_entry_section_1_2':nominal_mult,'single_entry_section_1_1':nominal_single}; frames=[]
 for _,pr in pnom.iterrows():
  for _,br in bs.iterrows():
   for pname,eg in es_cases.items():
    inter=pwr_dbw_100+bw_adj+act_db+float(br.bs_gain_dbi)-float(pr.basic_transmission_loss_db)+eg.earth_station_gain_dbi.to_numpy(float)-pol_loss
    frames.append(pd.DataFrame({'time_utc':eg.time_utc,'time_s':eg.time_s,'satellite_elevation_deg':eg.satellite_elevation_deg,'earth_station_off_axis_deg':eg.earth_station_off_axis_deg,'earth_station_gain_dbi':eg.earth_station_gain_dbi,'earth_station_pattern_type':pname,'coast_distance_km':float(pr.coast_distance_km),'p452_time_percentage':float(pr.time_percentage),'polarization_code':int(pr.polarization_code),'polarization_label':str(pr.polarization_label),'basic_transmission_loss_db':float(pr.basic_transmission_loss_db),'path_gain_linear':float(pr.path_gain_linear),'bs_gain_case':str(br.gain_case),'bs_gain_dbi':float(br.bs_gain_dbi),'conducted_power_dbw_per_100mhz':pwr_dbw_100,'bandwidth_adjustment_db':bw_adj,'activity_factor':activity,'activity_adjustment_db':act_db,'polarization_mismatch_loss_db':pol_loss,'conditional_interference_dbw_per_10mhz':inter,'long_threshold_dbw_per_10mhz':float(cfg['protection']['long_threshold_dbw_per_10mhz']),'short_threshold_dbw_per_10mhz':float(cfg['protection']['short_threshold_dbw_per_10mhz']),'long_exceeded':inter>float(cfg['protection']['long_threshold_dbw_per_10mhz']),'short_exceeded':inter>float(cfg['protection']['short_threshold_dbw_per_10mhz'])}))
 ts=pd.concat(frames,ignore_index=True); ts.to_csv(d/'gain_accounting_timeseries.csv.gz',index=False,compression='gzip')
 summary=(ts.groupby(['coast_distance_km','p452_time_percentage','polarization_label','bs_gain_case','earth_station_pattern_type'],as_index=False).agg(max_interference_dbw_per_10mhz=('conditional_interference_dbw_per_10mhz','max'),min_interference_dbw_per_10mhz=('conditional_interference_dbw_per_10mhz','min'),mean_interference_dbw_per_10mhz=('conditional_interference_dbw_per_10mhz','mean'),long_exceedance_fraction=('long_exceeded','mean'),short_exceedance_fraction=('short_exceeded','mean'),minimum_off_axis_deg=('earth_station_off_axis_deg','min'),maximum_earth_station_gain_dbi=('earth_station_gain_dbi','max')))
 summary.to_csv(d/'conditional_threshold_summary.csv',index=False)
 # Coast-distance sensitivity summary.
 coast=(results.groupby(['coast_distance_km','time_percentage','polarization_label'],as_index=False).agg(basic_transmission_loss_db=('basic_transmission_loss_db','first'))); coast.to_csv(d/'p452_coast_distance_sensitivity.csv',index=False)
 # Plots.
 fig,ax=plt.subplots(figsize=(8.5,5));
 for (c,p),g in results.groupby(['coast_distance_km','polarization_label']): ax.semilogx(g.time_percentage,g.basic_transmission_loss_db,marker='o',label=f'coast={c:g} km, {p}')
 ax.invert_xaxis(); ax.set_xlabel('P.452 time percentage p (%)'); ax.set_ylabel('Basic transmission loss (dB)'); ax.grid(True,which='both',alpha=.3); ax.legend(fontsize=7); ax.set_title('First-sector P.452 basic-loss sensitivity'); fig.tight_layout(); fig.savefig(review/'p452_basic_loss_vs_time_percentage.png',dpi=180); plt.close(fig)
 fig,ax1=plt.subplots(figsize=(9,5)); x=nominal_mult.time_s.to_numpy(float); ax1.plot(x,nominal_mult.earth_station_off_axis_deg,label='off-axis angle',color='C0'); ax1.set_ylabel('Off-axis angle (deg)'); ax1.set_xlabel('Time (s)'); ax1.grid(True,alpha=.3); ax2=ax1.twinx(); ax2.plot(x,nominal_mult.earth_station_gain_dbi,label='aggregate pattern gain',color='C1'); ax2.plot(x,nominal_single.earth_station_gain_dbi,label='single-entry sensitivity gain',color='C2',linestyle='--'); ax2.set_ylabel('Earth-station gain (dBi)'); lines=ax1.lines+ax2.lines; ax1.legend(lines,[l.get_label() for l in lines],fontsize=8); ax1.set_title('Protected-window earth-station geometry and reference gain'); fig.tight_layout(); fig.savefig(review/'earth_station_off_axis_and_gain.png',dpi=180); plt.close(fig)
 subset=ts.loc[(np.isclose(ts.p452_time_percentage,20.0))&(ts.polarization_label=='H')&(ts.earth_station_pattern_type=='multiple_entry_section_1_2')]
 fig,ax=plt.subplots(figsize=(9,5));
 for case,g in subset.groupby('bs_gain_case'): ax.plot(g.time_s,g.conditional_interference_dbw_per_10mhz,label=case)
 ax.axhline(float(cfg['protection']['long_threshold_dbw_per_10mhz']),linestyle='--',label='long threshold'); ax.axhline(float(cfg['protection']['short_threshold_dbw_per_10mhz']),linestyle=':',label='short threshold'); ax.set_xlabel('Time (s)'); ax.set_ylabel('Conditional interference (dBW/10 MHz)'); ax.grid(True,alpha=.3); ax.legend(fontsize=7); ax.set_title('Conditional first-sector accounting: P.452 p=20%, H branch'); fig.tight_layout(); fig.savefig(review/'conditional_interference_p20_H.png',dpi=180); plt.close(fig)
 peak=ts.loc[(np.isclose(ts.p452_time_percentage,20.0))&(ts.polarization_label=='H')&(ts.bs_gain_case=='COHERENT_ARRAY_UPPER_ENVELOPE')&(ts.earth_station_pattern_type=='multiple_entry_section_1_2')].sort_values('conditional_interference_dbw_per_10mhz').iloc[-1]
 components=pd.DataFrame({'component':['Power / 100 MHz','100-to-10 MHz','Activity','BS gain','-P.452 loss','ES gain','-polarization loss'],'value_db':[pwr_dbw_100,bw_adj,act_db,float(peak.bs_gain_dbi),-float(peak.basic_transmission_loss_db),float(peak.earth_station_gain_dbi),-pol_loss]}); components.to_csv(d/'peak_accounting_components.csv',index=False)
 fig,ax=plt.subplots(figsize=(9,4.8)); ax.bar(components.component,components.value_db); ax.axhline(0,color='black',linewidth=.7); ax.set_ylabel('Accounting term (dB or dBW)'); ax.tick_params(axis='x',rotation=35); ax.set_title(f"Peak conditional accounting; sum={peak.conditional_interference_dbw_per_10mhz:.3f} dBW/10 MHz"); fig.tight_layout(); fig.savefig(review/'peak_accounting_components.png',dpi=180); plt.close(fig)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'ACCOUNTING_READY_FOR_VALIDATION','claim_boundary':cfg['claim_boundary'],'sector_id':cfg['expected']['sector_id'],'protected_sample_count':len(protected),'p452_row_count':len(results),'gain_timeseries_row_count':len(ts),'nominal_coast_distance_km':nominal_coast,'conducted_power_dbw_per_100mhz':pwr_dbw_100,'bandwidth_adjustment_db':bw_adj,'activity_factor':activity,'polarization_mismatch_loss_db':pol_loss,'bs_gain_cases':bs[['gain_case','bs_gain_dbi']].to_dict('records'),'earth_station_minimum_off_axis_deg':float(nominal_mult.earth_station_off_axis_deg.min()),'earth_station_maximum_aggregate_gain_dbi':float(nominal_mult.earth_station_gain_dbi.max()),'time_accounting_status':cfg['protection']['time_accounting_status'],'open_items':['Final composite WMMSE beam gain is not available.','Exact coast distances are not frozen; sensitivity scenarios are retained.','Propagation-time and operational-exceedance composition is not frozen.','Physical polarization/XPD model is not frozen.']}
 write_json(d/'FIRST_SECTOR_P452_AUDIT.json',audit)
 (d/'FIRST_SECTOR_P452_AUDIT.md').write_text(f"# First-sector P.452 and gain-accounting audit\n\n- Status: `{audit['status']}`\n- Sector: `{audit['sector_id']}`\n- Claim boundary: `{audit['claim_boundary']}`\n- Protected samples: `{audit['protected_sample_count']}`\n- P.452 rows: `{audit['p452_row_count']}`\n- Gain-accounting rows: `{audit['gain_timeseries_row_count']}`\n- Nominal coast-distance sensitivity case: `{nominal_coast:g} km`\n- Conducted power: `{pwr_dbw_100:.3f} dBW/100 MHz`\n- 100-to-10 MHz adjustment: `{bw_adj:.3f} dB`\n- Minimum ES off-axis angle: `{audit['earth_station_minimum_off_axis_deg']:.9f} deg`\n- Maximum nominal aggregate ES gain: `{audit['earth_station_maximum_aggregate_gain_dbi']:.9f} dBi`\n\n## Boundaries\n\nThis is a one-sector accounting audit, not a paper result or compliance determination. P.452 time percentage, SA.1027 time criterion, and controller operational tokens remain separate. The final composite WMMSE beam gain and physical polarization model remain open.\n",encoding='utf-8')
 print('FIRST-SECTOR GAIN-ACCOUNTING BUILD: PASS'); print('Protected samples:',len(protected)); print('P.452 rows:',len(results)); print('Accounting rows:',len(ts)); print('Conducted power (dBW/100 MHz):',pwr_dbw_100); print('Bandwidth adjustment (dB):',bw_adj); print('BS gain cases:'); print(bs[['gain_case','bs_gain_dbi']].to_string(index=False)); print('Minimum ES off-axis (deg):',audit['earth_station_minimum_off_axis_deg']); print('Maximum nominal ES gain (dBi):',audit['earth_station_maximum_aggregate_gain_dbi']); print('Time-accounting status:',cfg['protection']['time_accounting_status']); return 0
if __name__=='__main__': raise SystemExit(main())
