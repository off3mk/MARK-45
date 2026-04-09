"""MARK-45 — Skill: Navegador Web"""
import logging
import urllib.parse
import webbrowser

logger = logging.getLogger("MARK45.Skills.Browser")


def google_search(query: str) -> str:
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Buscando '{query}' en Google."


def open_youtube(query: str = "") -> str:
    url = (f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
           if query else "https://www.youtube.com")
    webbrowser.open(url)
    return f"YouTube abierto{f': {query}' if query else ''}."


def open_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Abriendo {url}"
