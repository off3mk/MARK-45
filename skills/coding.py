"""MARK-45 — Skill: Codificación / Desarrollo"""
import logging
import os
import subprocess

logger = logging.getLogger("MARK45.Skills.Coding")


def run_script(path: str, timeout: int = 30) -> tuple:
    """Ejecutar script Python. Devuelve (ok, output)."""
    try:
        result = subprocess.run(
            ["python", path],
            capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timeout al ejecutar el script."
    except Exception as e:
        return False, str(e)


def shell_command(cmd: str, timeout: int = 15) -> tuple:
    """Ejecutar comando en shell. Devuelve (ok, output)."""
    BLOCKED = ['rm -rf', 'del /f /s', 'format c:', 'rmdir /s']
    if any(b in cmd.lower() for b in BLOCKED):
        return False, f"Comando bloqueado por seguridad: '{cmd}'"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout or result.stderr or "").strip()
        return True, output[:1500]
    except subprocess.TimeoutExpired:
        return False, "Timeout (15s)."
    except Exception as e:
        return False, str(e)
