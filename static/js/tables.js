$(document).ready(function() {
    // 初始化 DataTable
    var table = $('#example').DataTable({
        "paging": true, // 启用分页
        "searching": true, // 启用搜索
        "info": true, // 显示信息
        "lengthMenu": [5, 10, 20, 50] // 设置每页显示的记录数
    });

    // 监听复选框的变化，控制列的显示和隐藏
    $('.toggle-vis').on('change', function(e) {
        var column = table.column($(this).attr('data-column'));
        column.visible($(this).prop('checked'));
    });
});