"""Genera la memoria de cálculo en Word a partir de ``plantillas/memoria.docx``
usando docxtpl.
"""
from pathlib import Path
from tempfile import NamedTemporaryFile

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm

from .graficas import graficar_curva_granulometrica
from .modelo import formatear_opcional

RUTA_PLANTILLA = Path(__file__).resolve().parents[1] / "plantillas" / "memoria.docx"


def generar_memoria(resultado, proyecto, nombre_calculo, autor, fecha,
                    archivo_salida, tamices_entrada, peso_fondo_g,
                    verificacion=None):
    """Llena la plantilla de memoria de cálculo y la guarda en
    ``archivo_salida``.

    Args:
        resultado: :class:`app.modelo.ResultadoClasificacion`.
        proyecto: nombre del proyecto [str].
        nombre_calculo: nombre de este cálculo/muestra [str].
        autor: nombre de quien genera la memoria [str].
        fecha: fecha a mostrar [str], ya formateada.
        archivo_salida: ruta donde guardar el .docx resultante.
        tamices_entrada: lista de :class:`app.modelo.Tamiz` usados.
        peso_fondo_g: masa en el fondo [g].
        verificacion: :class:`app.especificaciones.VerificacionEspecificacion`
            opcional; agrega la sección "Verificación de la especificación"
            y sombrea la franja en la gráfica.

    Returns:
        ``archivo_salida`` (Path), para encadenar o enviarlo al usuario.
    """
    curva = resultado.curva
    doc = DocxTemplate(str(RUTA_PLANTILLA))

    # La gráfica se genera a un archivo temporal y se inserta como imagen
    # en línea (InlineImage exige un DocxTemplate ya creado).
    with NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        ruta_grafica = tmp.name
    graficar_curva_granulometrica(curva, titulo=f"Curva granulométrica — "
                                  f"{nombre_calculo}", archivo=ruta_grafica,
                                  especificacion=(verificacion.especificacion
                                                  if verificacion else None))
    imagen = InlineImage(doc, ruta_grafica, width=Cm(14))

    # % retenido acumulado por tamiz, para la tabla (ordenados como se
    # ingresaron, de mayor a menor abertura, como se acostumbra reportar).
    orden = sorted(tamices_entrada, key=lambda t: -t.abertura_mm)
    filas_tamices = []
    for t in orden:
        i = (curva.abertura_mm == t.abertura_mm).nonzero()[0]
        pct_pasa = float(curva.pasa[i[0]]) if len(i) else None
        filas_tamices.append({
            "nombre": t.nombre,
            "abertura_mm": f"{t.abertura_mm:g}",
            "retenido_g": f"{t.retenido_g:g}",
            "pct_retenido_acum": f"{100 - pct_pasa:.1f}" if pct_pasa is not None else "—",
            "pct_pasa": f"{pct_pasa:.1f}" if pct_pasa is not None else "—",
        })

    contexto = {
        "proyecto": proyecto,
        "nombre_calculo": nombre_calculo,
        "autor": autor,
        "fecha": fecha,
        "masa_total_g": f"{curva.masa_total_g:g}",
        "peso_fondo_g": f"{peso_fondo_g:g}",
        "tamices": filas_tamices,
        "grafica": imagen,
        "D10": formatear_opcional(curva.D10, 4),
        "D30": formatear_opcional(curva.D30, 4),
        "D60": formatear_opcional(curva.D60, 4),
        "Cu": formatear_opcional(curva.Cu, 2),
        "Cc": formatear_opcional(curva.Cc, 2),
        "pct_grava": f"{curva.pct_grava:.1f}",
        "pct_arena": f"{curva.pct_arena:.1f}",
        "pct_finos": f"{curva.pct_finos:.1f}",
        "uscs_simbolo": resultado.uscs_simbolo,
        "uscs_descripcion": resultado.uscs_descripcion,
        "tiene_atterberg": resultado.atterberg is not None,
    }
    if resultado.atterberg is not None:
        contexto["LL"] = f"{resultado.atterberg.LL:g}"
        contexto["LP"] = f"{resultado.atterberg.LP:g}"
        contexto["PI"] = f"{resultado.atterberg.PI:g}"
    if resultado.aashto is not None:
        contexto["aashto_grupo"] = resultado.aashto.grupo
        contexto["aashto_gi"] = resultado.aashto.indice_grupo
        contexto["aashto_descripcion"] = resultado.aashto.descripcion

    contexto["tiene_espec"] = verificacion is not None
    if verificacion is not None:
        e = verificacion.especificacion
        contexto.update({
            "espec_codigo": e.codigo,
            "espec_nombre": e.nombre,
            "espec_fuente": e.fuente,
            "filas_espec": [{
                "tamiz": f"{f.tamiz} ({f.abertura_mm:g} mm)",
                "pasa": "—" if f.origen == "sin dato" else f"{f.pasa:.1f}",
                "minimo": f"{f.minimo:g}", "maximo": f"{f.maximo:g}",
                "resultado": ("Sin dato" if f.origen == "sin dato" else
                              "Cumple" if f.cumple else "No cumple")
                             + (f" ({f.origen})" if f.origen in
                                ("interpolado", "100 %") else ""),
            } for f in verificacion.filas],
            "criterios_espec": [{"texto": t,
                                 "estado": "Cumple" if ok else "No cumple"}
                                for t, ok in verificacion.criterios],
            "espec_conclusion": (
                "La muestra CUMPLE la especificación." if verificacion.cumple
                else "La muestra NO CUMPLE la especificación."),
            "espec_nota": (
                "" if e.verificada else
                "Especificación definida por el usuario: no verificada "
                "contra una norma publicada."),
        })

    doc.render(contexto)
    archivo_salida = Path(archivo_salida)
    archivo_salida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(archivo_salida))
    return archivo_salida
