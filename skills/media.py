"""MARK-45 — Skill: Media / Multimedia"""
import logging
import subprocess
import platform

logger = logging.getLogger("MARK45.Skills.Media")


def toggle_play_pause():
    try:
        import pyautogui
        pyautogui.press('playpause')
        return True
    except Exception:
        pass
    return False


def volume_up(steps: int = 5):
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press('volumeup')
        return True
    except Exception:
        return False


def volume_down(steps: int = 5):
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press('volumedown')
        return True
    except Exception:
        return False


def mute():
    try:
        import pyautogui
        pyautogui.press('volumemute')
        return True
    except Exception:
        return False
