// clone_delivery.js - delegated handler for Clone Sequence modal
$(document).ready(function() {
    function getCsrf() {
        return $("input[name=csrfmiddlewaretoken]").first().val();
    }

    // Helper: create a labeled input cell
    function makeField(labelText, name, value, readOnly) {
        var wrapper = document.createElement('div');
        var lbl = document.createElement('label');
        lbl.className = 'ds-form-label';
        lbl.textContent = labelText;
        var inp = document.createElement('input');
        inp.name = name;
        inp.className = 'ds-form-control';
        inp.value = value || '';
        if (readOnly) inp.readOnly = true;
        wrapper.appendChild(lbl);
        wrapper.appendChild(inp);
        return wrapper;
    }

    // open modal and load deliveries (works for any page where .clone-seq-btn exists)
    $('body').on('click', '.clone-seq-btn', function(e) {
        e.preventDefault();
        var strand = $(this).data('strand-id');
        if (!strand) { alert('Strand ID not available'); return; }
        $('#cloneStrandId').text(strand);
        $('#modal_strand_id').val(strand);
        $('#cloneRowsContainer').empty();
        $.get('/clone_delivery/', { strand_id: strand }, function(resp) {
            if (resp.error) { alert(resp.error); return; }
            var rows = resp.deliveries;
            rows.forEach(function(r, idx) {
                var rowDiv = document.createElement('div');
                rowDiv.className = 'ds-clone-row';

                // Heading
                var h6 = document.createElement('h6');
                var seqType = (r.Seq_type || '').toString().toUpperCase();
                if (seqType === 'AS' || seqType === 'SS') {
                    h6.style.fontSize = '1.25rem';
                    h6.style.fontWeight = '600';
                }
                h6.textContent = 'Record ' + (idx + 1) + ' - ' + (r.Seq_type || '');
                rowDiv.appendChild(h6);

                // Row 1: Project, Target, Seq_type (readonly)
                var row1 = document.createElement('div');
                row1.className = 'ds-form-3col';
                row1.appendChild(makeField('Project',  'Project',  r.Project,  true));
                row1.appendChild(makeField('Target',   'Target',   r.Target,   true));
                row1.appendChild(makeField('Seq_type', 'Seq_type', r.Seq_type, true));
                rowDiv.appendChild(row1);

                // Row 2: Modify_seq (full width, editable)
                var row2 = document.createElement('div');
                row2.appendChild(makeField('Modify_seq', 'Modify_seq', r.Modify_seq, false));
                rowDiv.appendChild(row2);

                // Row 3: delivery5, delivery3 (editable)
                var row3 = document.createElement('div');
                row3.className = 'ds-form-2col';
                row3.appendChild(makeField('delivery5', 'delivery5', r.delivery5, false));
                row3.appendChild(makeField('delivery3', 'delivery3', r.delivery3, false));
                rowDiv.appendChild(row3);

                // Row 4: Strand_MWs, Parents, Remark (editable)
                var row4 = document.createElement('div');
                row4.className = 'ds-form-3col';
                row4.appendChild(makeField('Strand_MWs', 'Strand_MWs', r.Strand_MWs, false));
                row4.appendChild(makeField('Parents',    'Parents',    r.Parents,    false));
                row4.appendChild(makeField('Remark',     'Remark',     r.Remark,     false));
                rowDiv.appendChild(row4);

                $('#cloneRowsContainer').append(rowDiv);
            });
            // ensure divider sits between Record 1 and Record 2 (insert after first record)
            if (rows.length > 1) {
                $('#cloneRowsContainer .ds-clone-row').first().after('<div class="ds-clone-divider" aria-hidden="true"></div>');
            }
            $('#cloneModal').modal('show');
        }).fail(function(xhr) {
            alert('加载失败: ' + xhr.responseText);
        });
    });

    // submit cloned data
    $('body').on('click', '#confirmCloneBtn', function() {
        var deliveries = [];
        $('#cloneRowsContainer .ds-clone-row').each(function() {
            var $row = $(this);
            var obj = {};
            $row.find('input').each(function() {
                var name = $(this).attr('name');
                obj[name] = $(this).val();
            });
            deliveries.push(obj);
        });

        if (deliveries.length === 0) { alert('无可克隆的记录'); return; }

        var payload = { deliveries: deliveries };

        $.ajax({
            url: '/clone_delivery/',
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrf() },
            contentType: 'application/json',
            data: JSON.stringify(payload),
            success: function(resp) {
                if (resp.success) {
                    alert('克隆成功: ' + resp.duplex_id);
                    location.reload();
                } else if (resp.error) {
                    var msg = resp.error || '发生错误';
                    if (resp.detail && Array.isArray(resp.detail)) {
                        msg += '\n\n详情:';
                        resp.detail.forEach(function(d) { msg += '\n - ' + d; });
                    } else if (resp.detail) {
                        msg += '\n' + resp.detail;
                    }
                    alert(msg);
                }
            },
            error: function(xhr) {
                var txt = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : xhr.responseText;
                alert('提交失败: ' + txt);
            }
        });
    });
});
