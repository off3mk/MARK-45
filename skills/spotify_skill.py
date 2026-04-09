"""
MARK-45 — Skill: Spotify
==========================
Control de Spotify vía spotipy.
Configura credenciales en memory/spotify_config.json:
{
  "client_id": "TU_CLIENT_ID",
  "client_secret": "TU_CLIENT_SECRET",
  "redirect_uri": "http://localhost:8888/callback"
}
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("MARK45.Skills.Spotify")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "spotify_config.json")


class SpotifySkill:
    def __init__(self):
        self._sp = None
        self._try_init()

    def _try_init(self):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            if not os.path.exists(CONFIG_PATH):
                logger.info("Spotify: sin configuración (memory/spotify_config.json)")
                return
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            self._sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=cfg["client_id"],
                client_secret=cfg["client_secret"],
                redirect_uri=cfg.get("redirect_uri", "http://localhost:8888/callback"),
                scope="user-modify-playback-state user-read-playback-state",
            ))
            logger.info("✓ Spotify conectado")
        except ImportError:
            logger.debug("spotipy no instalado")
        except Exception as e:
            logger.debug(f"Spotify init: {e}")

    def execute(self, action: str, params: dict = None, raw: str = "") -> str:
        if not self._sp:
            return "Spotify no configurado. Crea memory/spotify_config.json con tus credenciales."
        params = params or {}
        try:
            if action == 'play':
                query = params.get('query', '')
                if query:
                    results = self._sp.search(q=query, type='track', limit=1)
                    tracks = results.get('tracks', {}).get('items', [])
                    if tracks:
                        self._sp.start_playback(uris=[tracks[0]['uri']])
                        return f"Reproduciendo: {tracks[0]['name']} — {tracks[0]['artists'][0]['name']}"
                else:
                    self._sp.start_playback()
                    return "Reproducción iniciada."
            elif action == 'pause':
                self._sp.pause_playback()
                return "Música pausada."
            elif action == 'next':
                self._sp.next_track()
                return "Siguiente canción."
            elif action == 'previous':
                self._sp.previous_track()
                return "Canción anterior."
            elif action == 'current':
                track = self._sp.current_playback()
                if track and track.get('item'):
                    name = track['item']['name']
                    artist = track['item']['artists'][0]['name']
                    return f"Sonando: {name} — {artist}"
                return "Sin reproducción activa."
            elif action == 'shuffle':
                state = self._sp.current_playback()
                current = state.get('shuffle_state', False) if state else False
                self._sp.shuffle(not current)
                return f"Shuffle {'activado' if not current else 'desactivado'}."
            elif action == 'volume':
                level = int(params.get('level', 50))
                self._sp.volume(level)
                return f"Volumen Spotify al {level}%."
        except Exception as e:
            return f"Error Spotify: {e}"
        return "Acción no reconocida."


_instance: Optional[SpotifySkill] = None


def get_spotify() -> SpotifySkill:
    global _instance
    if _instance is None:
        _instance = SpotifySkill()
    return _instance
