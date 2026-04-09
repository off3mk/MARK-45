#!/usr/bin/env python3
"""
MARK-45 — Launcher
====================
Hive Kernel — El sistema de IA más avanzado de Ali (Sidi3Ali)

Hardware: Ryzen 7 5800X | 32GB RAM | RTX 4060 Ti 8GB | Windows 11
Modelo:   Qwen3-8B Q5_K_M en LM Studio (CUDA)

Uso:
  python main.py          → GUI (ventana gráfica Tkinter Iron Man)
  python main.py --web    → Daemon headless + API FastAPI (localhost:8765)
  python main.py --cli    → Consola interactiva
  python main.py --debug  → Logs detallados
  python main.py --web --puerto 9000  → Puerto personalizado

Creado por Ali (Sidi3Ali) — MARK 45
"""

import argparse
import asyncio
import logging
import os
import sys
import threading
from datetime import datetime

# Asegurar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Crear directorios necesarios
for d in ["workspace", "memory", "logs", "assets"]:
    os.makedirs(d, exist_ok=True)


def setup_logging(debug: bool = False):
    level  = logging.DEBUG if debug else logging.INFO
    fmt    = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    log_file = os.path.join("logs", f"mark45_{datetime.now().strftime('%Y%m%d')}.log")
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # Silenciar librerías ruidosas
    for quiet in ["urllib3", "httpx", "PIL", "asyncio", "comtypes", "spotipy"]:
        logging.getLogger(quiet).setLevel(logging.WARNING)


# ── MODO CLI ──────────────────────────────────────────────────────────────────

async def run_cli(debug: bool = False):
    from core.orchestrator import Orchestrator
    orch = Orchestrator()

    print("\n" + "╔" + "═" * 58 + "╗")
    print("║  M A R K  4 5  — Hive Kernel  (Ali / Sidi3Ali)        ║")
    print("║  Ryzen 7 5800X | 32GB | RTX 4060 Ti 8GB | Win11        ║")
    print("╚" + "═" * 58 + "╝")
    print(f"  LLM: {getattr(orch.llm, 'active_provider', 'N/A')}")
    print(f"  Usuario: {orch._user_name}")
    print(f"  Escribe 'salir' para terminar\n")

    bg = asyncio.create_task(asyncio.gather(
        orch._loop_perception(),
        orch._loop_gaming(),
        orch._loop_cognitive(),
        orch._loop_execution(),
    ))

    try:
        while orch.running:
            try:
                user_input = await asyncio.to_thread(
                    input, f"\n{orch._user_name} › "
                )
                user_input = user_input.strip()
                if not user_input:
                    continue
                if user_input.lower() in ["salir", "exit", "quit", "bye"]:
                    await orch.shutdown()
                    break
                print(f"\nMARK 45 › ", end="", flush=True)
                response = await orch.handle_command(user_input)
                print(response)
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        bg.cancel()
        try:
            await bg
        except asyncio.CancelledError:
            pass

    print("\n🛑 MARK 45 apagado.")


# ── MODO WEB (DAEMON HEADLESS + API) ────────────────────────────────────────

async def run_web(host: str = "127.0.0.1", port: int = 8765):
    """
    Modo daemon headless: Hive Kernel + FastAPI + uvicorn en el mismo event loop.
    El Orchestrator publica eventos en el EventBus; la API los transmite
    por WebSocket a Pencil.dev o cualquier frontend externo.
    """
    logger = logging.getLogger("MARK45.Web")
    from core.orchestrator import Orchestrator
    from core.api_server import run_api_server

    logger.info("Iniciando Orchestrator (modo headless)...")
    orch = Orchestrator()

    # Iniciar el EventBus y las colas internas
    orch.running     = True
    orch.event_queue = asyncio.Queue()

    # Saludo de inicio
    await orch._speak(orch._greeting(), "greeting")

    logger.info("🚀 Hive Kernel + API arrancando...")

    # Correr todos los loops del kernel + el servidor API en paralelo
    await asyncio.gather(
        orch._loop_perception(),
        orch._loop_gaming(),
        orch._loop_cognitive(),
        orch._loop_voice(),
        orch._loop_execution(),
        run_api_server(orch, host=host, port=port),
    )


# ── MODO GUI ──────────────────────────────────────────────────────────────────

def run_gui():
    """GUI Tkinter — Iron Man HUD con el Hive Kernel de fondo."""
    logger = logging.getLogger("MARK45.GUI")
    try:
        from core.orchestrator import Orchestrator
        from ui.interface import JarvisInterface

        logger.info("Iniciando Orchestrator...")
        orch = Orchestrator()

        # Arrancar los bucles async del Hive Kernel en un hilo de fondo
        def run_background():
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            orch.event_queue = asyncio.Queue()
            orch.running     = True
            try:
                loop.run_until_complete(asyncio.gather(
                    orch._loop_perception(),
                    orch._loop_gaming(),
                    orch._loop_cognitive(),
                    orch._loop_voice(),
                    orch._loop_execution(),
                ))
            except Exception as e:
                logger.debug(f"Background loop: {e}")
            finally:
                loop.close()

        bg_thread = threading.Thread(target=run_background, daemon=True, name="HiveKernel")
        bg_thread.start()

        logger.info("Iniciando interfaz gráfica...")
        ui = JarvisInterface(orch)
        ui.run()

    except Exception as e:
        logger.error(f"Error GUI: {e}", exc_info=True)
        print(f"\n[ERROR] No se pudo iniciar la GUI: {e}")
        print("Iniciando en modo CLI como fallback...\n")
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_cli())


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MARK 45 — Hive Kernel — Ali (Sidi3Ali)"
    )
    parser.add_argument("--cli",    action="store_true", help="Modo consola interactiva")
    parser.add_argument("--web",    action="store_true", help="Daemon headless + API FastAPI")
    parser.add_argument("--debug",  action="store_true", help="Logs detallados")
    parser.add_argument("--host",   default="127.0.0.1",  help="Host para la API (default: 127.0.0.1)")
    parser.add_argument("--puerto", default=8765, type=int, help="Puerto para la API (default: 8765)")
    args = parser.parse_args()

    setup_logging(args.debug)
    logger = logging.getLogger("MARK45.Main")

    logger.info("=" * 60)
    logger.info("  MARK 45 — Hive Kernel — Iniciando")
    logger.info("  Ryzen 7 5800X | 32GB | RTX 4060 Ti 8GB | Win11")
    logger.info("  Creado por Ali (Sidi3Ali)")
    logger.info("=" * 60)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        if args.web:
            asyncio.run(run_web(host=args.host, port=args.puerto))
        elif args.cli:
            asyncio.run(run_cli(args.debug))
        else:
            run_gui()
    except KeyboardInterrupt:
        print("\n🛑 MARK 45 apagado por el usuario.")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
