"""Gestión centralizada de configuración editable desde el panel web."""

from flask import current_app

from .autenticacion import obtener_usuario_actual_id
from .configuracion_notificaciones import _guardar_valor
from .configuracion_notificaciones import _obtener_valor
from .configuracion_notificaciones import obtener_ajustes_notificaciones
from .extensions import bd


def _a_bool(valor):
    """Convierte strings/valores varios a booleano."""
    return str(valor).strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def _aplicar_en_config_runtime(ajustes):
    """Replica ajustes persistidos a `current_app.config` para uso inmediato."""
    current_app.config["TOKEN_BOT_TELEGRAM"] = ajustes["telegram_bot_token"]
    current_app.config["MODO_BOT"] = ajustes["modo_bot"]
    current_app.config["CAMPUS_CALENDARIO_URL"] = ajustes["campus_calendario_url"]
    current_app.config["ZONA_HORARIA"] = ajustes["zona_horaria"]
    current_app.config["TZ"] = ajustes["zona_horaria"]
    current_app.config["SINCRONIZACION_CAMPUS_ACTIVA"] = ajustes["sincronizacion_campus_activa"]
    current_app.config["MINUTOS_SINCRONIZACION_CAMPUS"] = ajustes["minutos_sincronizacion_campus"]


def obtener_ajustes_sistema(usuario_id=None):
    """Devuelve configuración funcional completa para panel administrativo."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    notificaciones = obtener_ajustes_notificaciones(usuario_id)
    return {
        "telegram_bot_token": notificaciones["telegram_bot_token"] or current_app.config.get("TOKEN_BOT_TELEGRAM", ""),
        "telegram_chat_id": notificaciones["telegram_chat_id"],
        "notificaciones_activas": notificaciones["notificaciones_activas"],
        "notificacion_hora": notificaciones["notificacion_hora"],
        "notificacion_frecuencia_horas": notificaciones["notificacion_frecuencia_horas"],
        "notificacion_ventana_dias": notificaciones["notificacion_ventana_dias"],
        "campus_calendario_url": _obtener_valor("campus_calendario_url", usuario_id) or "",
        "zona_horaria": _obtener_valor("zona_horaria", usuario_id)
        or current_app.config.get("ZONA_HORARIA", "America/Argentina/Buenos_Aires"),
        "sincronizacion_campus_activa": _a_bool(
            _obtener_valor("sincronizacion_campus_activa", usuario_id)
            or str(current_app.config.get("SINCRONIZACION_CAMPUS_ACTIVA", True))
        ),
        "minutos_sincronizacion_campus": int(
            _obtener_valor("minutos_sincronizacion_campus", usuario_id)
            or str(current_app.config.get("MINUTOS_SINCRONIZACION_CAMPUS", 30))
        ),
        "modo_bot": _obtener_valor("modo_bot", usuario_id) or current_app.config.get("MODO_BOT", "long_polling"),
    }


def guardar_ajustes_sistema(datos, usuario_id=None):
    """Valida y guarda configuración administrativa del sistema."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    if not usuario_id:
        return {}

    if "telegram_bot_token" in datos:
        _guardar_valor("telegram_bot_token", str(datos.get("telegram_bot_token") or "").strip(), usuario_id)
    if "telegram_chat_id" in datos:
        _guardar_valor("telegram_chat_id", str(datos.get("telegram_chat_id") or "").strip(), usuario_id)
    if "notificaciones_activas" in datos:
        _guardar_valor(
            "notificaciones_activas",
            "true" if _a_bool(datos.get("notificaciones_activas")) else "false",
            usuario_id,
        )
    if "notificacion_hora" in datos:
        _guardar_valor(
            "notificacion_hora",
            str(datos.get("notificacion_hora") or "08:00").strip() or "08:00",
            usuario_id,
        )
    if "notificacion_frecuencia_horas" in datos:
        _guardar_valor(
            "notificacion_frecuencia_horas",
            str(max(1, int(datos.get("notificacion_frecuencia_horas") or 24))),
            usuario_id,
        )
    if "notificacion_ventana_dias" in datos:
        _guardar_valor(
            "notificacion_ventana_dias",
            str(max(1, int(datos.get("notificacion_ventana_dias") or 7))),
            usuario_id,
        )
    if "campus_calendario_url" in datos:
        _guardar_valor("campus_calendario_url", str(datos.get("campus_calendario_url") or "").strip(), usuario_id)
    if "zona_horaria" in datos:
        _guardar_valor(
            "zona_horaria",
            str(datos.get("zona_horaria") or "America/Argentina/Buenos_Aires").strip(),
            usuario_id,
        )
    if "sincronizacion_campus_activa" in datos:
        _guardar_valor(
            "sincronizacion_campus_activa",
            "true" if _a_bool(datos.get("sincronizacion_campus_activa")) else "false",
            usuario_id,
        )
    if "minutos_sincronizacion_campus" in datos:
        _guardar_valor(
            "minutos_sincronizacion_campus",
            str(max(1, int(datos.get("minutos_sincronizacion_campus") or 30))),
            usuario_id,
        )
    if "modo_bot" in datos:
        modo_bot = str(datos.get("modo_bot") or "long_polling").strip().lower()
        if modo_bot not in {"long_polling", "webhook"}:
            modo_bot = "long_polling"
        _guardar_valor("modo_bot", modo_bot, usuario_id)

    bd.session.commit()
    ajustes = obtener_ajustes_sistema(usuario_id)
    _aplicar_en_config_runtime(ajustes)
    return ajustes


def aplicar_ajustes_sistema_a_config(aplicacion):
    """Carga ajustes persistidos y los aplica a `aplicacion.config` al iniciar."""
    with aplicacion.app_context():
        ajustes = obtener_ajustes_sistema()
        aplicacion.config["TOKEN_BOT_TELEGRAM"] = ajustes["telegram_bot_token"]
        aplicacion.config["MODO_BOT"] = ajustes["modo_bot"]
        aplicacion.config["CAMPUS_CALENDARIO_URL"] = ajustes["campus_calendario_url"]
        aplicacion.config["ZONA_HORARIA"] = ajustes["zona_horaria"]
        aplicacion.config["TZ"] = ajustes["zona_horaria"]
        aplicacion.config["SINCRONIZACION_CAMPUS_ACTIVA"] = ajustes["sincronizacion_campus_activa"]
        aplicacion.config["MINUTOS_SINCRONIZACION_CAMPUS"] = ajustes["minutos_sincronizacion_campus"]
