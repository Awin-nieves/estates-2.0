"""Análisis granulométrico y clasificación de suelos (USCS / AASHTO).

Módulo de cálculo puro: no importa Flet ni nada de interfaz, así que se
puede usar y probar por separado (``from app.modelo import procesar``).

Referencias:
    * Tamices: serie ASTM E11.
    * Clasificación unificada de suelos (USCS): ASTM D2487.
    * Clasificación AASHTO: AASHTO M 145 / ASTM D3282, incluido el
      índice de grupo (GI).

Convenciones:
    * Todas las aberturas de tamiz en milímetros.
    * Todos los porcentajes en base 0-100.
    * LL (límite líquido) y PI (índice de plasticidad) en porcentaje,
      como se reportan en el ensayo de límites de Atterberg.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import interp1d

# ---------------------------------------------------------------------------
# Serie de tamices ASTM E11 (nombre -> abertura en mm)
# ---------------------------------------------------------------------------
TAMICES_ASTM = {
    "3\"": 75.0, "2\"": 50.0, "1 1/2\"": 37.5, "1\"": 25.0, "3/4\"": 19.0,
    "1/2\"": 12.5, "3/8\"": 9.5, "No.4": 4.75, "No.10": 2.00, "No.20": 0.850,
    "No.40": 0.425, "No.60": 0.250, "No.100": 0.150, "No.200": 0.075,
}

ABERTURA_NO4 = TAMICES_ASTM["No.4"]      # límite grava / arena
ABERTURA_NO10 = TAMICES_ASTM["No.10"]    # usado en AASHTO
ABERTURA_NO40 = TAMICES_ASTM["No.40"]    # usado en AASHTO
ABERTURA_NO200 = TAMICES_ASTM["No.200"]  # límite arena / finos


# ---------------------------------------------------------------------------
# Granulometría
# ---------------------------------------------------------------------------
@dataclass
class Tamiz:
    """Un punto del ensayo de granulometría.

    Atributos:
        nombre: etiqueta del tamiz (p. ej. "No.40"); informativa.
        abertura_mm: abertura del tamiz [mm].
        retenido_g: masa retenida en ese tamiz [g].
    """
    nombre: str
    abertura_mm: float
    retenido_g: float


@dataclass
class CurvaGranulometrica:
    """Resultado del procesamiento de una serie de tamices.

    Atributos:
        abertura_mm: aberturas ordenadas de MENOR a MAYOR [mm].
        pasa: % que pasa acumulado, en el mismo orden.
        masa_total_g: masa total de la muestra (suma de retenidos + fondo).
        D10, D30, D60: diámetros interpolados [mm] para 10 %, 30 % y 60 %
            que pasa.
        Cu: coeficiente de uniformidad D60/D10.
        Cc: coeficiente de curvatura D30²/(D10·D60).
        pct_grava, pct_arena, pct_finos: fracciones del suelo [%].
    """
    abertura_mm: np.ndarray
    pasa: np.ndarray
    masa_total_g: float
    D10: float
    D30: float
    D60: float
    Cu: float
    Cc: float
    pct_grava: float
    pct_arena: float
    pct_finos: float


def calcular_curva(tamices, peso_fondo_g=0.0):
    """Procesa una lista de :class:`Tamiz` y devuelve la curva granulométrica.

    Vectorizado con NumPy: % retenido, % retenido acumulado y % que pasa
    se calculan con ``cumsum`` sobre el arreglo, sin ciclos ``for``.

    Args:
        tamices: lista de :class:`Tamiz`, en cualquier orden.
        peso_fondo_g: masa retenida en el fondo (pasa el tamiz más fino)
            [g].

    Returns:
        :class:`CurvaGranulometrica`.

    Raises:
        ValueError: si hay menos de 2 tamices, masas negativas, o la masa
            total es cero.
    """
    if len(tamices) < 2:
        raise ValueError("Se necesitan al menos 2 tamices para construir "
                         "la curva granulométrica.")

    orden = sorted(tamices, key=lambda t: t.abertura_mm)  # menor a mayor
    abertura = np.array([t.abertura_mm for t in orden], dtype=float)
    retenido = np.array([t.retenido_g for t in orden], dtype=float)

    if np.any(retenido < 0) or peso_fondo_g < 0:
        raise ValueError("Las masas retenidas no pueden ser negativas.")

    masa_total = retenido.sum() + peso_fondo_g
    if masa_total <= 0:
        raise ValueError("La masa total de la muestra debe ser mayor que "
                         "cero.")

    # Retenido acumulado de MAYOR a MENOR abertura -> invertimos, acumulamos
    # con cumsum (vectorizado) y volvemos a invertir.
    retenido_acum_desc = np.cumsum(retenido[::-1])[::-1]
    pct_retenido_acum = retenido_acum_desc / masa_total * 100.0
    pasa = 100.0 - pct_retenido_acum

    D10 = interpolar_diametro(abertura, pasa, 10.0)
    D30 = interpolar_diametro(abertura, pasa, 30.0)
    D60 = interpolar_diametro(abertura, pasa, 60.0)
    Cu = D60 / D10
    Cc = D30**2 / (D10 * D60)

    pasa_no4 = interpolar_pasa(abertura, pasa, ABERTURA_NO4)
    pasa_no200 = interpolar_pasa(abertura, pasa, ABERTURA_NO200)
    pct_grava = 100.0 - pasa_no4
    pct_finos = pasa_no200
    pct_arena = 100.0 - pct_grava - pct_finos

    return CurvaGranulometrica(abertura, pasa, masa_total, D10, D30, D60,
                               Cu, Cc, pct_grava, pct_arena, pct_finos)


def interpolar_pasa(abertura_mm, pasa, diametro_mm):
    """% que pasa para un diámetro cualquiera, interpolado en semi-log.

    La curva granulométrica se lee tradicionalmente en papel semi-
    logarítmico (abertura en escala log, % que pasa en escala lineal), así
    que se interpola linealmente sobre log10(abertura). Se usa
    ``scipy.interpolate.interp1d``.

    Args:
        abertura_mm: aberturas ordenadas de menor a mayor [mm].
        pasa: % que pasa correspondiente a cada abertura.
        diametro_mm: diámetro en el que se quiere el % que pasa [mm].

    Raises:
        ValueError: si ``diametro_mm`` cae fuera del rango de tamices
            ensayados (no se extrapola).
    """
    log_x = np.log10(abertura_mm)
    f = interp1d(log_x, pasa, kind="linear", bounds_error=True)
    try:
        return float(f(np.log10(diametro_mm)))
    except ValueError as e:
        raise ValueError(
            f"El diámetro {diametro_mm:g} mm está fuera del rango de "
            f"tamices ensayados ({abertura_mm.min():g}-"
            f"{abertura_mm.max():g} mm).") from e


def interpolar_diametro(abertura_mm, pasa, pasa_objetivo):
    """Diámetro [mm] para un % que pasa dado (D10, D30, D60, ...).

    Es la función inversa de :func:`interpolar_pasa`: dado que el % que
    pasa decrece monótonamente con la abertura, se interpola log10(D) como
    función de %pasa y se deshace el logaritmo.

    Args:
        abertura_mm: aberturas ordenadas de menor a mayor [mm].
        pasa: % que pasa correspondiente a cada abertura.
        pasa_objetivo: porcentaje que pasa buscado (p. ej. 10, 30, 60).

    Raises:
        ValueError: si ``pasa_objetivo`` está fuera del rango de la curva
            ensayada (p. ej. pedir D60 cuando el máximo % que pasa medido
            es 55 %): no se extrapola, hacen falta tamices más gruesos o
            más finos.
    """
    # Con las aberturas de menor a mayor, el % que pasa es NO decreciente
    # (crece o se repite). Se repite cuando un tamiz no retiene nada, así
    # que interp1d (que necesita x estrictamente monótono) daría un tramo
    # arbitrario. Se busca el tramo donde la curva cruza el objetivo:
    # pasa[j-1] < objetivo <= pasa[j], y se interpola log10(D) en él.
    if not pasa[0] <= pasa_objetivo <= pasa[-1]:
        raise ValueError(
            f"No se puede interpolar D para {pasa_objetivo:g} % que pasa: "
            f"está fuera del rango ensayado ({pasa.min():.1f}-"
            f"{pasa.max():.1f} % que pasa). Agrega tamices más gruesos o "
            "más finos.")
    log_x = np.log10(abertura_mm)
    j = int(np.searchsorted(pasa, pasa_objetivo, side="left"))
    if j == 0:                       # objetivo == pasa mínimo
        return float(abertura_mm[0])
    p0, p1 = pasa[j - 1], pasa[j]    # p0 < objetivo <= p1 (p1 > p0)
    fraccion = (pasa_objetivo - p0) / (p1 - p0)
    log_d = log_x[j - 1] + fraccion * (log_x[j] - log_x[j - 1])
    return float(10 ** log_d)


# ---------------------------------------------------------------------------
# Clasificación USCS (ASTM D2487)
# ---------------------------------------------------------------------------
@dataclass
class Atterberg:
    """Límites de Atterberg de la fracción fina.

    Atributos:
        LL: límite líquido [%].
        LP: límite plástico [%].
    """
    LL: float
    LP: float

    @property
    def PI(self):
        """Índice de plasticidad, PI = LL - LP [%]. No puede ser negativo."""
        return max(self.LL - self.LP, 0.0)


def _linea_A(LL):
    """PI de la línea A en la carta de plasticidad: PI = 0.73(LL - 20)."""
    return 0.73 * (LL - 20.0)


def _tipo_finos(at):
    """Clasifica la fracción fina sola: 'M' (limo), 'C' (arcilla) o 'M-C'
    (borde CL-ML / GM-GC / SM-SC), según PI frente a la línea A.

    No distingue orgánicos (OL/OH): requieren ensayo de materia orgánica,
    que está fuera del alcance de este modelo (ver limitaciones).
    """
    PI, LL = at.PI, at.LL
    pi_A = _linea_A(LL)
    if PI < 4 or PI < pi_A:
        return "M"
    if PI >= 7 and PI >= pi_A:
        return "C"
    return "M-C"                                      # zona CL-ML


def clasificar_uscs(curva, atterberg=None):
    """Clasifica el suelo según USCS (ASTM D2487), versión de curso.

    Args:
        curva: :class:`CurvaGranulometrica` ya calculada.
        atterberg: :class:`Atterberg` de la fracción fina; obligatorio si
            %finos >= 5 (coarse) o si %finos >= 50 (suelo fino).

    Returns:
        Tupla ``(simbolo, descripcion)``.

    Limitaciones (ver README): no distingue suelos orgánicos (OL/OH/Pt),
    que requieren ensayo de materia orgánica.
    """
    F = curva.pct_finos

    if F >= 50:
        # ---- Suelo de grano fino: Limo o arcilla -----------------------
        if atterberg is None:
            raise ValueError("Con % de finos >= 50 se necesitan los "
                             "límites de Atterberg (LL, LP) para "
                             "clasificar por USCS.")
        tipo = _tipo_finos(atterberg)
        sufijo = "H" if atterberg.LL >= 50 else "L"
        if tipo == "M":
            return f"M{sufijo}", _desc_uscs(f"M{sufijo}")
        if tipo == "C":
            return f"C{sufijo}", _desc_uscs(f"C{sufijo}")
        return "CL-ML", _desc_uscs("CL-ML")

    # ---- Suelo de grano grueso: Grava o arena --------------------------
    prefijo = "G" if curva.pct_grava >= curva.pct_arena else "S"
    cu_min, cc_lo, cc_hi = (4, 1, 3) if prefijo == "G" else (6, 1, 3)
    bien_graduado = curva.Cu >= cu_min and cc_lo <= curva.Cc <= cc_hi

    if F < 5:
        simbolo = f"{prefijo}{'W' if bien_graduado else 'P'}"
        return simbolo, _desc_uscs(simbolo)

    if F > 12:
        if atterberg is None:
            raise ValueError("Con % de finos > 12 se necesitan los "
                             "límites de Atterberg (LL, LP) para "
                             "clasificar por USCS.")
        tipo = _tipo_finos(atterberg)
        if tipo == "M":
            simbolo = f"{prefijo}M"
        elif tipo == "C":
            simbolo = f"{prefijo}C"
        else:
            simbolo = f"{prefijo}C-{prefijo}M"
        return simbolo, _desc_uscs(simbolo)

    # 5 % <= F <= 12 %: símbolo doble (gradación + tipo de finos)
    if atterberg is None:
        raise ValueError("Con 5 % <= % de finos <= 12 % se necesitan los "
                         "límites de Atterberg (LL, LP) para clasificar "
                         "por USCS (símbolo doble).")
    tipo = _tipo_finos(atterberg)
    letra_finos = "M" if tipo == "M" else "C"          # borde -> más fino
    simbolo = f"{prefijo}{'W' if bien_graduado else 'P'}-{prefijo}{letra_finos}"
    return simbolo, _desc_uscs(simbolo)


_DESC_USCS = {
    "GW": "Grava bien graduada", "GP": "Grava mal graduada",
    "GM": "Grava limosa", "GC": "Grava arcillosa",
    "GC-GM": "Grava limo-arcillosa",
    "GW-GM": "Grava bien graduada con limo",
    "GW-GC": "Grava bien graduada con arcilla",
    "GP-GM": "Grava mal graduada con limo",
    "GP-GC": "Grava mal graduada con arcilla",
    "SW": "Arena bien graduada", "SP": "Arena mal graduada",
    "SM": "Arena limosa", "SC": "Arena arcillosa",
    "SC-SM": "Arena limo-arcillosa",
    "SW-SM": "Arena bien graduada con limo",
    "SW-SC": "Arena bien graduada con arcilla",
    "SP-SM": "Arena mal graduada con limo",
    "SP-SC": "Arena mal graduada con arcilla",
    "ML": "Limo inorgánico de baja plasticidad",
    "CL": "Arcilla inorgánica de baja a media plasticidad",
    "CL-ML": "Limo arcilloso de baja plasticidad",
    "MH": "Limo inorgánico de alta plasticidad",
    "CH": "Arcilla inorgánica de alta plasticidad",
}


def _desc_uscs(simbolo):
    return _DESC_USCS.get(simbolo, simbolo)


# ---------------------------------------------------------------------------
# Clasificación AASHTO (AASHTO M 145 / ASTM D3282)
# ---------------------------------------------------------------------------
@dataclass
class ResultadoAASHTO:
    """Atributos:
        grupo: p. ej. "A-2-4".
        indice_grupo: índice de grupo GI (entero, >= 0).
        descripcion: calificación general del material.
    """
    grupo: str
    indice_grupo: int
    descripcion: str


def _indice_grupo(pasa200, LL, PI):
    """Índice de grupo (AASHTO M 145), con los términos recortados al
    rango normado antes de combinarlos."""
    a = np.clip(pasa200 - 35, 0, 40)
    b = np.clip(LL - 40, 0, 20)
    c = np.clip(pasa200 - 15, 0, 40)
    d = np.clip(PI - 10, 0, 20)
    gi = 0.2 * a + 0.005 * a * b + 0.01 * c * d
    return max(0, int(round(gi)))


def clasificar_aashto(curva, atterberg):
    """Clasifica el suelo según AASHTO M 145 / ASTM D3282.

    Args:
        curva: :class:`CurvaGranulometrica` ya calculada.
        atterberg: :class:`Atterberg`; obligatorio (AASHTO siempre usa
            LL y PI, incluso para material granular limpio, donde PI se
            reporta como "no plástico", PI=0).

    Returns:
        :class:`ResultadoAASHTO`.
    """
    pasa10 = interpolar_pasa(curva.abertura_mm, curva.pasa, ABERTURA_NO10)
    pasa40 = interpolar_pasa(curva.abertura_mm, curva.pasa, ABERTURA_NO40)
    pasa200 = curva.pct_finos
    LL, PI = atterberg.LL, atterberg.PI

    if pasa200 <= 35:                                  # ---- Granular ----
        if pasa10 <= 50 and pasa40 <= 30 and pasa200 <= 15 and PI <= 6:
            grupo = "A-1-a"
        elif pasa40 <= 50 and pasa200 <= 25 and PI <= 6:
            grupo = "A-1-b"
        elif pasa40 >= 51 and pasa200 <= 10 and PI <= 0.1:
            grupo = "A-3"
        elif LL <= 40 and PI <= 10:
            grupo = "A-2-4"
        elif LL >= 41 and PI <= 10:
            grupo = "A-2-5"
        elif LL <= 40 and PI >= 11:
            grupo = "A-2-6"
        else:
            grupo = "A-2-7"
    else:                                               # ---- Limo-arcilla
        if LL <= 40 and PI <= 10:
            grupo = "A-4"
        elif LL >= 41 and PI <= 10:
            grupo = "A-5"
        elif LL <= 40 and PI >= 11:
            grupo = "A-6"
        else:
            grupo = "A-7-5" if PI <= LL - 30 else "A-7-6"

    gi = _indice_grupo(pasa200, LL, PI)
    calificacion = ("Excelente a bueno" if grupo in
                    ("A-1-a", "A-1-b", "A-3", "A-2-4", "A-2-5", "A-2-6",
                     "A-2-7")
                    else "Regular a malo")
    return ResultadoAASHTO(grupo, gi, calificacion)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
@dataclass
class ResultadoClasificacion:
    """Resultado completo de un cálculo: curva + USCS + AASHTO.

    Atributos:
        curva: :class:`CurvaGranulometrica`.
        uscs_simbolo, uscs_descripcion: resultado USCS.
        aashto: :class:`ResultadoAASHTO` (``None`` si no se dieron límites
            de Atterberg y no eran obligatorios para USCS; AASHTO siempre
            necesita Atterberg).
        atterberg: límites usados, si se dieron.
    """
    curva: CurvaGranulometrica
    uscs_simbolo: str
    uscs_descripcion: str
    aashto: object = None
    atterberg: object = None


def procesar(tamices, peso_fondo_g=0.0, LL=None, LP=None):
    """Punto de entrada único: de datos crudos de laboratorio a
    clasificación completa.

    Args:
        tamices: lista de :class:`Tamiz`.
        peso_fondo_g: masa retenida en el fondo [g].
        LL: límite líquido [%] (opcional).
        LP: límite plástico [%] (opcional; se ignora si LL es None).

    Returns:
        :class:`ResultadoClasificacion`.
    """
    curva = calcular_curva(tamices, peso_fondo_g)
    atterberg = Atterberg(LL, LP) if LL is not None and LP is not None else None

    simbolo, descripcion = clasificar_uscs(curva, atterberg)

    aashto = None
    if atterberg is not None:
        aashto = clasificar_aashto(curva, atterberg)

    return ResultadoClasificacion(curva, simbolo, descripcion, aashto,
                                  atterberg)
