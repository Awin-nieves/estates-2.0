"""Pruebas de la capa de servicio: construcción de tamices desde texto,
cálculo + guardado en base de datos, y recálculo a partir del historial
(debe reproducir exactamente la misma clasificación)."""
import pytest

from app.db import BaseDatos
from app.servicio import (calcular_y_guardar, construir_tamices,
                          generar_memoria, recalcular_desde_historial)

FILAS = [
    {"nombre": "No.4", "abertura_mm": "4.75", "retenido_g": "0"},
    {"nombre": "No.10", "abertura_mm": "2.00", "retenido_g": "25"},
    {"nombre": "No.20", "abertura_mm": "0.850", "retenido_g": "50"},
    {"nombre": "No.40", "abertura_mm": "0.425", "retenido_g": "100"},
    {"nombre": "No.60", "abertura_mm": "0.250", "retenido_g": "125"},
    {"nombre": "No.100", "abertura_mm": "0.150", "retenido_g": "100"},
    {"nombre": "No.200", "abertura_mm": "0.075", "retenido_g": "75"},
]


@pytest.fixture
def bd(tmp_path):
    return BaseDatos(ruta=tmp_path / "test.db")


def test_construir_tamices_valida_numeros():
    tamices = construir_tamices(FILAS)
    assert len(tamices) == 7
    assert tamices[0].nombre == "No.4"
    assert tamices[0].abertura_mm == pytest.approx(4.75)


def test_construir_tamices_rechaza_texto_no_numerico():
    filas = [{"nombre": "No.4", "abertura_mm": "abc", "retenido_g": "0"}]
    with pytest.raises(ValueError, match="valor no numérico"):
        construir_tamices(filas)


def test_construir_tamices_rechaza_retenido_negativo():
    filas = [{"nombre": "No.4", "abertura_mm": "4.75", "retenido_g": "-5"}]
    with pytest.raises(ValueError, match="negativa"):
        construir_tamices(filas)


def test_calcular_y_guardar(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    resultado, cid = calcular_y_guardar(bd, pid, "Muestra A", FILAS, 25.0,
                                        LL=25, LP=18)
    assert resultado.uscs_simbolo == "SP-SC"
    guardado = bd.obtener_calculo(cid)
    assert guardado.nombre == "Muestra A"
    assert guardado.resultado["uscs_simbolo"] == "SP-SC"


def test_recalcular_desde_historial_reproduce_la_clasificacion(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    resultado_original, cid = calcular_y_guardar(
        bd, pid, "Muestra A", FILAS, 25.0, LL=25, LP=18)

    guardado = bd.obtener_calculo(cid)
    resultado_recalculado = recalcular_desde_historial(guardado)

    assert resultado_recalculado.uscs_simbolo == resultado_original.uscs_simbolo
    assert resultado_recalculado.curva.Cu == pytest.approx(
        resultado_original.curva.Cu)
    assert resultado_recalculado.aashto.grupo == resultado_original.aashto.grupo


def test_generar_memoria_desde_servicio(bd, tmp_path, monkeypatch):
    import app.servicio as servicio
    monkeypatch.setattr(servicio, "CARPETA_MEMORIAS", tmp_path / "memorias")

    pid = bd.crear_proyecto("Sondeo 1")
    resultado, _ = calcular_y_guardar(bd, pid, "Muestra A", FILAS, 25.0,
                                      LL=25, LP=18)
    from app.servicio import construir_tamices as ct
    ruta = generar_memoria(resultado, "Sondeo 1", "Muestra A", "Awin",
                           ct(FILAS), 25.0)
    assert ruta.exists()
    assert ruta.suffix == ".docx"


def test_guardar_con_especificacion_y_recuperar(tmp_path):
    from app.db import BaseDatos
    from app import servicio
    bd = BaseDatos(tmp_path / "t.db")
    pid = bd.crear_proyecto("Vía X")
    # Dataset con % pasa exacto (ver test_especificaciones.py)
    filas = [{"nombre": n, "abertura_mm": a, "retenido_g": r} for n, a, r in [
        ("1 1/2\"", 37.5, 0), ("1\"", 25.0, 150), ("1/2\"", 12.5, 150),
        ("3/8\"", 9.5, 100), ("No.4", 4.75, 150), ("No.10", 2.00, 130),
        ("No.40", 0.425, 140), ("No.200", 0.075, 100)]]
    resultado, cid = servicio.calcular_y_guardar(
        bd, pid, "M1", filas, 80.0, LL=24, LP=19, especificacion="SBG-38")
    guardado = bd.obtener_calculo(cid)
    assert guardado.entrada["especificacion"] == "SBG-38"
    assert guardado.resultado["cumple_especificacion"] is True
    # al reabrir desde el historial se vuelve a verificar con el modelo actual
    rec = servicio.recalcular_desde_historial(guardado)
    ver = servicio.verificar_especificacion(rec, "SBG-38")
    assert ver.cumple


def test_verificar_especificacion_desconocida():
    import pytest
    from app import servicio
    from app.modelo import procesar
    from tests.test_modelo import FONDO_REF, TAMICES_REF
    res = procesar(TAMICES_REF, FONDO_REF, LL=25, LP=18)
    with pytest.raises(ValueError, match="desconocida"):
        servicio.verificar_especificacion(res, "XYZ")
