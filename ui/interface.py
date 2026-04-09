"""
MARK-45 — Interfaz Gráfica
============================
UI conservada fielmente de JARVIS_v7: Tkinter, tema Iron Man oscuro.
Panel Chat (izquierda) + Panel Sistema (derecha) + Panel Logs.

Creado para MARK-45 por Ali (Sidi3Ali)
"""

import logging
import os
import queue
import threading
from datetime import datetime
from typing import Optional, Callable

logger = logging.getLogger("MARK45.UI")

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False
    logger.warning("tkinter no disponible")

# ── PALETA DE COLORES JARVIS (Iron Man Dark) ──────────────────────────────────
COLORS = {
    'bg_dark':       '#0a0e1a',
    'bg_medium':     '#0f1530',
    'bg_panel':      '#141c3a',
    'bg_input':      '#0d1428',
    'accent_blue':   '#00a8ff',
    'accent_cyan':   '#00e5ff',
    'accent_glow':   '#1a6fff',
    'text_primary':  '#e0f0ff',
    'text_secondary':'#7090c0',
    'text_jarvis':   '#00e5ff',
    'text_user':     '#80d0ff',
    'text_system':   '#40a0d0',
    'success':       '#00ff88',
    'warning':       '#ffb020',
    'danger':        '#ff4060',
    'border':        '#1a3060',
    'separator':     '#0d2040',
}


class AnimatedLabel(tk.Label):
    """Label con efecto de parpadeo."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._blink_state = True
        self._blink_job   = None
        self._blink_orig  = None

    def start_blink(self, interval: int = 800):
        self._blink_orig = self.cget('fg')

        def blink():
            if not self.winfo_exists():
                return
            self.config(fg=self._blink_orig if self._blink_state else COLORS['bg_dark'])
            self._blink_state = not self._blink_state
            self._blink_job   = self.after(interval, blink)

        blink()

    def stop_blink(self):
        if self._blink_job:
            self.after_cancel(self._blink_job)
        if self._blink_orig:
            self.config(fg=self._blink_orig)


class JarvisInterface:
    """Interfaz gráfica principal de MARK 45 — Iron Man HUD."""

    def __init__(self, orchestrator):
        if not TK_AVAILABLE:
            raise ImportError("tkinter no disponible")

        self.orch = orchestrator
        self.root = tk.Tk()
        self._msg_queue: queue.Queue = queue.Queue()
        self._processing = False
        self._voice_listening = False

        self._setup_window()
        self._build_ui()
        self._bind_events()
        self._schedule_ui_updates()

        # Registrar callback en orchestrator
        orchestrator.set_ui_callback(self._on_event)

    # ── CONFIGURACIÓN VENTANA ─────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("J.A.R.V.I.S.  MARK 45 — Hive Kernel")
        self.root.configure(bg=COLORS['bg_dark'])
        self.root.geometry("1300x820")
        self.root.minsize(950, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Estilo de progress bars
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "MARK.Horizontal.TProgressbar",
            troughcolor=COLORS['bg_dark'],
            background=COLORS['accent_cyan'],
            darkcolor=COLORS['accent_blue'],
            lightcolor=COLORS['accent_glow'],
            bordercolor=COLORS['border'],
        )

    # ── CONSTRUCCIÓN UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_main_content()
        self._build_status_bar()

    def _build_header(self):
        header = tk.Frame(self.root, bg=COLORS['bg_panel'], height=72)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)

        # Borde inferior
        tk.Frame(self.root, bg=COLORS['accent_blue'], height=2).pack(fill='x', side='top')

        # Título
        title_frame = tk.Frame(header, bg=COLORS['bg_panel'])
        title_frame.pack(side='left', padx=20, pady=10)

        tk.Label(
            title_frame, text="J.A.R.V.I.S.",
            font=('Courier New', 22, 'bold'),
            fg=COLORS['accent_cyan'], bg=COLORS['bg_panel']
        ).pack(side='top', anchor='w')

        tk.Label(
            title_frame, text="MARK 45 — Hive Kernel | Ali (Sidi3Ali)",
            font=('Courier New', 8),
            fg=COLORS['text_secondary'], bg=COLORS['bg_panel']
        ).pack(side='top', anchor='w')

        # Indicadores (derecha)
        indicators = tk.Frame(header, bg=COLORS['bg_panel'])
        indicators.pack(side='right', padx=20)

        self._ai_indicator    = self._create_indicator(indicators, "IA",   COLORS['accent_cyan'])
        self._voice_indicator = self._create_indicator(indicators, "VOZ",  COLORS['text_secondary'])
        self._llm_indicator   = self._create_indicator(indicators, "LLM",  COLORS['success'])

        # Reloj
        self._clock_lbl = tk.Label(
            header, font=('Courier New', 12, 'bold'),
            fg=COLORS['text_primary'], bg=COLORS['bg_panel']
        )
        self._clock_lbl.pack(side='right', padx=20)
        self._update_clock()

    def _create_indicator(self, parent, text: str, color: str) -> dict:
        frame = tk.Frame(parent, bg=COLORS['bg_panel'])
        frame.pack(side='right', padx=8)
        dot = tk.Label(frame, text="●", font=('Arial', 12), fg=color, bg=COLORS['bg_panel'])
        dot.pack(side='left')
        lbl = tk.Label(frame, text=text, font=('Courier New', 8),
                       fg=COLORS['text_secondary'], bg=COLORS['bg_panel'])
        lbl.pack(side='left')
        return {'frame': frame, 'dot': dot, 'label': lbl, 'active': False}

    def _build_main_content(self):
        main = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main.pack(fill='both', expand=True, padx=5, pady=5)

        # Panel izquierdo — Chat
        left = tk.Frame(main, bg=COLORS['bg_dark'])
        left.pack(side='left', fill='both', expand=True, padx=(0, 3))
        self._build_chat_panel(left)
        self._build_input_panel(left)

        # Panel derecho — Sistema + Logs
        right = tk.Frame(main, bg=COLORS['bg_dark'], width=310)
        right.pack(side='right', fill='y', padx=(3, 0))
        right.pack_propagate(False)
        self._build_system_panel(right)
        self._build_log_panel(right)

    def _build_chat_panel(self, parent):
        chat_header = tk.Frame(parent, bg=COLORS['bg_panel'], height=30)
        chat_header.pack(fill='x')
        tk.Label(
            chat_header, text="◈  INTERFAZ DE COMUNICACIÓN",
            font=('Courier New', 9, 'bold'),
            fg=COLORS['accent_blue'], bg=COLORS['bg_panel']
        ).pack(side='left', padx=10, pady=5)

        self.chat_area = scrolledtext.ScrolledText(
            parent,
            font=('Courier New', 10),
            bg=COLORS['bg_panel'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['accent_cyan'],
            wrap=tk.WORD,
            state='disabled',
            relief='flat', bd=0,
            selectbackground=COLORS['accent_glow'],
        )
        self.chat_area.pack(fill='both', expand=True, pady=(2, 0))

        # Tags de color
        self.chat_area.tag_configure('user',      foreground=COLORS['text_user'],    font=('Courier New', 10))
        self.chat_area.tag_configure('jarvis',    foreground=COLORS['text_jarvis'],  font=('Courier New', 10, 'bold'))
        self.chat_area.tag_configure('system',    foreground=COLORS['text_system'],  font=('Courier New', 9, 'italic'))
        self.chat_area.tag_configure('timestamp', foreground=COLORS['text_secondary'], font=('Courier New', 8))
        self.chat_area.tag_configure('success',   foreground=COLORS['success'])
        self.chat_area.tag_configure('warning',   foreground=COLORS['warning'])
        self.chat_area.tag_configure('error',     foreground=COLORS['danger'])

    def _build_input_panel(self, parent):
        tk.Frame(parent, bg=COLORS['accent_blue'], height=1).pack(fill='x')

        input_frame = tk.Frame(parent, bg=COLORS['bg_panel'], height=62)
        input_frame.pack(fill='x')
        input_frame.pack_propagate(False)

        tk.Label(
            input_frame, text="  SEÑOR › ",
            font=('Courier New', 11, 'bold'),
            fg=COLORS['accent_cyan'], bg=COLORS['bg_panel']
        ).pack(side='left', pady=15)

        self._input_var = tk.StringVar()
        self.input_field = tk.Entry(
            input_frame,
            textvariable=self._input_var,
            font=('Courier New', 11),
            bg=COLORS['bg_input'], fg=COLORS['text_primary'],
            insertbackground=COLORS['accent_cyan'],
            relief='flat', bd=5,
        )
        self.input_field.pack(side='left', fill='both', expand=True, pady=12, padx=(0, 5))

        # Botones
        btn_frame = tk.Frame(input_frame, bg=COLORS['bg_panel'])
        btn_frame.pack(side='right', padx=5)

        self._file_btn = tk.Button(
            btn_frame, text="📎", font=('Arial', 13),
            fg=COLORS['text_primary'], bg=COLORS['bg_medium'],
            relief='flat', padx=8, pady=6, cursor='hand2',
            command=self._upload_file
        )
        self._file_btn.pack(side='left', padx=3, pady=12)
        self._file_btn.bind('<Enter>', lambda e: self._file_btn.config(bg=COLORS['accent_blue']))
        self._file_btn.bind('<Leave>', lambda e: self._file_btn.config(bg=COLORS['bg_medium']))

        self._send_btn = tk.Button(
            btn_frame, text="ENVIAR",
            font=('Courier New', 9, 'bold'),
            fg=COLORS['bg_dark'], bg=COLORS['accent_cyan'],
            relief='flat', padx=10, pady=8, cursor='hand2',
            command=self._send_message
        )
        self._send_btn.pack(side='left', padx=3, pady=12)
        self._send_btn.bind('<Enter>', lambda e: self._send_btn.config(bg=COLORS['text_primary']))
        self._send_btn.bind('<Leave>', lambda e: self._send_btn.config(bg=COLORS['accent_cyan']))

        self._voice_btn = tk.Button(
            btn_frame, text="🎤", font=('Arial', 12),
            fg=COLORS['text_primary'], bg=COLORS['bg_medium'],
            relief='flat', padx=8, pady=8, cursor='hand2',
            command=self._toggle_voice
        )
        self._voice_btn.pack(side='left', padx=3, pady=12)

    def _build_system_panel(self, parent):
        sys_header = tk.Frame(parent, bg=COLORS['bg_panel'], height=30)
        sys_header.pack(fill='x')
        tk.Label(
            sys_header, text="◈  ESTADO DEL SISTEMA",
            font=('Courier New', 9, 'bold'),
            fg=COLORS['accent_blue'], bg=COLORS['bg_panel']
        ).pack(side='left', padx=10, pady=5)

        metrics = tk.Frame(parent, bg=COLORS['bg_panel'], padx=10, pady=10)
        metrics.pack(fill='x')

        # CPU
        self._cpu_var     = tk.StringVar(value="CPU: ---%")
        self._cpu_bar_var = tk.DoubleVar(value=0)
        cpu_frame = tk.Frame(metrics, bg=COLORS['bg_panel'])
        cpu_frame.pack(fill='x', pady=4)
        tk.Label(cpu_frame, textvariable=self._cpu_var,
                 font=('Courier New', 9), fg=COLORS['text_primary'],
                 bg=COLORS['bg_panel'], anchor='w').pack(side='top', fill='x')
        ttk.Progressbar(cpu_frame, variable=self._cpu_bar_var, maximum=100,
                        length=270, style="MARK.Horizontal.TProgressbar").pack(side='top', fill='x')

        # RAM
        self._ram_var     = tk.StringVar(value="RAM: ---%")
        self._ram_bar_var = tk.DoubleVar(value=0)
        ram_frame = tk.Frame(metrics, bg=COLORS['bg_panel'])
        ram_frame.pack(fill='x', pady=4)
        tk.Label(ram_frame, textvariable=self._ram_var,
                 font=('Courier New', 9), fg=COLORS['text_primary'],
                 bg=COLORS['bg_panel'], anchor='w').pack(side='top', fill='x')
        ttk.Progressbar(ram_frame, variable=self._ram_bar_var, maximum=100,
                        length=270, style="MARK.Horizontal.TProgressbar").pack(side='top', fill='x')

        # VRAM
        self._vram_var     = tk.StringVar(value="VRAM: --- MB")
        self._vram_bar_var = tk.DoubleVar(value=0)
        vram_frame = tk.Frame(metrics, bg=COLORS['bg_panel'])
        vram_frame.pack(fill='x', pady=4)
        tk.Label(vram_frame, textvariable=self._vram_var,
                 font=('Courier New', 9), fg=COLORS['text_primary'],
                 bg=COLORS['bg_panel'], anchor='w').pack(side='top', fill='x')
        ttk.Progressbar(vram_frame, variable=self._vram_bar_var, maximum=100,
                        length=270, style="MARK.Horizontal.TProgressbar").pack(side='top', fill='x')

        # Disco
        self._disk_var     = tk.StringVar(value="Disco: ---%")
        self._disk_bar_var = tk.DoubleVar(value=0)
        disk_frame = tk.Frame(metrics, bg=COLORS['bg_panel'])
        disk_frame.pack(fill='x', pady=4)
        tk.Label(disk_frame, textvariable=self._disk_var,
                 font=('Courier New', 9), fg=COLORS['text_primary'],
                 bg=COLORS['bg_panel'], anchor='w').pack(side='top', fill='x')
        ttk.Progressbar(disk_frame, variable=self._disk_bar_var, maximum=100,
                        length=270, style="MARK.Horizontal.TProgressbar").pack(side='top', fill='x')

        # Estado IA
        ai_frame = tk.Frame(metrics, bg=COLORS['bg_panel'])
        ai_frame.pack(fill='x', pady=8)
        tk.Label(ai_frame, text="FUENTE IA:",
                 font=('Courier New', 8), fg=COLORS['text_secondary'],
                 bg=COLORS['bg_panel']).pack(side='left')
        self._ai_source_var = tk.StringVar(value="Detectando...")
        tk.Label(ai_frame, textvariable=self._ai_source_var,
                 font=('Courier New', 8, 'bold'),
                 fg=COLORS['accent_cyan'], bg=COLORS['bg_panel']).pack(side='left', padx=5)

        # Modo Gaming
        self._gaming_var = tk.StringVar(value="")
        self._gaming_lbl = tk.Label(
            metrics, textvariable=self._gaming_var,
            font=('Courier New', 10, 'bold'),
            fg=COLORS['warning'], bg=COLORS['bg_panel']
        )
        self._gaming_lbl.pack(anchor='w')

        # Estado general
        tk.Label(metrics, text="ESTADO:", font=('Courier New', 8),
                 fg=COLORS['text_secondary'], bg=COLORS['bg_panel']).pack(anchor='w')
        self._mood_var = tk.StringVar(value="INICIANDO...")
        tk.Label(metrics, textvariable=self._mood_var,
                 font=('Courier New', 10, 'bold'),
                 fg=COLORS['success'], bg=COLORS['bg_panel']).pack(anchor='w')

    def _build_log_panel(self, parent):
        tk.Frame(parent, bg=COLORS['separator'], height=2).pack(fill='x', pady=5)
        log_header = tk.Frame(parent, bg=COLORS['bg_panel'], height=25)
        log_header.pack(fill='x')
        tk.Label(
            log_header, text="◈  LOGS DEL SISTEMA",
            font=('Courier New', 8, 'bold'),
            fg=COLORS['accent_blue'], bg=COLORS['bg_panel']
        ).pack(side='left', padx=10, pady=3)

        self.log_area = scrolledtext.ScrolledText(
            parent,
            font=('Courier New', 8),
            bg=COLORS['bg_dark'], fg=COLORS['text_secondary'],
            state='disabled', relief='flat', bd=0, height=12, wrap=tk.WORD
        )
        self.log_area.pack(fill='both', expand=True)

    def _build_status_bar(self):
        tk.Frame(self.root, bg=COLORS['accent_blue'], height=1).pack(fill='x')
        status_bar = tk.Frame(self.root, bg=COLORS['bg_panel'], height=25)
        status_bar.pack(fill='x', side='bottom')
        status_bar.pack_propagate(False)

        self._status_var = tk.StringVar(value="Sistema inicializado — A sus órdenes, Señor.")
        tk.Label(
            status_bar, textvariable=self._status_var,
            font=('Courier New', 8), fg=COLORS['text_secondary'], bg=COLORS['bg_panel']
        ).pack(side='left', padx=10, pady=3)

        tk.Label(
            status_bar, text="MARK 45 | Hive Kernel | Ali (Sidi3Ali)",
            font=('Courier New', 8),
            fg=COLORS['text_secondary'], bg=COLORS['bg_panel']
        ).pack(side='right', padx=10)

    # ── EVENTOS ───────────────────────────────────────────────────────────────

    def _bind_events(self):
        self.root.bind('<Return>', lambda e: self._send_message())
        self.root.bind('<Control-l>', lambda e: self._clear_chat())
        self.input_field.focus_set()

    def _on_event(self, event_type: str, data=None):
        """Callback del orchestrator → cola thread-safe."""
        self._msg_queue.put((event_type, data))

    def _process_msg_queue(self):
        while not self._msg_queue.empty():
            try:
                event_type, data = self._msg_queue.get_nowait()
                self._handle_event(event_type, data)
            except queue.Empty:
                break
            except Exception as e:
                logger.debug(f"Queue error: {e}")

    def _handle_event(self, event_type: str, data):
        if event_type == 'response':
            if isinstance(data, dict):
                user = data.get('user', '')
                mark = data.get('mark', '')
                if user:
                    self._add_chat_message("Señor", user, 'user')
                if mark:
                    self._add_chat_message("MARK 45", mark, 'jarvis')
                    self._set_status("Listo — A sus órdenes, Señor.")
            elif isinstance(data, str) and data:
                self._add_chat_message("MARK 45", data, 'jarvis')
        elif event_type == 'error':
            self._add_chat_message("Sistema", f"Error: {data}", 'error')
            self._set_ai_indicator(False)
        elif event_type == 'done':
            self._set_ai_indicator(False)
        elif event_type == 'stats':
            self._update_metrics_from_stats(data)
        elif event_type == 'log':
            self._add_log(str(data))
        elif event_type == 'alert':
            self._add_chat_message("Sistema", str(data), 'warning')

    # ── ENVÍO DE MENSAJES ─────────────────────────────────────────────────────

    def _send_message(self):
        if self._processing:
            return
        text = self._input_var.get().strip()
        if not text:
            return

        self._processing = True
        self._input_var.set('')
        self._add_chat_message("Señor", text, 'user')
        self._set_status("Procesando solicitud...")
        self._set_ai_indicator(True)

        def process():
            try:
                response = self.orch.send_text_command(text)
                self._msg_queue.put(('response_text', response))
            except Exception as e:
                self._msg_queue.put(('error', str(e)))
            finally:
                self._msg_queue.put(('done', None))
                self._processing = False

        threading.Thread(target=process, daemon=True).start()

    # ── ACTUALIZACIÓN UI ──────────────────────────────────────────────────────

    def _schedule_ui_updates(self):
        def update():
            self._process_msg_queue()
            if not self.root.winfo_exists():
                return
            self.root.after(800, update)
        self.root.after(800, update)

    def _update_metrics_from_stats(self, stats: dict):
        if not stats:
            return
        try:
            cpu   = stats.get('cpu', 0)
            ram   = stats.get('ram', 0)
            disk  = stats.get('disk', 0)
            vram_used  = stats.get('vram_used_mb', 0)
            vram_total = stats.get('vram_total_mb', 0)
            gaming = stats.get('gaming_mode', False)
            game   = stats.get('game_name', '')

            self._cpu_var.set(f"CPU: {cpu:.1f}%")
            self._cpu_bar_var.set(cpu)
            self._ram_var.set(f"RAM: {ram:.1f}%")
            self._ram_bar_var.set(ram)
            self._disk_var.set(f"Disco: {disk:.1f}%")
            self._disk_bar_var.set(disk)

            if vram_total:
                self._vram_var.set(f"VRAM: {vram_used}/{vram_total} MB")
                self._vram_bar_var.set((vram_used / vram_total) * 100 if vram_total else 0)
            else:
                self._vram_var.set("VRAM: N/A")

            if gaming:
                self._gaming_var.set(f"🎮  GAMING: {game}")
                self._mood_var.set("◉  GAMING MODE")
            else:
                self._gaming_var.set("")
                mood_val = "◉  PROCESANDO" if cpu > 60 else "●  NOMINAL"
                self._mood_var.set(mood_val)

            # LLM source
            if self.orch.llm:
                self._ai_source_var.set(self.orch.llm.active_provider)

        except Exception as e:
            logger.debug(f"update_metrics: {e}")

    def _handle_event(self, event_type: str, data):
        if event_type == 'response':
            if isinstance(data, dict):
                if data.get('mark'):
                    self._add_chat_message("MARK 45", data['mark'], 'jarvis')
                    self._set_status("Listo — A sus órdenes, Señor.")
        elif event_type == 'response_text':
            if data:
                self._add_chat_message("MARK 45", data, 'jarvis')
                self._set_status("Listo — A sus órdenes, Señor.")
                # Hablar en voz alta
                threading.Thread(
                    target=lambda: self.orch.speak_sync(data), daemon=True
                ).start()
        elif event_type == 'error':
            self._add_chat_message("Sistema", f"Error: {data}", 'error')
            self._set_ai_indicator(False)
        elif event_type == 'done':
            self._set_ai_indicator(False)
        elif event_type == 'stats':
            self._update_metrics_from_stats(data)
        elif event_type == 'log':
            self._add_log(str(data))
        elif event_type == 'alert':
            self._add_chat_message("Sistema", str(data), 'warning')

    # ── HELPERS ──────────────────────────────────────────────────────────────

    def _add_chat_message(self, sender: str, message: str, msg_type: str = 'system'):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_area.config(state='normal')
        self.chat_area.insert('end', f"[{timestamp}] ", 'timestamp')
        prefix = {
            'user':    f"[ {sender} ]: ",
            'jarvis':  f"[ {sender} ]: ",
            'system':  f"[ {sender} ]: ",
            'error':   "[ ERROR ]: ",
            'warning': "[ ⚠ ALERTA ]: ",
            'success': "[ ✓ ]: ",
        }.get(msg_type, f"[ {sender} ]: ")
        self.chat_area.insert('end', prefix, msg_type)
        self.chat_area.insert('end', f"{message}\n\n", msg_type)
        self.chat_area.config(state='disabled')
        self.chat_area.see('end')

    def _add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state='normal')
        self.log_area.insert('end', f"[{timestamp}] {message}\n")
        self.log_area.config(state='disabled')
        self.log_area.see('end')

    def _set_status(self, text: str):
        self._status_var.set(text)

    def _set_ai_indicator(self, active: bool):
        color = COLORS['warning'] if active else COLORS['accent_cyan']
        self._ai_indicator['dot'].config(fg=color)

    def _update_clock(self):
        self._clock_lbl.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._update_clock)

    # ── ACCIONES DE BOTONES ───────────────────────────────────────────────────

    def _upload_file(self):
        from tkinter import filedialog
        FILETYPES = [
            ("Todos los soportados", "*.docx *.pdf *.txt *.md *.py *.js *.html *.json *.csv *.jpg *.png"),
            ("Código",   "*.py *.js *.ts *.html *.css *.json *.xml *.cpp *.c *.java"),
            ("Texto",    "*.txt *.md *.pdf *.docx"),
            ("Imágenes", "*.jpg *.jpeg *.png"),
            ("Todos",    "*.*"),
        ]
        filepath = filedialog.askopenfilename(title="Seleccionar archivo para MARK 45", filetypes=FILETYPES)
        if not filepath:
            return
        filename = os.path.basename(filepath)
        self._add_chat_message("Señor", f"[Archivo: {filename}]", 'user')
        self._set_status("Cargando archivo...")
        self._set_ai_indicator(True)
        self._processing = True

        def process():
            try:
                response = self.orch.send_text_command(f"Lee y analiza este archivo: {filepath}")
                self._msg_queue.put(('response_text', response))
            except Exception as e:
                self._msg_queue.put(('error', str(e)))
            finally:
                self._msg_queue.put(('done', None))
                self._processing = False

        threading.Thread(target=process, daemon=True).start()

    def _toggle_voice(self):
        v = self.orch._voice
        if not v or not v.stt_enabled:
            self._add_chat_message("Sistema", "STT no disponible. Instala speech_recognition.", 'system')
            return

        wd = self.orch._wake_daemon
        if wd:
            new_state = not wd.enabled
            wd.set_enabled(new_state)
            if new_state:
                self._voice_btn.config(text="⏹", bg=COLORS['danger'])
                self._voice_indicator['dot'].config(fg=COLORS['success'])
                self._add_log("Wake word daemon habilitado (di 'Jarvis')")
            else:
                self._voice_btn.config(text="🎤", bg=COLORS['bg_medium'])
                self._voice_indicator['dot'].config(fg=COLORS['text_secondary'])
                self._add_log("Wake word daemon deshabilitado")
        else:
            # Sin daemon — escucha puntual
            if self._voice_listening:
                self._voice_listening = False
                self._voice_btn.config(text="🎤", bg=COLORS['bg_medium'])
                self._voice_indicator['dot'].config(fg=COLORS['text_secondary'])
            else:
                self._voice_listening = True
                self._voice_btn.config(text="⏹", bg=COLORS['danger'])
                self._voice_indicator['dot'].config(fg=COLORS['success'])
                threading.Thread(target=self._listen_once, daemon=True).start()

    def _listen_once(self):
        self._add_log("Escuchando comando de voz...")
        try:
            text = self.orch._voice.listen(timeout=8)
            if text:
                self._input_var.set(text)
                self.root.after(0, self._send_message)
            else:
                self._add_log("No se detectó voz.")
        except Exception as e:
            self._add_log(f"Error voz: {e}")
        finally:
            self._voice_listening = False
            self._voice_btn.config(text="🎤", bg=COLORS['bg_medium'])
            self._voice_indicator['dot'].config(fg=COLORS['text_secondary'])

    def _clear_chat(self):
        self.chat_area.config(state='normal')
        self.chat_area.delete('1.0', 'end')
        self.chat_area.config(state='disabled')
        self._add_chat_message("Sistema", "Historial de chat limpiado, Señor.", 'system')

    def _on_close(self):
        try:
            threading.Thread(
                target=lambda: self.orch.speak_sync("Hasta luego, Señor. MARK 45 desconectándose."),
                daemon=True
            ).start()
            self.orch.shutdown_sync()
        except Exception:
            pass
        self.root.destroy()

    # ── RUN ──────────────────────────────────────────────────────────────────

    def run(self):
        """Iniciar loop principal de UI y mostrar greeting."""
        try:
            greeting_text = self.orch._greeting()
            self._add_chat_message("MARK 45", greeting_text, 'jarvis')
            self._add_log("MARK 45 en línea. Hive Kernel activo.")
            threading.Thread(
                target=lambda: self.orch.speak_sync(greeting_text), daemon=True
            ).start()
        except Exception:
            self._add_chat_message("MARK 45", "En línea. ¿Qué necesita, Señor?", 'jarvis')

        self.root.mainloop()
