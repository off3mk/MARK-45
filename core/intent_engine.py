"""
MARK-45 — Motor de Intención Universal
=========================================
Estrategia dual:
  1. LLM (primario): clasifica CUALQUIER frase → JSON {intent, action, params, confidence}
  2. rapidfuzz (fallback): coincidencia difusa sobre frases canónicas en español

Sin if/elif de comandos hardcodeados.
El LLM interpreta cualquier forma de pedir algo en español.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MARK45.Intent")

# ── CATÁLOGO DE ACCIONES ──────────────────────────────────────────────────────

ACTIONS_CATALOG = """
Eres el clasificador de intenciones de MARK 45. Tu trabajo es entender
qué quiere el usuario, sin importar cómo lo diga en español.

ACCIONES DISPONIBLES:
──────────────────────────────────────────────────────────────────
SISTEMA
  system.status         → Ver estado del sistema (CPU, RAM, disco, procesos)
  system.open_app       → Abrir cualquier aplicación o programa
  system.close_app      → Cerrar una aplicación
  system.shutdown       → Apagar/reiniciar el PC
  system.volume         → Subir/bajar/silenciar el volumen
  system.minimize_all   → Minimizar todas las ventanas (Win+D)
  system.processes      → Ver/matar procesos activos
  system.gaming_mode    → Activar/desactivar modo gaming

PANTALLA Y VISIÓN
  screen.analyze        → Describir/analizar lo que hay en pantalla ahora
  screen.screenshot     → Tomar captura de pantalla
  screen.read_text      → Leer/extraer el texto visible en pantalla

WEB Y BÚSQUEDA
  web.search            → Buscar en internet (Google)
  web.open_url          → Abrir una URL específica
  web.youtube           → Buscar/abrir YouTube

MÚSICA Y SPOTIFY
  music.play            → Reproducir música/canción/artista/playlist
  music.pause           → Pausar música
  music.next            → Siguiente canción
  music.previous        → Canción anterior
  music.volume          → Cambiar volumen de música
  music.info            → Qué canción está sonando

ARCHIVOS Y DOCUMENTOS
  files.read            → Leer/analizar un archivo del disco
  files.organize        → Organizar carpeta (por tipo, fecha)
  files.search          → Buscar archivos en el disco
  files.disk_info       → Ver espacio en disco

CÓDIGO Y DESARROLLO
  code.generate         → Generar script/programa/función
  code.analyze          → Analizar/revisar código existente
  code.fix              → Corregir errores en código
  code.run              → Ejecutar un script
  code.terminal         → Ejecutar comando en terminal

IA Y RAZONAMIENTO
  ai.chat               → Conversación general, preguntas, respuestas
  ai.summarize          → Resumir texto/documento
  ai.translate          → Traducir texto
  ai.write              → Redactar texto, emails, documentos
  ai.explain            → Explicar conceptos técnicos

MARK 45 (autogestión)
  mark.status           → Estado general de MARK 45
  mark.history          → Ver historial de conversación
  mark.clear_history    → Limpiar historial
  mark.identity         → Quién creó MARK 45, versión, etc.
  mark.stop             → Apagar MARK 45
──────────────────────────────────────────────────────────────────

INSTRUCCIONES:
1. Lee el mensaje del usuario (puede estar mal escrito, en spanglish, coloquial)
2. Determina la intención real
3. Devuelve SOLO un JSON válido con esta estructura exacta:

{
  "intent": "descripción breve de lo que quiere en español",
  "action": "categoria.accion",
  "params": {"key": "value"},
  "confidence": 0.95,
  "response_hint": "respuesta corta si no se puede ejecutar"
}

EJEMPLOS:
Usuario: "oye ponme algo de spotify"
→ {"intent": "reproducir spotify", "action": "music.play", "params": {}, "confidence": 0.97, "response_hint": ""}

Usuario: "cuánta ram me queda"
→ {"intent": "ver estado RAM", "action": "system.status", "params": {"focus": "ram"}, "confidence": 0.98, "response_hint": ""}

Usuario: "minimiza todo que quiero ver el escritorio"
→ {"intent": "minimizar ventanas", "action": "system.minimize_all", "params": {}, "confidence": 0.96, "response_hint": ""}

Si ninguna acción es adecuada, usa "ai.chat".
NUNCA devuelvas texto fuera del JSON.
"""

# ── FRASES CANÓNICAS PARA RAPIDFUZZ ──────────────────────────────────────────

FRASES_CANONICAS: Dict[str, str] = {
    # Sistema
    "cuánto cpu tengo": "system.status",
    "cuánta ram tengo": "system.status",
    "estado del sistema": "system.status",
    "cómo está el pc": "system.status",
    "temperatura del sistema": "system.status",
    "ver procesos activos": "system.processes",
    "minimiza todo": "system.minimize_all",
    "minimiza las ventanas": "system.minimize_all",
    "muestra el escritorio": "system.minimize_all",
    "sube el volumen": "system.volume",
    "baja el volumen": "system.volume",
    "silencia el audio": "system.volume",
    "abre el explorador": "system.open_app",
    "modo gaming": "system.gaming_mode",
    # Música / Spotify
    "pon música": "music.play",
    "reproduce música": "music.play",
    "abre spotify": "music.play",
    "pon algo de spotify": "music.play",
    "ponme música en spotify": "music.play",
    "quiero escuchar música": "music.play",
    "pon una canción": "music.play",
    "reproduce spotify": "music.play",
    "pausa la música": "music.pause",
    "para la música": "music.pause",
    "siguiente canción": "music.next",
    "canción anterior": "music.previous",
    "qué está sonando": "music.info",
    "qué canción es esta": "music.info",
    # Web
    "busca en google": "web.search",
    "abre youtube": "web.youtube",
    "pon youtube": "web.youtube",
    "abre el navegador": "web.open_url",
    # Archivos
    "organiza las descargas": "files.organize",
    "cuánto espacio tengo": "files.disk_info",
    "busca un archivo": "files.search",
    # Código
    "genera un script": "code.generate",
    "crea un programa": "code.generate",
    "ejecuta en la terminal": "code.terminal",
    # IA
    "resume esto": "ai.summarize",
    "traduce esto": "ai.translate",
    "explica esto": "ai.explain",
    # MARK
    "quién eres": "mark.identity",
    "cuál es tu versión": "mark.identity",
    "apágate": "mark.stop",
    "hasta luego": "mark.stop",
    "limpia el historial": "mark.clear_history",
    "captura de pantalla": "screen.screenshot",
    "analiza la pantalla": "screen.analyze",
}


@dataclass
class Intent:
    """Resultado del análisis de intención."""
    intent:        str
    action:        str
    category:      str
    subcategory:   str
    params:        Dict  = field(default_factory=dict)
    confidence:    float = 0.0
    response_hint: str   = ""
    raw_input:     str   = ""
    _multi:        Any   = field(default=None, repr=False)  # multi-intent list

    @classmethod
    def from_dict(cls, d: Dict, raw: str = "") -> 'Intent':
        action = d.get('action', 'ai.chat')
        parts  = action.split('.', 1)
        return cls(
            intent      = d.get('intent', ''),
            action      = action,
            category    = parts[0] if len(parts) > 0 else 'ai',
            subcategory = parts[1] if len(parts) > 1 else 'chat',
            params      = d.get('params', {}),
            confidence  = float(d.get('confidence', 0.5)),
            response_hint = d.get('response_hint', ''),
            raw_input   = raw,
        )

    @classmethod
    def chat_fallback(cls, raw: str = "") -> 'Intent':
        return cls(
            intent='conversación general', action='ai.chat',
            category='ai', subcategory='chat',
            params={}, confidence=0.5, raw_input=raw
        )

    @classmethod
    def from_action(cls, action: str, raw: str = "", confidence: float = 0.8) -> 'Intent':
        parts = action.split('.', 1)
        return cls(
            intent      = raw,
            action      = action,
            category    = parts[0],
            subcategory = parts[1] if len(parts) > 1 else '',
            params      = {},
            confidence  = confidence,
            raw_input   = raw,
        )


class IntentEngine:
    """
    Motor de intención universal.
    Prioridad: LLM → HeuristicBrain (regex+sinónimos+contexto) → rapidly fallback → chat
    """

    CONFIDENCE_THRESHOLD = 0.65

    def __init__(self, llm_engine):
        self.llm = llm_engine
        self._cache: Dict[str, Intent] = {}
        self._stats = {'total': 0, 'llm': 0, 'rapidfuzz': 0, 'cache': 0, 'failures': 0}
        # Instanciar el cerebro heurístico de emergencia
        try:
            from core.heuristic_brain import HeuristicBrain
            self.brain = HeuristicBrain()
        except Exception as e:
            logger.warning(f"HeuristicBrain no cargado: {e}")
            self.brain = None

    def classify(
        self,
        user_input: str,
        screen_context: str = "",
        conversation_context: str = "",
        conversation_state=None,       # ConversationState opcional
    ) -> Intent:
        """Clasificar la intención del usuario. Devuelve el intent más probable."""
        self._stats['total'] += 1
        if not user_input or not user_input.strip():
            return Intent.chat_fallback()

        text = user_input.strip()

        # Bug 2: HARD OVERRIDE para evitar que el PC se apague cuando pide apagar IA
        t_lower = text.lower()
        if t_lower in ["apágate", "apagate", "apágate tú", "apagate tu", "desconéctate", "desconectate"]:
            intent = Intent.from_action('mark.stop', text, 1.0)
            logger.info(f"Intent [Override]: {intent.action} (100%)")
            return intent

        # Cache para frases repetidas
        cache_key = re.sub(r'[^\w\s]', '', text.lower()).strip()
        if cache_key in self._cache:
            self._stats['cache'] += 1
            cached = self._cache[cache_key]
            cached.raw_input = text
            return cached

        # 1. LLM primario
        if self.llm and self.llm._model:
            intent = self._classify_llm(text, screen_context, conversation_context)
            if intent and intent.confidence >= self.CONFIDENCE_THRESHOLD:
                self._stats['llm'] += 1
                if intent.confidence >= 0.7:
                    self._cache[cache_key] = intent
                logger.info(f"Intent [LLM]: {intent.action} ({intent.confidence:.0%})")
                return intent

        # 2. HeuristicBrain (motor offline avanzado)
        if self.brain:
            results = self.brain.classify_all(text, conversation_state)
            if results:
                best = results[0]   # Intent principal
                if best.get('action', 'ai.chat') != 'ai.chat' or len(results) == 1:
                    action = best['action']
                    intent = Intent.from_action(action, text, best.get('confidence', 0.80))
                    intent.params = best.get('params', {})
                    # Guardar lista completa en intent para multi-intent
                    intent._multi = results if len(results) > 1 else None
                    self._stats['rapidfuzz'] += 1
                    logger.info(f"Intent [Brain]: {action} ({intent.confidence:.0%}) params={intent.params}")
                    if best.get('confidence', 0) >= 0.75:
                        self._cache[cache_key] = intent
                    return intent

        # 3. Fallback rapidfuzz (frases canónicas originales)
        intent = self._classify_rapidfuzz(text)
        if intent:
            self._stats['rapidfuzz'] += 1
            logger.info(f"Intent [rapidfuzz]: {intent.action} ({intent.confidence:.0%})")
            return intent

        # 4. Fallback final: chat
        self._stats['failures'] += 1
        return Intent.chat_fallback(text)

    def classify_multi(
        self,
        user_input: str,
        conversation_state=None,
    ) -> 'List[Intent]':
        """
        Clasificar permitiendo multi-intent (para orquestación secuencial).
        Devuelve lista de intents (normalmente 1).
        """
        if self.brain:
            results = self.brain.classify_all(user_input.strip(), conversation_state)
            intents = []
            for r in results:
                i = Intent.from_action(r['action'], user_input, r.get('confidence', 0.80))
                i.params = r.get('params', {})
                intents.append(i)
            return intents
        # Fallback: clasificación única
        return [self.classify(user_input, conversation_state=conversation_state)]

    def _classify_llm(
        self, text: str, screen_ctx: str, conv_ctx: str
    ) -> Optional[Intent]:
        """Clasificar usando LLM."""
        context_parts = []
        if screen_ctx:
            context_parts.append(f"Pantalla: {screen_ctx[:200]}")
        if conv_ctx:
            context_parts.append(f"Contexto: {conv_ctx[:300]}")
        context_str = '\n'.join(context_parts)
        prompt = (
            f"{ACTIONS_CATALOG}\n\n"
            f"{'CONTEXTO:\n' + context_str + chr(10) if context_str else ''}"
            f'MENSAJE DEL USUARIO: "{text}"\n\nJSON:'
        )
        try:
            response = self.llm.generate(
                prompt, with_history=False, max_tokens=300, temperature=0.1
            )
            return self._parse_response(response, text)
        except Exception as e:
            logger.debug(f"LLM classify error: {e}")
            return None

    def _classify_rapidfuzz(self, text: str) -> Optional[Intent]:
        """Clasificar usando rapidfuzz (coincidencia difusa en español)."""
        t = text.lower()

        # ── Pre-check por palabras clave (antes de scoring) ──────────────────
        # Captura frases con tokens extra que confunden al scorer (e.g. "Spotify")
        if any(w in t for w in ['spotify', 'musica', 'música', 'cancion', 'canción', 'reproduce', 'ponme', 'quiero escuchar']):
            if any(w in t for w in ['pausa', 'para', 'stop']):
                return Intent.from_action('music.pause', text, 0.85)
            if any(w in t for w in ['siguiente', 'next', 'salta']):
                return Intent.from_action('music.next', text, 0.85)
            if any(w in t for w in ['anterior', 'anterior', 'prev']):
                return Intent.from_action('music.previous', text, 0.85)
            # Default: play
            intent = Intent.from_action('music.play', text, 0.82)
            intent.params = self._extract_params_heuristic(text, 'music.play')
            return intent

        try:
            from rapidfuzz import process, fuzz
            keys = list(FRASES_CANONICAS.keys())
            result = process.extractOne(
                t,
                keys,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=60,
            )
            if result:
                matched_phrase, score, _ = result
                action = FRASES_CANONICAS[matched_phrase]
                confidence = score / 100.0
                intent = Intent.from_action(action, text, confidence)
                intent.params = self._extract_params_heuristic(text, action)
                return intent
        except ImportError:
            logger.debug("rapidfuzz no disponible, usando heurística simple")
            return self._heuristic_fallback(text)
        except Exception as e:
            logger.debug(f"rapidfuzz error: {e}")
        return None

    def _extract_params_heuristic(self, text: str, action: str) -> Dict:
        """Extraer parámetros básicos del texto en español."""
        t = text.lower()
        params: Dict[str, Any] = {}

        if action == "system.status":
            if 'cpu' in t:
                params['focus'] = 'cpu'
            elif 'ram' in t or 'memoria' in t:
                params['focus'] = 'ram'
            elif 'disco' in t or 'espacio' in t:
                params['focus'] = 'disco'

        elif action == "system.volume":
            if any(w in t for w in ['sube', 'más', 'mas', 'subir', 'louder']):
                params['action'] = 'up'
            elif any(w in t for w in ['baja', 'menos', 'bajar', 'quieter']):
                params['action'] = 'down'
            elif any(w in t for w in ['silenci', 'mute', 'calla']):
                params['action'] = 'mute'

        elif action == "music.play":
            query = re.sub(
                r'(spotify|música|musica|reproduce|pon|escuchar|ponme|abre)\s*',
                '', t
            ).strip()
            if query:
                params['query'] = query

        elif action in ("web.search", "web.youtube"):
            query = re.sub(
                r'(busca|googlea|google|youtube|yt|pon|ver|buscar)\s*', '', t
            ).strip()
            if query:
                params['query'] = query

        elif action == "system.open_app":
            app = re.sub(
                r'(abre|lanza|inicia|ejecuta|pon|arranca)\s*(el|la|los|las)?\s*', '', t
            ).strip()
            if app:
                params['name'] = app

        return params

    def _parse_response(self, response: str, raw: str) -> Optional[Intent]:
        """Parsear respuesta JSON del LLM."""
        patterns = [
            r'\{[^{}]*"action"[^{}]*\}',
            r'\{.*?"action".*?\}',
            r'\{.*\}',
        ]
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    d = json.loads(match.group())
                    intent = Intent.from_dict(d, raw)
                    if '.' in intent.action:
                        return intent
                except json.JSONDecodeError:
                    continue
        return None

    def _heuristic_fallback(self, text: str) -> Optional[Intent]:
        """Heurística simple sin rapidfuzz."""
        t = text.lower()
        if any(w in t for w in ['cpu', 'ram', 'memoria', 'disco', 'estado', 'status']):
            return Intent.from_action('system.status', text, 0.80)
        if any(w in t for w in ['spotify', 'música', 'musica', 'canción', 'reproduce']):
            return Intent.from_action('music.play', text, 0.80)
        if any(w in t for w in ['minimiza', 'escritorio', 'ventanas']):
            return Intent.from_action('system.minimize_all', text, 0.85)
        if any(w in t for w in ['youtube', 'video', 'vídeo']):
            return Intent.from_action('web.youtube', text, 0.80)
        if any(w in t for w in ['busca', 'googlea', 'internet']):
            return Intent.from_action('web.search', text, 0.80)
        if any(w in t for w in ['captura', 'screenshot']):
            return Intent.from_action('screen.screenshot', text, 0.88)
        if any(w in t for w in ['apágate', 'apagate', 'hasta luego', 'adios', 'adiós']):
            return Intent.from_action('mark.stop', text, 0.90)
        if any(w in t for w in ['quién eres', 'quien eres', 'tu nombre', 'creador']):
            return Intent.from_action('mark.identity', text, 0.90)
        return None

    def get_stats(self) -> str:
        total = self._stats['total']
        if total == 0:
            return "IntentEngine: sin consultas todavía."
        return (
            f"Total: {total} | LLM: {self._stats['llm']} | "
            f"rapidfuzz: {self._stats['rapidfuzz']} | "
            f"cache: {self._stats['cache']} | "
            f"fallback: {self._stats['failures']}"
        )

    def clear_cache(self):
        self._cache.clear()
