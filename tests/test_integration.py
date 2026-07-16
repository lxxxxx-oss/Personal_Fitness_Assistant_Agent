"""Full integration tests — intent routing and memory."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestIntegration:
    def test_full_chat_flow_with_memory(self):
        """End-to-end: multi-turn conversation with memory."""
        user_id = "integration_test_user"

        resp1 = client.post("/chat", json={
            "user_id": user_id,
            "message": "what is a squat?",
        })
        assert resp1.status_code == 200
        assert resp1.json()["intent"] in ["chat", "search"]

        resp2 = client.post("/chat", json={
            "user_id": user_id,
            "message": "what should I pay attention to when squatting?",
        })
        assert resp2.status_code == 200
        assert len(resp2.json()["reply"]) > 0

        resp3 = client.get(f"/chat/{user_id}/history")
        assert resp3.status_code == 200
        history = resp3.json()["history"]
        assert len(history) >= 2

        resp4 = client.delete(f"/chat/{user_id}/history")
        assert resp4.status_code == 200

        resp5 = client.get(f"/chat/{user_id}/history")
        assert resp5.json()["history"] == []

    def test_intent_routing_diet(self):
        """Verify diet intent routing."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "减脂期间应该吃什么?",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "diet"

    def test_intent_routing_motion(self):
        """Verify motion intent routing."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "分析一下我的深蹲姿势",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "motion"

    def test_intent_routing_mcp(self):
        """Verify MCP intent routing."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "怎么做番茄炒蛋?",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "mcp"

    def test_unlisted_recipe_still_routes_to_mcp(self):
        """Unlisted recipes should still route to the MCP path."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "糖醋排骨怎么做",
        })
        data = resp.json()
        assert resp.status_code == 200
        assert data["intent"] == "mcp"
        assert len(data["reply"]) > 0

    def test_intent_routing_search(self):
        """Verify search intent routing."""
        resp = client.post("/chat", json={
            "user_id": "test_user",
            "message": "搜索一下最新的健身资讯",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "search"

    def test_health_endpoint(self):
        """Health check."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
