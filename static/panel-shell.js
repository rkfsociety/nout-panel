/* Общий header и footer на всех страницах */
(function () {
  var HEADER_HTML =
    '<header class="site-header" id="panel-site-header">' +
    '<div class="metrics-bar">' +
    '<div class="metrics-row">' +
    '<div class="metrics-brand">' +
    '<h1 id="host-title">Nout Panel</h1>' +
    '<span class="badge" id="status">…</span>' +
    '<span class="metrics-time" id="updated">—</span>' +
    '</div>' +
    '<div class="stat-row">' +
    '<div class="stat-chip"><span class="stat-lbl">CPU</span>' +
    '<span class="stat-val" id="cpu-val">—</span>' +
    '<div class="bar mini"><div class="bar-fill" id="cpu-bar" style="width:0%"></div></div></div>' +
    '<div class="stat-chip"><span class="stat-lbl">ОЗУ</span>' +
    '<span class="stat-val" id="ram-val">—</span>' +
    '<div class="bar mini"><div class="bar-fill" id="ram-bar" style="width:0%"></div></div></div>' +
    '<div class="stat-chip"><span class="stat-lbl">Ld</span>' +
    '<span class="stat-val" id="load-val">—</span>' +
    '<div class="bar mini"><div class="bar-fill" id="load-bar" style="width:0%"></div></div></div>' +
    '</div>' +
    '<div class="metrics-tail">' +
    '<div id="temps" class="temps-inline"></div>' +
    '<div id="disks" class="disks-row">…</div>' +
    '<p class="panel-meta" id="panel-process" hidden></p>' +
    '</div></div></div></header>';

  var FOOTER_HTML =
    '<footer class="site-footer" id="panel-site-footer">' +
    '<span>Nout Panel</span>' +
    '<span class="site-footer-sep">·</span>' +
    '<span id="footer-version">—</span>' +
    '<span class="site-footer-sep">·</span>' +
    '<a href="/">Главная</a>' +
    '<span class="site-footer-sep">·</span>' +
    '<a href="/chat">Чат</a>' +
    '<span class="site-footer-sep">·</span>' +
    '<a href="/settings">Настройки</a>' +
    '</footer>';

  var body = document.body;
  if (!body) return;

  body.classList.add('page-shell');

  if (!document.getElementById('panel-site-header')) {
    var panelBody = document.querySelector('.panel-body');
    if (panelBody) {
      panelBody.insertAdjacentHTML('beforebegin', HEADER_HTML);
    } else {
      body.insertAdjacentHTML('afterbegin', HEADER_HTML);
    }
  }

  if (!document.getElementById('panel-site-footer')) {
    var firstScript = body.querySelector('script');
    if (firstScript) {
      firstScript.insertAdjacentHTML('beforebegin', FOOTER_HTML);
    } else {
      body.insertAdjacentHTML('beforeend', FOOTER_HTML);
    }
  }

  var pageTitle = body.getAttribute('data-page-title');
  if (pageTitle) {
    document.title = pageTitle + ' — Nout Panel';
  }

  fetch('/api/status', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var el = document.getElementById('footer-version');
      if (!el || !d) return;
      var v = d.panel_version;
      el.textContent = v ? 'v' + v : 'LAN';
    })
    .catch(function () {});
})();
