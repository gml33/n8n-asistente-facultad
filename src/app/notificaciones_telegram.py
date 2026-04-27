"""Motor de envío de resúmenes de pendientes por Telegram."""

import logging
from datetime import datetime
from datetime import timedelta

import requests
from flask import current_app

from .autenticacion import obtener_usuario_actual_id
from .configuracion_notificaciones import _guardar_valor
from .configuracion_notificaciones import obtener_ajustes_notificaciones
from .configuracion_notificaciones import _obtener_valor
from .models import Entrega

logger = logging.getLogger(__name__)


def _debe_enviar_ahora(ajustes, usuario_id=None):
    """Evalúa ventana horaria y frecuencia antes de enviar."""
    if not ajustes["notificaciones_activas"]:
        return False
    token = ajustes["telegram_bot_token"] or current_app.config.get("TOKEN_BOT_TELEGRAM", "")
    if not ajustes["telegram_chat_id"] or not token:
        return False

    ahora = datetime.now()
    try:
        hora_config, minuto_config = ajustes["notificacion_hora"].split(":")
        hora_config = int(hora_config)
        minuto_config = int(minuto_config)
    except Exception:
        hora_config, minuto_config = 8, 0

    if (ahora.hour, ahora.minute) < (hora_config, minuto_config):
        return False

    ultima_envio = obtener_ultima_envio_at(usuario_id)
    if not ultima_envio:
        return True

    horas = max(1, int(ajustes.get("notificacion_frecuencia_horas", 24)))
    horas_efectivas = horas
    return (ahora - ultima_envio) >= timedelta(hours=horas_efectivas)


def _armar_mensaje(entregas, ventana_dias):
    """Construye el texto final enviado al chat de Telegram."""
    encabezado = f"📌 Pendientes próximos {ventana_dias} días\n"
    if not entregas:
        return encabezado + "\nNo hay entregas pendientes en ese período."

    lineas = []
    for entrega in entregas[:20]:
        fecha = entrega.fecha_entrega.strftime("%d/%m %H:%M")
        lineas.append(f"- {fecha} · {entrega.materia} · {entrega.titulo} [{entrega.prioridad}]")
    return encabezado + "\n\n" + "\n".join(lineas)


def obtener_ultima_envio_at(usuario_id=None):
    """Recupera timestamp de último envío exitoso."""
    valor = _obtener_valor("notificacion_ultima_fecha_envio", usuario_id)
    if not valor:
        return None
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    return None


def guardar_ultima_envio_at(fecha_hora, usuario_id=None):
    """Persiste el momento del último envío para respetar frecuencia."""
    if isinstance(fecha_hora, datetime):
        _guardar_valor("notificacion_ultima_fecha_envio", fecha_hora.strftime("%Y-%m-%dT%H:%M:%S"), usuario_id)
        from .extensions import bd

        bd.session.commit()


def enviar_resumen_pendientes_programado(forzar=False, usuario_id=None):
    """Envía resumen de pendientes dentro de la ventana configurada."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    ajustes = obtener_ajustes_notificaciones(usuario_id)
    if not forzar and not _debe_enviar_ahora(ajustes, usuario_id):
        return {"enviado": False, "motivo": "condiciones_no_cumplidas"}

    ahora = datetime.now()
    ventana = max(1, int(ajustes["notificacion_ventana_dias"]))
    limite = ahora + timedelta(days=ventana)

    entregas = (
        Entrega.query.filter(
            Entrega.usuario_id == usuario_id,
            Entrega.estado != "entregado",
            Entrega.fecha_entrega >= ahora,
            Entrega.fecha_entrega <= limite,
        )
        .order_by(Entrega.fecha_entrega.asc())
        .all()
    )

    mensaje = _armar_mensaje(entregas, ventana)
    token = ajustes["telegram_bot_token"] or current_app.config.get("TOKEN_BOT_TELEGRAM", "")
    chat_id = ajustes["telegram_chat_id"]

    # Envía una notificación de texto simple para alta compatibilidad.
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    respuesta = requests.post(url, json={"chat_id": chat_id, "text": mensaje}, timeout=20)
    data = respuesta.json()
    if not respuesta.ok or not data.get("ok"):
        logger.warning("No se pudo enviar notificación Telegram: %s", data)
        return {"enviado": False, "motivo": "error_telegram", "detalle": data}

    if not forzar:
        guardar_ultima_envio_at(ahora, usuario_id)
    return {"enviado": True, "total_entregas": len(entregas)}
