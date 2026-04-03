document.addEventListener('DOMContentLoaded', function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');

    // 基础元素不存在就退出，避免脚本报错导致其它功能失效
    if (!searchBtn || !searchInput) return;

    const table = window.table;
    if (!table) {
        console.error('[forms.js] window.table 未初始化，请确保 tables.js 在 forms.js 之前加载。');
        return;
    }

    let activeFilters = {};

    // ✅ 注册 DataTables 自定义搜索：只注册一次，避免重复 push
    if (!window.__normalSearchRegistered) {
        $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {
            const row = settings.aoData[dataIndex].nTr;
            const cells = data.map(cell => String(cell || '').toLowerCase());

            const modifySeqCell = row ? row.querySelector('[data-modify-seq]') : null;
            let modifySeqData = modifySeqCell ? (modifySeqCell.getAttribute('data-modify-seq') || '').toLowerCase() : '';
            modifySeqData = modifySeqData.replace(/[osf]/g, '');

            // 只做普通搜索：activeFilters.query
            if (activeFilters.query) {
                const queries = activeFilters.query
                    .split(',')
                    .map(q => q.trim())
                    .filter(Boolean);

                return (
                    cells.some(text => queries.some(q => text.includes(q))) ||
                    queries.some(q => modifySeqData.includes(q))
                );
            }

            // 没有普通搜索关键字时，不拦截（放行）
            return true;
        });

        window.__normalSearchRegistered = true;
    }

    // 工具：本次 draw 完成后，如果过滤结果为 0 就弹窗（只弹一次）
    function alertIfNoMatchOnce() {
        table.one('draw', function() {
            const count = table.rows({ filter: 'applied' }).count();
            if (count === 0) alert('没有搜索到指定内容');
        });
    }

    // 普通搜索按钮（不跳转）
    searchBtn.addEventListener('click', function(e) {
        e.preventDefault(); // ✅ 防止表单提交/跳转

        const query = searchInput.value.trim().toLowerCase();
        activeFilters = { query };

        alertIfNoMatchOnce(); // ✅ 先绑定，再 draw
        table.draw();
    });

    // 回车触发搜索（不跳转）
    searchInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault(); // ✅ 防止回车触发表单提交/跳转
            searchBtn.click();
        }
    });
});