// Подсветка активной вкладки по URL
(function () {
  var path = location.pathname.replace(/\/$/, '') || '/';
  if (path === '/index.html') path = '/';
  document.querySelectorAll('.panel-tabs .tab').forEach(function (a) {
    var href = (a.getAttribute('href') || '/').replace(/\/$/, '') || '/';
    if (path === href) a.classList.add('active');
  });
})();
