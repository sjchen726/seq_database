// 为每个复选框添加事件监听器
const checkboxes = document.querySelectorAll('.toggle-vis');
checkboxes.forEach(checkbox => {
    checkbox.addEventListener('change', toggleColumns);
});

function toggleColumns() {
    // 获取所有复选框的状态，并根据 data-column 控制列的显示/隐藏
    checkboxes.forEach(checkbox => {
        const columnIndex = checkbox.getAttribute('data-column');
        const showColumn = checkbox.checked; // 复选框状态

        // 根据列索引和复选框状态来显示/隐藏对应的列
        toggleColumnVisibility(columnIndex, showColumn);
    });
}

function toggleColumnVisibility(columnIndex, show) {
    // 根据列索引获取所有对应的列
    const columns = document.querySelectorAll('.column-' + columnIndex);
    columns.forEach(column => {
        column.style.display = show ? '' : 'none';
    });
}