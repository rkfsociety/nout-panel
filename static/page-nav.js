/* Подсветка текущей страницы в навигации */
(function () {
  var path = location.pathname.replace(/\/$/, '') || '/';
  if (path === '/index.html') path = '/';
  document.querySelectorAll('.page-nav a[data-page]').forEach(function (a) {
    var href = (a.getAttribute('href') || '/').replace(/\/$/, '') || '/';
    if (path === href) a.setAttribute('aria-current', 'page');
  });
})();
