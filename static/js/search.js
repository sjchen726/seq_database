document.addEventListener('DOMContentLoaded', function() {
    const advancedSearchBtn = document.getElementById('advancedSearchBtn');
    const advancedSearchPanel = document.getElementById('advancedSearchPanel');
    const closeSearchPanel = document.getElementById('closeSearchPanel');

    if (!advancedSearchPanel) return;

    // 面板默认关闭，搜索后不自动展开（活跃筛选条已显示当前筛选条件）

    // 点击按钮切换面板显示
    if (advancedSearchBtn) {
        advancedSearchBtn.addEventListener('click', function() {
            const visible = advancedSearchPanel.style.display === 'block';
            advancedSearchPanel.style.display = visible ? 'none' : 'block';
        });
    }

    // 点击”✖”关闭
    if (closeSearchPanel) {
        closeSearchPanel.addEventListener('click', function() {
            advancedSearchPanel.style.display = 'none';
        });
    }

    // 应用筛选后自动关闭面板
    const applyBtn = document.getElementById('applyFilters');
    if (applyBtn) {
        applyBtn.addEventListener('click', function() {
            advancedSearchPanel.style.display = 'none';
        });
    }

    // 清除筛选按钮：通过 JS 跳转清除所有高级筛选参数
    const clearBtn = document.getElementById('clearFilters');
    if (clearBtn) {
        clearBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const url = new URL(window.location.href);
            const advancedKeys = ['filterSequence','filterNakedSeq','filterSeq','filter5Delivery','filter3Delivery',
                                  'filterTarget','filterProject','filterSeqType','filterTranscript',
                                  'filterParents','filterRemarks','filterStrandMWs','filterPos','filterAsSeqtype',
                                  'filterModifySeq','filterParents','filterRemarks'];
            advancedKeys.forEach(k => url.searchParams.delete(k));
            window.location.href = url.toString();
        });
    }
});