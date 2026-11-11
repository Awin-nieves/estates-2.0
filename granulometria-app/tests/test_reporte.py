"""Prueba de humo de la generación de la memoria de cálculo: que el
.docx se genere, con la tabla de tamices completa y la gráfica embebida."""
import zipfile

from docx import Document

from app.modelo import procesar
from app.reporte import generar_memoria
from tests.test_modelo import FONDO_REF, TAMICES_REF


def test_generar_memoria_completa(tmp_path):
    resultado = procesar(TAMICES_REF, FONDO_REF, LL=25, LP=18)
    salida = tmp_path / "memoria.docx"

    ruta = generar_memoria(resultado, proyecto="Sondeo 1",
                           nombre_calculo="Muestra A", autor="Awin",
                           fecha="2026-11-07", archivo_salida=salida,
                           tamices_entrada=TAMICES_REF,
                           peso_fondo_g=FONDO_REF)

    assert ruta.exists()

    doc = Document(str(ruta))
    tablas = doc.tables
    tabla_tamices = next(t for t in tablas
                         if t.rows[0].cells[0].text == "Tamiz")
    # encabezado + 7 tamices = 8 filas (sin filas marcadoras sobrantes)
    assert len(tabla_tamices.rows) == 1 + len(TAMICES_REF)
    assert tabla_tamices.rows[1].cells[0].text == "No.4"

    texto_completo = "\n".join(p.text for p in doc.paragraphs)
    assert "SP-SC" in texto_completo
    assert "A-2-4" in texto_completo

    with zipfile.ZipFile(ruta) as z:
        assert any("media" in n for n in z.namelist())  # gráfica embebida


def _tabla_verificacion(doc):
    return next(t for t in doc.tables
                if t.rows[0].cells[0].text == "Tamiz"
                and t.rows[0].cells[1].text == "% que pasa")


def test_memoria_sin_especificacion_no_trae_la_seccion(tmp_path):
    resultado = procesar(TAMICES_REF, FONDO_REF, LL=25, LP=18)
    ruta = generar_memoria(resultado, "P", "M", "A", "2026-11-07",
                           tmp_path / "m.docx", TAMICES_REF, FONDO_REF)
    doc = Document(str(ruta))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "Verificación de la especificación" not in texto
    assert "{%" not in texto and "{{" not in texto
    assert "7. Observaciones" in texto
    assert not any(t.rows[0].cells[1].text == "% que pasa"
                   for t in doc.tables)


def test_memoria_con_especificacion(tmp_path):
    from app.especificaciones import verificar
    resultado = procesar(TAMICES_REF, FONDO_REF, LL=25, LP=18)
    ver = verificar(resultado.curva, "BG-25", resultado.atterberg)
    ruta = generar_memoria(resultado, "P", "M", "A", "2026-11-07",
                           tmp_path / "m.docx", TAMICES_REF, FONDO_REF,
                           verificacion=ver)
    doc = Document(str(ruta))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "6. Verificación de la especificación" in texto
    assert "BG-25" in texto and "INVIAS 2013, Art. 330" in texto
    assert "{%" not in texto and "{{" not in texto
    # 7 tamices en la franja BG-25 (25, 19, 9.5, 4.75, 2.00, 0.425, 0.075)
    tabla = _tabla_verificacion(doc)
    assert len(tabla.rows) == 1 + 7
    # la muestra pasa 100 % por 9.5 mm (franja 50-80) -> no cumple
    fila_95 = next(r for r in tabla.rows if "9.5 mm" in r.cells[0].text)
    assert "No cumple" in fila_95.cells[4].text
    assert "NO CUMPLE" in texto
    assert "Relación No.200 / No.40" in texto
