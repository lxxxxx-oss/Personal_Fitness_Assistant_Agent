/**
 * 后端 API 请求封装.
 */
var getApiBaseFn = require('./storage').getApiBase;
var API_CONFIG = require('./constants').API_CONFIG;

/**
 * 获取 WebSocket URL (从 HTTP URL 转换).
 */
function _getWsBase() {
  var httpBase = getApiBaseFn();
  return httpBase.replace(/^http/, 'ws');
}

/**
 * 通用 GET 请求.
 */
function _get(path) {
  var baseUrl = getApiBaseFn();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: baseUrl + path,
      method: 'GET',
      timeout: 10000,
      success: function (res) {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error('HTTP ' + res.statusCode + ': ' + JSON.stringify(res.data)));
      },
      fail: function (err) { reject(new Error('Network error: ' + err.errMsg)); },
    });
  });
}

/**
 * 通用 POST 请求.
 */
function _post(path, data, timeout) {
  timeout = timeout || 30000;
  var baseUrl = getApiBaseFn();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: baseUrl + path,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: data,
      timeout: timeout,
      success: function (res) {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error('HTTP ' + res.statusCode + ': ' + JSON.stringify(res.data)));
      },
      fail: function (err) { reject(new Error('Network error: ' + err.errMsg)); },
    });
  });
}

/**
 * 健康检查 — GET /health.
 */
function healthCheck() {
  return _get('/health');
}

/**
 * 非流式对话 (HTTP 降级方案) — POST /chat.
 */
function chat(userId, message) {
  return _post('/chat', { user_id: userId, message: message }, 120000);
}

function _uploadMotionFile(path, filePath, label, onProgress) {
  var baseUrl = getApiBaseFn();
  return new Promise(function (resolve, reject) {
    if (!filePath) {
      reject(new Error('请选择需要分析的' + label));
      return;
    }
    var uploadTask = wx.uploadFile({
      url: baseUrl + path,
      filePath: filePath,
      name: 'file',
      timeout: API_CONFIG.timeout,
      success: function (res) {
        var data;
        try {
          data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
        } catch (e) {
          reject(new Error('服务端返回了无法解析的' + label + '分析结果'));
          return;
        }
        if (res.statusCode === 200) {
          resolve(data);
          return;
        }
        var detail = data && data.detail ? data.detail : label + '分析失败';
        reject(new Error('HTTP ' + res.statusCode + ': ' + detail));
      },
      fail: function (err) {
        reject(new Error(label + '上传失败: ' + (err.errMsg || 'Unknown')));
      },
    });
    if (onProgress && uploadTask.onProgressUpdate) {
      uploadTask.onProgressUpdate(function (progress) {
        onProgress(progress.progress || 0);
      });
    }
  });
}

/** 上传动作图片并提取单帧姿态 — POST /motion/analyze-image. */
function analyzeMotionImage(filePath) {
  return _uploadMotionFile('/motion/analyze-image', filePath, '图片');
}

/** 上传动作视频并提取多帧姿态 — POST /motion/analyze-video. */
function analyzeMotionVideo(filePath, onProgress) {
  return _uploadMotionFile('/motion/analyze-video', filePath, '视频', onProgress);
}

/**
 * WebSocket 流式对话 — ws://host/chat/ws.
 *
 * 协议:
 *   Client → Server: {"user_id": "...", "message": "..."}
 *   Server → Client: {"type": "meta", "intent": "chat"}
 *   Server → Client: {"type": "token", "text": "..."}
 *   Server → Client: {"type": "done"}
 *   Server → Client: {"type": "error", "message": "..."}
 *
 * @param {string} userId
 * @param {string} message
 * @param {object} callbacks - { onMeta, onToken, onDone, onError }
 * @returns {WechatMiniprogram.SocketTask}
 */
function wsChat(userId, message, callbacks) {
  var wsUrl = _getWsBase() + '/chat/ws';
  console.log('[WS] Connecting to:', wsUrl);

  var socketTask = wx.connectSocket({
    url: wsUrl,
    header: { 'Content-Type': 'application/json' },
    protocols: [],
    tcpNoDelay: true,
    timeout: API_CONFIG.timeout,
  });

  var isClosed = false;
  var timer = null;

  function cleanup() {
    if (timer) clearTimeout(timer);
    if (!isClosed) {
      isClosed = true;
      try { socketTask.close({ code: 1000, reason: 'done' }); } catch (e) {}
    }
  }

  function onError(msg) {
    if (callbacks.onError && !isClosed) {
      callbacks.onError(new Error(msg));
    }
    cleanup();
  }

  socketTask.onOpen(function () {
    console.log('[WS] Connected, sending message');
    socketTask.send({
      data: JSON.stringify({ user_id: userId, message: message }),
    });

    // 超时保护
    timer = setTimeout(function () {
      onError('WebSocket timeout');
    }, API_CONFIG.timeout);
  });

  socketTask.onMessage(function (res) {
    if (isClosed) return;

    try {
      var msg = JSON.parse(res.data);
      switch (msg.type) {
        case 'meta':
          if (callbacks.onMeta) callbacks.onMeta(msg);
          break;
        case 'token':
          if (callbacks.onToken) callbacks.onToken(msg.text);
          break;
        case 'done':
          if (callbacks.onDone) callbacks.onDone();
          cleanup();
          break;
        case 'error':
          onError(msg.message);
          break;
        default:
          console.warn('[WS] Unknown message type:', msg.type);
      }
    } catch (e) {
      console.warn('[WS] Failed to parse message:', res.data);
    }
  });

  socketTask.onError(function (err) {
    onError('WebSocket error: ' + (err.errMsg || 'Unknown'));
  });

  socketTask.onClose(function () {
    cleanup();
  });

  return socketTask;
}

/**
 * 获取对话历史 — GET /chat/{userId}/history.
 */
function getHistory(userId) {
  return _get('/chat/' + encodeURIComponent(userId) + '/history');
}

/**
 * 清空对话历史 — DELETE /chat/{userId}/history.
 */
function clearHistory(userId) {
  var baseUrl = getApiBaseFn();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: baseUrl + '/chat/' + encodeURIComponent(userId) + '/history',
      method: 'DELETE',
      timeout: 10000,
      success: function (res) {
        if (res.statusCode === 200) resolve(res.data);
        else reject(new Error('HTTP ' + res.statusCode));
      },
      fail: function (err) { reject(new Error('Network error: ' + err.errMsg)); },
    });
  });
}

module.exports = {
  healthCheck: healthCheck,
  chat: chat,
  analyzeMotionImage: analyzeMotionImage,
  analyzeMotionVideo: analyzeMotionVideo,
  wsChat: wsChat,
  getHistory: getHistory,
  clearHistory: clearHistory,
};
