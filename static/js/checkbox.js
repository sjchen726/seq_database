// 控制列的显示和隐藏
document.getElementById('toggleStrandID').addEventListener('change', toggleColumns);
document.getElementById('toggleProject').addEventListener('change', toggleColumns);
document.getElementById('toggleSequences').addEventListener('change', toggleColumns);
document.getElementById('toggleDelivery5').addEventListener('change', toggleColumns);
document.getElementById('toggleDelivery3').addEventListener('change', toggleColumns);
document.getElementById('toggleTranscript').addEventListener('change', toggleColumns);
document.getElementById('toggleTarget').addEventListener('change', toggleColumns);
document.getElementById('togglePos').addEventListener('change', toggleColumns);
document.getElementById('toggleStrandMWs').addEventListener('change', toggleColumns);
document.getElementById('toggleParents').addEventListener('change', toggleColumns);
document.getElementById('toggleRemarks').addEventListener('change', toggleColumns);

function toggleColumns() {
    // 获取复选框状态
    const showStrandID = document.getElementById('toggleStrandID').checked;
    const showProject = document.getElementById('toggleProject').checked;
    const showSequences = document.getElementById('toggleSequences').checked;
    const showDelivery5 = document.getElementById('toggleDelivery5').checked;
    const showDelivery3 = document.getElementById('toggleDelivery3').checked;
    const showTranscript = document.getElementById('toggleTranscript').checked;
    const showTarget = document.getElementById('toggleTarget').checked;
    const showPos = document.getElementById('togglePos').checked;
    const showStrandMWs = document.getElementById('toggleStrandMWs').checked;
    const showParents = document.getElementById('toggleParents').checked;
    const showRemarks = document.getElementById('toggleRemarks').checked;

    // 控制每列的显示与隐藏
    toggleColumnVisibility('strandID', showStrandID);
    toggleColumnVisibility('project', showProject);
    toggleColumnVisibility('sequences', showSequences);
    toggleColumnVisibility('delivery5', showDelivery5);
    toggleColumnVisibility('delivery3', showDelivery3);
    toggleColumnVisibility('transcript', showTranscript);
    toggleColumnVisibility('target', showTarget);
    toggleColumnVisibility('pos', showPos);
    toggleColumnVisibility('strandMWs', showStrandMWs);
    toggleColumnVisibility('parents', showParents);
    toggleColumnVisibility('remarks', showRemarks);
}

function toggleColumnVisibility(className, show) {
    const columns = document.querySelectorAll('.' + className);
    columns.forEach(column => {
        column.style.display = show ? '' : 'none';
    });
}