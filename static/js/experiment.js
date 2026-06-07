(function () {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.exp-accordion-btn');
    if (!btn) return;
    var row = btn.closest('.exp-list-row');
    if (!row) return;
    var body = row.querySelector('.exp-accordion-body');
    if (!body) return;

    var isOpen = body.style.display === 'block';
    body.style.display = isOpen ? 'none' : 'block';
    btn.textContent = isOpen ? '展开 ▼' : '收起 ▲';
  });
})();
