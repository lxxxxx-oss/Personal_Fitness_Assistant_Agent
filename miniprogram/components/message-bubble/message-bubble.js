/**
 * 消息气泡组件 — 渲染单条聊天消息.
 */
const { INTENT_MAP } = require('../../utils/constants');

Component({
  properties: {
    role: {
      type: String,
      value: 'user',
    },
    intent: {
      type: String,
      value: '',
    },
    content: {
      type: String,
      value: '',
      observer: '_onContentChange',
    },
    isStreaming: {
      type: Boolean,
      value: false,
    },
    timestamp: {
      type: Number,
      value: 0,
    },
    isError: {
      type: Boolean,
      value: false,
    },
    sources: {
      type: Array,
      value: [],
    },
    warnings: {
      type: Array,
      value: [],
    },
    execution: {
      type: Array,
      value: [],
    },
    msgId: {
      type: String,
      value: '',
    },
  },

  data: {
    displayContent: '',
    intentInfo: null,
    formattedTime: '',
  },

  lifetimes: {
    attached() {
      this._updateDisplay();
    },
  },

  methods: {
    _onContentChange(newVal) {
      this._updateDisplay();
    },

    _updateDisplay() {
      const cleanContent = this._stripThinkTags(this.properties.content);
      const intentInfo = this.properties.intent
        ? INTENT_MAP[this.properties.intent] || null
        : null;
      const formattedTime = this._formatTime(this.properties.timestamp);
      this.setData({
        displayContent: cleanContent,
        intentInfo: intentInfo,
        formattedTime: formattedTime,
      });
    },

    _stripThinkTags(text) {
      if (!text) return '';
      return text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    },

    _formatTime(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      const pad = (n) => String(n).padStart(2, '0');
      return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
  },
});
