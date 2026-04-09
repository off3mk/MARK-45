"""MARK-45 — Skill: Sistema"""
import logging
import os
import platform
import subprocess

logger = logging.getLogger("MARK45.Skills.System")


def minimize_all():
    """Minimizar todas las ventanas."""
    try:
        import pyautogui
        pyautogui.hotkey('win', 'd')
        return True
    except Exception:
        pass
    if platform.system() == 'Windows':
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x44, 0, 0, 0)
            user32.keybd_event(0x44, 0, 2, 0)
            user32.keybd_event(0x5B, 0, 2, 0)
            return True
        except Exception:
            pass
    return False


def get_uptime_minutes() -> float:
    try:
        import psutil
        return (psutil.time.time() - psutil.boot_time()) / 60
    except Exception:
        return 0.0

async def handle_intent(intent, orch) -> str:
    """
    NUEVA ARQUITECTURA MODULAR DE SKILLS.
    El Dispatcher envía el Intent aquí dinámicamente si la categoría coincide con el nombre del módulo.
    Si la función devuelve un string vacío, el Dispatcher usará los métodos legacy internos.
    """
    sub = intent.subcategory

    if sub == 'minimize_all':
        if minimize_all():
            return "Escritorio despejado, Señor."
        return "No pude minimizar las ventanas en este entorno."
        
    if sub == 'uptime':
        mins = get_uptime_minutes()
        return f"El sistema lleva activo {mins:.1f} minutos."
        
    # Devolver cadena vacía permite que el Dispatcher haga fallback a _system_open_app, etc.
    return ""
