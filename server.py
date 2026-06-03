import base64
import json
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from agent.graph.workflow import app as langgraph_app
from agent.tools.backend_client import BackendClient

TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")
TOSS_API_BASE = "https://api.tosspayments.com/v1"

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_CHANNEL_PUBLIC_ID = os.getenv("KAKAO_CHANNEL_PUBLIC_ID", "")


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


async def _fetch_toss_payment(payment_key: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TOSS_API_BASE}/payments/{payment_key}",
            headers={"Authorization": _toss_auth_header()},
        )
        return resp.json()


async def _send_kakao_payment_confirmed(plusfriend_user_key: str, name: str, reserve_date: str, reserve_time: str) -> None:
    if not KAKAO_REST_API_KEY or not KAKAO_CHANNEL_PUBLIC_ID or not plusfriend_user_key:
        return

    message_text = (
        f"✅ 결제가 확인되었습니다!\n"
        f"{name}님의 예약이 확정되었어요.\n"
        f"📅 {reserve_date} {reserve_time}"
    )

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://kapi.kakao.com/v1/api/talk/channels/{KAKAO_CHANNEL_PUBLIC_ID}/messages",
            headers={
                "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "uuid": plusfriend_user_key,
                "template_object": json.dumps({
                    "object_type": "text",
                    "text": message_text,
                    "link": {},
                }),
            },
        )

server = FastAPI()


class KakaoRequest(BaseModel):
    userRequest: dict


@server.post("/chat")
async def chat(req: KakaoRequest):
    user_info = req.userRequest.get("user", {})
    utterance = req.userRequest.get("utterance", "")
    thread_id = user_info.get("id", "default")

    result = await langgraph_app.ainvoke(
        {
            "user_input": utterance,
            "kakao_user_id": user_info.get("id"),
            "plusfriend_user_key": user_info.get("properties", {}).get("plusfriendUserKey"),
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    response_text = result.get("response_draft", "죄송합니다, 응답을 생성하지 못했습니다.")

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": response_text}}
            ]
        }
    }


@server.post("/toss/webhook")
async def toss_webhook(request: Request):
    # 1. 서명 검증
    if not _verify_toss_signature(request):
        raise HTTPException(status_code=401, detail="Invalid signature")

    body = await request.json()
    payment_key = body.get("paymentKey")
    order_id = body.get("orderId", "")
    amount = body.get("amount")
    status = body.get("status")

    # 결제 완료(DONE)만 처리, 나머지는 무시하고 200 반환
    if status != "DONE":
        return {"result": "ignored", "status": status}

    # 2. 토스 API로 결제 상태 재확인 (Check_Payment)
    payment_info = await _fetch_toss_payment(payment_key)
    if payment_info.get("status") != "DONE":
        raise HTTPException(status_code=400, detail="Payment not confirmed by Toss")
    if payment_info.get("totalAmount") != amount:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    # 3. 백엔드 결제 상태 업데이트 (Update_Payment)
    if not order_id.startswith("booking_"):
        raise HTTPException(status_code=400, detail="Invalid orderId format")

    try:
        booking_id = int(order_id.removeprefix("booking_"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    result = BackendClient.update_payment(booking_id, {
        "amount": amount,
        "payment_status": "PAID",
        "payment_key": payment_key,
    })

    if not result.get("success"):
        raise HTTPException(status_code=502, detail="Failed to update payment status")

    # 4. 예약 정보 조회 (kakao_user_id 추출용)
    booking = BackendClient.get_reservation(booking_id)
    if booking.get("success"):
        data = booking.get("data") or {}
        if isinstance(data.get("data"), dict):
            data = data["data"]

        # 5. LangGraph 상태 갱신 (해당 유저 thread의 booking_status를 payment_confirmed로 업데이트)
        kakao_user_id = data.get("kakao_user_id")
        if kakao_user_id:
            await langgraph_app.aupdate_state(
                config={"configurable": {"thread_id": kakao_user_id}},
                values={"booking_status": "payment_confirmed"},
            )

        # 6. 카카오 채널 푸시 (비즈니스 채널 인증 후 활성화)
        # await _send_kakao_payment_confirmed(
        #     plusfriend_user_key=data.get("plusfriend_user_key", ""),
        #     name=data.get("name", "고객"),
        #     reserve_date=data.get("reserve_date", ""),
        #     reserve_time=data.get("reserve_time", ""),
        # )

    return {"result": "ok"}
