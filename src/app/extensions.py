"""Extensiones compartidas de Flask para toda la aplicación.

Centraliza la inicialización de objetos globales (por ahora SQLAlchemy) para
evitar ciclos de importación y permitir el patrón factory.
"""

from flask_sqlalchemy import SQLAlchemy

# Instancia única de SQLAlchemy reutilizada por modelos y rutas.
bd = SQLAlchemy()
