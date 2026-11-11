"""Vista "Historial": lista de cálculos guardados, con búsqueda, ver
detalle, regenerar memoria y eliminar."""
import asyncio

import flet as ft

from .. import servicio


def build_historial_view(page: ft.Page, bd):
    proyecto_dd = ft.Dropdown(
        label="Filtrar por proyecto", width=280,
        options=[ft.dropdown.Option(key="", text="Todos los proyectos")] + [
            ft.dropdown.Option(key=str(p.id), text=p.nombre)
            for p in bd.listar_proyectos()])
    proyecto_dd.value = ""
    buscar_tf = ft.TextField(label="Buscar por nombre", width=240)

    tabla = ft.DataTable(columns=[
        ft.DataColumn(ft.Text("Muestra")),
        ft.DataColumn(ft.Text("Fecha (UTC)")),
        ft.DataColumn(ft.Text("USCS")),
        ft.DataColumn(ft.Text("AASHTO")),
        ft.DataColumn(ft.Text("")),
    ], rows=[])

    mensaje_texto = ft.Text("")

    def mostrar_mensaje(texto, error=False):
        mensaje_texto.value = texto
        mensaje_texto.color = ft.Colors.ERROR if error else ft.Colors.GREEN
        page.update()

    def cargar(e=None):
        pid = int(proyecto_dd.value) if proyecto_dd.value else None
        calculos = bd.listar_calculos(proyecto_id=pid,
                                      filtro_nombre=buscar_tf.value or None)
        filas = []
        for c in calculos:
            filas.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(c.nombre)),
                ft.DataCell(ft.Text(c.creado_en[:16].replace("T", " "))),
                ft.DataCell(ft.Text(c.resultado.get("uscs_simbolo", "—"))),
                ft.DataCell(ft.Text(c.resultado.get("aashto_grupo", "—"))),
                ft.DataCell(ft.Row([
                    ft.IconButton(icon=ft.Icons.VISIBILITY,
                                 tooltip="Ver detalle / generar memoria",
                                 on_click=lambda e, c=c: ver_detalle(c)),
                    ft.IconButton(icon=ft.Icons.DELETE,
                                 tooltip="Eliminar",
                                 icon_color=ft.Colors.ERROR,
                                 on_click=lambda e, c=c: eliminar(c)),
                ])),
            ]))
        tabla.rows = filas
        page.update()

    def eliminar(calculo):
        bd.eliminar_calculo(calculo.id)
        mostrar_mensaje(f"Cálculo \"{calculo.nombre}\" eliminado.")
        cargar()

    def ver_detalle(calculo):
        resultado = servicio.recalcular_desde_historial(calculo)
        c = resultado.curva
        codigo = calculo.entrada.get("especificacion")
        try:
            verificacion = (servicio.verificar_especificacion(resultado,
                                                              codigo)
                            if codigo else None)
        except ValueError:       # p. ej. se borró la especificación propia
            verificacion = None

        def generar(e):
            proyectos = {p.id: p.nombre for p in bd.listar_proyectos()}
            from ..modelo import Tamiz
            tamices = [Tamiz(t["nombre"], t["abertura_mm"], t["retenido_g"])
                      for t in calculo.entrada["tamices"]]
            ruta = servicio.generar_memoria(
                resultado, proyectos.get(calculo.proyecto_id, "—"),
                calculo.nombre, "—", tamices,
                calculo.entrada["peso_fondo_g"], verificacion=verificacion)
            dialogo.open = False
            page.update()
            mostrar_mensaje(f"Memoria generada en: {ruta}")

        dialogo = ft.AlertDialog(
            title=ft.Text(calculo.nombre),
            content=ft.Column(tight=True, controls=[
                ft.Text(f"D10 = {c.D10:.4f} mm   D30 = {c.D30:.4f} mm   "
                       f"D60 = {c.D60:.4f} mm"),
                ft.Text(f"Cu = {c.Cu:.2f}   Cc = {c.Cc:.2f}"),
                ft.Text(f"Grava {c.pct_grava:.1f} % · Arena "
                       f"{c.pct_arena:.1f} % · Finos {c.pct_finos:.1f} %"),
                ft.Text(f"USCS: {resultado.uscs_simbolo} — "
                       f"{resultado.uscs_descripcion}"),
                ft.Text(
                    f"AASHTO: {resultado.aashto.grupo} (GI="
                    f"{resultado.aashto.indice_grupo})"
                    if resultado.aashto else "AASHTO: no calculado"),
                ft.Text(
                    f"Especificación {codigo}: "
                    + ("CUMPLE" if verificacion.cumple else "NO CUMPLE")
                    if verificacion else
                    (f"Especificación {codigo}: no disponible"
                     if codigo else "Sin especificación"),
                    weight=ft.FontWeight.BOLD),
            ]),
            actions=[
                ft.TextButton("Generar memoria (.docx)", on_click=generar),
                ft.TextButton("Cerrar",
                             on_click=lambda e: cerrar_dialogo()),
            ])

        def cerrar_dialogo():
            dialogo.open = False
            page.update()

        page.show_dialog(dialogo)

    proyecto_dd.on_change = cargar
    buscar_tf.on_change = cargar
    cargar()

    def ir_a_calculo(e):
        asyncio.create_task(page.push_route("/"))

    return ft.View(
        route="/historial",
        appbar=ft.AppBar(
            title=ft.Text("Historial de cálculos"),
            actions=[ft.TextButton("Nuevo cálculo", icon=ft.Icons.CALCULATE,
                                   on_click=ir_a_calculo)]),
        controls=[
            ft.Container(padding=20, content=ft.Column(
                scroll=ft.ScrollMode.AUTO, spacing=14, controls=[
                    ft.Row([proyecto_dd, buscar_tf]),
                    mensaje_texto,
                    ft.Row([tabla], scroll=ft.ScrollMode.AUTO),
                ]))
        ])
