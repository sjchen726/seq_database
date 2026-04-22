(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var btn = form.querySelector('button[type=submit], input[type=submit]');
    if (!btn) return;
    if (btn.classList.contains('ds-btn-loading')) { e.preventDefault(); return; }
    btn.classList.add('ds-btn-loading');
    btn.disabled = true;
    btn._originalText = btn.textContent;
    btn.textContent = '处理中…';
  });

  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      document.querySelectorAll('.ds-btn-loading').forEach(function (btn) {
        btn.classList.remove('ds-btn-loading');
        btn.disabled = false;
        if (btn._originalText) { btn.textContent = btn._originalText; }
      });
    }
  });
})();
