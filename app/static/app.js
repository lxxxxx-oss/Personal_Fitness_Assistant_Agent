(() => {
    "use strict";

    const API_ROOT = window.location.origin;
    const CHAT_TIMEOUT_MS = 90_000;
    const TEXTAREA_MIN_HEIGHT = 38;
    const TEXTAREA_MAX_HEIGHT = 150;
    const AUTO_FOLLOW_THRESHOLD_PX = 80;
    const CHAT_TRANSPORT = new URLSearchParams(window.location.search).get("transport") === "sse"
        ? "sse"
        : "http";
    const USER_ID_KEY = "fitagent.web.user_id";
    const CONVERSATION_ID_KEY = "fitagent.web.conversation_id";
    const MODEL_ID_KEY = "fitagent.web.model_id";

    const elements = {
        body: document.body,
        sidebar: document.getElementById("sidebar"),
        backdrop: document.getElementById("sidebar-backdrop"),
        openSidebar: document.getElementById("open-sidebar-button"),
        closeSidebar: document.getElementById("close-sidebar-button"),
        newChat: document.getElementById("new-chat-button"),
        temporaryChat: document.getElementById("temporary-chat-button"),
        memoryManager: document.getElementById("memory-manager-button"),
        searchConversations: document.getElementById("search-conversations-button"),
        conversationSearch: document.getElementById("conversation-search"),
        conversationSearchInput: document.getElementById("conversation-search-input"),
        clearConversationSearch: document.getElementById("clear-conversation-search"),
        conversationList: document.getElementById("conversation-list"),
        conversationListEmpty: document.getElementById("conversation-list-empty"),
        conversationCount: document.getElementById("conversation-count"),
        conversationTitle: document.getElementById("conversation-title"),
        serviceStatus: document.getElementById("service-status"),
        activeCapability: document.getElementById("active-capability"),
        modelSelect: document.getElementById("model-select"),
        chatScroll: document.getElementById("chat-scroll"),
        messages: document.getElementById("messages"),
        emptyState: document.getElementById("empty-state"),
        input: document.getElementById("user-input"),
        send: document.getElementById("send-button"),
        attach: document.getElementById("attach-button"),
        mediaInput: document.getElementById("media-input"),
        attachmentPreview: document.getElementById("attachment-preview"),
        attachmentName: document.getElementById("attachment-name"),
        attachmentDetail: document.getElementById("attachment-detail"),
        removeAttachment: document.getElementById("remove-attachment-button"),
        toastRegion: document.getElementById("toast-region"),
        memoryBackdrop: document.getElementById("memory-dialog-backdrop"),
        closeMemoryDialog: document.getElementById("close-memory-dialog"),
        memoryDialogBody: document.getElementById("memory-dialog-body"),
        memoryTabs: Array.from(document.querySelectorAll("[data-memory-tab]")),
    };

    const state = {
        userId: getOrCreateUserId(),
        conversationId: localStorage.getItem(CONVERSATION_ID_KEY),
        modelId: localStorage.getItem(MODEL_ID_KEY),
        activeController: null,
        isBusy: false,
        userStopped: false,
        selectedFile: null,
        hasMessages: false,
        autoFollow: true,
        conversations: [],
        conversationSearch: "",
        temporary: false,
        memoryTab: "durable",
    };

    const ICONS = {
        assistant: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7.5h2.2v9H7v-2H4.8v-5H7v-2Zm7.8 0H17v2h2.2v5H17v2h-2.2v-9ZM9.2 11h5.6v2H9.2v-2Z"/></svg>',
        error: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 7h2v6h-2V7Zm0 8h2v2h-2v-2Zm1-13 10 19H2L12 2Zm0 4.25L5.3 19h13.4L12 6.25Z"/></svg>',
        copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7V4h12v12h-3v4H4V7h4Zm2 0h7v7h1V6h-8v1Zm-4 2v9h9V9H6Z"/></svg>',
        chevron: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7-1.4-1.4 5.6-5.6-5.6-5.6L9 5Z"/></svg>',
    };

    function getOrCreateUserId() {
        const stored = localStorage.getItem(USER_ID_KEY);
        if (stored) return stored;
        const suffix = window.crypto?.randomUUID
            ? window.crypto.randomUUID().replaceAll("-", "").slice(0, 12)
            : Math.random().toString(36).slice(2, 14);
        const userId = `web_user_${suffix}`;
        localStorage.setItem(USER_ID_KEY, userId);
        return userId;
    }

    function setConversationId(conversationId) {
        state.conversationId = conversationId || null;
        if (state.conversationId && !state.temporary && !state.conversationId.startsWith("tmp_")) {
            localStorage.setItem(CONVERSATION_ID_KEY, state.conversationId);
        } else {
            localStorage.removeItem(CONVERSATION_ID_KEY);
        }
    }

    function setServiceStatus(mode, title, detail) {
        const dotClass = mode === "offline" ? "offline" : mode === "checking" ? "checking" : "";
        elements.serviceStatus.innerHTML = `
            <span class="status-dot ${dotClass}"></span>
            <span><strong></strong><small></small></span>
        `;
        elements.serviceStatus.querySelector("strong").textContent = title;
        elements.serviceStatus.querySelector("small").textContent = detail;
    }

    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast ${type === "error" ? "error" : ""}`;
        toast.textContent = message;
        elements.toastRegion.appendChild(toast);
        window.setTimeout(() => toast.remove(), 3_000);
    }

    function setCapability(intent) {
        const labels = {
            chat: "健身问答 · 上下文记忆",
            search: "实时搜索 · 来源追踪",
            motion: "动作分析 · 姿态估计",
            diet: "饮食建议 · 个性化约束",
            mcp: "外部工具 · MCP 调用",
            mixed: "复合任务 · 多意图编排",
        };
        elements.activeCapability.textContent = labels[intent] || "智能路由 · 上下文记忆";
    }

    function setConversationTitle(text) {
        const normalized = String(text || "").replace(/\s+/g, " ").trim();
        elements.conversationTitle.textContent = normalized
            ? (normalized.length > 18 ? `${normalized.slice(0, 18)}…` : normalized)
            : "新对话";
    }

    function showConversation() {
        if (!state.hasMessages) {
            elements.emptyState.hidden = false;
            return;
        }
        elements.emptyState.hidden = true;
    }

    function isNearBottom() {
        const distance = elements.chatScroll.scrollHeight
            - elements.chatScroll.scrollTop
            - elements.chatScroll.clientHeight;
        return distance <= AUTO_FOLLOW_THRESHOLD_PX;
    }

    function scrollToBottom(behavior = "smooth", force = false) {
        window.requestAnimationFrame(() => {
            if (!force && !state.autoFollow) return;
            elements.chatScroll.scrollTo({
                top: elements.chatScroll.scrollHeight,
                behavior,
            });
            state.autoFollow = true;
        });
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function renderInline(rawText) {
        let text = escapeHtml(rawText);
        text = text.replace(/`([^`\n]+)`/g, "<code>$1</code>");
        text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
        text = text.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_match, label, href) => {
            return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
        });
        return text;
    }

    function renderTextBlocks(rawText) {
        const lines = rawText.replaceAll("\r\n", "\n").split("\n");
        const output = [];
        let paragraph = [];
        let listType = null;

        const flushParagraph = () => {
            if (!paragraph.length) return;
            output.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
            paragraph = [];
        };
        const closeList = () => {
            if (!listType) return;
            output.push(`</${listType}>`);
            listType = null;
        };

        for (const line of lines) {
            const trimmed = line.trim();
            const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
            const unordered = trimmed.match(/^[-*]\s+(.+)$/);
            const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
            const quote = trimmed.match(/^>\s?(.*)$/);

            if (!trimmed) {
                flushParagraph();
                closeList();
                continue;
            }
            if (heading) {
                flushParagraph();
                closeList();
                const level = heading[1].length;
                output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
                continue;
            }
            if (unordered || ordered) {
                flushParagraph();
                const nextType = unordered ? "ul" : "ol";
                if (listType !== nextType) {
                    closeList();
                    output.push(`<${nextType}>`);
                    listType = nextType;
                }
                output.push(`<li>${renderInline((unordered || ordered)[1])}</li>`);
                continue;
            }
            if (quote) {
                flushParagraph();
                closeList();
                output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
                continue;
            }
            closeList();
            paragraph.push(line);
        }
        flushParagraph();
        closeList();
        return output.join("");
    }

    function renderMarkdown(rawText) {
        const segments = String(rawText ?? "").split("```");
        return segments.map((segment, index) => {
            if (index % 2 === 0) return renderTextBlocks(segment);
            const newlineIndex = segment.indexOf("\n");
            const code = newlineIndex >= 0 ? segment.slice(newlineIndex + 1) : segment;
            return `<pre><code>${escapeHtml(code.trimEnd())}</code></pre>`;
        }).join("");
    }

    function stripModelThinking(rawText) {
        return String(rawText ?? "")
            .replace(/<think>[\s\S]*?<\/think>/gi, "")
            .replace(/<think>[\s\S]*$/gi, "")
            .replace(/<\/?think>/gi, "")
            .trimStart();
    }

    function createUserMessage(text) {
        state.hasMessages = true;
        showConversation();
        const article = document.createElement("article");
        article.className = "message user";
        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = text;
        article.appendChild(content);
        elements.messages.appendChild(article);
        scrollToBottom("smooth", true);
        return article;
    }

    function createAssistantMessage({ intent = "chat", pendingText = "正在理解你的需求" } = {}) {
        state.hasMessages = true;
        showConversation();

        const article = document.createElement("article");
        article.className = "message assistant";
        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.innerHTML = ICONS.assistant;

        const main = document.createElement("div");
        main.className = "message-main";
        const role = document.createElement("div");
        role.className = "message-role";
        role.innerHTML = `<strong>FitAgent</strong><span class="intent-pill"></span>`;
        role.querySelector(".intent-pill").textContent = intentLabel(intent);

        const content = document.createElement("div");
        content.className = "assistant-content";
        const streamStatus = document.createElement("div");
        streamStatus.className = "stream-status";
        streamStatus.innerHTML = `<span class="thinking-dots"><i></i><i></i><i></i></span><span></span>`;
        streamStatus.querySelector("span:last-child").textContent = pendingText;
        content.appendChild(streamStatus);

        const metadata = document.createElement("div");
        metadata.className = "message-meta";
        const actions = document.createElement("div");
        actions.className = "message-actions";

        main.append(role, content, metadata, actions);
        article.append(avatar, main);
        elements.messages.appendChild(article);
        scrollToBottom("smooth", true);

        return { article, avatar, role, content, metadata, actions, rawText: "" };
    }

    function intentLabel(intent) {
        const labels = {
            chat: "问答",
            search: "搜索",
            motion: "动作",
            diet: "饮食",
            mcp: "工具",
            mixed: "复合",
        };
        return labels[intent] || "智能路由";
    }

    function setMessageIntent(message, intent) {
        if (!intent) return;
        message.role.querySelector(".intent-pill").textContent = intentLabel(intent);
        setCapability(intent);
    }

    function setPendingText(message, text) {
        const label = message.content.querySelector(".stream-status span:last-child");
        if (label) label.textContent = text;
    }

    function setAssistantText(message, rawText) {
        message.rawText = String(rawText ?? "");
        message.content.innerHTML = renderMarkdown(message.rawText);
        scrollToBottom("auto");
    }

    function setMessageError(message, text) {
        message.article.classList.add("error");
        message.avatar.innerHTML = ICONS.error;
        message.content.innerHTML = "";
        const paragraph = document.createElement("p");
        paragraph.textContent = text;
        message.content.appendChild(paragraph);
    }

    function createMetadataGroup(title, className = "") {
        const group = document.createElement("section");
        group.className = `metadata-group ${className}`.trim();
        const heading = document.createElement("strong");
        heading.textContent = title;
        group.appendChild(heading);
        return group;
    }

    function renderMessageMetadata(container, metadata = {}) {
        const sources = Array.isArray(metadata.sources) ? metadata.sources.filter(Boolean) : [];
        const warnings = Array.isArray(metadata.warnings) ? metadata.warnings.filter(Boolean) : [];
        const execution = Array.isArray(metadata.execution) ? metadata.execution : [];
        container.innerHTML = "";
        if (!sources.length && !warnings.length && !execution.length) return;

        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.className = "metadata-summary";
        summary.innerHTML = ICONS.chevron;
        const summaryText = document.createElement("span");
        const parts = [];
        if (sources.length) parts.push(`${sources.length} 条来源`);
        if (execution.length) parts.push(`${execution.length} 个执行步骤`);
        if (warnings.length) parts.push(`${warnings.length} 条提示`);
        summaryText.textContent = parts.join(" · ");
        summary.appendChild(summaryText);

        const content = document.createElement("div");
        content.className = "metadata-content";

        if (sources.length) {
            const group = createMetadataGroup("参考来源");
            const list = document.createElement("ul");
            for (const source of sources) {
                const item = document.createElement("li");
                if (/^https?:\/\//i.test(source)) {
                    const link = document.createElement("a");
                    link.href = source;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                    link.textContent = source;
                    item.appendChild(link);
                } else {
                    item.textContent = source;
                }
                list.appendChild(item);
            }
            group.appendChild(list);
            content.appendChild(group);
        }

        if (execution.length) {
            const group = createMetadataGroup("执行过程");
            for (const trace of execution) {
                const row = document.createElement("div");
                row.className = `trace-row ${trace.degraded ? "degraded" : ""}`;
                const component = document.createElement("span");
                component.className = "trace-component";
                component.textContent = trace.component || "unknown";
                const mode = document.createElement("span");
                mode.className = "trace-mode";
                mode.textContent = trace.degraded ? `${trace.mode || "fallback"} · 降级` : (trace.mode || "normal");
                const detail = document.createElement("span");
                detail.textContent = trace.detail || "";
                row.append(component, mode, detail);
                group.appendChild(row);
            }
            content.appendChild(group);
        }

        if (warnings.length) {
            const group = createMetadataGroup("运行提示", "warning");
            const list = document.createElement("ul");
            for (const warning of warnings) {
                const item = document.createElement("li");
                item.textContent = warning;
                list.appendChild(item);
            }
            group.appendChild(list);
            content.appendChild(group);
        }

        details.append(summary, content);
        container.appendChild(details);
    }

    function addCopyAction(message) {
        message.actions.innerHTML = "";
        if (!message.rawText) return;
        const button = document.createElement("button");
        button.className = "message-action";
        button.type = "button";
        button.innerHTML = `${ICONS.copy}<span>复制</span>`;
        button.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(message.rawText);
                button.querySelector("span").textContent = "已复制";
                window.setTimeout(() => {
                    if (button.isConnected) button.querySelector("span").textContent = "复制";
                }, 1_500);
            } catch {
                showToast("复制失败，请手动选择文本。", "error");
            }
        });
        message.actions.appendChild(button);
    }

    function buildRequest(message) {
        const payload = {
            user_id: state.userId,
            message,
        };
        if (state.conversationId) payload.conversation_id = state.conversationId;
        if (state.modelId) payload.model = state.modelId;
        if (state.temporary) payload.temporary = true;
        return payload;
    }

    async function readSseStream(response, handlers) {
        if (!response.body) throw new Error("浏览器未提供流式响应体");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const processEvent = (block) => {
            let eventName = "message";
            const dataLines = [];
            for (const line of block.split(/\r?\n/)) {
                if (line.startsWith("event:")) eventName = line.slice(6).trim() || "message";
                if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
            }
            if (!dataLines.length) return;
            handlers.onEvent(eventName, dataLines.join("\n"));
        };

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let boundary = buffer.search(/\r?\n\r?\n/);
            while (boundary >= 0) {
                const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
                const block = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + separator.length);
                if (block.trim()) processEvent(block);
                boundary = buffer.search(/\r?\n\r?\n/);
            }
        }
        buffer += decoder.decode();
        if (buffer.trim()) processEvent(buffer);
    }

    async function sendMessage(text, { showUser = true } = {}) {
        const prompt = String(text || "").trim();
        if (!prompt || state.isBusy) return;

        if (showUser) createUserMessage(prompt);
        if (elements.conversationTitle.textContent === "新对话") setConversationTitle(prompt);
        elements.input.value = "";
        resizeTextarea();

        const assistantMessage = createAssistantMessage();
        let rawReply = "";
        let visibleReply = "";
        let sawToken = false;
        let streamMetadata = {};
        let timedOut = false;
        state.userStopped = false;
        const controller = new AbortController();
        state.activeController = controller;
        setBusy(true);
        setServiceStatus("online", "智能体正在工作", "正在判断任务类型");
        const timeoutId = window.setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, CHAT_TIMEOUT_MS);

        try {
            if (CHAT_TRANSPORT === "http") {
                const response = await fetch(`${API_ROOT}/chat`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(buildRequest(prompt)),
                    signal: controller.signal,
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(formatApiError(data, response.status));
                setConversationId(data.conversation_id);
                setMessageIntent(assistantMessage, data.intent);
                const reply = stripModelThinking(data.reply || "");
                if (!reply.trim()) throw new Error("HTTP 响应为空");
                setAssistantText(assistantMessage, reply);
                renderMessageMetadata(assistantMessage.metadata, data);
                addCopyAction(assistantMessage);
                setServiceStatus("online", "服务运行正常", "HTTP 对话可用");
                return;
            }

            const response = await fetch(`${API_ROOT}/chat/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(buildRequest(prompt)),
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`流式接口返回 HTTP ${response.status}`);

            await readSseStream(response, {
                onEvent(eventName, rawData) {
                    if (eventName === "meta") {
                        const metadata = JSON.parse(rawData);
                        streamMetadata = metadata;
                        setConversationId(metadata.conversation_id);
                        setMessageIntent(assistantMessage, metadata.intent);
                        const sourceCount = Array.isArray(metadata.sources) ? metadata.sources.length : 0;
                        setPendingText(
                            assistantMessage,
                            sourceCount ? `已获得 ${sourceCount} 条依据，正在组织回答` : "任务已路由，正在生成回答",
                        );
                        return;
                    }
                    if (eventName === "token") {
                        const payload = JSON.parse(rawData);
                        if (typeof payload.text !== "string") return;
                        rawReply += payload.text;
                        const nextVisible = stripModelThinking(rawReply);
                        if (nextVisible) {
                            sawToken = true;
                            visibleReply = nextVisible;
                            setAssistantText(assistantMessage, visibleReply);
                        }
                        return;
                    }
                    if (eventName === "error") {
                        let detail = "流式生成失败";
                        try {
                            detail = JSON.parse(rawData).message || detail;
                        } catch {
                            detail = rawData || detail;
                        }
                        throw new Error(detail);
                    }
                },
            });

            if (!sawToken || !visibleReply.trim()) throw new Error("流式响应为空");
            renderMessageMetadata(assistantMessage.metadata, streamMetadata);
            addCopyAction(assistantMessage);
            setServiceStatus("online", "服务运行正常", "流式对话可用");
        } catch (error) {
            const stopped = state.userStopped;
            if (CHAT_TRANSPORT === "http") {
                if (stopped) {
                    const stoppedText = "已停止本次请求。";
                    setAssistantText(assistantMessage, stoppedText);
                    assistantMessage.rawText = stoppedText;
                    addCopyAction(assistantMessage);
                    showToast("已停止请求");
                } else {
                    const detail = timedOut ? "HTTP 请求超时" : error.message;
                    setMessageError(assistantMessage, `请求未完成：${detail}`);
                    setServiceStatus("offline", "对话服务异常", "请检查后端日志");
                }
                return;
            }

            const canFallback = !stopped && !sawToken;
            if (stopped) {
                const stoppedText = visibleReply.trim() || "已停止本次生成。";
                setAssistantText(assistantMessage, stoppedText);
                assistantMessage.rawText = stoppedText;
                addCopyAction(assistantMessage);
                showToast("已停止生成");
            } else if (canFallback) {
                setPendingText(assistantMessage, timedOut ? "流式请求超时，正在切换普通请求" : "流式不可用，正在切换普通请求");
                try {
                    const fallback = await fetch(`${API_ROOT}/chat`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(buildRequest(prompt)),
                    });
                    const data = await fallback.json().catch(() => ({}));
                    if (!fallback.ok) throw new Error(formatApiError(data, fallback.status));
                    setConversationId(data.conversation_id);
                    setMessageIntent(assistantMessage, data.intent);
                    setAssistantText(assistantMessage, stripModelThinking(data.reply || ""));
                    renderMessageMetadata(assistantMessage.metadata, data);
                    addCopyAction(assistantMessage);
                    setServiceStatus("online", "服务运行正常", "当前使用非流式回答");
                    showToast("流式连接不可用，已自动完成非流式回答。");
                } catch (fallbackError) {
                    setMessageError(assistantMessage, `请求未完成：${fallbackError.message}`);
                    setServiceStatus("offline", "对话服务异常", "请检查后端日志");
                }
            } else {
                setMessageError(assistantMessage, `生成中断：${error.message}`);
                renderMessageMetadata(assistantMessage.metadata, streamMetadata);
                setServiceStatus("offline", "生成过程异常", "已保留当前执行信息");
            }
        } finally {
            window.clearTimeout(timeoutId);
            state.activeController = null;
            state.userStopped = false;
            setBusy(false);
            if (!state.temporary) await refreshConversationList();
            elements.input.focus();
            scrollToBottom();
        }
    }

    function formatApiError(data, status) {
        const detail = data?.detail;
        if (typeof detail === "string") return detail;
        if (detail?.message) return detail.message;
        return `HTTP ${status}`;
    }

    function setBusy(isBusy) {
        state.isBusy = isBusy;
        const canStop = isBusy && Boolean(state.activeController);
        elements.send.classList.toggle("is-streaming", canStop);
        elements.send.disabled = isBusy ? !canStop : !canSubmit();
        elements.attach.disabled = isBusy;
        elements.newChat.disabled = isBusy;
        elements.temporaryChat.disabled = isBusy;
        elements.modelSelect.disabled = isBusy || !elements.modelSelect.options.length;
        elements.send.setAttribute("aria-label", canStop ? "停止生成" : isBusy ? "处理中" : "发送消息");
    }

    function canSubmit() {
        return Boolean(elements.input.value.trim() || state.selectedFile);
    }

    function updateSendState() {
        if (!state.isBusy) elements.send.disabled = !canSubmit();
    }

    function stopGeneration() {
        if (!state.activeController) return;
        state.userStopped = true;
        state.activeController.abort();
    }

    function resizeTextarea() {
        elements.input.style.height = "auto";
        const contentHeight = elements.input.value
            ? elements.input.scrollHeight
            : TEXTAREA_MIN_HEIGHT;
        elements.input.style.height = `${Math.min(contentHeight, TEXTAREA_MAX_HEIGHT)}px`;
        elements.input.style.overflowY = contentHeight > TEXTAREA_MAX_HEIGHT
            ? "auto"
            : "hidden";
        updateSendState();
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function setAttachment(file) {
        state.selectedFile = file || null;
        elements.attachmentPreview.hidden = !file;
        if (file) {
            elements.attachmentName.textContent = file.name;
            elements.attachmentDetail.textContent = `${file.type.startsWith("video/") ? "动作视频" : "姿态图片"} · ${formatFileSize(file.size)}`;
        } else {
            elements.mediaInput.value = "";
            elements.attachmentName.textContent = "";
            elements.attachmentDetail.textContent = "";
        }
        updateSendState();
    }

    function isVideoFile(file) {
        return file.type.startsWith("video/") || /\.(mp4|mov|avi)$/i.test(file.name);
    }

    function renderMotionResult(message, data, video) {
        message.content.innerHTML = "";
        message.rawText = data.message || `${video ? "视频" : "图片"}动作分析完成`;

        const card = document.createElement("section");
        card.className = "motion-card";
        const heading = document.createElement("h3");
        heading.textContent = video ? "视频姿态分析结果" : "图片姿态分析结果";
        const description = document.createElement("p");
        description.textContent = data.message || "姿态提取完成。";
        const metrics = document.createElement("div");
        metrics.className = "motion-metrics";

        const metricItems = [
            ["帧数", data.frames],
            ["关节点", data.joints],
            [video ? "有效帧比例" : "平均置信度", video
                ? `${Math.round((data.valid_frame_ratio || 0) * 100)}%`
                : (data.confidence_summary?.mean ?? "—")],
        ];
        if (video) metricItems.push(["采样帧", data.sampled_frames]);
        for (const [label, value] of metricItems) {
            const item = document.createElement("div");
            item.className = "motion-metric";
            const strong = document.createElement("strong");
            strong.textContent = value ?? "—";
            const small = document.createElement("small");
            small.textContent = label;
            item.append(strong, small);
            metrics.appendChild(item);
        }

        card.append(heading, description, metrics);
        message.content.appendChild(card);
        renderMessageMetadata(message.metadata, {
            warnings: data.warnings,
            execution: data.execution,
            sources: data.reference ? [`标准动作：${data.reference}`] : [],
        });
        addCopyAction(message);
    }

    async function uploadSelectedMedia() {
        const file = state.selectedFile;
        if (!file || state.isBusy) return;
        const video = isVideoFile(file);
        createUserMessage(`上传${video ? "动作视频" : "姿态图片"}：${file.name}`);
        if (elements.conversationTitle.textContent === "新对话") {
            setConversationTitle(`分析 ${file.name}`);
        }
        const assistantMessage = createAssistantMessage({
            intent: "motion",
            pendingText: video ? "正在抽取视频姿态序列" : "正在识别图片中的人体姿态",
        });
        setCapability("motion");
        setBusy(true);
        setServiceStatus("online", "正在分析动作素材", video ? "视频处理可能需要一些时间" : "正在调用姿态估计");

        try {
            const formData = new FormData();
            formData.append("file", file);
            const endpoint = video ? "/motion/analyze-video" : "/motion/analyze-image";
            const response = await fetch(`${API_ROOT}${endpoint}`, {
                method: "POST",
                body: formData,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(formatApiError(data, response.status));
            renderMotionResult(assistantMessage, data, video);
            setServiceStatus("online", "服务运行正常", "动作素材分析完成");
        } catch (error) {
            setMessageError(assistantMessage, `动作分析失败：${error.message}`);
            setServiceStatus("offline", "动作分析不可用", "请检查模型与运行依赖");
        } finally {
            setAttachment(null);
            setBusy(false);
            elements.input.focus();
            scrollToBottom();
        }
    }

    function clearConversationView() {
        for (const message of elements.messages.querySelectorAll(".message")) message.remove();
        state.hasMessages = false;
        state.autoFollow = true;
        setConversationTitle("");
        setCapability("");
        setAttachment(null);
        showConversation();
        elements.chatScroll.scrollTop = 0;
    }

    function closeConversationMenus(except = null) {
        for (const menu of elements.conversationList.querySelectorAll(".conversation-menu")) {
            if (menu !== except) {
                menu.hidden = true;
                menu.classList.remove("open-up");
                menu.style.left = "";
                menu.style.top = "";
                menu.closest(".conversation-row")
                    ?.querySelector(".conversation-more")
                    ?.setAttribute("aria-expanded", "false");
            }
        }
    }

    function positionConversationMenu(menu) {
        menu.classList.remove("open-up");
        const rowBounds = menu.closest(".conversation-row").getBoundingClientRect();
        const menuWidth = menu.offsetWidth;
        const menuHeight = menu.offsetHeight;
        const viewportGap = 8;
        const opensUp = rowBounds.bottom + 4 + menuHeight > window.innerHeight - viewportGap;
        const top = opensUp
            ? Math.max(viewportGap, rowBounds.top - menuHeight - 4)
            : rowBounds.bottom + 4;
        const left = Math.min(
            window.innerWidth - menuWidth - viewportGap,
            Math.max(viewportGap, rowBounds.right - menuWidth),
        );
        menu.style.top = `${top}px`;
        menu.style.left = `${left}px`;
        if (opensUp) {
            menu.classList.add("open-up");
        }
    }

    function renderConversationList() {
        const query = state.conversationSearch.trim().toLocaleLowerCase("zh-CN");
        const visible = state.conversations.filter((item) => (
            !query || String(item.title || "").toLocaleLowerCase("zh-CN").includes(query)
        ));
        elements.conversationList.replaceChildren();
        elements.conversationCount.textContent = state.conversations.length
            ? String(state.conversations.length)
            : "";
        elements.conversationListEmpty.hidden = visible.length > 0;
        elements.conversationListEmpty.textContent = query ? "没有匹配的对话" : "暂无最近对话";

        for (const item of visible) {
            const row = document.createElement("div");
            row.className = `conversation-row${item.id === state.conversationId ? " active" : ""}`;
            row.dataset.conversationId = item.id;

            const select = document.createElement("button");
            select.className = "conversation-item";
            select.type = "button";
            select.title = item.title || "新对话";
            select.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 3v-3a2 2 0 0 1-1-1.73V6a2 2 0 0 1 2-2Zm0 2v10h1v1.45L8.45 16H19V6H5Z"/></svg>';
            const label = document.createElement("span");
            label.textContent = item.title || "新对话";
            select.appendChild(label);
            select.addEventListener("click", () => loadConversation(item.id));

            const more = document.createElement("button");
            more.className = "conversation-more";
            more.type = "button";
            more.textContent = "•••";
            more.setAttribute("aria-label", `管理对话：${item.title || "新对话"}`);
            more.setAttribute("aria-expanded", "false");

            const menu = document.createElement("div");
            menu.className = "conversation-menu";
            menu.hidden = true;
            const rename = document.createElement("button");
            rename.type = "button";
            rename.textContent = "重命名";
            rename.addEventListener("click", () => renameConversation(item));
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "danger";
            remove.textContent = "删除";
            remove.addEventListener("click", () => deleteConversation(item));
            menu.append(rename, remove);

            more.addEventListener("click", (event) => {
                event.stopPropagation();
                const willOpen = menu.hidden;
                closeConversationMenus(menu);
                menu.hidden = !willOpen;
                more.setAttribute("aria-expanded", String(willOpen));
                if (willOpen) positionConversationMenu(menu);
            });
            row.append(select, more, menu);
            elements.conversationList.appendChild(row);
        }
    }

    async function refreshConversationList() {
        try {
            const response = await fetch(
                `${API_ROOT}/chat/${encodeURIComponent(state.userId)}/conversations?limit=50`,
            );
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            state.conversations = Array.isArray(data.conversations) ? data.conversations : [];
            renderConversationList();
            const active = state.conversations.find((item) => item.id === state.conversationId);
            if (active) setConversationTitle(active.title);
        } catch (error) {
            showToast(`最近会话加载失败：${error.message}`, "error");
        }
    }

    async function loadConversation(conversationId) {
        if (!conversationId || state.isBusy) return;
        try {
            const response = await fetch(
                `${API_ROOT}/chat/${encodeURIComponent(state.userId)}/conversations/${encodeURIComponent(conversationId)}`,
            );
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setTemporaryMode(false);
            clearConversationView();
            setConversationId(data.conversation_id);
            for (const item of Array.isArray(data.history) ? data.history : []) {
                if (!item?.content) continue;
                if (item.role === "user") {
                    createUserMessage(item.content);
                } else if (item.role === "assistant") {
                    const message = createAssistantMessage({ pendingText: "正在恢复历史回答" });
                    setAssistantText(message, stripModelThinking(item.content));
                    addCopyAction(message);
                }
            }
            const active = state.conversations.find((item) => item.id === conversationId);
            setConversationTitle(active?.title || "");
            renderConversationList();
            scrollToBottom("auto", true);
            closeSidebar();
        } catch (error) {
            showToast(`会话打开失败：${error.message}`, "error");
        }
    }

    async function startNewConversation({ silent = false } = {}) {
        if (state.isBusy) return;
        elements.newChat.disabled = true;
        try {
            setTemporaryMode(false);
            const response = await fetch(
                `${API_ROOT}/chat/${encodeURIComponent(state.userId)}/conversations`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: "{}",
                },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(formatApiError(data, response.status));
            setConversationId(data.id);
            clearConversationView();
            await refreshConversationList();
            if (!silent) showToast("已开始新对话");
            closeSidebar();
            elements.input.focus();
        } catch (error) {
            showToast(`新建对话失败：${error.message}`, "error");
        } finally {
            elements.newChat.disabled = false;
        }
    }

    function setTemporaryMode(enabled) {
        state.temporary = Boolean(enabled);
        elements.temporaryChat.classList.toggle("active", state.temporary);
        elements.temporaryChat.setAttribute("aria-pressed", String(state.temporary));
    }

    function startTemporaryConversation() {
        if (state.isBusy) return;
        setTemporaryMode(true);
        setConversationId(null);
        clearConversationView();
        setConversationTitle("临时对话");
        elements.activeCapability.textContent = "临时对话 · 不读取或保存长期记忆";
        renderConversationList();
        closeSidebar();
        showToast("临时对话已开启，刷新页面或新建对话后内容即消失");
        elements.input.focus();
    }

    async function renameConversation(item) {
        closeConversationMenus();
        const title = window.prompt("输入新的对话名称", item.title || "新对话");
        if (title === null || !title.trim()) return;
        try {
            const response = await fetch(
                `${API_ROOT}/chat/${encodeURIComponent(state.userId)}/conversations/${encodeURIComponent(item.id)}`,
                {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ title: title.trim() }),
                },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(formatApiError(data, response.status));
            await refreshConversationList();
            showToast("对话已重命名");
        } catch (error) {
            showToast(`重命名失败：${error.message}`, "error");
        }
    }

    async function deleteConversation(item) {
        closeConversationMenus();
        if (!window.confirm(`删除“${item.title || "新对话"}”？此操作不可撤销。`)) return;
        try {
            const response = await fetch(
                `${API_ROOT}/chat/${encodeURIComponent(state.userId)}/conversations/${encodeURIComponent(item.id)}`,
                { method: "DELETE" },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(formatApiError(data, response.status));
            const wasActive = item.id === state.conversationId;
            if (wasActive) {
                setConversationId(null);
                clearConversationView();
            }
            await refreshConversationList();
            if (wasActive) {
                const next = state.conversations[0];
                if (next) await loadConversation(next.id);
                else await startNewConversation({ silent: true });
            }
            showToast("对话已删除");
        } catch (error) {
            showToast(`删除失败：${error.message}`, "error");
        }
    }

    async function loadConversations() {
        await refreshConversationList();
        const saved = state.conversations.find((item) => item.id === state.conversationId);
        const target = saved || state.conversations[0];
        if (target) {
            await loadConversation(target.id);
        } else {
            await startNewConversation({ silent: true });
        }
    }

    function toggleConversationSearch(forceOpen = null) {
        const willOpen = forceOpen ?? elements.conversationSearch.hidden;
        elements.conversationSearch.hidden = !willOpen;
        elements.searchConversations.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) {
            elements.conversationSearchInput.focus();
        } else {
            state.conversationSearch = "";
            elements.conversationSearchInput.value = "";
            renderConversationList();
        }
    }

    async function checkHealth() {
        setServiceStatus("checking", "正在连接服务", "检查后端状态");
        try {
            const response = await fetch(`${API_ROOT}/health`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setServiceStatus("online", "服务运行正常", data.version ? `后端版本 ${data.version}` : "后端已连接");
        } catch {
            setServiceStatus("offline", "后端未连接", "请先启动 FastAPI 服务");
        }
    }

    async function loadModels() {
        elements.modelSelect.disabled = true;
        try {
            const response = await fetch(`${API_ROOT}/models`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const models = Array.isArray(data.models) ? data.models : [];
            if (!models.length) throw new Error("服务未返回可用模型配置");

            elements.modelSelect.replaceChildren();
            for (const model of models) {
                const option = document.createElement("option");
                option.value = model.id;
                option.textContent = model.available ? model.label : `${model.label}（未配置）`;
                option.disabled = !model.available;
                option.title = model.detail || "";
                elements.modelSelect.appendChild(option);
            }

            const saved = models.find((model) => model.id === state.modelId && model.available);
            const defaultModel = models.find((model) => model.default && model.available);
            const firstAvailable = models.find((model) => model.available);
            const selected = saved || defaultModel || firstAvailable;
            if (!selected) {
                const placeholder = document.createElement("option");
                placeholder.value = "";
                placeholder.textContent = "暂无已配置模型";
                placeholder.selected = true;
                elements.modelSelect.prepend(placeholder);
                state.modelId = "";
                elements.modelSelect.disabled = true;
                return;
            }

            state.modelId = selected.id;
            elements.modelSelect.value = selected.id;
            localStorage.setItem(MODEL_ID_KEY, selected.id);
            elements.modelSelect.disabled = state.isBusy;
        } catch (error) {
            elements.modelSelect.replaceChildren();
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "模型列表不可用";
            elements.modelSelect.appendChild(option);
            elements.modelSelect.disabled = true;
            showToast(`模型列表加载失败：${error.message}`, "error");
        }
    }

    function openSidebar() {
        elements.body.classList.add("sidebar-open");
    }

    function closeSidebar() {
        elements.body.classList.remove("sidebar-open");
    }

    async function requestJson(path, options = {}) {
        const response = await fetch(`${API_ROOT}${path}`, options);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(formatApiError(data, response.status));
        return data;
    }

    function formatMemoryTime(value) {
        if (!value) return "";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN");
    }

    function createMemoryBadge(text, tone = "") {
        const badge = document.createElement("span");
        badge.className = `memory-badge${tone ? ` ${tone}` : ""}`;
        badge.textContent = text;
        return badge;
    }

    function createMemoryCard({ title, content, badges = [], detail = "", actions = [] }) {
        const card = document.createElement("article");
        card.className = "memory-card";
        const header = document.createElement("div");
        header.className = "memory-card-header";
        const heading = document.createElement("strong");
        heading.textContent = title;
        const badgeRow = document.createElement("div");
        badgeRow.className = "memory-badges";
        badges.forEach((badge) => badgeRow.appendChild(createMemoryBadge(badge.text, badge.tone)));
        header.append(heading, badgeRow);
        const body = document.createElement("p");
        body.className = "memory-card-content";
        body.textContent = content;
        card.append(header, body);
        if (detail) {
            const meta = document.createElement("small");
            meta.className = "memory-card-detail";
            meta.textContent = detail;
            card.appendChild(meta);
        }
        if (actions.length) {
            const actionRow = document.createElement("div");
            actionRow.className = "memory-card-actions";
            actions.forEach(({ label, tone = "", onClick }) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = `memory-action${tone ? ` ${tone}` : ""}`;
                button.textContent = label;
                button.addEventListener("click", onClick);
                actionRow.appendChild(button);
            });
            card.appendChild(actionRow);
        }
        return card;
    }

    function renderMemoryEmpty(message) {
        const empty = document.createElement("div");
        empty.className = "memory-empty";
        empty.textContent = message;
        elements.memoryDialogBody.replaceChildren(empty);
    }

    async function runMemoryAction(action, successMessage) {
        try {
            await action();
            showToast(successMessage);
            await loadMemoryTab();
        } catch (error) {
            showToast(`记忆操作失败：${error.message}`, "error");
        }
    }

    async function renderDurableMemories() {
        const data = await requestJson(`/memory?user_id=${encodeURIComponent(state.userId)}&limit=100`);
        const items = Array.isArray(data.memories) ? data.memories : [];
        if (!items.length) {
            renderMemoryEmpty("还没有已确认的长期记忆。");
            return;
        }
        elements.memoryDialogBody.replaceChildren(...items.map((item) => createMemoryCard({
            title: item.kind || "长期记忆",
            content: item.content,
            badges: [
                { text: "已确认", tone: "confirmed" },
                { text: `置信度 ${Math.round((item.confidence ?? 1) * 100)}%` },
            ],
            detail: `更新时间：${formatMemoryTime(item.updated_at)}`,
            actions: [{
                label: "删除",
                tone: "danger",
                onClick: () => {
                    if (!window.confirm("删除这条长期记忆？后续回答将不再使用它。")) return;
                    runMemoryAction(
                        () => requestJson(
                            `/memory/${encodeURIComponent(item.id)}?user_id=${encodeURIComponent(state.userId)}`,
                            { method: "DELETE" },
                        ),
                        "长期记忆已删除",
                    );
                },
            }],
        })));
    }

    async function renderMemoryObservations() {
        const data = await requestJson(
            `/memory/observations?user_id=${encodeURIComponent(state.userId)}&status=open&limit=100`,
        );
        const items = Array.isArray(data.observations) ? data.observations : [];
        if (!items.length) {
            renderMemoryEmpty("暂无待验证线索。系统只会在有依据时生成线索。");
            return;
        }
        const kindLabels = {
            preference: "个人偏好",
            goal: "健身目标",
            constraint: "健康与训练约束",
            fact: "个人信息",
            note: "备注",
        };
        elements.memoryDialogBody.replaceChildren(...items.map((item) => {
            const needsReview = item.status === "review_required";
            return createMemoryCard({
                title: kindLabels[item.kind] || "待验证线索",
                content: item.content,
                badges: [
                    { text: needsReview ? "需你确认" : "低风险线索", tone: needsReview ? "review" : "observed" },
                    { text: `${item.evidence_count} 条证据 / ${item.conversation_count} 次对话` },
                    { text: `置信度 ${Math.round((item.confidence ?? 0) * 100)}%` },
                ],
                detail: item.expires_at ? `未再次出现时将于 ${formatMemoryTime(item.expires_at)} 过期` : "",
                actions: [
                    {
                        label: "确认记住",
                        tone: "primary",
                        onClick: () => runMemoryAction(
                            () => requestJson(
                                `/memory/observations/${encodeURIComponent(item.id)}/confirm?user_id=${encodeURIComponent(state.userId)}`,
                                { method: "POST" },
                            ),
                            "已转为长期记忆",
                        ),
                    },
                    {
                        label: "忽略",
                        onClick: () => runMemoryAction(
                            () => requestJson(
                                `/memory/observations/${encodeURIComponent(item.id)}/reject?user_id=${encodeURIComponent(state.userId)}`,
                                { method: "POST" },
                            ),
                            "线索已忽略",
                        ),
                    },
                ],
            });
        }));
    }

    async function renderMemoryEvents() {
        const data = await requestJson(`/memory/events?user_id=${encodeURIComponent(state.userId)}&limit=100`);
        const items = Array.isArray(data.events) ? data.events : [];
        if (!items.length) {
            renderMemoryEmpty("暂无记忆变更记录。");
            return;
        }
        const eventLabels = {
            capture: "捕获线索",
            reinforce: "补充证据",
            promote: "自动晋升",
            confirm: "用户确认",
            reject: "用户忽略",
            edit: "修改记忆",
            delete: "删除记忆",
            supersede: "替换旧记忆",
            expire: "线索过期",
            undo: "撤销操作",
        };
        elements.memoryDialogBody.replaceChildren(...items.map((item) => createMemoryCard({
            title: eventLabels[item.event_type] || item.event_type,
            content: item.payload?.content || item.payload?.observation_content || `对象：${item.subject_type}`,
            badges: [
                { text: item.actor === "user" ? "用户操作" : "系统操作" },
                ...(item.undone_at ? [{ text: "已撤销", tone: "review" }] : []),
            ],
            detail: formatMemoryTime(item.created_at),
            actions: item.reversible && !item.undone_at ? [{
                label: "撤销",
                onClick: () => runMemoryAction(
                    () => requestJson(
                        `/memory/events/${encodeURIComponent(item.id)}/undo?user_id=${encodeURIComponent(state.userId)}`,
                        { method: "POST" },
                    ),
                    "记忆变更已撤销",
                ),
            }] : [],
        })));
    }

    async function loadMemoryTab() {
        elements.memoryDialogBody.replaceChildren();
        const loading = document.createElement("p");
        loading.className = "memory-loading";
        loading.textContent = "正在读取记忆…";
        elements.memoryDialogBody.appendChild(loading);
        try {
            if (state.memoryTab === "observations") {
                await renderMemoryObservations();
            } else if (state.memoryTab === "events") {
                await renderMemoryEvents();
            } else {
                await renderDurableMemories();
            }
        } catch (error) {
            renderMemoryEmpty(`读取失败：${error.message}`);
        }
    }

    function selectMemoryTab(tab) {
        state.memoryTab = tab;
        for (const button of elements.memoryTabs) {
            const selected = button.dataset.memoryTab === tab;
            button.classList.toggle("active", selected);
            button.setAttribute("aria-selected", String(selected));
        }
        loadMemoryTab();
    }

    function openMemoryDialog() {
        elements.memoryBackdrop.hidden = false;
        elements.body.classList.add("memory-dialog-open");
        closeSidebar();
        loadMemoryTab();
        elements.closeMemoryDialog.focus();
    }

    function closeMemoryDialog() {
        elements.memoryBackdrop.hidden = true;
        elements.body.classList.remove("memory-dialog-open");
        elements.memoryManager.focus();
    }

    function handlePrimaryAction() {
        if (state.activeController) {
            stopGeneration();
            return;
        }
        if (state.selectedFile) {
            uploadSelectedMedia();
            return;
        }
        sendMessage(elements.input.value);
    }

    function handleChatWheel(event) {
        if (event.ctrlKey || elements.chatScroll.scrollHeight <= elements.chatScroll.clientHeight) return;
        const target = event.target instanceof Element ? event.target : null;
        if (target?.closest("textarea, input, select, pre")) return;
        const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
            ? 32
            : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
                ? elements.chatScroll.clientHeight
                : 1;
        const maximum = elements.chatScroll.scrollHeight - elements.chatScroll.clientHeight;
        const next = Math.max(0, Math.min(maximum, elements.chatScroll.scrollTop + event.deltaY * unit));
        if (next === elements.chatScroll.scrollTop) return;
        elements.chatScroll.scrollTop = next;
        state.autoFollow = isNearBottom();
        event.preventDefault();
    }

    function bindEvents() {
        elements.openSidebar.addEventListener("click", openSidebar);
        elements.closeSidebar.addEventListener("click", closeSidebar);
        elements.backdrop.addEventListener("click", closeSidebar);
        elements.newChat.addEventListener("click", startNewConversation);
        elements.temporaryChat.addEventListener("click", startTemporaryConversation);
        elements.memoryManager.addEventListener("click", openMemoryDialog);
        elements.closeMemoryDialog.addEventListener("click", closeMemoryDialog);
        elements.memoryBackdrop.addEventListener("click", (event) => {
            if (event.target === elements.memoryBackdrop) closeMemoryDialog();
        });
        elements.memoryTabs.forEach((button) => {
            button.addEventListener("click", () => selectMemoryTab(button.dataset.memoryTab));
        });
        elements.searchConversations.addEventListener("click", () => toggleConversationSearch());
        elements.clearConversationSearch.addEventListener("click", () => {
            state.conversationSearch = "";
            elements.conversationSearchInput.value = "";
            renderConversationList();
            elements.conversationSearchInput.focus();
        });
        elements.conversationSearchInput.addEventListener("input", () => {
            state.conversationSearch = elements.conversationSearchInput.value;
            renderConversationList();
        });
        elements.send.addEventListener("click", handlePrimaryAction);
        elements.attach.addEventListener("click", () => elements.mediaInput.click());
        elements.removeAttachment.addEventListener("click", () => setAttachment(null));
        elements.modelSelect.addEventListener("change", () => {
            state.modelId = elements.modelSelect.value || null;
            if (state.modelId) localStorage.setItem(MODEL_ID_KEY, state.modelId);
        });

        elements.mediaInput.addEventListener("change", (event) => {
            const [file] = event.target.files || [];
            if (file) setAttachment(file);
        });

        elements.input.addEventListener("input", resizeTextarea);
        elements.chatScroll.addEventListener("scroll", () => {
            state.autoFollow = isNearBottom();
        }, { passive: true });
        elements.chatScroll.addEventListener("wheel", handleChatWheel, { passive: false });
        elements.input.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                handlePrimaryAction();
            }
        });

        for (const card of document.querySelectorAll(".suggestion-card")) {
            card.addEventListener("click", () => {
                elements.input.value = card.dataset.prompt || "";
                resizeTextarea();
                elements.input.focus();
            });
        }

        window.addEventListener("resize", () => {
            if (window.innerWidth > 840) closeSidebar();
        });
        document.addEventListener("click", (event) => {
            if (!elements.conversationList.contains(event.target)) closeConversationMenus();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !elements.memoryBackdrop.hidden) closeMemoryDialog();
        });
    }

    async function initialize() {
        bindEvents();
        resizeTextarea();
        await Promise.all([checkHealth(), loadModels(), loadConversations()]);
        elements.input.focus();
    }

    initialize();
})();
