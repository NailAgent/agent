from fastapi import FastAPI
from pydantic import BaseModel
from agent.graph.workflow import app as langgraph_app

server = FastAPI()


class KakaoRequest(BaseModel):
    userRequest: dict


@server.post("/chat")
async def chat(req: KakaoRequest):
    utterance = req.userRequest.get("utterance", "")

    initial_state = {
        "user_input": utterance,
        "response_draft": "",
        "intent": "",
        "slots": None,
        "missing_fields": [],
        "is_bookable": False,
        "booking_status": "N/A",
        "next_action": "",
        "policy_check_results": {},
        "history": [],
    }

    result = await langgraph_app.ainvoke(initial_state)
    response_text = result.get("response_draft", "죄송합니다, 응답을 생성하지 못했습니다.")

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": response_text}}
            ]
        }
    }
