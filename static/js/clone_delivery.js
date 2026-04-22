// clone_delivery.js - delegated handler for Clone Sequence modal
$(document).ready(function() {
    function getCsrf() {
        return $("input[name=csrfmiddlewaretoken]").first().val();
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
                var html = '';
                html += '<div class="ds-clone-row">';
                var seqType = (r.Seq_type || '').toString().toUpperCase();
                var headingStyle = '';
                if (seqType === 'AS' || seqType === 'SS') {
                    headingStyle = 'style="font-size:1.25rem; font-weight:600;"';
                }
                html += '<h6 ' + headingStyle + '>Record ' + (idx + 1) + ' - ' + (r.Seq_type || '') + '</h6>';
                // first row: Project, Target, Seq_type
                html += '<div class="ds-form-3col">';
                html += '<div><label class="ds-form-label">Project</label><input name="Project" class="ds-form-control" value="' + (r.Project || '') + '" readonly /></div>';
                html += '<div><label class="ds-form-label">Target</label><input name="Target" class="ds-form-control" value="' + (r.Target || '') + '" readonly /></div>';
                html += '<div><label class="ds-form-label">Seq_type</label><input name="Seq_type" class="ds-form-control" value="' + (r.Seq_type || '') + '" readonly /></div>';
                html += '</div>';
                // second row: Modify_seq occupies full width
                html += '<div>';
                html += '<div><label class="ds-form-label">Modify_seq</label><input name="Modify_seq" class="ds-form-control" value="' + (r.Modify_seq || '') + '" /></div>';
                html += '</div>';
                // third row: delivery5 and delivery3 share the row
                html += '<div class="ds-form-2col">';
                html += '<div><label class="ds-form-label">delivery5</label><input name="delivery5" class="ds-form-control" value="' + (r.delivery5 || '') + '" /></div>';
                html += '<div><label class="ds-form-label">delivery3</label><input name="delivery3" class="ds-form-control" value="' + (r.delivery3 || '') + '" /></div>';
                html += '</div>';
                // fourth row: Strand_MWs, Parents, Remark share a single row (3 columns)
                html += '<div class="ds-form-3col">';
                html += '<div><label class="ds-form-label">Strand_MWs</label><input name="Strand_MWs" class="ds-form-control" value="' + (r.Strand_MWs || '') + '" /></div>';
                html += '<div><label class="ds-form-label">Parents</label><input name="Parents" class="ds-form-control" value="' + (r.Parents || '') + '" /></div>';
                html += '<div><label class="ds-form-label">Remark</label><input name="Remark" class="ds-form-control" value="' + (r.Remark || '') + '" /></div>';
                html += '</div>';
                html += '</div>';
                $('#cloneRowsContainer').append(html);
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