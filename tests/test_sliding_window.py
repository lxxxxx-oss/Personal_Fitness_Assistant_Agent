"""滑动窗口记忆测试."""
from concurrent.futures import ThreadPoolExecutor

from app.memory.sliding_window import SlidingWindowMemory


class TestSlidingWindowMemory:
    def test_add_and_get_all(self):
        mem = SlidingWindowMemory(max_turns=3)
        mem.add({"role": "user", "content": "你好"})
        mem.add({"role": "assistant", "content": "你好！"})
        history = mem.get_all()
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_evicts_oldest_when_full(self):
        mem = SlidingWindowMemory(max_turns=1)
        mem.add({"role": "user", "content": "msg1"})
        mem.add({"role": "assistant", "content": "reply1"})
        mem.add({"role": "user", "content": "msg2"})
        mem.add({"role": "assistant", "content": "reply2"})
        history = mem.get_all()
        assert len(history) == 2
        assert history[0]["content"] == "msg2"

    def test_clear(self):
        mem = SlidingWindowMemory(max_turns=5)
        mem.add({"role": "user", "content": "test"})
        mem.clear()
        assert len(mem.get_all()) == 0

    def test_max_turns_zero_means_unlimited(self):
        mem = SlidingWindowMemory(max_turns=0)
        for i in range(50):
            mem.add({"role": "user", "content": f"msg{i}"})
        assert len(mem.get_all()) == 50

    def test_get_last_n(self):
        mem = SlidingWindowMemory(max_turns=10)
        mem.add({"role": "user", "content": "a"})
        mem.add({"role": "assistant", "content": "b"})
        mem.add({"role": "user", "content": "c"})
        recent = mem.get_last_n(2)
        assert len(recent) == 2
        assert recent[0]["content"] == "b"

    def test_concurrent_turns_remain_atomic(self):
        mem = SlidingWindowMemory(max_turns=6)

        def add(index):
            mem.add_turn(f"question-{index}", f"answer-{index}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(add, range(40)))

        history = mem.get_all()
        assert len(history) == 12
        for index in range(0, len(history), 2):
            assert history[index]["role"] == "user"
            assert history[index + 1]["role"] == "assistant"
            assert history[index]["content"].split("-")[-1] == (
                history[index + 1]["content"].split("-")[-1]
            )
