/**
 * agent.js - AI 天文小助手前端
 * 面板：右上角浮动，🤖 HUD 按钮控制弹出/收回
 * 后端：POST /api/agent/chat
 */
(function () {
    const $ = id => document.getElementById(id);

    const panel       = $('agent-panel');
    const toggleBtn   = $('toggle-agent');
    const closeBtn    = $('agent-close');
    const clearBtn    = $('agent-clear');
    const input       = $('agent-input');
    const sendBtn     = $('agent-send');
    const messagesEl  = $('agent-messages');
    const useLocEl    = $('agent-use-location');

    if (!panel || !toggleBtn) {
        console.warn('[agent] 面板未找到，跳过初始化');
        return;
    }

    // ============================================================
    //  状态
    // ============================================================
    let sessionId = null;
    let sending   = false;
    let welcomed  = false;

    // ============================================================
    //  展开 / 收起
    // ============================================================
    function openPanel() {
        panel.classList.add('open');
        panel.setAttribute('aria-hidden', 'false');
        toggleBtn.classList.add('active');
        // 隐藏可能与面板重叠的天体信息面板
        if (window.celestialScene && window.celestialScene._hideInfoPanel) {
            window.celestialScene._hideInfoPanel();
        }
        setTimeout(() => input && input.focus(), 300);
    }

    function closePanel() {
        panel.classList.remove('open');
        panel.setAttribute('aria-hidden', 'true');
        toggleBtn.classList.remove('active');
    }

    function togglePanel() {
        if (panel.classList.contains('open')) closePanel();
        else openPanel();
    }

    toggleBtn.addEventListener('click', togglePanel);
    closeBtn && closeBtn.addEventListener('click', closePanel);

    // ESC 关闭
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && panel.classList.contains('open')) {
            closePanel();
        }
    });

    // ============================================================
    //  消息渲染
    // ============================================================
    function appendMessage(role, text, opts = {}) {
        const div = document.createElement('div');
        div.className = `agent-msg ${role}`;
        if (opts.thinking) div.classList.add('thinking');

        div.textContent = text || '';

        // 工具调用徽章
        if (opts.toolCalls && opts.toolCalls.length) {
            const wrap = document.createElement('div');
            wrap.className = 'agent-tool-badges';
            opts.toolCalls.forEach(tc => {
                const b = document.createElement('span');
                b.className = 'agent-tool-badge' + (tc.error ? ' error' : '');
                if (tc.error) {
                    b.textContent = `⚠ ${tc.tool_name}`;
                    b.title = `错误: ${tc.error}\n参数: ${JSON.stringify(tc.arguments, null, 2)}`;
                } else {
                    b.textContent = `🔧 ${tc.tool_name}`;
                    b.title = `参数: ${JSON.stringify(tc.arguments, null, 2)}`;
                }
                wrap.appendChild(b);
            });
            div.appendChild(wrap);
        }

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }

    // ============================================================
    //  发送消息
    // ============================================================
    async function send() {
        if (sending) return;
        const text = (input.value || '').trim();
        if (!text) return;

        sending = true;
        sendBtn.disabled = true;
        input.value = '';
        input.style.height = 'auto';

        appendMessage('user', text);
        const thinkingEl = appendMessage('assistant', '思考中…', { thinking: true });

        // 组装请求体
        const body = {
            message: text,
            session_id: sessionId,
        };
        if (useLocEl && useLocEl.checked && window.timeManager) {
            body.location = {
                lat: window.timeManager.latitude,
                lon: window.timeManager.longitude,
            };
        }

        try {
            const res = await fetch('/api/agent/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();
            sessionId = data.session_id;

            thinkingEl.remove();
            appendMessage('assistant', data.answer || '（无回复）', {
                toolCalls: data.tool_calls || [],
            });
        } catch (err) {
            console.error('[agent] 请求失败', err);
            thinkingEl.remove();
            appendMessage(
                'assistant',
                `❌ 请求失败：${err.message}\n请检查后端是否运行、网络是否正常。`,
                {}
            );
        } finally {
            sending = false;
            sendBtn.disabled = false;
            input.focus();
        }
    }

    sendBtn && sendBtn.addEventListener('click', send);

    // Enter 发送 / Shift+Enter 换行
    input && input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });

    // 输入框自动增高
    input && input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    // ============================================================
    //  清空对话
    // ============================================================
    clearBtn && clearBtn.addEventListener('click', async () => {
        if (sessionId) {
            try {
                await fetch(`/api/agent/sessions/${sessionId}/clear`, {
                    method: 'POST',
                });
            } catch (_) { /* 忽略 */ }
        }
        messagesEl.innerHTML = '';
        welcomed = false;
        welcome();
    });

    // ============================================================
    //  欢迎语（首次打开时）
    // ============================================================
    function welcome() {
        if (welcomed) return;
        welcomed = true;
        appendMessage(
            'assistant',
            '你好！我是 AI 天文小助手 🔭\n\n' +
            '我可以帮你：\n' +
            '· 🎓 回答天文知识问题\n' +
            '· 📍 推荐附近适合观星的地点\n' +
            '· 🌠 查看近期天象推荐指数\n' +
            '· 🚗 规划到观测地点的交通\n\n' +
            '试试问我：「今晚适合观星吗？」',
            {}
        );
    }

    // 面板首次打开时显示欢迎语
    const _originalOpen = openPanel;
    openPanel = function () {
        _originalOpen();
        welcome();
    };

    // ============================================================
    //  对外暴露 API（供其他模块调用）
    // ============================================================
    window.agentUI = {
        open:   openPanel,
        close:  closePanel,
        toggle: togglePanel,
        send:   (text) => {
            input.value = text;
            send();
        },
    };

    console.log('[agent] AI 小助手已就绪');
})();