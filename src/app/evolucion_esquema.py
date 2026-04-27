"""Migraciones ligeras sin Alembic.

Mantiene compatibilidad entre SQLite/PostgreSQL para columnas nuevas.
"""

from sqlalchemy import text
from sqlalchemy import inspect
from flask import current_app

from .extensions import bd
from .models import Usuario


def aplicar_evolucion_esquema():
    """Aplica cambios de esquema mínimos si todavía no existen."""
    motor = bd.engine
    dialecto = motor.dialect.name
    inspector = inspect(motor)

    # PostgreSQL soporta "IF NOT EXISTS" directamente.
    if dialecto == "postgresql":
        bd.session.execute(
            text(
                """
                ALTER TABLE entregas
                ADD COLUMN IF NOT EXISTS origen_evento_id VARCHAR(255)
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE entregas
                ADD COLUMN IF NOT EXISTS usuario_id INTEGER
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE materias
                ADD COLUMN IF NOT EXISTS usuario_id INTEGER
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(50)
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS activo BOOLEAN
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS origen_registro VARCHAR(20)
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS telegram_usuario_id VARCHAR(50)
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS telegram_codigo_vinculacion VARCHAR(32)
                """
            )
        )
        bd.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS telegram_codigo_expira_en TIMESTAMP
                """
            )
        )
        # Intenta liberar unicidad global previa para permitir multiusuario.
        bd.session.execute(text("DROP INDEX IF EXISTS ix_materias_nombre"))
        bd.session.execute(text("DROP INDEX IF EXISTS materias_nombre_key"))
    else:
        # SQLite requiere inspección previa para evitar error por columna duplicada.
        columnas = [columna["name"] for columna in inspector.get_columns("entregas")]
        if "origen_evento_id" not in columnas:
            bd.session.execute(text("ALTER TABLE entregas ADD COLUMN origen_evento_id VARCHAR(255)"))
        if "usuario_id" not in columnas:
            bd.session.execute(text("ALTER TABLE entregas ADD COLUMN usuario_id INTEGER"))

        columnas_materias = [columna["name"] for columna in inspector.get_columns("materias")]
        if "usuario_id" not in columnas_materias:
            bd.session.execute(text("ALTER TABLE materias ADD COLUMN usuario_id INTEGER"))

        columnas_usuarios = [columna["name"] for columna in inspector.get_columns("usuarios")]
        if "telegram_chat_id" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN telegram_chat_id VARCHAR(50)"))
        if "activo" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN activo BOOLEAN"))
        if "origen_registro" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN origen_registro VARCHAR(20)"))
        if "telegram_usuario_id" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN telegram_usuario_id VARCHAR(50)"))
        if "telegram_codigo_vinculacion" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN telegram_codigo_vinculacion VARCHAR(32)"))
        if "telegram_codigo_expira_en" not in columnas_usuarios:
            bd.session.execute(text("ALTER TABLE usuarios ADD COLUMN telegram_codigo_expira_en DATETIME"))

    bd.session.commit()
    bd.create_all()

    # Crea/obtiene usuario inicial para asociar datos preexistentes.
    email_admin = str(current_app.config.get("ADMIN_EMAIL", "admin@example.local")).strip().lower()
    password_admin = str(current_app.config.get("ADMIN_PASSWORD", "cambiar-admin-dev"))
    usuario_base = Usuario.query.filter(bd.func.lower(Usuario.email) == email_admin).first()
    if not usuario_base:
        usuario_base = Usuario(email=email_admin, es_admin=True)
        usuario_base.set_password(password_admin)
        usuario_base.activo = True
        usuario_base.origen_registro = "web"
        bd.session.add(usuario_base)
        bd.session.commit()
    else:
        if usuario_base.activo is not True:
            usuario_base.activo = True
        if not usuario_base.origen_registro:
            usuario_base.origen_registro = "web"
        bd.session.commit()

    # Backfill de registros legacy sin usuario.
    bd.session.execute(
        text("UPDATE entregas SET usuario_id = :uid WHERE usuario_id IS NULL"),
        {"uid": usuario_base.id},
    )
    bd.session.execute(
        text("UPDATE materias SET usuario_id = :uid WHERE usuario_id IS NULL"),
        {"uid": usuario_base.id},
    )
    bd.session.execute(text("UPDATE usuarios SET activo = TRUE WHERE activo IS NULL"))
    bd.session.execute(text("UPDATE usuarios SET origen_registro = 'web' WHERE origen_registro IS NULL"))

    # Índices/constraints multiusuario (idempotentes en PostgreSQL).
    if dialecto == "postgresql":
        bd.session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_materias_usuario_nombre
                ON materias (usuario_id, lower(nombre))
                """
            )
        )
        bd.session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ajustes_usuario_clave
                ON ajustes_usuario (usuario_id, clave)
                """
            )
        )
        bd.session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_telegram_chat_id
                ON usuarios (telegram_chat_id)
                WHERE telegram_chat_id IS NOT NULL
                """
            )
        )

    bd.session.commit()
