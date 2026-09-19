"""Ejemplo: viga continua de dos tramos, sección 30x50 cm de concreto.

Ejecutar desde la raíz del repositorio:  python examples/dos_tramos.py
"""
from pathlib import Path

from estates import Tramo, VigaContinua, concreto, seccion_rectangular

RUTA_IMAGEN = Path(__file__).resolve().parents[1] / "docs" / "img" / \
    "viga_continua.png"

concreto21 = concreto(21)                            # f'c = 21 MPa
sec = seccion_rectangular("30x50 cm", base=0.30, altura=0.50)

tramo1 = Tramo(L=5.0, material=concreto21, seccion=sec, w=20.0)
tramo2 = Tramo(L=4.0, material=concreto21, seccion=sec, w=15.0,
               puntuales=[(2.0, 30.0)])              # 30 kN a 2 m del nudo 1

viga = VigaContinua([tramo1, tramo2],
                    apoyos=["articulado", "articulado", "articulado"])
viga.resolver()
viga.resumen(limite_flecha=360)
viga.graficar(archivo=RUTA_IMAGEN)
