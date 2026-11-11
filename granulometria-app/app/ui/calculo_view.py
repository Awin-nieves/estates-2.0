"""Vista "Cálculo": formulario de tamizado + Atterberg, resultados y
botones para guardar y generar la memoria de cálculo."""
import asyncio
import csv
import io
import itertools
from pathlib import Path

import flet as ft

from .. import servicio
from ..modelo import TAMICES_ASTM

_contador_imagenes = itertools.count()

# Tamices por defecto (serie ASTM habitual para suelos granulares con finos)
TAMICES_DEFECTO = ["2\"", "1 1/2\"", "1\"", "3/4\"", "1/2\"", "3/8\"",
                   "No.4", "No.10", "No.20", "No.40", "No.60", "No.100",
                   "No.200"]


def build_calculo_view(page: ft.Page, bd, carpeta_assets: Path):
    """Construye la vista de cálculo. ``carpeta_assets`` es la carpeta
    ``assets/`` de la app (ahí se guarda la imagen de la curva para poder
    mostrarla con ``ft.Image``)."""

    estado = {"resultado": None, "tamices": None, "peso_fondo": 0.0,
              "verificacion": None}

    # ------------------------------------------------------------------
    # Proyecto
    # ------------------------------------------------------------------
    proyecto_dd = ft.Dropdown(label="Proyecto", width=320, options=[
        ft.dropdown.Option(key=str(p.id), text=p.nombre)
        for p in bd.listar_proyectos()])

    nuevo_proyecto_tf = ft.TextField(label="Nuevo proyecto", width=220)

    def refrescar_proyectos(seleccionar_id=None):
        proyecto_dd.options = [
            ft.dropdown.Option(key=str(p.id), text=p.nombre)
            for p in bd.listar_proyectos()]
        if seleccionar_id is not None:
            proyecto_dd.value = str(seleccionar_id)
        page.update()

    def crear_proyecto(e):
        nombre = (nuevo_proyecto_tf.value or "").strip()
        if not nombre:
            mostrar_mensaje("Escribe un nombre para el proyecto.", error=True)
            return
        pid = bd.crear_proyecto(nombre)
        nuevo_proyecto_tf.value = ""
        refrescar_proyectos(seleccionar_id=pid)
        mostrar_mensaje(f"Proyecto \"{nombre}\" creado.")

    crear_proyecto_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE,
                                       tooltip="Crear proyecto",
                                       on_click=crear_proyecto)

    # ------------------------------------------------------------------
    # Especificación (INVIAS, tuberías, propias)
    # ------------------------------------------------------------------
    try:
        especificaciones = servicio.especificaciones_disponibles()
        aviso_espec = ""
    except ValueError as exc:               # JSON propio mal formado
        especificaciones = servicio.especificaciones_disponibles(
            ruta_json="__no_existe__")
        aviso_espec = f"especificaciones_propias.json: {exc}"
    SIN_ESPEC = "ninguna"
    espec_dd = ft.Dropdown(
        label="Verificar contra especificación", width=420,
        value=SIN_ESPEC,
        options=[ft.dropdown.Option(key=SIN_ESPEC, text="(ninguna)")] + [
            ft.dropdown.Option(
                key=e.codigo,
                text=f"{e.codigo} — {e.nombre}"
                     + ("" if e.verificada else " [propia]"))
            for e in especificaciones.values()])

    # ------------------------------------------------------------------
    # Datos del cálculo
    # ------------------------------------------------------------------
    nombre_calculo_tf = ft.TextField(label="Nombre de la muestra",
                                     hint_text="p. ej. Apique 1 - M2",
                                     width=320)
    autor_tf = ft.TextField(label="Autor", width=320)

    # Filas de tamices: nombre -> TextField de retenido (g)
    campos_retenido = {}
    filas_tamices_ui = []
    for nombre in TAMICES_DEFECTO:
        abertura = TAMICES_ASTM[nombre]
        campo = ft.TextField(value="0", width=110, text_align=ft.TextAlign.RIGHT,
                             keyboard_type=ft.KeyboardType.NUMBER)
        campos_retenido[nombre] = campo
        filas_tamices_ui.append(
            ft.Row([
                ft.Container(ft.Text(nombre), width=90),
                ft.Container(ft.Text(f"{abertura:g} mm"), width=90),
                campo,
                ft.Text("g"),
            ]))

    peso_fondo_tf = ft.TextField(label="Masa en el fondo (g)", value="0",
                                 width=200,
                                 keyboard_type=ft.KeyboardType.NUMBER)

    LL_tf = ft.TextField(label="LL (%) — opcional", width=200,
                         keyboard_type=ft.KeyboardType.NUMBER)
    LP_tf = ft.TextField(label="LP (%) — opcional", width=200,
                         keyboard_type=ft.KeyboardType.NUMBER)

    # ------------------------------------------------------------------
    # Importar CSV
    # ------------------------------------------------------------------
    file_picker = ft.FilePicker()

    def _nombre_columna(fieldnames, candidatos):
        for c in candidatos:
            for f in fieldnames:
                if f.strip().lower() == c:
                    return f
        return None

    async def importar_csv(e):
        archivos = await file_picker.pick_files(
            dialog_title="Selecciona el CSV del ensayo",
            allowed_extensions=["csv"])
        if not archivos:
            return
        ruta = archivos[0].path
        if not ruta:
            mostrar_mensaje("No se pudo leer el archivo seleccionado.",
                           error=True)
            return
        try:
            with open(ruta, newline="", encoding="utf-8-sig") as f:
                lector = csv.DictReader(f)
                col_tamiz = _nombre_columna(lector.fieldnames,
                                            ["tamiz", "nombre"])
                col_retenido = _nombre_columna(
                    lector.fieldnames, ["retenido_g", "retenido", "peso_g"])
                if not col_tamiz or not col_retenido:
                    mostrar_mensaje(
                        "El CSV necesita una columna de tamiz (tamiz/"
                        "nombre) y una de masa retenida (retenido_g/"
                        "retenido/peso_g).", error=True)
                    return
                actualizados = 0
                for fila in lector:
                    nombre = fila[col_tamiz].strip()
                    if nombre in campos_retenido:
                        campos_retenido[nombre].value = fila[col_retenido].strip()
                        actualizados += 1
        except (OSError, csv.Error) as exc:
            mostrar_mensaje(f"No se pudo leer el CSV: {exc}", error=True)
            return
        page.update()
        mostrar_mensaje(f"Se actualizaron {actualizados} tamices desde el CSV.")

    importar_btn = ft.OutlinedButton(
        "Importar CSV", icon=ft.Icons.UPLOAD_FILE,
        on_click=lambda e: asyncio.create_task(importar_csv(e)))

    # ------------------------------------------------------------------
    # Resultados
    # ------------------------------------------------------------------
    resultado_texto = ft.Column(visible=False)
    verificacion_col = ft.Column(visible=False, spacing=2)
    imagen_curva = ft.Image(src="", visible=False, width=560)
    mensaje_texto = ft.Text("", color=ft.Colors.ERROR)

    def mostrar_mensaje(texto, error=False):
        mensaje_texto.value = texto
        mensaje_texto.color = ft.Colors.ERROR if error else ft.Colors.GREEN
        page.update()

    def leer_filas_tamices():
        return [{"nombre": n, "abertura_mm": TAMICES_ASTM[n],
                 "retenido_g": campo.value}
                for n, campo in campos_retenido.items()]

    def leer_LL_LP():
        ll = LL_tf.value.strip() if LL_tf.value else ""
        lp = LP_tf.value.strip() if LP_tf.value else ""
        if ll and lp:
            return float(ll), float(lp)
        return None, None

    def codigo_espec():
        v = espec_dd.value
        return None if not v or v == SIN_ESPEC else v

    def mostrar_verificacion(resultado):
        codigo = codigo_espec()
        if codigo is None:
            verificacion_col.visible = False
            estado["verificacion"] = None
            return
        ver = servicio.verificar_especificacion(resultado, codigo)
        estado["verificacion"] = ver
        color_ok, color_mal = ft.Colors.GREEN, ft.Colors.ERROR
        filas = [ft.DataRow(cells=[
            ft.DataCell(ft.Text(f"{f.tamiz} ({f.abertura_mm:g} mm)")),
            ft.DataCell(ft.Text("—" if f.origen == "sin dato"
                                else f"{f.pasa:.1f}")),
            ft.DataCell(ft.Text(f"{f.minimo:g} – {f.maximo:g}")),
            ft.DataCell(ft.Text(
                "Sin dato" if f.origen == "sin dato" else
                ("Cumple" if f.cumple else "No cumple")
                + (f" ({f.origen})" if f.origen in ("interpolado", "100 %")
                   else ""),
                color=(None if f.origen == "sin dato" else
                       color_ok if f.cumple else color_mal))),
        ]) for f in ver.filas]
        controles = [
            ft.Text(f"Verificación: {ver.especificacion.codigo}",
                    weight=ft.FontWeight.BOLD, size=16),
            ft.Text(f"Fuente: {ver.especificacion.fuente}", size=12),
            ft.DataTable(columns=[
                ft.DataColumn(ft.Text("Tamiz")),
                ft.DataColumn(ft.Text("% pasa")),
                ft.DataColumn(ft.Text("Franja")),
                ft.DataColumn(ft.Text("Resultado"))], rows=filas)]
        for texto, ok in ver.criterios:
            controles.append(ft.Text(
                f"{texto} — {'Cumple' if ok else 'No cumple'}",
                color=color_ok if ok else color_mal))
        controles.append(ft.Text(
            "La muestra CUMPLE la especificación." if ver.cumple
            else "La muestra NO CUMPLE la especificación.",
            weight=ft.FontWeight.BOLD,
            color=color_ok if ver.cumple else color_mal))
        if not ver.especificacion.verificada:
            controles.append(ft.Text(
                "Especificación propia: no verificada contra una norma "
                "publicada.", size=12, italic=True))
        verificacion_col.controls = controles
        verificacion_col.visible = True

    def calcular(e):
        mensaje_texto.value = ""
        try:
            peso_fondo = float(peso_fondo_tf.value or 0)
            LL, LP = leer_LL_LP()
            resultado = servicio.calcular(leer_filas_tamices(), peso_fondo,
                                          LL, LP)
        except ValueError as exc:
            resultado_texto.visible = False
            verificacion_col.visible = False
            imagen_curva.visible = False
            mostrar_mensaje(str(exc), error=True)
            return

        estado["resultado"] = resultado
        estado["tamices"] = servicio.construir_tamices(leer_filas_tamices())
        estado["peso_fondo"] = peso_fondo

        c = resultado.curva
        resultado_texto.controls = [
            ft.Text("Resultados", weight=ft.FontWeight.BOLD, size=16),
            ft.Text(f"D10 = {c.D10:.4f} mm    D30 = {c.D30:.4f} mm    "
                   f"D60 = {c.D60:.4f} mm"),
            ft.Text(f"Cu = {c.Cu:.2f}      Cc = {c.Cc:.2f}"),
            ft.Text(f"Grava: {c.pct_grava:.1f} %    Arena: "
                   f"{c.pct_arena:.1f} %    Finos: {c.pct_finos:.1f} %"),
            ft.Text(f"USCS: {resultado.uscs_simbolo} — "
                   f"{resultado.uscs_descripcion}",
                   weight=ft.FontWeight.BOLD),
            ft.Text(
                f"AASHTO: {resultado.aashto.grupo} (GI = "
                f"{resultado.aashto.indice_grupo}) — "
                f"{resultado.aashto.descripcion}"
                if resultado.aashto else
                "AASHTO: no calculado (se necesitan LL y LP)",
                weight=ft.FontWeight.BOLD),
        ]
        resultado_texto.visible = True
        mostrar_verificacion(resultado)

        # Gráfica: se guarda en assets/ con nombre único para que
        # ft.Image la pueda mostrar por ruta relativa.
        from ..graficas import graficar_curva_granulometrica
        nombre_img = f"curva_{next(_contador_imagenes)}.png"
        graficar_curva_granulometrica(
            c, titulo=nombre_calculo_tf.value or "Curva granulométrica",
            archivo=str(carpeta_assets / nombre_img),
            especificacion=(estado["verificacion"].especificacion
                            if estado.get("verificacion") else None))
        imagen_curva.src = nombre_img
        imagen_curva.visible = True

        mostrar_mensaje("Cálculo realizado.")

    def guardar(e):
        if estado["resultado"] is None:
            mostrar_mensaje("Primero presiona \"Calcular\".", error=True)
            return
        if not proyecto_dd.value:
            mostrar_mensaje("Selecciona o crea un proyecto.", error=True)
            return
        if not (nombre_calculo_tf.value or "").strip():
            mostrar_mensaje("Escribe un nombre para la muestra.", error=True)
            return
        try:
            peso_fondo = float(peso_fondo_tf.value or 0)
            LL, LP = leer_LL_LP()
            _, cid = servicio.calcular_y_guardar(
                bd, int(proyecto_dd.value), nombre_calculo_tf.value.strip(),
                leer_filas_tamices(), peso_fondo, LL, LP,
                especificacion=codigo_espec())
        except ValueError as exc:
            mostrar_mensaje(str(exc), error=True)
            return
        mostrar_mensaje(f"Cálculo guardado (id {cid}).")

    def generar_memoria(e):
        if estado["resultado"] is None:
            mostrar_mensaje("Primero presiona \"Calcular\".", error=True)
            return
        nombre_proyecto = next(
            (o.text for o in proyecto_dd.options
            if o.key == proyecto_dd.value), "Sin proyecto")
        ruta = servicio.generar_memoria(
            estado["resultado"], nombre_proyecto,
            nombre_calculo_tf.value.strip() or "calculo",
            autor_tf.value.strip() or "—", estado["tamices"],
            estado["peso_fondo"], verificacion=estado.get("verificacion"))
        mostrar_mensaje(f"Memoria generada en: {ruta}")

    calcular_btn = ft.FilledButton("Calcular", icon=ft.Icons.CALCULATE,
                                   on_click=calcular)
    guardar_btn = ft.OutlinedButton("Guardar", icon=ft.Icons.SAVE,
                                    on_click=guardar)
    memoria_btn = ft.OutlinedButton("Generar memoria (.docx)",
                                    icon=ft.Icons.DESCRIPTION,
                                    on_click=generar_memoria)

    def ir_a_historial(e):
        asyncio.create_task(page.push_route("/historial"))

    return ft.View(
        route="/",
        services=[file_picker],
        appbar=ft.AppBar(
            title=ft.Text("Granulometría y clasificación de suelos"),
            actions=[ft.TextButton("Historial", icon=ft.Icons.HISTORY,
                                   on_click=ir_a_historial)]),
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=14,
                    controls=[
                        ft.Row([proyecto_dd, crear_proyecto_btn,
                               nuevo_proyecto_tf]),
                        ft.Row([nombre_calculo_tf, autor_tf]),
                        espec_dd,
                        ft.Text(aviso_espec, color=ft.Colors.ERROR,
                                visible=bool(aviso_espec)),
                        ft.Text("Tamizado", weight=ft.FontWeight.BOLD),
                        ft.Column(filas_tamices_ui, spacing=4),
                        ft.Row([peso_fondo_tf, importar_btn]),
                        ft.Text("Límites de Atterberg (fracción fina)",
                               weight=ft.FontWeight.BOLD),
                        ft.Row([LL_tf, LP_tf]),
                        ft.Row([calcular_btn, guardar_btn, memoria_btn]),
                        mensaje_texto,
                        resultado_texto,
                        verificacion_col,
                        imagen_curva,
                    ]))
        ])
