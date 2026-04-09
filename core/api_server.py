"""
MARK-45 — API Server (FastAPI + WebSocket)
============================================
Daemon headless que expone el Hive Kernel a cualquier frontend.

Endpoints:
  GET  /              → Estado básico (JSON)
  GET  /estado        → Estado completo del kernel (JSON)
  POST /comando       → Enviar comando de texto al Orchestrator
  WS   /ws/eventos    → Stream en tiempo real (stats, chat, estado_ia)

Puerto por defecto: 8765
Todos los campos JSON y logs están en español.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Set, TYPE_CHECKING

logger = logging.getLogger("MARK45.API")

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False
    logger.warning("FastAPI no instalada. Ejecuta: pip install fastapi uvicorn[standard]")

if TYPE_CHECKING:
    from core.orchestrator import Orchestrator


# ── MODELOS ───────────────────────────────────────────────────────────────────

if FASTAPI_OK:
    class ComandoRequest(BaseModel):
        texto: str
        fuente: str = "api"       # "api" | "voz" | "test"


# ── GESTOR DE CONEXIONES WEBSOCKET ────────────────────────────────────────────

class ConexionManager:
    """Gestiona todas las conexiones WebSocket activas."""

    def __init__(self):
        self._clientes: Set[WebSocket] = set()

    async def conectar(self, ws: WebSocket):
        await ws.accept()
        self._clientes.add(ws)
        logger.info(f"WS conectado — clientes activos: {len(self._clientes)}")

    def desconectar(self, ws: WebSocket):
        self._clientes.discard(ws)
        logger.info(f"WS desconectado — clientes activos: {len(self._clientes)}")

    async def broadcast(self, evento: Dict):
        """Enviar evento JSON a todos los clientes conectados."""
        if not self._clientes:
            return
        texto = json.dumps(evento, ensure_ascii=False)
        muertos = set()
        for cliente in self._clientes.copy():
            try:
                await cliente.send_text(texto)
            except Exception:
                muertos.add(cliente)
        for m in muertos:
            self._clientes.discard(m)

    @property
    def num_clientes(self) -> int:
        return len(self._clientes)


# ── CREACIÓN DE LA APP ────────────────────────────────────────────────────────

def create_app(orchestrator: 'Orchestrator') -> Any:
    """
    Crear y configurar la aplicación FastAPI.
    Requiere el Orchestrator ya inicializado.
    """
    if not FASTAPI_OK:
        raise ImportError("FastAPI no instalada. Ejecuta: pip install fastapi uvicorn[standard]")

    app   = FastAPI(
        title="MARK 45 — Hive Kernel API",
        description="API del sistema de IA personal de Ali (Sidi3Ali)",
        version="45.0",
    )
    manager = ConexionManager()

    # ── CORS (permite cualquier origen local) ─────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # Restringir en producción
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Tarea de fondo: drenar el event_bus → broadcast WS ───────────────────
    async def _event_bus_drain():
        """Drena el EventBus del Orchestrator y hace broadcast a los clientes WS."""
        logger.info("Event bus drain activo")
        while True:
            try:
                if orchestrator.event_bus is None:
                    await asyncio.sleep(0.2)
                    continue
                try:
                    evento = await asyncio.wait_for(
                        orchestrator.event_bus.get(), timeout=0.5
                    )
                    orchestrator.event_bus.task_done()
                    if manager.num_clientes > 0:
                        await manager.broadcast(evento)
                except asyncio.TimeoutError:
                    pass
            except Exception as e:
                logger.debug(f"event_bus_drain: {e}")
                await asyncio.sleep(0.1)

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(_event_bus_drain())
        logger.info("MARK 45 API arrancada — event bus drain activo")

    # ── ENDPOINTS HTTP ────────────────────────────────────────────────────────

    @app.get("/", summary="Estado del servidor")
    async def raiz():
        return {
            "sistema": "MARK 45 — Hive Kernel",
            "creador": "Ali (Sidi3Ali)",
            "estado": "en_linea",
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "clientes_ws": manager.num_clientes,
        }

    @app.get("/estado", summary="Estado completo del kernel")
    async def estado():
        llm_info  = orchestrator.llm.get_status() if orchestrator.llm else {}
        mem_info  = orchestrator.memory.get_stats() if orchestrator.memory else {}
        stats = {}
        if orchestrator.monitor:
            try:
                stats = await asyncio.to_thread(orchestrator.monitor.get_stats)
            except Exception:
                pass
        return JSONResponse({
            "mark": {
                "version":      "45.0",
                "usuario":      orchestrator._user_name,
                "gaming_mode":  orchestrator.gaming_mode,
                "running":      orchestrator.running,
            },
            "llm":     llm_info,
            "memoria": mem_info,
            "sistema": {
                "cpu":         stats.get("cpu", 0),
                "ram":         stats.get("ram", 0),
                "ram_gb":      f"{stats.get('ram_used_gb', 0):.1f}/{stats.get('ram_total_gb', 0):.0f}",
                "disco":       stats.get("disk", 0),
                "vram_mb":     f"{stats.get('vram_used_mb', 0)}/{stats.get('vram_total_mb', 0)}",
                "gaming":      stats.get("gaming_mode", False),
                "juego":       stats.get("game_name", ""),
            },
            "clientes_ws": manager.num_clientes,
        })

    @app.post("/comando", summary="Enviar comando al Orchestrator")
    async def comando(req: ComandoRequest):
        if not req.texto or not req.texto.strip():
            return JSONResponse({"error": "Texto vacío"}, status_code=400)

        texto = req.texto.strip()
        logger.info(f"API CMD [{req.fuente}]: '{texto}'")

        # Publicar evento chat (usuario) antes de procesar
        await orchestrator.publish("chat", {
            "rol": "usuario",
            "texto": texto,
            "fuente": req.fuente,
        })
        await orchestrator.publish("estado_ia", {"estado": "PROCESANDO"})

        try:
            respuesta = await orchestrator.handle_command(texto)
            # handle_command ya publica el chat de MARK internamente
            await orchestrator.publish("estado_ia", {"estado": "NOMINAL"})
            # También hablar en voz alta si hay voice system
            asyncio.create_task(
                asyncio.to_thread(orchestrator.speak_sync, respuesta)
            )
            return {"respuesta": respuesta, "accion": "ok"}
        except Exception as e:
            logger.error(f"Error comando API: {e}")
            await orchestrator.publish("estado_ia", {"estado": "ERROR"})
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/historial", summary="Historial reciente de conversación")
    async def historial(n: int = 20):
        if not orchestrator.memory:
            return {"turnos": []}
        return {"turnos": orchestrator.memory.get_recent(n)}

    @app.post("/voz/toggle", summary="Activar/desactivar wake word daemon")
    async def voz_toggle():
        wd = orchestrator._wake_daemon
        if not wd:
            return {"error": "Wake word daemon no disponible"}
        wd.set_enabled(not wd.enabled)
        return {"wake_word_activo": wd.enabled}

    @app.post("/gaming/toggle", summary="Activar/desactivar modo gaming")
    async def gaming_toggle():
        orchestrator.gaming_mode = not orchestrator.gaming_mode
        estado = "activado" if orchestrator.gaming_mode else "desactivado"
        await orchestrator.publish("chat", {
            "rol": "mark",
            "texto": f"Modo Gaming {estado}.",
        })
        return {"gaming_mode": orchestrator.gaming_mode}

    # ── WEBSOCKET ─────────────────────────────────────────────────────────────

    @app.websocket("/ws/eventos")
    async def ws_eventos(websocket: WebSocket):
        await manager.conectar(websocket)
        # Enviar estado inicial al conectarse
        try:
            stats = await asyncio.to_thread(orchestrator.monitor.get_stats) if orchestrator.monitor else {}
        except Exception:
            stats = {}
        await websocket.send_text(json.dumps({
            "tipo": "bienvenida",
            "datos": {
                "mensaje": f"Conectado a MARK 45. Usuario: {orchestrator._user_name}",
                "llm": getattr(orchestrator.llm, 'active_provider', 'N/A'),
                "gaming": orchestrator.gaming_mode,
            },
            "hora": datetime.now().strftime("%H:%M:%S"),
        }, ensure_ascii=False))

        try:
            while True:
                # Escuchar mensajes del cliente (comandos via WS)
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        msg = {"tipo": "comando", "texto": raw}

                    if msg.get("tipo") == "comando":
                        texto = msg.get("texto", "").strip()
                        if texto:
                            logger.info(f"WS CMD: '{texto}'")
                            await orchestrator.publish("chat", {"rol": "usuario", "texto": texto})
                            await orchestrator.publish("estado_ia", {"estado": "PROCESANDO"})
                            respuesta = await orchestrator.handle_command(texto)
                            await orchestrator.publish("estado_ia", {"estado": "NOMINAL"})
                            asyncio.create_task(
                                asyncio.to_thread(orchestrator.speak_sync, respuesta)
                            )
                    elif msg.get("tipo") == "ping":
                        await websocket.send_text(json.dumps({"tipo": "pong"}))

                except asyncio.TimeoutError:
                    # Keepalive ping cada 30s
                    await websocket.send_text(json.dumps({"tipo": "ping"}))
        except WebSocketDisconnect:
            manager.desconectar(websocket)
        except Exception as e:
            logger.debug(f"WS error: {e}")
            manager.desconectar(websocket)

    return app


# ── RUNNER ────────────────────────────────────────────────────────────────────

async def run_api_server(orchestrator: 'Orchestrator', host: str = "127.0.0.1", port: int = 8765):
    """Arrancar el servidor API en el mismo event loop que el Orchestrator."""
    try:
        import uvicorn
        app = create_app(orchestrator)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",       # Silenciar uvicorn, dejar hablar MARK
            access_log=False,
        )
        server = uvicorn.Server(config)
        logger.info(f"MARK 45 API activa en http://{host}:{port}")
        logger.info(f"  WebSocket: ws://{host}:{port}/ws/eventos")
        logger.info(f"  Estado:    http://{host}:{port}/estado")
        # Imprimir en consola directamente (visible siempre)
        print(f"\n{'='*55}")
        print(f"  MARK 45 API activa en http://{host}:{port}")
        print(f"  WebSocket:  ws://{host}:{port}/ws/eventos")
        print(f"  Comandos:   POST http://{host}:{port}/comando")
        print(f"  Estado:     GET  http://{host}:{port}/estado")
        print(f"  Cliente:    Abre ui/test_client.html en el navegador")
        print(f"{'='*55}\n")
        await server.serve()
    except ImportError:
        logger.error("uvicorn no instalado. Ejecuta: pip install uvicorn[standard]")
        raise
