"""Verificación de VigaContinua contra soluciones analíticas."""
import pytest

from estates import (Material, Tramo, VigaContinua, concreto,
                     seccion_rectangular)

L, W, P = 6.0, 10.0, 40.0


@pytest.fixture
def mat():
    return Material("acero", E=2.0e8)                # sin peso propio


@pytest.fixture
def sec():
    return seccion_rectangular("0.10x0.20", 0.10, 0.20)


def test_simplemente_apoyada_carga_uniforme(mat, sec):
    EI = mat.E * sec.Iz
    viga = VigaContinua([Tramo(L, mat, sec, w=W)],
                        ["articulado", "articulado"]).resolver()
    r = viga.resultados[0]
    assert viga.R[0] == pytest.approx(W * L / 2)
    assert viga.R[2] == pytest.approx(W * L / 2)
    assert r["M"].max() == pytest.approx(W * L**2 / 8)
    assert r["v"].min() == pytest.approx(-5 * W * L**4 / (384 * EI))


def test_voladizo_carga_puntual_en_el_extremo(mat, sec):
    EI = mat.E * sec.Iz
    viga = VigaContinua([Tramo(L, mat, sec)], ["empotrado", "libre"],
                        cargas_nodales={1: (P, 0)}).resolver()
    assert viga.D[2] == pytest.approx(-P * L**3 / (3 * EI))
    assert viga.R[0] == pytest.approx(P)
    assert viga.R[1] == pytest.approx(P * L)         # momento de empotramiento


def test_voladizo_carga_uniforme(mat, sec):
    EI = mat.E * sec.Iz
    viga = VigaContinua([Tramo(L, mat, sec, w=W)],
                        ["empotrado", "libre"]).resolver()
    assert viga.D[2] == pytest.approx(-W * L**4 / (8 * EI))


def test_dos_tramos_iguales_carga_uniforme(mat, sec):
    viga = VigaContinua([Tramo(L, mat, sec, w=W), Tramo(L, mat, sec, w=W)],
                        ["articulado"] * 3).resolver()
    assert viga.R[0] == pytest.approx(3 * W * L / 8)
    assert viga.R[2] == pytest.approx(10 * W * L / 8)
    assert viga.resultados[0]["M"][-1] == pytest.approx(-W * L**2 / 8)


def test_doblemente_empotrada_carga_puntual_al_centro(mat, sec):
    EI = mat.E * sec.Iz
    viga = VigaContinua([Tramo(L, mat, sec, puntuales=[(L / 2, P)])],
                        ["empotrado", "empotrado"]).resolver()
    r = viga.resultados[0]
    assert r["M"][0] == pytest.approx(-P * L / 8)
    assert r["M"].max() == pytest.approx(P * L / 8)
    assert r["v"].min() == pytest.approx(-P * L**3 / (192 * EI))


def test_simplemente_apoyada_carga_puntual_excentrica(mat, sec):
    a = 2.0
    viga = VigaContinua([Tramo(L, mat, sec, puntuales=[(a, P)])],
                        ["articulado", "articulado"]).resolver()
    assert viga.R[0] == pytest.approx(P * (L - a) / L)
    assert viga.R[2] == pytest.approx(P * a / L)
    assert viga.resultados[0]["M"].max() == pytest.approx(P * a * (L - a) / L)


# --- Ejemplo de dos tramos con peso propio (concreto 30x50 cm) -----------
@pytest.fixture
def viga_ejemplo():
    c21 = concreto(21)
    s = seccion_rectangular("30x50 cm", 0.30, 0.50)
    t1 = Tramo(5.0, c21, s, w=20.0)
    t2 = Tramo(4.0, c21, s, w=15.0, puntuales=[(2.0, 30.0)])
    return VigaContinua([t1, t2], ["articulado"] * 3).resolver()


def test_ejemplo_equilibrio_global(viga_ejemplo):
    carga_total = sum(t.w_total * t.L for t in viga_ejemplo.tramos) + 30.0
    assert viga_ejemplo.R[0::2].sum() == pytest.approx(carga_total)


def test_ejemplo_ecuacion_de_tres_momentos(viga_ejemplo):
    # 2·M_B·(L1 + L2) = w1·L1³/4 + w2·L2³/4 + P·a·b·(L2 + b)/L2
    t1, t2 = viga_ejemplo.tramos
    a, b = 2.0, 2.0
    lado_der = (t1.w_total * t1.L**3 / 4 + t2.w_total * t2.L**3 / 4
                + 30.0 * a * b * (t2.L + b) / t2.L)
    M_B = -lado_der / (2 * (t1.L + t2.L))
    assert viga_ejemplo.resultados[0]["M"][-1] == pytest.approx(M_B)


def test_ejemplo_momento_continuo_sobre_el_apoyo(viga_ejemplo):
    r1, r2 = viga_ejemplo.resultados
    assert r1["M"][-1] == pytest.approx(r2["M"][0])


# --- Ejemplo de tres tramos con peso propio (concreto 25x45 cm) ----------
@pytest.fixture
def viga_tres_tramos():
    c28 = concreto(28)
    s = seccion_rectangular("25x45 cm", 0.25, 0.45)
    t1 = Tramo(4.0, c28, s, w=18.0)
    t2 = Tramo(5.0, c28, s, w=18.0, puntuales=[(2.5, 35.0)])
    t3 = Tramo(3.5, c28, s, w=18.0)
    return VigaContinua([t1, t2, t3], ["articulado"] * 4).resolver()


def test_tres_tramos_equilibrio_global(viga_tres_tramos):
    carga_total = (sum(t.w_total * t.L for t in viga_tres_tramos.tramos)
                   + 35.0)
    assert viga_tres_tramos.R[0::2].sum() == pytest.approx(carga_total)


def test_tres_tramos_momento_continuo_sobre_apoyos(viga_tres_tramos):
    r1, r2, r3 = viga_tres_tramos.resultados
    assert r1["M"][-1] == pytest.approx(r2["M"][0])
    assert r2["M"][-1] == pytest.approx(r3["M"][0])


# --- Validaciones de entrada ---------------------------------------------
def test_mecanismo_lanza_error(mat, sec):
    viga = VigaContinua([Tramo(L, mat, sec, w=W)], ["articulado", "libre"])
    with pytest.raises(ValueError, match="inestable"):
        viga.resolver()


def test_carga_puntual_fuera_del_tramo(mat, sec):
    viga = VigaContinua([Tramo(L, mat, sec, puntuales=[(L, P)])],
                        ["articulado", "articulado"])
    with pytest.raises(ValueError, match="dentro del tramo"):
        viga.resolver()


def test_numero_de_apoyos_incorrecto(mat, sec):
    with pytest.raises(ValueError, match="un apoyo por nudo"):
        VigaContinua([Tramo(L, mat, sec)], ["articulado"])
