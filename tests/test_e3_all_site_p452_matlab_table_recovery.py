from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_matlab_table_name_value_syntax_is_character_vector():
    text = (ROOT / "matlab/run_e3_all_site_p452.m").read_text(
        encoding="utf-8"
    )
    assert text.count("'VariableNames', {") == 2
    assert '"VariableNames", {' not in text


def test_matlab_table_shape_preflights_present():
    text = (ROOT / "matlab/run_e3_all_site_p452.m").read_text(
        encoding="utf-8"
    )
    assert "MATLAB RESULT COLUMN-SHAPE PREFLIGHT: PASS" in text
    assert "MATLAB RESULTS TABLE CONSTRUCTION: PASS" in text
    assert "MATLAB COUPLING TABLE CONSTRUCTION: PASS" in text
    assert "assert(height(results) == n_rows)" in text
    assert "assert(height(coupling) == rows)" in text
