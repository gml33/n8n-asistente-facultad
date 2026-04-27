# Asistente Facultad

Aplicación web y bot de Telegram para centralizar entregas, materias, recordatorios y eventos académicos importados desde un calendario de campus en formato iCalendar.

El proyecto nace para resolver un problema concreto: cuando las fechas importantes quedan repartidas entre el campus virtual, chats, notas personales y recordatorios manuales, es fácil perder visibilidad. Este asistente consolida esa información en un panel único, permite cargar tareas desde Telegram y automatiza avisos para reducir olvidos.

## Qué problema resuelve

- Reúne entregas, parciales, trabajos prácticos y materias en un solo lugar.
- Sincroniza eventos publicados por el campus mediante URL ICS.
- Envía recordatorios por Telegram con una ventana configurable.
- Permite operar desde web o desde bot, sin depender siempre del panel.
- Aísla los datos por usuario, incluyendo materias, entregas y configuración.
- Incluye administración básica de cuentas para habilitar usuarios registrados.

## Funcionalidades principales

- Panel web con login, registro, métricas y gestión de entregas.
- Alta, edición, filtros, cambio de estado y eliminación de entregas.
- Gestión de materias por usuario.
- Bot de Telegram con menús inline para cargar, listar, modificar y eliminar entregas.
- Vinculación segura de Telegram por código temporal.
- Registro desde Telegram con aprobación posterior de administrador.
- Sincronización automática y manual de calendario académico ICS.
- Notificaciones programadas por Telegram.
- Configuración editable desde el panel: zona horaria, bot, campus, frecuencia de avisos y modo de ejecución.
- Despliegue local con Docker Compose y despliegue en VPS/Portainer con Docker Swarm.

## Ventajas de implementación

- Arquitectura simple y portable: Flask, PostgreSQL, Docker y Telegram Bot API.
- Sincronización desacoplada: APScheduler ejecuta tareas periódicas sin requerir servicios externos adicionales.
- Seguridad práctica para un MVP real: sesiones HTTP-only, hashes de contraseña, configuración por variables de entorno y validación estricta en producción.
- Multiusuario desde el modelo de datos: cada usuario conserva su propio conjunto de entregas, materias y credenciales de integración.
- Integración flexible con Telegram: long polling para desarrollo local y webhook para producción.
- Preparado para demo técnica: endpoints claros, panel funcional, bot operativo y documentación de despliegue.

## Stack técnico

- Python 3.12
- Flask 3
- Flask-SQLAlchemy
- PostgreSQL 16
- APScheduler
- Requests
- iCalendar
- Gunicorn
- Docker / Docker Compose

## Estructura del repositorio

```text
.
├── Dockerfile
├── docker-compose.yml
├── docker-stack.portainer.yml
├── src
│   ├── app
│   │   ├── routes
│   │   ├── static
│   │   ├── templates
│   │   ├── telegram_bot.py
│   │   ├── sincronizador_campus.py
│   │   ├── programador_tareas.py
│   │   └── models.py
│   ├── config.py
│   ├── requirements.txt
│   └── run.py
├── .env.example
└── .env.production.example
```

## Configuración segura

El repositorio no debe versionar credenciales reales. Usá `.env.example` como plantilla local y mantené tu `.env` fuera de Git.

Variables principales:

```env
ENTORNO=desarrollo
CLAVE_SECRETA=cambiar-esta-clave
ZONA_HORARIA=America/Argentina/Cordoba

ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=cambiar-admin-dev

NOMBRE_BD=asistente_facultad
USUARIO_BD=postgres
CLAVE_BD=postgres
PUERTO_BD_LOCAL=5433
URL_BASE_DATOS=postgresql+psycopg://postgres:postgres@base_datos:5432/asistente_facultad

MODO_BOT=long_polling
TOKEN_BOT_TELEGRAM=
SECRETO_WEBHOOK_TELEGRAM=

CAMPUS_CALENDARIO_URL=
SINCRONIZACION_CAMPUS_ACTIVA=true
MINUTOS_SINCRONIZACION_CAMPUS=30
```

En producción (`ENTORNO=produccion`) la aplicación corta el arranque si detecta valores inseguros para `CLAVE_SECRETA`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` o el secreto de webhook cuando corresponde.

## Ejecución local

1. Crear archivo de entorno:

```bash
cp .env.example .env
```

2. Ajustar credenciales locales y, si vas a usar Telegram, cargar `TOKEN_BOT_TELEGRAM`.

3. Levantar servicios:

```bash
docker compose up --build
```

4. Abrir:

- Panel: `http://localhost:5000`
- Login: `http://localhost:5000/login`
- Registro: `http://localhost:5000/registro`
- Healthcheck: `http://localhost:5000/api/salud`
- PostgreSQL local: `localhost:5433`

## Uso con Telegram

Para desarrollo local:

```env
MODO_BOT=long_polling
TOKEN_BOT_TELEGRAM=token-del-bot
```

Comandos soportados:

- `/start` o `/menu`: abre el menú principal.
- `/estado`: muestra si el chat está vinculado y si la cuenta está habilitada.
- `/registrarme email contraseña`: crea una cuenta pendiente de aprobación.
- `/vincular CODIGO`: vincula una cuenta web con el chat actual.

Desde el panel web, cada usuario puede generar un código temporal en Configuración y enviarlo al bot con `/vincular CODIGO`.

## Sincronización de campus

El sistema acepta una URL iCalendar/ICS del campus virtual. Con esa URL puede importar eventos académicos como entregas de origen `campus`.

- Configuración por usuario desde el panel.
- Sincronización automática cada `MINUTOS_SINCRONIZACION_CAMPUS`.
- Sincronización manual con `POST /api/sincronizacion/campus`.
- Asociación automática de eventos con materias existentes cuando encuentra coincidencias.

## API principal

- `GET /api/salud`
- `GET /api/entregas`
- `POST /api/entregas`
- `PUT /api/entregas/<id>`
- `DELETE /api/entregas/<id>`
- `GET /api/materias`
- `POST /api/materias`
- `DELETE /api/materias/<id>`
- `GET /api/configuracion/sistema`
- `PUT /api/configuracion/sistema`
- `GET /api/configuracion/notificaciones`
- `PUT /api/configuracion/notificaciones`
- `POST /api/configuracion/notificaciones/probar`
- `POST /api/sincronizacion/campus`
- `GET /api/telegram/vinculacion`
- `POST /api/telegram/vinculacion/generar`
- `DELETE /api/telegram/vinculacion`
- `POST /api/telegram/webhook`

## Despliegue en Portainer / Docker Swarm

El archivo base es `docker-stack.portainer.yml`.

Supuestos:

- Traefik ya está publicado en la red externa `traefik_public`.
- Existe la red externa compartida `general_network`.
- PostgreSQL está disponible como `postgres:5432` dentro de `general_network`.
- La base `asistente_facultad` ya existe.
- El DNS público apunta al VPS.

Variables sugeridas para el stack:

```env
IMAGEN_ASISTENTE=asistente-facultad:latest
CLAVE_SECRETA=valor-largo-aleatorio
ADMIN_EMAIL=admin@tu-dominio.com
ADMIN_PASSWORD=clave-fuerte
POSTGRES_PASSWORD=clave-postgres-del-vps
ZONA_HORARIA=America/Argentina/Cordoba
MODO_BOT=webhook
TOKEN_BOT_TELEGRAM=token-del-bot
SECRETO_WEBHOOK_TELEGRAM=valor-largo-aleatorio
SINCRONIZACION_CAMPUS_ACTIVA=true
MINUTOS_SINCRONIZACION_CAMPUS=30
```

Configurar webhook de Telegram:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN_BOT_TELEGRAM>/setWebhook" \
  -d "url=https://tu-dominio.com/api/telegram/webhook" \
  -d "secret_token=<SECRETO_WEBHOOK_TELEGRAM>"
```

## Estado del proyecto

El proyecto está preparado como MVP funcional para portfolio: resuelve una necesidad concreta, muestra integración entre web, base de datos, jobs programados y bot conversacional, y puede evolucionar hacia analíticas académicas, integración con más calendarios o reglas de priorización inteligente.
