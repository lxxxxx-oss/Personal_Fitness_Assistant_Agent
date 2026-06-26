/**
 * 意图标签组件.
 */
const { INTENT_MAP } = require('../../utils/constants');

Component({
  properties: {
    intent: {
      type: String,
      value: 'chat',
    },
    active: {
      type: Boolean,
      value: false,
    },
    size: {
      type: String,
      value: 'small',
    },
  },

  data: {
    info: null,
  },

  lifetimes: {
    attached() {
      this._updateInfo();
    },
  },

  observers: {
    'intent'(newVal) {
      this._updateInfo();
    },
  },

  methods: {
    _updateInfo() {
      const info = INTENT_MAP[this.properties.intent] || INTENT_MAP.chat;
      this.setData({ info });
    },

    onTap() {
      this.triggerEvent('tap', { intent: this.properties.intent });
    },
  },
});
