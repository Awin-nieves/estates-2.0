"""Persistencia de proyectos y cálculos en SQLite.

Esquema (2 tablas relacionadas por llave foránea):

    proyectos(id, nombre, descripcion, creado_en)
    calculos(id, proyecto_id -> proyectos.id, nombre, creado_en,
             entrada_json, resultado_json)

``entrada_json`` guarda los datos crudos del ensayo (tamices, fondo,
Atterberg) y ``resultado_json`` guarda la curva y las clasificaciones, para
poder reabrir un cálculo sin tener que recalcular ni depender de que el
modelo no haya cambiado.

Todas las consultas usan marcadores ``?`` (nunca concatenación de
cadenas), y las tablas se crean solas la primera vez que se usa la base de
datos (``CREATE TABLE IF NOT EXISTS``).
"""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

RUTA_BD_DEFECTO = Path(__file__).resolve().parents[1] / "granulometria.db"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    creado_en   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calculos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id     INTEGER NOT NULL,
    nombre          TEXT NOT NULL,
    creado_en       TEXT NOT NULL,
    entrada_json    TEXT NOT NULL,
    resultado_json  TEXT NOT NULL,
    FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_calculos_proyecto ON calculos(proyecto_id);
"""


@dataclass
class Proyecto:
    id: int
    nombre: str
    descripcion: str
    creado_en: str


@dataclass
class Calculo:
    id: int
    proyecto_id: int
    nombre: str
    creado_en: str
    entrada: dict
    resultado: dict


class BaseDatos:
    """Envoltorio delgado sobre sqlite3 con el CRUD que necesita la app.

    Uso:
        bd = BaseDatos()                   # usa granulometria.db por defecto
        pid = bd.crear_proyecto("Sondeo 1")
        cid = bd.guardar_calculo(pid, "Muestra A", entrada, resultado)
        bd.listar_calculos(pid)
    """

    def __init__(self, ruta=RUTA_BD_DEFECTO):
        self.ruta = str(ruta)
        with self._conectar() as con:
            con.executescript(_ESQUEMA)

    @contextmanager
    def _conectar(self):
        con = sqlite3.connect(self.ruta)
        con.execute("PRAGMA foreign_keys = ON")
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Proyectos
    # ------------------------------------------------------------------
    def crear_proyecto(self, nombre, descripcion=""):
        """Crea un proyecto y devuelve su id."""
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conectar() as con:
            cur = con.execute(
                "INSERT INTO proyectos (nombre, descripcion, creado_en) "
                "VALUES (?, ?, ?)", (nombre, descripcion, ahora))
            return cur.lastrowid

    def listar_proyectos(self, filtro_nombre=None):
        """Lista los proyectos, más reciente primero. ``filtro_nombre``
        filtra por coincidencia parcial (``LIKE``), con marcador ``?``."""
        with self._conectar() as con:
            if filtro_nombre:
                filas = con.execute(
                    "SELECT * FROM proyectos WHERE nombre LIKE ? "
                    "ORDER BY creado_en DESC",
                    (f"%{filtro_nombre}%",)).fetchall()
            else:
                filas = con.execute(
                    "SELECT * FROM proyectos ORDER BY creado_en DESC"
                ).fetchall()
            return [Proyecto(**dict(f)) for f in filas]

    def eliminar_proyecto(self, proyecto_id):
        """Elimina un proyecto y, en cascada, sus cálculos."""
        with self._conectar() as con:
            con.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    def guardar_calculo(self, proyecto_id, nombre, entrada, resultado):
        """Guarda un cálculo (entrada y resultado como JSON) y devuelve su
        id. ``entrada`` y ``resultado`` deben ser dicts serializables."""
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conectar() as con:
            cur = con.execute(
                "INSERT INTO calculos "
                "(proyecto_id, nombre, creado_en, entrada_json, "
                " resultado_json) VALUES (?, ?, ?, ?, ?)",
                (proyecto_id, nombre, ahora, json.dumps(entrada),
                 json.dumps(resultado)))
            return cur.lastrowid

    def listar_calculos(self, proyecto_id=None, filtro_nombre=None):
        """Lista cálculos, más reciente primero. Si ``proyecto_id`` es
        ``None``, lista los de todos los proyectos."""
        condiciones, parametros = [], []
        if proyecto_id is not None:
            condiciones.append("proyecto_id = ?")
            parametros.append(proyecto_id)
        if filtro_nombre:
            condiciones.append("nombre LIKE ?")
            parametros.append(f"%{filtro_nombre}%")
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with self._conectar() as con:
            filas = con.execute(
                f"SELECT * FROM calculos {where} ORDER BY creado_en DESC",
                parametros).fetchall()
            return [_fila_a_calculo(f) for f in filas]

    def obtener_calculo(self, calculo_id):
        """Devuelve un :class:`Calculo` por id, o ``None`` si no existe."""
        with self._conectar() as con:
            fila = con.execute(
                "SELECT * FROM calculos WHERE id = ?", (calculo_id,)
            ).fetchone()
            return _fila_a_calculo(fila) if fila else None

    def eliminar_calculo(self, calculo_id):
        with self._conectar() as con:
            con.execute("DELETE FROM calculos WHERE id = ?", (calculo_id,))


def _fila_a_calculo(fila):
    d = dict(fila)
    return Calculo(id=d["id"], proyecto_id=d["proyecto_id"],
                   nombre=d["nombre"], creado_en=d["creado_en"],
                   entrada=json.loads(d["entrada_json"]),
                   resultado=json.loads(d["resultado_json"]))
