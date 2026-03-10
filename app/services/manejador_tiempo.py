"""
manejador_tiempo.py — Servicio de Gestión de Tiempos
=====================================================
Ejecuta un bucle asíncrono que monitorea el timer del turno activo.
Cuando el tiempo expira, emite el evento 'tiempo_agotado' vía Socket.IO,
lo que desencadena la transición automática al siguiente turno.

Diseño:
───────
- Se usa asyncio para no bloquear el event loop de uvicorn/FastAPI.
- Una sola tarea (Task) corre en background desde que arranca el servidor.
- La tarea duerme en intervalos cortos (0.5 s) y comprueba el estado.
- Solo actúa cuando timer_running=True y el timestamp de fin ha pasado.
"""

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class ManejadorTiempo:
    """
    Monitor asíncrono del temporizador de la sala.

    Se instancia una vez en main.py y recibe referencias al GestorSalas
    y al objeto sio (SocketIO server) para poder emitir eventos.
    """

    def __init__(self):
        self._tarea: asyncio.Task | None = None
        self._sio = None          # Se inyecta desde main.py
        self._gestor = None       # Referencia al GestorSalas singleton

    def iniciar(self, sio, gestor) -> None:
        """
        Inicia la tarea de monitoreo en el event loop de asyncio.
        Debe llamarse una vez, después de que el servidor arranca.
        """
        self._sio = sio
        self._gestor = gestor
        self._tarea = asyncio.create_task(self._bucle_monitor())
        logger.info("ManejadorTiempo iniciado.")

    async def _bucle_monitor(self) -> None:
        """
        Bucle principal: revisa cada 500 ms si algún timer ha expirado.
        Si expira, llama a sala.llamar_siguiente() y emite el nuevo estado.
        """
        while True:
            await asyncio.sleep(0.5)  # Resolución de medio segundo
            try:
                await self._verificar_timers()
            except Exception as e:
                # No dejar caer el bucle por errores puntuales
                logger.error(f"Error en bucle de timers: {e}")

    async def _verificar_timers(self) -> None:
        """
        Itera sobre todas las salas y comprueba si el timer activo expiró.
        """
        if not self._gestor:
            return

        for codigo, sala in self._gestor.listado_salas.items():
            # Solo procesar salas con timer activo y timestamp definido
            if not sala.timer_running or sala.timer_end_ts is None:
                continue

            # ¿El tiempo de fin ya pasó?
            if time.time() >= sala.timer_end_ts:
                logger.info(
                    f"[{codigo}] Timer expirado para turno: "
                    f"{sala.turno_actual}"
                )

                # Avanza al siguiente turno
                sala.timer_running = False
                nuevo_turno = sala.llamar_siguiente()

                # Emite el nuevo estado a todos los clientes de la sala
                await self._sio.emit(
                    "estado_sala",
                    sala.obtener_estado(),
                    room=codigo,      # Grupo/room del socket.io = código de sala
                )

                # Evento adicional para que los clientes sepan que fue por timeout
                await self._sio.emit(
                    "tiempo_agotado",
                    {
                        "codigo_sala": codigo,
                        "nuevo_turno": nuevo_turno.to_dict() if nuevo_turno else None,
                    },
                    room=codigo,
                )
