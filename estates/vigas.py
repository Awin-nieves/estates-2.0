"""Análisis de vigas continuas planas por el método de rigidez directa.

Expresiones tomadas de PyMAS (primitives.py):

  * Rigidez a flexión: bloque 4x4 con 12EI/L³, 6EI/L², 4EI/L y 2EI/L
    (``Frame.local_stiffness_matrix``).
  * Acciones de empotramiento perfecto para carga puntual y uniforme
    (``FramePointLoad`` y ``DistributedLoad.fixed_load_vector``).
  * Reconstrucción de V, M, giro y flecha integrando desde el extremo j, con
    los términos x³/(6EI), x²/(2EI) y x⁴/(24EI)
    (``Frame.get_internal_forces`` y ``get_internal_displacements``).

Convenciones (las mismas de PyMAS)
----------------------------------
  * Eje x a lo largo de la viga, eje y hacia ARRIBA, giros + antihorarios.
  * M > 0 tracciona la fibra inferior.
  * Al ENTRAR las cargas, hacia abajo es positivo.
  * Unidades: kN, m, kPa (= kN/m²).
"""
from dataclasses import dataclass, field

import numpy as np

APOYOS = {"empotrado": (True, True),
          "articulado": (True, False),
          "libre": (False, False)}


@dataclass
class Tramo:
    """Tramo de viga entre dos nudos.

    Atributos:
        L: longitud [m].
        material: objeto ``Material``.
        seccion: objeto ``Seccion``.
        w: carga uniforme hacia abajo [kN/m], sin incluir el peso propio.
        puntuales: lista de cargas puntuales ``(a, P)``, con ``a`` la
            distancia desde el nudo izquierdo [m] (0 < a < L) y ``P`` la
            carga hacia abajo [kN].
        peso_propio: si es True, suma gamma·A a la carga uniforme.
    """

    L: float
    material: object
    seccion: object
    w: float = 0.0
    puntuales: list = field(default_factory=list)
    peso_propio: bool = True

    @property
    def EI(self):
        return self.material.E * self.seccion.Iz

    @property
    def w_total(self):
        pp = self.material.gamma * self.seccion.A if self.peso_propio else 0.0
        return self.w + pp

    def rigidez_local(self):
        """Matriz de rigidez a flexión, grados de libertad [v_j, θ_j, v_k, θ_k]."""
        L, EI = self.L, self.EI
        e_l3 = 12 * EI / L**3
        e_l2 = 6 * EI / L**2
        e_l = EI / L
        return np.array([
            [e_l3,  e_l2,    -e_l3,  e_l2],
            [e_l2,  4 * e_l, -e_l2,  2 * e_l],
            [-e_l3, -e_l2,   e_l3,   -e_l2],
            [e_l2,  2 * e_l, -e_l2,  4 * e_l],
        ])

    def acciones_empotramiento(self):
        """Acciones de extremo con los nudos empotrados [fy_j, mz_j, fy_k, mz_k].

        Fuerzas con y hacia arriba y momentos antihorarios: son las acciones
        que los nudos ejercen sobre el tramo.
        """
        L = self.L
        q = -self.w_total                            # eje y hacia arriba
        f0 = np.array([-q * L / 2, -q * L**2 / 12, -q * L / 2, q * L**2 / 12])
        for a, P in self.puntuales:
            if not 0 < a < L:
                raise ValueError("La carga puntual debe estar dentro del "
                                 "tramo (0 < a < L); en un nudo, usa "
                                 "cargas_nodales.")
            b = L - a
            p = -P
            f0 += np.array([-p * b**2 * (3 * a + b) / L**3,
                            -p * a * b**2 / L**2,
                            -p * a**2 * (a + 3 * b) / L**3,
                            p * a**2 * b / L**2])
        return f0

    def campos(self, d, n=200):
        """V, M, giro y flecha a lo largo del tramo (integración desde j).

        Args:
            d: desplazamientos de los nudos [v_j, θ_j, v_k, θ_k].
            n: número de divisiones del tramo.

        Returns:
            Tupla (x, V, M, th, v) con x medida desde el nudo j.
        """
        L, EI = self.L, self.EI
        f = self.rigidez_local() @ d + self.acciones_empotramiento()
        fy_j, mz_j = f[0], f[1]
        q = -self.w_total

        x = np.linspace(0, L, n + 1)
        for a, _ in self.puntuales:                  # captura el salto en V
            x = np.concatenate([x, [a - 1e-9 * L, a + 1e-9 * L]])
        x = np.unique(x)

        V = fy_j + q * x
        M = -mz_j + fy_j * x + q * x**2 / 2
        th = d[1] + (-mz_j * x + fy_j * x**2 / 2 + q * x**3 / 6) / EI
        v = d[0] + d[1] * x + (-mz_j * x**2 / 2 + fy_j * x**3 / 6
                               + q * x**4 / 24) / EI
        for a, P in self.puntuales:
            p = -P
            s = np.clip(x - a, 0, None)              # <x - a>
            V = V + p * (x >= a)
            M = M + p * s
            th = th + p * s**2 / (2 * EI)
            v = v + p * s**3 / (6 * EI)
        return x, V, M, th, v


class VigaContinua:
    """Viga continua de uno o varios tramos.

    Args:
        tramos: lista de ``Tramo``.
        apoyos: un texto por nudo (len = tramos + 1): 'empotrado',
            'articulado' o 'libre'.
        cargas_nodales: {nudo: (P, M)} con P hacia abajo [kN] y M
            antihorario [kN·m].

    Después de ``resolver()`` quedan disponibles:
        D: desplazamientos nodales [v0, θ0, v1, θ1, ...].
        R: reacciones [Ry0, Mz0, Ry1, Mz1, ...] (cero en grados libres).
        resultados: lista (uno por tramo) de dicts con x (global), V, M,
            th y v.
    """

    def __init__(self, tramos, apoyos, cargas_nodales=None):
        if len(apoyos) != len(tramos) + 1:
            raise ValueError("Debe haber un apoyo por nudo (tramos + 1).")
        self.tramos = tramos
        self.apoyos = apoyos
        self.cargas_nodales = cargas_nodales or {}
        self.x_nudos = np.concatenate([[0], np.cumsum([t.L for t in tramos])])

    def resolver(self):
        n_nudos = len(self.tramos) + 1
        ndof = 2 * n_nudos                           # [v, θ] por nudo
        K = np.zeros((ndof, ndof))
        F0 = np.zeros(ndof)
        P = np.zeros(ndof)

        for i, t in enumerate(self.tramos):
            idx = np.arange(2 * i, 2 * i + 4)
            K[np.ix_(idx, idx)] += t.rigidez_local()
            F0[idx] += t.acciones_empotramiento()

        for nudo, (Pn, Mn) in self.cargas_nodales.items():
            P[2 * nudo] += -Pn
            P[2 * nudo + 1] += Mn

        rest = np.zeros(ndof, dtype=bool)
        for i, tipo in enumerate(self.apoyos):
            rest[2 * i], rest[2 * i + 1] = APOYOS[tipo]
        libres = np.nonzero(~rest)[0]

        D = np.zeros(ndof)
        if len(libres):                              # hay incógnitas
            Kff = K[np.ix_(libres, libres)]
            if np.linalg.matrix_rank(Kff) < len(libres):
                raise ValueError("La estructura es inestable (mecanismo): "
                                 "revisa los apoyos.")
            D[libres] = np.linalg.solve(Kff, P[libres] - F0[libres])
        R = np.where(rest, K @ D + F0 - P, 0.0)      # reacciones (y arriba)

        self.D, self.R = D, R
        self.resultados = []
        for i, t in enumerate(self.tramos):
            x, V, M, th, v = t.campos(D[2 * i:2 * i + 4])
            self.resultados.append(
                dict(x=x + self.x_nudos[i], V=V, M=M, th=th, v=v))
        return self

    def resumen(self, limite_flecha=360):
        """Imprime reacciones y verificaciones (σ, τ y flecha) por tramo."""
        print("=" * 62)
        print("REACCIONES  (Ry positiva hacia arriba, Mz antihoraria)")
        print("=" * 62)
        for i, tipo in enumerate(self.apoyos):
            if tipo == "libre":
                continue
            ry, mz = self.R[2 * i], self.R[2 * i + 1]
            linea = f"Nudo {i} ({tipo:10s}) x = {self.x_nudos[i]:6.2f} m:  "
            linea += f"Ry = {ry:9.3f} kN"
            if tipo == "empotrado":
                linea += f"   Mz = {mz:9.3f} kN·m"
            print(linea)

        print("\n" + "=" * 62)
        print("RESULTADOS Y VERIFICACIONES POR TRAMO")
        print("=" * 62)
        for i, (t, r) in enumerate(zip(self.tramos, self.resultados)):
            iM = np.argmax(np.abs(r["M"]))
            iV = np.argmax(np.abs(r["V"]))
            iv = np.argmax(np.abs(r["v"]))
            M_max, V_max = abs(r["M"][iM]), abs(r["V"][iV])
            v_max = abs(r["v"][iv])

            sigma = M_max * t.seccion.c / t.seccion.Iz / 1000   # MPa
            tau = t.seccion.k_tau * V_max / t.seccion.A / 1000  # MPa
            v_adm = t.L / limite_flecha

            print(f"\nTramo {i + 1}  (L = {t.L:g} m, {t.seccion.nombre}, "
                  f"w total = {t.w_total:.3f} kN/m)")
            print(f"  M+ máx = {r['M'].max():9.3f} kN·m | "
                  f"M- mín = {r['M'].min():9.3f} kN·m")
            print(f"  |V| máx = {V_max:8.3f} kN  (x = {r['x'][iV]:.2f} m)")
            print(f"  Flecha máx = {v_max * 1000:7.3f} mm  "
                  f"(admisible L/{limite_flecha} = {v_adm * 1000:.2f} mm)  "
                  f"-> {'CUMPLE' if v_max <= v_adm else 'NO CUMPLE'}")
            print(f"  σ máx = |M|·c/Iz = {sigma:8.3f} MPa | "
                  f"τ máx = {tau:6.3f} MPa")

    def graficar(self, archivo=None, mostrar=True):
        """Dibuja esquema, cortante, momento y flecha (requiere matplotlib)."""
        from .graficos import graficar
        return graficar(self, archivo=archivo, mostrar=mostrar)
