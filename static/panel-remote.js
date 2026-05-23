/* Управление: терминал, файлы, питание, экран (главная страница) */
(function () {
  const termWrap = document.getElementById('terminal-wrap');
  if (!termWrap || typeof Terminal === 'undefined') return;

  async function apiGet(url) {
    const r = await fetch(url, { cache: 'no-store' });
    const ct = r.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) return { json: await r.json(), blob: null, ok: r.ok };
    return { json: null, blob: await r.blob(), ok: r.ok };
  }
  async function apiPost(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return r.json();
  }

  let termSession = null;
  let pollOffset = 0;
  let pollTimer = null;
  const term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: 'ui-monospace, "Cascadia Mono", "DejaVu Sans Mono", monospace',
    theme: { background: '#000000', foreground: '#e8edf4', cursor: '#4da3ff' },
  });
  term.open(termWrap);

  function b64enc(bytes) {
    let s = '';
    bytes.forEach(b => { s += String.fromCharCode(b); });
    return btoa(s);
  }
  function b64dec(str) {
    const bin = atob(str);
    const u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return u8;
  }

  async function startTerminal() {
    if (termSession) await apiPost('/api/terminal/close', { session: termSession });
    pollOffset = 0;
    const d = await apiPost('/api/terminal/session', {});
    if (!d.ok) { term.writeln('\r\nОшибка сессии'); return; }
    termSession = d.session;
    term.reset();
    term.writeln('Подключено (' + termSession + ')');
    fitTerm();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollTerminal, 120);
  }

  function fitTerm() {
    if (termSession) apiPost('/api/terminal/resize', { session: termSession, cols: term.cols, rows: term.rows });
  }

  async function pollTerminal() {
    if (!termSession) return;
    try {
      const r = await fetch(
        '/api/terminal/poll?session=' + encodeURIComponent(termSession) + '&offset=' + pollOffset,
        { cache: 'no-store' }
      );
      const d = await r.json();
      if (!d.ok) return;
      pollOffset = d.offset;
      if (d.data) term.write(b64dec(d.data));
    } catch (_) { /* повтор */ }
  }

  term.onData(data => {
    if (!termSession) return;
    apiPost('/api/terminal/write', { session: termSession, data: b64enc(new TextEncoder().encode(data)) });
  });
  window.addEventListener('resize', () => { term.focus(); fitTerm(); });
  document.getElementById('term-new').addEventListener('click', startTerminal);
  startTerminal();

  let currentPath = null;

  async function loadFiles(path) {
    const url = path ? '/api/files/list?path=' + encodeURIComponent(path) : '/api/files/list';
    const { json: d } = await apiGet(url);
    const list = document.getElementById('file-list');
    const pathEl = document.getElementById('file-path');
    if (!d.ok) {
      pathEl.textContent = d.error || 'Ошибка';
      list.innerHTML = '';
      return;
    }
    if (!path && d.roots) {
      pathEl.textContent = 'Корни: ' + d.roots.map(r => r.label).join(', ');
      list.innerHTML = d.roots.map(r =>
        `<li><a href="#" data-path="${encodeURIComponent(r.path)}">📁 ${r.label}</a></li>`
      ).join('');
      bindFileLinks();
      currentPath = null;
      return;
    }
    currentPath = d.path;
    pathEl.textContent = d.path;
    let html = '';
    if (d.parent) {
      html += `<li><a href="#" data-path="${encodeURIComponent(d.parent)}">📁 ..</a></li>`;
    }
    d.entries.forEach(e => {
      const icon = e.dir ? '📁' : '📄';
      html += `<li>
        <a href="#" data-path="${encodeURIComponent(e.path)}" data-dir="${e.dir}">${icon} ${e.name}</a>
        ${e.dir ? '' : `<button type="button" class="btn-ctl" data-dl="${encodeURIComponent(e.path)}">↓</button>
          <button type="button" class="btn-ctl danger" data-del="${encodeURIComponent(e.path)}">✕</button>`}
      </li>`;
    });
    list.innerHTML = html || '<li class="muted-li">Пусто</li>';
    bindFileLinks();
  }

  function bindFileLinks() {
    document.querySelectorAll('#file-list a[data-path]').forEach(a => {
      a.onclick = ev => {
        ev.preventDefault();
        const p = decodeURIComponent(a.dataset.path);
        if (a.dataset.dir === 'true' || a.textContent.includes('📁')) loadFiles(p);
      };
    });
    document.querySelectorAll('[data-dl]').forEach(btn => {
      btn.onclick = () => window.open('/api/files/download?path=' + btn.dataset.dl, '_blank');
    });
    document.querySelectorAll('[data-del]').forEach(btn => {
      btn.onclick = async () => {
        const p = decodeURIComponent(btn.dataset.del);
        if (!confirm('Удалить?\n' + p)) return;
        const d = await apiPost('/api/files/delete', { path: p });
        if (d.ok) loadFiles(currentPath);
        else alert(d.error || 'Ошибка');
      };
    });
  }

  document.getElementById('file-up').onclick = () => {
    if (!currentPath) return;
    loadFiles(currentPath.replace(/\/[^/]+$/, '') || null);
  };
  document.getElementById('file-refresh').onclick = () => loadFiles(currentPath);
  document.getElementById('file-input').onchange = async ev => {
    const file = ev.target.files[0];
    if (!file || !currentPath) { alert('Откройте каталог'); return; }
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/files/upload?path=' + encodeURIComponent(currentPath), { method: 'POST', body: fd });
    const d = await r.json();
    if (d.ok) loadFiles(currentPath);
    else alert(d.error || 'Ошибка');
    ev.target.value = '';
  };
  loadFiles(null);

  document.querySelectorAll('[data-power]').forEach(btn => {
    btn.onclick = async () => {
      const action = btn.dataset.power;
      const word = btn.dataset.confirm;
      const labels = { suspend: 'спящий режим', reboot: 'перезагрузку', shutdown: 'выключение' };
      if (!confirm('Подтвердите ' + labels[action] + '.\n\nВведите: ' + word)) return;
      const typed = prompt('Введите ' + word + ':');
      if (typed !== word) return;
      const d = await apiPost('/api/power', { action, confirm: word });
      if (!d.ok) alert(d.error || 'Не удалось');
    };
  });

  async function loadScreenInfo() {
    const { json: d } = await apiGet('/api/screen/info');
    document.getElementById('screen-hint').textContent = d.available
      ? 'Доступно: ' + (d.tools || []).join(', ')
      : (d.hint || 'N/A');
  }
  document.getElementById('screen-shot').onclick = async () => {
    const img = document.getElementById('screen-img');
    const { blob, ok } = await apiGet('/api/screen/capture?' + Date.now());
    if (!ok) { alert('Скриншот недоступен'); return; }
    img.src = URL.createObjectURL(blob);
    img.hidden = false;
  };
  loadScreenInfo();
})();
