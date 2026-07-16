"""滑动窗口记忆系统 — 基于 collections.deque 实现."""
from collections import deque
import threading
from typing import Dict, List


class SlidingWindowMemory:
    """可配置容量的滑动窗口记忆,自动淘汰最旧记录."""

    def __init__(self, max_turns: int = 6):
        """
        Args:
            max_turns: 最大保留轮次(每轮=user+assistant两条消息).
                       设为0表示无限制.
        """
        self.max_turns = max_turns
        self._buffer: deque = deque()
        self._lock = threading.RLock()

    def add(self, message: Dict[str, str]) -> None:
        """添加一条消息到记忆.

        Args:
            message: {"role": "user|assistant", "content": "..."}
        """
        with self._lock:
            max_messages = self.max_turns * 2 if self.max_turns > 0 else None
            if max_messages and len(self._buffer) >= max_messages:
                self._buffer.popleft()
            self._buffer.append(message)

    def add_turn(self, user_msg: str, assistant_msg: str) -> None:
        """便捷方法:同时添加一轮对话(user + assistant)."""
        with self._lock:
            self.add({"role": "user", "content": user_msg})
            self.add({"role": "assistant", "content": assistant_msg})

    def get_all(self) -> List[Dict[str, str]]:
        """返回所有记忆中的消息(按时间顺序)."""
        with self._lock:
            return list(self._buffer)

    def get_last_n(self, n: int) -> List[Dict[str, str]]:
        """返回最近n条消息."""
        with self._lock:
            return list(self._buffer)[-n:] if n > 0 else []

    def clear(self) -> None:
        """清空全部记忆."""
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)
