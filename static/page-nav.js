/* Блоки навигации и подсветка текущей страницы */
(function () {
  var ITEMS = [
    { href: '/', mod: 'monitor', title: 'Главная', desc: 'Метрики и управление' },
    { href: '/chat', mod: 'chat', title: 'Чат', desc: 'Cursor Agent' },
    { href: '/settings', mod: 'settings', title: 'Настройки', desc: 'Конфиг и логи' },
  ];

  function normPath(p) {
    var path = (p || '/').replace(/\/$/, '') || '/';
    if (path === '/index.html') path = '/';
    return path;
  }

  var current = normPath(location.pathname);
  // /remote — старый URL, подсвечиваем главную
  if (current === '/remote') current = '/';

  document.querySelectorAll('[data-nav-mount]').forEach(function (mount) {
    mount.setAttribute('aria-label', 'Разделы');
    mount.classList.add('side-nav');
    ITEMS.forEach(function (item) {
      var a = document.createElement('a');
      a.href = item.href;
      a.className = 'nav-block nav-block--' + item.mod;
      a.setAttribute('data-page', '');
      if (normPath(item.href) === current) {
        a.setAttribute('aria-current', 'page');
      }
      a.innerHTML =
        '<span class="nav-block-bar"></span>' +
        '<span class="nav-block-title"></span>' +
        '<span class="nav-block-desc"></span>';
      a.querySelector('.nav-block-title').textContent = item.title;
      a.querySelector('.nav-block-desc').textContent = item.desc;
      mount.appendChild(a);
    });
  });
})();
