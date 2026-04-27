"""Punto de entrada local para ejecutar el servidor Flask."""

from app import crear_aplicacion

# Instancia WSGI consumida por flask/servidores.
aplicacion = crear_aplicacion()


if __name__ == "__main__":
    # Modo desarrollo local.
    aplicacion.run(host="0.0.0.0", port=5000)
