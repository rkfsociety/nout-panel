/* Чат Cursor Agent — колонка справа на главной */
(function () {
  const messagesEl = document.getElementById('chat-messages');
  if (!messagesEl) return;

  const inputEl = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const banner = document.getElementById('chat-banner');
  let sessionId = localStorage.getItem('nout_chat_session') || '';
  let busy = false;

  function addMsg(text, role) {
    const d = document.createElement('div');
    d.className = 'chat-msg ' + role;
    d.textContent = text;
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return d;
  }

  async function api(method, url, body) {
    const opt = { method, cache: 'no-store' };
    if (body) {
      opt.headers = { 'Content-Type': 'application/json' };
      opt.body = JSON.stringify(body);
    }
    return (await fetch(url, opt)).json();
  }

  async function checkStatus() {
    const s = await api('GET', '/api/chat/status');
    const hint = document.getElementById('chat-workspace');
    if (s.workspace) hint.textContent = s.workspace;
    if (!s.available) {
      banner.hidden = false;
      banner.textContent = s.hint || 'cursor agent login на ноуте';
      sendBtn.disabled = true;
      return false;
    }
    banner.hidden = true;
    sendBtn.disabled = false;
    return true;
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    const d = await api('POST', '/api/chat/session', { title: 'Панель' });
    if (!d.ok) throw new Error(d.error || 'session');
    sessionId = d.session_id;
    localStorage.setItem('nout_chat_session', sessionId);
    return sessionId;
  }

  async function pollJob(jobId, botEl) {
    let offset = 0;
    let acc = '';
    while (true) {
      const p = await api('GET', '/api/chat/poll?job=' + encodeURIComponent(jobId) + '&offset=' + offset);
      if (!p.ok) break;
      if (p.chunk) {
        acc += p.chunk;
        botEl.textContent = acc;
        botEl.classList.remove('thinking');
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      offset = p.offset;
      if (p.done) {
        if (p.error && !acc.trim()) botEl.textContent = 'Ошибка: ' + p.error;
        break;
      }
      await new Promise(r => setTimeout(r, 400));
    }
  }

  async function send() {
    const text = inputEl.value.trim();
    if (!text || busy) return;
    if (!(await checkStatus())) return;
    busy = true;
    sendBtn.disabled = true;
    inputEl.value = '';
    addMsg(text, 'user');
    const botEl = addMsg('Думаю…', 'bot thinking');
    try {
      await ensureSession();
      const d = await api('POST', '/api/chat/send', { session_id: sessionId, message: text });
      if (!d.ok) throw new Error(d.error || 'send');
      await pollJob(d.job_id, botEl);
    } catch (e) {
      botEl.textContent = 'Ошибка: ' + e.message;
      botEl.classList.remove('thinking');
    }
    busy = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }

  sendBtn.onclick = send;
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  addMsg('Задачи для Cursor Agent на ноуте — файлы, команды, код.', 'bot');
  checkStatus();
})();
