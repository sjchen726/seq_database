// 获取所有字段复选框
const columnCheckboxes = document.querySelectorAll('.toggle-vis');

// 添加事件监听：控制列显隐
columnCheckboxes.forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        const columnIndex = this.getAttribute('data-column');
        const show = this.checked;
        toggleColumnVisibility(columnIndex, show);
    });
});

// 显示/隐藏列函数
function toggleColumnVisibility(columnIndex, show) {
    const columns = document.querySelectorAll('.column-' + columnIndex);
    columns.forEach(column => {
        column.style.display = show ? '' : 'none';
    });
}