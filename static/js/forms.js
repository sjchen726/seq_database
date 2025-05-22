document.addEventListener('DOMContentLoaded', function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');
    const advancedSearchBtn = document.getElementById('advancedSearchBtn');
    const advancedSearchPanel = document.getElementById('advancedSearchPanel');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    const closeSearchPanel = document.getElementById('closeSearchPanel');

    let activeFilters = {};

    const table = window.table; // 从 tables.js 中获取已经初始化的 DataTable

    // ✅ 注册 DataTables 的自定义搜索
    $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {
        const row = settings.aoData[dataIndex].nTr;
        const cells = data.map(cell => cell.toLowerCase());

        const modifySeqCell = row.querySelector('[data-modify-seq]');
        let modifySeqData = modifySeqCell ? modifySeqCell.getAttribute('data-modify-seq').toLowerCase() : '';
        modifySeqData = modifySeqData.replace(/[osf]/g, '');

        // 普通搜索
        if (activeFilters.query) {
            const queries = activeFilters.query.split(',').map(q => q.trim());
            return cells.some(text => queries.some(q => text.includes(q))) ||
                queries.some(q => modifySeqData.includes(q));
        }

        // 高级搜索
        for (const [key, value] of Object.entries(activeFilters)) {
            if (!value || key === 'query') continue;
            const queryList = value.split(',').map(q => q.trim());

            if (key === 'modifySeq') {
                const filtered = queryList.map(v => v.replace(/[ofs\s]/g, ''));
                if (!filtered.some(val => modifySeqData.includes(val))) return false;
            } else {
                if (!queryList.some(query => cells.some(cell => cell.includes(query)))) return false;
            }
        }

        return true;
    });

    // 普通搜索按钮
    searchBtn.addEventListener('click', function() {
        const query = searchInput.value.trim().toLowerCase();
        activeFilters = { query };
        table.draw();
    });

    // 回车触发搜索
    searchInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            searchBtn.click();
        }
    });

    // 显示/隐藏高级搜索面板
    advancedSearchBtn.addEventListener('click', function() {
        if (advancedSearchPanel.style.display === 'none' || advancedSearchPanel.style.display === '') {
            advancedSearchPanel.style.display = 'block';
        } else {
            advancedSearchPanel.style.display = 'none';
        }
    });

    // 关闭高级搜索面板
    closeSearchPanel.addEventListener('click', function() {
        advancedSearchPanel.style.display = 'none';
    });

    // 应用高级筛选
    applyFilters.addEventListener('click', function() {
        activeFilters = {
            sequence: getInputValue('filterSequence'),
            project: getInputValue('filterProject'),
            delivery5: getInputValue('filter5Delivery'),
            delivery3: getInputValue('filter3Delivery'),
            modifySeq: getInputValue('filterModifySeq'),
            transcript: getInputValue('filterTranscript'),
            target: getInputValue('filterTarget'),
            pos: getInputValue('filterPos'),
            strandMWs: getInputValue('filterStrandMWs'),
            parents: getInputValue('filterParents'),
            remarks: getInputValue('filterRemarks'),
            asSeqId: getInputValue('filterAsSeqId'),
        };
        table.draw(false);
    });

    // 清除高级筛选
    clearFilters.addEventListener('click', function() {
        document.querySelectorAll('#advancedSearchPanel input').forEach(input => input.value = '');
        activeFilters = {};
        searchInput.value = '';
        table.search('').draw(); // 清除全局搜索
        table.draw(); // 清除高级搜索
    });

    // 获取表单字段的值
    function getInputValue(id) {
        const input = document.getElementById(id);
        return input ? input.value.trim().toLowerCase() : '';
    }
});