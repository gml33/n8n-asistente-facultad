"""Gestión de ajustes persistentes de notificaciones Telegram."""

from datetime import date
from datetime import datetime

from .autenticacion import obtener_usuario_actual_id
from .extensions import bd
from .models import AjusteUsuario

# Defaults del sistema para inicializar claves nuevas.
AJUSTES_POR_DEFECTO = {
    "notificaciones_activas": "false",
    "notificacion_hora": "08:00",
    "notificacion_frecuencia_dias": "1",
    "notificacion_frecuencia_horas": "24",
    "notificacion_ventana_dias": "7",
    "telegram_chat_id": "",
    "telegram_bot_token": "",
    "notificacion_ultima_fecha_envio": "",
}


def _obtener_valor(clave, usuario_id=None):
    """Devuelve valor guardado o default para una clave."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    if not usuario_id:
        return AJUSTES_POR_DEFECTO.get(clave, "")

    ajuste = AjusteUsuario.query.filter_by(usuario_id=usuario_id, clave=clave).first()
    if ajuste:
        return ajuste.valor
    return AJUSTES_POR_DEFECTO.get(clave, "")


def _guardar_valor(clave, valor, usuario_id=None):
    """Upsert simple en tabla de ajustes."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    if not usuario_id:
        return

    ajuste = AjusteUsuario.query.filter_by(usuario_id=usuario_id, clave=clave).first()
    if not ajuste:
        ajuste = AjusteUsuario(usuario_id=usuario_id, clave=clave, valor=str(valor))
        bd.session.add(ajuste)
    else:
        ajuste.valor = str(valor)


def obtener_ajustes_notificaciones(usuario_id=None):
    """Lee y tipa la configuración necesaria para programar notificaciones."""
    return {
        "notificaciones_activas": _obtener_valor("notificaciones_activas", usuario_id).lower() == "true",
        "notificacion_hora": _obtener_valor("notificacion_hora", usuario_id) or "08:00",
        "notificacion_frecuencia_dias": int(_obtener_valor("notificacion_frecuencia_dias", usuario_id) or "1"),
        "notificacion_frecuencia_horas": int(_obtener_valor("notificacion_frecuencia_horas", usuario_id) or "24"),
        "notificacion_ventana_dias": int(_obtener_valor("notificacion_ventana_dias", usuario_id) or "7"),
        "telegram_chat_id": _obtener_valor("telegram_chat_id", usuario_id),
        "telegram_bot_token": _obtener_valor("telegram_bot_token", usuario_id),
        "notificacion_ultima_fecha_envio": _obtener_valor("notificacion_ultima_fecha_envio", usuario_id),
    }


def guardar_ajustes_notificaciones(datos, usuario_id=None):
    """Valida y persiste configuración recibida desde API/panel."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    if not usuario_id:
        return AJUSTES_POR_DEFECTO.copy()

    claves = [
        "notificaciones_activas",
        "notificacion_hora",
        "notificacion_frecuencia_dias",
        "notificacion_frecuencia_horas",
        "notificacion_ventana_dias",
        "telegram_chat_id",
        "telegram_bot_token",
    ]
    for clave in claves:
        if clave not in datos:
            continue

        valor = datos[clave]
        if clave == "notificaciones_activas":
            valor = "true" if bool(valor) else "false"
        elif clave in {"notificacion_frecuencia_dias", "notificacion_frecuencia_horas", "notificacion_ventana_dias"}:
            valor = str(max(1, int(valor)))
        else:
            valor = str(valor).strip()

        _guardar_valor(clave, valor, usuario_id)

    bd.session.commit()
    return obtener_ajustes_notificaciones(usuario_id)


def registrar_chat_telegram(chat_id, usuario_id=None):
    """Guarda automáticamente el último chat_id que interactuó con el bot."""
    if usuario_id is None:
        usuario_id = obtener_usuario_actual_id()
    if not usuario_id:
        return
    if not chat_id:
        return
    _guardar_valor("telegram_chat_id", str(chat_id), usuario_id)
    bd.session.commit()


def obtener_ultima_fecha_envio(usuario_id=None):
    """Compatibilidad histórica con valor de última fecha (solo día)."""
    valor = _obtener_valor("notificacion_ultima_fecha_envio", usuario_id)
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def guardar_ultima_fecha_envio(fecha, usuario_id=None):
    """Compatibilidad histórica para persistir última fecha de envío."""
    if isinstance(fecha, date):
        _guardar_valor("notificacion_ultima_fecha_envio", fecha.strftime("%Y-%m-%d"), usuario_id)
        bd.session.commit()
