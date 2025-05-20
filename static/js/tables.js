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

    $('.toggle-vis').on('change', function(e) {
        var column = table.column($(this).attr('data-column'));
        column.visible($(this).prop('checked'));
    });

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

            // 缓存原始 Strand ID
            let originalText = $cell.data('original-text') || $cell.text().trim();
            $cell.data('original-text', originalText);

            if (originalText === prev) {
                $cell.text('');
            } else {
                $cell.text(originalText);
                prev = originalText;
                groupIndex++;
            }

            $row.addClass(colorClasses[groupIndex % colorClasses.length]);
        });
    });

    table.draw(); // 初次触发绘制
});