from __future__ import annotations

import base64
import inspect
import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from agent.graph.workflow import app as langgraph_app
from agent.tools.backend_client import BackendClient
from agent.tools.conversation_store import ConversationStateStore

logger = logging.getLogger(__name__)

TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")
TOSS_API_BASE = "https://api.tosspayments.com/v1"

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_CHANNEL_PUBLIC_ID = os.getenv("KAKAO_CHANNEL_PUBLIC_ID", "")

STATE_STORE = ConversationStateStore()

server = FastAPI()


def _toss_auth_header() -> str:
    encoded = base64.b64encode(f"{TOSS_SECRET_KEY}:".encode()).decode()
    return f"Basic {encoded}"


def _verify_toss_signature(request: Request) -> bool:
    if os.getenv("TOSS_SKIP_SIGNATURE", "false").lower() == "true":
        return True

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth.removeprefix("Basic ")).decode()
        return decoded.rstrip(":") == TOSS_SECRET_KEY
    except Exception:
        return False


async def _fetch_toss_payment(payment_key: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{TOSS_API_BASE}/payments/{payment_key}",
            headers={"Authorization": _toss_auth_header()},
        )
        try:
            payload = resp.json()
        except Exception:
            payload = {"status_code": resp.status_code, "message": "Invalid JSON from Toss"}
        if resp.status_code >= 400:
            logger.warning("Toss payment lookup returned %s: %s", resp.status_code, payload)
        return payload


async def _send_kakao_payment_confirmed(plusfriend_user_key: str, name: str, reserve_date: str, reserve_time: str) -> None:
    if not KAKAO_REST_API_KEY or not KAKAO_CHANNEL_PUBLIC_ID or not plusfriend_user_key:
        return

    message_text = (
        f"✅ 결제가 확인되었습니다!\n"
        f"{name}님의 예약이 확정되었어요.\n"
        f"📅 {reserve_date} {reserve_time}"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://kapi.kakao.com/v1/api/talk/channels/{KAKAO_CHANNEL_PUBLIC_ID}/messages",
            headers={
                "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "uuid": plusfriend_user_key,
                "template_object": json.dumps(
                    {
                        "object_type": "text",
                        "text": message_text,
                        "link": {},
                    }
                ),
            },
        )


def _kakao_response(text: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


class KakaoRequest(BaseModel):
    userRequest: dict[str, Any]
    flow: dict[str, Any] = Field(default_factory=dict)


async def _handle_image(image_url: str, plusfriend_user_key: str) -> str:
    if not image_url or not plusfriend_user_key:
        return "이미지 정보가 올바르지 않습니다."

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()

        result = BackendClient.upload_booking_image(
            image_data=img_resp.content,
            plusfriend_user_key=plusfriend_user_key,
        )
        if result.get("success"):
            return "이미지가 예약에 첨부되었습니다 📎"
        return "이미지 업로드에 실패했습니다. 다시 시도해주세요."
    except Exception:
        logger.exception("Image handling failed")
        return "이미지 처리 중 오류가 발생했습니다. 다시 시도해주세요."


async def _update_langgraph_payment_state(thread_id: str, booking_status: str = "payment_confirmed") -> bool:
    values = {
        "booking_status": booking_status,
        "next_action": "notify_success",
        "pending_intent": None,
        "pending_missing_fields": [],
        "pending_followup_question": None,
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if hasattr(langgraph_app, "aupdate_state"):
            result = langgraph_app.aupdate_state(config=config, values=values)
            if inspect.isawaitable(result):
                await result
            return True

        if hasattr(langgraph_app, "update_state"):
            result = langgraph_app.update_state(config=config, values=values)
            if inspect.isawaitable(result):
                await result
            return True
    except Exception:
        logger.exception("Failed to update LangGraph state for thread_id=%s", thread_id)
        return False

    logger.warning("LangGraph app does not expose update_state/aupdate_state")
    return False


@server.post("/chat")
async def chat(req: KakaoRequest):
    user_info = req.userRequest.get("user", {})
    utterance = req.userRequest.get("utterance", "")
    plusfriend_user_key = user_info.get("properties", {}).get("plusfriendUserKey", "")
    thread_id = user_info.get("id") or plusfriend_user_key or "default"

    if req.flow.get("trigger", {}).get("type") == "IMAGE_UPLOAD":
        response_text = await _handle_image(
            image_url=utterance,
            plusfriend_user_key=plusfriend_user_key,
        )
        return _kakao_response(response_text)

    persisted_state = STATE_STORE.load(thread_id)
    graph_input: dict[str, Any] = {
        "user_input": utterance,
        "kakao_user_id": user_info.get("id"),
        "plusfriend_user_key": plusfriend_user_key,
    }
    if persisted_state:
        graph_input = {**persisted_state, **graph_input}
        graph_input["user_input"] = utterance
        graph_input["kakao_user_id"] = user_info.get("id")
        graph_input["plusfriend_user_key"] = plusfriend_user_key

        # 이전 대화가 완료된 상태면 슬롯을 초기화해 새 대화 오염 방지
        _TERMINAL_STATUSES = {"payment_confirmed", "cancelled", "updated", "rejected"}
        if persisted_state.get("booking_status") in _TERMINAL_STATUSES:
            graph_input["slots"] = None
            graph_input["missing_fields"] = []
            graph_input["intent"] = None
            graph_input["booking_status"] = "N/A"
            graph_input["is_bookable"] = False
            graph_input["next_action"] = None
            graph_input["pending_intent"] = None
            graph_input["pending_missing_fields"] = []
            graph_input["pending_followup_question"] = None

    result = await langgraph_app.ainvoke(
        graph_input,
        config={"configurable": {"thread_id": thread_id}},
    )
    STATE_STORE.save(thread_id, {**graph_input, **result})
    response_text = result.get("response_draft", "죄송합니다, 응답을 생성하지 못했습니다.")
    return _kakao_response(response_text)


@server.post("/toss/webhook")
async def toss_webhook(request: Request):
    if not _verify_toss_signature(request):
        raise HTTPException(status_code=401, detail="Invalid signature")

    body = await request.json()
    payment_key = body.get("paymentKey")
    order_id = body.get("orderId", "")
    amount = body.get("amount")
    status = body.get("status")

    if not payment_key:
        raise HTTPException(status_code=400, detail="Missing paymentKey")
    if status != "DONE":
        return {"result": "ignored", "status": status}
    if not order_id.startswith("booking_"):
        raise HTTPException(status_code=400, detail="Invalid orderId format")

    try:
        booking_id = int(order_id.removeprefix("booking_"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    payment_info = await _fetch_toss_payment(payment_key)
    if payment_info.get("status") != "DONE":
        raise HTTPException(status_code=400, detail="Payment not confirmed by Toss")

    try:
        toss_amount = int(payment_info.get("totalAmount"))
        webhook_amount = int(amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid amount")

    if toss_amount != webhook_amount:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    result = BackendClient.update_payment(
        booking_id,
        {
            "amount": webhook_amount,
            "payment_status": "PAID",
            "payment_key": payment_key,
        },
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail="Failed to update payment status")

    booking = BackendClient.get_reservation(booking_id)
    if not booking.get("success"):
        logger.warning("Updated payment but could not load reservation %s: %s", booking_id, booking)
        return {"result": "ok", "state_updated": False}

    data = booking.get("data") or {}
    if isinstance(data.get("data"), dict):
        data = data["data"]

    kakao_user_id = data.get("kakao_user_id")
    if kakao_user_id:
        state_updated = await _update_langgraph_payment_state(kakao_user_id)
        STATE_STORE.update(
            kakao_user_id,
            {
                "booking_status": "payment_confirmed",
                "next_action": "notify_success",
                "pending_intent": None,
                "pending_missing_fields": [],
                "pending_followup_question": None,
            },
        )
        logger.info("LangGraph payment state update for %s: %s", kakao_user_id, state_updated)
    else:
        logger.warning("Reservation %s has no kakao_user_id; skipping LangGraph update", booking_id)

    # 운영 환경에서 채널 푸시를 붙일 수 있도록 남겨둠.
    # await _send_kakao_payment_confirmed(
    #     plusfriend_user_key=data.get("plusfriend_user_key", ""),
    #     name=data.get("name", "고객"),
    #     reserve_date=data.get("reserve_date", ""),
    #     reserve_time=data.get("reserve_time", ""),
    # )

    return {"result": "ok", "state_updated": bool(kakao_user_id)}
