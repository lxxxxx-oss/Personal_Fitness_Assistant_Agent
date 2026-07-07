/**
 * chat 页面 — 主聊天界面 (WebSocket 流式 + HTTP 降级).
 */
var getUserId = require('../../utils/storage').getUserId;
var api = require('../../utils/api');
var CONST = require('../../utils/constants');

var app = getApp();

Page({
  data: {
    messages: [],
    inputValue: '',
    isSending: false,
    currentIntent: 'chat',
    intentList: CONST.INTENT_LIST,
    scrollToId: '',
    serverOnline: true,
    useWebSocket: true,
    showRetry: false,
    isUploading: false,
  },

  onLoad: function () {
    var userId = getUserId();
    this.userId = userId;
    this.msgCounter = 0;
    this.socketTask = null;

    // Check if WebSocket is available (base library 1.7.0+)
    this._checkWsSupport();

    // Welcome message
    this._addMessage('assistant',
      '你好！我是你的健身智能助手。💪\n\n' +
      '我支持以下功能：\n' +
      '💬 知识问答 — "如何做深蹲？"\n' +
      '🥗 饮食推荐 — "减脂期间吃什么？"\n' +
      '🏃 动作分析 — "分析深蹲姿势"\n' +
      '🍳 菜谱查询 — "怎么做番茄炒蛋？"\n' +
      '🔍 联网搜索 — "搜索最新健身资讯"\n\n' +
      '也可以点击输入框左侧的 📷，上传一张动作图片进行静态姿态提取。\n\n' +
      '系统会自动识别你的意图并路由到对应的专业模块处理。',
      'chat'
    );
  },

  onUnload: function () {
    if (this.socketTask) {
      try { this.socketTask.close({ code: 1000, reason: 'page unload' }); } catch (e) {}
      this.socketTask = null;
    }
  },

  _checkWsSupport: function () {
    try {
      var systemInfo = wx.getSystemInfoSync();
      var SDKVersion = systemInfo.SDKVersion;
      var parts = SDKVersion.split('.');
      var major = parseInt(parts[0], 10);
      var minor = parseInt(parts[1], 10);
      // WebSocket available since 1.7.0, very safe
      // But we check anyway
      if (major < 1 || (major === 1 && minor < 7)) {
        console.warn('[Chat] WebSocket not supported, using HTTP fallback');
        this.setData({ useWebSocket: false });
      }
    } catch (e) {
      // Default to WebSocket
    }
  },

  onInput: function (e) {
    this.setData({ inputValue: e.detail.value });
  },

  sendMessage: function () {
    var msg = this.data.inputValue.trim();
    if (!msg || this.data.isSending) return;

    this.setData({ inputValue: '', isSending: true, showRetry: false });
    this._addMessage('user', msg);

    if (this.data.useWebSocket) {
      this._sendViaWebSocket(msg);
    } else {
      this._sendViaHttp(msg);
    }
  },

  chooseMotionImage: function () {
    if (this.data.isSending) return;
    var self = this;

    function handleSelected(filePath, size) {
      if (!filePath) return;
      if (size && size > CONST.MAX_MOTION_IMAGE_BYTES) {
        wx.showToast({ title: '图片不能超过 10MB', icon: 'none' });
        return;
      }
      self._uploadMotionImage(filePath);
    }

    if (wx.chooseMedia) {
      wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        sizeType: ['compressed'],
        success: function (res) {
          var file = res.tempFiles && res.tempFiles[0];
          if (file) handleSelected(file.tempFilePath, file.size);
        },
        fail: function (err) {
          if (!(err.errMsg || '').includes('cancel')) {
            wx.showToast({ title: '无法选择图片', icon: 'none' });
          }
        },
      });
      return;
    }

    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function (res) {
        var file = res.tempFiles && res.tempFiles[0];
        handleSelected(res.tempFilePaths[0], file && file.size);
      },
      fail: function (err) {
        if (!(err.errMsg || '').includes('cancel')) {
          wx.showToast({ title: '无法选择图片', icon: 'none' });
        }
      },
    });
  },

  _uploadMotionImage: function (filePath) {
    var filename = filePath.split('/').pop() || '动作图片';
    this.setData({
      isSending: true,
      isUploading: true,
      currentIntent: 'motion',
      showRetry: false,
    });
    this._addMessage(
      'user',
      '请分析这张动作图片：' + filename,
      'motion',
      false,
      [],
      [],
      [],
      filePath
    );
    var assistantId = this._addMessage('assistant', '正在提取人体关键点...', 'motion', true);
    var self = this;

    api.analyzeMotionImage(filePath).then(function (result) {
      var confidence = result.confidence_summary || {};
      var meanConfidence = typeof confidence.mean === 'number'
        ? Math.round(confidence.mean * 100) + '%'
        : '未提供';
      var content = [
        '图片姿态提取完成',
        '',
        '帧数：' + result.frames,
        '关键点：' + result.joints,
        '姿态模型：' + result.pose_model,
        '关键点规范：' + result.joint_schema,
        '平均置信度：' + meanConfidence,
        '',
        result.message,
      ].join('\n');
      self._updateMessage(
        assistantId,
        content,
        'motion',
        false,
        false,
        [],
        result.warnings || [],
        result.execution || []
      );
    }).catch(function (err) {
      self._updateMessage(
        assistantId,
        '❌ 图片分析失败：' + err.message + '\n请确认后端已安装 Motion 依赖并准备姿态模型。',
        'motion',
        false,
        true
      );
    }).finally(function () {
      self.setData({ isSending: false, isUploading: false });
      self._scrollToBottom();
    });
  },

  /**
   * WebSocket 流式发送 — 主路径.
   */
  _sendViaWebSocket: function (msg) {
    var assistantId = this._addMessage('assistant', '', '', true);
    var fullContent = '';
    var pendingContent = '';
    var throttleTimer = null;
    var intent = '';
    var sources = [];
    var warnings = [];
    var execution = [];
    var self = this;

    function updateUI() {
      fullContent += pendingContent;
      pendingContent = '';
      throttleTimer = null;
      self._updateMessage(assistantId, fullContent, intent, true, false, sources, warnings, execution);
    }

    this.socketTask = api.wsChat(this.userId, msg, {
      onMeta: function (meta) {
        intent = meta.intent || 'chat';
        sources = meta.sources || [];
        warnings = meta.warnings || [];
        execution = meta.execution || [];
        self.setData({ currentIntent: intent });
        self._updateMessage(assistantId, fullContent, intent, true, false, sources, warnings, execution);
      },

      onToken: function (token) {
        pendingContent += token;
        if (!throttleTimer) {
          throttleTimer = setTimeout(updateUI, CONST.STREAM_THROTTLE_MS);
        }
      },

      onDone: function () {
        if (throttleTimer) {
          clearTimeout(throttleTimer);
          updateUI();
        }
        // Final cleanup: strip any remaining think tags
        var cleaned = fullContent.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
        self._updateMessage(assistantId, cleaned, intent, false, false, sources, warnings, execution);
        self.setData({ isSending: false });
        self.socketTask = null;
        self._scrollToBottom();
      },

      onError: function (err) {
        console.error('[Chat] WS error:', err.message);
        if (throttleTimer) {
          clearTimeout(throttleTimer);
          updateUI();
        }
        // If we got some content, show it + error; otherwise fallback to HTTP
        if (fullContent) {
          self._updateMessage(
            assistantId,
            fullContent + '\n\n⚠️ 连接中断',
            intent || 'chat',
            false,
            true,
            sources,
            warnings,
            execution
          );
          self.setData({ isSending: false, showRetry: true });
        } else {
          // No content received — fallback to HTTP
          console.log('[Chat] WS failed with no content, falling back to HTTP');
          self.setData({ isSending: false });
          self._sendViaHttp(msg);
          return;
        }
        self.socketTask = null;
      },
    });
  },

  /**
   * HTTP 非流式发送 — 降级方案.
   */
  _sendViaHttp: function (msg) {
    var assistantId = this._addMessage('assistant', '思考中...', 'chat', true);
    var self = this;

    api.chat(this.userId, msg).then(function (result) {
      self._updateMessage(
        assistantId,
        result.reply,
        result.intent,
        false,
        false,
        result.sources || [],
        result.warnings || [],
        result.execution || []
      );
      self.setData({ currentIntent: result.intent });
    }).catch(function (err) {
      self._updateMessage(assistantId, '❌ ' + err.message, 'chat', false, true);
      self.setData({ showRetry: true });
    }).finally(function () {
      self.setData({ isSending: false });
      self._scrollToBottom();
    });
  },

  retrySend: function () {
    var messages = this.data.messages;
    if (messages.length > 0 && messages[messages.length - 1].isError) {
      messages.pop();
      this.setData({ messages: messages });
    }
    this.setData({ showRetry: false });
  },

  _addMessage: function (role, content, intent, isStreaming, sources, warnings, execution, imagePath) {
    intent = intent || '';
    isStreaming = isStreaming || false;
    sources = sources || [];
    warnings = warnings || [];
    execution = execution || [];
    imagePath = imagePath || '';
    var id = 'msg_' + (this.msgCounter++);
    var msg = {
      id: id,
      role: role,
      content: content,
      intent: intent,
      isStreaming: isStreaming,
      isError: false,
      sources: sources,
      warnings: warnings,
      execution: execution,
      imagePath: imagePath,
      timestamp: Date.now(),
    };
    var messages = this.data.messages.concat([msg]);
    if (messages.length > CONST.MAX_VISIBLE_MESSAGES) {
      messages.splice(0, messages.length - CONST.MAX_VISIBLE_MESSAGES);
    }
    this.setData({ messages: messages, scrollToId: id });
    return id;
  },

  _updateMessage: function (id, content, intent, isStreaming, isError, sources, warnings, execution) {
    intent = intent || '';
    isStreaming = isStreaming || false;
    isError = isError || false;
    var messages = this.data.messages.map(function (m) {
      if (m.id === id) {
        return {
          id: m.id,
          role: m.role,
          content: content,
          intent: intent,
          isStreaming: isStreaming,
          isError: isError,
          sources: sources || m.sources || [],
          warnings: warnings || m.warnings || [],
          execution: execution || m.execution || [],
          imagePath: m.imagePath || '',
          timestamp: Date.now(),
        };
      }
      return m;
    });
    this.setData({ messages: messages });
  },

  _scrollToBottom: function () {
    var messages = this.data.messages;
    if (messages.length > 0) {
      this.setData({ scrollToId: messages[messages.length - 1].id });
    }
  },

  clearChat: function () {
    var self = this;
    wx.showModal({
      title: '清空对话',
      content: '确定要清空当前对话吗？',
      success: function (res) {
        if (res.confirm) {
          self.setData({ messages: [] });
        }
      },
    });
  },
});
