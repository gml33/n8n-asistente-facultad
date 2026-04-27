"""Programación de tareas periódicas (sync campus + notificaciones)."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .configuracion_sistema import obtener_ajustes_sistema
from .models import Usuario
from .notificaciones_telegram import enviar_resumen_pendientes_programado
from .sincronizador_campus import sincronizar_campus

logger = logging.getLogger(__name__)
_scheduler = None


def iniciar_programador_si_corresponde(aplicacion):
    """Inicia scheduler singleton con jobs configurables por entorno."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    def _job_campus():
        """Job de sincronización del feed ICS de campus."""
        with aplicacion.app_context():
            try:
                for usuario in Usuario.query.all():
                    ajustes = obtener_ajustes_sistema(usuario.id)
                    if not ajustes.get("sincronizacion_campus_activa", True):
                        continue
                    url = ajustes.get("campus_calendario_url", "")
                    if not url:
                        continue
                    resultado = sincronizar_campus(url, usuario_id=usuario.id)
                    logger.info("Sincronización campus OK usuario=%s: %s", usuario.email, resultado)
            except Exception:
                logger.exception("Error en sincronización programada de campus")

    def _job_notificaciones():
        """Job de revisión/envío de recordatorios Telegram."""
        with aplicacion.app_context():
            try:
                for usuario in Usuario.query.all():
                    resultado = enviar_resumen_pendientes_programado(usuario_id=usuario.id)
                    if resultado.get("enviado"):
                        logger.info("Notificación enviada usuario=%s: %s", usuario.email, resultado)
            except Exception:
                logger.exception("Error en notificaciones programadas")

    minutos_campus = int(aplicacion.config.get("MINUTOS_SINCRONIZACION_CAMPUS", 30))

    with aplicacion.app_context():
        try:
            for usuario in Usuario.query.all():
                ajustes = obtener_ajustes_sistema(usuario.id)
                if not ajustes.get("sincronizacion_campus_activa", True):
                    continue
                url = ajustes.get("campus_calendario_url", "")
                if not url:
                    continue
                # Sincronización inicial para arrancar con datos frescos.
                resultado = sincronizar_campus(url, usuario_id=usuario.id)
                logger.info("Sincronización inicial campus OK usuario=%s: %s", usuario.email, resultado)
        except Exception:
            logger.exception("Error en sincronización inicial de campus")

    _scheduler = BackgroundScheduler(timezone=aplicacion.config.get("TZ", "UTC"))
    _scheduler.add_job(
        _job_campus,
        "interval",
        minutes=minutos_campus,
        id="sincronizacion_campus",
        replace_existing=True,
    )
    logger.info("Programador campus iniciado cada %s minutos", minutos_campus)

    _scheduler.add_job(
        _job_notificaciones,
        "interval",
        minutes=5,
        id="notificaciones_telegram",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Programador de notificaciones iniciado (revisión cada 5 minutos)")
