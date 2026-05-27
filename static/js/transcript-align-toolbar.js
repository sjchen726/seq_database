/**
 * transcript-align-toolbar.js
 * 为「转录本定位」按钮提供交互：
 * - 有勾选时启用按钮，无勾选时禁用
 * - 点击时收集选中行的 data-rm-code，以 POST 表单提交到 /transcript_align/
 */
(function () {
    var btn = document.getElementById('transcriptAlignBtn');
    if (!btn) return;

    function getCheckedRmCodes() {
        return Array.prototype.map.call(
            document.querySelectorAll('input.row-checkbox:checked'),
            function (cb) { var tr = cb.closest('tr'); return tr ? tr.dataset.rmCode : null; }
        ).filter(Boolean);
    }

    function updateBtn() {
        btn.disabled = getCheckedRmCodes().length === 0;
    }

    document.addEventListener('change', function (e) {
        if (e.target.matches('input.row-checkbox') || e.target.id === 'select-all') {
            updateBtn();
        }
    });

    btn.addEventListener('click', function () {
        var rmCodes = getCheckedRmCodes();
        if (!rmCodes.length) {
            alert('请先勾选至少一条序列');
            return;
        }

        // 去重
        var seen = {};
        var unique = rmCodes.filter(function (c) {
            if (seen[c]) return false;
            seen[c] = true;
            return true;
        });

        if (unique.length > 20) {
            alert('每次最多选择 20 条序列，请减少勾选数量');
            return;
        }

        // 动态表单 POST
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = btn.dataset.url;
        form.style.display = 'none';

        var csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
        if (!csrfMatch) { alert('CSRF 错误，请刷新页面'); return; }

        [
            { name: 'csrfmiddlewaretoken', value: csrfMatch[1] },
            { name: 'step',     value: 'init' },
            { name: 'back_url', value: window.location.href },
        ].forEach(function (f) {
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = f.name;
            inp.value = f.value;
            form.appendChild(inp);
        });

        unique.forEach(function (rmCode) {
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'rm_code';
            inp.value = rmCode;
            form.appendChild(inp);
        });

        document.body.appendChild(form);
        form.submit();
    });
})();
