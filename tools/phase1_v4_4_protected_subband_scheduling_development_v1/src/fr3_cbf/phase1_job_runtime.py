"""Phase-1 campaign runtime shared by local smoke and Nibi seed workers."""
from __future__ import annotations
from dataclasses import dataclass
import math, time
from typing import Sequence
import numpy as np
from fr3_cbf.constrained_pf_safety import PriceAllocator, action_grid
from fr3_cbf.online_pf_load_transition import (
    build_online_moving_pf_cost_grid,
    exact_user_rates_for_action,
    simulate_online_predictive_controller,
    simulate_online_myopic_controller,
    full_horizon_dynamic_envelope,
)
from fr3_cbf.robust_delayed_safety import choose_with_external_price
from fr3_cbf.null_floor_aware_sector_backoff import (
    simulate_sector_selective, simulate_uniform, exact_rates, exact_second_ratio,
)
from fr3_cbf.practical_architecture_mapping import safe_precoder, mode_leakage

@dataclass(frozen=True)
class EvaluatedRun:
    method_id: str
    q_db: np.ndarray
    sector_power_scale: np.ndarray
    long_ratio: np.ndarray
    short_ratio: np.ndarray
    delivered_total_rate: np.ndarray
    delivered_protected_rate: np.ndarray
    moving_average_rate: np.ndarray
    floor_violation_count: np.ndarray
    normalized_shortfall: np.ndarray
    sector_backoff_db: np.ndarray
    local_table_build_seconds: np.ndarray
    runtime_seconds: float
    extra: dict[str, object]


def _floor_metrics(delivered: np.ndarray, active: np.ndarray, eligible: np.ndarray, floors: np.ndarray):
    mask = np.asarray(active,bool)&np.asarray(eligible,bool)
    valid=mask&(np.asarray(floors,float)>0)
    viol=mask&(np.asarray(delivered,float)<np.asarray(floors,float)-1e-12)
    short=0.0
    if np.any(valid):
        short=float(np.sum(np.maximum(0,(floors[valid]-delivered[valid])/floors[valid])))
    return int(viol.sum()),short


def _mode_second_ratio(kappa, leakage_by_interval, q_by_interval, allowance, update_interval_s, uplift_db):
    k=np.asarray(kappa,float); leak=np.asarray(leakage_by_interval,float); q=np.asarray(q_by_interval,float); a=np.asarray(allowance,float)
    out=np.empty(len(k),float); uplift=10**(float(uplift_db)/10)
    for s in range(len(k)):
        i=min(s//int(update_interval_s),len(leak)-1)
        out[s]=uplift*np.sum(k[s,:,None]*leak[i]*np.power(10,-q[i]/10))/a[s]
    return out


def _evaluate_actions(method_id, q, sector_scale, states, long_kappa, short_kappa, long_allowance, short_allowance,
                      update_interval_s, uplift_db, serving, stream, noise, protected_weight, initial_average,
                      alpha, eligible, floors, runtime_seconds=0.0, sector_backoff=None, local_build=None, extra=None):
    q=np.asarray(q,float); scale=np.asarray(sector_scale,float)
    K=len(states); total=np.empty((K,228)); protected=np.empty_like(total); avg=np.asarray(initial_average,float).copy(); avg_trace=np.empty_like(total)
    fc=np.empty(K,np.int64); sh=np.empty(K,float)
    for i,st in enumerate(states):
        total[i],protected[i]=exact_rates(st,q[i],scale[i],serving,stream,noise,protected_weight)
        fc[i],sh[i]=_floor_metrics(total[i],st.active_user,eligible,floors[i])
        avg=(1-alpha)*avg+alpha*total[i]; avg_trace[i]=avg
    # leakage after q, before sector scale
    # caller may provide in extra to avoid recomputation; otherwise use nominal leakage exact scaling
    leakage=np.asarray([states[i].mode_leakage_w*np.power(10,-q[i]/10) for i in range(K)])
    long_ratio=exact_second_ratio(long_kappa,leakage,scale,long_allowance,update_interval_s,uplift_db)
    short_ratio=exact_second_ratio(short_kappa,leakage,scale,short_allowance,update_interval_s,uplift_db)
    if sector_backoff is None:
        sector_backoff=np.where(scale>0,-10*np.log10(np.maximum(scale,1e-300)),math.inf)
    if local_build is None: local_build=np.zeros(K)
    return EvaluatedRun(method_id,q,scale,long_ratio,short_ratio,total,protected,avg_trace,fc,sh,np.asarray(sector_backoff,float),np.asarray(local_build,float),float(runtime_seconds),extra or {})


def _capped_leakage(q_actions, matrices, matrix_indices, steering1, steering2, cap_db):
    qcap=np.minimum(np.asarray(q_actions,float),float(cap_db)); out=np.empty((len(qcap),57,2),float)
    for i,qq in enumerate(qcap):
        out[i]=mode_leakage(safe_precoder(matrices[matrix_indices[i]],qq),steering1,steering2)
    return qcap,out


def _wrap_backoff(method_id, q_actions, backoff_run, capped_leakage, short_kappa, short_allowance, update_interval_s, uplift_db, runtime, extra=None):
    short=exact_second_ratio(short_kappa,capped_leakage,backoff_run.sector_power_scale,short_allowance,update_interval_s,uplift_db)
    return EvaluatedRun(method_id,np.minimum(q_actions,65.0),backoff_run.sector_power_scale,backoff_run.second_ratio,short,
        backoff_run.delivered_total_rate,backoff_run.delivered_protected_rate,backoff_run.moving_average_rate,
        backoff_run.interval_floor_violation_count,backoff_run.interval_normalized_shortfall,backoff_run.sector_backoff_db,
        backoff_run.local_table_build_seconds,float(runtime),extra or {})


def run_phase1_methods(*, states: Sequence[object], matrices: Sequence[object], matrix_indices: Sequence[int],
        long_kappa: np.ndarray, short_kappa: np.ndarray, long_allowance: np.ndarray, short_allowance: np.ndarray,
        interval_lengths: np.ndarray, long_contribution: np.ndarray, serving: np.ndarray, stream: np.ndarray,
        protected_noise_w: float, protected_weight: float, initial_average: np.ndarray, alpha: float,
        eligible: np.ndarray, floors: np.ndarray, steering1: np.ndarray, steering2: np.ndarray,
        update_interval_s: int=5, delay_intervals: int=1, slew_db: float=3.0, uplift_db: float=3.0,
        cap_db: float=65.0, epsilon: float=0.001, virtual_queue_gain: float=1.0) -> dict[str,EvaluatedRun]:
    K=len(states); qgrid=action_grid(0,70,1); backoff_grid=np.asarray(list(range(13))+[math.inf],float)
    upper=np.asarray(long_contribution,float)*10**(uplift_db/10)
    app,cmd,_=full_horizon_dynamic_envelope(upper,delay_intervals,slew_db)
    methods={}
    # predictive
    t=time.perf_counter()
    pred=simulate_online_predictive_controller(qgrid,states,upper,np.asarray([np.min(long_allowance[i*update_interval_s:min((i+1)*update_interval_s,len(long_allowance))]) for i in range(K)]),app,cmd,
        delay_intervals,slew_db,70,initial_average.copy(),alpha,eligible,floors,serving,stream,protected_noise_w,protected_weight,epsilon,())
    qcap,leak=_capped_leakage(pred.applied_db,matrices,matrix_indices,steering1,steering2,cap_db)
    fb=simulate_sector_selective(pred.applied_db,leak,states,long_kappa,long_allowance,update_interval_s,uplift_db,cap_db,backoff_grid,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,epsilon)
    methods['robust_predictive_constrained_pf_with_sector_selective_fallback']=_wrap_backoff('robust_predictive_constrained_pf_with_sector_selective_fallback',pred.applied_db,fb,leak,short_kappa,short_allowance,update_interval_s,uplift_db,time.perf_counter()-t,{'mode_command_feasible':bool(np.all(pred.command_feasible))})
    # static q from full envelope and initial PF cost
    t=time.perf_counter(); cost,_=build_online_moving_pf_cost_grid(qgrid,states[0],np.zeros((57,2)),initial_average.copy(),eligible,floors[0],serving,stream,protected_noise_w,protected_weight,alpha,epsilon)
    allocator=PriceAllocator(qgrid,cost,float(np.min(long_allowance)))
    qstatic,ratio,ok,_=allocator.solve(np.max(upper,axis=0))
    if not ok: qstatic=np.full((57,2),70.0)
    qs=np.repeat(qstatic[None,:,:],K,axis=0); qcap,leak=_capped_leakage(qs,matrices,matrix_indices,steering1,steering2,cap_db)
    fb=simulate_sector_selective(qs,leak,states,long_kappa,long_allowance,update_interval_s,uplift_db,cap_db,backoff_grid,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,epsilon)
    methods['static_robust_constrained_pf_with_sector_selective_fallback']=_wrap_backoff('static_robust_constrained_pf_with_sector_selective_fallback',qs,fb,leak,short_kappa,short_allowance,update_interval_s,uplift_db,time.perf_counter()-t,{'static_mode_feasible':bool(ok),'static_pre_fallback_ratio':float(ratio)})
    # myopic unshielded and reactive fallback
    t=time.perf_counter()
    myo=simulate_online_myopic_controller(qgrid,states,upper,np.asarray([np.min(long_allowance[i*update_interval_s:min((i+1)*update_interval_s,len(long_allowance))]) for i in range(K)]),delay_intervals,slew_db,initial_average.copy(),alpha,eligible,floors,serving,stream,protected_noise_w,protected_weight,epsilon)
    ones=np.ones((K,57)); un=_evaluate_actions('delayed_myopic_constrained_pf_unshielded',myo.applied_db,ones,states,long_kappa,short_kappa,long_allowance,short_allowance,update_interval_s,uplift_db,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,time.perf_counter()-t,extra={'mode_interval_max_ratio':float(np.max(myo.upper_interval_ratio))})
    methods[un.method_id]=un
    t=time.perf_counter(); qcap,leak=_capped_leakage(myo.applied_db,matrices,matrix_indices,steering1,steering2,cap_db)
    fb=simulate_sector_selective(myo.applied_db,leak,states,long_kappa,long_allowance,update_interval_s,uplift_db,cap_db,backoff_grid,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,epsilon)
    methods['delayed_myopic_constrained_pf_with_reactive_sector_fallback']=_wrap_backoff('delayed_myopic_constrained_pf_with_reactive_sector_fallback',myo.applied_db,fb,leak,short_kappa,short_allowance,update_interval_s,uplift_db,time.perf_counter()-t)
    # virtual queue online diagnostic
    t=time.perf_counter(); command=np.empty((K,57,2)); applied=np.empty_like(command); avg=initial_average.copy(); delivered=np.empty((K,228)); prot=np.empty_like(delivered); avgtr=np.empty_like(delivered); build=np.empty(K); queue=np.zeros(K+1); prev=np.zeros((57,2));
    # safe-ish preload under current upper contribution, no future
    cost,_=build_online_moving_pf_cost_grid(qgrid,states[0],prev,avg,eligible,floors[0],serving,stream,protected_noise_w,protected_weight,alpha,epsilon); alloc=PriceAllocator(qgrid,cost,float(np.min(long_allowance[:update_interval_s]))); preload,_,ok,_=alloc.solve(upper[0]);
    if not ok: preload=np.full((57,2),70.0)
    prev=preload.copy()
    for i,st in enumerate(states):
        src=i-delay_intervals; applied[i]=command[src] if src>=0 else preload
        delivered[i],prot[i]=exact_user_rates_for_action(applied[i],st,serving,stream,protected_noise_w,protected_weight); avg=(1-alpha)*avg+alpha*delivered[i]; avgtr[i]=avg
        stt=time.perf_counter(); cost,_=build_online_moving_pf_cost_grid(qgrid,st,applied[i],avg,eligible,floors[i],serving,stream,protected_noise_w,protected_weight,alpha,epsilon); build[i]=time.perf_counter()-stt; alloc=PriceAllocator(qgrid,cost,float(np.min(long_allowance[i*update_interval_s:min((i+1)*update_interval_s,len(long_allowance))]))); command[i]=choose_with_external_price(alloc,upper[i],virtual_queue_gain*queue[i],prev,slew_db); prev=command[i]
        ratio=float(np.sum(upper[i]*np.power(10,-applied[i]/10))/alloc.allowance); queue[i+1]=max(0.0,queue[i]+ratio-1.0)
    methods['virtual_queue_unshielded']=_evaluate_actions('virtual_queue_unshielded',applied,ones,states,long_kappa,short_kappa,long_allowance,short_allowance,update_interval_s,uplift_db,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,time.perf_counter()-t,local_build=build,extra={'maximum_queue':float(queue.max()),'price_gain':virtual_queue_gain})
    # uniform fallback using predictive q
    t=time.perf_counter(); qcap,leak=_capped_leakage(pred.applied_db,matrices,matrix_indices,steering1,steering2,cap_db)
    uni=simulate_uniform(pred.applied_db,leak,states,long_kappa,long_allowance,update_interval_s,uplift_db,cap_db,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,epsilon)
    methods['uniform_protected_tone_backoff']=_wrap_backoff('uniform_protected_tone_backoff',pred.applied_db,uni,leak,short_kappa,short_allowance,update_interval_s,uplift_db,time.perf_counter()-t)
    # hard null or all-sector mute
    t=time.perf_counter(); qhard=np.full((K,57,2),cap_db); qcap,leak=_capped_leakage(qhard,matrices,matrix_indices,steering1,steering2,cap_db); scale=np.ones((K,57))
    # exact interval max, all-sector mute if any excess
    for i in range(K):
        start=i*update_interval_s; stop=min((i+1)*update_interval_s,len(long_kappa)); ratio=10**(uplift_db/10)*np.max(np.sum(long_kappa[start:stop,:,None]*leak[i][None,:,:],axis=(1,2))/long_allowance[start:stop]);
        if ratio>1+1e-12: scale[i]=0.0
    methods['hard_spatial_null_or_exact_mute']=_evaluate_actions('hard_spatial_null_or_exact_mute',qhard,scale,states,long_kappa,short_kappa,long_allowance,short_allowance,update_interval_s,uplift_db,serving,stream,protected_noise_w,protected_weight,initial_average.copy(),alpha,eligible,floors,time.perf_counter()-t)
    # Instantaneous noncausal common-scale reference. It sees exact coupling
    # at every protected second and has no delay/slew penalty. User rates are
    # averaged over the seconds in each 5-s controller interval before the
    # moving-PF update; this keeps the utility time grid comparable while the
    # reference itself remains explicitly noncausal and nonimplementable.
    t=time.perf_counter()
    qcommon=np.empty((K,57,2),float)
    common_total=np.empty((K,228),float)
    common_protected=np.empty_like(common_total)
    common_long=np.empty(len(long_kappa),float)
    common_short=np.empty(len(short_kappa),float)
    common_avg=np.asarray(initial_average,float).copy()
    common_avg_trace=np.empty_like(common_total)
    common_floor=np.empty(K,np.int64)
    common_shortfall=np.empty(K,float)
    uplift=10**(float(uplift_db)/10)
    for i,st in enumerate(states):
        start=i*int(update_interval_s)
        stop=min((i+1)*int(update_interval_s),len(long_kappa))
        interval_total=[]
        interval_protected=[]
        interval_q=[]
        for second in range(start,stop):
            nominal=float(np.sum(long_kappa[second,:,None]*st.mode_leakage_w))
            required=max(0.0,10*math.log10(max(uplift*nominal/float(long_allowance[second]),1e-300)))
            qq=np.full((57,2),required,float)
            total_rate,protected_rate=exact_user_rates_for_action(
                qq,st,serving,stream,protected_noise_w,protected_weight
            )
            interval_total.append(total_rate)
            interval_protected.append(protected_rate)
            interval_q.append(required)
            leakage=st.mode_leakage_w*np.power(10.0,-required/10.0)
            common_long[second]=uplift*np.sum(long_kappa[second,:,None]*leakage)/long_allowance[second]
            common_short[second]=uplift*np.sum(short_kappa[second,:,None]*leakage)/short_allowance[second]
        common_total[i]=np.mean(np.asarray(interval_total),axis=0)
        common_protected[i]=np.mean(np.asarray(interval_protected),axis=0)
        qcommon[i]=max(interval_q)
        common_floor[i],common_shortfall[i]=_floor_metrics(
            common_total[i],st.active_user,eligible,floors[i]
        )
        common_avg=(1-alpha)*common_avg+alpha*common_total[i]
        common_avg_trace[i]=common_avg
    methods['common_scale_instantaneous_noncausal_reference']=EvaluatedRun(
        'common_scale_instantaneous_noncausal_reference',qcommon,ones,
        common_long,common_short,common_total,common_protected,
        common_avg_trace,common_floor,common_shortfall,
        np.zeros((K,57),float),np.zeros(K,float),time.perf_counter()-t,
        {'time_resolution_seconds':1,'delay_intervals':0,'slew_constraint':False}
    )
    return methods


def summarize_method(run: EvaluatedRun, eligible: np.ndarray, interval_lengths: np.ndarray, epsilon: float=0.001):
    w=np.asarray(interval_lengths,float); pf=np.log(run.moving_average_rate[:,eligible]+epsilon).sum(axis=1)
    active_total=[]; active_protected=[]
    # delivered inactive are zero; use >? caller eligibility only; approximate include positive active values
    for i in range(len(run.delivered_total_rate)):
        vals=run.delivered_total_rate[i,eligible]; p=run.delivered_protected_rate[i,eligible]; mask=vals>0
        active_total.extend(vals[mask].tolist()); active_protected.extend(p[mask].tolist())
    active_total=np.asarray(active_total); active_protected=np.asarray(active_protected)
    mute=np.isinf(run.sector_backoff_db)
    return {
        'method_id':run.method_id,
        'long_violation_seconds':int(np.sum(run.long_ratio>1+1e-10)),
        'short_violation_seconds':int(np.sum(run.short_ratio>1+1e-10)),
        'long_maximum_excess_db':float(10*np.log10(np.max(run.long_ratio))),
        'short_maximum_excess_db':float(10*np.log10(np.max(run.short_ratio))),
        'eligible_floor_violation_user_intervals':int(np.sum(run.floor_violation_count)),
        'eligible_floor_violation_user_seconds':int(np.sum(run.floor_violation_count*np.asarray(interval_lengths))),
        'total_normalized_floor_shortfall':float(np.sum(run.normalized_shortfall)),
        'final_moving_pf_utility':float(pf[-1]),
        'duration_weighted_mean_moving_pf_utility':float(np.average(pf,weights=w)),
        'protected_active_eligible_p05_bps_hz':float(np.quantile(active_protected,.05)),
        'protected_active_eligible_geometric_mean_bps_hz':float(np.exp(np.mean(np.log(active_protected+epsilon)))-epsilon),
        'total_active_eligible_p05_bps_hz':float(np.quantile(active_total,.05)),
        'total_active_eligible_geometric_mean_bps_hz':float(np.exp(np.mean(np.log(active_total+epsilon)))-epsilon),
        'sector_mute_interval_count':int(mute.sum()),
        'intervals_with_any_sector_mute':int(np.sum(np.any(mute,axis=1))),
        'maximum_muted_sector_count':int(np.max(np.sum(mute,axis=1))),
        'runtime_seconds':float(run.runtime_seconds),
        'extra':run.extra,
    }
