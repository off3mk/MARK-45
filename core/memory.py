"""
MARK-45 — Memoria Persistente
==============================
Historial de conversación JSON y notas del sistema.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MARK45.Memory")

MEMORY_DIR  = os.path.join(os.path.dirname(__file__), "..", "memory")
HISTORY_FILE = os.path.join(MEMORY_DIR, "conversation_history.json")
NOTES_FILE   = os.path.join(MEMORY_DIR, "notas.json")


class Memory:
    """Memoria persistente de MARK-45."""

    def __init__(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self._history: List[Dict] = self._load(HISTORY_FILE, [])
        self._notes: Dict[str, Any] = self._load(NOTES_FILE, {})
        logger.info(f"✓ Memoria cargada — {len(self._history)} entradas en historial")

    # ── HISTORIAL ─────────────────────────────────────────────────────────────

    def add_turn(self, role: str, text: str):
        """Agregar turno de conversación (user/mark)."""
        self._history.append({
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })
        # Mantener solo los últimos 200 turnos
        if len(self._history) > 200:
            self._history = self._history[-200:]
        self._save(HISTORY_FILE, self._history)

    def get_recent(self, n: int = 10) -> List[Dict]:
        """Obtener los últimos n turnos."""
        return self._history[-n:]

    def get_context_str(self, n: int = 6) -> str:
        """Cadena de contexto reciente para el LLM."""
        recent = self.get_recent(n)
        return " | ".join(
            f"{'Tú' if h['role'] == 'user' else 'MARK'}: {h['text'][:60]}"
            for h in recent
        )

    def clear_history(self):
        """Limpiar historial."""
        self._history.clear()
        self._save(HISTORY_FILE, self._history)
        logger.info("Historial limpiado.")

    # ── NOTAS ─────────────────────────────────────────────────────────────────

    def set_note(self, key: str, value: Any):
        """Guardar nota del sistema."""
        self._notes[key] = value
        self._save(NOTES_FILE, self._notes)

    def get_note(self, key: str, default: Any = None) -> Any:
        """Recuperar nota."""
        return self._notes.get(key, default)

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    @staticmethod
    def _load(path: str, default) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def _save(path: str, data: Any):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error guardando {path}: {e}")

    def get_stats(self) -> Dict:
        return {
            "turnos_historial": len(self._history),
            "notas": len(self._notes),
        }
