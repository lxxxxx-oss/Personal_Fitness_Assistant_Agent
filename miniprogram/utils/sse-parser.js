/**
 * SSE (Server-Sent Events) 流式解析器.
 *
 * 用于解析 POST /chat/stream 返回的 text/event-stream 格式数据.
 * 配合 wx.request 的 enableChunked 使用.
 */

class SseParser {
  constructor(callbacks) {
    this.buffer = '';
    this.eventType = '';
    this.callbacks = {
      onMeta: callbacks.onMeta || null,
      onToken: callbacks.onToken || null,
      onDone: callbacks.onDone || null,
      onError: callbacks.onError || null,
    };
  }

  /**
   * 喂入原始 chunk 数据.
   * @param {ArrayBuffer} chunk - wx.onChunkReceived 回调的 res.data
   */
  feed(chunk) {
    try {
      const text = this._arrayBufferToString(chunk);
      this.buffer += text;
      this._parseLines();
    } catch (err) {
      if (this.callbacks.onError) {
        this.callbacks.onError(err);
      }
    }
  }

  /**
   * 解析缓冲区中的完整行.
   */
  _parseLines() {
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() || '';

    for (const line of lines) {
      this._processLine(line.trim());
    }
  }

  /**
   * 处理单行 SSE 数据.
   */
  _processLine(line) {
    if (line === '') {
      if (this.eventType === 'done') {
        if (this.callbacks.onDone) this.callbacks.onDone();
      }
      this.eventType = '';
      return;
    }

    if (line.startsWith('event:')) {
      this.eventType = line.slice(6).trim();
      return;
    }

    if (line.startsWith('data:')) {
      const data = line.slice(5).trim();
      this._processData(data);
      return;
    }
  }

  /**
   * 处理 data 行内容.
   */
  _processData(data) {
    if (this.eventType === 'meta') {
      try {
        const meta = JSON.parse(data);
        if (this.callbacks.onMeta) this.callbacks.onMeta(meta);
      } catch (e) {
        // meta JSON 解析失败，忽略
      }
      return;
    }

    if (this.eventType === 'done') {
      return;
    }

    // 普通 token — 过滤 think 标签后回调
    const clean = this._stripThinkTags(data);
    if (clean && this.callbacks.onToken) {
      this.callbacks.onToken(clean);
    }
  }

  /**
   * 过滤 Qwen3 模型的 <think>...</think> 标签.
   * 流式场景下处理三种情况:
   *   1. 完整块: <think>text</think>
   *   2. 开头块: <think>text...
   *   3. 尾巴块: ...text</think>
   */
  _stripThinkTags(text) {
    let result = text.replace(/<think>[\s\S]*?<\/think>/g, '');
    if (result.includes('<think>')) {
      result = result.replace(/<think>[\s\S]*$/, '');
    }
    if (result.includes('</think>')) {
      result = result.replace(/<\/think>/g, '');
    }
    return result;
  }

  /**
   * ArrayBuffer 转 UTF-8 字符串.
   * 微信小程序不支持 TextDecoder, 手动转换.
   */
  _arrayBufferToString(buffer) {
    const uint8 = new Uint8Array(buffer);
    let result = '';
    const CHUNK = 4096;
    for (let i = 0; i < uint8.length; i += CHUNK) {
      const slice = uint8.slice(i, i + CHUNK);
      result += String.fromCharCode.apply(null, slice);
    }
    return decodeURIComponent(escape(result));
  }

  /**
   * 重置解析器状态.
   */
  reset() {
    this.buffer = '';
    this.eventType = '';
  }
}

module.exports = { SseParser };
