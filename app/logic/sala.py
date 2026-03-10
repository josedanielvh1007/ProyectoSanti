"""
sala.py — Clase Sala
====================
Núcleo lógico del sistema de debate.
Gestiona la lista de turnos pendientes, el turno activo y el historial,
implementando las reglas de inserción prioritaria según el tipo de turno.

Reglas de cola (según las especificaciones del negocio):
────────────────────────────────────────────────────────
1. ESTÁNDAR   → Se añade al final de la cola.
2. RESPUESTA  → Se inserta inmediatamente DESPUÉS del bloque de respuestas
                consecutivas que ya existen al frente de la cola.
                (Agrupa todas las réplicas juntas antes de los estándares.)
3. PAUSA (Mod)→ El moderador elige dónde insertarla:
   - "after_current"   : Justo después del turno activo (primera posición cola).
   - "after_responses" : Después del bloque de respuestas al frente.
   - "end"             : Al final de toda la cola.
"""

from datetime import datetime
from .turno import Turno, TipoTurno, EstadoTurno


class Sala:
    """
    Gestiona el estado completo de una sesión de debate.

    Atributos:
    ──────────
    codigo_sala     : Identificador único de la sala (por ahora siempre "MAIN").
    lista_turnos    : Cola de turnos PENDIENTES ordenada por prioridad.
    historial_turnos: Turnos ya COMPLETADOS o CANCELADOS (para CSV y consulta).
    turno_actual    : El turno que está ejecutándose en este momento (o None).
    contador_turno  : Contador global para numerar turnos completados en orden.
    timer_running   : True si el cronómetro está activo.
    timer_end_ts    : Timestamp Unix (float) en que expira el temporizador actual.
    moderator_sid   : Socket ID del moderador de la sala.
    """

    def __init__(self, codigo_sala: str):
        self.codigo_sala: str = codigo_sala
        self.lista_turnos: list[Turno] = []      # Cola de pendientes
        self.historial_turnos: list[Turno] = []  # Turnos finalizados
        self.turno_actual: Turno | None = None
        self.contador_turno: int = 0             # Incrementa al completar turnos
        self.timer_running: bool = False
        self.timer_end_ts: float | None = None   # Timestamp Unix de fin
        self.moderator_sid: str | None = None    # SID del primer conectado
        self.delegaciones: dict[str, str] = {}   # sid → nombre delegación

    # ─── Gestión de Delegaciones ──────────────────────────────────────────────

    def registrar_delegacion(self, sid: str, pais: str) -> bool:
        """
        Registra una nueva delegación.
        Retorna True si es el primer usuario (se convierte en moderador).
        """
        self.delegaciones[sid] = pais
        if self.moderator_sid is None:
            self.moderator_sid = sid  # El primero en conectar es el moderador
            return True
        return False

    def desconectar_delegacion(self, sid: str) -> None:
        """
        Elimina la delegación y cancela sus turnos pendientes.
        Si era el moderador, el siguiente conectado hereda el rol.
        """
        if sid in self.delegaciones:
            del self.delegaciones[sid]

        # Cancela todos los turnos pendientes de este socket
        for turno in list(self.lista_turnos):
            if turno.socket_id == sid:
                turno.cancelar()
                self.lista_turnos.remove(turno)
                self.historial_turnos.append(turno)

        # Reasigna moderador al siguiente en la lista si era el moderador
        if sid == self.moderator_sid:
            if self.delegaciones:
                self.moderator_sid = next(iter(self.delegaciones))
            else:
                self.moderator_sid = None

    def renombrar_delegacion(self, sid: str, nuevo_nombre: str) -> bool:
        """El moderador puede cambiar el nombre de cualquier delegación."""
        if sid in self.delegaciones:
            viejo_nombre = self.delegaciones[sid]
            self.delegaciones[sid] = nuevo_nombre
            # Actualiza también los turnos pendientes de ese sid
            for turno in self.lista_turnos:
                if turno.socket_id == sid and turno.pais == viejo_nombre:
                    turno.pais = nuevo_nombre
            return True
        return False

    # ─── Lógica de Inserción en Cola ─────────────────────────────────────────

    def _encontrar_fin_bloque_respuestas(self) -> int:
        """
        Recorre la cola desde el frente y devuelve el índice del primer
        turno que NO es de tipo RESPUESTA.
        Sirve para saber dónde termina el bloque prioritario de réplicas.
        
        Ejemplo:
          cola = [Respuesta, Respuesta, Estándar, Estándar]
                  ↑ idx=0     ↑ idx=1   ↑ idx=2   ↑ idx=3
          retorna 2  → se inserta en posición 2
        """
        for idx, turno in enumerate(self.lista_turnos):
            if turno.tipo != TipoTurno.RESPUESTA:
                return idx
        # Si toda la cola son respuestas, se inserta al final del bloque
        return len(self.lista_turnos)

    def nuevo_turno(self, sid: str, tipo: str, duracion_max: int | None = None) -> Turno:
        """
        Crea un nuevo turno y lo inserta en la posición correcta de la cola.

        Reglas de inserción:
        ────────────────────
        ESTÁNDAR  → append al final
        RESPUESTA → antes del primer turno NO-RESPUESTA (agrupa réplicas)
        PAUSA     → no se crea aquí; usa insertar_pausa() del moderador
        """
        pais = self.delegaciones.get(sid, "Desconocido")
        turno = Turno(sid, pais, tipo, duracion_max)

        if turno.tipo == TipoTurno.ESTANDAR:
            # Turno normal: al final de la cola
            self.lista_turnos.append(turno)

        elif turno.tipo == TipoTurno.RESPUESTA:
            # Turno prioritario: agrupa réplicas al frente de la cola
            idx = self._encontrar_fin_bloque_respuestas()
            self.lista_turnos.insert(idx, turno)

        elif turno.tipo == TipoTurno.PAUSA:
            # Las pausas se gestionan con insertar_pausa(); si llegan aquí, al final
            self.lista_turnos.append(turno)

        return turno

    def insertar_pausa(self, sid: str, posicion: str) -> Turno | None:
        """
        El moderador inserta un turno de pausa en la posición indicada.

        posicion:
          "after_current"   → primera posición de la cola (inmediato)
          "after_responses" → después del bloque de respuestas
          "end"             → al final de toda la cola
        
        Retorna None si solo el moderador puede llamar este método y no lo es.
        """
        if sid != self.moderator_sid:
            return None  # Seguridad: solo el moderador puede pausar

        pais = self.delegaciones.get(sid, "Moderador")
        pausa = Turno(sid, pais, TipoTurno.PAUSA, duracion_max=0)

        if posicion == "after_current":
            # Posición 0 de la cola = próximo turno
            self.lista_turnos.insert(0, pausa)

        elif posicion == "after_responses":
            idx = self._encontrar_fin_bloque_respuestas()
            self.lista_turnos.insert(idx, pausa)

        else:  # "end" o cualquier otro valor
            self.lista_turnos.append(pausa)

        return pausa

    # ─── Control de Flujo de Turnos ───────────────────────────────────────────

    def llamar_siguiente(self) -> Turno | None:
        """
        Finaliza el turno actual (si existe) y activa el siguiente en la cola.
        
        Flujo:
        1. Si hay turno_actual activo → lo completa y lo mueve al historial.
        2. Si hay pendientes en cola  → activa el primero.
        3. Configura el timer_end_ts para sincronización de clientes.
        
        Retorna el nuevo turno_actual o None si la cola está vacía.
        """
        import time

        # Completar el turno en curso (si existe)
        if self.turno_actual and self.turno_actual.estado == EstadoTurno.ACTIVO:
            self._cerrar_turno_actual()

        # Si no hay pendientes, sala queda en reposo
        if not self.lista_turnos:
            self.turno_actual = None
            self.timer_running = False
            self.timer_end_ts = None
            return None

        # Sacar el primer turno de la cola y activarlo
        self.turno_actual = self.lista_turnos.pop(0)
        self.turno_actual.iniciar()

        # Configurar el cronómetro
        if self.turno_actual.duracion_max > 0:
            # Timer con límite: timestamp de expiración
            self.timer_end_ts = time.time() + self.turno_actual.duracion_max
            self.timer_running = True
        else:
            # Pausa: sin límite de tiempo
            self.timer_end_ts = None
            self.timer_running = False

        return self.turno_actual

    def _cerrar_turno_actual(self) -> None:
        """
        Finaliza el turno_actual, asigna su número de orden
        y lo mueve al historial.
        """
        if not self.turno_actual:
            return
        self.contador_turno += 1
        self.turno_actual.numero = self.contador_turno
        self.turno_actual.completar()
        self.historial_turnos.append(self.turno_actual)

    def finalizar_turno_activo(self, sid: str) -> bool:
        """
        Llamado cuando el DELEGADO pulsa "Finalizar mi turno".
        Solo puede actuar el socket_id que posee el turno activo.
        
        Retorna True si el cierre fue exitoso.
        """
        if (
            self.turno_actual
            and self.turno_actual.estado == EstadoTurno.ACTIVO
            and self.turno_actual.socket_id == sid
        ):
            self.llamar_siguiente()  # Cierra actual y activa el siguiente
            return True
        return False

    def remover_turno_cola(self, turno_id: str) -> bool:
        """
        El moderador elimina un turno PENDIENTE de la cola por su ID.
        Retorna True si se encontró y removió.
        """
        for turno in self.lista_turnos:
            if turno.turno_id == turno_id:
                turno.cancelar()
                self.lista_turnos.remove(turno)
                self.historial_turnos.append(turno)
                return True
        return False

    # ─── Serialización del Estado ─────────────────────────────────────────────

    def obtener_estado(self) -> dict:
        """
        Devuelve una instantánea completa del estado de la sala.
        Este dict es el payload principal que se emite a todos los clientes.
        """
        return {
            "codigo_sala":    self.codigo_sala,
            "moderator_sid":  self.moderator_sid,
            "timer_running":  self.timer_running,
            "timer_end_ts":   self.timer_end_ts,
            "turno_actual":   self.turno_actual.to_dict() if self.turno_actual else None,
            "lista_turnos":   [t.to_dict() for t in self.lista_turnos],
            "delegaciones":   self.delegaciones,   # {sid: pais}
            "total_historial": len(self.historial_turnos),
        }

    def historial_a_lista(self) -> list[dict]:
        """Retorna el historial como lista de dicts para el CSV."""
        return [t.to_dict() for t in self.historial_turnos]
