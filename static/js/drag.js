function makeDraggable(dragTarget, handle) {
    let offsetX = 0,
        offsetY = 0,
        isDragging = false;

    handle.style.cursor = 'move';

    handle.addEventListener('mousedown', function(e) {
        isDragging = true;
        const rect = dragTarget.getBoundingClientRect();
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;
        dragTarget.style.opacity = '0.7'; // 拖动时半透明
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;

        const panelWidth = dragTarget.offsetWidth;
        const panelHeight = dragTarget.offsetHeight;
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        let newLeft = e.clientX - offsetX;
        let newTop = e.clientY - offsetY;

        // 限制范围不出屏幕
        newLeft = Math.max(0, Math.min(viewportWidth - panelWidth, newLeft));
        newTop = Math.max(0, Math.min(viewportHeight - panelHeight, newTop));

        dragTarget.style.position = 'fixed';
        dragTarget.style.left = `${newLeft}px`;
        dragTarget.style.top = `${newTop}px`;
    });

    document.addEventListener('mouseup', function() {
        if (isDragging) {
            dragTarget.style.opacity = '1'; // 恢复透明度
            document.body.style.userSelect = '';
        }
        isDragging = false;
    });
}