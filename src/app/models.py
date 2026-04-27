"""Modelos de persistencia del asistente académico."""

from datetime import datetime

from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from .extensions import bd


class Usuario(bd.Model):
    """Cuenta de acceso al sistema (login web y propiedad de datos)."""

    __tablename__ = "usuarios"

    id = bd.Column(bd.Integer, primary_key=True)
    email = bd.Column(bd.String(255), nullable=False, unique=True, index=True)
    password_hash = bd.Column(bd.String(255), nullable=False)
    es_admin = bd.Column(bd.Boolean, nullable=False, default=False)
    activo = bd.Column(bd.Boolean, nullable=False, default=False, index=True)
    origen_registro = bd.Column(bd.String(20), nullable=False, default="web")
    telegram_chat_id = bd.Column(bd.String(50), nullable=True, unique=True, index=True)
    telegram_usuario_id = bd.Column(bd.String(50), nullable=True, index=True)
    telegram_codigo_vinculacion = bd.Column(bd.String(32), nullable=True, index=True)
    telegram_codigo_expira_en = bd.Column(bd.DateTime, nullable=True)
    creado_en = bd.Column(bd.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = bd.Column(
        bd.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def set_password(self, password):
        """Guarda hash seguro de contraseña."""
        self.password_hash = generate_password_hash(password)

    def verificar_password(self, password):
        """Valida contraseña en texto plano contra hash."""
        return check_password_hash(self.password_hash, password or "")

    def a_diccionario(self):
        """Serializa usuario sin exponer hash."""
        return {
            "id": self.id,
            "email": self.email,
            "es_admin": self.es_admin,
            "activo": self.activo,
            "origen_registro": self.origen_registro,
            "telegram_vinculado": bool(self.telegram_chat_id),
            "creado_en": self.creado_en.isoformat(),
        }


class Materia(bd.Model):
    """Catálogo de materias para asociar entregas."""

    __tablename__ = "materias"

    id = bd.Column(bd.Integer, primary_key=True)
    usuario_id = bd.Column(bd.Integer, bd.ForeignKey("usuarios.id"), nullable=False, index=True)
    nombre = bd.Column(bd.String(120), nullable=False, index=True)
    creado_en = bd.Column(bd.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (bd.UniqueConstraint("usuario_id", "nombre", name="uq_materias_usuario_nombre"),)

    def a_diccionario(self):
        """Serializa la entidad para respuestas JSON."""
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "nombre": self.nombre,
            "creado_en": self.creado_en.isoformat(),
        }


class AjusteSistema(bd.Model):
    """Almacén clave/valor para configuración editable en runtime."""

    __tablename__ = "ajustes_sistema"

    clave = bd.Column(bd.String(100), primary_key=True)
    valor = bd.Column(bd.Text, nullable=False, default="")
    actualizado_en = bd.Column(bd.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AjusteUsuario(bd.Model):
    """Ajustes clave/valor aislados por usuario."""

    __tablename__ = "ajustes_usuario"

    id = bd.Column(bd.Integer, primary_key=True)
    usuario_id = bd.Column(bd.Integer, bd.ForeignKey("usuarios.id"), nullable=False, index=True)
    clave = bd.Column(bd.String(100), nullable=False, index=True)
    valor = bd.Column(bd.Text, nullable=False, default="")
    actualizado_en = bd.Column(bd.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (bd.UniqueConstraint("usuario_id", "clave", name="uq_ajustes_usuario_clave"),)


class Entrega(bd.Model):
    """Entidad central de trabajos, parciales y eventos académicos."""

    __tablename__ = "entregas"

    id = bd.Column(bd.Integer, primary_key=True)
    usuario_id = bd.Column(bd.Integer, bd.ForeignKey("usuarios.id"), nullable=False, index=True)
    # Datos funcionales del evento/entrega.
    materia = bd.Column(bd.String(120), nullable=False)
    titulo = bd.Column(bd.String(200), nullable=False)
    tipo = bd.Column(bd.String(50), nullable=False)
    fecha_entrega = bd.Column(bd.DateTime, nullable=False, index=True)
    prioridad = bd.Column(bd.String(20), nullable=False, default="media", index=True)
    estado = bd.Column(bd.String(20), nullable=False, default="pendiente", index=True)
    nota = bd.Column(bd.Float, nullable=True)
    detalle = bd.Column(bd.Text, nullable=True)
    # Trazabilidad de origen (manual, telegram o campus).
    origen = bd.Column(bd.String(20), nullable=False, default="manual")
    origen_evento_id = bd.Column(bd.String(255), nullable=True, index=True)
    # Metadatos de auditoría temporal.
    creado_en = bd.Column(bd.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = bd.Column(
        bd.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def a_diccionario(self):
        """Serializa la entrega para API/web/bot."""
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "materia": self.materia,
            "titulo": self.titulo,
            "tipo": self.tipo,
            "fecha_entrega": self.fecha_entrega.isoformat(),
            "prioridad": self.prioridad,
            "estado": self.estado,
            "nota": self.nota,
            "detalle": self.detalle,
            "origen": self.origen,
            "origen_evento_id": self.origen_evento_id,
            "creado_en": self.creado_en.isoformat(),
            "actualizado_en": self.actualizado_en.isoformat(),
        }
