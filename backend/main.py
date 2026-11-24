import json
import os
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import litellm
from litellm import completion
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from database import init_db, SessionLocal, Message


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

load_dotenv()

LLM_KEYS = [
    key.strip()
    for key in os.getenv("LLM_API_KEYS", "").split(",")
    if key.strip()
]

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "gemini/gemini-3.5-flash-lite"
)

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

ENABLE_FAILURE_SIMULATION = (
    os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
)


# ============================================================
# LITELLM CACHE
# ============================================================

litellm.enable_cache(type="local")

CACHE_ENABLED = True


# ============================================================
# APP STARTUP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Lyftr AI Chatbot",
    version="1.0.0",
    lifespan=lifespan
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = None

    @field_validator("session_id", "message")
    @classmethod
    def validate_not_blank(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("must not be empty")

        return value


# ============================================================
# FAILURE SIMULATION
# ============================================================

def parse_simulated_failures(header_value: str | None):
    failures = {}

    if not ENABLE_FAILURE_SIMULATION or not header_value:
        return failures

    for item in header_value.split(","):
        item = item.strip()

        if "=" not in item:
            continue

        key_id, status = item.split("=", 1)

        key_id = key_id.strip()
        status = status.strip()

        if status in {"429", "500", "502", "503"}:
            failures[key_id] = int(status)

    return failures


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health_check():

    # Assignment requires health only when key pool exists.
    if len(LLM_KEYS) < 2:
        raise HTTPException(
            status_code=503,
            detail="insufficient API keys configured"
        )

    return {
        "status": "ok",
        "keys_configured": len(LLM_KEYS),
        "cache_enabled": CACHE_ENABLED
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    x_simulate_failure: str | None = Header(
        default=None,
        alias="X-Simulate-Failure"
    )
):

    # --------------------------------------------------------
    # Load previous conversation
    # --------------------------------------------------------

    previous_messages = (
        db.query(Message)
        .filter(Message.session_id == request.session_id)
        .order_by(Message.id.asc())
        .all()
    )

    # --------------------------------------------------------
    # Build complete LLM message list
    # --------------------------------------------------------

    llm_messages = [
        {
            "role": "system",
            "content": request.system_prompt
            or DEFAULT_SYSTEM_PROMPT
        }
    ]

    for stored_message in previous_messages:
        llm_messages.append({
            "role": stored_message.role,
            "content": stored_message.content
        })

    llm_messages.append({
        "role": "user",
        "content": request.message
    })

    # --------------------------------------------------------
    # Failure simulation
    # --------------------------------------------------------

    simulated_failures = parse_simulated_failures(
        x_simulate_failure
    )

    # --------------------------------------------------------
    # Start latency timer
    # --------------------------------------------------------

    start_time = time.perf_counter()

    response = None
    successful_key_id = None
    fallback_attempts = 0
    cache_hit = False

    # --------------------------------------------------------
    # Try configured keys
    # --------------------------------------------------------

    for index, api_key in enumerate(LLM_KEYS):

        key_id = f"key_{index + 1}"

        # Simulate provider/key failure when requested
        simulated_status = (
            simulated_failures.get(key_id)
            or simulated_failures.get("*")
        )

        if simulated_status:
            fallback_attempts += 1
            continue

        try:

            response = completion(
                model=LLM_MODEL,
                messages=llm_messages,
                api_key=api_key,
                timeout=30,
                caching=True
            )

            # ------------------------------------------------
            # Detect LiteLLM cache hit
            # ------------------------------------------------

            hidden_params = getattr(
                response,
                "_hidden_params",
                {}
            ) or {}

            cache_hit = bool(
                hidden_params.get("cache_hit")
            )

            if cache_hit:
                successful_key_id = None
                fallback_attempts = 0
            else:
                successful_key_id = key_id
                fallback_attempts = index

            break

        except Exception:
            fallback_attempts += 1
            continue

    # --------------------------------------------------------
    # Every key failed
    # --------------------------------------------------------

    if response is None:
        raise HTTPException(
            status_code=503,
            detail="all providers unavailable"
        )

    # --------------------------------------------------------
    # Latency
    # --------------------------------------------------------

    latency_ms = int(
        (time.perf_counter() - start_time) * 1000
    )

    # --------------------------------------------------------
    # Extract response
    # --------------------------------------------------------

    reply = response.choices[0].message.content

    input_tokens = (
        response.usage.prompt_tokens
        if response.usage
        else 0
    )

    output_tokens = (
        response.usage.completion_tokens
        if response.usage
        else 0
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {
        "resolution_source": (
            "LLM_CACHE"
            if cache_hit
            else "LIVE_INFERENCE"
        ),
        "model": LLM_MODEL,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "key_id": (
            None
            if cache_hit
            else successful_key_id
        ),
        "fallback_attempts": (
            0
            if cache_hit
            else fallback_attempts
        )
    }

    # --------------------------------------------------------
    # Save only successful requests
    # --------------------------------------------------------

    user_message = Message(
        session_id=request.session_id,
        role="user",
        content=request.message,
        metadata_json=None,
        created_at=datetime.now(
            timezone.utc
        ).isoformat()
    )

    assistant_message = Message(
        session_id=request.session_id,
        role="assistant",
        content=reply,
        metadata_json=json.dumps(metadata),
        created_at=datetime.now(
            timezone.utc
        ).isoformat()
    )

    db.add(user_message)
    db.add(assistant_message)
    db.commit()

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "session_id": request.session_id,
        "reply": reply,
        "metadata": metadata
    }


# ============================================================
# SESSION HISTORY
# ============================================================

@app.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db)
):

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.asc())
        .all()
    )

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="session not found"
        )

    history = []

    for message in messages:

        item = {
            "role": message.role,
            "content": message.content
        }

        if (
            message.role == "assistant"
            and message.metadata_json
        ):
            item["metadata"] = json.loads(
                message.metadata_json
            )

        history.append(item)

    return {
        "session_id": session_id,
        "messages": history
    }