"""Utilidades de autenticación y contexto de usuario actual."""

from datetime import datetime
from datetime import timedelta
import secrets

from flask import current_app
from flask import session

from .extensions import bd
from .models import Usuario


def obtener_usuario_actual():
    """Devuelve el usuario autenticado en sesión, o `None`."""
    try:
        usuario_id = session.get("usuario_id")
    except RuntimeError:
        return None
    if not usuario_id:
        return None
    return Usuario.query.get(usuario_id)


def obtener_usuario_actual_id():
    """Devuelve ID de usuario autenticado, o `None`."""
    usuario = obtener_usuario_actual()
    return usuario.id if usuario else None


def iniciar_sesion(usuario):
    """Crea sesión autenticada."""
    session["usuario_autenticado"] = True
    session["usuario_id"] = usuario.id
    session["usuario_email"] = usuario.email
    session["usuario_es_admin"] = bool(usuario.es_admin)


def cerrar_sesion():
    """Limpia sesión actual."""
    session.clear()


def asegurar_usuario_admin_desde_config():
    """Garantiza que exista usuario admin según variables de entorno."""
    email_admin = str(current_app.config.get("ADMIN_EMAIL", "admin@example.local")).strip().lower()
    password_admin = str(current_app.config.get("ADMIN_PASSWORD", "cambiar-admin-dev"))

    usuario = Usuario.query.filter(bd.func.lower(Usuario.email) == email_admin).first()
    if usuario:
        if not usuario.es_admin:
            usuario.es_admin = True
        if not usuario.activo:
            usuario.activo = True
        if not usuario.origen_registro:
            usuario.origen_registro = "web"
        bd.session.commit()
        return usuario

    usuario = Usuario(email=email_admin, es_admin=True, activo=True, origen_registro="web")
    usuario.set_password(password_admin)
    bd.session.add(usuario)
    bd.session.commit()
    return usuario


def obtener_usuario_por_chat_telegram(chat_id):
    """Busca usuario vinculado a un chat de Telegram."""
    if not chat_id:
        return None
    return Usuario.query.filter_by(telegram_chat_id=str(chat_id)).first()


def generar_codigo_vinculacion_telegram(usuario, minutos=10):
    """Genera código temporal para vincular cuenta web con bot Telegram."""
    codigo = "".join(secrets.choice("0123456789") for _ in range(6))
    usuario.telegram_codigo_vinculacion = codigo
    usuario.telegram_codigo_expira_en = datetime.utcnow() + timedelta(minutes=max(1, int(minutos)))
    bd.session.commit()
    return codigo, usuario.telegram_codigo_expira_en


def obtener_usuario_por_codigo_vinculacion(codigo):
    """Busca usuario por código temporal vigente."""
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    usuario = Usuario.query.filter_by(telegram_codigo_vinculacion=codigo).first()
    if not usuario:
        return None
    if not usuario.telegram_codigo_expira_en:
        return None
    if usuario.telegram_codigo_expira_en < datetime.utcnow():
        return None
    return usuario


def vincular_chat_telegram(usuario, chat_id, telegram_usuario_id=None):
    """Asocia chat de Telegram a un usuario y limpia código temporal."""
    if not usuario:
        return
    usuario.telegram_chat_id = str(chat_id)
    if telegram_usuario_id is not None:
        usuario.telegram_usuario_id = str(telegram_usuario_id)
    usuario.telegram_codigo_vinculacion = None
    usuario.telegram_codigo_expira_en = None
    bd.session.commit()
