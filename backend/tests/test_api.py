import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


# Make backend imports available when pytest runs from backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Ensure the app sees two configured keys during tests.
os.environ["LLM_API_KEYS"] = "test-key-1,test-key-2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

import main
from database import Base, Message


# ============================================================
# MOCK LITELLM RESPONSE
# ============================================================

def fake_completion(*args, **kwargs):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Mock AI response"
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5
        ),
        _hidden_params={}
    )


# Replace real LiteLLM calls with our mock.
main.completion = fake_completion


client = TestClient(main.app)


# ============================================================
# RESET DATABASE BEFORE EACH TEST
# ============================================================

@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=main.SessionLocal.kw["bind"])
    Base.metadata.create_all(bind=main.SessionLocal.kw["bind"])

    yield


# ============================================================
# HEALTH
# ============================================================

def test_health():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert data["keys_configured"] >= 2
    assert data["cache_enabled"] is True


# ============================================================
# VALIDATION
# ============================================================

def test_empty_message_returns_422():
    response = client.post(
        "/chat",
        json={
            "session_id": "test-session",
            "message": "   "
        }
    )

    assert response.status_code == 422


def test_empty_session_id_returns_422():
    response = client.post(
        "/chat",
        json={
            "session_id": "",
            "message": "Hello"
        }
    )

    assert response.status_code == 422


def test_message_over_4000_characters_returns_422():
    response = client.post(
        "/chat",
        json={
            "session_id": "test-session",
            "message": "a" * 4001
        }
    )

    assert response.status_code == 422


# ============================================================
# NORMAL CHAT
# ============================================================

def test_chat_success():
    response = client.post(
        "/chat",
        json={
            "session_id": "chat-test",
            "message": "Hello"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["session_id"] == "chat-test"
    assert data["reply"] == "Mock AI response"

    metadata = data["metadata"]

    assert metadata["resolution_source"] == "LIVE_INFERENCE"
    assert metadata["model"] == main.LLM_MODEL
    assert metadata["input_tokens"] == 10
    assert metadata["output_tokens"] == 5
    assert metadata["key_id"] == "key_1"
    assert metadata["fallback_attempts"] == 0


# ============================================================
# SESSION HISTORY
# ============================================================

def test_session_history():
    client.post(
        "/chat",
        json={
            "session_id": "history-test",
            "message": "Hello"
        }
    )

    response = client.get(
        "/sessions/history-test/messages"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["session_id"] == "history-test"
    assert len(data["messages"]) == 2

    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello"

    assert data["messages"][1]["role"] == "assistant"
    assert (
        data["messages"][1]["content"]
        == "Mock AI response"
    )


def test_unknown_session_returns_404():
    response = client.get(
        "/sessions/does-not-exist/messages"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "session not found"
    }


# ============================================================
# FAILURE SIMULATION
# ============================================================

def test_key_1_429_falls_back_to_key_2():
    response = client.post(
        "/chat",
        headers={
            "X-Simulate-Failure": "key_1=429"
        },
        json={
            "session_id": "fallback-test",
            "message": "Hello"
        }
    )

    assert response.status_code == 200

    metadata = response.json()["metadata"]

    assert metadata["key_id"] == "key_2"
    assert metadata["fallback_attempts"] == 1


def test_key_1_500_falls_back_to_key_2():
    response = client.post(
        "/chat",
        headers={
            "X-Simulate-Failure": "key_1=500"
        },
        json={
            "session_id": "fallback-500-test",
            "message": "Hello"
        }
    )

    assert response.status_code == 200

    metadata = response.json()["metadata"]

    assert metadata["key_id"] == "key_2"
    assert metadata["fallback_attempts"] == 1


def test_all_keys_fail_returns_503():
    response = client.post(
        "/chat",
        headers={
            "X-Simulate-Failure": "*=429"
        },
        json={
            "session_id": "all-fail-test",
            "message": "This should fail"
        }
    )

    assert response.status_code == 503

    assert response.json() == {
        "detail": "all providers unavailable"
    }


# ============================================================
# FAILED REQUEST MUST NOT ENTER HISTORY
# ============================================================

def test_failed_request_not_saved():
    response = client.post(
        "/chat",
        headers={
            "X-Simulate-Failure": "*=429"
        },
        json={
            "session_id": "failed-history-test",
            "message": "Do not save me"
        }
    )

    assert response.status_code == 503

    history_response = client.get(
        "/sessions/failed-history-test/messages"
    )

    assert history_response.status_code == 404