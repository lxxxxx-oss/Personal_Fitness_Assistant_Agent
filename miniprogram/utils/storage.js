/**
 * 本地存储封装 — 持久化 userId 和服务地址.
 */

const KEYS = {
  USER_ID: 'user_id',
  API_BASE: 'api_base_url',
};

/**
 * 获取或生成 userId.
 * 首次调用时生成唯一 ID 并持久化，后续调用返回已有 ID.
 */
function getUserId() {
  let userId = wx.getStorageSync(KEYS.USER_ID);
  if (!userId) {
    const ts = Date.now();
    const rand = Math.random().toString(36).slice(2, 8);
    userId = `wx_user_${ts}_${rand}`;
    wx.setStorageSync(KEYS.USER_ID, userId);
  }
  return userId;
}

/**
 * 获取 API 基础地址.
 */
function getApiBase() {
  const { API_CONFIG } = require('./constants');
  return wx.getStorageSync(KEYS.API_BASE) || API_CONFIG.baseUrl;
}

/**
 * 设置 API 基础地址.
 */
function setApiBase(url) {
  wx.setStorageSync(KEYS.API_BASE, url);
}

module.exports = {
  getUserId,
  getApiBase,
  setApiBase,
};
