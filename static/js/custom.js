$(document).ready(function() {
    // 保留原有 submenu 动画
    $(".submenu > a").click(function(e) {
        e.preventDefault();
        var $li = $(this).parent("li");
        var $ul = $(this).next("ul");

        if ($li.hasClass("open")) {
            $ul.slideUp(350);
            $li.removeClass("open");
        } else {
            $(".nav > li > ul").slideUp(350);
            $(".nav > li").removeClass("open");
            $ul.slideDown(350);
            $li.addClass("open");
        }
    });

    // 单个删除按钮的确认弹窗（form button）
    $(".single-delete-btn").click(function() {
        return confirm("确定要删除该模块吗？此操作不可恢复！");
    });

    // 批量删除按钮（用于 name="selected_ids[]" 多选项）
    $(".batch-delete-btn").click(function() {
        if (!$(".row-checkbox:checked").length) {
            alert("请至少选择一个要删除的模块。");
            return false;
        }
        return confirm("确定要批量删除选中的模块吗？");
    });
});