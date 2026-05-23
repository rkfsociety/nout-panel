/* Настройки, логи и перезапуск — блок на главной странице */
(function () {
  const form = document.getElementById('cfg-form');
  if (!form) return;

  const toast = document.getElementById('toast');
  function showToast(msg, isErr) {
    if (!toast) return;
    toast.textContent = msg;
    toast.style.display = 'block';
    toast.style.color = isErr ? '#f0a8a8' : '#3ecf8e';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { toast.style.display = 'none'; }, 4000);
  }

  function collectValues() {
    const keys = [
      'PANEL_PORT', 'PANEL_METRICS_INTERVAL', 'PANEL_LOG_FILE',
      'PANEL_LOG_MAX_MB', 'PANEL_LOG_BACKUP_COUNT', 'PANEL_FILE_ROOTS',
      'PANEL_AGENT_WORKSPACE', 'PANEL_CHAT_DIR',
    ];
    const values = {};
    keys.forEach(k => {
      const el = document.getElementById('f-' + k);
      if (el) values[k] = el.value;
    });
    return values;
  }

  async function loadInfo() {
    const line = document.getElementById('info-line');
    if (!line) return;
    const r = await fetch('/api/panel/info', { cache: 'no-store' });
    const d = await r.json();
    if (!d.ok) {
      line.textContent = d.error || 'Ошибка';
      line.className = 'status-line err';
      return;
    }
    const st = d.service_active ? 'работает' : d.service_state;
    line.textContent = 'Версия ' + d.version + ' · сервис ' + st;
    line.className = 'status-line ok';
  }

  async function loadAgent() {
    const el = document.getElementById('agent-line');
    if (!el) return;
    try {
      const r = await fetch('/api/chat/status', { cache: 'no-store' });
      const d = await r.json();
      if (d.available) {
        el.textContent = 'Cursor Agent: доступен';
        el.className = 'status-line ok';
      } else {
        el.textContent = 'Cursor Agent: ' + (d.hint || 'недоступен');
        el.className = 'status-line err';
      }
    } catch (_) {
      el.textContent = '';
    }
  }

  async function loadSudoStatus() {
    const line = document.getElementById('sudo-line');
    if (!line) return;
    try {
      const r = await fetch('/api/panel/sudo', { cache: 'no-store' });
      const d = await r.json();
      if (d.configured) {
        const where = d.path ? ' (' + d.path + ')' : '';
        line.textContent = 'Пароль sudo сохранён локально' + where;
        line.className = 'status-line ok';
      } else {
        line.textContent = 'Пароль не задан — перезапуск и «Сохранить и применить» могут не сработать';
        line.className = 'status-line';
      }
    } catch (_) {
      line.textContent = '—';
    }
  }

  async function saveSudoPassword(clear) {
    const input = document.getElementById('sudo-password');
    const pwd = clear ? '' : (input && input.value) || '';
    const r = await fetch('/api/panel/sudo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd }),
    });
    const d = await r.json();
    if (!d.ok) {
      showToast(d.error || 'Ошибка', true);
      return;
    }
    if (input && clear) input.value = '';
    showToast(d.message || 'Готово');
    loadSudoStatus();
  }

  async function loadConfig() {
    const r = await fetch('/api/panel/config', { cache: 'no-store' });
    const d = await r.json();
    if (!d.ok) {
      showToast(d.error || 'Не удалось загрузить конфиг', true);
      return;
    }
    Object.entries(d.readonly || {}).forEach(([k, v]) => {
      const el = document.getElementById('f-' + k);
      if (el) el.value = v;
    });
    Object.entries(d.values || {}).forEach(([k, v]) => {
      const el = document.getElementById('f-' + k);
      if (el) el.value = v;
    });
  }

  function waitForOnline() {
    if (window.noutPanelWaitOnline) {
      window.noutPanelWaitOnline(function () {
        loadInfo();
        loadConfig();
        loadLogs();
      });
      return;
    }
    showToast('Панель перезапускается…', false);
    location.reload();
  }

  async function saveConfig(apply) {
    const r = await fetch('/api/panel/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ values: collectValues(), apply }),
    });
    const d = await r.json();
    if (!d.ok) {
      showToast(d.error || 'Ошибка сохранения', true);
      return false;
    }
    showToast(d.message || 'Сохранено');
    if (d.applied) waitForOnline();
    return true;
  }

  async function loadLogs() {
    const box = document.getElementById('log-box');
    if (!box) return;
    try {
      const r = await fetch('/api/panel/logs?lines=200', { cache: 'no-store' });
      const d = await r.json();
      if (!d.ok) {
        box.textContent = d.error || 'Ошибка';
        return;
      }
      box.textContent = d.text || '(пусто)';
      box.scrollTop = box.scrollHeight;
    } catch (_) {
      box.textContent = 'Нет связи';
    }
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    saveConfig(true);
  });
  document.getElementById('btn-save-only').addEventListener('click', () => saveConfig(false));
  document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);
  document.getElementById('btn-sudo-save').addEventListener('click', () => saveSudoPassword(false));
  document.getElementById('btn-sudo-clear').addEventListener('click', () => saveSudoPassword(true));
  setInterval(() => {
    if (document.getElementById('log-auto').checked) loadLogs();
  }, 3000);

  loadInfo();
  loadAgent();
  loadSudoStatus();
  loadConfig();
  loadLogs();
})();
