/* compound_list.js — expand/collapse, tabs, charts, file preview */

// ── Row expand / collapse ─────────────────────────────────────
function clToggleRow(rowId, panelId) {
  const row = document.getElementById(rowId);
  const panel = document.getElementById(panelId);
  if (!row || !panel) return;

  const isOpen = row.classList.contains('open');
  row.classList.toggle('open', !isOpen);
  panel.classList.toggle('show', !isOpen);

  if (!isOpen) {
    // Initialize charts on first open (panel must be visible for canvas sizing)
    clInitChartsInPanel(panel);
  }
}

// ── Readout tabs ──────────────────────────────────────────────
function clSwitchTab(btn, tabGroupId, readout) {
  const group = document.getElementById(tabGroupId);
  if (!group) return;

  // Update button states
  group.querySelectorAll('.cl-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  // Show / hide tab content panes
  let activePane = null;
  group.querySelectorAll('.cl-tab-pane').forEach(pane => {
    if (pane.dataset.readout === readout) {
      pane.style.display = '';
      activePane = pane;
    } else {
      pane.style.display = 'none';
    }
  });

  // Initialize charts in the newly visible pane (canvas was zero-width when hidden)
  if (activePane) {
    clInitChartsInPanel(activePane);
  }
}

// ── Chart.js initialization ───────────────────────────────────
const _clChartInstances = {};

function clInitChartsInPanel(panel) {
  panel.querySelectorAll('canvas[data-chart]').forEach(canvas => {
    if (_clChartInstances[canvas.id]) return; // already initialized

    const type = canvas.dataset.chart;
    if (type === 'vitro') {
      _clInitVitroChart(canvas);
    } else if (type === 'vivo') {
      _clInitVivoChart(canvas);
    }
  });
}

function _clInitVitroChart(canvas) {
  const mrna = JSON.parse(canvas.dataset.mrna || '[]');
  const datasets = [
    {
      label: 'mRNA残余%',
      data: mrna.map(([x, y]) => ({ x, y })),
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,.08)',
      tension: 0.3,
      pointRadius: 3,
    },
  ];
  _clChartInstances[canvas.id] = new Chart(canvas, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'log₁₀(nM)', font: { size: 9 } },
          ticks: { font: { size: 9 } },
        },
        y: {
          min: 0, max: 110,
          title: { display: true, text: 'mRNA%', font: { size: 9 } },
          ticks: { font: { size: 9 } },
        },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function _clInitVivoChart(canvas) {
  const days    = JSON.parse(canvas.dataset.days    || '[]');
  const groups  = JSON.parse(canvas.dataset.groups  || '[]');
  const control = JSON.parse(canvas.dataset.control || 'null');

  const COLORS = ['#ef4444','#f97316','#eab308','#22c55e','#3b82f6','#8b5cf6'];
  const datasets = [];

  if (control) {
    datasets.push({
      label: control.label,
      data: days.map((d, i) => ({ x: d, y: control.data[i] })).filter(p => p.y != null),
      borderColor: '#94a3b8',
      borderDash: [4, 3],
      backgroundColor: 'transparent',
      tension: 0.2,
      pointRadius: 2,
    });
  }

  groups.forEach((g, idx) => {
    datasets.push({
      label: g.label,
      data: days.map((d, i) => ({ x: d, y: g.data[i] })).filter(p => p.y != null),
      borderColor: COLORS[idx % COLORS.length],
      backgroundColor: 'transparent',
      tension: 0.2,
      pointRadius: 2,
    });
  });

  _clChartInstances[canvas.id] = new Chart(canvas, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Day', font: { size: 9 } },
          ticks: { font: { size: 9 }, maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: '%', font: { size: 9 } },
          ticks: { font: { size: 9 } },
        },
      },
      plugins: {
        legend: {
          display: true,
          labels: { font: { size: 9 }, boxWidth: 12, padding: 8 },
        },
      },
    },
  });
}

// ── Inline file preview ───────────────────────────────────────
function clTogglePreview(btnEl, wrapId, attachPk) {
  const wrap = document.getElementById(wrapId);
  if (!wrap) return;

  const isShown = wrap.classList.contains('show');
  if (isShown) {
    wrap.classList.remove('show');
    btnEl.textContent = '👁 预览';
    return;
  }

  // If already loaded, just show
  if (wrap.dataset.loaded) {
    wrap.classList.add('show');
    btnEl.textContent = '收起';
    return;
  }

  btnEl.textContent = '加载中…';
  fetch(`/attachments/${attachPk}/preview/`)
    .then(r => r.json())
    .then(data => {
      if (data.headers && data.headers.length) {
        let html = '<table class="cl-preview-tbl"><thead><tr>';
        data.headers.forEach(h => { html += `<th>${_clEsc(h)}</th>`; });
        html += '</tr></thead><tbody>';
        data.rows.forEach(row => {
          html += '<tr>';
          row.forEach(cell => { html += `<td>${_clEsc(String(cell))}</td>`; });
          html += '</tr>';
        });
        html += '</tbody></table>';
        wrap.innerHTML = html;
      } else {
        wrap.innerHTML = '<p style="padding:8px;color:#94a3b8;">无法预览此文件</p>';
      }
      wrap.dataset.loaded = '1';
      wrap.classList.add('show');
      btnEl.textContent = '收起';
    })
    .catch(() => {
      wrap.innerHTML = '<p style="padding:8px;color:#ef4444;">加载失败</p>';
      wrap.classList.add('show');
      btnEl.textContent = '收起';
    });
}

function _clEsc(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Vitro mRNA% / KD% toggle ─────────────────────────────────
function clToggleVitroReadout(btn, chartId, readout) {
  const chart = _clChartInstances[chartId];
  if (!chart) return;
  btn.closest('.cl-vitro-toggle').querySelectorAll('.cl-vtoggle-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const canvas = document.getElementById(chartId);
  const mrna = JSON.parse(canvas.dataset.mrna || '[]');
  const kd   = JSON.parse(canvas.dataset.kd   || '[]');
  const pts  = readout === 'kd' ? kd : mrna;
  chart.data.datasets[0].data  = pts.map(([x, y]) => ({ x, y }));
  chart.data.datasets[0].label = readout === 'kd' ? 'KD%' : 'mRNA残余%';
  chart.options.scales.y.title.text = readout === 'kd' ? 'KD%' : 'mRNA%';
  chart.update();
}
