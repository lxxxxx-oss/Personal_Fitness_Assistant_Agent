/**
 * 健身智能助手 — 微信小程序入口.
 */
const { getUserId } = require('./utils/storage');
const { healthCheck } = require('./utils/api');

App({
  onLaunch() {
    // 初始化 userId
    this.globalData.userId = getUserId();
    console.log('[App] userId:', this.globalData.userId);

    // 健康检查
    healthCheck()
      .then((data) => {
        this.globalData.serverOnline = true;
        this.globalData.serverVersion = data.version;
        console.log(`[App] Server online, version: ${data.version}`);
      })
      .catch((err) => {
        this.globalData.serverOnline = false;
        console.warn('[App] Server offline:', err.message);
      });
  },

  globalData: {
    userId: '',
    serverOnline: false,
    serverVersion: '',
    currentIntent: 'chat',
  },
});
