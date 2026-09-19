"""Gráficos de esquema y diagramas de una viga continua."""
import matplotlib.pyplot as plt
import numpy as np


def graficar(viga, archivo=None, mostrar=True):
    """Esquema de la viga con sus cargas y diagramas de V, M y flecha.

    Args:
        viga: ``VigaContinua`` ya resuelta (``viga.resolver()``).
        archivo: ruta para guardar la imagen (opcional).
        mostrar: si es True, abre la ventana del gráfico.
    """
    fig, ax = plt.subplots(
        4, 1, figsize=(10, 10), sharex=True,
        gridspec_kw={"height_ratios": [0.9, 1.2, 1.2, 1.2]})

    # Esquema de la viga -----------------------------------------------
    e = ax[0]
    L_total = viga.x_nudos[-1]
    e.plot([0, L_total], [0, 0], color="black", lw=4)
    marcador = {"empotrado": "s", "articulado": "^"}
    for xn, tipo in zip(viga.x_nudos, viga.apoyos):
        if tipo != "libre":
            e.plot(xn, -0.12, marcador[tipo], color="tab:blue", ms=12)
    for t, x0 in zip(viga.tramos, viga.x_nudos[:-1]):
        if t.w_total > 0:
            for xa in np.linspace(x0, x0 + t.L, 9):
                e.annotate("", xy=(xa, 0.05), xytext=(xa, 0.45),
                           arrowprops=dict(arrowstyle="->", color="tab:red"))
            e.text(x0 + 0.25 * t.L, 0.55, f"w = {t.w_total:.1f} kN/m",
                   ha="center", color="tab:red", fontsize=9)
        for a, P in t.puntuales:
            e.annotate("", xy=(x0 + a, 0.05), xytext=(x0 + a, 0.8),
                       arrowprops=dict(arrowstyle="->", color="tab:green",
                                       lw=2))
            e.text(x0 + a, 0.85, f"{P:g} kN", ha="center",
                   color="tab:green", fontsize=9)
    for nudo, (Pn, _) in viga.cargas_nodales.items():
        if Pn:
            xn = viga.x_nudos[nudo]
            e.annotate("", xy=(xn, 0.05), xytext=(xn, 0.8),
                       arrowprops=dict(arrowstyle="->", color="tab:green",
                                       lw=2))
            e.text(xn, 0.85, f"{Pn:g} kN", ha="center",
                   color="tab:green", fontsize=9)
    e.set_ylim(-0.4, 1.1)
    e.axis("off")

    # Diagramas --------------------------------------------------------
    x = np.concatenate([r["x"] for r in viga.resultados])
    V = np.concatenate([r["V"] for r in viga.resultados])
    M = np.concatenate([r["M"] for r in viga.resultados])
    v = np.concatenate([r["v"] for r in viga.resultados]) * 1000

    for a, y, etiqueta, titulo, color in [
            (ax[1], V, "V [kN]", "Cortante", "tab:orange"),
            (ax[2], M, "M [kN·m]", "Momento flector (+ tracciona la "
             "fibra inferior; eje invertido)", "tab:blue"),
            (ax[3], v, "v [mm]", "Flecha (− = hacia abajo)", "tab:purple")]:
        a.plot(x, y, color=color)
        a.fill_between(x, y, 0, color=color, alpha=0.2)
        a.axhline(0, color="black", lw=0.8)
        for xn in viga.x_nudos:
            a.axvline(xn, color="gray", lw=0.5, ls=":")
        a.set_ylabel(etiqueta)
        a.set_title(titulo, fontsize=10, loc="left")
        a.grid(alpha=0.3)
    ax[2].invert_yaxis()
    ax[3].set_xlabel("x [m]")

    fig.tight_layout()
    if archivo:
        fig.savefig(archivo, dpi=150)
    if mostrar:
        plt.show()
    return fig
