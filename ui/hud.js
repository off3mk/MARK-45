/**
 * MARK-45 — Stark HUD | hud.js
 * Lógica WebSocket + animaciones en tiempo real
 * Creado por Ali (Sidi3Ali)
 */

'use strict';

// ── CONFIG ──────────────────────────────────────────────────────
const API_BASE  = 'http://127.0.0.1:8765';
const WS_URL    = 'ws://127.0.0.1:8765/ws/eventos';
const VRAM_MAX  = 8192;   // RTX 4060 Ti 8GB

// ── STATE ───────────────────────────────────────────────────────
let ws              = null;
let reconnectTimer  = null;
let reconnectCount  = 0;
const MAX_RECONNECT = 99;

// ── DOM REFS ────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── RELOJ ───────────────────────────────────────────────────────
function updateClock() {
  $('hud-clock').textContent = new Date().toLocaleTimeString('es-ES', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── ESTADO IA → TEMA VISUAL ─────────────────────────────────────
const STATE_CLASSES = {
  'NOMINAL':      'state-nominal',
  'ESCUCHANDO':   'state-escuchando',
  'MODOACTIVO':   'state-modoactivo',
  'PROCESANDO':   'state-procesando',
  'HABLANDO':     'state-hablando',
  'ERROR':        'state-error',
  'OFFLINE':      'state-offline',
};
const STATE_LABELS = {
  'NOMINAL':      '● NOMINAL',
  'ESCUCHANDO':   '◎ ESCUCHANDO',
  'MODOACTIVO':   '◎ MODO ACTIVO',
  'PROCESANDO':   '◈ PROCESANDO',
  'HABLANDO':     '▶ HABLANDO',
  'ERROR':        '✕ ERROR',
  'OFFLINE':      '○ OFFLINE',
};
const STATE_COLORS = {
  nominal:     '#00e5ff',
  escuchando:  '#9d4eff',
  modoactivo:  '#b500ff',
  procesando:  '#ff9d00',
  hablando:    '#00ff88',
  error:       '#ff2050',
  offline:     '#334455',
};

function setEstado(estado) {
  const body  = document.body;
  const badge = $('state-badge');
  const dot   = $('ws-dot');
  const label = $('ws-label');

  // Quitar todas las clases de estado
  Object.values(STATE_CLASSES).forEach(c => body.classList.remove(c));
  const cls = STATE_CLASSES[estado] || 'state-nominal';
  body.classList.add(cls);

  // Badge
  if (badge) {
    badge.textContent = STATE_LABELS[estado] || `● ${estado}`;
  }

  // Actualizaar reactor SVG con el color del estado
  updateReactorColor(cls.replace('state-', ''));

  // WS dot parpadeo
  if (dot) {
    dot.className = 'hud-dot' + ((estado === 'ESCUCHANDO' || estado === 'MODOACTIVO') ? ' blink' : '');
    if (estado === 'ERROR' || estado === 'OFFLINE') {
      dot.classList.add('offline');
    }
  }
}

function updateReactorColor(stateName) {
  const color = STATE_COLORS[stateName] || STATE_COLORS.nominal;
  document.querySelectorAll('.ring-outer,.ring-mid,.ring-inner').forEach(el => {
    el.setAttribute('stroke', color);
  });
  const core = document.querySelector('.reactor-core');
  if (core) {
    const stops = core.querySelectorAll('stop');
    stops.forEach(s => {
      if (s.getAttribute('offset') === '0%') s.setAttribute('stop-color', color);
    });
  }
}

// ── CHAT ────────────────────────────────────────────────────────
function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function addMsg(rol, texto) {
  const container = $('chat-messages');
  if (!container) return;
  const hora = new Date().toLocaleTimeString('es-ES', { hour12: false });
  const nombre = rol === 'usuario' ? 'SEÑOR' : 'MARK 45';
  const div = document.createElement('div');
  div.className = 'msg-block';
  div.innerHTML = `
    <div class="msg-header ${rol}">
      <span class="msg-header-dot"></span>
      <span>${nombre}</span>
      <span style="color:var(--text-muted);font-weight:400">${hora}</span>
    </div>
    <div class="msg-text ${rol}">${escHtml(texto)}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

// ── LOGS ────────────────────────────────────────────────────────
function addLog(msg) {
  const el = $('log-area');
  if (!el) return;
  const hora = new Date().toLocaleTimeString('es-ES', { hour12: false });
  el.textContent += `[${hora}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}

// ── MÉTRICAS ─────────────────────────────────────────────────────
function updateBar(prefix, pct) {
  const bar = $(`${prefix}-bar`);
  if (!bar) return;
  bar.style.width = Math.min(100, pct) + '%';
  bar.className = 'bar-fill';
  if (pct > 85) bar.classList.add('crit');
  else if (pct > 65) bar.classList.add('warn');
}

function updateMetrics(datos) {
  const cpu  = datos.cpu  ?? 0;
  const ram  = datos.ram  ?? 0;
  const disk = datos.disco ?? 0;
  const vu   = datos.vram_usado_mb ?? 0;
  const vt   = datos.vram_total_mb ?? VRAM_MAX;
  const vPct = vt ? (vu / vt) * 100 : 0;

  // CPU
  const cpuEl = $('cpu-val');
  if (cpuEl) cpuEl.textContent = `${cpu.toFixed(1)}%`;
  updateBar('cpu', cpu);

  // RAM
  const ramEl = $('ram-val');
  if (ramEl) ramEl.textContent = `${datos.ram_gb ?? '?/?'} GB · ${ram.toFixed(1)}%`;
  updateBar('ram', ram);

  // VRAM
  const vramEl = $('vram-val');
  if (vramEl) vramEl.textContent = vt ? `${vu} / ${vt} MB · ${vPct.toFixed(0)}%` : 'N/A';
  updateBar('vram', vPct);

  // Disco
  const diskEl = $('disk-val');
  if (diskEl) diskEl.textContent = `${disk.toFixed(1)}%`;
  updateBar('disk', disk);

  // Gaming badge
  const gb = $('gaming-badge');
  if (gb) gb.style.display = datos.gaming ? 'block' : 'none';
}

// ── WEBSOCKET ────────────────────────────────────────────────────
function connect() {
  if (reconnectCount >= MAX_RECONNECT) return;
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    reconnectCount = 0;
    setEstado('NOMINAL');
    const wsDot = $('ws-dot');
    if (wsDot) { wsDot.className = 'hud-dot'; }
    const wsLabel = $('ws-label');
    if (wsLabel) wsLabel.textContent = 'CONECTADO';
    $('footer-status').textContent = 'Conectado a MARK 45 Hive Kernel.';
    addLog('WebSocket conectado.');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    fetchEstadoInicial();
  };

  ws.onmessage = ({ data }) => {
    let ev;
    try { ev = JSON.parse(data); } catch { return; }
    const tipo  = ev.tipo  ?? '';
    const datos = ev.datos ?? {};

    switch (tipo) {
      case 'stats':
        updateMetrics(datos);
        break;

      case 'chat':
        addMsg(datos.rol ?? 'mark', datos.texto ?? '');
        break;

      case 'estado_ia':
        setEstado((datos.estado ?? 'NOMINAL').toUpperCase());
        break;

      case 'bienvenida':
        addMsg('mark', datos.mensaje ?? 'MARK 45 conectado.');
        if (datos.llm) {
          const llmEl = $('llm-label');
          if (llmEl) llmEl.textContent = datos.llm;
        }
        addLog(`LLM: ${datos.llm ?? 'N/A'} | Gaming: ${datos.gaming ? 'ON' : 'OFF'}`);
        break;

      case 'alerta':
        addLog(`⚠ ${datos.texto ?? JSON.stringify(datos)}`);
        break;

      case 'ping':
        ws.send(JSON.stringify({ tipo: 'pong' }));
        break;
    }
  };

  ws.onclose = () => {
    setEstado('OFFLINE');
    const wsLabel = $('ws-label');
    if (wsLabel) wsLabel.textContent = 'DESCONECTADO';
    reconnectCount++;
    const delay = Math.min(reconnectCount * 2000, 15000);
    addLog(`Desconectado. Reintento ${reconnectCount} en ${delay/1000}s...`);
    $('footer-status').textContent = `Reconectando... (intento ${reconnectCount})`;
    reconnectTimer = setTimeout(connect, delay);
  };

  ws.onerror = () => addLog('Error de WebSocket.');
}

// ── ENVIAR COMANDO ────────────────────────────────────────────────
function sendCommand() {
  const input = $('cmd-input');
  const texto  = (input?.value || '').trim();
  if (!texto) return;
  input.value = '';
  addMsg('usuario', texto);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ tipo: 'comando', texto }));
    setEstado('PROCESANDO');
  } else {
    // Fallback REST
    setEstado('PROCESANDO');
    fetch(`${API_BASE}/comando`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, fuente: 'web' }),
    })
    .then(r => r.json())
    .then(d => {
      if (d.respuesta) addMsg('mark', d.respuesta);
      setEstado('NOMINAL');
    })
    .catch(e => {
      addLog(`Error REST: ${e}`);
      setEstado('ERROR');
    });
  }
}

// ── ESTADO INICIAL (REST) ─────────────────────────────────────────
async function fetchEstadoInicial() {
  try {
    const r = await fetch(`${API_BASE}/estado`);
    const d = await r.json();
    const llmEl = $('llm-label');
    if (llmEl) llmEl.textContent = d.llm?.provider ?? d.llm?.model ?? 'N/A';
    const userEl = $('user-label');
    if (userEl) userEl.textContent = d.mark?.usuario ?? 'SEÑOR';
    addLog(`MARK 45 v${d.mark?.version ?? '45'} | ${d.mark?.usuario ?? '?'}`);
    if (d.sistema) updateMetrics({
      cpu: d.sistema.cpu, ram: d.sistema.ram, disco: d.sistema.disco,
      ram_gb: d.sistema.ram_gb, vram_usado_mb: 0, vram_total_mb: VRAM_MAX,
      gaming: d.sistema.gaming,
    });
  } catch(e) {
    addLog(`Estado inicial: sin conexión REST (${e.message})`);
  }
}

// ── UI EVENTS ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const sendBtn = $('send-btn');
  const cmdInput = $('cmd-input');

  sendBtn?.addEventListener('click', sendCommand);
  cmdInput?.addEventListener('keydown', e => { if (e.key === 'Enter') sendCommand(); });

  // Iniciar conexión
  connect();
  setEstado('OFFLINE');   // inicial hasta que WS conecte
});
