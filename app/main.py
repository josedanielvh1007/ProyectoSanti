"""
main.py — Servidor Principal (FastAPI + Socket.IO)
===================================================
Punto de entrada de la aplicación. Combina:

1. FastAPI : Rutas HTTP para servir HTML estático y descargar el CSV.
2. Socket.IO (python-socketio): Comunicación bidireccional en tiempo real.
3. ManejadorTiempo: Tarea asyncio que monitorea la expiración de timers.

Arquitectura de eventos Socket.IO:
────────────────────────────────────
Cliente → Servidor  (escucha el servidor):
  - unirse_sala       : El cliente se une con nombre de delegación.
  - solicitar_turno   : Delegado pide turno Estándar o Respuesta.
  - finalizar_turno   : Delegado da por terminada su intervención.
  - llamar_siguiente  : Moderador avanza manualmente al siguiente turno.
  - insertar_pausa    : Moderador inserta pausa en posición elegida.
  - asignar_turno     : Moderador asigna turno a cualquier delegación.
  - renombrar_deleg   : Moderador cambia el nombre de una delegación.
  - expulsar_deleg    : Moderador desconecta a una delegación.
  - remover_de_cola   : Moderador borra un turno pendiente.
  - pedir_estado      : Cualquier cliente solicita el estado actual.

Servidor → Cliente  (el servidor emite):
  - estado_sala       : Instantánea completa del estado (broadcast).
  - tiempo_agotado    : Notifica que el timer expiró automáticamente.
  - error             : Mensaje de error dirigido solo al emisor.
"""

import asyncio
import logging
import os
from pathlib import Path

import socketio
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from logic.gestor_salas import GestorSalas
from services.exportador_csv import exportar_historial, limpiar_csvs_antiguos
from services.manejador_tiempo import ManejadorTiempo

# ─── Configuración de logging ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Instancias Globales ──────────────────────────────────────────────────────

# GestorSalas es un Singleton: siempre devuelve la misma instancia
gestor = GestorSalas()

# Crear la sala principal al arrancar (código fijo para el prototipo LAN)
SALA_CODIGO = "MAIN"
gestor.crear_sala(SALA_CODIGO)

# Socket.IO en modo ASGI con CORS abierto para la LAN
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",       # En producción limitar a la IP del host
    logger=False,
    engineio_logger=False,
)

# FastAPI como aplicación base
app = FastAPI(title="Debate Manager", version="1.0.0")

# Directorios estáticos (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

# Envolver FastAPI con Socket.IO para obtener la app ASGI final
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Timer monitor asíncrono
timer_manager = ManejadorTiempo()


# ─── Evento: Startup del servidor ────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    """
    Al arrancar el servidor se inicia el monitor de timers.
    Necesitamos hacerlo aquí para tener acceso al event loop de uvicorn.
    """
    timer_manager.iniciar(sio, gestor)
    logger.info("Servidor Debate Manager listo.")


# ─── Rutas HTTP ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """
    Redirige al usuario a la pantalla de entrada (delegate.html).
    El frontend detecta si es el primer usuario y redirige a moderator.html.
    """
    return FileResponse(str(STATIC_DIR / "delegate.html"))


@app.get("/moderador", response_class=HTMLResponse)
async def moderador_view():
    """Panel del moderador (acceso directo para pruebas)."""
    return FileResponse(str(STATIC_DIR / "moderator.html"))


@app.get("/delegado", response_class=HTMLResponse)
async def delegado_view():
    """Vista del delegado."""
    return FileResponse(str(STATIC_DIR / "delegate.html"))


@app.get("/descargar-csv")
async def descargar_csv():
    """
    Genera y descarga el historial CSV de la sesión actual.
    Disponible para cualquier usuario conectado (GET directo desde el navegador).
    """
    sala = gestor.obtener_sala(SALA_CODIGO)
    if not sala:
        return {"error": "Sala no encontrada"}

    historial = sala.historial_a_lista()

    if not historial:
        return HTMLResponse("<h3>No hay historial para exportar aún.</h3>")

    ruta_csv = exportar_historial(historial, SALA_CODIGO)
    limpiar_csvs_antiguos(max_archivos=10)

    nombre_descarga = Path(ruta_csv).name
    return FileResponse(
        path=ruta_csv,
        media_type="text/csv",
        filename=nombre_descarga,
    )


# ─── Eventos Socket.IO ────────────────────────────────────────────────────────

async def _broadcast_estado(sala_codigo: str):
    """
    Helper: emite el estado completo de la sala a todos sus clientes.
    Se llama después de cualquier cambio de estado para mantener sync.
    """
    sala = gestor.obtener_sala(sala_codigo)
    if sala:
        await sio.emit("estado_sala", sala.obtener_estado(), room=sala_codigo)


@sio.event
async def connect(sid: str, environ: dict, auth: dict = None):
    """
    Evento de conexión inicial.
    Solo registra la conexión; el cliente envía 'unirse_sala' con su nombre.
    """
    logger.info(f"[CONNECT] sid={sid}")


@sio.event
async def disconnect(sid: str):
    """
    Evento de desconexión.
    Limpia la delegación de la sala y notifica a todos los demás.
    """
    codigo = gestor.remover_sid(sid)
    if codigo:
        sala = gestor.obtener_sala(codigo)
        if sala:
            sala.desconectar_delegacion(sid)
            logger.info(f"[DISCONNECT] {sid} salió de la sala {codigo}")
            await _broadcast_estado(codigo)


@sio.event
async def unirse_sala(sid: str, data: dict):
    """
    El cliente se une a la sala con su nombre de delegación.

    data = { "pais": "España", "sala": "MAIN" }

    Respuesta:
    - Añade el sid al room de Socket.IO.
    - Registra la delegación en la Sala.
    - Emite el estado completo para que el cliente renderice la vista.
    - Informa si el cliente es el moderador.
    """
    pais = data.get("pais", "Delegación").strip()
    sala_cod = data.get("sala", SALA_CODIGO)

    sala = gestor.obtener_sala(sala_cod)
    if not sala:
        await sio.emit("error", {"msg": "Sala no existe"}, to=sid)
        return

    # Registrar el sid en el room de socket.io (para broadcasts segmentados)
    await sio.enter_room(sid, sala_cod)
    gestor.unir_sid_a_sala(sid, sala_cod)

    # Registrar delegación — retorna True si es el moderador
    es_moderador = sala.registrar_delegacion(sid, pais)

    logger.info(
        f"[JOIN] {pais} (sid={sid}) → sala={sala_cod} "
        f"{'[MODERADOR]' if es_moderador else ''}"
    )

    # Confirmar al cliente su rol y estado
    await sio.emit(
        "bienvenida",
        {
            "es_moderador": es_moderador,
            "sid": sid,
            "pais": pais,
            "sala": sala_cod,
        },
        to=sid,
    )

    # Broadcast del nuevo estado a todos en la sala
    await _broadcast_estado(sala_cod)


@sio.event
async def solicitar_turno(sid: str, data: dict):
    """
    Un delegado solicita un turno Estándar o de Respuesta.

    data = { "tipo": "Estándar" | "Respuesta" }

    Lógica:
    - Crea el turno y lo inserta en la cola según el tipo.
    - Si no hay turno activo, llama al siguiente automáticamente.
    - Broadcast del nuevo estado.
    """
    tipo = data.get("tipo", "Estándar")
    sala = gestor.sala_por_sid(sid)
    if not sala:
        await sio.emit("error", {"msg": "No estás en ninguna sala"}, to=sid)
        return

    # Crear el turno según el tipo solicitado
    turno = sala.nuevo_turno(sid, tipo)
    logger.info(f"[TURNO] {turno.pais} solicita {tipo} → id={turno.turno_id}")

    # Si no hay ningún turno activo, activar el primero de la cola automáticamente
    if sala.turno_actual is None:
        sala.llamar_siguiente()

    await _broadcast_estado(sala.codigo_sala)


@sio.event
async def finalizar_turno(sid: str, data: dict):
    """
    El delegado que tiene el turno activo lo da por concluido manualmente.
    Solo tiene efecto si el sid coincide con el propietario del turno.
    """
    sala = gestor.sala_por_sid(sid)
    if not sala:
        return

    exito = sala.finalizar_turno_activo(sid)
    if exito:
        logger.info(f"[FINALIZAR] {sid} terminó su turno")
        await _broadcast_estado(sala.codigo_sala)
    else:
        await sio.emit(
            "error",
            {"msg": "No puedes finalizar un turno que no es tuyo"},
            to=sid,
        )


@sio.event
async def llamar_siguiente(sid: str, data: dict):
    """
    El MODERADOR avanza manualmente al siguiente turno.
    Puede usarse para saltarse el turno actual o iniciar el debate.
    """
    sala = gestor.sala_por_sid(sid)
    if not sala:
        return

    # Verificar que es el moderador
    if sid != sala.moderator_sid:
        await sio.emit("error", {"msg": "Solo el moderador puede avanzar turnos"}, to=sid)
        return

    sala.llamar_siguiente()
    logger.info(f"[MODERADOR] {sid} llamó al siguiente turno")
    await _broadcast_estado(sala.codigo_sala)


@sio.event
async def insertar_pausa(sid: str, data: dict):
    """
    El MODERADOR inserta un turno de pausa en la cola.

    data = { "posicion": "after_current" | "after_responses" | "end" }
    """
    posicion = data.get("posicion", "end")
    sala = gestor.sala_por_sid(sid)
    if not sala:
        return

    pausa = sala.insertar_pausa(sid, posicion)
    if pausa:
        logger.info(f"[PAUSA] Moderador insertó pausa en posición '{posicion}'")
        await _broadcast_estado(sala.codigo_sala)
    else:
        await sio.emit("error", {"msg": "Solo el moderador puede insertar pausas"}, to=sid)


@sio.event
async def asignar_turno(sid: str, data: dict):
    """
    El MODERADOR asigna un turno directamente a una delegación.

    data = { "target_sid": "...", "tipo": "Estándar" | "Respuesta" }
    """
    target_sid = data.get("target_sid")
    tipo = data.get("tipo", "Estándar")

    sala = gestor.sala_por_sid(sid)
    if not sala:
        return

    if sid != sala.moderator_sid:
        await sio.emit("error", {"msg": "Solo el moderador puede asignar turnos"}, to=sid)
        return

    if target_sid not in sala.delegaciones:
        await sio.emit("error", {"msg": "La delegación objetivo no está conectada"}, to=sid)
        return

    turno = sala.nuevo_turno(target_sid, tipo)
    logger.info(
        f"[ASIGNAR] Moderador asignó turno {tipo} a {turno.pais} (sid={target_sid})"
    )

    if sala.turno_actual is None:
        sala.llamar_siguiente()

    await _broadcast_estado(sala.codigo_sala)


@sio.event
async def renombrar_deleg(sid: str, data: dict):
    """
    El MODERADOR cambia el nombre de una delegación.

    data = { "target_sid": "...", "nuevo_nombre": "..." }
    """
    target_sid = data.get("target_sid")
    nuevo_nombre = data.get("nuevo_nombre", "").strip()

    sala = gestor.sala_por_sid(sid)
    if not sala or sid != sala.moderator_sid:
        await sio.emit("error", {"msg": "Acción no autorizada"}, to=sid)
        return

    if not nuevo_nombre:
        await sio.emit("error", {"msg": "El nombre no puede estar vacío"}, to=sid)
        return

    exito = sala.renombrar_delegacion(target_sid, nuevo_nombre)
    if exito:
        logger.info(f"[RENOMBRAR] sid={target_sid} → '{nuevo_nombre}'")
        await _broadcast_estado(sala.codigo_sala)


@sio.event
async def expulsar_deleg(sid: str, data: dict):
    """
    El MODERADOR expulsa a una delegación de la sala.

    data = { "target_sid": "..." }
    """
    target_sid = data.get("target_sid")

    sala = gestor.sala_por_sid(sid)
    if not sala or sid != sala.moderator_sid:
        await sio.emit("error", {"msg": "Acción no autorizada"}, to=sid)
        return

    if target_sid == sid:
        await sio.emit("error", {"msg": "El moderador no puede expulsarse a sí mismo"}, to=sid)
        return

    # Notificar al expulsado antes de desconectarlo
    await sio.emit(
        "expulsado",
        {"msg": "Has sido expulsado de la sala por el moderador."},
        to=target_sid,
    )

    # Limpiar estado
    gestor.remover_sid(target_sid)
    sala.desconectar_delegacion(target_sid)
    await sio.disconnect(target_sid)

    logger.info(f"[EXPULSAR] Moderador expulsó a sid={target_sid}")
    await _broadcast_estado(sala.codigo_sala)


@sio.event
async def remover_de_cola(sid: str, data: dict):
    """
    El MODERADOR elimina un turno pendiente de la cola.

    data = { "turno_id": "uuid-del-turno" }
    """
    turno_id = data.get("turno_id")
    sala = gestor.sala_por_sid(sid)
    if not sala or sid != sala.moderator_sid:
        await sio.emit("error", {"msg": "Acción no autorizada"}, to=sid)
        return

    exito = sala.remover_turno_cola(turno_id)
    if exito:
        logger.info(f"[REMOVER] Turno {turno_id} eliminado de la cola")
        await _broadcast_estado(sala.codigo_sala)


@sio.event
async def pedir_estado(sid: str, data: dict):
    """
    Cualquier cliente puede solicitar el estado completo de la sala.
    Útil al reconectar o al cargar la página.
    """
    sala = gestor.sala_por_sid(sid)
    if sala:
        await sio.emit("estado_sala", sala.obtener_estado(), to=sid)


# ─── Punto de entrada (desarrollo local sin Docker) ──────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",    # Escucha en todas las interfaces de red (LAN)
        port=8000,
        reload=False,      # Desactivar reload en producción/Docker
        log_level="info",
    )
