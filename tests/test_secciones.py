import numpy as np
import pytest

from estates import seccion_circular, seccion_rectangular


def test_circular_area_e_inercias():
    d = 0.4
    s = seccion_circular("d=0.4", d)
    assert s.A == pytest.approx(np.pi * d**2 / 4)
    assert s.Iy == pytest.approx(np.pi * d**4 / 64)
    assert s.Iz == pytest.approx(np.pi * d**4 / 64)
    assert s.J == pytest.approx(2 * s.Iz)            # J = Ip = 2·I
    assert s.c == pytest.approx(d / 2)


def test_rectangular_area_e_inercias():
    b, h = 0.30, 0.50
    s = seccion_rectangular("30x50", b, h)
    assert s.A == pytest.approx(b * h)
    assert s.Iz == pytest.approx(b * h**3 / 12)      # flexión vertical
    assert s.Iy == pytest.approx(h * b**3 / 12)
    assert s.c == pytest.approx(h / 2)
    assert s.k_tau == 1.5


def test_rectangular_torsion_cuadrado():
    # Para un cuadrado, J ≈ 0.1406·a⁴ (aproximación de Saint-Venant).
    a = 0.2
    s = seccion_rectangular("cuadrado", a, a)
    assert s.J == pytest.approx(0.1406 * a**4, rel=5e-3)


def test_rectangular_torsion_no_depende_del_orden_de_lados():
    s1 = seccion_rectangular("a", 0.2, 0.5)
    s2 = seccion_rectangular("b", 0.5, 0.2)
    assert s1.J == pytest.approx(s2.J)
