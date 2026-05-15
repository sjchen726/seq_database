(function () {
  var concUnits   = JSON.parse(document.getElementById('conc_unit_choices').textContent);
  var readoutTypes = JSON.parse(document.getElementById('readout_type_choices').textContent);

  function buildSelect(name, choices, required) {
    var s = '<select name="' + name + '" class="ds-form-control"' + (required ? ' required' : '') + '>';
    if (!required) s += '<option value="">--</option>';
    for (var i = 0; i < choices.length; i++) {
      s += '<option value="' + choices[i].v + '">' + choices[i].l + '</option>';
    }
    s += '</select>';
    return s;
  }

  function dpRow() {
    var tr = document.createElement('tr');
    tr.innerHTML = ''
      + '<td><input type="number" step="any" name="dp_conc" class="ds-form-control"></td>'
      + '<td>' + buildSelect('dp_conc_unit', concUnits, false) + '</td>'
      + '<td><input type="text" name="dp_timepoint" class="ds-form-control" placeholder="48h / Day7"></td>'
      + '<td>' + buildSelect('dp_readout_type', readoutTypes, true) + '</td>'
      + '<td><input type="number" step="any" name="dp_value" class="ds-form-control" required></td>'
      + '<td><input type="text" name="dp_value_unit" class="ds-form-control" placeholder="% / ng/mL"></td>'
      + '<td><input type="text" name="dp_replicate" class="ds-form-control" placeholder="n=3"></td>'
      + '<td><button type="button" class="ds-btn ds-btn-ghost remove-dp" style="height:24px;padding:0 6px;">×</button></td>';
    return tr;
  }

  function attachRow() {
    var div = document.createElement('div');
    div.className = 'attach-row';
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;';
    div.innerHTML = ''
      + '<input type="file" name="att_file" class="ds-form-control" style="flex:1;min-width:0;">'
      + '<input type="text" name="att_url" class="ds-form-control" placeholder="或填外部链接" style="flex:1;min-width:0;">'
      + '<input type="text" name="att_label" class="ds-form-control" placeholder="描述" style="flex:2;min-width:0;">'
      + '<button type="button" class="ds-btn ds-btn-ghost remove-attach" style="height:24px;padding:0 6px;flex-shrink:0;">×</button>';
    return div;
  }

  var savedRows = JSON.parse(document.getElementById('dp_rows_json').textContent || '[]');
  if (savedRows.length > 0) {
    savedRows.forEach(function(row) {
      var tr = dpRow();
      tr.querySelector('[name="dp_conc"]').value = row.conc || '';
      tr.querySelector('[name="dp_conc_unit"]').value = row.conc_unit || '';
      tr.querySelector('[name="dp_timepoint"]').value = row.timepoint || '';
      tr.querySelector('[name="dp_readout_type"]').value = row.readout_type || '';
      tr.querySelector('[name="dp_value"]').value = row.value || '';
      tr.querySelector('[name="dp_value_unit"]').value = row.value_unit || '';
      tr.querySelector('[name="dp_replicate"]').value = row.replicate || '';
      document.getElementById('datapoints_body').appendChild(tr);
    });
  } else {
    document.getElementById('datapoints_body').appendChild(dpRow());
  }

  document.getElementById('addDataPointBtn').addEventListener('click', function () {
    document.getElementById('datapoints_body').appendChild(dpRow());
  });
  document.getElementById('datapoints_body').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-dp')) {
      var tbody = document.getElementById('datapoints_body');
      if (tbody.children.length > 1) e.target.closest('tr').remove();
    }
  });

  document.getElementById('addAttachBtn').addEventListener('click', function () {
    document.getElementById('attachments_wrap').appendChild(attachRow());
  });
  document.getElementById('attachments_wrap').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-attach')) {
      e.target.closest('.attach-row').remove();
    }
  });

  // assay_type options valid per exp_type
  var ASSAY_BY_TYPE = {
    in_vitro: ['single_point', 'dose_response'],
    in_vivo:  ['in_vivo_efficacy', 'pk'],
  };

  function toggleExpType() {
    var t = document.getElementById('exp_type_select').value;
    document.getElementById('cell_line_wrap').style.display = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('reagent_wrap').style.display   = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('animal_wrap').style.display    = (t === 'in_vivo')  ? '' : 'none';
    document.getElementById('route_wrap').style.display     = (t === 'in_vivo')  ? '' : 'none';

    var allowed = ASSAY_BY_TYPE[t] || [];
    var sel = document.querySelector('[name="assay_type"]');
    var current = sel.value;
    Array.prototype.forEach.call(sel.options, function (opt) {
      var show = allowed.length === 0 || allowed.indexOf(opt.value) !== -1;
      opt.style.display = show ? '' : 'none';
    });
    // Reset to first visible option if current selection is now hidden
    if (allowed.length > 0 && allowed.indexOf(sel.value) === -1) {
      sel.value = allowed[0];
    }
  }
  document.getElementById('exp_type_select').addEventListener('change', toggleExpType);
  toggleExpType();
})();
