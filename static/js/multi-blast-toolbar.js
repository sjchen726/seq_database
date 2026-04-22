(function () {
  var btn = document.getElementById('multiBlastBtn');
  if (!btn) return;

  function updateBtn() {
    btn.disabled = document.querySelectorAll('input.row-checkbox:checked').length === 0;
  }

  document.addEventListener('change', function (e) {
    if (e.target.matches('input.row-checkbox') || e.target.id === 'select-all') {
      updateBtn();
    }
  });

  btn.addEventListener('click', function () {
    var checked = document.querySelectorAll('input.row-checkbox:checked');
    if (!checked.length) return;

    var form = document.createElement('form');
    form.method = 'POST';
    form.action = btn.dataset.url;

    var csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = 'csrfmiddlewaretoken';
    var csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
    if (!csrfMatch) return;
    csrf.value = csrfMatch[1];
    form.appendChild(csrf);

    Array.prototype.forEach.call(checked, function (cb) {
      var row = cb.closest('tr');
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'seq_id';
      input.value = row.dataset.rmCode;
      form.appendChild(input);
    });

    document.body.appendChild(form);
    form.submit();
  });
})();
