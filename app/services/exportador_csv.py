"""
exportador_csv.py — Servicio de Exportación a CSV
==================================================
Escribe el historial de turnos en un archivo CSV temporal en /data/.
El archivo se nombra con un timestamp para que cada descarga sea única
y no sobreescriba sesiones anteriores.

Formato CSV (columnas acordadas en las especificaciones):
─────────────────────────────────────────────────────────
Orden | Delegación | Tipo de Turno | Duración Real (s) | Timestamp Inicio

El archivo se crea/reescribe cada vez que se llama a exportar(),
permitiendo que los usuarios descarguen el historial actualizado
en cualquier momento de la sesión.
"""

import csv
import os
from datetime import datetime
from pathlib import Path

# Directorio donde se guardan los CSV (montado con permisos de escritura en Docker)
DATA_DIR = Path("/data")


def exportar_historial(historial: list[dict], codigo_sala: str = "MAIN") -> str:
    """
    Escribe el historial de turnos en un archivo CSV y devuelve su ruta absoluta.

    Parámetros:
    ───────────
    historial   : Lista de dicts generada por Sala.historial_a_lista().
    codigo_sala : Código de la sala (para nombrar el archivo).

    Retorna:
    ────────
    Ruta absoluta del archivo CSV generado.
    """
    # Asegura que el directorio existe (importante en el contenedor Docker)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Nombre con timestamp para evitar colisiones entre sesiones
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"historial_{codigo_sala}_{ts}.csv"
    ruta = DATA_DIR / nombre_archivo

    # Columnas del CSV según especificaciones del negocio
    campos = [
        "Orden",
        "Delegación",
        "Tipo de Turno",
        "Duración Real (s)",
        "Timestamp Inicio",
        "Timestamp Fin",
    ]

    with open(ruta, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()

        for turno in historial:
            # Solo exportamos turnos que llegaron a ejecutarse
            if turno.get("estado") not in ("completado", "activo"):
                continue

            writer.writerow({
                "Orden":            turno.get("numero", ""),
                "Delegación":       turno.get("pais", ""),
                "Tipo de Turno":    turno.get("tipo", ""),
                "Duración Real (s)": turno.get("duracion_real", 0),
                "Timestamp Inicio": turno.get("timestamp_inicio", ""),
                "Timestamp Fin":    turno.get("timestamp_fin", ""),
            })

    return str(ruta)


def limpiar_csvs_antiguos(max_archivos: int = 10) -> None:
    """
    Borra los CSV más antiguos si hay más de `max_archivos` en /data.
    Útil para no llenar el volumen Docker en sesiones largas.
    """
    if not DATA_DIR.exists():
        return

    archivos = sorted(DATA_DIR.glob("historial_*.csv"), key=os.path.getmtime)

    # Elimina los más viejos si superamos el límite
    while len(archivos) > max_archivos:
        archivos[0].unlink(missing_ok=True)
        archivos.pop(0)
