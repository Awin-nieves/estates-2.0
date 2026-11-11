"""Pruebas de la verificación contra especificaciones.

Dataset de referencia (1000 g en total) diseñado para tener % que pasa
exactos:  37.5 mm:100, 25.0:85, 12.5:70, 9.5:60, 4.75:45, 2.00:32,
0.425:18, 0.075:8  (retenidos 0,150,150,100,150,130,140,100 g y 80 g en el
fondo; cada retenido acumulado se resta de 1000 g).
"""
import json
from dataclasses import replace

import numpy as np
import pytest

from app.especificaciones import (ESPECIFICACIONES, Especificacion,
                                  cargar_especificaciones_json,
                                  todas_las_especificaciones, verificar)
from app.modelo import Atterberg, Tamiz, calcular_curva

RETENIDOS = [("1 1/2\"", 37.5, 0), ("1\"", 25.0, 150), ("1/2\"", 12.5, 150),
             ("3/8\"", 9.5, 100), ("No.4", 4.75, 150), ("No.10", 2.00, 130),
             ("No.40", 0.425, 140), ("No.200", 0.075, 100)]


@pytest.fixture
def curva():
    tamices = [Tamiz(n, a, r) for n, a, r in RETENIDOS]
    return calcular_curva(tamices, peso_fondo_g=80.0)


def test_dataset_de_referencia(curva):
    esperado = {37.5: 100, 25.0: 85, 12.5: 70, 9.5: 60, 4.75: 45,
                2.00: 32, 0.425: 18, 0.075: 8}
    for ab, p in esperado.items():
        i = int(np.where(np.isclose(curva.abertura_mm, ab))[0][0])
        assert curva.pasa[i] == pytest.approx(p)


def test_subbase_sbg38_cumple(curva):
    v = verificar(curva, "SBG-38", Atterberg(LL=24, LP=19))   # IP = 5
    assert v.cumple
    assert all(f.origen == "medido" for f in v.filas)
    assert len(v.filas) == 8
    assert all(ok for _, ok in v.criterios)       # LL 24 <= 25, IP 5 <= 6


def test_subbase_incumple_por_plasticidad(curva):
    v = verificar(curva, "SBG-38", Atterberg(LL=30, LP=20))   # LL 30 > 25
    assert all(f.cumple for f in v.filas)          # la granulometría sí
    assert not v.cumple                            # pero LL falla
    assert [ok for _, ok in v.criterios] == [False, False]  # LL e IP (10>6)


def test_sin_atterberg_no_se_puede_demostrar_plasticidad(curva):
    v = verificar(curva, "SBG-38")
    assert not v.cumple
    assert all("sin datos" in t for t, _ in v.criterios)


def test_incumple_por_tamiz(curva):
    # SBG-50 pide 70-95 en 37.5 mm: la muestra pasa 100 -> no cumple.
    v = verificar(curva, "SBG-50", Atterberg(LL=20, LP=16))
    fila = next(f for f in v.filas if f.abertura_mm == 37.5)
    assert fila.pasa == pytest.approx(100)
    assert not fila.cumple and not v.cumple
    # el tamiz de 50 mm no se ensayó y es mayor que el mayor: se asume 100 %
    f50 = next(f for f in v.filas if f.abertura_mm == 50.0)
    assert f50.origen == "100 %" and f50.cumple


def test_base_bg38_cumple_con_relacion_200_40(curva):
    v = verificar(curva, "BG-38")
    # 19.0 mm no se ensayó -> se interpola entre 25.0 (85) y 12.5 (70)
    f19 = next(f for f in v.filas if f.abertura_mm == 19.0)
    assert f19.origen == "interpolado"
    # semilog: 70 + 15*(log19-log12.5)/(log25-log12.5) = 79.06
    esperado = 70 + 15 * (np.log10(19) - np.log10(12.5)) / (
        np.log10(25) - np.log10(12.5))
    assert f19.pasa == pytest.approx(esperado)
    assert f19.pasa == pytest.approx(79.06, abs=0.01)
    assert v.cumple
    texto, ok = v.criterios[0]
    assert ok and "0.444" in texto          # 8 / 18


def test_base_incumple_relacion_200_40():
    # 1000 g: pasa 25 mm:100, 4.75:40, 0.425:14, 0.075:10 (fondo 100 g)
    # => relación No.200/No.40 = 10/14 = 0.714 > 2/3
    tamices = [Tamiz("1\"", 25.0, 0), Tamiz("No.4", 4.75, 600),
               Tamiz("No.40", 0.425, 260), Tamiz("No.200", 0.075, 40)]
    curva = calcular_curva(tamices, peso_fondo_g=100.0)
    v = verificar(curva, ESPECIFICACIONES["BG-25"])
    texto, ok = v.criterios[0]
    assert not ok and "0.714" in texto
    assert not v.cumple


def test_tamiz_sin_dato_no_cuenta_como_incumplimiento(curva):
    # Curva truncada (sin el tamiz No.200): la franja pide 0.075 mm, que
    # queda por debajo del tamiz más fino ensayado -> "sin dato".
    corta = replace(curva, abertura_mm=curva.abertura_mm[1:],
                    pasa=curva.pasa[1:])
    v = verificar(corta, "TUB-SELECCIONADO")
    f200 = next(f for f in v.filas if f.abertura_mm == 0.075)
    assert f200.origen == "sin dato" and np.isnan(f200.pasa)
    assert v.sin_dato == [f200]
    assert v.cumple          # 37.5 mm: pasa 100 %; el 0.075 no se evalúa


def test_tuberias_grava_tamano_maximo(curva):
    # 19 mm se interpola a 79 % -> no cumple "100 % pasa 3/4\""
    assert not verificar(curva, "TUB-GRAVA").cumple


def test_especificacion_desconocida(curva):
    with pytest.raises(ValueError, match="desconocida"):
        verificar(curva, "NO-EXISTE")


def test_las_franjas_incluidas_son_coherentes():
    """min <= max, y los porcentajes decrecen con la abertura (una franja
    no puede pedir más material pasando por un tamiz más fino)."""
    for e in ESPECIFICACIONES.values():
        abs_ = sorted(e.franja, reverse=True)
        for ab in abs_:
            mn, mx = e.franja[ab]
            assert 0 <= mn <= mx <= 100, (e.codigo, ab)
        for grande, chico in zip(abs_, abs_[1:]):
            assert e.franja[grande][0] >= e.franja[chico][0], (e.codigo,
                                                              grande)
            assert e.franja[grande][1] >= e.franja[chico][1], (e.codigo,
                                                              grande)


def test_json_propio(tmp_path):
    ruta = tmp_path / "propias.json"
    ruta.write_text(json.dumps([{
        "codigo": "MI-ESPEC", "nombre": "Mi material", "fuente": "Pliego X",
        "franja": {"25.0": [100, 100], "4.75": [35, 65]}, "LL_max": 30}]),
        encoding="utf-8")
    cargadas = cargar_especificaciones_json(ruta)
    e = cargadas["MI-ESPEC"]
    assert isinstance(e, Especificacion) and not e.verificada
    assert e.franja == {25.0: (100.0, 100.0), 4.75: (35.0, 65.0)}
    assert e.LL_max == 30 and e.IP_max is None
    todas = todas_las_especificaciones(ruta)
    assert "MI-ESPEC" in todas and "SBG-38" in todas


@pytest.mark.parametrize("contenido, mensaje", [
    ("no es json", "No se pudo leer"),
    ('{"a": 1}', "lista"),
    ('[{"codigo": "X", "franja": {"25": [90, 80]}}]', "inválida"),
    ('[{"codigo": "X", "franja": {}}]', "vacía"),
    ('[{"franja": {"25": [0, 100]}}]', "inválida"),
])
def test_json_invalido(tmp_path, contenido, mensaje):
    ruta = tmp_path / "x.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ValueError, match=mensaje):
        cargar_especificaciones_json(ruta)
