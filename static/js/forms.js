document.addEventListener('DOMContentLoaded', function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');

    if (!searchBtn || !searchInput) return;

    function doSearch() {
        const query = searchInput.value.trim();
        const url = new URL(window.location.href);
        if (query) {
            url.searchParams.set('q', query);
        } else {
            url.searchParams.delete('q');
        }
        // 清除高级搜索参数，避免冲突
        ['filterSequence','filterNakedSeq','filterSeq','filter5Delivery','filter3Delivery',
         'filterTarget','filterProject','filterSeqType','filterTranscript',
         'filterParents','filterRemarks'].forEach(k => url.searchParams.delete(k));
        window.location.href = url.toString();
    }

    searchBtn.addEventListener('click', function(e) {
        e.preventDefault();
        doSearch();
    });

    searchInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            doSearch();
        }
    });
});