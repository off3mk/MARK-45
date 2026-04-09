"""
MARK-45 — Monitor del Sistema
==============================
CPU, RAM, VRAM, disco, procesos activos.
Detección automática de Modo Gaming.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import logging
import os
import platform
import time
from typing import Dict, List, Optional

logger = logging.getLogger("MARK45.Monitor")

# Juegos conocidos (detectar modo gaming)
GAME_PROCESSES = {
    "csgo.exe", "cs2.exe", "valorant.exe", "fortnite.exe", "apex_legends.exe",
    "leagueclient.exe", "league of legends.exe", "dota2.exe", "overwatch.exe",
    "minecraft.exe", "cyberpunk2077.exe", "witcher3.exe", "eldenring.exe",
    "gta5.exe", "gtav.exe", "rdr2.exe", "destiny2.exe", "warzone.exe",
    "r5apex.exe", "bf2042.exe", "cod.exe", "modernwarfare.exe",
}


class SystemMonitor:
    """Monitor de recursos del sistema."""

    def __init__(self):
        self._psutil_ok  = False
        self._nvml_ok    = False
        self._last_stats: Dict = {}
        self._init_psutil()
        self._init_nvml()

    def _init_psutil(self):
        try:
            import psutil
            self._psutil_ok = True
            logger.info("✓ psutil disponible")
        except ImportError:
            logger.warning("psutil no disponible (pip install psutil)")

    def _init_nvml(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_ok = True
            logger.info("✓ pynvml disponible (VRAM monitoring)")
        except Exception:
            logger.debug("pynvml no disponible — sin monitoreo de VRAM")

    def get_stats(self) -> Dict:
        """Obtener estadísticas completas del sistema."""
        stats: Dict = {
            "cpu": 0.0,
            "ram": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "disk": 0.0,
            "vram_used_mb": 0,
            "vram_total_mb": 0,
            "gaming_mode": False,
            "game_name": "",
            "active_window": "",
            "top_processes": [],
        }

        if not self._psutil_ok:
            return stats

        try:
            import psutil

            # CPU (intervalo 1 s para lectura real)
            stats["cpu"] = psutil.cpu_percent(interval=0.1)

            # RAM
            ram = psutil.virtual_memory()
            stats["ram"]          = ram.percent
            stats["ram_used_gb"]  = ram.used / 1e9
            stats["ram_total_gb"] = ram.total / 1e9

            # Disco (C:\ en Windows, / en Unix)
            try:
                disk_path = "C:\\" if platform.system() == "Windows" else "/"
                disk = psutil.disk_usage(disk_path)
                stats["disk"] = disk.percent
            except Exception:
                pass

            # Procesos — detectar gaming
            try:
                procs = []
                for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                    try:
                        pname = p.info["name"].lower()
                        procs.append(p.info)
                        if pname in GAME_PROCESSES:
                            stats["gaming_mode"] = True
                            stats["game_name"] = p.info["name"]
                    except Exception:
                        pass
                # Top 8 por CPU
                procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
                stats["top_processes"] = [
                    {"name": p.get("name", "?"), "cpu": p.get("cpu_percent", 0), "mem": p.get("memory_percent", 0)}
                    for p in procs[:8]
                ]
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"get_stats error: {e}")

        # VRAM
        if self._nvml_ok:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem    = pynvml.nvmlDeviceGetMemoryInfo(handle)
                stats["vram_used_mb"]  = mem.used // (1024 * 1024)
                stats["vram_total_mb"] = mem.total // (1024 * 1024)
            except Exception:
                pass

        self._last_stats = stats
        return stats

    def get_top_processes(self, n: int = 8) -> List[Dict]:
        """Obtener top N procesos por CPU."""
        return self._last_stats.get("top_processes", [])[:n]

    def get_summary_text(self) -> str:
        """Resumen en texto para el LLM."""
        s = self._last_stats
        if not s:
            s = self.get_stats()
        lines = [
            f"CPU: {s['cpu']:.1f}%",
            f"RAM: {s['ram']:.1f}% ({s['ram_used_gb']:.1f}/{s['ram_total_gb']:.0f} GB)",
            f"Disco: {s['disk']:.1f}%",
        ]
        if s.get("vram_total_mb"):
            lines.append(f"VRAM: {s['vram_used_mb']}/{s['vram_total_mb']} MB")
        if s.get("gaming_mode"):
            lines.append(f"🎮 Modo Gaming: {s['game_name']}")
        return " | ".join(lines)
