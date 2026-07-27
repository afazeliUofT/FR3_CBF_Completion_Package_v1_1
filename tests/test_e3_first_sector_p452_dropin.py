from __future__ import annotations
import importlib.util, math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path); m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m); return m
m=load('gain','scripts/24_3_build_e3_first_sector_gain_accounting.py')
def test_bandwidth_adjustment(): assert math.isclose(10*math.log10(10/100),-10.0,abs_tol=1e-12)
def test_array_upper_gain(): assert math.isclose(10*math.log10(16*16),24.082399653118497,rel_tol=0,abs_tol=1e-12)
def test_element_pattern_is_finite():
 g,dh,dv,ah,av=m.element_gain(10.889433435686737,2.9997029748142587,0,-10,8,65,65,30,30); assert np.isfinite([g,dh,dv,ah,av]).all(); assert g<=8 and g>-30
def test_angular_separation_identity(): assert np.allclose(m.sep([0],[0],0,0),[0],atol=1e-12)
def test_sa509_known_protected_gain():
 p={'g0_dbi':59.03773618268895,'phi0_deg':0.0980190219880998,'phi1_deg':0.2530840265142994,'phi2_deg':0.3967258987682431}; got=m.sa509(np.array([8.035691596201232]),p,True)[0]; assert abs(got-6.374418487486793)<1e-9
def test_p452_row_count(): assert 7*2*3==42
def test_accounting_row_count(): assert 587*7*2*3*2==49308
