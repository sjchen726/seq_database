document.addEventListener('DOMContentLoaded', function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');
    const advancedSearchBtn = document.getElementById('advancedSearchBtn');
    const advancedSearchPanel = document.getElementById('advancedSearchPanel');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    const closeSearchPanel = document.getElementById('closeSearchPanel');

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
        // const cells = Array.from(row.querySelectorAll('td')).map(cell => cell.textContent.toLowerCase());
        const cells = Array.from(row.querySelectorAll('td')).map(cell => cell.textContent.toLowerCase());
        console.log(cells); // 打印每一行的单元格数据，检查是否有 Target 数据


        // **获取 data-modify-seq 的值**
        const modifySeqCell = row.querySelector('td div[data-modify-seq]'); // 获取嵌套在 div 中的 data-modify-seq
        let modifySeqData = modifySeqCell ? modifySeqCell.getAttribute('data-modify-seq').toLowerCase() : '';
        console.log('modifySeqData:', modifySeqData); // 打印 modifySeqData，检查是否正确获取


        // **处理 modifySeq 数据：移除 "o" 和 "s" 字符**
        modifySeqData = modifySeqData.replace(/[osf]/g, ''); // 移除 'o', 's', 'f'
        modifySeqData = modifySeqData.replace(/\s/g, ''); // 移除空格
        // console.log(modifySeqData); // 打印 modifySeqData，检查是否正确处理  
        console.log('modifySeqData111:', modifySeqData); // 输出 modifySeqData 进行调试

        // **普通搜索**
        if (filters.query) {
            const queryList = filters.query.split(',').map(q => q.trim().toLowerCase()); // 多个查询值
            const match = cells.some(cellText => queryList.some(query => cellText.includes(query))) || queryList.some(query => modifySeqData.includes(query));
            row.style.display = match ? '' : 'none';
            return;
        }

        // **高级搜索**
        const match = Object.entries(filters).every(([key, value]) => {
            if (!value) return true; // 跳过空值
            const queryList = value.split(',').map(q => q.trim().toLowerCase()); // 多个查询值

            // **匹配 modifySeq**
            if (key === 'modifySeq') {
                const modifiedValue = queryList.map(v => v.replace(/[ofs\s]/g, '')); // Clean up input value
                return modifiedValue.some(val => modifySeqData.includes(val)); // Match against modifySeqData
            }


            // 对其他字段进行普通匹配
            return queryList.some(query => cells.some(cellText => cellText.includes(query)));
        });

        row.style.display = match ? '' : 'none';
    });
}