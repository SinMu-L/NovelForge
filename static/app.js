let results = [];
let selectedIndex = 0;
let currentOriginal = '';
let SAMPLE_COUNT = 8;

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
const sampleStatus = document.getElementById('sample-status');

inputText.addEventListener('input', function () {
    const chars = countChars(this.value);
    charCountDisplay.textContent = chars + ' 字';
});

function countChars(text) {
    return text.replace(/[\s\n\r\t]/g, '').length;
}

function sanitizeToken(token) {
    token = token.replace(/[\u200B-\u200D\uFEFF\u2060\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
    if (!token) return '';
    if (token.includes('\uFFFD')) return '';
    if (/[\uD800-\uDFFF]/.test(token)) return '';
    if (token.length >= 20 && new Set(token).size <= 1) return '';
    if (token.length >= 5) {
        let unusualCount = 0;
        for (const ch of token) {
            const code = ch.charCodeAt(0);
            const isNormal =
                (code >= 0x4E00 && code <= 0x9FFF) ||
                (code >= 0x3400 && code <= 0x4DBF) ||
                (code >= 0x0020 && code <= 0x007E) ||
                (code === 0x000A || code === 0x000D) ||
                (code >= 0x3000 && code <= 0x303F) ||
                (code >= 0xFF00 && code <= 0xFFEF) ||
                (code >= 0x2000 && code <= 0x206F);
            if (!isNormal) unusualCount++;
        }
        if (unusualCount / token.length > 0.4) return '';
    }
    return token;
}

function isTextGarbled(text) {
    if (!text || !text.trim()) return false;
    const cleaned = sanitizeToken(text);
    return !cleaned;
}

function createBadges(count) {
    sampleStatus.innerHTML = '';
    for (let i = 0; i < count; i++) {
        const badge = document.createElement('span');
        badge.className = 'sample-badge';
        badge.dataset.index = i;
        badge.textContent = i + 1;
        badge.addEventListener('click', () => selectSample(i));
        sampleStatus.appendChild(badge);
    }
}

function updateBadge(index) {
    const r = results[index];
    const badge = sampleStatus.querySelector(`[data-index="${index}"]`);
    if (!badge) return;
    badge.className = 'sample-badge';
    if (r.truncated) {
        badge.classList.add('truncated');
        badge.textContent = index + 1 + '⚠';
    } else if (r.garbled) {
        badge.classList.add('garbled');
        badge.textContent = index + 1 + '✗';
    } else if (r.done) {
        badge.classList.add('done');
        badge.textContent = index + 1 + '✓';
    } else if (r.text) {
        badge.classList.add('streaming');
        badge.textContent = index + 1 + '…';
    } else {
        badge.textContent = index + 1;
    }
    if (index === selectedIndex) {
        badge.classList.add('active');
    }
}

function selectSample(index) {
    if (index < 0 || index >= results.length) return;
    selectedIndex = index;
    displaySelected();
    updateBadge(index);
    updateNavButtons();
}

function displaySelected() {
    const r = results[selectedIndex];
    sampleIndex.textContent = (selectedIndex + 1) + '/' + results.length;
    if (r.truncated) {
        const content = r.fullText || r.text;
        currentOriginal = currentOriginal || inputText.value.trim();
        const html = renderDiff(currentOriginal, content);
        diffContent.innerHTML = html + '<div style="margin-top:8px;padding:6px 10px;background:#fef9e7;border-radius:6px;color:#92400e;font-size:13px;">⚠ 该结果文本过长，已自动截断</div>';
        plainTextDiv.textContent = content;
    } else if (r.done && !r.garbled) {
        currentOriginal = currentOriginal || inputText.value.trim();
        const html = renderDiff(currentOriginal, r.fullText || r.text);
        diffContent.innerHTML = html;
        plainTextDiv.textContent = r.fullText || r.text;
    } else if (r.text) {
        diffContent.innerHTML = '';
        plainTextDiv.textContent = r.text;
    } else if (r.garbled) {
        diffContent.innerHTML = '<span style="color:#dc2626;">该结果存在乱码，已标记为失败</span>';
        plainTextDiv.textContent = '';
    } else {
        diffContent.innerHTML = '<span style="color:#8b7355;">等待生成中…</span>';
        plainTextDiv.textContent = '';
    }
}

function updateNavButtons() {
    prevBtn.disabled = selectedIndex <= 0;
    nextBtn.disabled = selectedIndex >= results.length - 1;
}

function navigate(delta) {
    const newIndex = selectedIndex + delta;
    if (newIndex >= 0 && newIndex < results.length) {
        selectSample(newIndex);
    }
}

async function doRewrite() {
    const text = inputText.value.trim();
    if (!text) {
        showError('请输入要润色的文本');
        return;
    }

    rewriteBtn.disabled = true;
    rewriteBtn.textContent = '润色中';
    showStatus('正在生成...');
    resultsDiv.classList.remove('hidden');
    statusBar.classList.remove('hidden');

    diffContent.innerHTML = '';
    plainTextDiv.textContent = '';

    const formData = new FormData();
    formData.append('text', text);
    formData.append('n', SAMPLE_COUNT);

    currentOriginal = text;
    results = Array.from({ length: SAMPLE_COUNT }, () => ({
        text: '', done: false, garbled: false, truncated: false, error: '', fullText: ''
    }));
    selectedIndex = 0;
    createBadges(SAMPLE_COUNT);
    updateBadge(0);
    displaySelected();
    updateNavButtons();

    try {
        const resp = await fetch('/rewrite', { method: 'POST', body: formData });

        if (!resp.ok) {
            const data = await resp.json();
            showError(data.error);
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed.startsWith('data: ')) continue;
                const dataStr = trimmed.slice(6);
                try {
                    const data = JSON.parse(dataStr);
                    if (data.error && data.index === undefined) {
                        showError(data.error);
                        continue;
                    }
                    const idx = data.index;
                    if (data.token !== undefined) {
                        const cleaned = sanitizeToken(data.token);
                        if (cleaned) {
                            results[idx].text += cleaned;
                        } else if (!results[idx].text) {
                            results[idx].text += data.token;
                        }
                        if (results[idx].text) {
                            if (idx === selectedIndex) {
                                plainTextDiv.textContent = results[idx].text;
                            }
                            updateBadge(idx);
                        }
                    } else if (data.done) {
                        results[idx].done = true;
                        results[idx].fullText = data.full_text || '';
                        results[idx].error = data.error || '';
                        results[idx].truncated = data.truncated || false;
                        if (!results[idx].error && !results[idx].truncated && isTextGarbled(results[idx].fullText)) {
                            results[idx].garbled = true;
                        }
                        if (data.remaining !== undefined) {
                            updateRemaining(data.remaining);
                        }
                        updateBadge(idx);
                        if (idx === selectedIndex) {
                            displaySelected();
                        }
                    }
                } catch (e) {
                    // ignore parse errors
                }
            }
        }

        statusBar.classList.add('hidden');
        if (results.some(r => r.done)) {
            if (results[selectedIndex].garbled || (!results[selectedIndex].done && !results[selectedIndex].text)) {
                const firstValid = results.findIndex(r => r.done && !r.garbled);
                if (firstValid >= 0) {
                    selectSample(firstValid);
                } else {
                    const firstTruncated = results.findIndex(r => r.truncated);
                    if (firstTruncated >= 0) selectSample(firstTruncated);
                }
            }
        }
    } catch (e) {
        showError('网络错误，请检查连接');
    } finally {
        rewriteBtn.disabled = false;
        rewriteBtn.textContent = '开始润色';
    }
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

function updateRemaining(remaining) {
    if (remainingDisplay) remainingDisplay.textContent = remaining;
    if (remainingInfo) remainingInfo.textContent = '剩余 ' + remaining + ' 字';
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
