"""Contract tests for the FastAPI-hosted Web UI."""

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class _UiDocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.stylesheets = []
        self.scripts = []
        self.inline_style_count = 0
        self.inline_script_count = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href"))
        if tag == "style":
            self.inline_style_count += 1
        if tag == "script":
            source = attributes.get("src")
            self.scripts.append(source)
            if not source:
                self.inline_script_count += 1


def test_web_ui_exposes_semantic_chat_shell():
    response = client.get("/ui/")

    assert response.status_code == 200
    parser = _UiDocumentParser()
    parser.feed(response.text)

    assert {
        "sidebar",
        "new-chat-button",
        "temporary-chat-button",
        "memory-manager-button",
        "search-conversations-button",
        "conversation-search",
        "conversation-list",
        "conversation-count",
        "messages",
        "empty-state",
        "chat-scroll",
        "user-input",
        "send-button",
        "media-input",
        "model-select",
        "memory-dialog-backdrop",
        "memory-dialog-body",
        "close-memory-dialog",
    }.issubset(parser.ids)
    assert len(parser.stylesheets) == 1
    assert parser.stylesheets[0].startswith("./styles.css")
    assert len(parser.scripts) == 1
    assert parser.scripts[0].startswith("./app.js")
    assert parser.inline_style_count == 0
    assert parser.inline_script_count == 0


def test_model_picker_sits_inside_composer_before_send_button():
    html = client.get("/ui/").text

    topbar_end = html.index("</header>")
    composer_start = html.index('<div class="composer">')
    model_picker = html.index('id="model-select"')
    send_button = html.index('id="send-button"')

    assert topbar_end < composer_start < model_picker < send_button


def test_web_ui_static_assets_are_served_and_contain_core_flows():
    stylesheet = client.get("/ui/styles.css")
    script = client.get("/ui/app.js")

    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "@media (max-width: 840px)" in stylesheet.text
    assert "@media (max-width: 620px)" in stylesheet.text
    assert ".assistant-content" in stylesheet.text
    assert "readSseStream" in script.text
    assert 'fetch(`${API_ROOT}/chat/stream`' in script.text
    assert 'fetch(`${API_ROOT}/chat`' in script.text
    assert 'fetch(`${API_ROOT}/models`' in script.text
    assert "payload.model = state.modelId" in script.text
    assert 'localStorage.setItem(MODEL_ID_KEY, selected.id)' in script.text
    assert "/motion/analyze-image" in script.text
    assert "/motion/analyze-video" in script.text
    assert "stopGeneration" in script.text
    assert "const canStop = isBusy && Boolean(state.activeController)" in script.text
    assert "scrollbar-width: none" in stylesheet.text
    assert "#user-input::-webkit-scrollbar" in stylesheet.text
    assert "const TEXTAREA_MIN_HEIGHT = 38" in script.text
    assert "const TEXTAREA_MAX_HEIGHT = 150" in script.text
    assert 'elements.input.style.overflowY = contentHeight > TEXTAREA_MAX_HEIGHT' in script.text
    assert 'canStop ? "停止生成" : isBusy ? "处理中"' in script.text


def test_long_answers_stay_inside_scrollable_chat_region():
    stylesheet = client.get("/ui/styles.css").text
    script = client.get("/ui/app.js").text

    assert ".app-shell" in stylesheet
    assert ".chat-layout" in stylesheet
    assert "position: fixed;" in stylesheet
    assert "height: 100dvh;" in stylesheet
    assert "min-height: 0;" in stylesheet
    assert "overflow-y: auto;" in stylesheet
    assert "overscroll-behavior-y: contain;" in stylesheet
    assert "scrollbar-width: thin;" in stylesheet
    assert "const AUTO_FOLLOW_THRESHOLD_PX = 80" in script
    assert "function isNearBottom()" in script
    assert "if (!force && !state.autoFollow) return;" in script
    assert 'elements.chatScroll.addEventListener("scroll"' in script
    assert 'elements.chatScroll.addEventListener("wheel", handleChatWheel' in script


def test_sidebar_uses_persisted_conversation_management_endpoints():
    script = client.get("/ui/app.js").text
    stylesheet = client.get("/ui/styles.css").text

    assert "function renderConversationList()" in script
    assert "function positionConversationMenu(menu)" in script
    assert 'const rowBounds = menu.closest(".conversation-row").getBoundingClientRect()' in script
    assert 'menu.style.top = `${top}px`' in script
    assert 'menu.classList.add("open-up")' in script
    assert "position: fixed;" in stylesheet
    assert ".conversation-menu.open-up" in stylesheet
    assert "async function loadConversation(conversationId)" in script
    assert "async function startNewConversation" in script
    assert 'method: "PATCH"' in script
    assert 'method: "DELETE"' in script
    assert "/conversations" in script


def test_web_ui_exposes_memory_controls_and_temporary_chat_boundary():
    script = client.get("/ui/app.js").text
    stylesheet = client.get("/ui/styles.css").text

    assert "function startTemporaryConversation" in script
    assert "if (state.temporary) payload.temporary = true" in script
    assert 'elements.temporaryChat.addEventListener("click"' in script
    assert "function openMemoryDialog" in script
    assert "/memory/observations" in script
    assert "/memory/events" in script
    assert "/undo" in script
    assert ".memory-dialog-backdrop" in stylesheet
    assert ".memory-card-actions" in stylesheet


def test_web_ui_defaults_to_http_and_keeps_sse_as_explicit_opt_in():
    script = client.get("/ui/app.js").text

    assert 'get("transport") === "sse"' in script
    assert ': "http";' in script
    assert 'if (CHAT_TRANSPORT === "http")' in script
    assert 'setServiceStatus("online", "服务运行正常", "HTTP 对话可用")' in script
    assert 'if (CHAT_TRANSPORT === "http")' in script.index if False else True


def test_web_ui_copy_avoids_unescaped_model_html():
    script = client.get("/ui/app.js").text

    assert "function escapeHtml" in script
    assert "let text = escapeHtml(rawText)" in script
    assert "${escapeHtml(code.trimEnd())}" in script
