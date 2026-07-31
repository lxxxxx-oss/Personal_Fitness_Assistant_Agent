"""Conversation-management API integration tests."""

from fastapi.testclient import TestClient

import app.main as main_module
from app.memory.conversation_store import ConversationStore


def test_conversation_lifecycle_is_user_scoped(monkeypatch, tmp_path):
    store = ConversationStore(str(tmp_path / "conversations.db"))
    monkeypatch.setattr(main_module, "_conversation_store", store)
    main_module._sessions.clear()
    client = TestClient(main_module.app)

    created = client.post(
        "/chat/sidebar-user/conversations",
        json={"title": "训练计划"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]
    assert created.json()["title"] == "训练计划"
    assert created.json()["message_count"] == 0

    listing = client.get("/chat/sidebar-user/conversations")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["conversations"]] == [
        conversation_id
    ]

    history = client.get(
        f"/chat/sidebar-user/conversations/{conversation_id}"
    )
    assert history.status_code == 200
    assert history.json()["history"] == []

    renamed = client.patch(
        f"/chat/sidebar-user/conversations/{conversation_id}",
        json={"title": "增肌训练计划"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "增肌训练计划"

    assert client.get(
        f"/chat/another-user/conversations/{conversation_id}"
    ).status_code == 404
    assert client.patch(
        f"/chat/another-user/conversations/{conversation_id}",
        json={"title": "越权修改"},
    ).status_code == 404
    assert client.delete(
        f"/chat/another-user/conversations/{conversation_id}"
    ).status_code == 404

    deleted = client.delete(
        f"/chat/sidebar-user/conversations/{conversation_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert client.get(
        f"/chat/sidebar-user/conversations/{conversation_id}"
    ).status_code == 404
    assert client.get(
        "/chat/sidebar-user/conversations"
    ).json()["conversations"] == []


def test_conversation_requests_validate_titles_and_list_limit(monkeypatch, tmp_path):
    store = ConversationStore(str(tmp_path / "conversations.db"))
    monkeypatch.setattr(main_module, "_conversation_store", store)
    client = TestClient(main_module.app)

    assert client.patch(
        "/chat/u1/conversations/missing",
        json={"title": ""},
    ).status_code == 422
    response = client.get("/chat/u1/conversations?limit=not-a-number")
    assert response.status_code == 422
