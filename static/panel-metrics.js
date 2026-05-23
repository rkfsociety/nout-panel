/* Обновление метрик в общем header */
(function () {
  if (!document.getElementById('host-title')) return;

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function barClass(pct) {
    if (pct >= 90) return 'danger';
    if (pct >= 75) return 'warn';
    return '';
  }

  function setBar(id, pct) {
    var el = document.getElementById(id);
    if (!el) return;
    if (pct == null || isNaN(pct)) {
      el.style.width = '0%';
      el.className = 'bar-fill';
      return;
    }
    var v = Math.min(100, Math.max(0, pct));
    el.style.width = v + '%';
    el.className = 'bar-fill ' + barClass(v);
  }

  function renderDisks(disks) {
    var root = document.getElementById('disks');
    if (!root) return;
    if (!disks || !disks.length) {
      root.innerHTML = '<span class="na">Диски: —</span>';
      return;
    }
    root.innerHTML = disks.map(function (d) {
      return (
        '<div class="disk-chip" title="' + esc(d.device) + ' · ' + d.free_gb + ' ГБ свободно">' +
        '<span class="disk-name">' + esc(d.mount) + '</span>' +
        '<span class="disk-pct">' + d.percent + '%</span>' +
        '<div class="bar mini"><div class="bar-fill ' + barClass(d.percent) +
        '" style="width:' + d.percent + '%"></div></div></div>'
      );
    }).join('');
  }

  function renderTemps(block) {
    var root = document.getElementById('temps');
    if (!root) return;
    var sensors = block && block.available && block.sensors ? block.sensors : [];
    root.innerHTML = sensors.map(function (t) {
      return '<span class="t">' + esc(t.name) + ' ' + esc(t.celsius) + '°</span>';
    }).join('');
  }

  function formatUptime(sec) {
    if (sec == null || sec < 0) return '—';
    if (sec >= 86400) {
      return Math.floor(sec / 86400) + ' д ' + Math.floor((sec % 86400) / 3600) + ' ч';
    }
    if (sec >= 3600) {
      return Math.floor(sec / 3600) + ' ч ' + Math.floor((sec % 3600) / 60) + ' м';
    }
    if (sec >= 60) return Math.floor(sec / 60) + ' м';
    return Math.round(sec) + ' с';
  }

  function renderPanel(p) {
    var el = document.getElementById('panel-process');
    if (!el) return;
    if (!p || !p.available) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    var ram = p.rss_mb != null ? p.rss_mb + ' МБ RAM' : 'RAM —';
    var thr = p.threads != null ? ' · ' + p.threads + ' поток.' : '';
    el.textContent = 'Панель: PID ' + p.pid + ' · ' + ram + thr + ' · uptime ' + formatUptime(p.uptime_sec);
  }

  var hostname = 'Nout Panel';
  var pageSuffix = document.body.getAttribute('data-page-title') || 'Nout Panel';

  function setDocumentTitle() {
    document.title = hostname + ' — ' + pageSuffix;
  }

  async function loadHost() {
    try {
      var r = await fetch('/api/status', { cache: 'no-store' });
      var d = await r.json();
      if (d.hostname) {
        hostname = d.hostname;
        var ht = document.getElementById('host-title');
        if (ht) ht.textContent = hostname;
        setDocumentTitle();
      }
    } catch (_) { /* повторим позже */ }
  }

  async function tick() {
    try {
      var r = await fetch('/api/metrics', { cache: 'no-store' });
      var d = await r.json();
      if (!d.ok) throw new Error(d.error || 'API error');

      var status = document.getElementById('status');
      if (status) {
        status.textContent = hostname;
        status.className = 'badge';
      }

      var cpu = d.cpu_percent != null ? d.cpu_percent : 0;
      var mem = d.memory || {};
      var ld = d.load || {};
      var ram = mem.ram_percent;
      var loadPct = ld.load_percent;

      var cpuVal = document.getElementById('cpu-val');
      if (cpuVal) cpuVal.textContent = cpu + '%';

      if (mem.available === false || ram == null) {
        var rv = document.getElementById('ram-val');
        if (rv) rv.textContent = '—';
        setBar('ram-bar', null);
      } else {
        var rv2 = document.getElementById('ram-val');
        if (rv2) rv2.textContent = ram + '%';
        setBar('ram-bar', ram);
      }

      if (ld.load_1 == null || loadPct == null) {
        var lv = document.getElementById('load-val');
        if (lv) lv.textContent = '—';
        setBar('load-bar', null);
      } else {
        var lv2 = document.getElementById('load-val');
        if (lv2) lv2.textContent = loadPct + '%';
        setBar('load-bar', Math.min(100, loadPct));
      }

      setBar('cpu-bar', cpu);
      renderDisks(d.disks);
      renderTemps(d.temperatures);
      renderPanel(d.panel);

      var updated = document.getElementById('updated');
      if (updated) {
        var t = new Date(d.time_utc);
        updated.textContent = t.toLocaleTimeString('ru-RU', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
      }
    } catch (e) {
      var st = document.getElementById('status');
      if (st) {
        st.textContent = 'Нет связи';
        st.className = 'badge offline';
      }
    }
  }

  loadHost();
  tick();
  setInterval(tick, 1000);
  setInterval(loadHost, 30000);
})();
