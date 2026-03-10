"""
turno.py — Clase Turno
======================
Representa una única intervención dentro de la sala de debate.
Cada instancia contiene toda la información necesaria para gestionar,
cronometrar y registrar un turno de palabra.
"""

import uuid
from datetime import datetime
from enum import Enum


# ─── Tipos de turno posibles en el sistema ───────────────────────────────────

class TipoTurno(str, Enum):
    ESTANDAR = "Estándar"    # Turno normal, se añade al final de la cola
    RESPUESTA = "Respuesta"  # Turno prioritario, se inserta tras el bloque actual
    PAUSA    = "Pausa"       # Turno del moderador, sin límite de tiempo


# ─── Estados por los que puede pasar un turno ────────────────────────────────

class EstadoTurno(str, Enum):
    PENDIENTE  = "pendiente"   # En cola, aún no ha comenzado
    ACTIVO     = "activo"      # Actualmente en curso
    COMPLETADO = "completado"  # Finalizado normalmente (por el delegado o tiempo)
    CANCELADO  = "cancelado"   # Eliminado de la cola por el moderador


# ─── Duración por defecto en segundos según tipo de turno ────────────────────

DURACION_POR_TIPO: dict[str, int] = {
    TipoTurno.ESTANDAR:  90,   # 1 minuto 30 segundos
    TipoTurno.RESPUESTA: 45,   # 45 segundos
    TipoTurno.PAUSA:      0,   # Sin límite
}


class Turno:
    """
    Modela una intervención en la sala de debate.

    Atributos principales:
    ─────────────────────
    turno_id     : Identificador único generado automáticamente (UUID4).
    socket_id    : ID del socket del cliente que solicitó este turno.
    pais         : Nombre de la delegación que tiene la palabra.
    tipo         : TipoTurno — Estándar, Respuesta o Pausa.
    estado       : EstadoTurno — ciclo de vida del turno.
    numero       : Posición ordinal en el historial de la sesión (se asigna al completarse).
    duracion_max : Segundos máximos permitidos (0 = sin límite, solo en Pausa).
    duracion_real: Segundos reales que duró la intervención (calculado al finalizar).
    timestamp_inicio : Momento en que el turno se marcó como ACTIVO.
    timestamp_fin    : Momento en que el turno se marcó como COMPLETADO/CANCELADO.
    """

    def __init__(
        self,
        socket_id: str,
        pais: str,
        tipo: TipoTurno = TipoTurno.ESTANDAR,
        duracion_max: int | None = None,
    ):
        # Identificación
        self.turno_id: str = str(uuid.uuid4())
        self.socket_id: str = socket_id        # Vincula el turno al cliente conectado
        self.pais: str = pais
        self.numero: int = 0                   # Se asigna al completarse el turno

        # Clasificación
        self.tipo: TipoTurno = TipoTurno(tipo)
        self.estado: EstadoTurno = EstadoTurno.PENDIENTE

        # Tiempos — si no se especifica, usa el default según el tipo
        self.duracion_max: int = (
            duracion_max if duracion_max is not None
            else DURACION_POR_TIPO.get(self.tipo, 90)
        )
        self.duracion_real: float = 0.0        # Segundos reales (se calcula al cerrar)

        # Marcas de tiempo
        self.timestamp_inicio: datetime | None = None
        self.timestamp_fin: datetime | None = None
        self.timestamp_creacion: datetime = datetime.now()

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    def iniciar(self) -> None:
        """Marca el turno como activo y registra el timestamp de inicio."""
        self.estado = EstadoTurno.ACTIVO
        self.timestamp_inicio = datetime.now()

    def completar(self) -> None:
        """
        Cierra el turno normalmente y calcula la duración real.
        Llamado cuando el delegado pulsa 'Finalizar' o expira el tiempo.
        """
        self.estado = EstadoTurno.COMPLETADO
        self.timestamp_fin = datetime.now()
        if self.timestamp_inicio:
            delta = self.timestamp_fin - self.timestamp_inicio
            self.duracion_real = round(delta.total_seconds(), 2)

    def cancelar(self) -> None:
        """
        Cancela un turno que estaba en cola (PENDIENTE).
        No registra duración real porque nunca llegó a ejecutarse.
        """
        self.estado = EstadoTurno.CANCELADO
        self.timestamp_fin = datetime.now()

    # ─── Serialización ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Convierte el turno a un diccionario JSON-serializable.
        Utilizado por el SocketController para emitir eventos al frontend.
        """
        return {
            "turno_id":        self.turno_id,
            "socket_id":       self.socket_id,
            "pais":            self.pais,
            "numero":          self.numero,
            "tipo":            self.tipo.value,
            "estado":          self.estado.value,
            "duracion_max":    self.duracion_max,
            "duracion_real":   self.duracion_real,
            "timestamp_inicio": (
                self.timestamp_inicio.isoformat() if self.timestamp_inicio else None
            ),
            "timestamp_fin": (
                self.timestamp_fin.isoformat() if self.timestamp_fin else None
            ),
            "timestamp_creacion": self.timestamp_creacion.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<Turno #{self.numero} | {self.pais} | "
            f"{self.tipo.value} | {self.estado.value}>"
        )
