"""Inicialización principal de la aplicación Flask.

Define el patrón factory para crear la app, registrar blueprints, preparar
base de datos e iniciar procesos en background (bot/scheduler).
"""

from flask import Flask

from config import Configuracion
from config import validar_configuracion_produccion

from .autenticacion import asegurar_usuario_admin_desde_config
from .configuracion_sistema import aplicar_ajustes_sistema_a_config
from .evolucion_esquema import aplicar_evolucion_esquema
from .extensions import bd
from .programador_tareas import iniciar_programador_si_corresponde
from .routes.api import rutas_api
from .routes.web import rutas_web
from .telegram_bot import iniciar_long_polling_si_corresponde


def crear_aplicacion():
    """Construye y configura una instancia lista para ejecutar."""
    aplicacion = Flask(__name__)
    aplicacion.config.from_object(Configuracion)
    validar_configuracion_produccion(aplicacion.config)

    # Inicializa extensiones y endpoints HTTP.
    bd.init_app(aplicacion)
    aplicacion.register_blueprint(rutas_api)
    aplicacion.register_blueprint(rutas_web)

    # Prepara esquema y servicios auxiliares al levantar la app.
    with aplicacion.app_context():
        bd.create_all()
        aplicar_evolucion_esquema()
        asegurar_usuario_admin_desde_config()
        aplicar_ajustes_sistema_a_config(aplicacion)
        iniciar_long_polling_si_corresponde(aplicacion)
        iniciar_programador_si_corresponde(aplicacion)

    return aplicacion
