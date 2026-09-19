"""Ejemplo: viga continua de tres tramos, sección 25x45 cm de concreto.

Datos supuestos (típicos de una viga de piso continua sobre tres apoyos
intermedios):
  - Tramo 1: L = 4.0 m, w = 18 kN/m
  - Tramo 2: L = 5.0 m, w = 18 kN/m, carga puntual de 35 kN a 2.5 m del
    nudo izquierdo (centro del tramo)
  - Tramo 3: L = 3.5 m, w = 18 kN/m
  - Los 4 nudos son apoyos articulados.

Ejecutar desde la raíz del repositorio:  python examples/tres_tramos.py
"""
from pathlib import Path

from estates import Tramo, VigaContinua, concreto, seccion_rectangular

RUTA_IMAGEN = Path(__file__).resolve().parents[1] / "docs" / "img" / \
    "tres_tramos.png"

concreto28 = concreto(28)                            # f'c = 28 MPa
sec = seccion_rectangular("25x45 cm", base=0.25, altura=0.45)

tramo1 = Tramo(L=4.0, material=concreto28, seccion=sec, w=18.0)
tramo2 = Tramo(L=5.0, material=concreto28, seccion=sec, w=18.0,
               puntuales=[(2.5, 35.0)])              # 35 kN al centro del tramo
tramo3 = Tramo(L=3.5, material=concreto28, seccion=sec, w=18.0)

viga = VigaContinua([tramo1, tramo2, tramo3],
                    apoyos=["articulado"] * 4)
viga.resolver()
viga.resumen(limite_flecha=360)
viga.graficar(archivo=RUTA_IMAGEN, mostrar=False)
