let currentResults = [];
let currentIndex = 0;
let currentOriginal = '';

const inputText = document.getElementById('input-text');
const rewriteBtn = document.getElementById('rewrite-btn');
const resultsDiv = document.getElementById('results');
const diffContent = document.getElementById('diff-content');
const plainTextDiv = document.getElementById('plain-text');
const sampleIndex = document.getElementById('sample-index');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const statusBar = document.getElementById('status-bar');
const statusText = document.getElementById('status-text');
const charCountDisplay = document.getElementById('char-count-display');
const remainingInfo = document.getElementById('remaining-info');
const remainingDisplay = document.getElementById('remaining-display');

inputText.addEventListener('input', function () {
    const chars = countChars(this.value);
    charCountDisplay.textContent = chars + ' 字';
});

function countChars(text) {
    return text.replace(/[\s\n\r\t]/g, '').length;
}

async function doRewrite() {
    const text = inputText.value.trim();
    if (!text) {
        showError('请输入要润色的文本');
        return;
    }

    rewriteBtn.disabled = true;
    rewriteBtn.textContent = '润色中';
    showStatus('正在调用润色服务');
    resultsDiv.classList.add('hidden');
    statusBar.classList.remove('hidden');

    const formData = new FormData();
    formData.append('text', text);
    formData.append('n', 8);

    try {
        const resp = await fetch('/rewrite', { method: 'POST', body: formData });
        const data = await resp.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        currentResults = data.rewritten;
        currentIndex = 0;
        currentOriginal = data.original;

        displayResult(0);
        updateStatusBar(data);
        resultsDiv.classList.remove('hidden');
        statusBar.classList.add('hidden');
    } catch (e) {
        showError('网络错误，请检查连接');
    } finally {
        rewriteBtn.disabled = false;
        rewriteBtn.textContent = '开始润色';
    }
}

function displayResult(index) {
    const rewritten = currentResults[index];
    const html = renderDiff(currentOriginal, rewritten);
    diffContent.innerHTML = html;
    plainTextDiv.textContent = rewritten;
    sampleIndex.textContent = (index + 1) + '/' + currentResults.length;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === currentResults.length - 1;
}

function renderDiff(original, rewritten) {
    const diff = Diff.diffWords(original, rewritten);
    let html = '';
    diff.forEach(function (part) {
        const value = escapeHtml(part.value);
        if (part.added) {
            html += '<ins>' + value + '</ins>';
        } else if (part.removed) {
            html += '<del>' + value + '</del>';
        } else {
            html += '<span class="unchanged">' + value + '</span>';
        }
    });
    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function navigate(delta) {
    const newIndex = currentIndex + delta;
    if (newIndex >= 0 && newIndex < currentResults.length) {
        currentIndex = newIndex;
        displayResult(newIndex);
    }
}

function updateStatusBar(data) {
    const remaining = data.remaining;
    if (remainingDisplay) {
        remainingDisplay.textContent = remaining;
    }
    if (remainingInfo) {
        remainingInfo.textContent = '剩余 ' + remaining + ' 字';
    }
}

function showStatus(msg) {
    statusBar.classList.remove('hidden');
    statusText.textContent = msg;
    statusText.style.color = '#6b5a3e';
}

function showError(msg) {
    statusBar.classList.remove('hidden');
    statusText.textContent = msg;
    statusText.style.color = '#dc2626';
    resultsDiv.classList.add('hidden');
}
