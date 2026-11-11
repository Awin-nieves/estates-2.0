"""Capa de servicio: conecta modelo + base de datos + memoria de cálculo.

La interfaz Flet llama a estas funciones en vez de hablar directamente con
``app.modelo``, ``app.db`` o ``app.reporte``, para no mezclar lógica de
negocio con widgets (criterio de arquitectura del proyecto).
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import especificaciones as _esp
from .modelo import Atterberg, Tamiz, procesar
from .reporte import generar_memoria as _generar_memoria_docx

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_MEMORIAS = RAIZ / "memorias"
# Especificaciones propias del usuario (opcional; ver README).
RUTA_ESPECIFICACIONES_PROPIAS = RAIZ / "especificaciones_propias.json"


def especificaciones_disponibles(ruta_json=None):
    """Dict ``{codigo: Especificacion}``: las incluidas más las propias del
    archivo ``especificaciones_propias.json`` si existe.

    Raises:
        ValueError: si el JSON propio tiene un formato inválido.
    """
    return _esp.todas_las_especificaciones(
        RUTA_ESPECIFICACIONES_PROPIAS if ruta_json is None else ruta_json)


def verificar_especificacion(resultado, codigo, ruta_json=None):
    """Verifica ``resultado.curva`` contra la especificación ``codigo``.

    Returns:
        :class:`app.especificaciones.VerificacionEspecificacion`.

    Raises:
        ValueError: si el código no existe.
    """
    todas = especificaciones_disponibles(ruta_json)
    if codigo not in todas:
        raise ValueError(f"Especificación desconocida: {codigo}")
    return _esp.verificar(resultado.curva, todas[codigo],
                          resultado.atterberg)


def construir_tamices(filas):
    """Convierte filas crudas de la interfaz (dicts con nombre, abertura_mm
    y retenido_g como texto) en una lista de :class:`Tamiz`, validando que
    las abertura/retenido sean numéricos y no negativos.

    Args:
        filas: lista de dicts con llaves ``nombre``, ``abertura_mm``,
            ``retenido_g`` (los dos últimos como str o número).

    Raises:
        ValueError: con un mensaje pensado para mostrar en la interfaz, si
            algún valor no es numérico o es negativo.
    """
    tamices = []
    for fila in filas:
        try:
            abertura = float(fila["abertura_mm"])
            retenido = float(fila["retenido_g"])
        except (TypeError, ValueError):
            raise ValueError(
                f"El tamiz {fila.get('nombre', '?')} tiene un valor no "
                "numérico.")
        if abertura <= 0:
            raise ValueError(f"El tamiz {fila['nombre']} debe tener una "
                             "abertura mayor que cero.")
        if retenido < 0:
            raise ValueError(f"El tamiz {fila['nombre']} tiene una masa "
                             "retenida negativa.")
        tamices.append(Tamiz(fila["nombre"], abertura, retenido))
    return tamices


def _resultado_a_dict(resultado):
    """Serializa un :class:`ResultadoClasificacion` a un dict JSON-able
    (para guardarlo en la base de datos; ver también :func:`_entrada_dict`).
    """
    curva = resultado.curva
    d = {
        "D10": curva.D10, "D30": curva.D30, "D60": curva.D60,
        "Cu": curva.Cu, "Cc": curva.Cc,
        "pct_grava": curva.pct_grava, "pct_arena": curva.pct_arena,
        "pct_finos": curva.pct_finos,
        "masa_total_g": curva.masa_total_g,
        "uscs_simbolo": resultado.uscs_simbolo,
        "uscs_descripcion": resultado.uscs_descripcion,
    }
    if resultado.aashto is not None:
        d["aashto_grupo"] = resultado.aashto.grupo
        d["aashto_gi"] = resultado.aashto.indice_grupo
        d["aashto_descripcion"] = resultado.aashto.descripcion
    return d


def _entrada_dict(tamices, peso_fondo_g, LL, LP, especificacion=None):
    return {
        "tamices": [asdict(t) for t in tamices],
        "peso_fondo_g": peso_fondo_g,
        "LL": LL,
        "LP": LP,
        "especificacion": especificacion,
    }


def calcular(filas_tamices, peso_fondo_g, LL=None, LP=None):
    """Valida, calcula y clasifica. No toca la base de datos.

    Returns:
        :class:`app.modelo.ResultadoClasificacion`.
    """
    tamices = construir_tamices(filas_tamices)
    return procesar(tamices, peso_fondo_g, LL, LP)


def calcular_y_guardar(bd, proyecto_id, nombre_calculo, filas_tamices,
                       peso_fondo_g, LL=None, LP=None, especificacion=None):
    """Calcula y guarda el cálculo bajo un proyecto existente.

    Si se da ``especificacion`` (código), se guarda también el código y si
    la muestra cumple o no.

    Returns:
        Tupla ``(resultado, calculo_id)``.
    """
    tamices = construir_tamices(filas_tamices)
    resultado = procesar(tamices, peso_fondo_g, LL, LP)
    entrada = _entrada_dict(tamices, peso_fondo_g, LL, LP, especificacion)
    resumen = _resultado_a_dict(resultado)
    if especificacion:
        v = verificar_especificacion(resultado, especificacion)
        resumen["especificacion"] = especificacion
        resumen["cumple_especificacion"] = bool(v.cumple)
    calculo_id = bd.guardar_calculo(proyecto_id, nombre_calculo, entrada,
                                    resumen)
    return resultado, calculo_id


def recalcular_desde_historial(calculo):
    """Reconstruye un :class:`ResultadoClasificacion` a partir de un
    :class:`app.db.Calculo` guardado, recalculando con el modelo actual
    (no confía en los valores ya guardados, por si el modelo cambió).
    """
    entrada = calculo.entrada
    tamices = [Tamiz(t["nombre"], t["abertura_mm"], t["retenido_g"])
              for t in entrada["tamices"]]
    return procesar(tamices, entrada["peso_fondo_g"], entrada.get("LL"),
                    entrada.get("LP"))


def generar_memoria(resultado, proyecto_nombre, nombre_calculo, autor,
                    tamices_entrada, peso_fondo_g, verificacion=None):
    """Genera la memoria de cálculo en ``memorias/`` y devuelve su ruta.
    ``verificacion`` (opcional) agrega la sección de especificación."""
    CARPETA_MEMORIAS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"memoria_{nombre_calculo}_{marca}.docx".replace(" ", "_")
    archivo_salida = CARPETA_MEMORIAS / nombre_archivo
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return _generar_memoria_docx(
        resultado, proyecto=proyecto_nombre, nombre_calculo=nombre_calculo,
        autor=autor, fecha=fecha, archivo_salida=archivo_salida,
        tamices_entrada=tamices_entrada, peso_fondo_g=peso_fondo_g,
        verificacion=verificacion)
