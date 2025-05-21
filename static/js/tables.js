$(document).ready(function() {
    var table = $('#example').DataTable({
        paging: true,
        searching: true,
        info: true,
        ordering: true,
        pageLength: 20,
        order: [
            [0, 'asc']
        ],
        lengthMenu: [5, 10, 20, 50]
    });

    // 切换列显示
    $('.toggle-vis').on('change', function(e) {
        var column = table.column($(this).attr('data-column'));
        column.visible($(this).prop('checked'));
    });

    // 初始化折叠状态
    var isCollapsed = false;

    // 处理折叠按钮的点击事件
    $('#toggleCollapseBtn').on('click', function() {
        isCollapsed = !isCollapsed; // 切换折叠状态

        // 触发重新绘制表格
        table.draw();
    });

    // 绘制表格时，处理分组背景色和折叠逻辑
    table.on('draw', function() {
        let prev = null;
        let groupIndex = 0;
        let colorClasses = ['group-bg-1', 'group-bg-2'];

        $('#example tbody tr')
            .removeClass('group-bg-1 group-bg-2')
            .removeAttr('style');

        table.column(0, { page: 'current' }).nodes().each(function(cell, i) {
            let $cell = $(cell);
            let $row = $cell.closest('tr');

            // 获取原始 strand_id
            let originalText = $cell.data('original-text') || $cell.text().trim();
            $cell.data('original-text', originalText);

            // 如果折叠状态为 true，清空后续的 strand_id
            if (isCollapsed && originalText === prev) {
                $cell.text(''); // 清空后续行的 strand_id
            } else {
                $cell.text(originalText); // 显示当前行的 strand_id
                prev = originalText;
                groupIndex++;
            }

            // 添加交替背景色
            $row.addClass(colorClasses[groupIndex % colorClasses.length]);
        });
    });

    // 初次触发绘制
    table.draw();
});