"""Integración Telegram por long polling/webhook con flujos inline.

Este módulo implementa toda la lógica conversacional del bot:
- Menú principal con botones inline.
- Flujos de alta, modificación y eliminación de entregas.
- Gestión de materias.
- Selector de fecha con calendario inline.
"""

import calendar
import logging
import threading
import time
from datetime import datetime

import requests
from flask import current_app

from .autenticacion import obtener_usuario_por_chat_telegram
from .autenticacion import obtener_usuario_por_codigo_vinculacion
from .autenticacion import vincular_chat_telegram
from .configuracion_notificaciones import registrar_chat_telegram
from .extensions import bd
from .models import Entrega, Materia, Usuario

logger = logging.getLogger(__name__)

# Estado en memoria del worker del bot.
_hilo_long_polling = None
_detener_long_polling = threading.Event()
_estado_usuarios = {}

# Catálogo de tipos válidos para normalizar botones/texto.
_TIPOS_ENTREGA = {
    "trabajo_practico": "trabajo practico",
    "parcial": "parcial",
    "lectura": "lectura",
    "cuestionario": "cuestionario",
    "otro": "otro",
}
_MESES_ES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def _base_api(token):
    """Construye URL base de la API HTTP de Telegram."""
    return f"https://api.telegram.org/bot{token}"


def _teclado_principal():
    """Menú principal del asistente con acciones frecuentes."""
    return {
        "inline_keyboard": [
            [
                {"text": "➕ Agregar entrega", "callback_data": "menu:agregar"},
                {"text": "📋 Listar entregas", "callback_data": "menu:listar"},
            ],
            [
                {"text": "✏️ Modificar", "callback_data": "menu:modificar"},
                {"text": "🗑️ Eliminar", "callback_data": "menu:eliminar"},
            ],
            [
                {"text": "📚 Materias", "callback_data": "menu:materias"},
            ],
        ]
    }


def _teclado_cancelar():
    """Botón estándar para cancelar flujos en curso."""
    return {"inline_keyboard": [[{"text": "⬅️ Cancelar", "callback_data": "flujo:cancelar"}]]}


def _teclado_materias_menu():
    """Submenú de gestión CRUD de materias."""
    return {
        "inline_keyboard": [
            [{"text": "➕ Agregar materia", "callback_data": "mat:agregar"}],
            [{"text": "📋 Listar materias", "callback_data": "mat:listar"}],
            [{"text": "🗑️ Eliminar materia", "callback_data": "mat:eliminar"}],
            [{"text": "⬅️ Volver", "callback_data": "flujo:cancelar"}],
        ]
    }


def _teclado_listados_entregas():
    """Submenú de filtros de listado de entregas."""
    return {
        "inline_keyboard": [
            [{"text": "📌 Pendientes futuras", "callback_data": "listar:futuras"}],
            [{"text": "🕘 Eventos anteriores", "callback_data": "listar:anteriores"}],
            [{"text": "⬅️ Volver", "callback_data": "flujo:cancelar"}],
        ]
    }


def _teclado_materias_para_entrega(usuario_app_id):
    """Botones de selección de materia al crear una entrega."""
    materias = Materia.query.filter(Materia.usuario_id == usuario_app_id).order_by(Materia.nombre.asc()).all()
    if not materias:
        return None

    botones = [
        [{"text": materia.nombre, "callback_data": f"alta:materia:{materia.id}"}]
        for materia in materias
    ]
    botones.append([{"text": "⬅️ Cancelar", "callback_data": "flujo:cancelar"}])
    return {"inline_keyboard": botones}


def _teclado_materias_para_eliminar(usuario_app_id):
    """Botones de materias disponibles para eliminación."""
    materias = Materia.query.filter(Materia.usuario_id == usuario_app_id).order_by(Materia.nombre.asc()).all()
    if not materias:
        return None

    botones = [
        [{"text": f"🗑️ {materia.nombre}", "callback_data": f"mat:eliminar:{materia.id}"}]
        for materia in materias
    ]
    botones.append([{"text": "⬅️ Volver", "callback_data": "menu:materias"}])
    return {"inline_keyboard": botones}


def _teclado_prioridades(callback_prefijo):
    """Teclado reutilizable para elegir prioridad."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔴 Alta", "callback_data": f"{callback_prefijo}:alta"},
                {"text": "🟡 Media", "callback_data": f"{callback_prefijo}:media"},
                {"text": "🟢 Baja", "callback_data": f"{callback_prefijo}:baja"},
            ],
            [{"text": "⬅️ Cancelar", "callback_data": "flujo:cancelar"}],
        ]
    }


def _teclado_estados(callback_prefijo):
    """Teclado reutilizable para elegir estado."""
    return {
        "inline_keyboard": [
            [
                {"text": "🕒 Pendiente", "callback_data": f"{callback_prefijo}:pendiente"},
                {"text": "✅ Entregado", "callback_data": f"{callback_prefijo}:entregado"},
            ],
            [{"text": "⬅️ Cancelar", "callback_data": "flujo:cancelar"}],
        ]
    }


def _teclado_tipos_entrega(callback_prefijo):
    """Teclado reutilizable para elegir tipo de entrega."""
    return {
        "inline_keyboard": [
            [{"text": "📄 Trabajo práctico", "callback_data": f"{callback_prefijo}:trabajo_practico"}],
            [{"text": "🧪 Parcial", "callback_data": f"{callback_prefijo}:parcial"}],
            [{"text": "📚 Lectura", "callback_data": f"{callback_prefijo}:lectura"}],
            [{"text": "📝 Cuestionario", "callback_data": f"{callback_prefijo}:cuestionario"}],
            [{"text": "📌 Otro", "callback_data": f"{callback_prefijo}:otro"}],
            [{"text": "⬅️ Cancelar", "callback_data": "flujo:cancelar"}],
        ]
    }


def _anio_actual():
    """Devuelve año actual del servidor."""
    return datetime.now().year


def _teclado_calendario(callback_prefijo, mes):
    """Genera calendario inline mensual del año en curso."""
    anio = _anio_actual()
    mes = max(1, min(12, mes))
    semanas = calendar.monthcalendar(anio, mes)

    filas = [
        [{"text": f"{_MESES_ES[mes - 1]} {anio}", "callback_data": "noop"}],
        [
            {"text": "L", "callback_data": "noop"},
            {"text": "M", "callback_data": "noop"},
            {"text": "X", "callback_data": "noop"},
            {"text": "J", "callback_data": "noop"},
            {"text": "V", "callback_data": "noop"},
            {"text": "S", "callback_data": "noop"},
            {"text": "D", "callback_data": "noop"},
        ],
    ]

    for semana in semanas:
        fila = []
        for dia in semana:
            if dia == 0:
                fila.append({"text": " ", "callback_data": "noop"})
            else:
                fila.append(
                    {
                        "text": str(dia),
                        "callback_data": f"{callback_prefijo}:dia:{anio}{mes:02d}{dia:02d}",
                    }
                )
        filas.append(fila)

    nav = []
    if mes > 1:
        nav.append({"text": "⬅️", "callback_data": f"{callback_prefijo}:mes:{mes - 1}"})
    if mes < 12:
        nav.append({"text": "➡️", "callback_data": f"{callback_prefijo}:mes:{mes + 1}"})
    if nav:
        filas.append(nav)

    filas.append([{"text": "❌ Cancelar", "callback_data": "flujo:cancelar"}])
    return {"inline_keyboard": filas}


def _teclado_campos_modificar(entrega_id):
    """Botones de campos editables para una entrega."""
    return {
        "inline_keyboard": [
            [
                {"text": "Título", "callback_data": f"mod:campo:{entrega_id}:titulo"},
                {"text": "Fecha", "callback_data": f"mod:campo:{entrega_id}:fecha_entrega"},
            ],
            [
                {"text": "Tipo", "callback_data": f"mod:campo:{entrega_id}:tipo"},
                {"text": "Prioridad", "callback_data": f"mod:campo:{entrega_id}:prioridad"},
                {"text": "Estado", "callback_data": f"mod:campo:{entrega_id}:estado"},
            ],
            [
                {"text": "Nota", "callback_data": f"mod:campo:{entrega_id}:nota"},
                {"text": "Detalle", "callback_data": f"mod:campo:{entrega_id}:detalle"},
            ],
        ]
    }


def _teclado_confirmar_eliminar(entrega_id):
    """Confirmación de borrado de entrega."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Sí, eliminar", "callback_data": f"del:ok:{entrega_id}"},
                {"text": "❌ Cancelar", "callback_data": "del:no"},
            ]
        ]
    }


def _enviar_mensaje(token, chat_id, texto, teclado=None):
    """Envía mensaje simple de texto con teclado opcional."""
    payload = {"chat_id": chat_id, "text": texto}
    if teclado:
        payload["reply_markup"] = teclado

    requests.post(f"{_base_api(token)}/sendMessage", json=payload, timeout=15)


def _responder_callback(token, callback_query_id, texto=None):
    """Responde callback para evitar spinner en cliente Telegram."""
    payload = {"callback_query_id": callback_query_id}
    if texto:
        payload["text"] = texto
    requests.post(f"{_base_api(token)}/answerCallbackQuery", json=payload, timeout=15)


def _obtener_usuario_id(update):
    """Extrae id de usuario desde mensaje o callback."""
    if update.get("message"):
        return update["message"].get("from", {}).get("id")
    if update.get("callback_query"):
        return update["callback_query"].get("from", {}).get("id")
    return None


def _obtener_chat_id(update):
    if update.get("message"):
        return update["message"].get("chat", {}).get("id")
    if update.get("callback_query"):
        return update["callback_query"].get("message", {}).get("chat", {}).get("id")
    return None


def _resolver_usuario_app_por_update(update):
    """Busca usuario de app vinculado al chat Telegram del update."""
    chat_id = _obtener_chat_id(update)
    if not chat_id:
        return None
    return obtener_usuario_por_chat_telegram(chat_id)


def _procesar_comando_vincular(token, chat_id, telegram_usuario_id, texto):
    """Vincula chat Telegram con usuario web usando código temporal."""
    partes = (texto or "").split()
    if len(partes) < 2:
        _enviar_mensaje(
            token,
            chat_id,
            "Para vincular tu cuenta: /vincular CODIGO\nGenerá el código desde el panel web.",
        )
        return
    codigo = partes[1].strip()
    usuario = obtener_usuario_por_codigo_vinculacion(codigo)
    if not usuario:
        _enviar_mensaje(token, chat_id, "Código inválido o vencido. Generá uno nuevo en el panel web.")
        return

    vincular_chat_telegram(usuario, chat_id, telegram_usuario_id=telegram_usuario_id)
    registrar_chat_telegram(chat_id, usuario.id)
    _enviar_mensaje(token, chat_id, f"✅ Cuenta vinculada: {usuario.email}\nUsá /menu para comenzar.")


def _mensaje_estado_usuario(usuario_app):
    """Arma texto de estado de vinculación y habilitación de cuenta."""
    if not usuario_app:
        return (
            "Estado: chat NO vinculado.\n"
            "1) Ingresá al panel web\n"
            "2) Generá código\n"
            "3) Enviá /vincular CODIGO"
        )

    estado = "habilitada" if usuario_app.activo else "pendiente de habilitación"
    return (
        f"Cuenta vinculada: {usuario_app.email}\n"
        f"Estado de cuenta: {estado}\n"
        f"Admin: {'sí' if usuario_app.es_admin else 'no'}"
    )


def _procesar_comando_registrarme(token, chat_id, telegram_user_id, texto):
    """Registra cuenta desde Telegram y la deja pendiente de aprobación."""
    partes = (texto or "").split()
    if len(partes) < 3:
        _enviar_mensaje(
            token,
            chat_id,
            "Uso: /registrarme email contraseña\nEjemplo: /registrarme usuario@mail.com clave123",
        )
        return

    email = partes[1].strip().lower()
    password = partes[2].strip()
    if "@" not in email:
        _enviar_mensaje(token, chat_id, "Email inválido.")
        return
    if len(password) < 3:
        _enviar_mensaje(token, chat_id, "La contraseña debe tener al menos 3 caracteres.")
        return

    existente = Usuario.query.filter(bd.func.lower(Usuario.email) == email).first()
    if existente:
        _enviar_mensaje(token, chat_id, "Ese email ya existe. Si es tuyo, usá /estado o vinculá con código.")
        return

    usuario = Usuario(
        email=email,
        es_admin=False,
        activo=False,
        origen_registro="bot",
        telegram_chat_id=str(chat_id),
        telegram_usuario_id=str(telegram_user_id) if telegram_user_id is not None else None,
    )
    usuario.set_password(password)
    bd.session.add(usuario)
    bd.session.commit()

    _enviar_mensaje(
        token,
        chat_id,
        "✅ Cuenta creada desde Telegram.\nQueda pendiente de habilitación por administrador.",
    )


def _guardar_estado_usuario(usuario_id, estado):
    """Persiste estado conversacional en memoria."""
    _estado_usuarios[usuario_id] = estado


def _leer_estado_usuario(usuario_id):
    """Lee estado conversacional actual."""
    return _estado_usuarios.get(usuario_id)


def _limpiar_estado_usuario(usuario_id):
    """Borra estado conversacional para volver al menú limpio."""
    _estado_usuarios.pop(usuario_id, None)


def _parsear_fecha(texto):
    """Parsea fecha con formatos soportados por entrada de texto."""
    formatos = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]
    for formato in formatos:
        try:
            fecha = datetime.strptime(texto, formato)
            if formato == "%Y-%m-%d":
                return fecha.replace(hour=23, minute=59)
            return fecha
        except ValueError:
            continue
    return None


def _resumen_entrega(entrega):
    """Arma representación legible de una entrega para chat."""
    return (
        f"#{entrega.id} | {entrega.titulo}\n"
        f"Materia: {entrega.materia}\n"
        f"Tipo: {entrega.tipo}\n"
        f"Fecha: {entrega.fecha_entrega.strftime('%Y-%m-%d %H:%M')}\n"
        f"Prioridad: {entrega.prioridad}\n"
        f"Estado: {entrega.estado}"
    )


def _listar_entregas_token(
    token, chat_id, usuario_app_id, modo="futuras", para_modificar=False, para_eliminar=False
):
    """Lista entregas por filtro y opcionalmente agrega botones de acción."""
    ahora = datetime.now()
    consulta = Entrega.query.filter(Entrega.usuario_id == usuario_app_id)
    if modo == "futuras":
        consulta = consulta.filter(
            Entrega.fecha_entrega >= ahora,
            Entrega.estado != "entregado",
        )
    elif modo == "anteriores":
        consulta = consulta.filter(Entrega.fecha_entrega < ahora)

    entregas = consulta.order_by(Entrega.fecha_entrega.asc(), Entrega.id.asc()).limit(10).all()
    if not entregas:
        mensaje = "No hay entregas para este filtro."
        _enviar_mensaje(token, chat_id, mensaje, _teclado_principal())
        return

    _enviar_mensaje(token, chat_id, "Últimas entregas:")
    for entrega in entregas:
        teclado = None
        if para_modificar:
            teclado = {
                "inline_keyboard": [
                    [{"text": "✏️ Modificar", "callback_data": f"mod:sel:{entrega.id}"}]
                ]
            }
        elif para_eliminar:
            teclado = {
                "inline_keyboard": [
                    [{"text": "🗑️ Eliminar", "callback_data": f"del:conf:{entrega.id}"}]
                ]
            }
        _enviar_mensaje(token, chat_id, _resumen_entrega(entrega), teclado)

    if not para_modificar and not para_eliminar:
        _enviar_mensaje(token, chat_id, "Fin del listado.", _teclado_principal())


def _abrir_menu_materias(token, chat_id):
    """Abre menú de materias."""
    _enviar_mensaje(token, chat_id, "Gestión de materias:", _teclado_materias_menu())


def _listar_materias_token(token, chat_id, usuario_app_id):
    """Lista materias cargadas en base de datos."""
    materias = Materia.query.filter(Materia.usuario_id == usuario_app_id).order_by(Materia.nombre.asc()).all()
    if not materias:
        _enviar_mensaje(token, chat_id, "No hay materias cargadas.", _teclado_materias_menu())
        return

    texto = "Materias cargadas:\n" + "\n".join([f"- {materia.nombre}" for materia in materias])
    _enviar_mensaje(token, chat_id, texto, _teclado_materias_menu())


def _abrir_calendario_alta(token, chat_id, mes=None):
    """Muestra selector de fecha para alta de entrega."""
    if mes is None:
        mes = datetime.now().month
    _enviar_mensaje(
        token,
        chat_id,
        "Seleccioná la fecha de entrega (año actual):",
        _teclado_calendario("alta:fecha", mes),
    )


def _abrir_calendario_modificacion(token, chat_id, entrega_id, mes=None):
    """Muestra selector de fecha para edición de entrega."""
    if mes is None:
        mes = datetime.now().month
    _enviar_mensaje(
        token,
        chat_id,
        "Seleccioná la nueva fecha (año actual):",
        _teclado_calendario(f"mod:fecha:{entrega_id}", mes),
    )


def _procesar_flujo_alta(token, chat_id, usuario_id, texto, estado_usuario, usuario_app_id):
    """Procesa pasos secuenciales del alta de una entrega."""
    datos = estado_usuario.setdefault("datos", {})
    paso = estado_usuario.get("paso", "titulo")

    if paso == "titulo":
        datos["titulo"] = texto
        estado_usuario["paso"] = "tipo"
        _guardar_estado_usuario(usuario_id, estado_usuario)
        _enviar_mensaje(
            token,
            chat_id,
            "Seleccioná el tipo de entrega:",
            _teclado_tipos_entrega("alta:tipo"),
        )
        return

    if paso == "tipo":
        _enviar_mensaje(token, chat_id, "Usá los botones para elegir tipo.", _teclado_tipos_entrega("alta:tipo"))
        return

    if paso == "fecha_entrega":
        _abrir_calendario_alta(token, chat_id)
        return

    if paso == "prioridad":
        _enviar_mensaje(
            token,
            chat_id,
            "Usá los botones para elegir prioridad.",
            teclado=_teclado_prioridades("alta:prioridad"),
        )
        return

    if paso == "estado":
        _enviar_mensaje(
            token,
            chat_id,
            "Usá los botones para elegir estado.",
            teclado=_teclado_estados("alta:estado"),
        )
        return

    if paso == "detalle":
        detalle = None if texto == "-" else texto
        entrega = Entrega(
            usuario_id=usuario_app_id,
            materia=datos["materia"],
            titulo=datos["titulo"],
            tipo=datos["tipo"],
            fecha_entrega=datos["fecha_entrega"],
            prioridad=datos["prioridad"],
            estado=datos["estado"],
            detalle=detalle,
            origen="telegram",
        )
        bd.session.add(entrega)
        bd.session.commit()
        _limpiar_estado_usuario(usuario_id)
        _enviar_mensaje(
            token,
            chat_id,
            f"Entrega creada con ID #{entrega.id}.",
            teclado=_teclado_principal(),
        )


def _seleccionar_materia_alta(token, chat_id, usuario_id, usuario_app_id, materia_id):
    """Guarda materia elegida y avanza al título."""
    materia = Materia.query.filter_by(id=materia_id, usuario_id=usuario_app_id).first()
    if not materia:
        _enviar_mensaje(token, chat_id, "Materia no encontrada.", _teclado_principal())
        return

    estado_usuario = _leer_estado_usuario(usuario_id) or {}
    if estado_usuario.get("modo") != "alta":
        _enviar_mensaje(token, chat_id, "No hay una alta en curso.", _teclado_principal())
        return

    datos = estado_usuario.setdefault("datos", {})
    datos["materia"] = materia.nombre
    estado_usuario["paso"] = "titulo"
    _guardar_estado_usuario(usuario_id, estado_usuario)
    _enviar_mensaje(token, chat_id, f"Materia seleccionada: {materia.nombre}\nIngresá el título.")


def _seleccionar_tipo_alta(token, chat_id, usuario_id, tipo):
    """Guarda tipo elegido y abre calendario de fecha."""
    tipo_normalizado = _TIPOS_ENTREGA.get(tipo, tipo)
    if tipo_normalizado not in _TIPOS_ENTREGA.values():
        _enviar_mensaje(token, chat_id, "Tipo inválido.", _teclado_principal())
        return

    estado_usuario = _leer_estado_usuario(usuario_id) or {}
    if estado_usuario.get("modo") != "alta":
        _enviar_mensaje(token, chat_id, "No hay una alta en curso.", _teclado_principal())
        return

    datos = estado_usuario.setdefault("datos", {})
    datos["tipo"] = tipo_normalizado
    estado_usuario["paso"] = "fecha_entrega"
    _guardar_estado_usuario(usuario_id, estado_usuario)
    _abrir_calendario_alta(token, chat_id)


def _seleccionar_fecha_alta(token, chat_id, usuario_id, fecha_yyyymmdd):
    """Guarda fecha elegida y avanza a prioridad."""
    try:
        fecha_base = datetime.strptime(fecha_yyyymmdd, "%Y%m%d")
    except ValueError:
        _enviar_mensaje(token, chat_id, "Fecha inválida.", _teclado_principal())
        return

    if fecha_base.year != _anio_actual():
        _enviar_mensaje(token, chat_id, "Solo se permite seleccionar fechas del año actual.")
        return

    estado_usuario = _leer_estado_usuario(usuario_id) or {}
    if estado_usuario.get("modo") != "alta":
        _enviar_mensaje(token, chat_id, "No hay una alta en curso.", _teclado_principal())
        return

    datos = estado_usuario.setdefault("datos", {})
    datos["fecha_entrega"] = fecha_base.replace(hour=23, minute=59)
    estado_usuario["paso"] = "prioridad"
    _guardar_estado_usuario(usuario_id, estado_usuario)
    _enviar_mensaje(
        token,
        chat_id,
        f"Fecha seleccionada: {fecha_base.strftime('%Y-%m-%d')}\nSeleccioná la prioridad:",
        _teclado_prioridades("alta:prioridad"),
    )


def _seleccionar_fecha_modificacion(token, chat_id, usuario_app_id, entrega_id, fecha_yyyymmdd):
    """Actualiza la fecha de una entrega desde selector inline."""
    try:
        fecha_base = datetime.strptime(fecha_yyyymmdd, "%Y%m%d")
    except ValueError:
        _enviar_mensaje(token, chat_id, "Fecha inválida.", _teclado_principal())
        return

    if fecha_base.year != _anio_actual():
        _enviar_mensaje(token, chat_id, "Solo se permite seleccionar fechas del año actual.")
        return

    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app_id).first()
    if not entrega:
        _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
        return

    entrega.fecha_entrega = entrega.fecha_entrega.replace(
        year=fecha_base.year,
        month=fecha_base.month,
        day=fecha_base.day,
    )
    bd.session.commit()
    _enviar_mensaje(
        token,
        chat_id,
        f"Entrega #{entrega.id} actualizada con fecha {fecha_base.strftime('%Y-%m-%d')}.",
        _teclado_principal(),
    )


def _procesar_flujo_alta_materia(token, chat_id, usuario_id, usuario_app_id, texto):
    """Crea una materia nueva validando duplicados por nombre."""
    nombre = texto.strip()
    if not nombre:
        _enviar_mensaje(token, chat_id, "Nombre inválido. Probá de nuevo.", _teclado_cancelar())
        return

    existente = Materia.query.filter(
        Materia.usuario_id == usuario_app_id,
        bd.func.lower(Materia.nombre) == nombre.lower(),
    ).first()
    if existente:
        _enviar_mensaje(token, chat_id, "Esa materia ya existe.", _teclado_materias_menu())
        _limpiar_estado_usuario(usuario_id)
        return

    materia = Materia(usuario_id=usuario_app_id, nombre=nombre)
    bd.session.add(materia)
    bd.session.commit()
    _limpiar_estado_usuario(usuario_id)
    _enviar_mensaje(token, chat_id, f"Materia creada: {materia.nombre}", _teclado_materias_menu())


def _seleccionar_prioridad_alta(token, chat_id, usuario_id, prioridad):
    """Guarda prioridad y avanza al estado inicial."""
    if prioridad not in {"alta", "media", "baja"}:
        _enviar_mensaje(token, chat_id, "Prioridad inválida.", _teclado_principal())
        return

    estado_usuario = _leer_estado_usuario(usuario_id) or {}
    if estado_usuario.get("modo") != "alta":
        _enviar_mensaje(token, chat_id, "No hay una alta en curso.", _teclado_principal())
        return

    datos = estado_usuario.setdefault("datos", {})
    datos["prioridad"] = prioridad
    estado_usuario["paso"] = "estado"
    _guardar_estado_usuario(usuario_id, estado_usuario)
    _enviar_mensaje(
        token,
        chat_id,
        "Seleccioná el estado inicial:",
        teclado=_teclado_estados("alta:estado"),
    )


def _seleccionar_estado_alta(token, chat_id, usuario_id, estado):
    """Guarda estado inicial y avanza al detalle."""
    if estado not in {"pendiente", "entregado"}:
        _enviar_mensaje(token, chat_id, "Estado inválido.", _teclado_principal())
        return

    estado_usuario = _leer_estado_usuario(usuario_id) or {}
    if estado_usuario.get("modo") != "alta":
        _enviar_mensaje(token, chat_id, "No hay una alta en curso.", _teclado_principal())
        return

    datos = estado_usuario.setdefault("datos", {})
    datos["estado"] = estado
    estado_usuario["paso"] = "detalle"
    _guardar_estado_usuario(usuario_id, estado_usuario)
    _enviar_mensaje(token, chat_id, "Ingresá detalle (o '-' para vacío).", _teclado_cancelar())


def _procesar_flujo_modificacion(token, chat_id, usuario_id, usuario_app_id, texto, estado_usuario):
    """Actualiza campos libres de una entrega durante edición."""
    entrega_id = estado_usuario.get("entrega_id")
    campo = estado_usuario.get("campo")
    if not entrega_id or not campo:
        _limpiar_estado_usuario(usuario_id)
        _enviar_mensaje(token, chat_id, "Estado inválido. Volvé al menú.", _teclado_principal())
        return

    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app_id).first()
    if not entrega:
        _limpiar_estado_usuario(usuario_id)
        _enviar_mensaje(token, chat_id, "La entrega ya no existe.", _teclado_principal())
        return

    if campo == "fecha_entrega":
        _abrir_calendario_modificacion(token, chat_id, entrega_id)
        return
    elif campo == "tipo":
        tipo = texto.lower().strip().replace("á", "a")
        if tipo not in _TIPOS_ENTREGA.values():
            _enviar_mensaje(
                token,
                chat_id,
                "Tipo inválido. Usá botones o uno de: trabajo practico, parcial, lectura, cuestionario, otro.",
            )
            return
        entrega.tipo = tipo
    elif campo == "prioridad":
        prioridad = texto.lower()
        if prioridad not in {"alta", "media", "baja"}:
            _enviar_mensaje(token, chat_id, "Prioridad inválida. Usá: alta, media o baja.")
            return
        entrega.prioridad = prioridad
    elif campo == "estado":
        estado = texto.lower()
        if estado not in {"pendiente", "entregado"}:
            _enviar_mensaje(token, chat_id, "Estado inválido. Usá: pendiente o entregado.")
            return
        entrega.estado = estado
    elif campo == "nota":
        try:
            entrega.nota = float(texto)
        except ValueError:
            _enviar_mensaje(token, chat_id, "Nota inválida. Ejemplo: 8.5")
            return
    elif campo == "detalle":
        entrega.detalle = None if texto == "-" else texto
    elif campo == "titulo":
        entrega.titulo = texto
    else:
        _enviar_mensaje(token, chat_id, "Campo no soportado.", _teclado_principal())
        return

    bd.session.commit()
    _limpiar_estado_usuario(usuario_id)
    _enviar_mensaje(
        token,
        chat_id,
        f"Entrega #{entrega.id} actualizada.",
        teclado=_teclado_principal(),
    )


def _modificar_prioridad_desde_boton(token, chat_id, usuario_app_id, entrega_id, prioridad):
    """Modifica prioridad en un solo click."""
    if prioridad not in {"alta", "media", "baja"}:
        _enviar_mensaje(token, chat_id, "Prioridad inválida.", _teclado_principal())
        return

    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app_id).first()
    if not entrega:
        _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
        return

    entrega.prioridad = prioridad
    bd.session.commit()
    _enviar_mensaje(token, chat_id, f"Entrega #{entrega.id} actualizada.", _teclado_principal())


def _modificar_estado_desde_boton(token, chat_id, usuario_app_id, entrega_id, estado):
    """Modifica estado en un solo click."""
    if estado not in {"pendiente", "entregado"}:
        _enviar_mensaje(token, chat_id, "Estado inválido.", _teclado_principal())
        return

    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app_id).first()
    if not entrega:
        _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
        return

    entrega.estado = estado
    bd.session.commit()
    _enviar_mensaje(token, chat_id, f"Entrega #{entrega.id} actualizada.", _teclado_principal())


def _modificar_tipo_desde_boton(token, chat_id, usuario_app_id, entrega_id, tipo):
    """Modifica tipo en un solo click."""
    tipo_normalizado = _TIPOS_ENTREGA.get(tipo, tipo)
    if tipo_normalizado not in _TIPOS_ENTREGA.values():
        _enviar_mensaje(token, chat_id, "Tipo inválido.", _teclado_principal())
        return

    entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app_id).first()
    if not entrega:
        _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
        return

    entrega.tipo = tipo_normalizado
    bd.session.commit()
    _enviar_mensaje(token, chat_id, f"Entrega #{entrega.id} actualizada.", _teclado_principal())


def procesar_update_telegram(update, token):
    """Dispatcher principal de updates (mensaje y callbacks inline)."""
    mensaje = update.get("message")
    usuario_estado_id = _obtener_usuario_id(update)
    usuario_app = _resolver_usuario_app_por_update(update)

    if mensaje:
        chat_id = mensaje.get("chat", {}).get("id")
        telegram_user_id = mensaje.get("from", {}).get("id")
        texto = (mensaje.get("text") or "").strip()
        if not chat_id:
            return

        if texto.lower().startswith("/estado"):
            _enviar_mensaje(token, chat_id, _mensaje_estado_usuario(usuario_app))
            return

        if texto.lower().startswith("/vincular"):
            _procesar_comando_vincular(token, chat_id, telegram_user_id, texto)
            return

        if texto.lower().startswith("/registrarme"):
            _procesar_comando_registrarme(token, chat_id, telegram_user_id, texto)
            return

        if not usuario_app:
            _enviar_mensaje(
                token,
                chat_id,
                "Tu chat no está vinculado.\n1) Ingresá al panel web\n2) Generá código de vinculación\n3) Enviá /vincular CODIGO",
            )
            return

        if not usuario_app.activo:
            _enviar_mensaje(
                token,
                chat_id,
                "Tu cuenta está pendiente de habilitación por administrador.\nPodés consultar con /estado.",
            )
            return

        registrar_chat_telegram(chat_id, usuario_app.id)

        if texto.lower() in {"/start", "/menu", "menu"}:
            _limpiar_estado_usuario(usuario_estado_id)
            mensaje_inicio = "Menú principal del asistente"
            if usuario_app and getattr(usuario_app, "email", None):
                mensaje_inicio = f"Menú principal del asistente\nCuenta vinculada: {usuario_app.email}"
            _enviar_mensaje(
                token,
                chat_id,
                mensaje_inicio,
                teclado=_teclado_principal(),
            )
            return

        estado_usuario = _leer_estado_usuario(usuario_estado_id)
        if estado_usuario and estado_usuario.get("modo") == "alta":
            _procesar_flujo_alta(token, chat_id, usuario_estado_id, texto, estado_usuario, usuario_app.id)
            return

        if estado_usuario and estado_usuario.get("modo") == "alta_materia":
            _procesar_flujo_alta_materia(token, chat_id, usuario_estado_id, usuario_app.id, texto)
            return

        if estado_usuario and estado_usuario.get("modo") == "modificacion":
            _procesar_flujo_modificacion(token, chat_id, usuario_estado_id, usuario_app.id, texto, estado_usuario)
            return

        _enviar_mensaje(
            token,
            chat_id,
            "Usá /menu para operar con botones inline.",
            teclado=_teclado_principal(),
        )
        return

    callback_query = update.get("callback_query")
    if not callback_query:
        return

    callback_id = callback_query.get("id")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    telegram_user_id = callback_query.get("from", {}).get("id")
    accion = callback_query.get("data", "")

    if callback_id:
        _responder_callback(token, callback_id)

    if not chat_id:
        return

    if accion.startswith("vincular:"):
        _procesar_comando_vincular(token, chat_id, telegram_user_id, f"/vincular {accion.split(':', 1)[1]}")
        return

    if not usuario_app:
        _enviar_mensaje(
            token,
            chat_id,
            "Tu chat no está vinculado. Generá código en el panel y enviá /vincular CODIGO.",
        )
        return

    if not usuario_app.activo:
        _enviar_mensaje(
            token,
            chat_id,
            "Tu cuenta está pendiente de habilitación por administrador.\nPodés consultar con /estado.",
        )
        return

    registrar_chat_telegram(chat_id, usuario_app.id)

    if accion == "noop":
        return

    if accion == "menu:agregar":
        teclado_materias = _teclado_materias_para_entrega(usuario_app.id)
        if not teclado_materias:
            _enviar_mensaje(
                token,
                chat_id,
                "No hay materias cargadas. Primero agregá una en 📚 Materias.",
                _teclado_principal(),
            )
            return
        _guardar_estado_usuario(usuario_estado_id, {"modo": "alta", "paso": "titulo", "datos": {}})
        _enviar_mensaje(token, chat_id, "Seleccioná la materia de la entrega:", teclado_materias)
        return

    if accion == "menu:listar":
        _limpiar_estado_usuario(usuario_estado_id)
        _enviar_mensaje(token, chat_id, "Elegí el tipo de listado:", _teclado_listados_entregas())
        return

    if accion == "listar:futuras":
        _limpiar_estado_usuario(usuario_estado_id)
        _listar_entregas_token(token, chat_id, usuario_app.id, modo="futuras")
        return

    if accion == "listar:anteriores":
        _limpiar_estado_usuario(usuario_estado_id)
        _listar_entregas_token(token, chat_id, usuario_app.id, modo="anteriores")
        return

    if accion == "menu:modificar":
        _limpiar_estado_usuario(usuario_estado_id)
        _listar_entregas_token(token, chat_id, usuario_app.id, modo="todas", para_modificar=True)
        return

    if accion == "menu:eliminar":
        _limpiar_estado_usuario(usuario_estado_id)
        _listar_entregas_token(token, chat_id, usuario_app.id, modo="todas", para_eliminar=True)
        return

    if accion == "menu:materias":
        _limpiar_estado_usuario(usuario_estado_id)
        _abrir_menu_materias(token, chat_id)
        return

    if accion == "mat:agregar":
        _guardar_estado_usuario(usuario_estado_id, {"modo": "alta_materia"})
        _enviar_mensaje(token, chat_id, "Ingresá el nombre de la materia:", _teclado_cancelar())
        return

    if accion == "mat:listar":
        _listar_materias_token(token, chat_id, usuario_app.id)
        return

    if accion == "mat:eliminar":
        teclado = _teclado_materias_para_eliminar(usuario_app.id)
        if not teclado:
            _enviar_mensaje(token, chat_id, "No hay materias para eliminar.", _teclado_materias_menu())
            return
        _enviar_mensaje(token, chat_id, "Seleccioná la materia a eliminar:", teclado)
        return

    if accion.startswith("mat:eliminar:"):
        try:
            materia_id = int(accion.split(":")[2])
        except (IndexError, ValueError):
            _enviar_mensaje(token, chat_id, "Materia inválida.", _teclado_materias_menu())
            return
        materia = Materia.query.filter_by(id=materia_id, usuario_id=usuario_app.id).first()
        if not materia:
            _enviar_mensaje(token, chat_id, "Materia no encontrada.", _teclado_materias_menu())
            return
        tiene_entregas = (
            Entrega.query.filter(
                Entrega.usuario_id == usuario_app.id,
                Entrega.materia == materia.nombre,
            ).first()
            is not None
        )
        if tiene_entregas:
            _enviar_mensaje(
                token,
                chat_id,
                "No se puede eliminar: la materia tiene entregas asociadas.",
                _teclado_materias_menu(),
            )
            return
        bd.session.delete(materia)
        bd.session.commit()
        _enviar_mensaje(token, chat_id, f"Materia eliminada: {materia.nombre}", _teclado_materias_menu())
        return

    if accion.startswith("mod:sel:"):
        try:
            entrega_id = int(accion.split(":")[2])
        except (IndexError, ValueError):
            _enviar_mensaje(token, chat_id, "ID inválido.", _teclado_principal())
            return
        entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app.id).first()
        if not entrega:
            _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
            return
        _enviar_mensaje(
            token,
            chat_id,
            f"Elegí campo a modificar de la entrega #{entrega_id}.",
            _teclado_campos_modificar(entrega_id),
        )
        return

    if accion.startswith("mod:campo:"):
        try:
            _, _, entrega_id, campo = accion.split(":", 3)
            entrega_id = int(entrega_id)
        except (ValueError, IndexError):
            _enviar_mensaje(token, chat_id, "Acción inválida.", _teclado_principal())
            return
        if campo == "fecha_entrega":
            _abrir_calendario_modificacion(token, chat_id, entrega_id)
            return
        if campo == "tipo":
            _enviar_mensaje(
                token,
                chat_id,
                "Seleccioná el nuevo tipo de entrega:",
                teclado=_teclado_tipos_entrega(f"mod:valor:{entrega_id}:tipo"),
            )
            return
        if campo == "prioridad":
            _enviar_mensaje(
                token,
                chat_id,
                "Seleccioná la nueva prioridad:",
                teclado=_teclado_prioridades(f"mod:valor:{entrega_id}:prioridad"),
            )
            return
        if campo == "estado":
            _enviar_mensaje(
                token,
                chat_id,
                "Seleccioná el nuevo estado:",
                teclado=_teclado_estados(f"mod:valor:{entrega_id}:estado"),
            )
            return
        _guardar_estado_usuario(
            usuario_estado_id,
            {"modo": "modificacion", "entrega_id": entrega_id, "campo": campo},
        )
        mensajes = {
            "titulo": "Ingresá el nuevo título.",
            "fecha_entrega": "Ingresá la nueva fecha (YYYY-MM-DD HH:MM o YYYY-MM-DD).",
            "nota": "Ingresá la nota (número, ejemplo 8.5).",
            "detalle": "Ingresá el detalle (o '-' para vacío).",
        }
        _enviar_mensaje(
            token,
            chat_id,
            mensajes.get(campo, "Ingresá el nuevo valor."),
            _teclado_cancelar(),
        )
        return

    if accion == "flujo:cancelar":
        _limpiar_estado_usuario(usuario_estado_id)
        _enviar_mensaje(token, chat_id, "Operación cancelada.", _teclado_principal())
        return

    if accion.startswith("alta:materia:"):
        try:
            materia_id = int(accion.rsplit(":", 1)[1])
        except ValueError:
            _enviar_mensaje(token, chat_id, "Materia inválida.", _teclado_principal())
            return
        _seleccionar_materia_alta(token, chat_id, usuario_estado_id, usuario_app.id, materia_id)
        return

    if accion.startswith("alta:tipo:"):
        tipo = accion.rsplit(":", 1)[1]
        _seleccionar_tipo_alta(token, chat_id, usuario_id, tipo)
        return

    if accion.startswith("alta:fecha:mes:"):
        try:
            mes = int(accion.rsplit(":", 1)[1])
        except ValueError:
            _enviar_mensaje(token, chat_id, "Mes inválido.", _teclado_principal())
            return
        _abrir_calendario_alta(token, chat_id, mes)
        return

    if accion.startswith("alta:fecha:dia:"):
        fecha_yyyymmdd = accion.rsplit(":", 1)[1]
        _seleccionar_fecha_alta(token, chat_id, usuario_estado_id, fecha_yyyymmdd)
        return

    if accion.startswith("alta:prioridad:"):
        prioridad = accion.rsplit(":", 1)[1]
        _seleccionar_prioridad_alta(token, chat_id, usuario_estado_id, prioridad)
        return

    if accion.startswith("alta:estado:"):
        estado = accion.rsplit(":", 1)[1]
        _seleccionar_estado_alta(token, chat_id, usuario_estado_id, estado)
        return

    if accion.startswith("mod:valor:"):
        partes = accion.split(":")
        if len(partes) != 5:
            _enviar_mensaje(token, chat_id, "Acción inválida.", _teclado_principal())
            return
        _, _, entrega_id_str, campo, valor = partes
        try:
            entrega_id = int(entrega_id_str)
        except ValueError:
            _enviar_mensaje(token, chat_id, "ID inválido.", _teclado_principal())
            return
        if campo == "tipo":
            _modificar_tipo_desde_boton(token, chat_id, usuario_app.id, entrega_id, valor)
            return
        if campo == "prioridad":
            _modificar_prioridad_desde_boton(token, chat_id, usuario_app.id, entrega_id, valor)
            return
        if campo == "estado":
            _modificar_estado_desde_boton(token, chat_id, usuario_app.id, entrega_id, valor)
            return
        _enviar_mensaje(token, chat_id, "Campo no soportado.", _teclado_principal())
        return

    if accion.startswith("mod:fecha:"):
        partes = accion.split(":")
        if len(partes) != 5:
            _enviar_mensaje(token, chat_id, "Acción inválida.", _teclado_principal())
            return
        _, _, entrega_id_str, tipo_accion, valor = partes
        try:
            entrega_id = int(entrega_id_str)
        except ValueError:
            _enviar_mensaje(token, chat_id, "ID inválido.", _teclado_principal())
            return
        if tipo_accion == "mes":
            try:
                mes = int(valor)
            except ValueError:
                _enviar_mensaje(token, chat_id, "Mes inválido.", _teclado_principal())
                return
            _abrir_calendario_modificacion(token, chat_id, entrega_id, mes)
            return
        if tipo_accion == "dia":
            _seleccionar_fecha_modificacion(token, chat_id, usuario_app.id, entrega_id, valor)
            return
        _enviar_mensaje(token, chat_id, "Acción inválida.", _teclado_principal())
        return

    if accion.startswith("del:conf:"):
        try:
            entrega_id = int(accion.split(":")[2])
        except (ValueError, IndexError):
            _enviar_mensaje(token, chat_id, "ID inválido.", _teclado_principal())
            return
        entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app.id).first()
        if not entrega:
            _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
            return
        _enviar_mensaje(
            token,
            chat_id,
            f"Confirmar eliminación de #{entrega.id} - {entrega.titulo}?",
            _teclado_confirmar_eliminar(entrega.id),
        )
        return

    if accion.startswith("del:ok:"):
        try:
            entrega_id = int(accion.split(":")[2])
        except (ValueError, IndexError):
            _enviar_mensaje(token, chat_id, "ID inválido.", _teclado_principal())
            return
        entrega = Entrega.query.filter_by(id=entrega_id, usuario_id=usuario_app.id).first()
        if not entrega:
            _enviar_mensaje(token, chat_id, "Entrega no encontrada.", _teclado_principal())
            return
        bd.session.delete(entrega)
        bd.session.commit()
        _enviar_mensaje(token, chat_id, f"Entrega #{entrega_id} eliminada.", _teclado_principal())
        return

    if accion == "del:no":
        _enviar_mensaje(token, chat_id, "Eliminación cancelada.", _teclado_principal())
        return

    _enviar_mensaje(token, chat_id, "Acción no reconocida.", _teclado_principal())


def _loop_long_polling(token, aplicacion):
    """Loop bloqueante de `getUpdates` con offset incremental."""
    offset = None
    url = f"{_base_api(token)}/getUpdates"
    logger.warning("Long polling de Telegram en ejecución")

    while not _detener_long_polling.is_set():
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            respuesta = requests.get(url, params=params, timeout=35)
            data = respuesta.json()
            if not data.get("ok"):
                logger.warning("Respuesta Telegram no OK en getUpdates: %s", data)
                time.sleep(2)
                continue

            resultados = data.get("result", [])
            for update in resultados:
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1
                with aplicacion.app_context():
                    procesar_update_telegram(update, token)
        except Exception:
            logger.exception("Error en long polling de Telegram")
            time.sleep(2)


def iniciar_long_polling_si_corresponde(aplicacion=None):
    """Arranca hilo daemon de long polling según configuración."""
    global _hilo_long_polling

    if _hilo_long_polling and _hilo_long_polling.is_alive():
        logger.warning("Long polling ya estaba activo")
        return

    if aplicacion is None:
        try:
            aplicacion = current_app._get_current_object()
        except RuntimeError:
            logger.warning("No se pudo iniciar long polling: sin contexto de app")
            return

    modo_bot = aplicacion.config.get("MODO_BOT")
    token = aplicacion.config.get("TOKEN_BOT_TELEGRAM")
    if modo_bot != "long_polling":
        logger.warning("Long polling no iniciado: MODO_BOT=%s", modo_bot)
        return
    if not token:
        logger.warning("Long polling no iniciado: TOKEN_BOT_TELEGRAM vacío")
        return

    _detener_long_polling.clear()
    _hilo_long_polling = threading.Thread(
        target=_loop_long_polling,
        args=(token, aplicacion),
        daemon=True,
        name="telegram-long-polling",
    )
    _hilo_long_polling.start()
    logger.warning("Long polling de Telegram iniciado")
