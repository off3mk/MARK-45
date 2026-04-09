"""
MARK-45 — Hive Kernel (Orchestrator)
=======================================
Cerebro central asíncrono de MARK 45.

Hardware: Ryzen 7 5800X | 32GB RAM | RTX 4060 Ti 8GB | Win11
Modelo LLM objetivo: Qwen3-8B Q5_K_M en LM Studio (CUDA)

Arquitectura:
  • asyncio puro — 6 bucles paralelos, nunca se bloquea
  • IntentEngine  — LLM + rapidfuzz clasifica cualquier frase → acción
  • Dispatcher    — ejecuta la acción sin lógica de interpretación
  • WakeWordDaemon — escucha continua "Jarvis", pausa al hablar
  • Gaming Mode   — detecta juegos, libera VRAM automáticamente

Creado por Ali (Sidi3Ali) — MARK 45
"""

import asyncio
import getpass
import importlib
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("MARK45")

_IDENTITY = {
    "name":    "MARK 45",
    "creator": "Ali",
    "alias":   "Sidi3Ali",
    "version": "45.0",
    "hw":      "Ryzen 7 5800X | 32GB | RTX 4060 Ti 8GB | Win11",
}


class Orchestrator:
    """Director central de MARK 45 — Hive Kernel."""

    def __init__(self):
        self.running     = False
        self.gaming_mode = False
        self._ui_cb: Optional[Callable] = None   # Tkinter (modo GUI)
        self._chat: List[Dict] = []
        self._llm_notified = False   # Notificación TTS única por caída de LLM

        # EventBus — cola agnóstica compartida entre Tkinter y API
        self.event_bus: asyncio.Queue = asyncio.Queue(maxsize=500)

        # Control de Event Loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Continuous Conversation Mode (Bypass Wake Word)
        self.last_successful_command_time: float = 0.0

        # Bug 1: Control de confirmaciones directas (PendingAction)
        self.pending_action: Optional[str] = None

        # Perfilador de hardware
        try:
            from core.hardware_profiler import get_profile
            self.hardware_mode = get_profile()
        except Exception:
            self.hardware_mode = "MODE_LIGHT"

        # Estado conversacional (para HeuristicBrain)
        try:
            from core.heuristic_brain import ConversationState
            self._conv_state = ConversationState()
        except Exception:
            self._conv_state = None

        self._print_banner()

        # Identidad del usuario
        self._user_name  = "Señor"
        self._is_creator = False
        self._load_identity()

        # Módulos — orden importa
        self.llm     = self._init("LLM Engine",      self._load_llm)
        self.memory  = self._init("Memoria",         self._load_memory)
        self.monitor = self._init("Monitor Sistema", self._load_monitor)
        self._voice  = self._init("Voz",             self._load_voice)
        self._skills: Dict[str, Any] = {}
        self._load_skills()

        self.intent   = self._init("IntentEngine",  self._load_intent)
        self.dispatch = self._init("Dispatcher",    self._load_dispatcher)

        # Wake word daemon
        self._wake_daemon: Optional[Any] = None
        if self._voice:
            self._wake_daemon = self._init("WakeWord", self._load_wake_daemon)

        # Cola asyncio — se crea en start()
        self.event_queue: Optional[asyncio.Queue] = None

        self._print_ready()

    # ── BANNER ────────────────────────────────────────────────────────────────

    def _print_banner(self):
        logger.info("=" * 60)
        logger.info("  M A R K  4 5  — Hive Kernel")
        logger.info(f"  Creado por Ali (Sidi3Ali)")
        logger.info(f"  HW: {_IDENTITY['hw']}")
        logger.info("=" * 60)

    def _print_ready(self):
        logger.info("-" * 60)
        logger.info(f"  Usuario:  {self._user_name} ({'Creador' if self._is_creator else 'Estándar'})")
        logger.info(f"  LLM:      {getattr(self.llm, 'active_provider', 'N/A')}")
        logger.info(f"  Voz TTS:  {'✓ edge-tts' if getattr(self._voice, 'tts_enabled', False) else '✗'}")
        logger.info(f"  Voz STT:  {'✓' if getattr(self._voice, 'stt_enabled', False) else '✗'}")
        logger.info(f"  WakeWord: {'✓ Jarvis' if self._wake_daemon else '✗'}")
        logger.info(f"  Monitor:  {'✓' if self.monitor else '✗'}")
        logger.info("-" * 60)

    # ── LOADERS ───────────────────────────────────────────────────────────────

    def _init(self, name: str, loader) -> Any:
        try:
            result = loader()
            return result
        except Exception as e:
            logger.debug(f"{name} no cargado: {e}")
            return None

    def _load_identity(self):
        try:
            uname = getpass.getuser().lower()
            self._is_creator = any(x in uname for x in ["ali", "sidi"])
            self._user_name  = "Señor" if self._is_creator else uname.capitalize()
        except Exception:
            pass

    def _load_llm(self):
        from core.llm_engine import LLMEngine
        llm = LLMEngine()
        logger.info(f"✓ LLM Engine ({llm.active_provider})")
        return llm

    def _load_memory(self):
        from core.memory import Memory
        m = Memory()
        logger.info("✓ Memoria persistente")
        return m

    def _load_monitor(self):
        from perception.system_monitor import SystemMonitor
        m = SystemMonitor()
        logger.info("✓ Monitor del sistema")
        return m

    def _load_voice(self):
        from core.voice import VoiceSystem
        v = VoiceSystem()
        logger.info("✓ Sistema de voz")
        return v

    def _load_wake_daemon(self):
        from core.voice import WakeWordDaemon
        def on_wake_command(text: str):
            if self.event_queue and self._loop:
                # Usar call_soon_threadsafe para evitar RuntimeError o warning no-awaited en Queue.put
                self._loop.call_soon_threadsafe(
                    self.event_queue.put_nowait,
                    {"type": "voice_command", "text": text}
                )
            else:
                # Procesado síncrono si el loop no está activo
                import threading
                threading.Thread(
                    target=lambda: self._process_voice_cmd_sync(text),
                    daemon=True
                ).start()
        daemon = WakeWordDaemon(self._voice, on_wake_command)
        daemon.start()
        logger.info(f"✓ Wake word daemon (Jarvis) [{self.hardware_mode}]")
        return daemon

    def _load_intent(self):
        from core.intent_engine import IntentEngine
        ie = IntentEngine(self.llm)
        logger.info("✓ IntentEngine (LLM + rapidfuzz)")
        return ie

    def _load_dispatcher(self):
        from core.dispatcher import ActionDispatcher
        d = ActionDispatcher(self)
        logger.info("✓ Dispatcher")
        return d

    def _load_skills(self):
        import pkgutil
        import skills
        
        logger.info("Cargando sistema de skills dinámico...")
        for _, name, _ in pkgutil.iter_modules(skills.__path__):
            try:
                mod_path = f"skills.{name}"
                # Quitar sufijo '_skill' si existe para que calce con la categoría (e.g. 'spotify_skill' -> 'spotify')
                cat_name = name.replace('_skill', '')
                self._skills[cat_name] = importlib.import_module(mod_path)
                logger.debug(f"  + Skill registrada: {cat_name} ({mod_path})")
            except Exception as e:
                logger.error(f"Error cargando skill '{name}': {e}")

    # ── ARRANQUE ASYNC ────────────────────────────────────────────────────────

    async def start(self):
        """Punto de entrada asíncrono principal."""
        self._loop = asyncio.get_running_loop()
        self.running = True
        self.event_queue = asyncio.Queue()
        logger.info("MARK 45 en línea.")

        await self._speak(self._greeting(), "greeting")
        logger.info("🚀 MARK 45 — Todos los sistemas activos")

        await asyncio.gather(
            self._loop_perception(),
            self._loop_gaming(),
            self._loop_cognitive(),
            self._loop_voice(),
            self._loop_execution(),
            self._loop_active_window(),
        )

    # ── BUCLES ASYNC ──────────────────────────────────────────────────────────

    async def _loop_perception(self):
        """Sensores HW — cada 1s."""
        while self.running:
            try:
                if self.monitor:
                    stats = await asyncio.to_thread(self.monitor.get_stats)
                    self.gaming_mode = stats.get("gaming_mode", False)
                    # Publicar en EventBus (API WebSocket)
                    await self.publish("stats", {
                        "cpu":           stats.get("cpu", 0),
                        "ram":           stats.get("ram", 0),
                        "ram_gb":        f"{stats.get('ram_used_gb',0):.1f}/{stats.get('ram_total_gb',0):.0f}",
                        "disco":         stats.get("disk", 0),
                        "vram_usado_mb": stats.get("vram_used_mb", 0),
                        "vram_total_mb": stats.get("vram_total_mb", 0),
                        "gaming":        stats.get("gaming_mode", False),
                        "juego":         stats.get("game_name", ""),
                    })
                    # Tkinter callback (modo GUI)
                    if self._ui_cb:
                        self._ui_cb("stats", stats)
            except Exception as e:
                logger.debug(f"perception loop: {e}")
            await asyncio.sleep(1)

    async def _loop_gaming(self):
        """Transiciones Gaming Mode — cada 5s."""
        was_gaming = False
        while self.running:
            try:
                if self.gaming_mode and not was_gaming:
                    logger.warning("🎮 GAMING MODE ON")
                    await self._speak(
                        f"Modo Gaming activado, {self._user_name}. VRAM liberada.", "info"
                    )
                    if self.llm:
                        await asyncio.to_thread(self.llm.unload_model)
                    was_gaming = True
                elif not self.gaming_mode and was_gaming:
                    logger.info("✅ GAMING MODE OFF")
                    await self._speak("Modo Gaming desactivado. Sistemas a pleno rendimiento.", "info")
                    if self.llm:
                        await asyncio.to_thread(self.llm.reload_model)
                    was_gaming = False
            except Exception as e:
                logger.debug(f"gaming loop: {e}")
            await asyncio.sleep(5)

    async def _loop_cognitive(self):
        """Monitoreo cognitivo — cada 30s (pausado en gaming)."""
        while self.running:
            interval = 60 if self.gaming_mode else 30
            try:
                if not self.gaming_mode and self.monitor:
                    stats = await asyncio.to_thread(self.monitor.get_stats)
                    cpu = stats.get("cpu", 0)
                    ram = stats.get("ram", 0)
                    if cpu > 90:
                        if self.event_queue:
                            await self.event_queue.put({
                                "type": "speak",
                                "text": f"Alerta: CPU al {cpu:.0f} por ciento, Señor.",
                                "speech_type": "alert",
                            })
                    if ram > 90:
                        if self.event_queue:
                            await self.event_queue.put({
                                "type": "speak",
                                "text": f"Memoria RAM al {ram:.0f} por ciento. Considera cerrar aplicaciones.",
                                "speech_type": "alert",
                            })
            except Exception as e:
                logger.debug(f"cognitive loop: {e}")
            await asyncio.sleep(interval)

    async def _loop_active_window(self):
        """Monitor de la ventana activa para modos de conversación continua (30s)."""
        was_active = False
        while self.running:
            try:
                is_active = self._is_window_active()
                if is_active and not was_active:
                    was_active = True
                    await self.publish("estado_ia", {"estado": "MODOACTIVO"})
                elif not is_active and was_active:
                    was_active = False
                    await self.publish("estado_ia", {"estado": "NOMINAL"})
            except Exception as e:
                logger.debug(f"active_window loop: {e}")
            await asyncio.sleep(0.5)

    def _is_window_active(self) -> bool:
        return (time.time() - self.last_successful_command_time) < 30.0

    async def _loop_voice(self):
        """STT loop — solo si no hay WakeWordDaemon activo."""
        v = self._voice
        # Si el wake daemon está corriendo, este loop no hace nada
        if self._wake_daemon and self._wake_daemon.is_alive():
            return
        if not v or not getattr(v, "stt_enabled", False):
            return
        while self.running:
            try:
                if v.is_speaking():
                    await asyncio.sleep(0.1)
                    continue
                text = await asyncio.to_thread(v.listen, 3.0, 15.0)
                if text and len(text.strip()) > 1:
                    if self.event_queue:
                        await self.event_queue.put({
                            "type": "voice_command",
                            "text": text.strip(),
                        })
            except Exception:
                await asyncio.sleep(0.5)

    async def _loop_execution(self):
        """Ejecutor de eventos de la cola."""
        while self.running:
            try:
                ev = await asyncio.wait_for(
                    self.event_queue.get(), timeout=1.0
                )
                await self._process_event(ev)
                self.event_queue.task_done()
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"execution loop: {e}")

    async def _process_event(self, ev: Dict):
        t = ev.get("type", "")
        if t == "speak":
            texto = ev.get("text", "")
            await self._speak(texto, ev.get("speech_type", "info"))
            if texto:
                await self.publish("chat", {"rol": "mark", "texto": texto})
        elif t in ("voice_command", "text_command"):
            text = ev.get("text", "")
            if text:
                await self.publish("chat", {"rol": "usuario", "texto": text})
                await self.publish("estado_ia", {"estado": "PROCESANDO"})
                resp = await self.handle_command(text)
                if resp:
                    await self._speak(resp)
                    if self._is_window_active():
                        await self.publish("estado_ia", {"estado": "MODOACTIVO"})
                    else:
                        await self.publish("estado_ia", {"estado": "NOMINAL"})
                    if self._ui_cb:
                        self._ui_cb("response", {"user": text, "mark": resp})

    # ── COMANDO PRINCIPAL ─────────────────────────────────────────────────────

    async def handle_command(self, user_input: str) -> str:
        """
        Procesar CUALQUIER entrada del usuario.
        Flujo: IntentEngine (LLM→Brain→fuzzy) → Dispatcher → Respuesta en español.
        Soporta multi-intent secuencial.
        """
        if not user_input or not user_input.strip():
            return ""

        text = user_input.strip()
        logger.info(f"CMD: '{text}'")

        if self.memory:
            self.memory.add_turn("user", text)

        # Detectar caída de LLM y notificar una sola vez
        llm_offline = not (self.llm and getattr(self.llm, '_model', None))
        if llm_offline and not self._llm_notified:
            self._llm_notified = True
            aviso = "Servidores de IA desconectados. Operando en modo táctico heurístico."
            logger.warning(aviso)
            await self.publish("estado_ia", {"estado": "OFFLINE"})
            await self._speak(aviso, "alert")
        elif not llm_offline:
            # LLM vuelve en línea: restablecer flag
            self._llm_notified = False

        # --- BUG 1: INTERCEPTO PENDING_ACTION (INFINITE LOOP) ---
        if self.pending_action == 'shutdown':
            t_lower = text.lower()
            if any(w in t_lower for w in ['sí', 'si', 'apaga', 'hazlo', 'ok', 'vale']):
                import os, platform
                if platform.system() == 'Windows':
                    os.system('shutdown /s /t 10')
                else:
                    os.system('sudo shutdown now')
                self.pending_action = None
                resp = "Apagando el ordenador principal."
                await self._speak(resp)
                if self.memory: self.memory.add_turn("mark", resp)
                await self.publish("chat", {"rol": "mark", "texto": resp})
                return resp
            elif any(w in t_lower for w in ['no', 'cancela', 'para', 'detén']):
                self.pending_action = None
                resp = "Apagado del sistema cancelado."
                await self._speak(resp)
                if self.memory: self.memory.add_turn("mark", resp)
                await self.publish("chat", {"rol": "mark", "texto": resp})
                return resp
            # Si no es sí/no, asumimos que ignora la confirmación y sigue adelante:
            self.pending_action = None

        conv_ctx = self.memory.get_context_str(6) if self.memory else ""

        if not self.intent or not self.dispatch:
            return await self._llm_fallback(text)

        # Clasificar — pasar ConversationState al engine
        intent = await asyncio.to_thread(
            self.intent.classify, text, "", conv_ctx, self._conv_state
        )
        logger.info(f"Intent: {intent.action} ({intent.confidence:.0%}) — {intent.intent}")

        # Multi-intent: si el Brain devuelvió varios intents, ejecutarlos secuencialmente
        multi = getattr(intent, '_multi', None)
        if multi and len(multi) > 1:
            responses = []
            for item in multi:
                from core.intent_engine import Intent
                sub_intent = Intent.from_action(
                    item['action'], text, item.get('confidence', 0.80)
                )
                sub_intent.params = item.get('params', {})
                resp = await self.dispatch.dispatch(sub_intent)
                if resp:
                    responses.append(resp)
                # Actualizar estado conversacional
                if self._conv_state:
                    self._conv_state.update(item['action'],
                                            item.get('params', {}).get('query', ''),
                                            item.get('params', {}))
            response = ' '.join(responses) or "Entendido."
        else:
            response = await self.dispatch.dispatch(intent)
            response = response or "Entendido, Señor."
            # Actualizar estado conversacional
            if self._conv_state:
                self._conv_state.update(intent.action,
                                        intent.params.get('query', ''),
                                        intent.params)

        if self.memory:
            self.memory.add_turn("mark", response)

        # Publicar en EventBus para API WebSocket
        await self.publish("chat", {"rol": "mark", "texto": response})

        # Al renovar o completar comandos con éxito, extender la ventana de conversación 30s
        self.last_successful_command_time = time.time()

        return response

    def _process_voice_cmd_sync(self, text: str):
        """Procesar un comando de voz de forma síncrona (sin asyncio activo)."""
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(self.handle_command(text))
            if resp and self._voice:
                self._voice.speak(resp)
            if self._ui_cb:
                self._ui_cb("response", {"user": text, "mark": resp})
        finally:
            loop.close()

    async def _llm_fallback(self, text: str) -> str:
        if not self.llm:
            return "Sistema no disponible. Comprueba los logs."
        return await asyncio.to_thread(self.llm.generate, text, True, 700)

    # ── VOZ ───────────────────────────────────────────────────────────────────

    async def _speak(self, text: str, speech_type: str = "info"):
        if not text or not self._voice:
            return
        try:
            v = self._voice
            if hasattr(v, "speak"):
                await asyncio.to_thread(v.speak, text)
        except Exception as e:
            logger.debug(f"speak: {e}")

    def speak_sync(self, text: str):
        v = self._voice
        if v and hasattr(v, "speak"):
            try:
                v.speak(text)
            except Exception:
                pass

    def _greeting(self) -> str:
        h = datetime.now().hour
        g = "Buenos días" if h < 12 else "Buenas tardes" if h < 20 else "Buenas noches"
        return (
            f"{g}, {self._user_name}. "
            f"MARK 45 en línea. "
            f"Hive Kernel activo — todos los sistemas a su disposición."
        )

    # ── EventBus (API WebSocket) ───────────────────────────────────────────────

    async def publish(self, tipo: str, datos: dict):
        """
        Publicar un evento en el EventBus.
        La API server drena este bus y hace broadcast por WebSocket.
        Tipos: 'stats' | 'chat' | 'estado_ia' | 'alerta'
        """
        evento = {
            "tipo":  tipo,
            "datos": datos,
            "hora":  datetime.now().strftime("%H:%M:%S"),
        }
        try:
            self.event_bus.put_nowait(evento)
        except asyncio.QueueFull:
            # Si el bus está lleno, descartar evento más antiguo
            try:
                self.event_bus.get_nowait()
                self.event_bus.put_nowait(evento)
            except Exception:
                pass

    # ── UTILIDADES PÚBLICAS ───────────────────────────────────────────────────

    def set_ui_callback(self, cb: Callable):
        """Registrar callback Tkinter (modo GUI). No afecta al WebSocket."""
        self._ui_cb = cb

    def send_text_command(self, text: str) -> str:
        """Llamada síncrona desde UI (hilo separado, sin asyncio activo)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.handle_command(text))
        finally:
            loop.close()

    def get_stats(self) -> Dict:
        if self.monitor:
            try:
                return {"system": self.monitor.get_stats()}
            except Exception:
                pass
        return {}

    async def shutdown(self):
        logger.info("Apagando MARK 45...")
        self.running = False
        if self._wake_daemon:
            self._wake_daemon.stop()
        logger.info("MARK 45 apagado.")

    def shutdown_sync(self):
        if self._wake_daemon:
            self._wake_daemon.stop()
        self.running = False
