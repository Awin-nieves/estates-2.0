"""Verificación de la granulometría contra especificaciones (husos).

Cada especificación define una *franja granulométrica*: para ciertos
tamices, el % que pasa mínimo y máximo. La curva ensayada cumple si en cada
tamiz de la franja su % que pasa queda dentro de [mínimo, máximo]. Además
una especificación puede exigir límites de plasticidad (LL, IP), un máximo
de finos o la relación entre los tamices No.200 y No.40.

Fuentes incluidas (``verificada=True``): INVIAS, Especificaciones Generales
de Construcción de Carreteras 2013 — Art. 320 (subbase granular, Tabla
320-3 y 320-2) y Art. 330 (base granular, Tabla 330-3); y criterios de
cimentación de tuberías de la norma EMCALI NDC-SE-AA-012.

IMPORTANTE: los valores deben contrastarse con la edición vigente de la
norma que rija el contrato (INVIAS actualiza sus artículos y cada empresa de
acueducto tiene su propia norma). Para otros materiales (afirmado, mezclas
asfálticas, concreto, normas de otra empresa) se pueden cargar
especificaciones propias desde un archivo JSON con
:func:`cargar_especificaciones_json` (ver ``ejemplos/especificaciones_propias.json``).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .modelo import ABERTURA_NO40, ABERTURA_NO200, TAMICES_ASTM

TOLERANCIA = 1e-9


@dataclass
class Especificacion:
    """Una especificación granulométrica.

    Atributos:
        codigo: identificador corto (p. ej. "SBG-38").
        nombre: descripción.
        fuente: norma de origen.
        franja: dict ``{abertura_mm: (minimo, maximo)}`` de % que pasa.
        LL_max, IP_max: límites de plasticidad máximos [%] (opcionales).
        relacion_200_40_max: máximo de (% pasa No.200)/(% pasa No.40).
        verificada: True si los valores se contrastaron con la norma
            publicada; False para especificaciones cargadas por el usuario.
    """
    codigo: str
    nombre: str
    fuente: str
    franja: dict
    LL_max: float = None
    IP_max: float = None
    relacion_200_40_max: float = None
    verificada: bool = True


def _nombre_tamiz(abertura_mm):
    """Nombre ASTM del tamiz de una abertura (o la abertura en mm)."""
    for nombre, ab in TAMICES_ASTM.items():
        if np.isclose(ab, abertura_mm):
            return nombre
    return f"{abertura_mm:g} mm"


# ---------------------------------------------------------------------------
# Especificaciones incluidas
# ---------------------------------------------------------------------------
_F_SBG = "INVIAS 2013, Art. 320 (Tablas 320-2 y 320-3)"
_F_BG = "INVIAS 2013, Art. 330 (Tabla 330-3)"
_F_TUB = "EMCALI NDC-SE-AA-012 (num. 6.4.2 y 6.4.5)"

ESPECIFICACIONES = {
    e.codigo: e for e in [
        Especificacion(
            "SBG-50", "Subbase granular, franja SBG-50", _F_SBG,
            {50.0: (100, 100), 37.5: (70, 95), 25.0: (60, 90),
             12.5: (45, 75), 9.5: (40, 70), 4.75: (25, 55),
             2.00: (15, 40), 0.425: (6, 25), 0.075: (2, 15)},
            LL_max=25, IP_max=6),
        Especificacion(
            "SBG-38", "Subbase granular, franja SBG-38", _F_SBG,
            {37.5: (100, 100), 25.0: (75, 95), 12.5: (55, 85),
             9.5: (45, 75), 4.75: (30, 60), 2.00: (20, 45),
             0.425: (8, 30), 0.075: (2, 15)},
            LL_max=25, IP_max=6),
        Especificacion(
            "BG-40", "Base granular, franja BG-40 (gruesa)", _F_BG,
            {37.5: (100, 100), 25.0: (75, 100), 19.0: (65, 90),
             9.5: (45, 68), 4.75: (30, 50), 2.00: (15, 32),
             0.425: (7, 20), 0.075: (0, 9)},
            relacion_200_40_max=2 / 3),
        Especificacion(
            "BG-27", "Base granular, franja BG-27 (gruesa)", _F_BG,
            {25.0: (100, 100), 19.0: (75, 100), 9.5: (52, 78),
             4.75: (35, 59), 2.00: (20, 40), 0.425: (8, 22),
             0.075: (0, 9)},
            relacion_200_40_max=2 / 3),
        Especificacion(
            "BG-38", "Base granular, franja BG-38 (fina)", _F_BG,
            {37.5: (100, 100), 25.0: (70, 100), 19.0: (60, 90),
             9.5: (45, 75), 4.75: (30, 60), 2.00: (20, 45),
             0.425: (10, 30), 0.075: (5, 15)},
            relacion_200_40_max=2 / 3),
        Especificacion(
            "BG-25", "Base granular, franja BG-25 (fina)", _F_BG,
            {25.0: (100, 100), 19.0: (70, 100), 9.5: (50, 80),
             4.75: (35, 65), 2.00: (20, 45), 0.425: (10, 30),
             0.075: (5, 15)},
            relacion_200_40_max=2 / 3),
        Especificacion(
            "TUB-GRAVA", "Cimentación de tuberías: grava (tamaño máx. 3/4\")",
            _F_TUB, {19.0: (100, 100)}),
        Especificacion(
            "TUB-SELECCIONADO",
            "Cimentación de tuberías: material importado seleccionado "
            "(tamaño máx. 1 1/2\", finos < 35 %)", _F_TUB,
            {37.5: (100, 100), 0.075: (0, 35)}),
    ]
}


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------
@dataclass
class FilaVerificacion:
    """Resultado en un tamiz de la franja.

    ``origen``: "medido" (el tamiz se ensayó), "interpolado" (entre dos
    tamices ensayados), "100 %" (la abertura es mayor que el tamiz más
    grande ensayado: se asume que todo pasa) o "sin dato" (menor que el
    tamiz más fino ensayado; no se evalúa).
    """
    abertura_mm: float
    tamiz: str
    pasa: float
    minimo: float
    maximo: float
    origen: str
    cumple: bool


@dataclass
class VerificacionEspecificacion:
    especificacion: Especificacion
    filas: list
    criterios: list = field(default_factory=list)  # (texto, cumple)

    @property
    def cumple(self):
        """True si todos los tamices evaluados y criterios cumplen. Un
        tamiz "sin dato" no cuenta como incumplimiento, pero se informa."""
        return (all(f.cumple for f in self.filas)
                and all(ok for _, ok in self.criterios))

    @property
    def sin_dato(self):
        return [f for f in self.filas if f.origen == "sin dato"]


def _pasa_en(curva, abertura_mm):
    """% que pasa en ``abertura_mm`` y de dónde sale (ver FilaVerificacion)."""
    ab = curva.abertura_mm
    exacto = np.isclose(ab, abertura_mm)
    if exacto.any():
        return float(curva.pasa[exacto][0]), "medido"
    if abertura_mm > ab.max():
        return 100.0, "100 %"
    if abertura_mm < ab.min():
        return float("nan"), "sin dato"
    from .modelo import interpolar_pasa
    return interpolar_pasa(ab, curva.pasa, abertura_mm), "interpolado"


def verificar(curva, especificacion, atterberg=None):
    """Compara una :class:`CurvaGranulometrica` con una especificación.

    Args:
        curva: curva calculada por :func:`app.modelo.calcular_curva`.
        especificacion: :class:`Especificacion` o su código.
        atterberg: :class:`app.modelo.Atterberg` (opcional). Si la
            especificación exige LL/IP y no se dan, el criterio se reporta
            como no cumplido (no se puede demostrar).

    Returns:
        :class:`VerificacionEspecificacion`.
    """
    if isinstance(especificacion, str):
        try:
            especificacion = ESPECIFICACIONES[especificacion]
        except KeyError:
            raise ValueError(f"Especificación desconocida: {especificacion}")

    filas = []
    for ab in sorted(especificacion.franja, reverse=True):
        mn, mx = especificacion.franja[ab]
        pasa, origen = _pasa_en(curva, ab)
        if origen == "sin dato":
            cumple = True
        else:
            cumple = (mn - TOLERANCIA) <= pasa <= (mx + TOLERANCIA)
        filas.append(FilaVerificacion(ab, _nombre_tamiz(ab), pasa, mn, mx,
                                      origen, bool(cumple)))

    criterios = []
    if especificacion.LL_max is not None:
        if atterberg is None:
            criterios.append((f"LL ≤ {especificacion.LL_max:g} % "
                              "(sin datos de Atterberg)", False))
        else:
            criterios.append((f"LL = {atterberg.LL:g} % ≤ "
                              f"{especificacion.LL_max:g} %",
                              atterberg.LL <= especificacion.LL_max))
    if especificacion.IP_max is not None:
        if atterberg is None:
            criterios.append((f"IP ≤ {especificacion.IP_max:g} % "
                              "(sin datos de Atterberg)", False))
        else:
            criterios.append((f"IP = {atterberg.PI:g} % ≤ "
                              f"{especificacion.IP_max:g} %",
                              atterberg.PI <= especificacion.IP_max))
    if especificacion.relacion_200_40_max is not None:
        p200, o200 = _pasa_en(curva, ABERTURA_NO200)
        p40, o40 = _pasa_en(curva, ABERTURA_NO40)
        if "sin dato" in (o200, o40) or p40 <= 0:
            criterios.append(("Relación No.200 / No.40 (sin datos)", False))
        else:
            rel = p200 / p40
            criterios.append(
                (f"Relación No.200 / No.40 = {rel:.3f} ≤ "
                 f"{especificacion.relacion_200_40_max:.3f}",
                 rel <= especificacion.relacion_200_40_max + TOLERANCIA))

    return VerificacionEspecificacion(especificacion, filas, criterios)


# ---------------------------------------------------------------------------
# Especificaciones propias (JSON)
# ---------------------------------------------------------------------------
def cargar_especificaciones_json(ruta):
    """Lee un JSON con especificaciones propias y las devuelve en un dict
    ``{codigo: Especificacion}`` (con ``verificada=False``).

    Formato (lista de objetos)::

        [{"codigo": "MI-ESPEC", "nombre": "...", "fuente": "...",
          "franja": {"25.0": [100, 100], "4.75": [35, 65]},
          "LL_max": 30, "IP_max": 8}]

    Las claves de ``franja`` son aberturas en mm; los valores, [mín, máx]
    de % que pasa.

    Raises:
        ValueError: si el archivo no tiene el formato esperado.
    """
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer {ruta}: {exc}") from exc
    if not isinstance(datos, list):
        raise ValueError("El JSON debe ser una lista de especificaciones.")
    resultado = {}
    for d in datos:
        try:
            franja = {}
            for k, (mn, mx) in d["franja"].items():
                mn, mx = float(mn), float(mx)
                if not 0 <= mn <= mx <= 100:
                    raise ValueError(
                        f"límites inválidos en tamiz {k} ({mn}-{mx})")
                franja[float(k)] = (mn, mx)
            if not franja:
                raise ValueError("la franja está vacía")
            codigo = str(d["codigo"]).strip()
            if not codigo:
                raise ValueError("falta el código")
            resultado[codigo] = Especificacion(
                codigo, d.get("nombre", codigo),
                d.get("fuente", "Definida por el usuario"), franja,
                d.get("LL_max"), d.get("IP_max"),
                d.get("relacion_200_40_max"), verificada=False)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Especificación inválida ({d.get('codigo', '?') if isinstance(d, dict) else d}): "
                f"{exc}") from exc
    return resultado


def todas_las_especificaciones(ruta_json=None):
    """Incluidas + (opcionalmente) las propias de ``ruta_json``."""
    todas = dict(ESPECIFICACIONES)
    if ruta_json is not None and Path(ruta_json).exists():
        todas.update(cargar_especificaciones_json(ruta_json))
    return todas
