"""
MARK-45 — Emergency Heuristic Brain
======================================
Motor de intención OFFLINE de alta capacidad.
Se activa cuando el LLM (Ollama / LM Studio) está caído.

Capacidades:
  1. Regex Pattern Engine   — extrae parámetros con grupos de captura
  2. Synonym Dictionary     — 200+ frases en español con alias coloquiales
  3. State Machine          — contexto conversacional básico
  4. Multi-Intent Splitter  — "pon música y sube el volumen" → 2 acciones
  5. rapidfuzz fallback     — para frases no cubiertas por patrones

Todo el texto de respuesta y logs en español.
Creado por Ali (Sidi3Ali) — MARK 45
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("MARK45.HeuristicBrain")


# ══════════════════════════════════════════════════════════════════════════════
# 1. STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConversationState:
    """Estado conversacional liviano."""
    last_action:   str = ""      # e.g. "music.play"
    last_subject:  str = ""      # e.g. "AC/DC"
    last_file:     str = ""      # e.g. "C:/users/foo.txt"
    mode:          str = "nominal"  # nominal | media | gaming | coding | web

    def update(self, action: str, subject: str = "", params: Optional[Dict] = None):
        self.last_action  = action
        if subject:
            self.last_subject = subject
        
        # Bug 4: Amnesia de archivos — guardar archivo mencionado
        if params and ('path' in params or 'file' in params):
            f = params.get('path', '') or params.get('file', '')
            if f:
                self.last_file = f

        # Actualizar modo
        cat = action.split(".")[0] if "." in action else ""
        if cat == "music":
            self.mode = "media"
        elif cat == "code":
            self.mode = "coding"
        elif cat == "web":
            self.mode = "web"
        elif action == "system.gaming_mode":
            self.mode = "gaming"
        elif cat in ("mark", "system"):
            pass   # mantener modo actual
        else:
            self.mode = "nominal"


# ══════════════════════════════════════════════════════════════════════════════
# 2. REGEX PATTERN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

# Cada entrada: (patrón_compilado, acción, función_de_params)
_P = re.compile   # alias

REGEX_PATTERNS: List[Tuple] = [
    # ── MÚSICA / SPOTIFY ────────────────────────────────────────────────────
    (_P(r'(?:pon(?:me)?|reproduce|escucha(?:r)?|dale\s+a|quiero\s+oir|quiero\s+escuchar)\s+(?:música\s+de|a|al?)\s+(?P<query>.+)', re.I),
     'music.play', lambda m: {'query': m.group('query').strip()}),

    (_P(r'(?:pon(?:me)?|reproduce|escucha(?:r)?)\s+(?P<query>[\w\s\-\'/&]+)\s+(?:en\s+spotify|de\s+spotify)', re.I),
     'music.play', lambda m: {'query': m.group('query').strip()}),

    (_P(r'(?:pon(?:me)?|reproduce|escucha(?:r)?|dale)\s+(?:algo\s+de\s+)?(?P<query>[\w\s\-\'/&]{3,})\s*$', re.I),
     'music.play', lambda m: {'query': m.group('query').strip()}),

    (_P(r'\b(?:siguiente\s+canci[oó]n|siguiente\s+tema|skip|salta(?:r)?(?:\s+canci[oó]n)?|next)\b', re.I),
     'music.next', lambda m: {}),

    (_P(r'\b(?:canci[oó]n\s+anterior|anterior|atr[aá]s|prev(?:ious)?)\b', re.I),
     'music.previous', lambda m: {}),

    (_P(r'\b(?:pausa(?:r)?|para(?:r)?\s+(?:la\s+)?m[uú]sica|stop\s+(?:la\s+)?m[uú]sica)\b', re.I),
     'music.pause', lambda m: {}),

    (_P(r'(?:qu[eé]\s+(?:canci[oó]n|tema)\s+(?:es\s+esta|suena|est[aá]\s+sonando)|qu[eé]\s+est[aá]\s+sonando|qu[eé]\s+suena)', re.I),
     'music.info', lambda m: {}),

    # ── WEB / BÚSQUEDAS ─────────────────────────────────────────────────────
    (_P(r'(?:busca(?:r)?|googlea(?:r)?|busca\s+en\s+google|consulta(?:r)?|encuentra(?:r)?|investiga(?:r)?)\s+(?:sobre\s+|acerca\s+de\s+|informaci[oó]n\s+(?:sobre\s+|de\s+))?(?P<query>.+)', re.I),
     'web.search', lambda m: {'query': m.group('query').strip()}),

    (_P(r'(?:busca(?:r)?|pon(?:me)?|abre(?:r)?|mira(?:r)?|ver?)\s+(?:en\s+)?(?:youtube|yt)\s+(?P<query>.+)', re.I),
     'web.youtube', lambda m: {'query': m.group('query').strip()}),

    (_P(r'(?:pon(?:me)?|abre?|pone)\s+(?:el\s+)?youtube(?:\s+(?P<query>.+))?', re.I),
     'web.youtube', lambda m: {'query': (m.group('query') or '').strip()}),

    (_P(r'(?:abre?|navega\s+a|entra\s+(?:en|a))\s+(?P<url>(?:https?://)?[\w\-]+\.[\w\-./]+)', re.I),
     'web.open_url', lambda m: {'url': m.group('url').strip()}),

    # ── SISTEMA — ESTADO ────────────────────────────────────────────────────
    (_P(r'(?:cu[aá]nta?\s+(?:ram|memoria|cpu|vram|disco)|c[oó]mo\s+(?:est[aá]|va)\s+(?:el\s+pc|el\s+sistema|la\s+ram|el\s+cpu)|estado\s+del\s+sistema|m[eé]tricas?)', re.I),
     'system.status', lambda m: {}),

    # ── SISTEMA — VOLUMEN ────────────────────────────────────────────────────
    (_P(r'(?:s[uú]be(?:le)?|aumenta(?:r)?|m[aá]s)\s+(?:el\s+)?volumen(?:\s+(?:a\s+)?(?P<lvl>\d+))?', re.I),
     'system.volume', lambda m: {'action': 'up', 'level': m.group('lvl') or ''}),

    (_P(r'(?:b[aá]ja(?:le)?|disminuye|menos)\s+(?:el\s+)?volumen(?:\s+(?:a\s+)?(?P<lvl>\d+))?', re.I),
     'system.volume', lambda m: {'action': 'down', 'level': m.group('lvl') or ''}),

    (_P(r'(?:silencia(?:r)?|mutea(?:r)?|mute|s[iaá]lenciate|calla(?:te)?|sin\s+sonido)', re.I),
     'system.volume', lambda m: {'action': 'mute'}),

    (_P(r'(?:volumen\s+(?:al?\s+)?(?P<lvl>\d{1,3}(?:\s*(?:por\s+ciento|%))?))', re.I),
     'system.volume', lambda m: {'action': 'set', 'level': re.sub(r'[^\d]', '', m.group('lvl'))}),

    # ── SISTEMA — APLICACIONES ───────────────────────────────────────────────
    (_P(r'(?:abre?|lanza(?:r)?|inicia(?:r)?|ejecuta(?:r)?|arranca(?:r)?|pon|abre\s+el|abre\s+la)\s+(?:el\s+|la\s+|los\s+|las\s+)?(?P<name>[\w\s\-\.]{2,30})', re.I),
     'system.open_app', lambda m: {'name': m.group('name').strip()}),

    (_P(r'(?:cierra?|mata(?:r)?|k[i1]lla(?:r)?|termina(?:r)?|finaliza(?:r)?)\s+(?:el\s+|la\s+)?(?P<name>[\w\s\-\.]{2,30})', re.I),
     'system.close_app', lambda m: {'name': m.group('name').strip()}),

    # ── SISTEMA — VENTANAS ───────────────────────────────────────────────────
    (_P(r'(?:minimiza(?:r)?\s+(?:todo|las\s+ventanas|todo\s+lo)?|despeja(?:r)?\s+(?:la\s+)?pantalla|vete\s+al\s+escritorio|escritorio|ense[nñ]a(?:r)?\s+el\s+escritorio|oculta\s+(?:todo|las\s+ventanas)|limpia(?:r)?\s+(?:la\s+)?pantalla|purga\s+(?:las\s+)?ventanas|necesito\s+(?:que\s+)?limpies\s+(?:la\s+)?pantalla)', re.I),
     'system.minimize_all', lambda m: {}),

    # ── SISTEMA — APAGADO ────────────────────────────────────────────────────
    (_P(r'(?:apaga(?:r)?\s+el\s+pc|apaga(?:r)?\s+(?:el\s+)?ordenador|shut\s*down|reinicia(?:r)?(?:\s+el\s+pc)?)', re.I),
     'system.shutdown', lambda m: {}),

    # ── GAMING MODE ─────────────────────────────────────────────────────────
    (_P(r'(?:activa(?:r)?|modo)\s+gaming|gaming\s+mode|modo\s+juego|voy\s+a\s+jugar', re.I),
     'system.gaming_mode', lambda m: {}),

    # ── PANTALLA ─────────────────────────────────────────────────────────────
    (_P(r'(?:captura(?:r)?\s+(?:de\s+)?pantalla|screenshot|captura|foto\s+de\s+pantalla)', re.I),
     'screen.screenshot', lambda m: {}),

    (_P(r'(?:analiza(?:r)?\s+(?:la\s+)?pantalla|qu[eé]\s+hay\s+en\s+pantalla|describe\s+(?:la\s+)?pantalla|lee\s+(?:la\s+)?pantalla)', re.I),
     'screen.analyze', lambda m: {}),

    # ── CÓDIGO ───────────────────────────────────────────────────────────────
    (_P(r'(?:genera(?:r)?|crea(?:r)?|escribe(?:r)?|programa(?:r)?|hazme)\s+(?:un\s+|una\s+)?(?:script|programa|funci[oó]n|c[oó]digo)\s+(?:de\s+|para\s+|en\s+)?(?P<desc>.+)', re.I),
     'code.generate', lambda m: {'description': m.group('desc').strip()}),

    (_P(r'(?:ejecuta(?:r)?|corre(?:r)?|run)\s+(?:el\s+(?:script|programa|archivo)\s+)?(?P<path>[\w\-\./\\]+\.py)', re.I),
     'code.run', lambda m: {'path': m.group('path').strip()}),

    (_P(r'(?:ejecuta(?:r)?|corre(?:r)?|run)\s+(?:en\s+(?:la\s+)?terminal|cmd|consola)\s+(?P<cmd>.+)', re.I),
     'code.terminal', lambda m: {'command': m.group('cmd').strip()}),

    # ── ARCHIVOS ─────────────────────────────────────────────────────────────
    (_P(r'(?:organiza(?:r)?|ordena(?:r)?|limpia(?:r)?)\s+(?:la\s+carpeta\s+de\s+|la\s+carpeta\s+)?(?P<folder>descargas?|documentos?|escritorio|downloads?|[\w\s]+)', re.I),
     'files.organize', lambda m: {'folder': m.group('folder').strip()}),

    (_P(r'(?:busca(?:r)?\s+(?:el\s+archivo|archivos?|fichero)\s+|encuentra(?:r)?\s+(?:el\s+archivo\s+)?)(?P<query>.+)', re.I),
     'files.search', lambda m: {'query': m.group('query').strip()}),

    (_P(r'(?:cu[aá]nto\s+(?:espacio|disco|almacenamiento)|espacio\s+(?:en\s+)?(?:disco|libre|disponible))', re.I),
     'files.disk_info', lambda m: {}),

    # ── IA / TEXTO ────────────────────────────────────────────────────────────
    (_P(r'(?:resume(?:r)?|resumen\s+de?|haz(?:me)?\s+un\s+resumen)\s+(?:de\s+|del?\s+)?(?P<text>.+)', re.I),
     'ai.summarize', lambda m: {'text': m.group('text').strip()}),

    (_P(r'(?:traduce(?:r)?|traduc(?:ción|e)\s+(?:al?\s+)?(?P<lang>[\w]+)\s+)?(?P<text>.{10,})', re.I),
     'ai.translate', lambda m: {'text': m.group('text').strip()}),

    (_P(r'(?:explica(?:r)?(?:\s+qu[eé]\s+es)?|qu[eé]\s+es|c[oó]mo\s+funciona)\s+(?P<topic>.+)', re.I),
     'ai.explain', lambda m: {'topic': m.group('topic').strip()}),

    # ── MARK — AUTOGESTIÓN ───────────────────────────────────────────────────
    (_P(r'(?:qui[eé]n\s+eres|cu[aá]l\s+es\s+tu\s+nombre|cu[aá]ndo\s+te\s+(?:hicieron|crearon)|tu\s+creador|qu[eé]\s+eres)', re.I),
     'mark.identity', lambda m: {}),

    (_P(r'(?:cu[aá]l\s+es\s+tu\s+(?:estado|status)|c[oó]mo\s+est[aá]s\s+t[uú]|estado\s+de\s+mark)', re.I),
     'mark.status', lambda m: {}),

    (_P(r'(?:limpia(?:r)?\s+(?:el\s+)?historial|borra(?:r)?\s+(?:el\s+)?historial|reset\s+conversaci[oó]n)', re.I),
     'mark.clear_history', lambda m: {}),

    (_P(r'\b(?:ap[aá]gate|ap[aá]gat[eé]|sal|cierra(?:te)?|bye|adi[oó]s|hasta\s+luego|hasta\s+pronto|chao|nos\s+vemos)\b', re.I),
     'mark.stop', lambda m: {}),
]


# ══════════════════════════════════════════════════════════════════════════════
# 3. SYNONYM DICTIONARY (200+ frases en español)
# ══════════════════════════════════════════════════════════════════════════════

SINONIMOS: Dict[str, str] = {
    # ── system.minimize_all ──────────────────────────────────────────────────
    "minimiza todo":                       "system.minimize_all",
    "minimiza las ventanas":               "system.minimize_all",
    "minimiza todas las ventanas":         "system.minimize_all",
    "vete al escritorio":                  "system.minimize_all",
    "muéstrame el escritorio":             "system.minimize_all",
    "muestra el escritorio":               "system.minimize_all",
    "escritorio":                          "system.minimize_all",
    "despeja la pantalla":                 "system.minimize_all",
    "despeja pantalla":                    "system.minimize_all",
    "limpia la pantalla":                  "system.minimize_all",
    "limpia pantalla":                     "system.minimize_all",
    "purga las ventanas":                  "system.minimize_all",
    "purga ventanas":                      "system.minimize_all",
    "oculta todo":                         "system.minimize_all",
    "oculta las ventanas":                 "system.minimize_all",
    "necesito ver el escritorio":          "system.minimize_all",
    "quita todo de la pantalla":           "system.minimize_all",
    "necesito que limpies la pantalla":    "system.minimize_all",
    "despejar el escritorio":              "system.minimize_all",
    "quitame todo":                        "system.minimize_all",

    # ── system.status ────────────────────────────────────────────────────────
    "estado del sistema":                  "system.status",
    "estatus del sistema":                 "system.status",
    "cómo está el pc":                     "system.status",
    "cómo va el ordenador":                "system.status",
    "cuánta ram tengo":                    "system.status",
    "cuánta ram me queda":                 "system.status",
    "cuánto cpu tengo":                    "system.status",
    "temperatura del sistema":             "system.status",
    "métricas del sistema":                "system.status",
    "diagnóstico del sistema":             "system.status",
    "informe del sistema":                 "system.status",
    "rendimiento del pc":                  "system.status",
    "cuánto disco me queda":               "system.status",
    "cuánto espacio tengo":                "system.status",
    "ver procesos activos":                "system.processes",
    "qué procesos corren":                 "system.processes",

    # ── system.volume ────────────────────────────────────────────────────────
    "sube el volumen":                     "system.volume",
    "súbele":                              "system.volume",
    "baja el volumen":                     "system.volume",
    "bájale":                              "system.volume",
    "silencia el audio":                   "system.volume",
    "silencia":                            "system.volume",
    "mutea":                               "system.volume",
    "sin sonido":                          "system.volume",
    "más volumen":                         "system.volume",
    "menos volumen":                       "system.volume",
    "activa el sonido":                    "system.volume",
    "quita el mute":                       "system.volume",

    # ── music.play ───────────────────────────────────────────────────────────
    "pon música":                          "music.play",
    "ponme música":                        "music.play",
    "reproduce música":                    "music.play",
    "quiero escuchar música":              "music.play",
    "abre spotify":                        "music.play",
    "pon el spotify":                      "music.play",
    "dale":                                "music.play",
    "dale al spotify":                     "music.play",
    "pon algo":                            "music.play",
    "pon una canción":                     "music.play",
    "reproduce spotify":                   "music.play",
    "quiero música":                       "music.play",
    "pon algo chido":                      "music.play",
    "pon algo bueno":                      "music.play",
    "música":                              "music.play",

    # ── music.pause ──────────────────────────────────────────────────────────
    "pausa la música":                     "music.pause",
    "para la música":                      "music.pause",
    "para eso":                            "music.pause",
    "para":                                "music.pause",
    "pausa":                               "music.pause",
    "para un momento":                     "music.pause",

    # ── music.next ───────────────────────────────────────────────────────────
    "siguiente canción":                   "music.next",
    "siguiente tema":                      "music.next",
    "salta la canción":                    "music.next",
    "pon otra":                            "music.next",
    "otra canción":                        "music.next",
    "cambia la canción":                   "music.next",
    "no me gusta esta":                    "music.next",

    # ── music.previous ───────────────────────────────────────────────────────
    "canción anterior":                    "music.previous",
    "la anterior":                         "music.previous",
    "vuelve atrás":                        "music.previous",
    "pon la anterior":                     "music.previous",

    # ── music.info ───────────────────────────────────────────────────────────
    "qué está sonando":                    "music.info",
    "qué canción es esta":                 "music.info",
    "cómo se llama esta canción":          "music.info",
    "quién canta esto":                    "music.info",
    "qué suena":                           "music.info",

    # ── web.search ───────────────────────────────────────────────────────────
    "busca en google":                     "web.search",
    "googlear":                            "web.search",
    "busca información":                   "web.search",
    "busca en internet":                   "web.search",
    "qué es":                              "web.search",

    # ── web.youtube ──────────────────────────────────────────────────────────
    "abre youtube":                        "web.youtube",
    "pon youtube":                         "web.youtube",
    "abre el youtube":                     "web.youtube",
    "mete youtube":                        "web.youtube",
    "quiero ver youtube":                  "web.youtube",

    # ── screen.screenshot ────────────────────────────────────────────────────
    "captura de pantalla":                 "screen.screenshot",
    "toma una captura":                    "screen.screenshot",
    "screenshot":                          "screen.screenshot",
    "foto de la pantalla":                 "screen.screenshot",
    "captura":                             "screen.screenshot",

    # ── screen.analyze ───────────────────────────────────────────────────────
    "analiza la pantalla":                 "screen.analyze",
    "qué hay en pantalla":                 "screen.analyze",
    "describe la pantalla":                "screen.analyze",
    "qué ves en pantalla":                 "screen.analyze",
    "lee la pantalla":                     "screen.analyze",

    # ── files.disk_info ──────────────────────────────────────────────────────
    "cuánto espacio libre tengo":          "files.disk_info",
    "espacio en disco":                    "files.disk_info",
    "disco lleno":                         "files.disk_info",
    "cuánto queda en el disco":            "files.disk_info",

    # ── code.generate ────────────────────────────────────────────────────────
    "genera un script":                    "code.generate",
    "crea un programa":                    "code.generate",
    "escríbeme código":                    "code.generate",
    "hazme un script":                     "code.generate",
    "programa esto":                       "code.generate",

    # ── code.terminal ────────────────────────────────────────────────────────
    "ejecuta en la terminal":              "code.terminal",
    "abre la terminal":                    "system.open_app",
    "abre cmd":                            "system.open_app",
    "abre powershell":                     "system.open_app",

    # ── mark.identity ────────────────────────────────────────────────────────
    "quién eres":                          "mark.identity",
    "cuál es tu nombre":                   "mark.identity",
    "preséntate":                          "mark.identity",
    "quién te hizo":                       "mark.identity",
    "cuál es tu versión":                  "mark.identity",

    # ── mark.stop ────────────────────────────────────────────────────────────
    "apágate":                             "mark.stop",
    "ciérrate":                            "mark.stop",
    "hasta luego":                         "mark.stop",
    "adiós":                               "mark.stop",
    "hasta pronto":                        "mark.stop",
    "chao":                                "mark.stop",
    "nos vemos":                           "mark.stop",
    "bye":                                 "mark.stop",
    "sal":                                 "mark.stop",

    # ── mark.clear_history ───────────────────────────────────────────────────
    "limpia el historial":                 "mark.clear_history",
    "borra la conversación":               "mark.clear_history",
    "reinicia la conversación":            "mark.clear_history",
    "olvídalo todo":                       "mark.clear_history",

    # ── system.gaming_mode ───────────────────────────────────────────────────
    "modo gaming":                         "system.gaming_mode",
    "activa gaming":                       "system.gaming_mode",
    "voy a jugar":                         "system.gaming_mode",
    "modo juego":                          "system.gaming_mode",

    # ── ai.explain ───────────────────────────────────────────────────────────
    "explícame":                           "ai.explain",
    "explica esto":                        "ai.explain",
    "qué significa":                       "ai.explain",
    "cómo funciona":                       "ai.explain",

    # ── ai.summarize ─────────────────────────────────────────────────────────
    "resume esto":                         "ai.summarize",
    "haz un resumen":                      "ai.summarize",
    "resúmelo":                            "ai.summarize",

    # ── ai.translate ─────────────────────────────────────────────────────────
    "traduce esto":                        "ai.translate",
    "tradúcelo":                           "ai.translate",
    "cómo se dice en inglés":             "ai.translate",
}

# ── REGLAS DE CONTEXTO ────────────────────────────────────────────────────────
# (mode, keywords) → action con parámetros
CONTEXT_RULES: List[Tuple[str, List[str], str, Dict]] = [
    # modo media: "súbele", "más" → volume up
    ("media", ["súbele", "más volumen", "más", "louder", "sube", "subir"],
     "system.volume", {"action": "up"}),
    # modo media: "bájale", "menos" → volume down
    ("media", ["bájale", "menos volumen", "menos", "quieter", "baja", "bajar"],
     "system.volume", {"action": "down"}),
    # modo media: "otra", "cambia", "salta" → next
    ("media", ["otra", "otra canción", "cambia", "salta", "skip", "siguiente"],
     "music.next", {}),
    # modo media: "para", "pausa" → music.pause
    ("media", ["para", "pausa", "detén", "stop"],
     "music.pause", {}),
    # modo coding: "ejecuta", "corre" → code.run
    ("coding", ["ejecuta", "corre", "run", "lanza", "arranca"],
     "code.run", {}),
]

# ── TOKENS MULTI-INTENT ───────────────────────────────────────────────────────
MULTI_INTENT_SEPARATORS = [
    r'\by\s+(?:también\s+)?',     # "y", "y también"
    r'\bdespu[eé]s\s+',           # "después"
    r'\bluego\s+',                 # "luego"
    r'\btambi[eé]n\s+',           # "también"
    r'\badicionalmente\s+',        # "adicionalmente"
    r',\s+',                       # coma
]
_MULTI_SPLIT = re.compile(
    '|'.join(MULTI_INTENT_SEPARATORS), re.I
)


# ══════════════════════════════════════════════════════════════════════════════
# 4. HEURISTIC BRAIN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class HeuristicBrain:
    """
    Motor de clasificación de intenciones offline.
    Sin LLM, sin llamadas externas. Solo Python + rapidfuzz.
    """

    RAPIDFUZZ_CUTOFF = 60   # Umbral de confianza para fuzzy matching

    def __init__(self):
        self._stats = {
            'total': 0, 'regex': 0, 'context': 0,
            'sinonimo': 0, 'fuzzy': 0, 'fallback': 0, 'multi': 0,
        }
        logger.info("✓ Heuristic Brain cargado (%d patrones regex, %d sinónimos)",
                    len(REGEX_PATTERNS), len(SINONIMOS))

    def classify_all(self, text: str, state: Optional[ConversationState] = None
                     ) -> List[Dict]:
        """
        Punto de entrada principal.
        Devuelve lista de intents (normalmente 1, pero puede ser N por multi-intent).
        """
        self._stats['total'] += 1
        if not text or not text.strip():
            return [self._fallback(text)]

        text = text.strip()
        parts = self._split_multi(text)

        results = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            intent = self._classify_single(part, state)
            results.append(intent)
            if len(parts) > 1:
                self._stats['multi'] += 1

        return results or [self._fallback(text)]

    def _classify_single(self, text: str, state: Optional[ConversationState]) -> Dict:
        """Clasificar una sola frase."""
        t = text.lower().strip()

        # 1. CONTEXTO (estado de conversación)
        if state:
            ctx = self._check_context(t, state)
            if ctx:
                self._stats['context'] += 1
                logger.debug(f"Brain [contexto]: {ctx['action']} ← modo={state.mode}")
                return ctx

        # 2. REGEX con extracción de parámetros
        regex_result = self._match_regex(text)
        if regex_result:
            self._stats['regex'] += 1
            logger.debug(f"Brain [regex]: {regex_result['action']} params={regex_result.get('params')}")
            return regex_result

        # 3. SINÓNIMOS exactos / normalizados
        syn_result = self._match_sinonimo(t)
        if syn_result:
            self._stats['sinonimo'] += 1
            logger.debug(f"Brain [sinónimo]: {syn_result['action']}")
            return syn_result

        # 4. rapidfuzz sobre diccionario de sinónimos
        fuzzy_result = self._match_fuzzy(t)
        if fuzzy_result:
            self._stats['fuzzy'] += 1
            logger.debug(f"Brain [fuzzy]: {fuzzy_result['action']} ({fuzzy_result['confidence']:.0%})")
            return fuzzy_result

        # 5. Fallback → chat
        self._stats['fallback'] += 1
        return self._fallback(text)

    # ── MULTI-INTENT SPLITTER ─────────────────────────────────────────────────

    def _split_multi(self, text: str) -> List[str]:
        """Dividir texto en sub-comandos por conectores."""
        parts = _MULTI_SPLIT.split(text)
        if len(parts) > 1:
            logger.debug(f"Multi-intent: {len(parts)} partes de '{text}'")
        return [p for p in parts if len(p.strip()) > 2]

    # ── CONTEXT RULES ─────────────────────────────────────────────────────────

    def _check_context(self, text: str, state: ConversationState) -> Optional[Dict]:
        """Aplicar reglas de contexto según el modo actual."""
        for mode, keywords, action, params in CONTEXT_RULES:
            if state.mode != mode:
                continue
            if any(kw in text for kw in keywords):
                return {
                    'action':     action,
                    'params':     dict(params),
                    'confidence': 0.82,
                    'method':     'context',
                    'raw':        text,
                }
        return None

    # ── REGEX ENGINE ──────────────────────────────────────────────────────────

    def _match_regex(self, text: str) -> Optional[Dict]:
        """Intentar coincidencia con los patrones regex."""
        for pattern, action, param_fn in REGEX_PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    params = param_fn(m)
                    # Limpiar parámetros vacíos
                    params = {k: v for k, v in params.items() if v}
                except Exception:
                    params = {}
                return {
                    'action':     action,
                    'params':     params,
                    'confidence': 0.88,
                    'method':     'regex',
                    'raw':        text,
                }
        return None

    # ── SINÓNIMO EXACTO ───────────────────────────────────────────────────────

    def _match_sinonimo(self, text: str) -> Optional[Dict]:
        """Buscar coincidencia exacta en el diccionario de sinónimos."""
        # Normalizar: quitar acentos para comparación
        normalized = _normalize(text)
        for key, action in SINONIMOS.items():
            if normalized == _normalize(key) or text == key:
                return {
                    'action':     action,
                    'params':     {},
                    'confidence': 0.95,
                    'method':     'sinonimo',
                    'raw':        text,
                }
        return None

    # ── FUZZY MATCHING ────────────────────────────────────────────────────────

    def _match_fuzzy(self, text: str) -> Optional[Dict]:
        """Fuzzy match sobre el diccionario de sinónimos con rapidfuzz."""
        try:
            from rapidfuzz import process, fuzz
            keys = list(SINONIMOS.keys())
            result = process.extractOne(
                text,
                keys,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=self.RAPIDFUZZ_CUTOFF,
            )
            if result:
                matched, score, _ = result
                action = SINONIMOS[matched]
                return {
                    'action':     action,
                    'params':     {},
                    'confidence': score / 100.0,
                    'method':     'fuzzy',
                    'raw':        text,
                    'matched_phrase': matched,
                }
        except ImportError:
            logger.debug("rapidfuzz no disponible")
        except Exception as e:
            logger.debug(f"fuzzy error: {e}")
        return None

    # ── FALLBACK ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback(text: str) -> Dict:
        return {
            'action':     'ai.chat',
            'params':     {},
            'confidence': 0.5,
            'method':     'fallback',
            'raw':        text,
        }

    def get_stats(self) -> str:
        t = self._stats['total'] or 1
        return (
            f"Brain Heurístico | Total: {t} | "
            f"regex: {self._stats['regex']} | "
            f"contexto: {self._stats['context']} | "
            f"sinónimo: {self._stats['sinonimo']} | "
            f"fuzzy: {self._stats['fuzzy']} | "
            f"multi: {self._stats['multi']} | "
            f"fallback: {self._stats['fallback']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════════════

_ACCENT_MAP = str.maketrans(
    'áéíóúüñÁÉÍÓÚÜÑ',
    'aeiouunAEIOUUN'
)


def _normalize(text: str) -> str:
    """Normalizar texto: minúsculas + sin acentos."""
    return text.lower().translate(_ACCENT_MAP)
