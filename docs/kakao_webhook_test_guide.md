# Kakao Webhook Test Guide

이 문서는 `agent`의 `/chat` 엔드포인트를 로컬에서 직접 테스트하는 방법을 정리한 안내서입니다.

## `/chat`이 의미하는 것

- `/chat`은 **카카오톡 화면**이 아니라, **카카오가 우리 서버로 보내는 webhook 주소**입니다.
- 즉, 실제 흐름은 아래처럼 이해하면 됩니다.

```text
카카오톡 사용자 입력
→ 카카오 webhook
→ 우리 FastAPI 서버의 /chat
→ LangGraph agent 실행
→ 카카오 응답 형식(JSON) 반환
→ 카카오톡 화면에 응답 표시
```

- 그래서 `/chat`을 `curl`로 호출하면, 카카오가 보낸 것과 비슷한 요청을 **로컬에서 흉내내는 것**입니다.

## 준비

1. `backend` 서버 실행
2. `agent` 서버 실행
3. `BACKEND_BASE_URL=http://localhost:8080` 확인

예시:

```bash
conda activate agent
cd /home/sallysooo/Desktop/Nailgent/agent
export BACKEND_BASE_URL='http://localhost:8080'
uvicorn server:server --reload
```

## 1. 기본 채팅 테스트

### 샘플 payload

파일:
- [samples/kakao_chat_booking.json](./samples/kakao_chat_booking.json)

### curl

```bash
curl -X POST 'http://127.0.0.1:8000/chat' \
  -H 'Content-Type: application/json' \
  --data @docs/samples/kakao_chat_booking.json
```

### 기대 결과

- `version: "2.0"`
- `template.outputs[0].simpleText.text` 안에 예약 안내가 들어옵니다.

## 2. 후속 질문 테스트

이 payload는 이전 대화 상태가 저장되어 있다는 가정 하에 사용합니다.

### 샘플 payload

파일:
- [samples/kakao_chat_followup.json](./samples/kakao_chat_followup.json)

### curl

```bash
curl -X POST 'http://127.0.0.1:8000/chat' \
  -H 'Content-Type: application/json' \
  --data @docs/samples/kakao_chat_followup.json
```

## 3. 이미지 업로드 테스트

카카오 이미지 업로드 트리거를 흉내 내는 예시입니다.

### 샘플 payload

파일:
- [samples/kakao_image_upload.json](./samples/kakao_image_upload.json)

### curl

```bash
curl -X POST 'http://127.0.0.1:8000/chat' \
  -H 'Content-Type: application/json' \
  --data @docs/samples/kakao_image_upload.json
```

## 4. payload 필드 설명

최소한 아래 필드가 있으면 됩니다.

- `userRequest.user.id`: 카카오 사용자 ID처럼 쓰는 값
- `userRequest.user.properties.plusfriendUserKey`: 플러스친구 키
- `userRequest.utterance`: 사용자가 입력한 메시지
- `flow.trigger.type`: `IMAGE_UPLOAD`일 때 이미지 분기로 처리

## 5. 실제 카카오 연동 시 주의할 점

- 로컬 `127.0.0.1`은 카카오가 접근할 수 없습니다.
- 실제 카카오 테스트에는 `ngrok` 또는 배포 URL이 필요합니다.
- `/chat` 응답은 카카오가 기대하는 JSON 형식이어야 합니다.
