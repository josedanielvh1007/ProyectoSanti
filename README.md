# 🏛️ Debate Manager — Sistema de Gestión de Sala de Debate

> Prototipo funcional en Python para validar la lógica antes de la migración a C++.  
> Comunicación en tiempo real vía Socket.IO · Dockerizado para despliegue LAN inmediato.

---

## Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Estructura de Carpetas](#estructura-de-carpetas)
4. [Requisitos Previos](#requisitos-previos)
5. [Despliegue con Docker](#despliegue-con-docker)
6. [Ejecución sin Docker (Desarrollo Local)](#ejecución-sin-docker-desarrollo-local)
7. [Guía de Uso](#guía-de-uso)
8. [Exportación CSV](#exportación-csv)
9. [Lógica de Negocio — Reglas de Cola](#lógica-de-negocio--reglas-de-cola)
10. [Referencia de Eventos Socket.IO](#referencia-de-eventos-socketio)
11. [Guía para Encontrar la IP en la LAN](#guía-para-encontrar-la-ip-en-la-lan)
12. [Limitaciones del Prototipo](#limitaciones-del-prototipo)

---

## Descripción General

Debate Manager es una aplicación web LAN que centraliza la gestión de tiempos y turnos en una sala de debate formal. Un **Moderador** (el primer usuario en conectar) controla el flujo, mientras las **Delegaciones** (usuarios subsiguientes) solicitan intervenciones de forma autónoma.

**No es:**
- ❌ Un sistema de videoconferencia
- ❌ Una aplicación de chat
- ❌ Un sistema con base de datos externa (todo en memoria + CSV)

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────┐
│  CLIENTE (Navegador)                                    │
│  ┌─────────────────┐    ┌────────────────────────────┐  │
│  │  moderator.html  │    │      delegate.html          │  │
│  │  (ModeratorView) │    │      (DelegateView)         │  │
│  └────────┬────────┘    └─────────────┬──────────────┘  │
│           └─────────────┬─────────────┘                  │
│                    Socket.IO (WS)                         │
└────────────────────────┼────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  SERVIDOR (Docker / Python 3.11)                        │
│                                                          │
│  FastAPI ── main.py ── SocketController                 │
│                │                                         │
│         ┌──────┼──────────────────┐                     │
│         ▼      ▼                  ▼                     │
│     GestorSalas  ManejadorTiempo  Rutas HTTP            │
│         │                                               │
│         ▼                                               │
│       Sala ──► Cola de Turnos (lista_turnos[])          │
│         │    ──► Turno Activo (turno_actual)            │
│         │    ──► Historial (historial_turnos[])         │
│         ▼                                               │
│   ExportadorCSV ──► /data/historial_MAIN_*.csv          │
└─────────────────────────────────────────────────────────┘
```

---

## Estructura de Carpetas

```
debate-manager/
│
├── app/
│   ├── main.py                # Servidor FastAPI + SocketController (eventos)
│   │
│   ├── logic/
│   │   ├── __init__.py
│   │   ├── turno.py           # Clase Turno: modelo de datos de cada intervención
│   │   ├── sala.py            # Clase Sala: lógica de cola y flujo de turnos
│   │   └── gestor_salas.py    # Singleton GestorSalas: registro de salas activas
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── exportador_csv.py  # Genera y guarda archivos CSV del historial
│   │   └── manejador_tiempo.py# Tarea asyncio: detecta expiración de timers
│   │
│   └── static/
│       ├── assets/
│       │   └── style.css      # Estilos compartidos (tema parlamentario oscuro)
│       ├── moderator.html     # UI del Moderador
│       └── delegate.html      # UI del Delegado
│
├── data/                      # Volumen Docker: CSV de sesión (persistente)
│
├── Dockerfile                 # Imagen python:3.11-slim
├── requirements.txt           # Dependencias Python
└── README.md                  # Esta documentación
```

---

## Requisitos Previos

| Componente | Versión mínima |
|------------|---------------|
| Docker     | 20.10+        |
| Docker Compose | 2.0+ (opcional) |
| Python     | 3.11+ (solo sin Docker) |
| Navegador  | Chrome 90+ / Firefox 88+ / Edge 90+ |

---

## Despliegue con Docker

### 1. Construir la imagen

```bash
# Desde la raíz del proyecto (donde está el Dockerfile)
cd debate-manager
docker build -t debate-manager:latest .
```

### 2. Ejecutar el contenedor

```bash
docker run -d \
  --name debate-manager \
  -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  debate-manager:latest
```

Flags explicados:
- `-d` : Ejecutar en background (detached)
- `-p 8000:8000` : Exponer puerto 8000 del contenedor al host
- `-v $(pwd)/data:/data` : Montar el directorio local `data/` para persistir CSVs
- `--name debate-manager` : Nombre amigable para el contenedor

### 3. Verificar que está corriendo

```bash
docker logs debate-manager -f
# Deberías ver: "Servidor Debate Manager listo."
```

### 4. Parar el contenedor

```bash
docker stop debate-manager
docker rm debate-manager
```

### 5. Reconstruir tras cambios de código

```bash
docker stop debate-manager && docker rm debate-manager
docker build -t debate-manager:latest .
docker run -d --name debate-manager -p 8000:8000 -v "$(pwd)/data:/data" debate-manager:latest
```

---

## Ejecución sin Docker (Desarrollo Local)

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Crear directorio de datos
mkdir -p data

# 4. Ejecutar el servidor
cd app
uvicorn main:socket_app --host 0.0.0.0 --port 8000 --reload
```

---

## Guía de Uso

### Acceso desde la red LAN

Una vez que el servidor está corriendo:

| Usuario | URL de acceso |
|---------|--------------|
| Primer usuario (Moderador) | `http://<IP-SERVIDOR>:8000/` |
| Delegados | `http://<IP-SERVIDOR>:8000/delegado` |
| Panel moderador (directo) | `http://<IP-SERVIDOR>:8000/moderador` |

> ⚠️ El **primer usuario** en conectar con cualquier URL adquiere automáticamente el rol de Moderador y es redirigido al panel de gestión.

### Flujo de sesión

```
1. Moderador abre el navegador → ingresa nombre → accede al panel de control
2. Delegados abren sus navegadores → ingresan nombre de delegación
3. Moderador ve el listado de delegaciones en tiempo real
4. Delegados solicitan "Turno Estándar" o "Turno de Respuesta"
5. El primer turno solicitado se activa automáticamente (si no hay activo)
6. El cronómetro cuenta regresivamente en todos los navegadores sincronizados
7. Solo el poseedor del turno ve el botón "Finalizar mi intervención"
8. Al finalizar (manual o por tiempo), el siguiente turno se activa automáticamente
9. Cualquier usuario puede descargar el CSV en cualquier momento
```

### Panel del Moderador — Controles Exclusivos

| Acción | Descripción |
|--------|-------------|
| ⏭ Siguiente | Corta el turno actual y activa el siguiente en cola |
| ⏸ Pausa — Ahora | Inserta pausa inmediatamente después del turno activo |
| ⏸ Pausa — Tras réplicas | Inserta pausa después del bloque de Respuestas |
| ⏸ Pausa — Al final | Inserta pausa al final de toda la cola |
| 🎯 Asignar turno | Fuerza un turno a cualquier delegación conectada |
| ✏️ Renombrar | Cambia el nombre de una delegación |
| ✕ Expulsar | Desconecta a una delegación y cancela sus turnos |
| ✕ (en cola) | Elimina un turno específico de la cola |
| ⬇ Exportar CSV | Descarga el historial completo al instante |

**Atajo de teclado:** `Ctrl+→` para avanzar al siguiente turno.

---

## Exportación CSV

El CSV se genera dinámicamente en `/data/` y está disponible en cualquier momento:

### URL de descarga

```
GET http://<IP-SERVIDOR>:8000/descargar-csv
```

El botón "⬇ Exportar CSV" / "⬇ CSV" en ambas vistas apunta a esta URL.

### Nomenclatura del archivo

Los archivos se nombran con timestamp para preservar sesiones anteriores:

```
historial_MAIN_20241215_143022.csv
              │    │       │
              │    │       └── HH:MM:SS
              │    └── YYYYMMDD
              └── Código de sala
```

### Formato y columnas

```csv
Orden,Delegación,Tipo de Turno,Duración Real (s),Timestamp Inicio,Timestamp Fin
1,República Argentina,Estándar,87.34,2024-12-15T14:05:12.334,2024-12-15T14:06:39.674
2,Reino de España,Respuesta,41.18,2024-12-15T14:06:41.002,2024-12-15T14:07:22.182
3,Moderador,Pausa,0.0,2024-12-15T14:07:25.000,2024-12-15T14:09:00.123
```

| Columna | Descripción |
|---------|-------------|
| `Orden` | Número secuencial del turno completado en la sesión |
| `Delegación` | Nombre de la delegación que tuvo la palabra |
| `Tipo de Turno` | `Estándar`, `Respuesta` o `Pausa` |
| `Duración Real (s)` | Segundos reales que duró la intervención |
| `Timestamp Inicio` | ISO 8601 — momento en que se activó el turno |
| `Timestamp Fin` | ISO 8601 — momento en que se cerró el turno |

> Los turnos cancelados (delegados expulsados, turnos removidos de cola) **no aparecen** en el CSV ya que nunca llegaron a ejecutarse.

---

## Lógica de Negocio — Reglas de Cola

### Tipos de turno y prioridades

```
COLA VISUAL:
┌─────────────────────────────────────────────────────────────┐
│  [ACTIVO]  España — Estándar — ⏱ 1:23 restantes            │
├─────────────────────────────────────────────────────────────┤
│  [1] Francia — RESPUESTA  ←── bloque prioritario de réplicas│
│  [2] Italia  — RESPUESTA  ←─┘                               │
│  [3] Brasil  — Estándar                                     │
│  [4] Japón   — Estándar                                     │
│  [5] PAUSA   — (Moderador)                                  │
└─────────────────────────────────────────────────────────────┘
```

### Regla de inserción por tipo

| Tipo | Posición de inserción |
|------|-----------------------|
| **Estándar** | Al final de toda la cola |
| **Respuesta** | Inmediatamente después del último `Respuesta` consecutivo al frente |
| **Pausa** | Según elija el moderador (3 posiciones disponibles) |

### Ejemplo de inserción de Respuesta

```
Cola antes: [Respuesta-A, Respuesta-B, Estándar-C, Estándar-D]
Nueva Respuesta-E → se inserta después de Respuesta-B
Cola después: [Respuesta-A, Respuesta-B, Respuesta-E, Estándar-C, Estándar-D]
```

### Finalización de turnos

- **Por tiempo:** El `ManejadorTiempo` detecta la expiración y emite `tiempo_agotado`.
- **Manual (delegado):** Solo el poseedor del turno activo puede pulsar "Finalizar".
- **Manual (moderador):** "⏭ Siguiente" corta el turno activo y avanza.
- **Pausa:** Sin límite de tiempo. Solo el moderador puede avanzar desde una pausa.

---

## Referencia de Eventos Socket.IO

### Cliente → Servidor

| Evento | Payload | Quién puede enviarlo |
|--------|---------|---------------------|
| `unirse_sala` | `{pais, sala}` | Todos |
| `solicitar_turno` | `{tipo}` | Delegados |
| `finalizar_turno` | `{}` | Poseedor del turno activo |
| `llamar_siguiente` | `{}` | Solo Moderador |
| `insertar_pausa` | `{posicion}` | Solo Moderador |
| `asignar_turno` | `{target_sid, tipo}` | Solo Moderador |
| `renombrar_deleg` | `{target_sid, nuevo_nombre}` | Solo Moderador |
| `expulsar_deleg` | `{target_sid}` | Solo Moderador |
| `remover_de_cola` | `{turno_id}` | Solo Moderador |
| `pedir_estado` | `{}` | Todos |

### Servidor → Cliente

| Evento | Payload | Destinatario |
|--------|---------|-------------|
| `bienvenida` | `{es_moderador, sid, pais, sala}` | Solo el emisor |
| `estado_sala` | Estado completo de la sala | Broadcast a la sala |
| `tiempo_agotado` | `{codigo_sala, nuevo_turno}` | Broadcast a la sala |
| `error` | `{msg}` | Solo el emisor |
| `expulsado` | `{msg}` | Solo el expulsado |

---

## Guía para Encontrar la IP en la LAN

### Linux / macOS

```bash
# Opción 1: ip
ip addr show | grep "inet " | grep -v "127.0.0.1"
# Ejemplo de salida: inet 192.168.1.105/24

# Opción 2: ifconfig
ifconfig | grep "inet " | grep -v "127.0.0.1"

# Opción 3: hostname
hostname -I
```

### Windows

```cmd
ipconfig
# Buscar "Dirección IPv4" bajo el adaptador de red activo
# Ejemplo: 192.168.1.105
```

### macOS (alternativa gráfica)

Preferencias del Sistema → Red → Seleccionar conexión activa → Ver IP

### Verificar que el servidor es alcanzable desde otro dispositivo

```bash
# Desde otro dispositivo en la misma red
curl http://192.168.1.105:8000/
# Debe responder con el HTML de la página de ingreso
```

---

## Limitaciones del Prototipo

| Limitación | Impacto | Solución para producción C++ |
|------------|---------|------------------------------|
| Estado en memoria (1 proceso) | Reiniciar el servidor borra todo | Redis / base de datos persistente |
| Sin autenticación real | El "rol" se basa en orden de conexión | Token de moderador o contraseña |
| 1 sala fija ("MAIN") | No se pueden crear múltiples salas | GestorSalas ya soporta N salas |
| 1 worker Uvicorn | No escala más allá de ~100 clientes | Múltiples workers + Redis PubSub |
| Sin HTTPS | Comunicación en texto plano en LAN | Certificado SSL + Nginx reverse proxy |

---

## Licencia

Prototipo educativo/funcional. Adaptar según las necesidades del equipo antes del despliegue en producción.
