$(document).ready(function() {
    // seq_list 使用 table-container 类标记，需要开启横纵向滚动
    var isScrollable = $('#example').hasClass('table-container');

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
        scrollX: isScrollable,
        scrollY: isScrollable ? '62vh' : undefined,
        scrollCollapse: isScrollable,
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

    // 每次重绘后，确保编辑/关联链接包含当前页码参数 dt_page
    table.on('draw', function() {
        try {
            const currentPage = table.page(); // 0-based
            // 编辑链接
            $('#example a[href*="/edit_seq/"]').each(function() {
                const $a = $(this);
                const url = new URL($a.prop('href'), window.location.origin);
                url.searchParams.set('dt_page', currentPage);
                $a.prop('href', url.toString());
            });
            // 关联链接
            $('#example a[href*="/cor_seq/"]').each(function() {
                const $a = $(this);
                const url = new URL($a.prop('href'), window.location.origin);
                url.searchParams.set('dt_page', currentPage);
                $a.prop('href', url.toString());
            });

            // 将当前页码写入浏览器地址栏（不刷新页面），以便 F5 刷新时能保留页码
            try {
                const curUrl = new URL(window.location.href);
                curUrl.searchParams.set('dt_page', currentPage);
                window.history.replaceState({}, document.title, curUrl.toString());
            } catch (e) {
                console.warn('update URL dt_page failed', e);
            }
        } catch (e) {
            console.warn('append dt_page failed', e);
        }
    });

    // 高亮处理：读取 URL 参数 highlight_duplex / highlight_delivery 并在表格中标记对应行
    function applyHighlights() {
        try {
            const params = new URLSearchParams(window.location.search);
            const hDuplex = params.get('highlight_duplex');
            const hDelivery = params.get('highlight_delivery');
            const hSeqType = params.get('highlight_seq_type');

            // 先移除旧的高亮
            $('#example tbody tr').removeClass('highlight-row');

            if (!hDuplex && !hDelivery) return;

            // 搜索并标记行：我们在模板里把 rm_code 或 delivery id 放在 tr 的 data 属性
            let matched = $();
            $('#example tbody tr').each(function() {
                const $tr = $(this);
                const duplexText = $tr.find('td:nth-child(2)').text().trim(); // Strand ID 列
                const deliveryId = $tr.data('delivery-id');
                const rmCode = $tr.data('rm-code');

                // 仅在 seq_type 匹配时才高亮（如果提供了 hSeqType）
                const rowSeqType = $tr.data('seq-type') || $tr.attr('data-seq-type') || '';
                const seqTypeMatches = !hSeqType || String(rowSeqType) === String(hSeqType);

                if (seqTypeMatches && hDuplex && duplexText && duplexText.indexOf(hDuplex) !== -1) {
                    matched = matched.add($tr);
                }

                if (seqTypeMatches && hDelivery && deliveryId && String(deliveryId) === String(hDelivery)) {
                    matched = matched.add($tr);
                }

                // 兼容 rm_code 高亮（部分场景）
                if (seqTypeMatches && hDelivery && rmCode && String(rmCode) === String(hDelivery)) {
                    matched = matched.add($tr);
                }
            });

            if (matched.length) {
                matched.addClass('highlight-row');

                // 滚动到第一个匹配行（若不在可视区域）
                const first = matched.first();
                const pageTop = $(window).scrollTop();
                const offset = first.offset().top - 100;
                $('html, body').animate({ scrollTop: offset }, 300);

                // 5 秒后移除高亮并从 URL 中移除相关参数（历史替换）
                setTimeout(function() {
                    matched.removeClass('highlight-row');
                    try {
                        const url = new URL(window.location.href);
                        url.searchParams.delete('highlight_duplex');
                        url.searchParams.delete('highlight_delivery');
                        window.history.replaceState({}, document.title, url.toString());
                    } catch (e) {}
                }, 5000);
            }
        } catch (e) {
            console.warn('applyHighlights failed', e);
        }
    }

    // 在每次 draw 后应用高亮（以应对分页恢复）
    table.on('draw', function() {
        applyHighlights();
    });

    // 初始调用
    applyHighlights();

    // 初始渲染：优先从 URL 恢复 dt_page，然后再绘制（避免初始 draw 覆盖 URL）
    (function initDrawWithDtPage() {
        try {
            const params = new URLSearchParams(window.location.search);
            const dtPage = params.get('dt_page');
            if (dtPage !== null) {
                const pageIndex = parseInt(dtPage, 10);
                if (!isNaN(pageIndex)) {
                    table.page(pageIndex).draw(false);
                    return;
                }
            }
        } catch (e) {
            console.warn('读取 dt_page 失败', e);
        }

        // 默认绘制第一页
        table.draw();
    })();
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