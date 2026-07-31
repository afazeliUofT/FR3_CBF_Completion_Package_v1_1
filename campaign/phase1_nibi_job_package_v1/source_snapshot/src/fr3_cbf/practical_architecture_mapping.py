"""Generic 64T64R and hybrid subarray architecture mapping tools.

The mappings are explicit engineering models, not replicas of a vendor radio.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from fr3_cbf.online_pf_load_transition import LoadState

C_M_S=299_792_458.0

@dataclass(frozen=True)
class GenericArchitecture:
    architecture_id:str
    rf_chains:int
    analog_phase_bits:int|None
    groups:tuple[tuple[int,...],...]
    analog_matrix_by_sector:np.ndarray
    effective_steering_pol1:np.ndarray
    effective_steering_pol2:np.ndarray
    maximum_column_orthogonality_error:float

@dataclass(frozen=True)
class GenericModeMatrices:
    perpendicular:np.ndarray
    polarization_1:np.ndarray
    polarization_2:np.ndarray

def rotation_matrix_zyx(yaw:float,pitch:float,roll:float)->np.ndarray:
    ca,sa=math.cos(yaw),math.sin(yaw); cb,sb=math.cos(pitch),math.sin(pitch); cg,sg=math.cos(roll),math.sin(roll)
    rz=np.array([[ca,-sa,0.0],[sa,ca,0.0],[0.0,0.0,1.0]])
    ry=np.array([[cb,0.0,sb],[0.0,1.0,0.0],[-sb,0.0,cb]])
    rx=np.array([[1.0,0.0,0.0],[0.0,cg,-sg],[0.0,sg,cg]])
    return rz@ry@rx

def port_groups(rf_chains:int)->tuple[tuple[int,...],...]:
    result=[]
    if rf_chains==128:
        return tuple((index,) for index in range(128))
    if rf_chains==64:
        for offset in (0,64):
            for column in range(8):
                for pair in range(4):
                    result.append((offset+8*column+2*pair,offset+8*column+2*pair+1))
    elif rf_chains==32:
        for offset in (0,64):
            for col_pair in range(4):
                for row_pair in range(4):
                    result.append(tuple(offset+8*column+row for column in (2*col_pair,2*col_pair+1) for row in (2*row_pair,2*row_pair+1)))
    else:
        raise ValueError("supported RF-chain counts are 128, 64, and 32")
    if len(result)!=rf_chains or sorted(index for group in result for index in group)!=list(range(128)):
        raise RuntimeError("invalid disjoint subarray grouping")
    return tuple(result)

def _mean_local_user_direction(sector:int,user_table:pd.DataFrame,sector_table:pd.DataFrame)->np.ndarray:
    row=sector_table.iloc[sector]
    bs=row[["x_m","y_m","z_m"]].to_numpy(float)
    users=user_table.loc[user_table["serving_bs_index"]==sector,["x_m","y_m","z_m"]].to_numpy(float)
    direction=users-bs[None,:]
    direction/=np.linalg.norm(direction,axis=1,keepdims=True)
    world=direction.mean(axis=0); world/=np.linalg.norm(world)
    local=rotation_matrix_zyx(float(row.yaw_rad),float(row.pitch_rad),float(row.roll_rad)).T@world
    return local/np.linalg.norm(local)

def _quantized_phase(value:np.ndarray,bits:int|None)->np.ndarray:
    if bits is None:
        return np.exp(1j*np.angle(value))
    levels=2**int(bits); phase=np.angle(value)%(2.0*np.pi); index=np.round(phase*levels/(2.0*np.pi))%levels
    return np.exp(1j*2.0*np.pi*index/levels)

def build_architecture(architecture_id:str,rf_chains:int,analog_phase_bits:int|None,port_table:pd.DataFrame,user_table:pd.DataFrame,sector_table:pd.DataFrame,steering_pol1:np.ndarray,steering_pol2:np.ndarray,carrier_frequency_hz:float)->GenericArchitecture:
    positions=port_table[["x_m","y_m","z_m"]].to_numpy(float)
    groups=port_groups(rf_chains)
    analog=np.zeros((57,128,rf_chains),dtype=np.complex64)
    effective1=np.empty((57,rf_chains),dtype=np.complex64); effective2=np.empty_like(effective1)
    maximum_error=0.0
    for sector in range(57):
        if rf_chains==128:
            matrix=np.eye(128,dtype=np.complex64)
        else:
            local=_mean_local_user_direction(sector,user_table,sector_table)
            ideal=np.exp(-1j*2.0*np.pi*float(carrier_frequency_hz)/C_M_S*(positions@local))
            phase=_quantized_phase(ideal,analog_phase_bits)
            matrix=np.zeros((128,rf_chains),dtype=np.complex64)
            for column,group in enumerate(groups):
                matrix[list(group),column]=phase[list(group)]/math.sqrt(len(group))
        gram=matrix.conj().T@matrix
        maximum_error=max(maximum_error,float(np.max(np.abs(gram-np.eye(rf_chains)))))
        analog[sector]=matrix
        effective1[sector]=matrix.conj().T@steering_pol1[sector]
        effective2[sector]=matrix.conj().T@steering_pol2[sector]
    return GenericArchitecture(architecture_id,rf_chains,analog_phase_bits,groups,analog,effective1,effective2,maximum_error)

def effective_channel(frequency_response:np.ndarray,architecture:GenericArchitecture)->np.ndarray:
    h=np.asarray(frequency_response)
    result=np.empty((9,228,57,architecture.rf_chains),dtype=np.complex64)
    for sector in range(57):
        result[:,:,sector]=np.einsum("fum,mr->fur",np.asarray(h[:,:,sector]),architecture.analog_matrix_by_sector[sector],optimize=True)
    return result

def _local_rzf(rows:np.ndarray,power_w:float,noise_w:float)->np.ndarray:
    h=np.asarray(rows,dtype=np.complex128); columns=h.conj().T; users=h.shape[0]; alpha=max(float(users*noise_w/power_w),1e-20); gram=columns.conj().T@columns; eye=np.eye(users,dtype=np.complex128); value=columns@np.linalg.solve(gram+alpha*eye,eye); norm=float(np.sum(np.abs(value)**2).real)
    if not np.isfinite(norm) or norm<=0.0: raise RuntimeError("invalid RZF norm")
    return (value*math.sqrt(float(power_w)/norm)).astype(np.complex64)

def recompute_architecture_load_state(h_effective:np.ndarray,active_user:np.ndarray,serving_bs_index:np.ndarray,serving_stream_index:np.ndarray,transmit_power_by_frequency_w:np.ndarray,noise_power_by_frequency_w:np.ndarray,frequency_weights:np.ndarray,protected_frequency_index:int,steering_pol1:np.ndarray,steering_pol2:np.ndarray)->tuple[LoadState,GenericModeMatrices,dict[str,float]]:
    h=np.asarray(h_effective); active=np.asarray(active_user,dtype=bool); serving=np.asarray(serving_bs_index,dtype=np.int64); stream=np.asarray(serving_stream_index,dtype=np.int64); power=np.asarray(transmit_power_by_frequency_w,float); noise=np.asarray(noise_power_by_frequency_w,float); weights=np.asarray(frequency_weights,float); rf=h.shape[-1]
    precoder=np.zeros((9,57,rf,4),dtype=np.complex64); minimum_nullspace=10**9; maximum_condition=0.0; rank_failures=0
    for bs in range(57):
        users=np.flatnonzero((serving==bs)&active); local_stream=stream[users]; minimum_nullspace=min(minimum_nullspace,rf-len(users)-2)
        for frequency in range(9):
            rows=np.asarray(h[frequency,users,bs]); singular=np.linalg.svd(rows,compute_uv=False); rank_failures+=int(np.sum(singular>max(float(singular[0])*1e-8,1e-12))<len(users)); maximum_condition=max(maximum_condition,float(singular[0]/max(singular[-1],1e-30))); precoder[frequency,bs][:,local_stream]=_local_rzf(rows,float(power[frequency]),float(noise[frequency]))
    amplitude=np.einsum("fubr,fbrk->fubk",h,precoder,optimize=True).astype(np.complex64); amp_power=np.abs(amplitude)**2; total=amp_power.sum(axis=(2,3)); desired=amp_power[:,np.arange(228),serving,stream]; rate=np.log2(1.0+desired/(total-desired+noise[:,None])); rate[:,~active]=0.0; total_rate=(weights[:,None]*rate).sum(axis=0); protected=rate[protected_frequency_index].copy(); other=total_rate-float(weights[protected_frequency_index])*protected
    p0=np.empty((57,rf,4),dtype=np.complex128); p1=np.empty_like(p0); p2=np.empty_like(p0); a0=np.empty((228,57,4),dtype=np.complex64); a1=np.empty_like(a0); a2=np.empty_like(a0); leakage=np.empty((57,2),dtype=np.float64); maximum_mode_condition=0.0
    for bs in range(57):
        v1=np.asarray(steering_pol1[bs],dtype=np.complex128); v2=np.asarray(steering_pol2[bs],dtype=np.complex128); matrix=np.column_stack((v1,v2)); singular=np.linalg.svd(matrix,compute_uv=False); maximum_mode_condition=max(maximum_mode_condition,float(singular[0]/max(singular[-1],1e-30))); u1=v1/np.linalg.norm(v1); orthogonal=v2-u1*(u1.conj()@v2); u2=orthogonal/np.linalg.norm(orthogonal); value=np.asarray(precoder[protected_frequency_index,bs],dtype=np.complex128); value1=u1[:,None]*(u1.conj()@value)[None,:]; value2=u2[:,None]*(u2.conj()@value)[None,:]; value0=value-value1-value2; p0[bs]=value0; p1[bs]=value1; p2[bs]=value2; channel=np.asarray(h[protected_frequency_index,:,bs],dtype=np.complex128); a0[:,bs]=(channel@value0).astype(np.complex64); a1[:,bs]=(channel@value1).astype(np.complex64); a2[:,bs]=(channel@value2).astype(np.complex64); coefficient1=v1.conj()@value; coefficient2=v2.conj()@value; leakage[bs]=[np.sum(np.abs(coefficient1)**2),np.sum(np.abs(coefficient2)**2)]
    state=LoadState(active,precoder,total_rate,protected,other,a0,a1,a2,leakage)
    audit={"minimum_available_digital_nullspace_dimension":int(minimum_nullspace),"local_channel_rank_failure_count":int(rank_failures),"maximum_local_channel_condition_number":float(maximum_condition),"maximum_protected_mode_condition_number":float(maximum_mode_condition)}
    return state,GenericModeMatrices(p0,p1,p2),audit

def safe_precoder(matrices:GenericModeMatrices,q_db:np.ndarray)->np.ndarray:
    scale=np.power(10.0,-np.asarray(q_db,float)/20.0)
    return matrices.perpendicular+scale[:,0,None,None]*matrices.polarization_1+scale[:,1,None,None]*matrices.polarization_2

def mode_leakage(precoder:np.ndarray,steering_pol1:np.ndarray,steering_pol2:np.ndarray)->np.ndarray:
    c1=np.einsum("br,brk->bk",np.asarray(steering_pol1).conj(),np.asarray(precoder),optimize=True); c2=np.einsum("br,brk->bk",np.asarray(steering_pol2).conj(),np.asarray(precoder),optimize=True)
    return np.column_stack((np.sum(np.abs(c1)**2,axis=1),np.sum(np.abs(c2)**2,axis=1))).astype(np.float64)
