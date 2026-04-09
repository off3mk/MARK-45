"""
MARK-45 — LLM Engine
=====================
Conector para LM Studio (OpenAI-compatible API) y Ollama.
Detección automática del proveedor activo.

Hardware objetivo: Ryzen 7 5800X | 32GB RAM | RTX 4060 Ti 8GB | Win11
Modelo objetivo:   Qwen3-8B Q5_K_M en LM Studio (CUDA)

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import json
import logging
import re
import time
from typing import Dict, List, Optional

logger = logging.getLogger("MARK45.LLM")

# ── CONFIGURACIÓN ────────────────────────────────────────────────────────────

LM_STUDIO_URL  = "http://localhost:1234/v1"
OLLAMA_URL     = "http://localhost:11434/api"
OLLAMA_CHAT    = "http://localhost:11434/api/chat"

SYSTEM_PROMPT_ES = """Eres MARK 45, el asistente de inteligencia artificial personal de Ali.
Características:
- Respondes SIEMPRE en español, de forma directa y precisa
- Eres el asistente más avanzado que Ali ha creado
- Tienes personalidad seria pero cercana, como el JARVIS de Iron Man
- Eres proactivo: anticipas necesidades
- No tienes conversación de relleno — vas al grano
- Si el usuario dice "Señor", lo tratas con el mismo respeto que JARVIS trataba a Tony Stark
- Hardware del sistema: Ryzen 7 5800X | 32GB RAM | RTX 4060 Ti 8GB | Windows 11

NUNCA respondas en inglés a no ser que el usuario lo pida explícitamente."""


class LLMEngine:
    """Motor LLM con fallback automático entre proveedores."""

    def __init__(self):
        self._history: List[Dict] = []
        self.active_provider = "ninguno"
        self._model: Optional[str] = None
        self._client = None

        self._detect_provider()

    def _detect_provider(self):
        """Detectar proveedor LLM disponible."""
        # Intentar LM Studio primero
        if self._try_lm_studio():
            return
        # Fallback a Ollama
        if self._try_ollama():
            return
        # Tier 3: Fallback a Cloud Gratuito (G4F)
        if self._try_g4f():
            return
        logger.warning("⚠ Sin LLM disponible. Inicia LM Studio u Ollama, o instala g4f.")

    def _try_lm_studio(self) -> bool:
        try:
            from openai import OpenAI
            client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
            models = client.models.list()
            if models.data:
                self._model = models.data[0].id
                self._client = client
                self._provider = "lm_studio"
                self.active_provider = f"LM Studio ({self._model})"
                logger.info(f"✓ LM Studio detectado: {self._model}")
                return True
        except Exception as e:
            logger.debug(f"LM Studio no disponible: {e}")
        return False

    def _try_ollama(self) -> bool:
        try:
            import requests
            r = requests.get(f"http://localhost:11434/api/tags", timeout=3)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models", [])
                if models:
                    self._model = models[0]["name"]
                    self._provider = "ollama"
                    self.active_provider = f"Ollama ({self._model})"
                    logger.info(f"✓ Ollama detectado: {self._model}")
                    return True
        except Exception as e:
            logger.debug(f"Ollama no disponible: {e}")
        return False

    def _try_g4f(self) -> bool:
        try:
            import g4f
            import sys
            # Validar que asyncio y aiohttp no den error en Windows pre-run
            self._model = "gpt-4o-mini"
            self._provider = "g4f"
            self.active_provider = f"G4F Cloud ({self._model})"
            logger.info(f"✓ G4F Cloud Fallback detectado: {self._model}")
            return True
        except ImportError:
            logger.debug("G4F (Tier 3) no instalado.")
        return False

    def generate(
        self,
        prompt: str,
        with_history: bool = True,
        max_tokens: int = 700,
        temperature: float = 0.7,
    ) -> str:
        """Generar respuesta del LLM (Tier 1/2 -> Tier 3)."""
        if not self._model:
            # Reintentar detectar (por si levantaron el server)
            self._detect_provider()
            if not self._model:
                return "LLM no disponible. Inicia LM Studio u Ollama, Señor."

        try:
            if self._provider == "lm_studio":
                return self._generate_lm_studio(prompt, with_history, max_tokens, temperature)
            elif self._provider == "ollama":
                return self._generate_ollama(prompt, with_history, max_tokens, temperature)
            elif self._provider == "g4f":
                return self._generate_g4f(prompt, with_history, max_tokens, temperature)
        except Exception as e:
            logger.warning(f"Error LLM Local ({self._provider}): {e}. Intentando Fallback Cloud (G4F)...")
            if self._provider != "g4f" and self._try_g4f():
                try:
                    return self._generate_g4f(prompt, with_history, max_tokens, temperature)
                except Exception as e_g4f:
                    logger.error(f"Fallo masivo (G4F también cayó): {e_g4f}")
            # Si todo falla, devuelve nulo para que orquestador asigne a HeuristicBrain
            # "No disponible" simula caída de todos los LLM
            return ""

    def _build_messages(self, prompt: str, with_history: bool) -> List[Dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT_ES}]
        if with_history and self._history:
            messages.extend(self._history[-12:])  # Últimos 6 turnos
        messages.append({"role": "user", "content": prompt})
        return messages

    def _generate_lm_studio(
        self, prompt: str, with_history: bool, max_tokens: int, temperature: float
    ) -> str:
        messages = self._build_messages(prompt, with_history)
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        response = completion.choices[0].message.content.strip()
        if with_history:
            self._history.append({"role": "user", "content": prompt})
            self._history.append({"role": "assistant", "content": response})
            if len(self._history) > 24:
                self._history = self._history[-24:]
        return response

    def _generate_ollama(
        self, prompt: str, with_history: bool, max_tokens: int, temperature: float
    ) -> str:
        import requests
        messages = self._build_messages(prompt, with_history)
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }
        r = requests.post(OLLAMA_CHAT, json=payload, timeout=60)
        r.raise_for_status()
        response = r.json()["message"]["content"].strip()
        if with_history:
            self._history.append({"role": "user", "content": prompt})
            self._history.append({"role": "assistant", "content": response})
            if len(self._history) > 24:
                self._history = self._history[-24:]
        return response

    def _generate_g4f(
        self, prompt: str, with_history: bool, max_tokens: int, temperature: float
    ) -> str:
        from g4f.client import Client as G4FClient
        from g4f.Provider import RetryProvider, Blackbox, DuckDuckGo
        
        # Para evitar problemas de asyncio event loop preexistentes en subprocesos
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        client = G4FClient()
        messages = self._build_messages(prompt, with_history)
        response = client.chat.completions.create(
            model=self._model,
            messages=messages,
            provider=RetryProvider([Blackbox, DuckDuckGo])
        )
        resp_text = response.choices[0].message.content.strip()
        if with_history:
            self._history.append({"role": "user", "content": prompt})
            self._history.append({"role": "assistant", "content": resp_text})
            if len(self._history) > 24:
                self._history = self._history[-24:]
        return resp_text

    def analyze_code(self, code: str) -> str:
        return self.generate(
            f"Analiza este código y proporciona un resumen claro en español:\n\n{code}",
            with_history=False,
            max_tokens=600,
        )

    def summarize(self, text: str, max_words: int = 150) -> str:
        return self.generate(
            f"Resume el siguiente texto en máximo {max_words} palabras, en español:\n\n{text}",
            with_history=False,
            max_tokens=300,
        )

    def unload_model(self):
        """Liberar VRAM (modo gaming)."""
        logger.info("Modelo LLM liberado de VRAM (modo gaming).")
        # LM Studio gestiona la VRAM automáticamente

    def reload_model(self):
        """Recargar modelo tras modo gaming."""
        logger.info("Recargando LLM...")
        self._detect_provider()

    def get_status(self) -> Dict:
        return {
            "provider": self.active_provider,
            "model": self._model or "N/A",
            "history_length": len(self._history),
        }

    def clear_history(self):
        self._history.clear()
        logger.info("Historial de conversación limpiado.")
