"""
MARK-45 — Action Dispatcher
=============================
Ejecuta la acción correcta basándose en el intent recibido del IntentEngine.
Todas las respuestas están en español.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import asyncio
import logging
import os
import platform
import re
import subprocess
import urllib.parse
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.intent_engine import Intent

logger = logging.getLogger("MARK45.Dispatcher")
SYSTEM = platform.system()


class ActionDispatcher:
    """Ejecuta acciones analizadas, priorizando plugins dinámicos y fallback local."""

    # LISTA BLANCA DE SEGURIDAD (Evita inyección OS)
    APP_WHITELIST = {
        'chrome', 'vscode', 'code', 'spotify', 'notepad', 'calc',
        'cmd', 'powershell', 'explorer', 'discord', 'steam', 'edge', 'brave'
    }

    def __init__(self, orchestrator):
        self._orch = orchestrator

    async def dispatch(self, intent: 'Intent') -> str:
        """Punto de entrada principal."""
        skill_name = intent.category

        # 1. ENRUTADOR DINÁMICO (Nueva Arquitectura Modular)
        if hasattr(self._orch, '_skills') and skill_name in self._orch._skills:
            skill_module = self._orch._skills[skill_name]
            if hasattr(skill_module, 'handle_intent'):
                try:
                    if asyncio.iscoroutinefunction(skill_module.handle_intent):
                        res = await skill_module.handle_intent(intent, self._orch)
                    else:
                        res = await asyncio.to_thread(skill_module.handle_intent, intent, self._orch)
                    if res: return res
                except Exception as e:
                    logger.error(f"Error en skill modular '{skill_name}': {e}", exc_info=True)
                    return f"Fallo interno en el módulo independiente {skill_name}."

        # 2. FALLBACK LEGACY (Local en Dispatcher)
        handler = self._get_handler(intent.category, intent.subcategory)
        if not handler:
            return await self._ai_chat(intent)
        try:
            result = await handler(intent)
            return result or await self._ai_chat(intent)
        except Exception as e:
            logger.error(f"Dispatcher Legacy [{intent.action}]: {e}", exc_info=True)
            return f"Error ejecutando '{intent.intent}': {e}"

    def _get_handler(self, category: str, subcategory: str) -> Optional[Callable]:
        handlers = {
            # SISTEMA
            ('system', 'status'):       self._system_status,
            ('system', 'open_app'):     self._system_open_app,
            ('system', 'close_app'):    self._system_close_app,
            ('system', 'shutdown'):     self._system_shutdown,
            ('system', 'volume'):       self._system_volume,
            ('system', 'minimize_all'): self._system_minimize_all,
            ('system', 'processes'):    self._system_processes,
            ('system', 'gaming_mode'):  self._system_gaming_mode,
            # PANTALLA
            ('screen', 'analyze'):      self._screen_analyze,
            ('screen', 'screenshot'):   self._screen_screenshot,
            ('screen', 'read_text'):    self._screen_read_text,
            # WEB
            ('web', 'search'):          self._web_search,
            ('web', 'open_url'):        self._web_open_url,
            ('web', 'youtube'):         self._web_youtube,
            # MÚSICA
            ('music', 'play'):          self._music_play,
            ('music', 'pause'):         self._music_pause,
            ('music', 'next'):          self._music_next,
            ('music', 'previous'):      self._music_previous,
            ('music', 'volume'):        self._music_volume,
            ('music', 'info'):          self._music_info,
            # ARCHIVOS
            ('files', 'read'):          self._files_read,
            ('files', 'organize'):      self._files_organize,
            ('files', 'search'):        self._files_search,
            ('files', 'disk_info'):     self._files_disk_info,
            # CÓDIGO
            ('code', 'generate'):       self._code_generate,
            ('code', 'analyze'):        self._code_analyze,
            ('code', 'fix'):            self._code_fix,
            ('code', 'run'):            self._code_run,
            ('code', 'terminal'):       self._code_terminal,
            # IA
            ('ai', 'chat'):             self._ai_chat,
            ('ai', 'summarize'):        self._ai_summarize,
            ('ai', 'translate'):        self._ai_translate,
            ('ai', 'write'):            self._ai_write,
            ('ai', 'explain'):          self._ai_explain,
            # MARK
            ('mark', 'status'):         self._mark_status,
            ('mark', 'history'):        self._mark_history,
            ('mark', 'clear_history'):  self._mark_clear_history,
            ('mark', 'identity'):       self._mark_identity,
            ('mark', 'stop'):           self._mark_stop,
        }
        return handlers.get((category, subcategory))

    # ── SISTEMA ───────────────────────────────────────────────────────────────

    async def _system_status(self, intent: 'Intent') -> str:
        monitor = self._orch.monitor
        if not monitor:
            return "Monitor del sistema no disponible."
        stats  = await asyncio.to_thread(monitor.get_stats)
        focus  = intent.params.get('focus', '')
        lines  = []
        if not focus or 'cpu' in focus:
            lines.append(f"CPU: {stats.get('cpu', 0):.1f}%")
        if not focus or 'ram' in focus:
            lines.append(f"RAM: {stats.get('ram', 0):.1f}% ({stats.get('ram_used_gb', 0):.1f}/{stats.get('ram_total_gb', 32):.0f} GB)")
        if not focus or 'disco' in focus or 'disk' in focus:
            lines.append(f"Disco: {stats.get('disk', 0):.1f}%")
        if stats.get('vram_total_mb'):
            lines.append(f"VRAM: {stats['vram_used_mb']}/{stats['vram_total_mb']} MB")
        if stats.get('gaming_mode'):
            lines.append(f"🎮 Gaming: {stats.get('game_name', 'activo')}")
        return '\n'.join(lines) if lines else monitor.get_summary_text()

    async def _system_open_app(self, intent: 'Intent') -> str:
        app = intent.params.get('name', '') or intent.raw_input
        app = re.sub(r'^(abre|lanza|inicia|ejecuta|pon)\s+(?:el\s+|la\s+)?', '', app, flags=re.IGNORECASE).strip()
        if not app:
            return "¿Qué aplicación quieres abrir, Señor?"
            
        # Validar Whitelist por Seguridad
        app_name_clean = app.split()[0].lower().replace('.exe', '')
        if app_name_clean not in self.APP_WHITELIST:
            logger.warning(f"⚠️ Seguridad: Bloqueada app '{app}' no autorizada.")
            return f"Acceso denegado. La app '{app}' no está en mi protocolo de seguridad autorizada."

        try:
            if SYSTEM == 'Windows':
                # Bug 3: Usar comando start nativo para resolver PATH variables sin pedir rutas completas
                os.system(f'start "" "{app}"')
            else:
                subprocess.Popen([app])
            return f"Abriendo {app}..."
        except Exception as e:
            return f"No pude abrir '{app}': {e}"

    async def _system_close_app(self, intent: 'Intent') -> str:
        app = intent.params.get('name', '') or intent.raw_input
        if not app:
            return "¿Qué aplicación quieres cerrar?"
        try:
            if SYSTEM == 'Windows':
                subprocess.run(f'taskkill /F /IM "{app}.exe"', shell=True, capture_output=True)
            else:
                subprocess.run(['pkill', '-f', app], capture_output=True)
            return f"Cerrando {app}..."
        except Exception as e:
            return f"No pude cerrar '{app}': {e}"

    async def _system_shutdown(self, intent: 'Intent') -> str:
        raw = intent.raw_input.lower()
        if any(w in raw for w in ['reinici', 'restart', 'reboot']):
            if SYSTEM == 'Windows':
                os.system('shutdown /r /t 10')
            else:
                os.system('sudo reboot')
            return "Reiniciando el sistema en 10 segundos. Para cancelar: shutdown /a"
        return "¿Confirmas que quieres apagar el PC? Di 'sí, apaga el PC' para confirmar."

    async def _system_volume(self, intent: 'Intent') -> str:
        action = intent.params.get('action', '')
        raw    = intent.raw_input.lower()
        if SYSTEM == 'Windows':
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                import ctypes
                devices = AudioUtilities.GetSpeakers()
                iface   = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume  = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
                if any(w in raw for w in ['sube', 'más', 'mas', 'subir']):
                    current = volume.GetMasterVolumeLevelScalar()
                    volume.SetMasterVolumeLevelScalar(min(1.0, current + 0.1), None)
                    return "Volumen subido."
                elif any(w in raw for w in ['baja', 'menos', 'bajar']):
                    current = volume.GetMasterVolumeLevelScalar()
                    volume.SetMasterVolumeLevelScalar(max(0.0, current - 0.1), None)
                    return "Volumen bajado."
                elif any(w in raw for w in ['silenci', 'mute', 'calla']):
                    volume.SetMute(1, None)
                    return "Audio silenciado."
            except ImportError:
                pass
        # Fallback: teclas multimedia via pyautogui
        try:
            import pyautogui
            if any(w in raw for w in ['sube', 'más', 'mas', 'subir']):
                for _ in range(5):
                    pyautogui.press('volumeup')
                return "Volumen subido."
            elif any(w in raw for w in ['baja', 'menos', 'bajar']):
                for _ in range(5):
                    pyautogui.press('volumedown')
                return "Volumen bajado."
            elif any(w in raw for w in ['silenci', 'mute', 'calla']):
                pyautogui.press('volumemute')
                return "Audio silenciado."
        except Exception:
            pass
        return "Ajuste de volumen no disponible. Instala pycaw o pyautogui."

    async def _system_minimize_all(self, intent: 'Intent') -> str:
        try:
            import pyautogui
            pyautogui.hotkey('win', 'd')
            return "Todas las ventanas minimizadas."
        except ImportError:
            try:
                if SYSTEM == 'Windows':
                    import ctypes
                    user32 = ctypes.windll.user32
                    user32.keybd_event(0x5B, 0, 0, 0)   # Win key down
                    user32.keybd_event(0x44, 0, 0, 0)   # D key down
                    user32.keybd_event(0x44, 0, 2, 0)   # D key up
                    user32.keybd_event(0x5B, 0, 2, 0)   # Win key up
                    return "Escritorio a la vista, Señor."
            except Exception as e:
                return f"No pude minimizar las ventanas: {e}"
        return "Escritorio mostrado."

    async def _system_processes(self, intent: 'Intent') -> str:
        monitor = self._orch.monitor
        if not monitor:
            return "Monitor no disponible."
        procs = await asyncio.to_thread(monitor.get_top_processes, 8)
        if not procs:
            return "No pude obtener la lista de procesos."
        lines = ["Top procesos por CPU:"]
        for p in procs:
            lines.append(f"  {p['name'][:25]:25} CPU:{p['cpu']:.1f}%  RAM:{p['mem']:.1f}%")
        return '\n'.join(lines)

    async def _system_gaming_mode(self, intent: 'Intent') -> str:
        raw = intent.raw_input.lower()
        if any(w in raw for w in ['activa', 'on', 'encien', 'pon', 'inicia']):
            self._orch.gaming_mode = True
            return f"Modo Gaming activado. VRAM liberada para el juego, {self._orch._user_name}."
        elif any(w in raw for w in ['desactiva', 'off', 'apaga', 'quita', 'desconecta']):
            self._orch.gaming_mode = False
            return "Modo Gaming desactivado. Todos los sistemas cognitivos a pleno rendimiento."
        return f"Modo Gaming: {'🎮 ACTIVO' if self._orch.gaming_mode else '✓ Inactivo'}"

    # ── PANTALLA ──────────────────────────────────────────────────────────────

    async def _screen_analyze(self, intent: 'Intent') -> str:
        try:
            import mss
            import mss.tools
            from PIL import Image
            import io
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img_data = sct.grab(monitor)
            img = Image.frombytes("RGB", img_data.size, img_data.bgra, "raw", "BGRX")
            # Análisis básico sin OCR
            return (
                "He tomado una captura de la pantalla. "
                "Para análisis visual completo necesito un modelo multimodal o pytesseract."
            )
        except Exception as e:
            return f"No pude analizar la pantalla: {e}. Instala mss y Pillow."

    async def _screen_screenshot(self, intent: 'Intent') -> str:
        try:
            import mss
            import mss.tools
            from datetime import datetime
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img_data = sct.grab(monitor)
                fname = os.path.join(
                    os.path.expanduser("~"), "Desktop",
                    f"MARK45_{datetime.now().strftime('%H%M%S')}.png"
                )
                mss.tools.to_png(img_data.rgb, img_data.size, output=fname)
            return f"Captura guardada en el escritorio: {os.path.basename(fname)}"
        except Exception as e:
            return f"Error tomando captura: {e}. Instala mss."

    async def _screen_read_text(self, intent: 'Intent') -> str:
        try:
            import pytesseract
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img_data = sct.grab(monitor)
            img  = Image.frombytes("RGB", img_data.size, img_data.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(img, lang='spa')
            return f"Texto en pantalla:\n\n{text[:2000]}" if text.strip() else "No detecté texto en pantalla."
        except ImportError:
            return "OCR no disponible. Instala pytesseract y mss."
        except Exception as e:
            return f"Error OCR: {e}"

    # ── WEB ───────────────────────────────────────────────────────────────────

    async def _web_search(self, intent: 'Intent') -> str:
        query = intent.params.get('query', '') or intent.raw_input
        query = re.sub(r'^(busca|googlea|google|buscar|en internet)\s+', '', query, flags=re.IGNORECASE).strip()
        if not query:
            return "¿Qué quieres buscar en internet, Señor?"
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Buscando '{query}' en Google."

    async def _web_open_url(self, intent: 'Intent') -> str:
        url = intent.params.get('url', '')
        if not url:
            m = re.search(r'https?://\S+', intent.raw_input)
            url = m.group() if m else ''
        if not url:
            return "¿Qué URL quieres abrir, Señor?"
        if not url.startswith('http'):
            url = 'https://' + url
        webbrowser.open(url)
        return f"Abriendo {url}"

    async def _web_youtube(self, intent: 'Intent') -> str:
        query = intent.params.get('query', '')
        if not query:
            query = re.sub(r'(youtube|yt|pon|busca|ver)\s*', '', intent.raw_input, flags=re.IGNORECASE).strip()
        url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            if query else "https://www.youtube.com"
        )
        webbrowser.open(url)
        return f"Abriendo YouTube{f': {query}' if query else ''}."

    # ── MÚSICA ───────────────────────────────────────────────────────────────

    def _get_spotify(self):
        sp_mod = self._orch._skills.get('spotify')
        if sp_mod:
            try:
                return sp_mod.get_spotify()
            except Exception:
                pass
        return None

    async def _music_play(self, intent: 'Intent') -> str:
        query = (
            intent.params.get('query') or intent.params.get('song') or
            intent.params.get('artist') or intent.params.get('playlist', '')
        )
        sp = self._get_spotify()
        if sp:
            try:
                if query:
                    return await asyncio.to_thread(sp.execute, 'play', {'query': query}, query)
                return await asyncio.to_thread(sp.execute, 'play')
            except Exception:
                pass
        # Fallback YouTube
        url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote((query or '') + ' música')}"
            if query else "https://www.youtube.com/results?search_query=música"
        )
        webbrowser.open(url)
        return f"Abriendo YouTube{f' para {query}' if query else ''}. (Spotify no configurado)"

    async def _music_pause(self, intent: 'Intent') -> str:
        sp = self._get_spotify()
        if sp:
            try:
                return await asyncio.to_thread(sp.execute, 'pause')
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'space')
        except Exception:
            pass
        return "Pausa enviada."

    async def _music_next(self, intent: 'Intent') -> str:
        sp = self._get_spotify()
        if sp:
            try:
                return await asyncio.to_thread(sp.execute, 'next')
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'right')
        except Exception:
            pass
        return "Siguiente canción."

    async def _music_previous(self, intent: 'Intent') -> str:
        sp = self._get_spotify()
        if sp:
            try:
                return await asyncio.to_thread(sp.execute, 'previous')
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'left')
        except Exception:
            pass
        return "Canción anterior."

    async def _music_volume(self, intent: 'Intent') -> str:
        level = intent.params.get('level', 50)
        sp    = self._get_spotify()
        if sp:
            try:
                return await asyncio.to_thread(sp.execute, 'volume', {'level': level})
            except Exception:
                pass
        return f"Volumen ajustado (Spotify no configurado). Usa el comando de sistema para el volumen general."

    async def _music_info(self, intent: 'Intent') -> str:
        sp = self._get_spotify()
        if sp:
            try:
                return await asyncio.to_thread(sp.execute, 'current')
            except Exception:
                pass
        return "Spotify no configurado. Añade tus credenciales en memory/spotify_config.json."

    # ── ARCHIVOS ──────────────────────────────────────────────────────────────

    async def _files_read(self, intent: 'Intent') -> str:
        path = intent.params.get('path', '') or intent.params.get('file', '')
        
        # Bug 4: Amnesia de contexto. Interrogar state si no hay archivo en la frase
        if not path and self._orch._conv_state:
            path = self._orch._conv_state.last_file

        if not path:
            m = re.search(r'["\']([^"\']+\.[a-zA-Z0-9]+)["\']|([A-Za-z]:\\[^\s]+|/[^\s]+)', intent.raw_input)
            if m:
                path = m.group(1) or m.group(2)
        if not path:
            return "¿Qué archivo quieres que lea? Dime la ruta o el nombre, Señor."
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if self._orch.llm:
                return await asyncio.to_thread(
                    self._orch.llm.generate,
                    f"Analiza este archivo y da un resumen:\n\n{content[:3000]}",
                    False, 600
                )
            return content[:2000]
        except Exception as e:
            return f"No pude leer '{path}': {e}"

    async def _files_organize(self, intent: 'Intent') -> str:
        folder = intent.params.get('folder', '')
        raw    = intent.raw_input.lower()
        if not folder:
            if 'descargas' in raw or 'downloads' in raw:
                folder = os.path.expanduser('~/Downloads')
                if not os.path.exists(folder):
                    folder = os.path.expanduser('~/Descargas')
            elif 'escritorio' in raw or 'desktop' in raw:
                folder = os.path.expanduser('~/Desktop')
        if not folder or not os.path.exists(folder):
            return f"No encontré la carpeta '{folder}'. Indica una ruta válida."
        try:
            from skills.file_skill import FileSkill
            fs = FileSkill()
            result = await asyncio.to_thread(fs.organize_by_type, folder)
            moved = result.get('moved', 0)
            return f"Carpeta organizada: {moved} archivos movidos por tipo."
        except Exception as e:
            return f"Error organizando archivos: {e}"

    async def _files_search(self, intent: 'Intent') -> str:
        query = intent.params.get('query', '') or intent.params.get('name', '')
        if not query:
            query = re.sub(r'(busca|encuentra|dónde|donde|archivos?)\s*', '', intent.raw_input, flags=re.IGNORECASE).strip()
        try:
            from skills.file_skill import FileSkill
            fs = FileSkill()
            results = await asyncio.to_thread(fs.search_files, query)
            if not results:
                return f"No encontré archivos que coincidan con '{query}'."
            lines = [f"Archivos encontrados para '{query}':"]
            for r in results[:10]:
                lines.append(f"  • {r}")
            return '\n'.join(lines)
        except Exception as e:
            return f"Error buscando archivos: {e}"

    async def _files_disk_info(self, intent: 'Intent') -> str:
        monitor = self._orch.monitor
        if monitor:
            stats = await asyncio.to_thread(monitor.get_stats)
            return f"Disco C:\\: {stats.get('disk', 0):.1f}% usado."
        try:
            import shutil
            total, used, free = shutil.disk_usage("C:\\")
            return (
                f"Disco C:\\ — Total: {total//1e9:.0f} GB | "
                f"Usado: {used//1e9:.0f} GB | "
                f"Libre: {free//1e9:.0f} GB ({free/total*100:.1f}%)"
            )
        except Exception as e:
            return f"Error obteniendo información del disco: {e}"

    # ── CÓDIGO ────────────────────────────────────────────────────────────────

    async def _code_generate(self, intent: 'Intent') -> str:
        description = intent.params.get('description', '') or intent.raw_input
        language    = intent.params.get('language', 'python')
        if not self._orch.llm:
            return "LLM no disponible para generar código."
        code = await asyncio.to_thread(
            self._orch.llm.generate,
            f"Genera código {language} completo y funcional para:\n{description}\n\n"
            f"Solo el código limpio y comentado en español, sin explicaciones adicionales.",
            False, 1500, 0.3
        )
        # Extraer bloque de código si está en markdown
        match = re.search(r'```(?:\w+)?\n(.*?)```', code, re.DOTALL)
        if match:
            code = match.group(1)
        safe = re.sub(r'[^\w]', '_', description.split()[-1] or 'script')[:20]
        fp   = os.path.join('workspace', f'{safe}.py')
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(code)
            preview = code[:400] + '\n...' if len(code) > 400 else code
            return f"Script guardado en `{fp}`:\n\n```{language}\n{preview}\n```"
        except Exception:
            return f"Código generado:\n\n```{language}\n{code[:800]}\n```"

    async def _code_analyze(self, intent: 'Intent') -> str:
        code = intent.params.get('code', '') or intent.raw_input
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(self._orch.llm.analyze_code, code)

    async def _code_fix(self, intent: 'Intent') -> str:
        code = intent.params.get('code', '') or intent.raw_input
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(
            self._orch.llm.generate,
            f"Corrige este código y explica en español qué estaba mal:\n\n{code}",
            False, 800
        )

    async def _code_run(self, intent: 'Intent') -> str:
        path = intent.params.get('path', '') or intent.params.get('script', '')
        if not path:
            return "¿Qué script quieres ejecutar?"
        try:
            result = subprocess.run(
                ['python', path], capture_output=True, text=True, timeout=30
            )
            output = (result.stdout or result.stderr or '').strip()
            return output[:1500] if output else f"Script ejecutado. Código: {result.returncode}"
        except subprocess.TimeoutExpired:
            return "El script tardó demasiado (timeout 30s)."
        except Exception as e:
            return f"Error ejecutando script: {e}"

    async def _code_terminal(self, intent: 'Intent') -> str:
        cmd = intent.params.get('cmd', '') or intent.params.get('command', '')
        if not cmd:
            cmd = re.sub(r'(ejecuta|corre|run|terminal)\s*', '', intent.raw_input, flags=re.IGNORECASE).strip()
        if not cmd:
            return "¿Qué comando quieres ejecutar?"
        # Bloquear comandos peligrosos
        BLOCKED = ['rm -rf', 'del /f', 'format', 'rmdir /s', 'rd /s', 'shutdown', 'reboot']
        if any(b in cmd.lower() for b in BLOCKED):
            return f"Comando rechazado por seguridad: '{cmd}'"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            output = (result.stdout or result.stderr or '').strip()
            return output[:1500] if output else f"Comando ejecutado (sin salida). Código: {result.returncode}"
        except subprocess.TimeoutExpired:
            return "Timeout (15s)."
        except Exception as e:
            return f"Error: {e}"

    # ── IA / CONVERSACIÓN ─────────────────────────────────────────────────────

    async def _ai_chat(self, intent: 'Intent') -> str:
        text = intent.raw_input
        if not text:
            return f"Aquí, {self._orch._user_name}. ¿En qué puedo ayudarle?"
        if intent.params.get('type') == 'greeting':
            import random
            h = datetime.now().hour
            time_str = "buenos días" if h < 12 else "buenas tardes" if h < 20 else "buenas noches"
            return random.choice([
                f"{time_str.capitalize()}, {self._orch._user_name}. ¿Qué necesita?",
                f"Sistemas activos. ¿En qué puedo ayudarle, {self._orch._user_name}?",
                f"Aquí, Señor. ¿Qué le traigo?",
            ])
        # Hora/fecha
        if any(w in text.lower() for w in ['hora', 'fecha', 'día', 'date', 'time']):
            return datetime.now().strftime("Son las %H:%M del %d de %B de %Y.")
        if not self._orch.llm:
            return "LLM no disponible. Inicia LM Studio u Ollama."
        ctx    = self._orch.memory.get_context_str() if self._orch.memory else ""
        prompt = f"[Usuario: {self._orch._user_name}. {ctx}]\n\n{text}" if ctx else text
        return await asyncio.to_thread(self._orch.llm.generate, prompt, True, 700)

    async def _ai_summarize(self, intent: 'Intent') -> str:
        text = intent.params.get('text', '') or intent.raw_input
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(self._orch.llm.summarize, text)

    async def _ai_translate(self, intent: 'Intent') -> str:
        text   = intent.params.get('text', '') or intent.raw_input
        target = intent.params.get('to', 'inglés')
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(
            self._orch.llm.generate,
            f"Traduce al {target}:\n\n{text}", False, 500
        )

    async def _ai_write(self, intent: 'Intent') -> str:
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(
            self._orch.llm.generate, f"Redacta:\n{intent.raw_input}", True, 800
        )

    async def _ai_explain(self, intent: 'Intent') -> str:
        if not self._orch.llm:
            return "LLM no disponible."
        return await asyncio.to_thread(
            self._orch.llm.generate,
            f"Explica de forma clara y directa en español:\n{intent.raw_input}", True, 600
        )

    # ── MARK (AUTOGESTIÓN) ────────────────────────────────────────────────────

    async def _mark_status(self, intent: 'Intent') -> str:
        llm_s  = self._orch.llm.active_provider if self._orch.llm else "No disponible"
        mon_s  = self._orch.monitor.get_summary_text() if self._orch.monitor else "Monitor: N/A"
        intent_s = self._orch.intent.get_stats() if self._orch.intent else "IntentEngine: N/A"
        mem_s  = str(self._orch.memory.get_stats()) if self._orch.memory else ""
        gaming = "🎮 GAMING MODE" if self._orch.gaming_mode else "Modo normal"
        return (
            f"MARK 45 — Estado\n"
            f"  LLM: {llm_s}\n"
            f"  Sistema: {mon_s}\n"
            f"  Intenciones: {intent_s}\n"
            f"  Memoria: {mem_s}\n"
            f"  Modo: {gaming}"
        )

    async def _mark_history(self, intent: 'Intent') -> str:
        if not self._orch.memory:
            return "Memoria no disponible."
        recent = self._orch.memory.get_recent(10)
        if not recent:
            return "No hay historial de conversación todavía."
        lines = ["Historial reciente:"]
        for h in recent:
            role = "Señor" if h['role'] == 'user' else "MARK"
            lines.append(f"  [{h.get('timestamp', '?')[:16]}] {role}: {h['text'][:80]}")
        return '\n'.join(lines)

    async def _mark_clear_history(self, intent: 'Intent') -> str:
        if self._orch.memory:
            self._orch.memory.clear_history()
        if self._orch.llm:
            self._orch.llm.clear_history()
        return "Historial de conversación limpiado, Señor."

    async def _mark_identity(self, intent: 'Intent') -> str:
        return (
            "Soy MARK 45, el asistente de inteligencia artificial personal de Ali (Sidi3Ali). "
            "Ejecutándome en un Ryzen 7 5800X con 32GB de RAM y RTX 4060 Ti 8GB. "
            "Creado para ser el sistema de IA más avanzado que Ali ha construido."
        )

    async def _mark_stop(self, intent: 'Intent') -> str:
        self._orch.running = False
        return f"Hasta luego, {self._orch._user_name}. MARK 45 desconectándose."
