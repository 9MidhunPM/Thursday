/* ============================================================
   Thursday Web — v2 Frontend
   Conversation management, streaming, stats, thinking indicator.
   Vanilla JS. No frameworks.
   ============================================================ */

const API = '';

// ---- DOM refs ----
const sidebar          = document.getElementById('sidebar');
const convList         = document.getElementById('conversation-list');
const btnNewChat       = document.getElementById('btn-new-chat');
const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
const btnOpenSidebar   = document.getElementById('btn-open-sidebar');
const btnMemorySidebar = document.getElementById('btn-memory-sidebar');
const chatMessages     = document.getElementById('chat-messages');
const chatContainer    = document.getElementById('chat-container');
const chatTitle        = document.getElementById('chat-title');
const welcomeScreen    = document.getElementById('welcome-screen');
const thinkingEl       = document.getElementById('thinking-indicator');
const userInput        = document.getElementById('user-input');
const btnSend          = document.getElementById('btn-send');
const modeBadge        = document.getElementById('mode-badge');
const modeBadgeText    = document.getElementById('mode-badge-text');
const statusDot        = document.getElementById('status-dot');
const statusText       = document.getElementById('status-text');
const memoryModal      = document.getElementById('memory-modal');
const memoryList       = document.getElementById('memory-list');
const modalClose       = document.getElementById('modal-close');
const modalBackdrop    = memoryModal.querySelector('.modal-backdrop');

// Stats elements
const statTokens       = document.getElementById('stat-tokens');
const statSpeed        = document.getElementById('stat-speed');
const statElapsed      = document.getElementById('stat-elapsed');
const statTTFT         = document.getElementById('stat-ttft');

// Live stats state
let liveStats = { startTime: 0, firstTokenTime: 0, tokenCount: 0, inputTokens: 0, elapsedTimer: null };

// ---- State ----
let isStreaming = false;
let activeConversationId = null;
let conversations = [];
let localMessages = [];  // messages for current view (used for raw mode)

// ============================================================
// INIT
// ============================================================

async function init() {
    checkHealth();
    setInterval(checkHealth, 30000);

    // Event listeners
    btnNewChat.addEventListener('click', createNewChat);
    btnToggleSidebar.addEventListener('click', toggleSidebar);
    btnOpenSidebar.addEventListener('click', toggleSidebar);
    btnSend.addEventListener('click', sendMessage);
    btnMemorySidebar.addEventListener('click', openMemoryModal);
    userInput.addEventListener('keydown', handleKeyDown);
    userInput.addEventListener('input', onInputChange);
    modalClose.addEventListener('click', closeMemoryModal);
    modalBackdrop.addEventListener('click', closeMemoryModal);

    // Chips
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            userInput.value = chip.dataset.prompt;
            onInputChange();
            sendMessage();
        });
    });

    onInputChange();
    await loadConversations();

    // Open most recent conversation
    if (conversations.length > 0) {
        await switchConversation(conversations[0].id);
    }
}

// ============================================================
// HEALTH
// ============================================================

async function checkHealth() {
    try {
        const r = await fetch(`${API}/health`);
        const d = await r.json();
        const ok = d.llama_server === 'ok';
        statusDot.className = `status-dot ${ok ? 'connected' : 'disconnected'}`;
        statusText.textContent = ok ? 'llama-server connected' : 'llama-server unreachable';
    } catch {
        statusDot.className = 'status-dot disconnected';
        statusText.textContent = 'Proxy unreachable';
    }
}



// ============================================================
// SIDEBAR
// ============================================================

function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
}

// ============================================================
// CONVERSATIONS
// ============================================================

async function loadConversations() {
    try {
        const r = await fetch(`${API}/v1/conversations`);
        const d = await r.json();
        conversations = d.conversations || [];
        renderConversationList();
    } catch {
        conversations = [];
        renderConversationList();
    }
}

// Retry wrapper — polls until the conversation list includes a given id
async function ensureConversationVisible(convId, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
        await loadConversations();
        if (conversations.some(c => c.id === convId)) return;
        await new Promise(r => setTimeout(r, 300));
    }
}

function renderConversationList() {
    convList.innerHTML = '';

    if (conversations.length === 0) {
        convList.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:0.8rem;">No conversations yet</div>';
        return;
    }

    // Group by relative date
    const groups = groupByDate(conversations);

    for (const [label, convs] of Object.entries(groups)) {
        const groupEl = document.createElement('div');
        groupEl.className = 'conv-date-group';
        groupEl.textContent = label;
        convList.appendChild(groupEl);

        for (const conv of convs) {
            const item = document.createElement('div');
            item.className = `conv-item ${conv.id === activeConversationId ? 'active' : ''}`;
            item.dataset.id = conv.id;
            item.innerHTML = `
                <svg class="conv-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                <span class="conv-title">${escapeHtml(conv.title)}</span>
                <button class="conv-delete" title="Delete" data-id="${conv.id}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete')) return;
                switchConversation(conv.id);
            });

            item.querySelector('.conv-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
            });

            convList.appendChild(item);
        }
    }
}

function groupByDate(convs) {
    const groups = {};
    const now = Date.now() / 1000;
    const dayS = 86400;

    for (const c of convs) {
        const age = now - c.updated_at;
        let label;
        if (age < dayS) label = 'Today';
        else if (age < 2 * dayS) label = 'Yesterday';
        else if (age < 7 * dayS) label = 'Previous 7 days';
        else if (age < 30 * dayS) label = 'Previous 30 days';
        else label = 'Older';

        if (!groups[label]) groups[label] = [];
        groups[label].push(c);
    }
    return groups;
}

async function createNewChat() {
    try {
        const r = await fetch(`${API}/v1/conversations`, { method: 'POST' });
        const conv = await r.json();
        conversations.unshift(conv);
        activeConversationId = conv.id;
        renderConversationList();
        clearChatUI();
        chatTitle.textContent = 'New Chat';
        showWelcome(true);
        userInput.focus();
    } catch {
        // fallback
    }
}

async function switchConversation(convId) {
    if (convId === activeConversationId && chatMessages.querySelector('.message')) return;

    activeConversationId = convId;
    renderConversationList();

    // Load messages from server
    try {
        const r = await fetch(`${API}/v1/conversations/${convId}`);
        const d = await r.json();
        clearChatUI();

        const conv = conversations.find(c => c.id === convId);
        chatTitle.textContent = conv ? conv.title : 'Chat';

        if (d.messages && d.messages.length > 0) {
            showWelcome(false);
            localMessages = [...d.messages];
            for (const msg of d.messages) {
                appendMessage(msg.role, msg.content);
            }
            scrollToBottom();
        } else {
            localMessages = [];
            showWelcome(true);
        }
    } catch {
        // silent
    }

    hideStats();
    userInput.focus();
}

async function deleteConversation(convId) {
    try {
        await fetch(`${API}/v1/conversations/${convId}`, { method: 'DELETE' });
        conversations = conversations.filter(c => c.id !== convId);
        renderConversationList();

        if (convId === activeConversationId) {
            activeConversationId = null;
            clearChatUI();
            showWelcome(true);
            chatTitle.textContent = 'Thursday';
        }
    } catch {
        // silent
    }
}

// ============================================================
// SEND MESSAGE
// ============================================================

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isStreaming) return;

    const mode = 'thursday';

    // Auto-create conversation if needed
    if (!activeConversationId) {
        await createNewChat();
    }

    showWelcome(false);
    appendMessage('user', text);
    localMessages.push({ role: 'user', content: text });

    userInput.value = '';
    onInputChange();
    setStreaming(true);
    showThinking(true);

    // Prepare request
    const body = {
        messages: localMessages,
        mode: mode,
        conversation_id: activeConversationId,
        stream: true,
        temperature: 0.7,
        max_tokens: 512,
    };

    // --- Live stats setup ---
    liveStats.startTime = performance.now();
    liveStats.firstTokenTime = 0;
    liveStats.tokenCount = 0;
    liveStats.inputTokens = estimateTokens(text);
    showLiveStats();
    startElapsedTimer();

    // Create assistant message element with inline thinking
    const msgEl = appendMessage('assistant', '', true);
    const contentEl = msgEl.querySelector('.message-content');
    contentEl.innerHTML = '<span class="inline-thinking"><span class="inline-thinking-text">Thinking</span></span>';
    let inlineThinkingTimer = startInlineThinking(contentEl.querySelector('.inline-thinking-text'));
    scrollToBottom();

    try {
        const resp = await fetch(`${API}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        showThinking(false);

        if (!resp.ok) {
            contentEl.textContent = `[Error: HTTP ${resp.status}]`;
            msgEl.classList.remove('streaming');
            setStreaming(false);
            stopElapsedTimer();
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = line.slice(6).trim();
                if (data === '[DONE]') continue;

                try {
                    const chunk = JSON.parse(data);
                    const token = chunk.choices?.[0]?.delta?.content || '';

                    if (token) {
                        liveStats.tokenCount++;
                        if (!liveStats.firstTokenTime) {
                            liveStats.firstTokenTime = performance.now();
                            updateStatTTFT();
                            // Stop inline thinking dots
                            if (inlineThinkingTimer) {
                                clearInterval(inlineThinkingTimer);
                                inlineThinkingTimer = null;
                            }
                        }
                        fullText += token;
                        contentEl.innerHTML = renderMarkdown(fullText);
                        injectStreamingCursor(contentEl);
                        updateStatTokensAndSpeed();
                        scrollToBottom();
                    }
                } catch { /* skip */ }
            }
        }

        // Finalize
        stopElapsedTimer();
        msgEl.classList.remove('streaming');
        contentEl.innerHTML = renderMarkdown(fullText);
        localMessages.push({ role: 'assistant', content: fullText });

        // Add action buttons now that streaming is done
        const msgBody = msgEl.querySelector('.message-body');
        if (msgBody) {
            msgBody.insertAdjacentHTML('beforeend', buildActionButtons());
            wireActionButtons(msgEl);
        }

        // Final stats snapshot
        finalizeStats(fullText);

        // Refresh conversation list (title may have been auto-set)
        if (mode === 'thursday' && activeConversationId) {
            await ensureConversationVisible(activeConversationId);
            const conv = conversations.find(c => c.id === activeConversationId);
            if (conv) chatTitle.textContent = conv.title;
        }

    } catch (err) {
        showThinking(false);
        stopElapsedTimer();
        if (inlineThinkingTimer) { clearInterval(inlineThinkingTimer); inlineThinkingTimer = null; }
        contentEl.textContent = `[Error: ${err.message}]`;
        msgEl.classList.remove('streaming');
    } finally {
        setStreaming(false);
        scrollToBottom();
    }
}

// ============================================================
// UI HELPERS
// ============================================================

function appendMessage(role, text, streaming = false) {
    const msg = document.createElement('div');
    msg.className = `message ${role}${streaming ? ' streaming' : ''}`;

    if (role === 'user') {
        msg.innerHTML = `<div class="user-bubble">${text ? escapeHtml(text) : ''}</div>`;
    } else {
        msg.innerHTML = `
            <div class="message-avatar">T</div>
            <div class="message-body">
                <div class="message-role">Thursday</div>
                <div class="message-content">${text ? renderMarkdown(text) : ''}</div>
                ${!streaming ? buildActionButtons() : ''}
            </div>
        `;
        if (!streaming) wireActionButtons(msg);
    }

    chatMessages.appendChild(msg);
    scrollToBottom();
    return msg;
}

function buildActionButtons() {
    return `
        <div class="message-actions">
            <button class="msg-action-btn action-copy" title="Copy">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button class="msg-action-btn action-regen" title="Regenerate">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
        </div>
    `;
}

function wireActionButtons(msgEl) {
    const copyBtn = msgEl.querySelector('.action-copy');
    const regenBtn = msgEl.querySelector('.action-regen');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const content = msgEl.querySelector('.message-content');
            const text = content ? content.innerText : '';
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
                setTimeout(() => {
                    copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                }, 2000);
            });
        });
    }
    if (regenBtn) {
        regenBtn.addEventListener('click', () => {
            // Remove this assistant message and resend the last user message
            const allMsgs = chatMessages.querySelectorAll('.message');
            if (allMsgs.length < 1) return;
            // Remove the assistant message
            msgEl.remove();
            // Pop assistant message from local
            if (localMessages.length && localMessages[localMessages.length - 1].role === 'assistant') {
                localMessages.pop();
            }
            // Re-send
            const lastUserMsg = localMessages.filter(m => m.role === 'user').pop();
            if (lastUserMsg) {
                // Pop the user message too so sendMessage re-adds it
                localMessages.pop();
                userInput.value = lastUserMsg.content;
                onInputChange();
                sendMessage();
            }
        });
    }
}

function clearChatUI() {
    // Remove all messages but keep welcome
    const msgs = chatMessages.querySelectorAll('.message');
    msgs.forEach(m => m.remove());
}

function showWelcome(show) {
    if (welcomeScreen) {
        welcomeScreen.style.display = show ? 'flex' : 'none';
    }
}

let thinkingDotsTimer = null;

function showThinking(show) {
    if (show) {
        thinkingEl.classList.remove('hidden');
        scrollToBottom();
        startThinkingDots();
    } else {
        thinkingEl.classList.add('hidden');
        stopThinkingDots();
    }
}

function startThinkingDots() {
    stopThinkingDots();
    const dotsEl = thinkingEl.querySelector('.thinking-dots-text');
    let count = 0;
    dotsEl.textContent = '';
    thinkingDotsTimer = setInterval(() => {
        count = (count + 1) % 4;
        dotsEl.textContent = '.'.repeat(count || 0);
    }, 400);
}

function stopThinkingDots() {
    if (thinkingDotsTimer) {
        clearInterval(thinkingDotsTimer);
        thinkingDotsTimer = null;
    }
}

function startInlineThinking(el) {
    let count = 0;
    el.textContent = 'Thinking';
    return setInterval(() => {
        count = (count + 1) % 4;
        el.textContent = 'Thinking' + '.'.repeat(count);
    }, 400);
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function injectStreamingCursor(contentEl) {
    // Remove any old cursor
    const old = contentEl.querySelector('.streaming-cursor');
    if (old) old.remove();

    // Don't put cursor inside code blocks
    const lastChild = contentEl.lastElementChild;
    if (lastChild && lastChild.classList.contains('code-block-wrapper')) return;

    // Find the deepest last text-containing element and append cursor there
    let target = contentEl;
    while (target.lastElementChild &&
           !target.lastElementChild.classList.contains('code-block-wrapper') &&
           target.lastElementChild.tagName !== 'BR') {
        target = target.lastElementChild;
    }

    const cursor = document.createElement('span');
    cursor.className = 'streaming-cursor';
    target.appendChild(cursor);
}

function setStreaming(val) {
    isStreaming = val;
    btnSend.disabled = val || userInput.value.trim().length === 0;
    if (!val) userInput.focus();
}

function onInputChange() {
    autoResize();
    btnSend.disabled = isStreaming || userInput.value.trim().length === 0;
}

function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// ============================================================
// LIVE STATS
// ============================================================

function showLiveStats() {
    statTokens.classList.remove('hidden');
    statSpeed.classList.remove('hidden');
    statElapsed.classList.remove('hidden');
    statTTFT.classList.remove('hidden');

    statTokens.querySelector('.stat-value').textContent = '0';
    statSpeed.querySelector('.stat-value').textContent = '--';
    statElapsed.querySelector('.stat-value').textContent = '0.0s';
    statTTFT.querySelector('.stat-value').textContent = '--';

    // Reset tooltips
    statTokens.dataset.tooltip = '';
    statSpeed.dataset.tooltip = '';
    statElapsed.dataset.tooltip = '';
    statTTFT.dataset.tooltip = '';
}

function updateStatTokensAndSpeed() {
    const { tokenCount, firstTokenTime } = liveStats;
    statTokens.querySelector('.stat-value').textContent = tokenCount;

    if (firstTokenTime && tokenCount > 1) {
        const genTime = (performance.now() - firstTokenTime) / 1000;
        const tokPerSec = ((tokenCount - 1) / genTime).toFixed(1);
        statSpeed.querySelector('.stat-value').textContent = tokPerSec;
    }
}

function updateStatTTFT() {
    const ttft = liveStats.firstTokenTime - liveStats.startTime;
    statTTFT.querySelector('.stat-value').textContent = formatMs(ttft);
    statTTFT.dataset.tooltip = `Time To First Token: ${ttft.toFixed(0)}ms\nTime from request sent to first token received.\nIncludes prompt processing by the model.`;
}

function startElapsedTimer() {
    stopElapsedTimer();
    liveStats.elapsedTimer = setInterval(() => {
        const elapsed = performance.now() - liveStats.startTime;
        statElapsed.querySelector('.stat-value').textContent = formatMs(elapsed);
    }, 100);
}

function stopElapsedTimer() {
    if (liveStats.elapsedTimer) {
        clearInterval(liveStats.elapsedTimer);
        liveStats.elapsedTimer = null;
    }
}

function finalizeStats(fullText) {
    const now = performance.now();
    const { startTime, firstTokenTime, tokenCount, inputTokens } = liveStats;
    const totalTime = now - startTime;
    const genTime = firstTokenTime ? (now - firstTokenTime) / 1000 : 0;
    const ttft = firstTokenTime ? firstTokenTime - startTime : 0;
    const tokPerSec = (tokenCount > 1 && genTime > 0) ? ((tokenCount - 1) / genTime).toFixed(1) : '--';
    const promptTokPerSec = (inputTokens > 0 && ttft > 0) ? (inputTokens / (ttft / 1000)).toFixed(1) : '--';
    const outputChars = fullText ? fullText.length : 0;

    // Final display values
    statElapsed.querySelector('.stat-value').textContent = formatMs(totalTime);

    // Hover tooltips with detailed info
    statTokens.dataset.tooltip = [
        `Generated Tokens: ${tokenCount}`,
        `Est. Input Tokens: ~${inputTokens}`,
        `Output Characters: ${outputChars}`,
        `Approx ratio: ${outputChars ? (outputChars / tokenCount).toFixed(1) : '--'} chars/token`,
    ].join('\n');

    statSpeed.dataset.tooltip = [
        `Generation Speed: ${tokPerSec} tokens/sec`,
        `Est. Prompt Speed: ~${promptTokPerSec} tokens/sec`,
        `Gen time (after first token): ${genTime.toFixed(2)}s`,
        `Tokens generated: ${tokenCount}`,
    ].join('\n');

    statElapsed.dataset.tooltip = [
        `Total Response Time: ${totalTime.toFixed(0)}ms`,
        `TTFT: ${ttft.toFixed(0)}ms`,
        `Generation: ${(genTime * 1000).toFixed(0)}ms`,
        `TTFT is ${totalTime > 0 ? ((ttft / totalTime) * 100).toFixed(0) : 0}% of total time`,
    ].join('\n');
}

function hideStats() {
    statTokens.classList.add('hidden');
    statSpeed.classList.add('hidden');
    statElapsed.classList.add('hidden');
    statTTFT.classList.add('hidden');
}

function formatMs(ms) {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}

function estimateTokens(text) {
    return Math.max(1, Math.round(text.length / 4));
}

// ============================================================
// MARKDOWN RENDERER
// ============================================================

function renderMarkdown(text) {
    if (!text) return '';

    // Strip [REMIND: ...] tags and replace with a visual badge
    let reminderBadges = '';
    const remindTagRe = /\[REMIND:\s*(.+?)\s*\|\s*(.+?)\s*\]/gi;
    const remindMatches = [...text.matchAll(remindTagRe)];
    for (const m of remindMatches) {
        reminderBadges += `<div class="reminder-badge">⏰ Reminder set: ${escapeHtml(m[2])}</div>`;
    }
    text = text.replace(remindTagRe, '').trim();

    // Extract COMPLETE code blocks first: ```lang\n...\n```
    const codeBlocks = [];
    let processed = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        const placeholder = `%%CODEBLOCK_${codeBlocks.length}%%`;
        codeBlocks.push({ lang: lang || '', code: code, partial: false });
        return placeholder;
    });

    // Check for an INCOMPLETE code block (opening ``` with no closing ```)
    const partialMatch = processed.match(/```(\w*)\n?([\s\S]*)$/);
    if (partialMatch) {
        const placeholder = `%%CODEBLOCK_${codeBlocks.length}%%`;
        codeBlocks.push({ lang: partialMatch[1] || '', code: partialMatch[2], partial: true });
        processed = processed.slice(0, partialMatch.index) + placeholder;
    }

    // Now escape HTML on the non-code parts
    let html = escapeHtml(processed);

    // Inline code (but not lone backticks that might be partial ```)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

    // Headers (## text)
    html = html.replace(/^### (.+)$/gm, '<strong style="font-size:0.95rem;">$1</strong>');
    html = html.replace(/^## (.+)$/gm, '<strong style="font-size:1rem;">$1</strong>');

    // Lists
    html = html.replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Paragraphs (double newline)
    html = html.replace(/\n\n/g, '</p><p>');
    html = `<p>${html}</p>`;
    html = html.replace(/<p><\/p>/g, '');

    // Single newlines
    html = html.replace(/\n/g, '<br>');

    // Now inject code blocks back with header + copy button
    const codeIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`;
    const copyIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    for (let i = 0; i < codeBlocks.length; i++) {
        const { lang, code, partial } = codeBlocks[i];
        const trimmedCode = partial ? code : code.replace(/\n$/, '');
        const escapedCode = escapeHtml(trimmedCode);
        const langLabel = lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : 'Code';
        const copyBtn = partial
            ? `<span class="code-block-streaming">streaming...</span>`
            : `<button class="code-copy-btn" onclick="copyCodeBlock(this)">${copyIcon}</button>`;
        const block = `<div class="code-block-wrapper${partial ? ' streaming-code' : ''}" data-code-index="${i}"><div class="code-block-header"><span class="code-block-lang">${codeIcon} ${langLabel}</span>${copyBtn}</div><pre><code>${escapedCode}</code></pre></div>`;
        // The placeholder might be wrapped in <p> tags — unwrap it
        html = html.replace(new RegExp(`<p>\\s*%%CODEBLOCK_${i}%%\\s*<\\/p>|%%CODEBLOCK_${i}%%`), block);
    }

    // Append reminder badges if any
    if (reminderBadges) {
        html += reminderBadges;
    }

    return html;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function copyCodeBlock(btn) {
    const wrapper = btn.closest('.code-block-wrapper');
    const codeEl = wrapper.querySelector('pre code');
    const text = codeEl.textContent;

    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        const origHTML = btn.innerHTML;
        btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = origHTML;
        }, 2000);
    }).catch(() => {
        // Fallback for non-HTTPS
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);

        btn.classList.add('copied');
        const origHTML = btn.innerHTML;
        btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = origHTML;
        }, 2000);
    });
}

// ============================================================
// MEMORY MODAL
// ============================================================

async function openMemoryModal() {
    memoryModal.classList.remove('hidden');
    memoryList.innerHTML = '<p class="loading">Loading...</p>';

    try {
        const r = await fetch(`${API}/v1/memory`);
        const d = await r.json();

        if (!d.facts || d.facts.length === 0) {
            memoryList.innerHTML = '<p class="empty">No long-term memories stored yet.</p>';
            return;
        }

        memoryList.innerHTML = '';
        for (const fact of d.facts) {
            const item = document.createElement('div');
            item.className = 'memory-item';
            item.innerHTML = `
                <span class="fact-id">#${fact.id}</span>
                <span class="fact-text">${escapeHtml(fact.content)}</span>
                <button onclick="deleteFact(${fact.id}, this)">Delete</button>
            `;
            memoryList.appendChild(item);
        }
    } catch {
        memoryList.innerHTML = '<p class="empty">Failed to load memories.</p>';
    }
}

function closeMemoryModal() {
    memoryModal.classList.add('hidden');
}

async function deleteFact(id, btn) {
    try {
        const r = await fetch(`${API}/v1/memory/${id}`, { method: 'DELETE' });
        if (r.ok) {
            btn.closest('.memory-item').remove();
            if (memoryList.children.length === 0) {
                memoryList.innerHTML = '<p class="empty">No long-term memories stored yet.</p>';
            }
        }
    } catch { /* silent */ }
}

// ============================================================
// BOOT
// ============================================================

init();
