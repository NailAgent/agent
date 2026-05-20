from fastapi import FastAPI
from pydantic import BaseModel
from agent.graph.workflow import app as langgraph_app

server = FastAPI()


class KakaoRequest(BaseModel):
    userRequest: dict


@server.post("/chat")
async def chat(req: KakaoRequest):
    utterance = req.userRequest.get("utterance", "")
    thread_id = req.userRequest.get("user", {}).get("id", "default")

    result = await langgraph_app.ainvoke(
        {"user_input": utterance},
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
