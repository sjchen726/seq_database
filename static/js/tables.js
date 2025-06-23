$(document).ready(function() {
    // 初始化 DataTable
    window.table = $('#example').DataTable({
        paging: true,
        searching: true,
        info: true,
        ordering: true,
        pageLength: 20,
        order: [
            [1, 'asc']
        ],
        lengthMenu: [5, 10, 20, 50],
        columnDefs: [{
            targets: 0,
            orderable: false,
        }],
        createdRow: function(row, data) {
            // 强制初始化选中状态
            if (typeof data._selected === 'undefined') {
                data._selected = false;
            }
            // 根据 data._selected 设置复选框是否选中
            $(row).find('.row-checkbox').prop('checked', data._selected);
        }
    });

    // 初始化已有行的 _selected 字段
    table.rows().every(function() {
        let data = this.data();
        if (typeof data._selected === 'undefined') {
            data._selected = false;
            this.data(data);
        }
    });

    // 全选 / 取消全选
    $('#select-all').on('click', function() {
        let isChecked = $(this).prop('checked');
        table.rows({ page: 'current' }).every(function() {
            let data = this.data();
            data._selected = isChecked;
            this.data(data);
            // 手动同步复选框显示
            $(this.node()).find('.row-checkbox').prop('checked', isChecked);
        });
        updateSelectAllState();
    });

    // 单行复选框改变时更新状态
    $('#example tbody').on('change', '.row-checkbox', function() {
        let $checkbox = $(this);
        let row = table.row($checkbox.closest('tr'));
        let data = row.data();

        // 1. 更新 data._selected
        data._selected = $checkbox.prop('checked');
        // 2. 把整个 data 重新写回去
        row.data(data);
        // 3. 手动再把复选框设成 data._selected，避免 DataTable 重渲染时把状态覆盖
        $(row.node()).find('.row-checkbox').prop('checked', data._selected);

        updateSelectAllState();
    });

    // 更新“全选”按钮状态
    function updateSelectAllState() {
        let currentPageRows = table.rows({ page: 'current' }).nodes().to$();
        let allChecked = currentPageRows.find('.row-checkbox:not(:checked)').length === 0;
        $('#select-all').prop('checked', allChecked);
    }

    // 显示选中项按钮
    $('#show-selected').on('click', function() {
        // 移除已有的 selectedFilter，避免重复
        $.fn.dataTable.ext.search = $.fn.dataTable.ext.search.filter(f => f.name !== 'selectedFilter');

        // 新增一个只显示 _selected 为 true 的行的过滤器
        const selectedFilter = function(settings, data, dataIndex) {
            let rowData = table.row(dataIndex).data();
            if (typeof rowData._selected === 'undefined') {
                rowData._selected = false;
                table.row(dataIndex).data(rowData);
            }
            return rowData._selected === true;
        };
        selectedFilter.name = 'selectedFilter';
        $.fn.dataTable.ext.search.push(selectedFilter);

        table.draw();

        if (!$('#reset-view').length) {
            $('<button id="reset-view" class="btn btn-warning" style="margin-left:10px;">恢复全部显示</button>')
                .insertAfter('#show-selected')
                .on('click', function() {
                    $.fn.dataTable.ext.search = $.fn.dataTable.ext.search.filter(f => f.name !== 'selectedFilter');
                    table.draw();
                    $(this).remove();
                });
        }
    });

    // 列显示切换
    $('.toggle-vis').on('change', function() {
        let column = table.column($(this).attr('data-column'));
        column.visible($(this).prop('checked'));
    });

    // 折叠功能
    let isCollapsed = false;
    $('#toggleCollapseBtn').on('click', function() {
        isCollapsed = !isCollapsed;
        table.draw();
    });

    // 每次重绘时处理：折叠 + 复选框同步
    table.on('draw', function() {
        let prev = null;
        let groupIndex = 0;
        const colorClasses = ['group-bg-1', 'group-bg-2'];

        $('#example tbody tr')
            .removeClass('group-bg-1 group-bg-2')
            .removeAttr('style');

        // 处理折叠逻辑
        table.column(1, { page: 'current' }).nodes().each(function(cell, i) {
            const $cell = $(cell);
            const $row = $cell.closest('tr');
            const originalText = $cell.data('original-text') || $cell.text().trim();

            $cell.data('original-text', originalText);

            if (isCollapsed && originalText === prev) {
                $cell.text('');
            } else {
                $cell.text(originalText);
                prev = originalText;
                groupIndex++;
            }

            $row.addClass(colorClasses[groupIndex % colorClasses.length]);
        });

        // 同步复选框状态
        table.rows().every(function() {
            let data = this.data();
            if (typeof data._selected === 'undefined') {
                data._selected = false;
                this.data(data);
            }
            $(this.node()).find('.row-checkbox').prop('checked', data._selected);
        });

        updateSelectAllState(); // 每次绘制后更新全选状态
    });

    // 初始渲染
    table.draw();
});

//下载选中项

// 下载选中项
document.getElementById('download-selected').addEventListener('click', function() {
    // ✅ 获取勾选字段（不限制在旧容器中）
    const checkboxes = document.querySelectorAll('input.export-field:checked');
    const selectedColumns = Array.from(checkboxes).map(cb => cb.value);

    // ✅ 必须选择字段
    if (selectedColumns.length === 0) {
        alert("请至少选择一个字段导出");
        return;
    }

    // ✅ 强制要求选择关键字段
    if (!selectedColumns.includes('duplex_id') || !selectedColumns.includes('id')) {
        alert("导出必须包含字段：Starnd ID 和 Sequence ID");
        return;
    }

    // ✅ 获取选中行中的 duplex_id 和 seq_type
    const selectedIds = [];
    const selectedSeqTypes = [];

    table.rows().every(function() {
        const row = this.node();
        if ($(row).find('input.row-checkbox').prop('checked')) {
            const duplexId = $(row).find('td:nth-child(2)').text().trim();
            const seqType = $(row).find('td:nth-child(5)').text().trim();

            if (duplexId && seqType) {
                selectedIds.push(duplexId);
                selectedSeqTypes.push(seqType);
            }
        }
    });

    if (selectedIds.length === 0) {
        alert("请先选择至少一条序列");
        return;
    }

    // ✅ 构建并提交隐藏表单
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/download_selected/';
    form.style.display = 'none';

    const csrfToken = document.querySelector('input[name=csrfmiddlewaretoken]').value;

    // ✅ CSRF Token
    form.appendChild(Object.assign(document.createElement('input'), {
        type: 'hidden',
        name: 'csrfmiddlewaretoken',
        value: csrfToken
    }));

    // ✅ 选中字段
    form.appendChild(Object.assign(document.createElement('input'), {
        type: 'hidden',
        name: 'selected_columns',
        value: JSON.stringify(selectedColumns)
    }));

    // ✅ duplex_id 列表
    form.appendChild(Object.assign(document.createElement('input'), {
        type: 'hidden',
        name: 'selected_ids',
        value: JSON.stringify(selectedIds)
    }));

    // ✅ seq_type 列表
    form.appendChild(Object.assign(document.createElement('input'), {
        type: 'hidden',
        name: 'selected_seq_types',
        value: JSON.stringify(selectedSeqTypes)
    }));

    document.body.appendChild(form);
    form.submit();
});