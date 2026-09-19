"""Materiales de construcción para el análisis estructural."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Material:
    """Material elástico lineal.

    Atributos:
        nombre: nombre del material.
        E: módulo de elasticidad [kPa].
        G: módulo de elasticidad en cortante [kPa] (no interviene en flexión).
        gamma: peso específico [kN/m³], usado para el peso propio.
    """

    nombre: str
    E: float
    G: float = 0.0
    gamma: float = 0.0


def concreto(fc_mpa, nu=0.2, gamma=24.0):
    """Concreto de peso normal a partir de su resistencia f'c.

    Usa Ec = 3900·sqrt(f'c) [MPa] (NSR-10 C.8.5.1). Verifica la expresión y
    la rigidez efectiva (fisuración) que exija tu curso o norma.

    Args:
        fc_mpa: resistencia a compresión f'c [MPa].
        nu: relación de Poisson, para G = E / (2(1 + nu)).
        gamma: peso específico [kN/m³].
    """
    E = 3900.0 * np.sqrt(fc_mpa) * 1000.0            # MPa -> kPa
    return Material(f"Concreto f'c={fc_mpa:g} MPa", E, E / (2 * (1 + nu)),
                    gamma)
