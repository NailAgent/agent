# Reservia

<p align="center">
  <img src="https://github.com/user-attachments/assets/051e66c9-dfa9-4447-81c0-3ad9055032b2" alt="Reservia Logo" width="448" height="280" />
</p>

<p align="center">
  <b>고객의 비정형 예약 메시지를 구조화하여 예약 문의, 변경, 취소, 결제 확인, 일정 등록까지 자동 처리하는<br/>네일샵 사장님을 위한 AI 예약 응대 매니저</b>
</p>

<p align="center">
  <b>Team Nailgent</b> · 🏆 2026 Low-Code AI Challenge Hackathon 3rd place
</p>

### Team Nailgent

| Role | Name | GitHub |
|---|---|---|
| AI / Agent | 김미지 | [@miji0](https://github.com/miji0) |
| AI / Agent | 김지수 | [@sallysooo](https://github.com/sallysooo) |
| Backend / Infra | 남민서 | [@minseo0313](https://github.com/minseo0313) |
| Frontend / Design | 정교은 | [@kyooonnnggg](https://github.com/kyooonnnggg) |

---


## 1. Project Overview

<p align="center">
  <img width="2560" height="1440" src="https://github.com/user-attachments/assets/93c5d156-3f46-4752-8e7d-b6f57654c21f" alt="Introducing Reservia" />
</p>


**Reservia**는 1인 네일샵과 소규모 예약 기반 업종의 사장님들을 위한 AI 예약 자동화 서비스입니다. 고객은 카카오톡이나 웹 채팅에서 평소처럼 자유롭게 문의하고, 시스템은 해당 메시지에서 예약에 필요한 정보를 추출하여 예약 가능 여부 확인, 누락 정보 재질문, 예약금 결제 확인, Google Calendar 등록, 예약 변경 및 취소까지 자동으로 처리합니다.

기존 예약 서비스는 정해진 입력 양식에 맞춰 날짜와 시간을 선택하는 방식에 가깝습니다. 하지만 실제 네일샵 예약 문의는 다음처럼 훨씬 자유롭고 복잡합니다.

```text
내일 오후 3시에 젤 제거하고 젤네일 가능해요?
첫방문이고 이름은 김지수예요.
```

Reservia는 이런 자연어 메시지를 읽고 다음과 같은 구조화된 정보로 변환합니다.

```json
{
  "intent": "booking",
  "slots": {
    "name": "김지수",
    "reserve_date": "2026-05-30",
    "reserve_time": "15:00",
    "service_code": "GEL_NAIL",
    "off_removal": true,
    "past_visit": false
  },
  "missing_fields": ["phone_num"],
  "next_action": "ask_missing_field"
}
```

그리고 필요한 정보가 부족하면 고객에게 자동으로 다시 질문합니다.

```text
안녕하세요 김지수 고객님 😊
예약을 도와드리기 위해 전화번호도 함께 알려주시겠어요?
```

---

## 2. Problem Statement

소규모 네일샵 사장님은 시술 중에도 계속 들어오는 예약 문의를 직접 확인해야 합니다. 고객 문의는 카카오톡, 네이버 톡톡, 인스타그램 DM 등 여러 채널로 흩어져 있고, 문의 형식도 모두 다릅니다.

반복적으로 발생하는 문제는 다음과 같습니다.

| 문제 | 설명 |
|---|---|
| 비정형 문의 | 고객이 정해진 양식 없이 자유롭게 예약 요청을 보냅니다. |
| 반복 확인 | 이름, 전화번호, 희망 시간, 시술 옵션, 제거 여부 등을 매번 다시 확인해야 합니다. |
| 예약 가능 여부 확인 | 사장님이 직접 캘린더를 보고 가능한 시간대를 확인해야 합니다. |
| 변경/취소 처리 | 기존 예약을 찾아서 변경 가능 여부와 정책을 확인해야 합니다. |
| 선입금 확인 | 예약금 입금 여부를 확인한 뒤 최종 예약 확정을 해야 합니다. |
| 정보 관리 어려움 | 가격표, 운영시간, 예약 정책이 바뀌면 고객 응대 내용도 함께 수정해야 합니다. |

Reservia는 이러한 수작업을 AI와 자동화 워크플로우로 연결하여 사장님의 예약 응대 부담을 줄이는 것을 목표로 합니다.

---

## 3. Target Users

### Main Target

- 1인 네일샵 사장님
- 소규모 네일샵 직원
- 예약 문의와 옵션 선택을 직접 관리하는 뷰티샵 운영자

### Future Expansion

Reservia의 구조는 네일샵뿐 아니라 다음과 같은 예약 기반 업종으로 확장할 수 있습니다.

- 케이크샵
- 꽃집
- 공방 클래스
- 에스테틱 / 속눈썹 / 왁싱샵
- 원데이 클래스
- 렌탈 스튜디오
- 기타 맞춤형 예약이 필요한 소상공인 업종

---

## 4. Key Features

### 4.1 비정형 자연어 예약 문의 처리

고객이 정해진 양식 없이 자유롭게 작성한 메시지를 분석합니다. 시스템은 고객 메시지에서 예약 의도와 필요한 slot을 추출하고, 누락된 정보가 있으면 자동으로 재질문합니다.

예시:

```text
고객: 내일 3시에 젤 제거하고 젤네일 가능해요?
시스템: 가능 여부를 확인해드릴게요. 성함과 전화번호도 함께 알려주시겠어요?
```

### 4.2 예약 가능 시간 확인 및 대체 시간 제안

고객이 요청한 시간이 이미 예약되어 있거나 영업시간과 맞지 않는 경우, 예약 데이터와 Policy Engine을 통해 가능한 대체 시간대를 제안합니다.

예시:

```text
요청하신 오후 3시는 이미 예약이 있어요.
대신 오후 4시, 5시 30분, 7시 예약이 가능합니다.
원하시는 시간대를 선택해주세요 😊
```

### 4.3 예약금 결제 확인 후 최종 예약 확정

예약은 바로 확정되지 않고, 예약금 결제 확인 이후 최종 확정됩니다. Toss Payments 웹훅 연동을 통해 자동 처리됩니다.

결제 흐름:

**경로 A — 고객이 "결제 완료" 메시지 전송 시 (주 경로)**

1. 예약 생성 → `booking_id`, `order_id`(`booking_{id}_{timestamp}`) state 저장 → 결제 링크와 함께 "30분 이내 미결제 시 자동 취소" 안내 전송
2. 고객이 Toss 결제 완료 후 "결제 완료" 메시지 전송
3. Toss API 직접 조회 (`GET /v1/payments/orders/{order_id}`)
4. `status: DONE`이면 결제 확정 응답
5. Toss 조회 결과가 없거나 미결제면 백엔드 `payment_status` 조회로 fallback
   - `PAID` → 결제 확정 응답
   - `CANCELLED` (30분 내 미결제로 자동 취소됨) → 취소 안내 + "예약 문의"로 재예약 유도
   - 그 외(`PENDING`) → "아직 결제가 확인되지 않았습니다" 안내

**경로 B — Toss successUrl 리다이렉트 시 (백엔드 처리)**

1. 고객이 Toss 결제 완료 → successUrl로 리다이렉트 (`paymentKey`, `orderId`, `amount` 포함)
2. 백엔드 successUrl 핸들러: `POST /api/v1/payments/confirm` 호출
3. Toss 최종 승인 (`POST /v1/payments/confirm`) → `status: DONE`
4. 백엔드 결제 상태 업데이트 (`PATCH /api/v1/payments/{id}`)

**경로 C — Toss 웹훅 수신 시 (보조 경로)**

1. Toss가 `POST /toss/webhook`으로 결제 완료 이벤트 전송
2. 서명 검증 (TOSS_SECRET_KEY 기반 Basic auth)
3. Toss API 재조회로 결제 상태 확인 (`status: DONE`, 금액 검증)
4. 백엔드 결제 상태 업데이트 (`PATCH /api/v1/payments/{id}`)
5. LangGraph 해당 유저 thread 상태 갱신 (`booking_status: payment_confirmed`)
6. 카카오 채널 푸시 발송 *(비즈니스 채널 인증 후 활성화 예정)*

### 4.4 예약 변경 및 취소 / 환불 자동 처리

고객이 예약 변경이나 취소를 요청하면 기존 예약을 조회하고, 정책에 따라 변경 가능 여부를 판단합니다. 가능한 경우 예약 정보를 수정하고, 불가능하거나 애매한 경우 사장님 검토로 넘깁니다.

취소 시 결제 상태에 따라 자동 분기됩니다.

- **결제 완료(PAID)**: `POST /api/v1/payments/{id}/refund` 호출 → 백엔드가 Toss 환불 처리 및 예약 삭제
- **미결제**: `DELETE /api/v1/bookings/{id}` 호출 → 예약 삭제
- 환불 완료 시 고객에게 "예약금은 3~5일 내 환불됩니다. (결제사에 따라 상이)" 안내

### 4.5 기타 문의 응대

운영시간, 가격, 위치, 예약금, 시술 옵션 등 일반 문의는 `GET /api/v1/shopinfo`로 가져온 샵 정보를 바탕으로 LLM이 1차 답변을 시도합니다. 사장님이 등록한 정책과 가격 정보로 답변할 수 있는 경우 즉시 응답하고, 샵 정보에 없는 내용은 SSE를 통해 사장님에게 알림을 전송한 뒤 대기 안내 메시지를 반환합니다.

### 4.6 관리자 대시보드

사장님은 웹 대시보드에서 다음 정보를 확인하고 관리할 수 있습니다.

- 샵 정보 관리
- 고객 목록 관리
- 예약 목록 관리
- 일정 관리
- 예약 상태 확인
- 결제 상태 확인
- 고객이 업로드한 네일 디자인 이미지 확인

---

## 5. System Architecture

Reservia는 고객 메시지를 단순히 LLM에 전달해 답변하는 챗봇이 아닙니다. 고객 입력을 구조화하고, 예약 업무에 필요한 여러 시스템을 연결하는 **AI workflow automation system**입니다.

전체 구조는 다음과 같습니다.

```mermaid
flowchart LR
    A[Customer Message<br/>KakaoTalk] --> B[Kakao Webhook]
    B --> C[FastAPI]
    C --> D[LangGraph]
    D --> E[Intake Agent<br/>GPT-4o]
    E --> F[Router]

    F --> G[Greeting]
    F --> H[Inquiry]
    F --> I[Booking Agent]
    F --> J[Cancel Agent]
    F --> K[Change Agent]
    F --> L[Payment Agent]

    I --> M[Reservation API]
    I --> N[Policy Engine]
    I --> O[Toss Payments API]
    I --> P[Google Calendar<br/>구현 예정]
    J --> M
    K --> M

    G --> Q[Response]
    H --> Q
    I --> Q
    J --> Q
    K --> Q
    L --> Q

    Q --> R[Customer Reply]
    Q --> S[Owner Dashboard]
```

---

## 6. Agent Workflow

<p align="center">
  <img width="2560" height="1440" src="https://github.com/user-attachments/assets/8947b65b-3d02-4d09-a1c5-c1eb5c8b0c1a" alt="Reservia Agent Workflow" />
</p>

LangGraph는 Reservia의 핵심 자동화 흐름을 연결하는 orchestration layer입니다. 고객 메시지가 카카오 웹훅을 통해 FastAPI 서버로 들어오면, LangGraph workflow가 Intake Agent와 Router를 거쳐 목적에 맞는 노드로 연결합니다.

### 6.1 Workflow Summary

| Step | Component | Role |
|---|---|---|
| 1 | Kakao Webhook | 고객 메시지 수신 |
| 2 | FastAPI + LangGraph | 메시지 파싱 및 워크플로우 실행 |
| 3 | Intake Agent (GPT-4o) | 의도 분류, slot 추출, 기존 고객 DB 보완 |
| 4 | Router | Greeting, Inquiry, Booking, Cancel, Change, Payment로 분기 |
| 5 | Inquiry Agent | 가격, 운영시간, 정책 등 기타 문의 응대 → 처리 불가 시 SSE로 사장님 알림 |
| 6 | Booking Agent | 신규 예약 등록 및 가능 여부 확인 + 결제 링크 생성 |
| 7 | Policy Engine | DB 기반 영업시간·휴무일·시술 소요시간 검증, 예약 가능 여부 판단 |
| 8 | Payments Flow | 예약 생성 시 결제 링크 발송 → successUrl 리다이렉트 → Toss confirm → 결제 확정 → 백엔드 DB 업데이트 |
| 9 | Google Calendar | 확정 예약 일정 등록 *(구현 예정)* |
| 10 | Cancel / Change Agent | 기존 예약 조회 후 취소 또는 변경 처리 |
| 11 | Response | 고객에게 최종 응답 반환 |

### 6.2 Shared State

LangGraph workflow에서는 고객 메시지를 처리하기 위해 다음과 같은 상태값을 유지합니다.

| Field | Description |
|---|---|
| `kakao_user_id` | 카카오 사용자 식별자 |
| `user_input` | 고객의 원본 메시지 |
| `intent` | 예약, 문의, 변경, 취소 등 고객 의도 |
| `slots` | 이름, 전화번호, 날짜, 시간, 시술 옵션 등 추출된 정보 |
| `missing_fields` | 예약 처리를 위해 추가로 필요한 정보 |
| `is_bookable` | 현재 요청이 예약 가능한 상태인지 여부 |
| `booking_status` | 예약 상태 |
| `booking_id` | 예약 생성 후 저장되는 예약 ID (결제 확인에 사용) |
| `order_id` | Toss 결제 조회용 주문번호 (`booking_{id}_{timestamp}`, 결제 확인에 사용) |
| `policy_check_results` | 정책 검증 결과 및 조회된 예약 정보 |
| `next_action` | 다음에 수행해야 할 작업 |
| `response_draft` | 고객에게 보낼 응답 초안 |

---

## 7. Core Agents

### 7.1 Intake Agent

Intake Agent는 모든 고객 메시지가 처음 도착하는 진입점입니다.

주요 역할:

- 고객 의도 분류
- 예약 관련 slot 추출
- 누락 정보 감지
- 기존 고객 여부 확인
- 다음 workflow 분기 결정

예시:

```json
{
  "intent": "booking",
  "slots": {
    "name": "김지수",
    "reserve_date": "2026-05-30",
    "reserve_time": "15:00",
    "service_code": "GEL_NAIL",
    "off_removal": true,
    "past_visit": false
  },
  "missing_fields": ["phone_num"],
  "next_action": "ask_missing_field"
}
```

### 7.2 Greeting

처음 방문한 고객 또는 신규 대화에 대해 환영 메시지를 제공합니다.

주요 역할:

- 신규 고객 안내
- 기본 예약 절차 안내
- 필요한 정보 입력 유도

### 7.3 Inquiry Agent

예약 외의 일반 문의를 처리합니다. `GET /api/v1/shopinfo`로 샵 정보를 조회한 뒤 LLM이 답변 가능 여부를 판단합니다.

주요 역할:

- "기타", "문의요", "궁금한거 있어요" 등 트리거 입력 감지(LLM 판단) → 실제 질문 유도
- 샵 정보 기반 LLM 1차 답변 시도, 가능 시 즉시 응답
- 샵 정보에 없는 내용은 `notify_owner()` SSE 알림 전송 후 대기 안내 (human-in-the-loop)

### 7.4 Booking Agent

신규 예약을 담당합니다.

주요 역할:

- 예약 slot 검증
- 시술 옵션 확인
- 샵 운영시간 확인
- 예약 가능 시간 조회
- 예약 draft 생성
- 예약금 결제 대기 상태 처리
- 결제 확인 후 예약 확정
- Google Calendar 등록

### 7.5 Cancel Agent

고객의 예약 취소 요청을 처리합니다.

주요 역할:

- kakao_user_id 기반 기존 고객 DB 조회로 이름 자동 보완
- 이름으로 미래 예약 중 가장 최근에 생성된 1건 자동 선택
- 예약 확인 메시지 후 고객 응답(맞아요/아니요)으로 분기
- 맞아요 → 결제 완료(PAID)면 환불 처리, 미결제면 예약 삭제 / 아니요 → 날짜/시간 재요청

### 7.6 Change Agent

고객의 예약 변경 요청을 처리합니다.

주요 역할:

- kakao_user_id 기반 기존 고객 DB 조회로 이름 자동 보완
- 이름으로 미래 예약 중 가장 최근에 생성된 1건 자동 선택
- 예약 찾으면 새 날짜/시간만 요청 (이름/전화번호 재요청 없음)
- 새 시간대 가능 여부 확인 후 예약 정보 수정

### 7.7 Exception Handler

정상적인 자동 처리 흐름으로 해결하기 어려운 요청을 담당합니다.

예외 상황 예시:

- 고객 요청이 너무 모호한 경우
- 예약 정책과 충돌하는 경우
- 결제는 되었지만 예약 정보가 불완전한 경우
- 기존 예약을 찾을 수 없는 경우
- backend error가 발생한 경우
- 사람이 직접 판단해야 하는 이미지/디자인 요청인 경우

이 경우 시스템은 무리하게 자동 확정하지 않고 사장님 검토로 넘깁니다.

---

## 8. Main User Scenarios

### Scenario 1. 신규 예약

```text
고객: 내일 오후 3시에 젤 제거하고 젤네일 가능해요? 첫방문이고 이름은 김지수예요.
```

시스템 처리:

1. `booking` intent로 분류
2. 이름, 날짜, 시간, 시술 옵션, 제거 여부 추출
3. 전화번호 누락 감지
4. 고객에게 전화번호 재질문
5. 예약 가능 시간 확인
6. 예약금 결제 안내
7. 결제 확인 후 예약 확정
8. Google Calendar 등록

### Scenario 2. 예약 시간 불가 및 대체 시간 제안

```text
고객: 오늘 10시로 예약할게요.
```

시스템 처리:

1. 요청 시간대 확인
2. 이미 예약이 있거나 불가능한 시간인지 판단
3. 가능한 대체 시간대 조회
4. 고객에게 대체 시간 제안

### Scenario 3. 기타 문의

**Case A. 직접 질문**

```text
고객: 네일 가격이 궁금해요.
```

1. `inquiry` intent로 분류
2. `GET /api/v1/shopinfo`로 샵 정보 조회
3. LLM이 샵 정보 기반 답변 생성 시도
4. 정보가 없는 경우 SSE로 사장님 알림 전송 후 대기 안내

**Case B. 트리거 입력 후 실제 질문**

```text
고객: 기타  (또는 "문의요", "궁금한거 있어요" 등)
시스템: 궁금하신 점을 남겨주세요! 가격, 영업시간, 예약 정책 등 무엇이든 편하게 문의해 주세요😊
고객: 젤네일 가격이 얼마예요?
시스템: (샵 정보 기반 LLM 답변 또는 SSE 알림 후 대기 안내)
```

### Scenario 4. 예약 취소

```text
고객: 예약 취소하고 싶어요.
시스템: 정교은님의 최근 예약 정보입니다.
        📅 2026-06-15 11:00 / 💅 젤네일
        이 예약을 취소해드릴까요? (맞아요 / 아니요)
고객: 맞아요
시스템: 정교은님의 예약이 취소되었습니다. 😢
```

시스템 처리:

1. `cancel` intent로 분류
2. kakao_user_id로 고객 DB 조회 → 이름 자동 보완
3. 이름으로 미래 예약 중 가장 최근에 생성된 1건 자동 선택
4. 예약 정보 확인 메시지 출력
5. 맞아요 → 결제 완료(PAID)면 환불 처리, 미결제면 예약 삭제 / 아니요 → 날짜·시간 재요청

### Scenario 5. 예약 변경

```text
고객: 예약 변경하고 싶어요.
시스템: 정교은님의 예약을 찾았습니다.
        📅 2026-06-15 11:00 젤네일
        변경 희망 날짜와 시간을 알려주시면 바로 반영하겠습니다.
고객: 6월 20일 오후 2시로 바꿔주세요.
시스템: ✅ 예약이 변경되었습니다!

        📅 변경된 일정: 2026-06-20 14:00-15:30

        또 궁금하신 점이 있으면 편하게 말씀해 주세요 😊
```

시스템 처리:

1. `change` intent로 분류
2. kakao_user_id로 고객 DB 조회 → 이름 자동 보완
3. 이름으로 미래 예약 중 가장 최근에 생성된 1건 자동 선택
4. 새 날짜·시간만 요청 (이름·전화번호 재요청 없음)
5. 새 시간대 가능 여부 확인 후 예약 정보 수정

---

## 9. Frontend Dashboard

Reservia는 고객 응대 자동화뿐 아니라, 사장님이 예약과 샵 정보를 관리할 수 있는 dashboard를 제공합니다.

### 9.1 Shop Info Management

사장님은 다음 정보를 직접 등록하거나 수정할 수 있습니다.

- 운영시간
- 예약금
- 가게 위치
- 예약 양식
- 대표 가격
- 예약 멘트
- 정책 안내
- 가격표/안내문 이미지

Document Parsing을 통해 가격표 이미지를 업로드하면, 시스템이 텍스트 정보를 추출하여 고객 응대에 활용할 수 있습니다.

### 9.2 Customer Management

고객 탭에서는 고객 이름, 전화번호, 예약 이력, 노쇼 여부 등을 관리할 수 있습니다.

### 9.3 Reservation Management

예약 탭에서는 예약 목록과 예약 상태를 확인합니다.

관리 가능한 정보 예시:

- 고객명
- 시술명
- 예약 날짜 및 시간
- 예약금 상태
- 예약 상태
- 고객이 업로드한 네일 디자인 이미지

### 9.4 Schedule Management

일정 탭에서는 Google Calendar와 연동된 예약 일정을 확인할 수 있습니다. 확정된 예약은 캘린더에 자동 등록되어 사장님이 실시간으로 확인할 수 있습니다.

---

## 10. Backend & Integrations

Reservia는 다음 외부 시스템과 연동됩니다.

| Integration | Purpose |
|---|---|
| Kakao Webhook | 고객 메시지 수신 |
| OpenAI GPT-4o | 자연어 이해 및 slot 추출 |
| Customer DB | 고객 정보 및 기존 예약 조회 |
| Reservation API | 예약 생성, 변경, 취소 |
| Policy Engine | 영업시간, 예약 가능 여부, 예외 조건 판단 |
| Toss Payments API | 예약금 결제 확인 |
| Google Calendar API | 확정 예약 일정 등록 |
| Frontend Dashboard | 사장님용 관리 화면 제공 |

---

## 11. MVP Scope

### In Scope

- 카카오톡/웹 기반 고객 메시지 수신
- 자연어 의도 분류
- 예약 slot 추출
- 누락 정보 재질문
- 신규 예약 처리
- 예약 가능 시간 확인
- 대체 시간대 제안
- 예약금 결제 확인
- Google Calendar 등록
- 예약 변경/취소 처리
- 가격표/운영정보 기반 기타 문의 응대
- 사장님용 관리자 화면

### Out of Scope for Current MVP

- 복수 디자이너 최적 배정
- 고난도 네일 디자인 이미지 자동 판별
- 여러 지점 동시 운영
- 모든 업종에 대한 완전 일반화

---

## 12. Future Work

- 네일샵 외 예약 업종 확장
- 업종별 정책 템플릿 제공
- 고객 재방문/노쇼 이력 기반 예약 정책 고도화
- 가격표/안내문 자동 파싱 정확도 개선
- 고객 맞춤형 추천 응답 생성
- 복수 직원/디자이너 스케줄링 지원
- CRM 및 마케팅 자동화 연동

---

