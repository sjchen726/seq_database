document.addEventListener('DOMContentLoaded', function() {
    const advancedSearchBtn = document.getElementById('advancedSearchBtn');
    const advancedSearchPanel = document.getElementById('advancedSearchPanel');
    const closeSearchPanel = document.getElementById('closeSearchPanel');
    const form = document.getElementById('advancedSearchForm');

    // 切换显示/隐藏（但不自动关闭）
    if (advancedSearchBtn && advancedSearchPanel) {
        advancedSearchBtn.addEventListener('click', function() {
            const visible = advancedSearchPanel.style.display === 'block';
            advancedSearchPanel.style.display = visible ? 'none' : 'block';
        });
    }

    // ✅ 只有点击“✖”才关闭
    if (closeSearchPanel && advancedSearchPanel) {
        closeSearchPanel.addEventListener('click', function() {
            advancedSearchPanel.style.display = 'none';
        });
    }

    // ✅ 加载上次表单记录（localStorage）
    const savedFilters = JSON.parse(localStorage.getItem('advancedSearchValues') || '{}');
    Object.entries(savedFilters).forEach(([name, value]) => {
        const input = form.querySelector(`[name="${name}"]`);
        if (input) input.value = value;
    });

    // ✅ 提交前保存表单值
    form.addEventListener('submit', function() {
        const formData = new FormData(form);
        const filtersToSave = {};
        for (let [name, value] of formData.entries()) {
            filtersToSave[name] = value;
        }
        localStorage.setItem('advancedSearchValues', JSON.stringify(filtersToSave));
    });

    // ✅ 点击“清除筛选”时清除保存
    const clearBtn = document.getElementById('clearFilters');
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            localStorage.removeItem('advancedSearchValues');
        });
    }
});