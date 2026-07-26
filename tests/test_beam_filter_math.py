import numpy as np

from fr3_cbf.beam_filter import _psd_sqrt


def test_psd_sqrt_reproduces_quadratic_form():
    r = np.array([[2.0, 0.5 - 0.2j], [0.5 + 0.2j, 1.0]], dtype=np.complex128)
    l = _psd_sqrt(r)
    assert np.allclose(l.conj().T @ l, r, atol=1e-10)
    w = np.array([[1.0 + 0.3j], [-0.2 + 0.7j]])
    left = np.linalg.norm(l @ w) ** 2
    right = float(np.real(np.trace(w.conj().T @ r @ w)))
    assert np.isclose(left, right)


def test_psd_sqrt_rejects_non_psd():
    r = np.diag([1.0, -0.1])
    try:
        _psd_sqrt(r)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected non-PSD matrix to be rejected")
