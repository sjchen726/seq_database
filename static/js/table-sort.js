(function () {
  document.querySelectorAll('table').forEach(function (table) {
    var headers = table.querySelectorAll('th.ds-th-sort');
    if (!headers.length) return;
    var state = { col: -1, dir: 'asc' };

    headers.forEach(function (th) {
      var icon = document.createElement('span');
      icon.className = 'ds-sort-icon';
      icon.textContent = '↕';
      th.appendChild(icon);

      th.addEventListener('click', function () {
        var colIdx = Array.from(th.parentNode.children).indexOf(th);
        var newDir = (state.col === colIdx && state.dir === 'asc') ? 'desc' : 'asc';

        headers.forEach(function (h) {
          h.classList.remove('ds-sort-asc', 'ds-sort-desc');
          h.querySelector('.ds-sort-icon').textContent = '↕';
        });

        th.classList.add(newDir === 'asc' ? 'ds-sort-asc' : 'ds-sort-desc');
        th.querySelector('.ds-sort-icon').textContent = newDir === 'asc' ? '↑' : '↓';
        state = { col: colIdx, dir: newDir };

        var tbody = table.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function (a, b) {
          var av = (a.cells[colIdx] ? a.cells[colIdx].textContent : '').trim();
          var bv = (b.cells[colIdx] ? b.cells[colIdx].textContent : '').trim();
          var an = parseFloat(av), bn = parseFloat(bv);
          if (!isNaN(an) && !isNaN(bn)) return newDir === 'asc' ? an - bn : bn - an;
          return newDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
