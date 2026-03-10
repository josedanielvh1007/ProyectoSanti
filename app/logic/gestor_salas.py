"""
gestor_salas.py — Clase GestorSalas
=====================================
Singleton que administra el conjunto de salas activas.
En el prototipo LAN se usa una única sala ("MAIN"), pero la arquitectura
permite escalar a múltiples salas sin modificar el SocketController.

Responsabilidades:
──────────────────
- Crear y eliminar salas por código.
- Proveer acceso centralizado a la sala activa.
- Mantener un índice sid→sala_codigo para despacho rápido de eventos.
"""

from .sala import Sala


class GestorSalas:
    """
    Registro central de todas las salas activas en el servidor.

    Atributos:
    ──────────
    listado_salas : dict[str, Sala] — código_sala → objeto Sala.
    _sid_a_sala   : dict[str, str]  — socket_id   → código_sala (índice auxiliar).
    """

    # ─── Patrón Singleton ─────────────────────────────────────────────────────
    # (En FastAPI/uvicorn en modo single-worker es suficiente con una instancia
    # global; para multi-worker se necesitaría Redis, fuera del alcance.)

    _instance: "GestorSalas | None" = None

    def __new__(cls) -> "GestorSalas":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.listado_salas = {}
            cls._instance._sid_a_sala = {}
        return cls._instance

    # ─── CRUD de Salas ────────────────────────────────────────────────────────

    def crear_sala(self, codigo: str) -> Sala:
        """
        Crea una nueva sala con el código dado.
        Si ya existe, devuelve la sala existente (idempotente).
        """
        if codigo not in self.listado_salas:
            self.listado_salas[codigo] = Sala(codigo)
        return self.listado_salas[codigo]

    def eliminar_sala(self, codigo: str) -> None:
        """
        Elimina una sala del registro.
        Los sids asociados se limpian del índice auxiliar.
        """
        if codigo not in self.listado_salas:
            return
        # Limpiar índice auxiliar
        sids_a_borrar = [
            sid for sid, cod in self._sid_a_sala.items() if cod == codigo
        ]
        for sid in sids_a_borrar:
            del self._sid_a_sala[sid]
        del self.listado_salas[codigo]

    def listar_salas(self) -> list[str]:
        """Retorna la lista de códigos de salas activas."""
        return list(self.listado_salas.keys())

    # ─── Acceso a Sala ────────────────────────────────────────────────────────

    def obtener_sala(self, codigo: str) -> Sala | None:
        """Retorna la sala por código, o None si no existe."""
        return self.listado_salas.get(codigo)

    def sala_por_sid(self, sid: str) -> Sala | None:
        """Retorna la sala en la que está conectado un socket_id."""
        codigo = self._sid_a_sala.get(sid)
        if codigo:
            return self.listado_salas.get(codigo)
        return None

    # ─── Gestión de Membresía ────────────────────────────────────────────────

    def unir_sid_a_sala(self, sid: str, codigo: str) -> None:
        """Registra que un socket_id pertenece a una sala."""
        self._sid_a_sala[sid] = codigo

    def remover_sid(self, sid: str) -> str | None:
        """
        Elimina el sid del índice y retorna el código de sala del que salió.
        Útil en el evento 'disconnect' para saber a qué sala notificar.
        """
        return self._sid_a_sala.pop(sid, None)

    # ─── Getters / Setters (compatibilidad con UML) ───────────────────────────

    def get_listado_salas(self) -> dict:
        return self.listado_salas

    def set_listado_salas(self, salas: dict) -> None:
        self.listado_salas = salas
