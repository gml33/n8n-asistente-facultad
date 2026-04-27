"""Sincronización del calendario ICS del campus con la tabla de entregas."""

import logging
from datetime import date
from datetime import datetime
from datetime import time
import re
import unicodedata

import requests
from icalendar import Calendar

from .extensions import bd
from .models import Entrega
from .models import Materia

logger = logging.getLogger(__name__)


def _to_datetime(valor):
    """Normaliza fechas del parser ICS a `datetime` naive local."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    if isinstance(valor, date):
        return datetime.combine(valor, time(hour=23, minute=59))
    return None


def _tipo_desde_titulo(titulo):
    """Infiere tipo de entrega a partir del título del evento."""
    texto = (titulo or "").lower()
    if "trabajo práctico" in texto or "trabajo practico" in texto or "tp" in texto:
        return "trabajo practico"
    if "parcial" in texto:
        return "parcial"
    if "lectura" in texto:
        return "lectura"
    if "cuestionario" in texto or "quiz" in texto:
        return "cuestionario"
    return "otro"


def _normalizar_texto(texto):
    """Normaliza strings para matching tolerante de materias."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _resolver_materia_evento(evento, materias_por_normalizado):
    """Mapea un evento importado a una materia existente o probable."""
    bloques = [evento.get("titulo", ""), evento.get("detalle", "")]
    bloques.extend(evento.get("categorias", []))
    texto = _normalizar_texto(" ".join([bloque for bloque in bloques if bloque]))

    mejor_nombre = None
    mejor_longitud = -1
    for nombre_normalizado, nombre_real in materias_por_normalizado.items():
        if not nombre_normalizado:
            continue
        if re.search(rf"\b{re.escape(nombre_normalizado)}\b", texto):
            if len(nombre_normalizado) > mejor_longitud:
                mejor_longitud = len(nombre_normalizado)
                mejor_nombre = nombre_real

    if mejor_nombre:
        return mejor_nombre

    categorias = [categoria for categoria in evento.get("categorias", []) if str(categoria).strip()]
    if categorias:
        return str(categorias[0]).strip()

    return "Campus UNDEF"


def _obtener_eventos_ics(url):
    """Descarga y parsea el feed ICS remoto del campus."""
    respuesta = requests.get(url, timeout=30)
    respuesta.raise_for_status()
    calendario = Calendar.from_ical(respuesta.content)

    eventos = []
    for componente in calendario.walk("VEVENT"):
        uid = str(componente.get("uid", "")).strip()
        if not uid:
            continue

        titulo = str(componente.get("summary", "Entrega Campus")).strip() or "Entrega Campus"
        descripcion = str(componente.get("description", "")).strip() or None
        inicio = _to_datetime(componente.decoded("dtstart", None))
        if not inicio:
            continue

        categorias = componente.get("categories")
        categorias_lista = [str(valor).strip() for valor in categorias.cats] if categorias else []

        eventos.append(
            {
                "uid": uid,
                "titulo": titulo,
                "detalle": descripcion,
                "fecha_entrega": inicio,
                "categorias": categorias_lista,
                "tipo": _tipo_desde_titulo(titulo),
            }
        )

    return eventos


def sincronizar_campus(url, usuario_id=None):
    """Importa/actualiza/elimina entregas de origen `campus`."""
    if not url:
        logger.info("Sincronización de campus omitida: CAMPUS_CALENDARIO_URL vacío")
        return {"importados": 0, "actualizados": 0, "eliminados": 0, "total_eventos": 0}

    eventos = _obtener_eventos_ics(url)
    consulta_materias = Materia.query
    if usuario_id is not None:
        consulta_materias = consulta_materias.filter(Materia.usuario_id == usuario_id)
    materias_existentes = consulta_materias.order_by(Materia.nombre.asc()).all()
    materias_por_normalizado = {
        _normalizar_texto(materia.nombre): materia.nombre for materia in materias_existentes
    }
    ids_evento = set()
    importados = 0
    actualizados = 0
    materias_creadas = 0

    for evento in eventos:
        ids_evento.add(evento["uid"])
        nombre_materia = _resolver_materia_evento(evento, materias_por_normalizado)
        clave_materia = _normalizar_texto(nombre_materia)
        if clave_materia and clave_materia not in materias_por_normalizado:
            materia_nueva = Materia(usuario_id=usuario_id, nombre=nombre_materia)
            bd.session.add(materia_nueva)
            materias_por_normalizado[clave_materia] = nombre_materia
            materias_creadas += 1

        consulta_entrega = Entrega.query.filter_by(origen="campus", origen_evento_id=evento["uid"])
        if usuario_id is not None:
            consulta_entrega = consulta_entrega.filter(Entrega.usuario_id == usuario_id)
        entrega = consulta_entrega.first()
        if not entrega:
            entrega = Entrega(
                usuario_id=usuario_id,
                materia=nombre_materia,
                titulo=evento["titulo"],
                tipo=evento["tipo"],
                fecha_entrega=evento["fecha_entrega"],
                prioridad="media",
                estado="pendiente",
                detalle=evento["detalle"],
                origen="campus",
                origen_evento_id=evento["uid"],
            )
            bd.session.add(entrega)
            importados += 1
            continue

        entrega.materia = nombre_materia
        entrega.titulo = evento["titulo"]
        entrega.tipo = evento["tipo"]
        entrega.fecha_entrega = evento["fecha_entrega"]
        entrega.detalle = evento["detalle"]
        actualizados += 1

    eliminados = 0
    consulta_campus = Entrega.query.filter_by(origen="campus")
    if usuario_id is not None:
        consulta_campus = consulta_campus.filter(Entrega.usuario_id == usuario_id)
    entregas_campus = consulta_campus.all()
    for entrega in entregas_campus:
        # Solo elimina pendientes que ya no figuran en el calendario remoto.
        if entrega.origen_evento_id and entrega.origen_evento_id not in ids_evento:
            if entrega.estado == "entregado":
                continue
            bd.session.delete(entrega)
            eliminados += 1

    bd.session.commit()
    return {
        "importados": importados,
        "actualizados": actualizados,
        "eliminados": eliminados,
        "materias_creadas": materias_creadas,
        "total_eventos": len(eventos),
    }
