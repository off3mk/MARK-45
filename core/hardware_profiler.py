"""
MARK-45 — Hardware Auto-Profiler
==================================
Identifica automáticamente el hardware subyacente y asigna un perfil:
- MODE_HEAVY: >= 16GB RAM + CPU potente + Posible GPU
- MODE_LIGHT: <= 8GB RAM o CPU básica (ej. Intel N100)

Se utiliza para ajustar tasas de concurrencia, animaciones del HUD
y complejidad del contexto LLM.
"""

import logging
import platform

logger = logging.getLogger("MARK45.HardwareProfiler")

def get_profile() -> str:
    """Devuelve MODE_HEAVY o MODE_LIGHT."""
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        cpu_count = psutil.cpu_count(logical=True) or 2
        
        has_gpu = False
        try:
            import pynvml
            pynvml.nvmlInit()
            has_gpu = pynvml.nvmlDeviceGetCount() > 0
            pynvml.nvmlShutdown()
        except:
            pass
            
        logger.info(f"Hardware detectado: {ram_gb:.1f}GB RAM, {cpu_count} hilos, GPU Dedicada: {has_gpu}")
        
        # Criterios dinámicos
        if ram_gb > 12 and cpu_count >= 8:
            return "MODE_HEAVY"
        else:
            return "MODE_LIGHT"
            
    except ImportError:
        logger.warning("psutil no disponible. Asumiendo MODE_LIGHT.")
        return "MODE_LIGHT"

def get_system_prompt_addition(mode: str) -> str:
    """Modificador del prompt principal según el hardware."""
    if mode == "MODE_LIGHT":
        return "\nIMPORTANTE: Estamos en hardware (Intel N100). Sé extremadamente breve y directo para ahorrar recursos."
    return ""
