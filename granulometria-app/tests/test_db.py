"""Pruebas del CRUD de la base de datos SQLite. Cada prueba usa un
archivo de base de datos nuevo y temporal (fixture ``tmp_path`` de
pytest), para no tocar la base de datos real de la aplicación."""
import pytest

from app.db import BaseDatos


@pytest.fixture
def bd(tmp_path):
    return BaseDatos(ruta=tmp_path / "test.db")


def test_crear_y_listar_proyecto(bd):
    pid = bd.crear_proyecto("Sondeo 1", "Vía El Dorado, km 3")
    proyectos = bd.listar_proyectos()
    assert len(proyectos) == 1
    assert proyectos[0].id == pid
    assert proyectos[0].nombre == "Sondeo 1"


def test_guardar_y_listar_calculo(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    entrada = {"tamices": [{"nombre": "No.4", "abertura_mm": 4.75,
                            "retenido_g": 0}], "LL": 25, "LP": 18}
    resultado = {"uscs_simbolo": "SP-SC", "Cu": 4.05}
    cid = bd.guardar_calculo(pid, "Muestra A", entrada, resultado)

    calculos = bd.listar_calculos(pid)
    assert len(calculos) == 1
    assert calculos[0].id == cid
    assert calculos[0].entrada == entrada
    assert calculos[0].resultado == resultado


def test_obtener_calculo_por_id(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    cid = bd.guardar_calculo(pid, "Muestra A", {"x": 1}, {"y": 2})
    c = bd.obtener_calculo(cid)
    assert c.nombre == "Muestra A"
    assert bd.obtener_calculo(cid + 999) is None


def test_listar_calculos_de_todos_los_proyectos(bd):
    p1 = bd.crear_proyecto("Sondeo 1")
    p2 = bd.crear_proyecto("Sondeo 2")
    bd.guardar_calculo(p1, "Muestra A", {}, {})
    bd.guardar_calculo(p2, "Muestra B", {}, {})
    assert len(bd.listar_calculos()) == 2
    assert len(bd.listar_calculos(proyecto_id=p1)) == 1


def test_buscar_proyecto_por_nombre_parcial(bd):
    bd.crear_proyecto("Sondeo Norte")
    bd.crear_proyecto("Sondeo Sur")
    bd.crear_proyecto("Relleno sanitario")
    encontrados = bd.listar_proyectos(filtro_nombre="Sondeo")
    assert {p.nombre for p in encontrados} == {"Sondeo Norte", "Sondeo Sur"}


def test_eliminar_calculo(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    cid = bd.guardar_calculo(pid, "Muestra A", {}, {})
    bd.eliminar_calculo(cid)
    assert bd.obtener_calculo(cid) is None


def test_eliminar_proyecto_elimina_calculos_en_cascada(bd):
    pid = bd.crear_proyecto("Sondeo 1")
    bd.guardar_calculo(pid, "Muestra A", {}, {})
    bd.guardar_calculo(pid, "Muestra B", {}, {})
    bd.eliminar_proyecto(pid)
    assert bd.listar_calculos(pid) == []


def test_tablas_se_crean_solas(tmp_path):
    """No debe lanzar error aunque el archivo de base de datos no exista
    todavía (CREATE TABLE IF NOT EXISTS)."""
    ruta = tmp_path / "nueva.db"
    assert not ruta.exists()
    bd = BaseDatos(ruta=ruta)
    assert ruta.exists()
    assert bd.listar_proyectos() == []
