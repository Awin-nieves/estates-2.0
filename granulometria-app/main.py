"""Punto de entrada de la aplicación. Ejecutar con:

    python main.py
    # o
    flet run

Arma la ventana, conecta la base de datos SQLite (se crea sola la primera
vez) y navega entre las vistas "Cálculo" (/) e "Historial" (/historial).
"""
import asyncio
from pathlib import Path

import flet as ft

from app.db import BaseDatos
from app.ui.calculo_view import build_calculo_view
from app.ui.historial_view import build_historial_view

RAIZ = Path(__file__).resolve().parent
CARPETA_ASSETS = RAIZ / "assets"


def main(page: ft.Page):
    page.title = "Granulometría y clasificación de suelos"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 980
    page.window.height = 800

    CARPETA_ASSETS.mkdir(exist_ok=True)
    bd = BaseDatos()

    def route_change(e=None):
        page.views.clear()
        if page.route == "/historial":
            page.views.append(build_historial_view(page, bd))
        else:
            page.views.append(build_calculo_view(page, bd, CARPETA_ASSETS))
        page.update()

    async def view_pop(e):
        if e.view is not None and len(page.views) > 1:
            page.views.remove(e.view)
            await page.push_route(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    route_change()


if __name__ == "__main__":
    ft.run(main, assets_dir=str(CARPETA_ASSETS))
