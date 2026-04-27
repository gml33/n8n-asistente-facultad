"""Rutas web del panel HTML."""

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..autenticacion import cerrar_sesion
from ..autenticacion import iniciar_sesion
from ..autenticacion import obtener_usuario_actual
from ..extensions import bd
from ..models import Usuario

rutas_web = Blueprint("web", __name__)


def _esta_autenticado():
    """Indica si existe sesión de usuario autenticada."""
    return bool(session.get("usuario_autenticado") and session.get("usuario_id"))


@rutas_web.before_request
def proteger_vistas_web():
    """Restringe panel a usuarios logueados."""
    if request.endpoint in {"web.login", "web.registro", "web.favicon"}:
        return None
    if not _esta_autenticado():
        return redirect(url_for("web.login"))
    return None


@rutas_web.get("/")
def panel():
    """Renderiza la vista principal del panel."""
    usuario = obtener_usuario_actual()
    return render_template("index.html", usuario_email=session.get("usuario_email"), usuario=usuario)


@rutas_web.route("/login", methods=["GET", "POST"])
def login():
    """Pantalla de acceso al panel por email y contraseña."""
    if _esta_autenticado():
        return redirect(url_for("web.panel"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        usuario = Usuario.query.filter(bd.func.lower(Usuario.email) == email).first()
        if usuario and usuario.verificar_password(password):
            if not usuario.activo:
                error = "Cuenta pendiente de habilitación por administrador."
                return render_template("login.html", error=error)
            iniciar_sesion(usuario)
            return redirect(url_for("web.panel"))
        error = "Credenciales inválidas."

    return render_template("login.html", error=error)


@rutas_web.route("/registro", methods=["GET", "POST"])
def registro():
    """Registro simple de nuevo usuario."""
    if _esta_autenticado():
        return redirect(url_for("web.panel"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password_2 = request.form.get("password_2") or ""

        if not email or "@" not in email:
            error = "Email inválido."
        elif len(password) < 3:
            error = "La contraseña debe tener al menos 3 caracteres."
        elif password != password_2:
            error = "Las contraseñas no coinciden."
        else:
            existente = Usuario.query.filter(bd.func.lower(Usuario.email) == email).first()
            if existente:
                error = "Ese email ya está registrado."
            else:
                usuario = Usuario(email=email, es_admin=False, activo=False, origen_registro="web")
                usuario.set_password(password)
                bd.session.add(usuario)
                bd.session.commit()
                return render_template(
                    "login.html",
                    error="Cuenta creada. Queda pendiente de habilitación por administrador.",
                )

    return render_template("registro.html", error=error)


@rutas_web.post("/logout")
def logout():
    """Cierra sesión del panel."""
    cerrar_sesion()
    return redirect(url_for("web.login"))


@rutas_web.get("/favicon.ico")
def favicon():
    """Compatibilidad con navegadores que piden favicon.ico explícitamente."""
    return redirect(url_for("static", filename="favicon.svg"), code=302)
