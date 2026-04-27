"""API REST del asistente (entregas, materias, sync y bot)."""

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session

from ..autenticacion import generar_codigo_vinculacion_telegram
from ..autenticacion import obtener_usuario_actual
from ..autenticacion import obtener_usuario_actual_id
from ..configuracion_notificaciones import guardar_ajustes_notificaciones
from ..configuracion_notificaciones import obtener_ajustes_notificaciones
from ..configuracion_sistema import guardar_ajustes_sistema
from ..configuracion_sistema import obtener_ajustes_sistema
from ..extensions import bd
from ..models import Entrega, Materia, Usuario
from ..notificaciones_telegram import enviar_resumen_pendientes_programado
from ..sincronizador_campus import sincronizar_campus
from ..telegram_bot import procesar_update_telegram

rutas_api = Blueprint("api", __name__, url_prefix="/api")


@rutas_api.before_request
def proteger_api():
    """Requiere sesión para endpoints administrativos."""
    if request.endpoint in {"api.salud", "api.webhook_telegram"}:
        return None
    if not session.get("usuario_autenticado") or not session.get("usuario_id"):
        return jsonify({"error": "No autenticado"}), 401
    return None


@rutas_api.get("/salud")
def salud():
    """Endpoint de verificación básica de servicio."""
    return jsonify({"estado": "ok"})


@rutas_api.post("/entregas")
def crear_entrega():
    """Crea una nueva entrega manual desde web/API."""
    usuario_id = obtener_usuario_actual_id()
    datos = request.get_json(silent=True) or {}
    campos_requeridos = ["materia", "titulo", "tipo", "fecha_entrega"]
    campos_faltantes = [campo for campo in campos_requeridos if not datos.get(campo)]
    if campos_faltantes:
        return jsonify({"error": f"Faltan campos: {', '.join(campos_faltantes)}"}), 400

    try:
        fecha_entrega = datetime.fromisoformat(datos["fecha_entrega"])
    except ValueError:
        return jsonify({"error": "fecha_entrega debe usar formato ISO"}), 400

    entrega = Entrega(
        usuario_id=usuario_id,
        materia=datos["materia"],
        titulo=datos["titulo"],
        tipo=datos["tipo"],
        fecha_entrega=fecha_entrega,
        prioridad=datos.get("prioridad", "media"),
        estado=datos.get("estado", "pendiente"),
        nota=datos.get("nota"),
        detalle=datos.get("detalle"),
        origen=datos.get("origen", "manual"),
    )
    bd.session.add(entrega)
    bd.session.commit()

    return jsonify(entrega.a_diccionario()), 201


@rutas_api.get("/entregas")
def listar_entregas():
    """Lista entregas con filtros opcionales por estado/prioridad."""
    usuario_id = obtener_usuario_actual_id()
    consulta = Entrega.query.filter(Entrega.usuario_id == usuario_id)

    estado = request.args.get("estado")
    prioridad = request.args.get("prioridad")
    if estado:
        consulta = consulta.filter(Entrega.estado == estado)
    if prioridad:
        consulta = consulta.filter(Entrega.prioridad == prioridad)

    entregas = consulta.order_by(Entrega.fecha_entrega.asc()).all()
    return jsonify([entrega.a_diccionario() for entrega in entregas])


@rutas_api.put("/entregas/<int:entrega_id>")
def actualizar_entrega(entrega_id):
    """Actualiza campos permitidos de una entrega existente."""
    usuario_id = obtener_usuario_actual_id()
    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_id).first()
    if not entrega:
        return jsonify({"error": "Entrega no encontrada"}), 404

    datos = request.get_json(silent=True) or {}
    if "materia" in datos:
        entrega.materia = (datos.get("materia") or "").strip()
    if "titulo" in datos:
        entrega.titulo = (datos.get("titulo") or "").strip()
    if "tipo" in datos:
        entrega.tipo = (datos.get("tipo") or "").strip()
    if "prioridad" in datos:
        entrega.prioridad = (datos.get("prioridad") or "").strip()
    if "estado" in datos:
        entrega.estado = (datos.get("estado") or "").strip()
    if "detalle" in datos:
        entrega.detalle = (datos.get("detalle") or "").strip() or None
    if "nota" in datos:
        entrega.nota = datos.get("nota")
    if "fecha_entrega" in datos:
        try:
            entrega.fecha_entrega = datetime.fromisoformat(datos["fecha_entrega"])
        except ValueError:
            return jsonify({"error": "fecha_entrega debe usar formato ISO"}), 400

    campos_obligatorios = {
        "materia": entrega.materia,
        "titulo": entrega.titulo,
        "tipo": entrega.tipo,
    }
    faltantes = [campo for campo, valor in campos_obligatorios.items() if not valor]
    if faltantes:
        return jsonify({"error": f"Faltan campos obligatorios: {', '.join(faltantes)}"}), 400

    bd.session.commit()
    return jsonify(entrega.a_diccionario())


@rutas_api.delete("/entregas/<int:entrega_id>")
def eliminar_entrega(entrega_id):
    """Elimina una entrega por ID."""
    usuario_id = obtener_usuario_actual_id()
    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_id).first()
    if not entrega:
        return jsonify({"error": "Entrega no encontrada"}), 404

    bd.session.delete(entrega)
    bd.session.commit()
    return jsonify({"ok": True})


@rutas_api.post("/materias")
def crear_materia():
    """Crea una materia evitando duplicados por nombre."""
    usuario_id = obtener_usuario_actual_id()
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    existente = Materia.query.filter(
        Materia.usuario_id == usuario_id,
        bd.func.lower(Materia.nombre) == nombre.lower(),
    ).first()
    if existente:
        return jsonify({"error": "La materia ya existe"}), 409

    materia = Materia(usuario_id=usuario_id, nombre=nombre)
    bd.session.add(materia)
    bd.session.commit()
    return jsonify(materia.a_diccionario()), 201


@rutas_api.get("/materias")
def listar_materias():
    """Lista materias ordenadas alfabéticamente."""
    usuario_id = obtener_usuario_actual_id()
    materias = Materia.query.filter(Materia.usuario_id == usuario_id).order_by(Materia.nombre.asc()).all()
    return jsonify([materia.a_diccionario() for materia in materias])


@rutas_api.get("/configuracion/notificaciones")
def obtener_configuracion_notificaciones():
    """Devuelve configuración de notificaciones Telegram."""
    usuario_id = obtener_usuario_actual_id()
    return jsonify(obtener_ajustes_notificaciones(usuario_id))


@rutas_api.put("/configuracion/notificaciones")
def actualizar_configuracion_notificaciones():
    """Guarda configuración de notificaciones desde panel/API."""
    usuario_id = obtener_usuario_actual_id()
    datos = request.get_json(silent=True) or {}
    configuracion = guardar_ajustes_notificaciones(datos, usuario_id)
    return jsonify(configuracion)


@rutas_api.get("/configuracion/sistema")
def obtener_configuracion_sistema():
    """Devuelve configuración global editable desde panel."""
    usuario_id = obtener_usuario_actual_id()
    return jsonify(obtener_ajustes_sistema(usuario_id))


@rutas_api.put("/configuracion/sistema")
def actualizar_configuracion_sistema():
    """Guarda configuración global del sistema."""
    usuario_id = obtener_usuario_actual_id()
    datos = request.get_json(silent=True) or {}
    configuracion = guardar_ajustes_sistema(datos, usuario_id)
    return jsonify(configuracion)


@rutas_api.post("/configuracion/notificaciones/probar")
def probar_notificacion_telegram():
    """Dispara un envío inmediato de prueba al chat configurado."""
    usuario_id = obtener_usuario_actual_id()
    resultado = enviar_resumen_pendientes_programado(forzar=True, usuario_id=usuario_id)
    if not resultado.get("enviado"):
        return jsonify(resultado), 400
    return jsonify(resultado)


@rutas_api.post("/sincronizacion/campus")
def sincronizar_campus_manual():
    """Lanza sincronización manual del calendario de campus."""
    usuario_id = obtener_usuario_actual_id()
    configuracion_usuario = obtener_ajustes_sistema(usuario_id)
    url = (configuracion_usuario.get("campus_calendario_url") or "").strip()
    if not url:
        return jsonify({"error": "Configurá tu URL iCal de campus para sincronizar."}), 400

    resultado = sincronizar_campus(url, usuario_id=usuario_id)
    return jsonify(resultado)


@rutas_api.post("/telegram/webhook")
def webhook_telegram():
    """Recibe updates Telegram por webhook y delega al procesador."""
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "Payload JSON inválido"}), 400

    modo_bot = current_app.config.get("MODO_BOT")
    token_bot = current_app.config.get("TOKEN_BOT_TELEGRAM")
    secreto_esperado = current_app.config.get("SECRETO_WEBHOOK_TELEGRAM")
    secreto_recibido = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    if not token_bot:
        return jsonify({"error": "TOKEN_BOT_TELEGRAM no configurado"}), 500

    if modo_bot == "webhook" and secreto_esperado and secreto_recibido != secreto_esperado:
        return jsonify({"error": "Secreto de webhook inválido"}), 403

    procesar_update_telegram(datos, token_bot)
    return jsonify({"ok": True})


@rutas_api.get("/usuarios")
def listar_usuarios():
    """Lista usuarios (solo admin)."""
    usuario_actual = obtener_usuario_actual()
    if not usuario_actual or not usuario_actual.es_admin:
        return jsonify({"error": "Solo admin"}), 403
    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    return jsonify([usuario.a_diccionario() for usuario in usuarios])


@rutas_api.post("/usuarios")
def crear_usuario():
    """Crea usuario (solo admin)."""
    usuario_actual = obtener_usuario_actual()
    if not usuario_actual or not usuario_actual.es_admin:
        return jsonify({"error": "Solo admin"}), 403

    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip().lower()
    password = datos.get("password") or ""
    es_admin = bool(datos.get("es_admin", False))

    if not email or "@" not in email:
        return jsonify({"error": "Email inválido"}), 400
    if len(password) < 3:
        return jsonify({"error": "Password demasiado corto"}), 400

    existente = Usuario.query.filter(bd.func.lower(Usuario.email) == email).first()
    if existente:
        return jsonify({"error": "El email ya existe"}), 409

    usuario = Usuario(email=email, es_admin=es_admin, activo=True, origen_registro="admin")
    usuario.set_password(password)
    bd.session.add(usuario)
    bd.session.commit()
    return jsonify(usuario.a_diccionario()), 201


@rutas_api.get("/admin/usuarios")
def admin_listar_usuarios():
    """Lista usuarios para panel administrativo."""
    usuario_actual = obtener_usuario_actual()
    if not usuario_actual or not usuario_actual.es_admin:
        return jsonify({"error": "Solo admin"}), 403

    solo_pendientes = request.args.get("pendientes", "").lower() in {"1", "true", "si"}
    consulta = Usuario.query
    if solo_pendientes:
        consulta = consulta.filter(Usuario.activo.is_(False))
    usuarios = consulta.order_by(Usuario.creado_en.desc()).all()
    return jsonify([usuario.a_diccionario() for usuario in usuarios])


@rutas_api.put("/admin/usuarios/<int:usuario_id>/estado")
def admin_actualizar_estado_usuario(usuario_id):
    """Habilita o deshabilita una cuenta de usuario."""
    usuario_actual = obtener_usuario_actual()
    if not usuario_actual or not usuario_actual.es_admin:
        return jsonify({"error": "Solo admin"}), 403
    if usuario_actual.id == usuario_id:
        return jsonify({"error": "No podés deshabilitarte a vos mismo"}), 400

    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404

    datos = request.get_json(silent=True) or {}
    if "activo" in datos:
        usuario.activo = bool(datos.get("activo"))
    if "es_admin" in datos:
        usuario.es_admin = bool(datos.get("es_admin"))
    bd.session.commit()
    return jsonify(usuario.a_diccionario())


@rutas_api.get("/telegram/vinculacion")
def estado_vinculacion_telegram():
    """Devuelve estado de vinculación Telegram del usuario logueado."""
    usuario = obtener_usuario_actual()
    if not usuario:
        return jsonify({"error": "No autenticado"}), 401
    return jsonify(
        {
            "telegram_vinculado": bool(usuario.telegram_chat_id),
            "telegram_chat_id": usuario.telegram_chat_id,
            "telegram_usuario_id": usuario.telegram_usuario_id,
            "telegram_codigo_pendiente": usuario.telegram_codigo_vinculacion,
            "telegram_codigo_expira_en": (
                usuario.telegram_codigo_expira_en.isoformat() if usuario.telegram_codigo_expira_en else None
            ),
        }
    )


@rutas_api.post("/telegram/vinculacion/generar")
def generar_vinculacion_telegram():
    """Genera código temporal para vincular el bot Telegram."""
    usuario = obtener_usuario_actual()
    if not usuario:
        return jsonify({"error": "No autenticado"}), 401
    codigo, expira_en = generar_codigo_vinculacion_telegram(usuario, minutos=10)
    return jsonify(
        {
            "codigo": codigo,
            "expira_en": expira_en.isoformat(),
            "instruccion": f"En Telegram enviá: /vincular {codigo}",
        }
    )


@rutas_api.delete("/telegram/vinculacion")
def desvincular_telegram():
    """Elimina vínculo Telegram del usuario logueado."""
    usuario = obtener_usuario_actual()
    if not usuario:
        return jsonify({"error": "No autenticado"}), 401
    usuario.telegram_chat_id = None
    usuario.telegram_usuario_id = None
    usuario.telegram_codigo_vinculacion = None
    usuario.telegram_codigo_expira_en = None
    bd.session.commit()
    return jsonify({"ok": True})
