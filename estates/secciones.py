"""Propiedades geométricas de secciones transversales.

Expresiones tomadas de ``RectangularSection`` y ``CircularSection`` de
PyMAS (primitives.py).
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class Seccion:
    """Sección transversal.

    Atributos:
        nombre: nombre de la sección.
        A: área [m²].
        J: constante torsional [m⁴].
        Iy: inercia respecto al eje local y [m⁴].
        Iz: inercia respecto al eje local z [m⁴]; es la que gobierna la
            flexión en el plano vertical x-y.
        c: distancia del eje neutro a la fibra extrema, en y [m].
        k_tau: factor del cortante máximo, tau_max = k_tau · V / A
            (1.5 para rectángulo, 4/3 para círculo).
    """

    nombre: str
    A: float
    J: float
    Iy: float
    Iz: float
    c: float
    k_tau: float


def seccion_circular(nombre, diametro):
    """Sección circular maciza de diámetro ``diametro`` [m]."""
    r = diametro / 2
    A = np.pi * r**2
    J = np.pi * r**4 / 2
    Iy = Iz = np.pi * r**4 / 4
    return Seccion(nombre, A, J, Iy, Iz, c=r, k_tau=4 / 3)


def seccion_rectangular(nombre, base, altura):
    """Sección rectangular de ``base`` (eje z) y ``altura`` (eje y) [m].

    La constante torsional J usa la aproximación de Saint-Venant, con
    a = lado menor y b = lado mayor.
    """
    a, b = sorted((base, altura))
    A = base * altura
    J = (1 / 3 - 0.21 * (a / b) * (1 - (1 / 12) * (a / b)**4)) * b * a**3
    Iy = (1 / 12) * altura * base**3
    Iz = (1 / 12) * base * altura**3
    return Seccion(nombre, A, J, Iy, Iz, c=altura / 2, k_tau=1.5)
