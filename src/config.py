"""Configuración central de la aplicación.

Lee variables de entorno y define defaults seguros para desarrollo local.
"""

import os


class Configuracion:
    """Contenedor de configuración consumido por Flask."""

    ENTORNO = os.getenv("ENTORNO", "desarrollo").strip().lower()
    ES_PRODUCCION = ENTORNO == "produccion"

    # Seguridad de sesión y firmas de Flask.
    CLAVE_SECRETA = os.getenv("CLAVE_SECRETA", os.getenv("SECRET_KEY", "cambiar-clave-dev"))
    SECRET_KEY = CLAVE_SECRETA
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.local")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "cambiar-admin-dev")
    SESSION_COOKIE_SECURE = ES_PRODUCCION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Conexión a base de datos (PostgreSQL por defecto vía Docker).
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "URL_BASE_DATOS",
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@base_datos:5432/asistente_facultad",
        ),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Zona horaria operativa (scheduler, fechas de negocio, etc.).
    ZONA_HORARIA = os.getenv("ZONA_HORARIA", os.getenv("TZ", "America/Argentina/Buenos_Aires"))
    TZ = ZONA_HORARIA

    # Modo de integración del bot Telegram.
    MODO_BOT = os.getenv("MODO_BOT", "long_polling")
    TOKEN_BOT_TELEGRAM = os.getenv("TOKEN_BOT_TELEGRAM", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    SECRETO_WEBHOOK_TELEGRAM = os.getenv(
        "SECRETO_WEBHOOK_TELEGRAM",
        os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
    )

    # Sincronización de calendario del campus (ICS).
    CAMPUS_CALENDARIO_URL = os.getenv("CAMPUS_CALENDARIO_URL", "")
    MINUTOS_SINCRONIZACION_CAMPUS = int(os.getenv("MINUTOS_SINCRONIZACION_CAMPUS", "30"))
    SINCRONIZACION_CAMPUS_ACTIVA = os.getenv("SINCRONIZACION_CAMPUS_ACTIVA", "true").lower() == "true"


def validar_configuracion_produccion(config):
    """Corta el arranque si faltan valores mínimos seguros de producción."""
    if not config.get("ES_PRODUCCION"):
        return

    faltantes = []
    if not config.get("SECRET_KEY") or config.get("SECRET_KEY") in {"cambiar-clave-dev", "cambiar-esta-clave"}:
        faltantes.append("CLAVE_SECRETA")
    if not config.get("ADMIN_EMAIL") or config.get("ADMIN_EMAIL") == "admin@example.local":
        faltantes.append("ADMIN_EMAIL")
    if not config.get("ADMIN_PASSWORD") or config.get("ADMIN_PASSWORD") == "cambiar-admin-dev":
        faltantes.append("ADMIN_PASSWORD")
    if config.get("MODO_BOT") == "webhook" and not config.get("SECRETO_WEBHOOK_TELEGRAM"):
        faltantes.append("SECRETO_WEBHOOK_TELEGRAM")

    if faltantes:
        raise RuntimeError(
            "Configuración insegura para producción. Definí: " + ", ".join(sorted(set(faltantes)))
        )
