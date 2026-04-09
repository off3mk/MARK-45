"""
MARK-45 — Sistema de Voz
==========================
TTS: Edge TTS (es-ES-AlvaroNeural) → pyttsx3 fallback
STT: speech_recognition (Google, es-ES)
Wake Word Daemon: escucha continua, pausa cuando el sistema habla.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import asyncio
import logging
import os
import queue
import re
import tempfile
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("MARK45.Voice")


# ── LIMPIADOR DE TEXTO ───────────────────────────────────────────────────────

class TextCleaner:
    """Limpia texto para que suene natural al hablar en español."""

    REMOVE_PATTERNS = [
        r'\([^)]*\)',           # (contenido entre paréntesis)
        r'\[[^\]]*\]',          # [etiquetas]
        r'https?://\S+',        # URLs
        r'www\.\S+',
        r'\*+([^*]+)\*+',       # **negrita** → solo texto
        r'#{1,6}\s+',           # Headers markdown
        r'`+([^`]*)`+',         # `código`
        r'[•▪►◦▸→]',
        r'✓|✗|△|☆|★|◈',
        r'\d+\.\s(?=\w)',
        r'[-]{2,}',
        r'[_]{2,}',
    ]

    REPLACEMENTS = [
        (r'(\d+)%', r'\1 por ciento'),
        (r'(\d+\.?\d*)\s*GB', r'\1 gigabytes'),
        (r'(\d+\.?\d*)\s*MB', r'\1 megabytes'),
        (r'(\d+\.?\d*)\s*KB', r'\1 kilobytes'),
        (r'\bCPU\b', 'la CPU'),
        (r'\bRAM\b', 'la RAM'),
        (r'\bPC\b', 'el PC'),
        (r'J\.A\.R\.V\.I\.S\.', 'MARK'),
        (r'M\.A\.R\.K\.', 'MARK'),
    ]

    def clean_for_tts(self, text: str) -> str:
        if not text:
            return ""
        result = text
        for pattern in self.REMOVE_PATTERNS:
            result = re.sub(pattern, ' ', result)
        for pattern, replacement in self.REPLACEMENTS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        result = re.sub(r',\s*', ' ', result)
        result = re.sub(r';', ' ', result)
        result = re.sub(r':\s*(?!\d)', ' ', result)
        result = re.sub(r'—|–', ' ', result)
        result = re.sub(r'\.\.\.', '.', result)
        result = re.sub(r'\n+', '. ', result)
        result = re.sub(r'\s+', ' ', result).strip()
        # Resumir si es muy largo
        if len(result) > 250:
            cut = result.find('.', 150)
            if 0 < cut < 220:
                result = result[:cut + 1] + " Más detalles en pantalla."
            else:
                result = result[:200].rstrip() + "... más detalles en pantalla."
        return result.strip()

    def should_speak(self, text: str) -> bool:
        if not text or len(text.strip()) < 3:
            return False
        if len(text.strip().split('\n')) > 10:
            return False
        return True


# ── SISTEMA DE VOZ PRINCIPAL ─────────────────────────────────────────────────

class VoiceSystem:
    """TTS natural + STT en español para MARK-45."""

    def __init__(self):
        self.tts_enabled = False
        self.stt_enabled = False
        self.voice_name  = "es-ES-AlvaroNeural"
        self._tts_queue: queue.Queue = queue.Queue()
        self._speaking   = False
        self._use_pyttsx3 = False
        self.cleaner     = TextCleaner()
        self.is_muted    = False  # EXTRA PRO: Modo Silencio o Desactivar Escucha

        self._init_tts()
        self._init_stt()
        if self.tts_enabled:
            self._start_tts_worker()
        logger.info(
            f"VoiceSystem listo — TTS: {'edge-tts' if not self._use_pyttsx3 else 'pyttsx3'} | "
            f"STT: {'✓' if self.stt_enabled else '✗'}"
        )

    # ── INIT ──────────────────────────────────────────────────────────────────

    def _init_tts(self):
        try:
            import edge_tts  # noqa
            self.tts_enabled  = True
            self._use_pyttsx3 = False
            logger.info("✓ Edge TTS disponible (es-ES-AlvaroNeural)")
            return
        except ImportError:
            pass
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty('rate', 165)
            self._engine.setProperty('volume', 0.9)
            voices = self._engine.getProperty('voices')
            for v in voices:
                if any(x in v.name.lower() for x in ['spanish', 'español', 'helena', 'pablo', 'sabina']):
                    self._engine.setProperty('voice', v.id)
                    break
            self.tts_enabled  = True
            self._use_pyttsx3 = True
            logger.info("✓ pyttsx3 disponible como TTS fallback")
        except ImportError:
            logger.warning("⚠ Sin TTS disponible (instala edge-tts)")

    def _init_stt(self):
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            # EXTRA PRO: Sensibilidad Configurable
            self._recognizer.energy_threshold    = 300  # Más alto = menos falso positivo (ruido leve)
            self._recognizer.pause_threshold     = 0.8  # Rápidex de corte de silencio
            self._recognizer.dynamic_energy_threshold = True
            self.stt_enabled = True
            logger.info("✓ STT disponible (speech_recognition)")
        except ImportError:
            logger.warning("⚠ speech_recognition no disponible")

    def _start_tts_worker(self):
        t = threading.Thread(target=self._tts_worker, daemon=True, name="TTS-Worker")
        t.start()

    def _tts_worker(self):
        while True:
            try:
                text = self._tts_queue.get(timeout=1)
                if text:
                    self._speak_sync(text)
                self._tts_queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.debug(f"TTS worker error: {e}")

    # ── HABLAR ────────────────────────────────────────────────────────────────

    def speak(self, text: str, priority: bool = False):
        """Sintetizar texto (limpieza automática para TTS natural)."""
        if not self.tts_enabled or not text:
            return
        if not self.cleaner.should_speak(text):
            return
        clean = self.cleaner.clean_for_tts(text)
        if not clean or len(clean) < 3:
            return
        if priority:
            while not self._tts_queue.empty():
                try:
                    self._tts_queue.get_nowait()
                except queue.Empty:
                    break
        self._tts_queue.put(clean)

    def _speak_sync(self, text: str):
        self._speaking = True
        try:
            if self._use_pyttsx3:
                self._speak_pyttsx3(text)
            else:
                self._speak_edge(text)
        except Exception as e:
            logger.debug(f"Error TTS: {e}")
        finally:
            self._speaking = False

    def _speak_edge(self, text: str):
        try:
            import edge_tts

            async def generate():
                communicate = edge_tts.Communicate(text, self.voice_name)
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    audio_file = f.name
                await communicate.save(audio_file)
                return audio_file

            loop = asyncio.new_event_loop()
            audio_file = loop.run_until_complete(generate())
            loop.close()

            played = False
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
                played = True
            except Exception:
                pass

            if not played:
                try:
                    import playsound
                    playsound.playsound(audio_file)
                    played = True
                except Exception:
                    pass

            if not played:
                import subprocess
                subprocess.Popen(['start', '', audio_file], shell=True)
                time.sleep(2)

            try:
                os.unlink(audio_file)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Edge TTS error: {e}")

    def _speak_pyttsx3(self, text: str):
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            logger.debug(f"pyttsx3 error: {e}")

    # ── ESCUCHAR ──────────────────────────────────────────────────────────────

    def listen(self, timeout: float = 5.0, phrase_limit: float = 15.0) -> Optional[str]:
        """Escuchar una frase del micrófono."""
        if not self.stt_enabled:
            return None
        try:
            import speech_recognition as sr
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            try:
                return self._recognizer.recognize_google(audio, language='es-ES')
            except sr.UnknownValueError:
                return None
            except Exception:
                return None
        except Exception as e:
            logger.debug(f"STT error: {e}")
            return None

    def is_speaking(self) -> bool:
        return self._speaking or not self._tts_queue.empty()

    def toggle_tts(self) -> bool:
        self.tts_enabled = not self.tts_enabled
        return self.tts_enabled

    def set_voice(self, voice_name: str):
        self.voice_name = voice_name

    def toggle_mute(self) -> bool:
        """EXTRA PRO: Desactivar Escucha (Modo Silencio)."""
        self.is_muted = not self.is_muted
        logger.info(f"Micrófono {'Silenciado' if self.is_muted else 'Activo'}.")
        return self.is_muted


# ── WAKE WORD DAEMON ─────────────────────────────────────────────────────────

class WakeWordDaemon(threading.Thread):
    """
    Daemon de escucha continua.
    Detecta la palabra de activación "Jarvis" y luego escucha el comando.
    Se pausa automáticamente mientras MARK está hablando.
    """

    WAKE_WORDS = ["jarvis", "járvis", "jar vis", "oye jarvis", "hey jarvis"]

    def __init__(self, voice: VoiceSystem, on_command: Callable[[str], None], is_active_window: Callable[[], bool] = None):
        super().__init__(daemon=True, name="WakeWord-Daemon")
        self.voice      = voice
        self.on_command = on_command
        self.is_active_window = is_active_window or (lambda: False)
        self.running    = False
        self.enabled    = True    # Permite activar/desactivar manualmente

    def run(self):
        self.running = True
        logger.info("🎙 Wake word daemon activo — escuchando 'Jarvis'")
        while self.running:
            try:
                if not self.enabled or not self.voice.stt_enabled:
                    time.sleep(0.5)
                    continue

                # Pausar si el sistema está hablando
                if self.voice.is_speaking():
                    time.sleep(0.1)
                    continue

                # Escuchar (timeout corto para no bloquear)
                text = self.voice.listen(timeout=2.5, phrase_limit=5.0)
                if not text:
                    continue

                t = text.lower().strip()
                logger.debug(f"WakeWord oído: '{t}'")

                # Continuous Conversation Mode (Bypass de Wake Word)
                if self.is_active_window():
                    # Ignoramos si es vacío o muy corto (ruido de fondo)
                    if len(t) > 2:
                        logger.info(f"🎤 [Active] Detectado comando directo: '{t}'")
                        self.on_command(t)
                    continue

                # Detectar wake word (fuera de ventana)
                if any(ww in t for ww in self.WAKE_WORDS):
                    logger.info(f"✓ Wake word detectado: '{t}'")
                    # Extraer comando inline si el usuario dijo todo junto
                    # "Jarvis, abre el navegador" → comando = "abre el navegador"
                    command = t
                    for ww in self.WAKE_WORDS:
                        command = command.replace(ww, '').strip().lstrip(',').strip()

                    if len(command) > 2:
                        # Comando inline
                        self.on_command(command)
                    else:
                        # Escuchar comando por separado
                        if self.voice.tts_enabled:
                            self.voice.speak("Dígame, Señor.", priority=True)
                        time.sleep(0.8)  # Esperar que termine el TTS
                        cmd = self.voice.listen(timeout=6.0, phrase_limit=15.0)
                        if cmd and len(cmd.strip()) > 1:
                            self.on_command(cmd.strip())
                        else:
                            logger.debug("Sin comando tras wake word")

            except Exception as e:
                logger.debug(f"WakeWord daemon error: {e}")
                time.sleep(1)

    def stop(self):
        self.running = False
        logger.info("Wake word daemon detenido.")

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        state = "activado" if enabled else "desactivado"
        logger.info(f"Wake word daemon {state}.")
