/* Перезапуск панели — кнопка в header на всех страницах */
(function () {
  function showToast(msg, isErr) {
    var toast = document.getElementById('panel-toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.hidden = false;
    toast.className = 'panel-toast' + (isErr ? ' err' : '');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
      toast.hidden = true;
    }, 4000);
  }

  function waitForOnline(done) {
    showToast('Панель перезапускается…');
    var n = 0;
    function tick() {
      fetch('/api/status', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) {
            showToast('Панель снова в сети');
            if (typeof done === 'function') done();
            else location.reload();
          } else {
            throw new Error();
          }
        })
        .catch(function () {
          n++;
          if (n < 45) setTimeout(tick, 1000);
          else showToast('Панель не ответила', true);
        });
    }
    setTimeout(tick, 1500);
  }

  window.noutPanelWaitOnline = waitForOnline;

  var btn = document.getElementById('btn-panel-restart');
  if (!btn) return;

  btn.addEventListener('click', async function () {
    if (!confirm('Перезапустить панель?')) return;
    btn.disabled = true;
    try {
      var r = await fetch('/api/panel/restart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: 'RESTART_PANEL' }),
      });
      var d = await r.json();
      if (!d.ok) {
        showToast(d.error || 'Ошибка', true);
        btn.disabled = false;
        return;
      }
    } catch (_) {
      showToast('Ошибка запроса', true);
      btn.disabled = false;
      return;
    }
    waitForOnline(function () {
      btn.disabled = false;
      location.reload();
    });
  });
})();
