"""Pruebas del modelo de granulometría y clasificación de suelos.

Estrategia de verificación (3 niveles independientes):
  1. Los % retenido/acumulado/que pasa se comprueban con una suma directa
     (sin pasar por la función), para un caso de masas diseñado a mano.
  2. La interpolación se comprueba por consistencia ida-y-vuelta:
     interpolar_pasa(interpolar_diametro(p)) debe devolver p de nuevo, lo
     cual es independiente de si el valor de D "parece" razonable.
  3. D10/D30/D60 también se comparan contra el cálculo manual en semi-log
     (el mismo método con que se leen a mano de la curva en papel
     semilogarítmico), y Cu/Cc contra su fórmula.
"""
import math

import numpy as np
import pytest

from app.modelo import (ABERTURA_NO10, ABERTURA_NO40, Atterberg,
                        CurvaGranulometrica, Tamiz, calcular_curva,
                        clasificar_aashto, clasificar_uscs,
                        interpolar_diametro, interpolar_pasa, procesar)

# ---------------------------------------------------------------------------
# Caso de referencia, diseñado para que los % acumulados sean exactos
# (masa total = 500 g). Se usa en varias pruebas.
# ---------------------------------------------------------------------------
TAMICES_REF = [
    Tamiz("No.4", 4.75, 0),
    Tamiz("No.10", 2.00, 25),
    Tamiz("No.20", 0.850, 50),
    Tamiz("No.40", 0.425, 100),
    Tamiz("No.60", 0.250, 125),
    Tamiz("No.100", 0.150, 100),
    Tamiz("No.200", 0.075, 75),
]
FONDO_REF = 25.0  # masa total = 0+25+50+100+125+100+75+25 = 500 g


def test_porcentajes_retenido_y_pasa():
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    # % que pasa esperado, calculado directamente (independiente de
    # calcular_curva): acumulado de retenidos desde el tamiz más grueso.
    esperado = {
        4.75: 100.0,     # nada retenido en No.4
        2.00: 95.0,      # (500-25)/500*100
        0.850: 85.0,     # (500-75)/500*100
        0.425: 65.0,     # (500-175)/500*100
        0.250: 40.0,     # (500-300)/500*100
        0.150: 20.0,     # (500-400)/500*100
        0.075: 5.0,      # (500-475)/500*100
    }
    for abertura, pasa_esperado in esperado.items():
        i = np.where(np.isclose(curva.abertura_mm, abertura))[0][0]
        assert curva.pasa[i] == pytest.approx(pasa_esperado)
    assert curva.masa_total_g == pytest.approx(500.0)


def test_interpolacion_ida_y_vuelta():
    """interpolar_pasa(interpolar_diametro(p)) debe devolver p: comprueba
    que la inversa realmente invierte a la directa, sin asumir de
    antemano cuál es el valor "correcto" de D."""
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    for objetivo in (10.0, 30.0, 60.0, 17.5, 73.2):
        d = interpolar_diametro(curva.abertura_mm, curva.pasa, objetivo)
        pasa_recuperado = interpolar_pasa(curva.abertura_mm, curva.pasa, d)
        assert pasa_recuperado == pytest.approx(objetivo, abs=1e-6)


def test_D10_D30_D60_contra_calculo_manual_en_semilog():
    """D10, D30 y D60 calculados a mano con el método semi-log estándar
    (interpolación lineal sobre log10 de la abertura entre los dos
    tamices que encierran el % buscado)."""
    curva = calcular_curva(TAMICES_REF, FONDO_REF)

    def manual(p1, x1, p2, x2, objetivo):
        # x = log10(abertura); interpola linealmente en (p, x)
        t = (objetivo - p1) / (p2 - p1)
        log_d = x1 + t * (x2 - x1)
        return 10 ** log_d

    # D10 entre (5%, 0.075mm) y (20%, 0.150mm)
    D10_manual = manual(5, math.log10(0.075), 20, math.log10(0.150), 10)
    # D30 entre (20%, 0.150mm) y (40%, 0.250mm)
    D30_manual = manual(20, math.log10(0.150), 40, math.log10(0.250), 30)
    # D60 entre (40%, 0.250mm) y (65%, 0.425mm)
    D60_manual = manual(40, math.log10(0.250), 65, math.log10(0.425), 60)

    assert curva.D10 == pytest.approx(D10_manual, rel=1e-9)
    assert curva.D30 == pytest.approx(D30_manual, rel=1e-9)
    assert curva.D60 == pytest.approx(D60_manual, rel=1e-9)
    # Valores de referencia (mm), calculados a mano por fuera de pytest
    assert curva.D10 == pytest.approx(0.0945, abs=2e-4)
    assert curva.D30 == pytest.approx(0.1937, abs=2e-4)
    assert curva.D60 == pytest.approx(0.3823, abs=2e-4)


def test_Cu_y_Cc():
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    assert curva.Cu == pytest.approx(curva.D60 / curva.D10, rel=1e-9)
    assert curva.Cc == pytest.approx(
        curva.D30**2 / (curva.D10 * curva.D60), rel=1e-9)
    # Valores de referencia
    assert curva.Cu == pytest.approx(4.05, abs=0.05)
    assert curva.Cc == pytest.approx(1.04, abs=0.03)


def test_fracciones_grava_arena_finos():
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    assert curva.pct_grava == pytest.approx(0.0, abs=1e-9)   # nada en No.4
    assert curva.pct_finos == pytest.approx(5.0, abs=1e-9)   # exacto, No.200
    assert curva.pct_arena == pytest.approx(95.0, abs=1e-9)
    total = curva.pct_grava + curva.pct_arena + curva.pct_finos
    assert total == pytest.approx(100.0)


def test_clasificacion_uscs_simbolo_doble_sp_sc():
    """Con 5 % <= finos <= 12 % y Cu < 6 para arena: símbolo doble SP-SC
    si los finos son arcillosos (PI por encima de la línea A)."""
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    at = Atterberg(LL=25, LP=18)                      # PI = 7
    assert at.PI == pytest.approx(7.0)
    simbolo, _ = clasificar_uscs(curva, at)
    assert simbolo == "SP-SC"


def test_clasificacion_aashto_a2_4():
    curva = calcular_curva(TAMICES_REF, FONDO_REF)
    at = Atterberg(LL=25, LP=18)
    r = clasificar_aashto(curva, at)
    assert r.grupo == "A-2-4"
    assert r.indice_grupo == 0


def test_procesar_de_extremo_a_extremo():
    r = procesar(TAMICES_REF, FONDO_REF, LL=25, LP=18)
    assert r.uscs_simbolo == "SP-SC"
    assert r.aashto.grupo == "A-2-4"
    assert r.curva.Cu == pytest.approx(4.05, abs=0.05)


# ---------------------------------------------------------------------------
# Clasificación USCS: casos límite construidos directamente (sin pasar por
# calcular_curva), para aislar cada rama de la lógica de clasificación.
# ---------------------------------------------------------------------------
def _curva(Cu, Cc, pct_grava, pct_arena, pct_finos, abertura=None, pasa=None):
    if abertura is None:
        abertura = np.array([ABERTURA_NO40, ABERTURA_NO10, 4.75])
        pasa = np.array([max(pct_finos, 1.0), 50.0, 100.0 - pct_grava])
    return CurvaGranulometrica(abertura, pasa, 1000.0, 1.0, 2.0, 4.0,
                               Cu, Cc, pct_grava, pct_arena, pct_finos)


def test_uscs_grava_bien_graduada_GW():
    c = _curva(Cu=5, Cc=2, pct_grava=70, pct_arena=27, pct_finos=3)
    simbolo, _ = clasificar_uscs(c)
    assert simbolo == "GW"


def test_uscs_grava_mal_graduada_GP():
    c = _curva(Cu=2, Cc=2, pct_grava=70, pct_arena=27, pct_finos=3)
    simbolo, _ = clasificar_uscs(c)
    assert simbolo == "GP"


def test_uscs_arena_bien_graduada_SW():
    c = _curva(Cu=7, Cc=1.5, pct_grava=10, pct_arena=87, pct_finos=3)
    simbolo, _ = clasificar_uscs(c)
    assert simbolo == "SW"


def test_uscs_limo_de_baja_plasticidad_ML():
    c = _curva(Cu=0, Cc=0, pct_grava=0, pct_arena=10, pct_finos=90)
    at = Atterberg(LL=30, LP=27)                      # PI = 3 < 4
    simbolo, _ = clasificar_uscs(c, at)
    assert simbolo == "ML"


def test_uscs_arcilla_de_baja_plasticidad_CL():
    c = _curva(Cu=0, Cc=0, pct_grava=0, pct_arena=10, pct_finos=90)
    at = Atterberg(LL=30, LP=15)                      # PI = 15
    # línea A en LL=30: 0.73*(30-20)=7.3; PI=15 >= 7.3 y >= 7 -> C
    simbolo, _ = clasificar_uscs(c, at)
    assert simbolo == "CL"


def test_uscs_arcilla_de_alta_plasticidad_CH():
    c = _curva(Cu=0, Cc=0, pct_grava=0, pct_arena=5, pct_finos=95)
    at = Atterberg(LL=60, LP=25)                      # PI = 35
    simbolo, _ = clasificar_uscs(c, at)
    assert simbolo == "CH"


def test_uscs_limo_de_alta_plasticidad_MH():
    c = _curva(Cu=0, Cc=0, pct_grava=0, pct_arena=5, pct_finos=95)
    at = Atterberg(LL=60, LP=50)                      # PI = 10, bajo línea A
    simbolo, _ = clasificar_uscs(c, at)
    assert simbolo == "MH"


def test_uscs_requiere_atterberg_si_finos_altos():
    c = _curva(Cu=0, Cc=0, pct_grava=0, pct_arena=10, pct_finos=90)
    with pytest.raises(ValueError, match="Atterberg"):
        clasificar_uscs(c, atterberg=None)


# ---------------------------------------------------------------------------
# Clasificación AASHTO: casos límite
# ---------------------------------------------------------------------------
def test_aashto_a1a_material_granular_limpio():
    abertura = np.array([ABERTURA_NO40, ABERTURA_NO10, 4.75])
    pasa = np.array([20.0, 40.0, 60.0])
    c = CurvaGranulometrica(abertura, pasa, 1000.0, 1.0, 2.0, 4.0,
                            5.0, 2.0, 40.0, 50.0, 10.0)
    at = Atterberg(LL=20, LP=16)                      # PI = 4
    r = clasificar_aashto(c, at)
    assert r.grupo == "A-1-a"


def test_aashto_a4_limo_arcilloso():
    abertura = np.array([ABERTURA_NO40, ABERTURA_NO10, 4.75])
    pasa = np.array([80.0, 95.0, 100.0])
    c = CurvaGranulometrica(abertura, pasa, 1000.0, 0.01, 0.02, 0.05,
                            5.0, 1.0, 0.0, 20.0, 80.0)
    at = Atterberg(LL=35, LP=27)                      # PI = 8
    r = clasificar_aashto(c, at)
    assert r.grupo == "A-4"


def test_aashto_a7_6_con_indice_de_grupo_positivo():
    abertura = np.array([ABERTURA_NO40, ABERTURA_NO10, 4.75])
    pasa = np.array([90.0, 97.0, 100.0])
    c = CurvaGranulometrica(abertura, pasa, 1000.0, 0.01, 0.02, 0.05,
                            5.0, 1.0, 0.0, 10.0, 90.0)
    at = Atterberg(LL=55, LP=25)                      # PI = 30
    r = clasificar_aashto(c, at)
    # PI=30 > LL-30=25 -> A-7-6
    assert r.grupo == "A-7-6"
    assert r.indice_grupo > 0                          # material pobre


# ---------------------------------------------------------------------------
# Validaciones de entrada
# ---------------------------------------------------------------------------
def test_error_menos_de_dos_tamices():
    with pytest.raises(ValueError, match="al menos 2 tamices"):
        calcular_curva([Tamiz("No.4", 4.75, 10)], 0)


def test_error_masa_negativa():
    with pytest.raises(ValueError, match="negativas"):
        calcular_curva([Tamiz("No.4", 4.75, -5), Tamiz("No.200", 0.075, 10)],
                       0)


def test_error_masa_total_cero():
    with pytest.raises(ValueError, match="mayor que cero"):
        calcular_curva([Tamiz("No.4", 4.75, 0), Tamiz("No.200", 0.075, 0)],
                       0)


def test_error_extrapolacion_fuera_de_rango():
    # Todo el material pasa el tamiz más grueso ensayado con %pasa=100,
    # y el mínimo %pasa medido es 70 -> pedir D60 es correcto, pero D80
    # (si se pidiera) estaría fuera de rango. Forzamos ese caso con muy
    # pocos finos ensayados.
    tamices = [Tamiz("No.4", 4.75, 0), Tamiz("No.10", 2.00, 300)]
    with pytest.raises(ValueError, match="fuera del rango"):
        calcular_curva(tamices, 0)                     # pide D10 -> fuera


def test_D_con_tamices_intermedios_sin_retenido():
    """Tamices con 0 g repiten el % que pasa (tramo plano). D30 debe salir
    del tramo donde la curva realmente cruza 30 %, no de un tramo ambiguo.

    pasa: 2.00 mm -> 32 %, 0.85 mm -> 32 % (No.20 sin retenido),
    0.425 mm -> 18 %. D30 está entre 0.85 (32 %) y 0.425 (18 %):
    log10 D = log10(0.85) + (32-30)/(32-18)·(log10(0.425)-log10(0.85))
    """
    import numpy as np
    from app.modelo import interpolar_diametro
    ab = np.array([0.075, 0.425, 0.85, 2.00, 4.75])
    pasa = np.array([8.0, 18.0, 32.0, 32.0, 45.0])
    esperado = 10 ** (np.log10(0.85) + (2 / 14) * (np.log10(0.425)
                                                   - np.log10(0.85)))
    assert interpolar_diametro(ab, pasa, 30.0) == pytest.approx(esperado)
    assert esperado == pytest.approx(0.7695, abs=1e-3)
    # objetivo exactamente en el tramo plano: devuelve el menor diámetro
    assert interpolar_diametro(ab, pasa, 32.0) == pytest.approx(0.85)
    # extremos
    assert interpolar_diametro(ab, pasa, 8.0) == pytest.approx(0.075)
    assert interpolar_diametro(ab, pasa, 45.0) == pytest.approx(4.75)
