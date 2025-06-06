document.addEventListener('DOMContentLoaded', function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');
    const advancedSearchBtn = document.getElementById('advancedSearchBtn');
    const advancedSearchPanel = document.getElementById('advancedSearchPanel');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    const closeSearchPanel = document.getElementById('closeSearchPanel');
    const panel = document.getElementById("advancedSearchPanel");
    const handle = document.getElementById("dragHandle");
    if (panel && handle) {
        makeDraggable(panel, handle);
    }

    // **普通搜索**
    searchBtn.addEventListener('click', function() {
        const query = searchInput.value.trim().toLowerCase();
        searchTable({ query });
    });

    // **按下 Enter 键触发搜索**
    searchInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            searchBtn.click();
        }
    });

    // **显示/隐藏高级搜索面板**
    advancedSearchBtn.addEventListener('click', function() {
        advancedSearchPanel.style.display = advancedSearchPanel.style.display === 'none' ? 'block' : 'none';
    });

    // **关闭高级搜索面板**
    closeSearchPanel.addEventListener('click', function() {
        advancedSearchPanel.style.display = 'none';
    });

    // **应用高级筛选**
    applyFilters.addEventListener('click', function() {
        const filters = {
            sequence: getInputValue('filterSequence'),
            project: getInputValue('filterProject'),
            delivery5: getInputValue('filter5Delivery'),
            delivery3: getInputValue('filter3Delivery'),
            Seq: getInputValue('filterSeq'),
            modifySeq: getInputValue('filterModifySeq'),
            transcript: getInputValue('filterTranscript'),
            target: getInputValue('filterTarget'),
            pos: getInputValue('filterPos'),
            strandMWs: getInputValue('filterStrandMWs'),
            parents: getInputValue('filterParents'),
            remarks: getInputValue('filterRemarks'),
            seqType: getInputValue('filterAsSeqtype')
        };

        // console.log(filters); // 在控制台打印所有筛选器的值，查看是否捕获到 Target 值

        searchTable(filters);
    });

    // **清除筛选**
    clearFilters.addEventListener('click', function() {
        document.querySelectorAll('#advancedSearchPanel input').forEach(input => input.value = '');
        searchTable({}); // 重新加载所有数据
    });
});

// **获取输入框的值，并转换为小写**
function getInputValue(id) {
    const input = document.getElementById(id);
    return input ? input.value.trim().toLowerCase() : '';
}

// **表格搜索逻辑**
function searchTable(filters = {}) {
    const table = document.getElementById('example');
    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        const cells = Array.from(row.querySelectorAll('td')).map(cell => cell.textContent.toLowerCase());

        // 获取裸序列（来自 data-modify-seq）
        const modifySeqCell = row.querySelector('td div[data-modify-seq]');
        const nakedSeq = modifySeqCell ? modifySeqCell.getAttribute('data-modify-seq').toLowerCase().trim() : '';

        // 获取修饰序列（由 span.seq-container 拼接）
        let fullModifiedSeq = '';
        let compressedModifiedSeq = '';
        if (modifySeqCell) {
            const spanElems = modifySeqCell.querySelectorAll('span.seq-container');
            const fragments = Array.from(spanElems).map(span => span.textContent.trim());
            fullModifiedSeq = fragments.join(' ').toLowerCase(); // 带空格显示用
            compressedModifiedSeq = fragments.join('').toLowerCase(); // 去除空格，用于搜索
        }

        // 普通搜索
        if (filters.query) {
            const queryList = filters.query.split(',').map(q => q.trim().toLowerCase());
            const match =
                cells.some(cellText => queryList.some(query => cellText.includes(query))) ||
                queryList.some(query => nakedSeq.includes(query)) ||
                queryList.some(query => fullModifiedSeq.includes(query));
            row.style.display = match ? '' : 'none';
            return;
        }

        // 高级搜索
        const match = Object.entries(filters).every(([key, value]) => {
            if (!value) return true;
            const queryList = value.split(',').map(q => q.trim().toLowerCase());

            if (key === 'Seq') {
                return queryList.some(query => nakedSeq.includes(query));
            }

            if (key === 'modifySeq') {
                return queryList.every(query => compressedModifiedSeq.includes(query));
            }


            return queryList.some(query => cells.some(cellText => cellText.includes(query)));
        });

        row.style.display = match ? '' : 'none';
    });

}