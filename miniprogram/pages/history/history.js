/**
 * history 页面 — 对话历史查看.
 */
const { getUserId } = require('../../utils/storage');
const { getHistory, clearHistory } = require('../../utils/api');

Page({
  data: {
    history: [],
    isEmpty: true,
    isLoading: true,
    error: '',
  },

  onShow() {
    this.loadHistory();
  },

  async loadHistory() {
    this.setData({ isLoading: true, error: '' });

    try {
      const userId = getUserId();
      const result = await getHistory(userId);
      const history = result.history || [];
      this.setData({
        history: history,
        isEmpty: history.length === 0,
        isLoading: false,
      });
    } catch (err) {
      this.setData({
        isLoading: false,
        error: err.message,
      });
    }
  },

  onClearHistory() {
    const self = this;
    wx.showModal({
      title: '清空历史',
      content: '确定要清空所有对话历史吗？此操作不可撤销。',
      confirmColor: '#ef4444',
      success: async function (res) {
        if (res.confirm) {
          try {
            const userId = getUserId();
            await clearHistory(userId);
            self.setData({ history: [], isEmpty: true });
            wx.showToast({ title: '已清空', icon: 'success' });
          } catch (err) {
            wx.showToast({ title: '清空失败', icon: 'error' });
          }
        }
      },
    });
  },

  onPullDownRefresh() {
    this.loadHistory().finally(() => {
      wx.stopPullDownRefresh();
    });
  },
});
