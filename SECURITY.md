# Seguridad

Este repositorio usa variables de entorno para todos los valores sensibles. No subas archivos `.env`, tokens de Telegram, URLs privadas de calendarios, contraseñas reales ni dumps de base de datos.

Antes de publicar:

- Revisá que `.env` no exista en el commit.
- Usá `.env.example` y `.env.production.example` solo con placeholders.
- Rotá cualquier token que haya estado escrito en archivos locales.
- Cambiá `CLAVE_SECRETA`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD` y `SECRETO_WEBHOOK_TELEGRAM` en producción.
- Si usás webhook de Telegram, mantené activo el header `X-Telegram-Bot-Api-Secret-Token`.

Si se filtra un token, revocalo desde el proveedor correspondiente y generá uno nuevo antes de volver a desplegar.
