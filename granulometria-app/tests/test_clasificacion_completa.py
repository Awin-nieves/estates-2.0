"""Pruebas de punta a punta: datos crudos de tamizado -> ``procesar``.

Las pruebas de ``test_modelo.py`` arman curvas "a mano" para probar la
clasificación por separado; estas, en cambio, recorren todo el camino
(``calcular_curva`` incluido), que es lo que hace la aplicación. Cubren los
suelos con muchos finos, donde D10 (y a veces D30) no existen en la curva.

Datos (1000 g en total). Cada juego fija el % que pasa por tamiz:

    GRUESO_30 (30 % finos): % que pasa No.4: 90, No.10: 75, No.40: 45,
        No.200: 30. Retenidos 100, 150, 300 y 150 g; 300 g en el fondo.
    FINO_60 (60 % finos): % que pasa No.4: 95, No.10: 90, No.40: 70,
        No.200: 60. Retenidos 50, 50, 200 y 100 g; 600 g en el fondo.
"""
import pytest

from app.modelo import Tamiz, formatear_opcional, procesar


def _tamices(retenidos):
    nombres = [("No.4", 4.75), ("No.10", 2.00), ("No.40", 0.425),
               ("No.200", 0.075)]
    return [Tamiz(n, a, r) for (n, a), r in zip(nombres, retenidos)]


# pasa: No.4 90, No.10 75, No.40 45, No.200 30 -> 30 % finos, 10 % grava
GRUESO_30 = (_tamices([100, 150, 300, 150]), 300.0)
# pasa: No.4 95, No.10 90, No.40 70, No.200 60 -> 60 % finos
FINO_60 = (_tamices([50, 50, 200, 100]), 600.0)


def test_curvas_de_referencia_tienen_los_pasa_esperados():
    from app.modelo import calcular_curva
    for (tamices, fondo), esperado in [
            (GRUESO_30, [90, 75, 45, 30]), (FINO_60, [95, 90, 70, 60])]:
        c = calcular_curva(tamices, fondo)
        # la curva va de menor a mayor abertura: 0.075, 0.425, 2.00, 4.75
        assert list(c.pasa) == pytest.approx(esperado[::-1])


# (datos, LL, LP) -> (USCS, AASHTO, GI)
@pytest.mark.parametrize("datos, LL, LP, uscs, aashto, gi", [
    # 30 % finos, arena (60 % arena vs 10 % grava)
    # LL=30, PI=4: bajo la línea A (0.73·(30-20)=7.3) -> limo -> SM
    (GRUESO_30, 30, 26, "SM", "A-2-4", 0),
    # LL=30, PI=12: sobre la línea A y PI > 7 -> arcilla -> SC;
    # A-2-6, GI = 0.01·(30-15)·(12-10) = 0.3 -> 0
    (GRUESO_30, 30, 18, "SC", "A-2-6", 0),
    # 60 % finos. LL=35, PI=5: bajo la línea A (10.95) -> ML.
    # A-4, GI = 0.2·25 = 5
    (FINO_60, 35, 30, "ML", "A-4", 5),
    # LL=35, PI=15: sobre la línea A -> CL. A-6,
    # GI = 0.2·25 + 0.01·40·5 = 7
    (FINO_60, 35, 20, "CL", "A-6", 7),
    # LL=60, PI=35: sobre la línea A (29.2) y LL >= 50 -> CH.
    # PI 35 > LL-30 = 30 -> A-7-6. GI = 5 + 0.005·25·20 + 0.01·40·20 = 15.5
    (FINO_60, 60, 25, "CH", "A-7-6", 16),
    # LL=60, PI=20: bajo la línea A (29.2) -> MH.
    # PI 20 <= 30 -> A-7-5. GI = 5 + 2.5 + 0.01·40·10 = 11.5
    (FINO_60, 60, 40, "MH", "A-7-5", 12),
])
def test_clasificacion_completa_con_finos(datos, LL, LP, uscs, aashto, gi):
    tamices, fondo = datos
    r = procesar(tamices, fondo, LL=LL, LP=LP)     # antes: ValueError (D10)
    assert r.uscs_simbolo == uscs
    assert r.aashto.grupo == aashto
    assert r.aashto.indice_grupo == gi


def test_con_finos_D10_Cu_Cc_no_aplican():
    tamices, fondo = FINO_60
    c = procesar(tamices, fondo, LL=35, LP=20).curva
    assert c.pct_finos == pytest.approx(60)
    assert c.D10 is None and c.D30 is None      # pasa mínimo = 60 %
    assert c.Cu is None and c.Cc is None
    assert c.D60 == pytest.approx(0.075)        # 60 % = pasa del No.200
    assert formatear_opcional(c.D10) == "no aplica"
    assert formatear_opcional(c.D60, 4, " mm") == "0.0750 mm"


def test_con_30_pct_finos_D10_no_aplica_pero_D60_si():
    tamices, fondo = GRUESO_30
    c = procesar(tamices, fondo, LL=30, LP=26).curva
    assert c.D10 is None and c.Cu is None and c.Cc is None
    assert c.D60 is not None and c.D30 == pytest.approx(0.075)


def test_grueso_limpio_sigue_calculando_Cu_y_Cc():
    """Sin regresión: con pocos finos D10, Cu y Cc se siguen calculando."""
    tamices = _tamices([0, 50, 300, 600])
    # pasa: No.4 100, No.10 95, No.40 65, No.200 5 -> fondo 50 g
    r = procesar(tamices, 50.0, LL=20, LP=20)
    c = r.curva
    assert c.D10 is not None and c.Cu is not None and c.Cc is not None
    assert r.uscs_simbolo.startswith("S")


def test_uscs_entre_10_y_12_pct_finos_sin_D10_da_error_claro():
    """Con 11 % de finos USCS necesita Cu/Cc; si D10 cae bajo el tamiz más
    fino, debe decirlo (no devolver una clasificación inventada)."""
    tamices = _tamices([0, 100, 400, 390])      # pasa No.200 = 110/1000 = 11 %
    with pytest.raises(ValueError, match="Cu y Cc"):
        procesar(tamices, 110.0, LL=30, LP=20)


# --- AASHTO con decimales (límites LL > 40 e IP > 10) --------------------
@pytest.mark.parametrize("datos, LL, LP, aashto", [
    # LL=30, IP=10.5 -> A-2-6 (antes A-2-7)
    (GRUESO_30, 30, 19.5, "A-2-6"),
    # LL=40.5, IP=4.5 con 60 % finos -> A-5 (antes A-7-5)
    (FINO_60, 40.5, 36, "A-5"),
    # LL=35, IP=10.5 con 60 % finos -> A-6 (antes A-7-6)
    (FINO_60, 35, 24.5, "A-6"),
    # LL=40.5, IP=10.5, 30 % finos -> A-2-7
    (GRUESO_30, 40.5, 30, "A-2-7"),
    # LL=40.5, IP=10.5, 60 % finos -> A-7-5 (IP = LL-30)
    (FINO_60, 40.5, 30, "A-7-5"),
    # los enteros de siempre no cambian: LL=40/IP=10 -> A-4 y A-2-4
    (FINO_60, 40, 30, "A-4"),
    (GRUESO_30, 40, 30, "A-2-4"),
])
def test_aashto_con_decimales(datos, LL, LP, aashto):
    tamices, fondo = datos
    assert procesar(tamices, fondo, LL=LL, LP=LP).aashto.grupo == aashto


# --- Servicio, historial y memoria Word con "no aplica" -------------------
FILAS_FINO_60 = [
    {"nombre": "No.4", "abertura_mm": 4.75, "retenido_g": "50"},
    {"nombre": "No.10", "abertura_mm": 2.00, "retenido_g": "50"},
    {"nombre": "No.40", "abertura_mm": 0.425, "retenido_g": "200"},
    {"nombre": "No.200", "abertura_mm": 0.075, "retenido_g": "100"},
]


def test_servicio_calcula_guarda_y_recalcula_suelo_fino(tmp_path):
    from app import servicio
    from app.db import BaseDatos
    bd = BaseDatos(tmp_path / "t.db")
    pid = bd.crear_proyecto("Vía Usme")
    resultado, cid = servicio.calcular_y_guardar(
        bd, pid, "Arcilla K2", FILAS_FINO_60, 600.0, LL=35, LP=20)
    assert resultado.uscs_simbolo == "CL"
    guardado = bd.obtener_calculo(cid)
    # None se guarda como null y vuelve como None
    assert guardado.resultado["D10"] is None
    assert guardado.resultado["Cu"] is None
    assert guardado.resultado["D60"] == pytest.approx(0.075)
    rec = servicio.recalcular_desde_historial(guardado)
    assert rec.uscs_simbolo == "CL" and rec.aashto.grupo == "A-6"


def test_memoria_word_de_suelo_fino_dice_no_aplica(tmp_path):
    from docx import Document
    from app import servicio
    resultado = servicio.calcular(FILAS_FINO_60, 600.0, LL=35, LP=20)
    tam = servicio.construir_tamices(FILAS_FINO_60)
    from app.reporte import generar_memoria
    ruta = generar_memoria(resultado, "Vía Usme", "Arcilla K2", "Est.",
                           "2026-11-13", tmp_path / "m.docx", tam, 600.0)
    doc = Document(str(ruta))
    texto = "\n".join(p.text for p in doc.paragraphs)
    celdas = "\n".join(c.text for t in doc.tables for r in t.rows
                       for c in r.cells)
    assert "no aplica" in texto + celdas
    assert "CL" in texto and "A-6" in texto
    assert "{{" not in texto and "None" not in texto + celdas


def test_grafica_sin_D10_ni_D30_no_falla(tmp_path):
    from app.graficas import graficar_curva_granulometrica
    tamices, fondo = FINO_60
    c = procesar(tamices, fondo, LL=35, LP=20).curva
    archivo = tmp_path / "g.png"
    graficar_curva_granulometrica(c, archivo=str(archivo))
    assert archivo.stat().st_size > 1000
