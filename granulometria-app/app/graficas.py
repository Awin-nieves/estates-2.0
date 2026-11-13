"""Curva granulométrica (Matplotlib), para mostrar en la app y reutilizar
en la memoria de cálculo."""
import matplotlib
matplotlib.use("Agg")                                  # sin ventana: Flet y
import matplotlib.pyplot as plt                        # docx la insertan como imagen


def graficar_curva_granulometrica(curva, titulo="Curva granulométrica",
                                   archivo=None, especificacion=None):
    """Dibuja la curva granulométrica en papel semi-logarítmico.

    Eje x: abertura del tamiz [mm], escala logarítmica (como en el papel
    semi-log tradicional). Eje y: % que pasa, escala lineal. Marca D10,
    D30 y D60 con líneas guía.

    Args:
        curva: :class:`app.modelo.CurvaGranulometrica` ya calculada.
        titulo: título de la gráfica.
        archivo: si se da, guarda la imagen en esa ruta (PNG).
        especificacion: :class:`app.especificaciones.Especificacion`
            opcional; si se da, se sombrea su franja granulométrica.

    Returns:
        La figura de Matplotlib (``archivo`` ya quedó guardado si se dio).
    """
    fig, ax = plt.subplots(figsize=(7.5, 4.8))

    ax.plot(curva.abertura_mm, curva.pasa, marker="o", color="tab:blue",
           lw=1.8, label="Curva granulométrica")
    if especificacion is not None:
        abs_ = sorted(especificacion.franja)
        minimos = [especificacion.franja[a][0] for a in abs_]
        maximos = [especificacion.franja[a][1] for a in abs_]
        ax.fill_between(abs_, minimos, maximos, color="tab:green", alpha=0.18,
                        label=f"Franja {especificacion.codigo}")
        ax.plot(abs_, minimos, color="tab:green", lw=1.2, ls="--")
        ax.plot(abs_, maximos, color="tab:green", lw=1.2, ls="--")
    ax.set_xscale("log")
    ax.invert_xaxis()                                  # grueso -> fino, izq a der
    ax.set_xlabel("Abertura del tamiz [mm]")
    ax.set_ylabel("% que pasa")
    ax.set_title(titulo)
    ax.set_ylim(0, 100)
    ax.grid(True, which="both", alpha=0.3)

    desplazamientos = {"D10": (-60, 10), "D30": (6, -14), "D60": (6, 8)}
    for D, pasa, etiqueta in [(curva.D10, 10, "D10"),
                              (curva.D30, 30, "D30"),
                              (curva.D60, 60, "D60")]:
        if D is None:       # el % que pasa no está en la curva: no aplica
            continue
        ax.plot([D], [pasa], marker="s", color="tab:red", ms=6, zorder=5)
        ax.annotate(f"{etiqueta} = {D:.3f} mm", xy=(D, pasa),
                   xytext=desplazamientos[etiqueta],
                   textcoords="offset points", fontsize=8,
                   color="tab:red")
        ax.axhline(pasa, color="tab:red", lw=0.5, ls=":", alpha=0.5)

    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    if archivo:
        fig.savefig(archivo, dpi=150)
    return fig
