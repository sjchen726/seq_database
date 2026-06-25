/* compound_list.js — expand/collapse, tabs, charts, file preview */

// Move floating elements (bar, overlay, modal) to <body> so they
// are never clipped by ancestor overflow:hidden containers.
document.addEventListener('DOMContentLoaded', () => {
  ['cl-cmp-bar', 'cl-cmp-overlay', 'cl-cmp-modal'].forEach(id => {
    const el = document.getElementById(id);
    if (el) document.body.appendChild(el);
  });
});

// ── Row expand / collapse ─────────────────────────────────────
function clToggleRow(rowId, panelId) {
  const row = document.getElementById(rowId);
  const panel = document.getElementById(panelId);
  if (!row || !panel) return;

  const isOpen = row.classList.contains('open');
  row.classList.toggle('open', !isOpen);
  panel.classList.toggle('show', !isOpen);

  if (!isOpen) {
    clInitChartsInPanel(panel);
    // Scroll the expand panel into view so the user sees the content
    setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80);
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
          min: 0,
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
          grid: {
            color: (ctx) => ctx.tick.value === 0 ? '#94a3b8' : '#e2e8f0',
            lineWidth: (ctx) => ctx.tick.value === 0 ? 1.5 : 1,
          },
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
        let html = '';
        if (data.note) {
          html += `<p class="cl-preview-note">${_clEsc(data.note)}</p>`;
        }
        html += '<table class="cl-preview-tbl"><thead><tr>';
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

// ── Compound comparison ───────────────────────────────────────
const _clCmpSelected = [];   // [{cid, panelId, expType}]
const _clCmpCharts   = {};   // keyed by chart id

const CMP_COLORS = [
  '#e11d48','#2563eb','#16a34a','#d97706',
  '#7c3aed','#0891b2','#be185d','#059669',
];

function clToggleCmpCheck(chk) {
  const row = chk.closest('tr.cmp-row');
  const {cid, expType, panelId, expId} = row.dataset;
  const expIds = expId ? expId.split(',').map(Number).filter(n => n > 0) : [];
  row.classList.toggle('cmp-selected', chk.checked);
  if (chk.checked) {
    if (!_clCmpSelected.find(s => s.panelId === panelId))
      _clCmpSelected.push({cid, expType, panelId, expIds});
  } else {
    const idx = _clCmpSelected.findIndex(s => s.panelId === panelId);
    if (idx >= 0) _clCmpSelected.splice(idx, 1);
  }
  _clUpdateCmpBar();
  _clSyncBatchSelectAll(row);
}

function _clUpdateCmpBar() {
  const bar = document.getElementById('cl-cmp-bar');
  document.getElementById('cl-cmp-count').textContent =
    `已选 ${_clCmpSelected.length} 个化合物`;
  bar.style.display = _clCmpSelected.length >= 2 ? 'flex' : 'none';
}

function clClearCmpSelection() {
  _clCmpSelected.length = 0;
  document.querySelectorAll('.cl-cmp-chk').forEach(c => {
    c.checked = false;
    c.closest('tr.cmp-row')?.classList.remove('cmp-selected');
  });
  _clUpdateCmpBar();
}

function clOpenCmpModal() {
  const hasVitro = _clCmpSelected.some(s => s.expType === 'vitro');
  const hasVivo  = _clCmpSelected.some(s => s.expType === 'vivo');

  document.getElementById('cl-cmp-tab-vitro').disabled = !hasVitro;
  document.getElementById('cl-cmp-tab-vivo').disabled  = !hasVivo;

  document.getElementById('cl-cmp-overlay').style.display = 'block';
  document.getElementById('cl-cmp-modal').style.display   = 'flex';

  if (hasVitro) {
    clCmpTab(document.getElementById('cl-cmp-tab-vitro'), 'vitro');
    _clBuildVitroCompare('mrna');
  } else {
    clCmpTab(document.getElementById('cl-cmp-tab-vivo'), 'vivo');
  }
  if (hasVivo) _clBuildVivoCompare();
}

function clCloseCmpModal() {
  document.getElementById('cl-cmp-overlay').style.display = 'none';
  document.getElementById('cl-cmp-modal').style.display   = 'none';
  Object.values(_clCmpCharts).forEach(c => c.destroy());
  for (const k in _clCmpCharts) delete _clCmpCharts[k];
}

function clCmpTab(btn, tab) {
  ['vitro','vivo'].forEach(t => {
    document.getElementById(`cl-cmp-tab-${t}`).classList.toggle('active', t === tab);
    document.getElementById(`cl-cmp-pane-${t}`).style.display = t === tab ? '' : 'none';
  });
}

// Vitro comparison
function _clBuildVitroCompare(readout) {
  if (_clCmpCharts['vitro']) { _clCmpCharts['vitro'].destroy(); delete _clCmpCharts['vitro']; }
  const canvas = document.getElementById('cl-cmp-vitro-canvas');
  const vitros = _clCmpSelected.filter(s => s.expType === 'vitro');
  const datasets = vitros.flatMap((s, i) => {
    const src = document.querySelector(`#${s.panelId} canvas[data-chart="vitro"]`);
    if (!src) return [];
    const pts = JSON.parse(readout === 'kd' ? src.dataset.kd : src.dataset.mrna);
    return [{
      label: s.cid,
      data: pts.map(([x, y]) => ({x, y})),
      borderColor: CMP_COLORS[i % CMP_COLORS.length],
      backgroundColor: 'transparent',
      tension: 0.3, pointRadius: 3,
    }];
  });
  _clCmpCharts['vitro'] = new Chart(canvas, {
    type: 'line', data: {datasets},
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: {type:'linear', title:{display:true,text:'log₁₀(nM)',font:{size:10}}, ticks:{font:{size:10}}},
        y: {min:0, title:{display:true,text:readout==='kd'?'KD%':'mRNA%',font:{size:10}}, ticks:{font:{size:10}}},
      },
      plugins: {legend:{display:true, labels:{font:{size:10},boxWidth:14,padding:10}}},
    },
  });
}

function clCmpVitroReadout(btn, readout) {
  btn.closest('.cl-vitro-toggle').querySelectorAll('.cl-vtoggle-btn')
     .forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _clBuildVitroCompare(readout);
}

// Vivo comparison
function _clBuildVivoCompare() {
  const vivos = _clCmpSelected.filter(s => s.expType === 'vivo');
  const readouts = [...new Set(vivos.flatMap(s =>
    [...document.querySelectorAll(`#${s.panelId} canvas[data-chart="vivo"]`)]
      .map(c => c.dataset.readout).filter(Boolean)
  ))];

  const tabsEl   = document.getElementById('cl-cmp-vivo-rt-tabs');
  const chartsEl = document.getElementById('cl-cmp-vivo-charts');
  tabsEl.innerHTML = '';
  chartsEl.innerHTML = '';
  tabsEl.style.display = readouts.length > 1 ? '' : 'none';

  readouts.forEach((rt, ri) => {
    const label = rt === 'body_weight' ? '⚖ 体重变化%'
                : rt === 'knockdown_pct' ? '🧬 KD%' : rt;

    if (readouts.length > 1) {
      const btn = document.createElement('button');
      btn.className = 'cl-tab-btn' + (ri === 0 ? ' active' : '');
      btn.textContent = label;
      btn.onclick = () => {
        tabsEl.querySelectorAll('.cl-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        chartsEl.querySelectorAll('.cl-cmp-vivo-pane')
          .forEach((p, i) => p.style.display = i === ri ? '' : 'none');
      };
      tabsEl.appendChild(btn);
    }

    const pane = document.createElement('div');
    pane.className = 'cl-cmp-vivo-pane';
    pane.style.display = ri === 0 ? '' : 'none';
    const wrap = document.createElement('div');
    wrap.className = 'cl-cmp-chart-wrap';
    const canvas = document.createElement('canvas');
    canvas.id = `cl-cmp-vivo-${rt}`;
    wrap.appendChild(canvas);
    pane.appendChild(wrap);
    chartsEl.appendChild(pane);
    _clBuildVivoReadoutChart(canvas, vivos, rt);
  });
}

function _clBuildVivoReadoutChart(canvas, vivos, readout) {
  const chartKey = `vivo_${readout}`;
  if (_clCmpCharts[chartKey]) { _clCmpCharts[chartKey].destroy(); delete _clCmpCharts[chartKey]; }

  const datasets = [];
  let controlAdded = false;

  vivos.forEach((s, i) => {
    const src = document.querySelector(
      `#${s.panelId} canvas[data-chart="vivo"][data-readout="${readout}"]`
    );
    if (!src) return;
    const days    = JSON.parse(src.dataset.days    || '[]');
    const groups  = JSON.parse(src.dataset.groups  || '[]');
    const control = JSON.parse(src.dataset.control || 'null');
    const color   = CMP_COLORS[i % CMP_COLORS.length];

    groups.forEach((g, gi) => {
      datasets.push({
        label: `${s.cid} · ${g.label}`,
        data: days.map((d, j) => ({x:d, y:g.data[j]})).filter(p => p.y != null),
        borderColor: color,
        borderDash: gi > 0 ? [5, 3] : [],
        backgroundColor: 'transparent',
        tension: 0.2, pointRadius: 2,
      });
    });

    if (control && !controlAdded) {
      controlAdded = true;
      datasets.push({
        label: control.label,
        data: days.map((d, j) => ({x:d, y:control.data[j]})).filter(p => p.y != null),
        borderColor: '#94a3b8', borderDash: [4,3],
        backgroundColor: 'transparent',
        tension: 0.2, pointRadius: 2,
      });
    }
  });

  _clCmpCharts[chartKey] = new Chart(canvas, {
    type: 'line', data: {datasets},
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: {type:'linear', title:{display:true,text:'Day',font:{size:10}}, ticks:{font:{size:10},maxTicksLimit:8}},
        y: {
          title:{display:true,text:'%',font:{size:10}}, ticks:{font:{size:10}},
          grid:{color:ctx=>ctx.tick.value===0?'#94a3b8':'#e2e8f0',
                lineWidth:ctx=>ctx.tick.value===0?1.5:1},
        },
      },
      plugins: {legend:{display:true, labels:{font:{size:10},boxWidth:14,padding:8}}},
    },
  });
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

// ── Compound-view batch card drawer ──────────────────────────
function clSelectBatchCard(event, cardEl) {
  event.stopPropagation();
  const drawerId = cardEl.dataset.drawer;
  const panelId  = cardEl.dataset.panel;
  const drawer   = document.getElementById(drawerId);
  const grid     = cardEl.closest('.cl-batch-cards-grid');
  if (!drawer || !grid) return;

  // Clicking the already-selected card closes the drawer
  if (cardEl.classList.contains('selected')) {
    cardEl.classList.remove('selected');
    drawer.classList.remove('show');
    return;
  }

  // Deselect all cards in this grid
  grid.querySelectorAll('.cl-batch-card').forEach(c => c.classList.remove('selected'));
  cardEl.classList.add('selected');

  // Hide all panels in drawer, show the target panel
  drawer.querySelectorAll('.cl-drawer-panel').forEach(p => { p.style.display = 'none'; });
  const panel = document.getElementById(panelId);
  if (panel) panel.style.display = 'block';

  // Update drawer title from card badge
  const badge = cardEl.querySelector('.cl-card-badge');
  const title = drawer.querySelector('.cl-drawer-title');
  if (title && badge) title.textContent = badge.textContent.trim();

  // Show drawer and init charts lazily
  drawer.classList.add('show');
  if (panel) clInitChartsInPanel(panel);
}

function clCloseBatchDrawer(event, drawerId) {
  event.stopPropagation();
  const drawer = document.getElementById(drawerId);
  if (!drawer) return;
  drawer.classList.remove('show');
  document.querySelectorAll(`[data-drawer="${drawerId}"]`).forEach(c => c.classList.remove('selected'));
}

function _clSyncBatchSelectAll(row) {
  const table = row.closest('table');
  if (!table) return;
  const selectAll = table.querySelector('.cl-batch-select-all');
  if (!selectAll) return;
  const all = [...table.querySelectorAll('.cl-cmp-chk')];
  const checkedCount = all.filter(c => c.checked).length;
  if (checkedCount === 0) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  } else if (checkedCount === all.length) {
    selectAll.checked = true;
    selectAll.indeterminate = false;
  } else {
    selectAll.checked = false;
    selectAll.indeterminate = true;
  }
}

// ── Batch select-all header checkbox ─────────────────────────
function clToggleBatchSelectAll(chkEl) {
  const table = chkEl.closest('table');
  if (!table) return;
  table.querySelectorAll('.cl-cmp-chk').forEach(chk => {
    if (chk.checked !== chkEl.checked) {
      chk.checked = chkEl.checked;
      clToggleCmpCheck(chk);
    }
  });
}

// ── CSRF helper ───────────────────────────────────────────────
function _clCsrfToken() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : '';
}

// ── Delete selected experiments ───────────────────────────────
function clDeleteSelected() {
  const expIds = _clCmpSelected.flatMap(s => s.expIds);
  if (!confirm(`确认删除选中的 ${expIds.length} 条实验记录？此操作不可撤销。`)) return;
  fetch('/api/experiments/bulk-delete/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken()},
    body: JSON.stringify({exp_ids: expIds}),
  })
    .then(r => r.json().then(data => ({ok: r.ok, data})))
    .then(({ok, data}) => {
      if (!ok) { alert(data.error || '删除失败'); return; }
      alert(`已删除 ${data.deleted} 条实验记录`);
      location.reload();
    })
    .catch(() => alert('删除失败，请重试'));
}
