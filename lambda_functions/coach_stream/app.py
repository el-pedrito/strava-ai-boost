"""Coach streaming endpoint — Starlette app behind Lambda Web Adapter.

Emits AG-UI protocol events over Server-Sent Events (SSE) so the frontend can
render the coach response token-by-token.

AG-UI event sequence per run:
    RUN_STARTED
      TEXT_MESSAGE_START
      TEXT_MESSAGE_CONTENT  (xN, one per model delta)
      TEXT_MESSAGE_END
    RUN_FINISHED            (or RUN_ERROR on failure)

Starlette (not FastAPI) is used deliberately: it and uvicorn are pure-Python,
so they vendor into the Lambda asset without Docker bundling (project convention).

This handler is purely additive: the buffered /coach/ask API Gateway handler
(coach_ask_api.py) remains the fallback and is untouched.
"""

import json
import os
import uuid
from collections.abc import AsyncIterator

import boto3
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from shared.coach_context import (
    COACH_CONVERSATION_PROMPT,
    build_user_context,
    retrieve_memory_observations,
    write_chat_to_memory,
)
from shared.logger import get_logger

logger = get_logger("coach-stream")

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")
MAX_QUESTION_LEN = 500


def _sse(event_type: str, data: dict) -> str:
    """Serialize an AG-UI event as a single SSE frame."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_message(question: str, user_id: str) -> str:
    """Assemble the user message with athlete context + past observations."""
    context_parts = build_user_context(user_id)
    memory_context = retrieve_memory_observations(user_id)
    if memory_context:
        context_parts.append(f"Observations passées: {memory_context}")
    if context_parts:
        return f"[Contexte: {' | '.join(context_parts)}]\n\n{question}"
    return question


async def _event_stream(question: str, user_id: str, message_id: str) -> AsyncIterator[str]:
    """Produce the AG-UI SSE event stream for a coach answer."""
    run_id = uuid.uuid4().hex
    yield _sse("RUN_STARTED", {"runId": run_id})

    answer_parts: list[str] = []
    try:
        user_message = _build_message(question, user_id)

        bedrock = boto3.client("bedrock-runtime", region_name=REGION)
        response = bedrock.converse_stream(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            system=[{"text": COACH_CONVERSATION_PROMPT}],
            inferenceConfig={"maxTokens": 800, "temperature": 0.7},
        )

        yield _sse("TEXT_MESSAGE_START", {"messageId": message_id, "role": "assistant"})

        for chunk in response.get("stream", []):
            delta = chunk.get("contentBlockDelta", {}).get("delta", {}).get("text")
            if delta:
                answer_parts.append(delta)
                yield _sse(
                    "TEXT_MESSAGE_CONTENT", {"messageId": message_id, "delta": delta}
                )

        yield _sse("TEXT_MESSAGE_END", {"messageId": message_id})

        answer = "".join(answer_parts)
        if answer:
            write_chat_to_memory(user_id, question, answer)

        yield _sse("RUN_FINISHED", {"runId": run_id})
    except Exception as e:
        logger.error(f"Coach stream error: {e}")
        yield _sse("RUN_ERROR", {"runId": run_id, "message": "Failed to stream coach response"})


async def ask_stream(request: Request) -> StreamingResponse | JSONResponse:
    """Stream a coach answer as AG-UI SSE events."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    question = (body.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "Missing 'question' field"}, status_code=400)
    if len(question) > MAX_QUESTION_LEN:
        return JSONResponse(
            {"error": f"Question too long (max {MAX_QUESTION_LEN} chars)"}, status_code=400
        )

    user_id = body.get("user_id") or DEFAULT_USER_ID
    message_id = uuid.uuid4().hex
    logger.info(f"Coach stream ask: '{question[:50]}'")

    return StreamingResponse(
        _event_stream(question, user_id, message_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def health(_request: Request) -> JSONResponse:
    """Liveness probe for the Lambda Web Adapter readiness check."""
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/coach/ask/stream", ask_stream, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ]
)
