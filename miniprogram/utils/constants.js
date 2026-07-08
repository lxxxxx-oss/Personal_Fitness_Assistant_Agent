/**
 * 全局常量定义.
 */

// 意图映射表
const INTENT_MAP = {
  chat:   { label: '知识问答', color: '#5eead4', icon: '💬', bgColor: '#0f766e' },
  search: { label: '联网搜索', color: '#93c5fd', icon: '🔍', bgColor: '#1e3a5f' },
  motion: { label: '动作分析', color: '#c4b5fd', icon: '🏃', bgColor: '#3b2f5e' },
  diet:   { label: '饮食推荐', color: '#fde68a', icon: '🥗', bgColor: '#5c4b1f' },
  mcp:    { label: '菜谱查询', color: '#fca5a5', icon: '🍳', bgColor: '#5c2d2d' },
};

// 意图列表（用于横向滚动标签栏）
const INTENT_LIST = [
  { key: 'chat',   label: '💬 知识问答' },
  { key: 'search', label: '🔍 联网搜索' },
  { key: 'motion', label: '🏃 动作分析' },
  { key: 'diet',   label: '🥗 饮食推荐' },
  { key: 'mcp',    label: '🍳 菜谱查询' },
];

// API 配置
const API_CONFIG = {
  baseUrl: 'http://127.0.0.1:8000',
  timeout: 120000,
};

// 流式渲染节流间隔 (ms)
const STREAM_THROTTLE_MS = 50;

// 消息列表最大渲染条数
const MAX_VISIBLE_MESSAGES = 100;
const MAX_MOTION_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_MOTION_VIDEO_BYTES = 30 * 1024 * 1024;

module.exports = {
  INTENT_MAP,
  INTENT_LIST,
  API_CONFIG,
  STREAM_THROTTLE_MS,
  MAX_VISIBLE_MESSAGES,
  MAX_MOTION_IMAGE_BYTES,
  MAX_MOTION_VIDEO_BYTES,
};
