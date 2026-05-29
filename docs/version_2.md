
## 14. Change / Cancel / Payment Flow

이제 v2부터는 예약만 처리하는 것이 아니라, 아래 4가지 intent를 분기해서 다룹니다.

### 14.1 Routing Rule
`intake_agent.py`가 intent를 먼저 분류합니다.

- `booking` -> `booking_node`
- `change` -> `change_node`
- `cancel` -> `cancel_node`
- `payment` -> `payment_node`
- `greeting / inquiry / unknown` -> `response_node`

### 14.2 각 노드가 하는 일

#### booking_node
- 샵 정보 조회
- 해당 날짜의 스케줄 조회
- 영업시간/휴무일/시간 충돌 검사
- 예약 가능하면 백엔드 예약 생성 요청
- 고객에게 입금 안내 응답 생성

#### change_node
- name 없으면 즉시 성함 요청
- 이름/날짜/시간/시술명으로 기존 예약 탐색
- 새 일정이 확인되면 `PATCH /api/v1/bookings/{id}` 로 실제 변경

#### cancel_node
- name 없으면 즉시 성함 요청
- 이름 기반으로 예약 탐색
- 예약 발견 시 `DELETE /api/v1/bookings/{id}` 로 실제 취소

#### payment_node
- name 없으면 즉시 성함 요청
- `GET /api/v1/bookings` 조회 후 이름 필터 → 최근 예약의 `payment_status` 확인
- PAID: "✅ 결제 확인", 미결제: "⚠️ 아직 미확인" 고정 메시지 반환
- Toss 웹훅 연동 시 결제 상태 자동 갱신 예정

---

- 예약은 정책 검증 후 자동 진행
- 변경/취소는 백엔드 API 호출로 자동 처리 (name 없으면 성함 먼저 요청)
- 결제 확인은 결제 상태 조회 후 고정 메시지 반환 (Toss 웹훅 연동 시 자동화 예정)

---

## 15. Google Calendar 연동 설계

우리가 원하는 것은 다음 두 가지입니다.

1. 예약 가능한 시간을 구글 캘린더에서 계산하기
2. 예약이 확정되면 구글 캘린더에도 이벤트를 생성하기

### 15.1 권장 구조
**agent가 Google Calendar를 직접 호출하지 말고, backend가 호출하는 구조**가 가장 좋습니다.

왜냐하면:
- Google 인증 정보는 민감합니다
- refresh token 또는 service account 키를 agent에 두면 관리가 어려워집니다
- 캘린더 동기화는 예약 시스템의 핵심 저장소와 가까운 backend가 맡는 편이 자연스럽습니다

즉 흐름은 이렇게 갑니다.

1. 고객 메시지 수신
2. agent가 intent/slot 추출
3. agent가 backend의 schedule API 호출
4. backend가 Google Calendar의 free/busy 정보를 조회
5. backend가 빈 슬롯을 계산해서 agent에게 반환
6. agent가 예약 가능 여부를 고객에게 안내
7. 예약 확정 시 backend가 Google Calendar에 이벤트 생성

### 15.2 Google Calendar에서 주로 쓰는 API

#### [freeBusy.query](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query?hl=ko)
예약 가능 시간 조회에 가장 중요합니다.

- 일정 구간의 busy 시간을 조회
- 해당 구간에서 비어 있는 시간대를 계산할 수 있음

실제로는 `timeMin`, `timeMax`, `timeZone`, `items`를 넣어 조회합니다.

#### [events.insert](https://developers.google.com/workspace/calendar/api/guides/overview?hl=ko)
예약이 확정되면 캘린더 이벤트를 만듭니다.

- 제목: 고객명 / 시술명 / 전화번호 등
- 시작/종료 시간: 예약 시간
- 설명: 예약 메모, 입금 정보, 참고 사항

### 15.3 인증 방식 선택

#### 일반 Gmail 1개 계정만 사용할 때
보통 **[OAuth 2.0 웹 서버 방식](https://developers.google.com/identity/protocols/oauth2/web-server?hl=ko)**이 가장 무난합니다.

- Google Cloud Project 생성
- Calendar API 활성화
- OAuth 동의 화면 설정
- 사용자 계정으로 최초 1회 승인
- backend가 refresh token을 저장
- 이후에는 backend가 access token을 갱신하면서 API 호출


### 15.4 지금 프로젝트에 맞는 현실적인 선택
- Google 계정 1개를 만들어 캘린더 1개를 예약 전용으로 사용
- backend가 Google OAuth를 담당
- agent는 `GET /api/v1/bookings/schedule`와 `POST /api/v1/bookings`만 호출

이렇게 가는 것이 가장 단순합니다.

### 15.5 왜 agent가 직접 Google Calendar를 안 만지는가

agent가 직접 Google API를 호출하면:
- 인증 토큰 관리가 어려워지고
- 재시도 / 오류 처리 / 저장 일관성을 따로 설계해야 하며
- 나중에 backend DB와 캘린더 데이터가 어긋날 수 있습니다

그래서 **source of truth는 backend**, **calendar는 backend가 동기화**, **agent는 대화와 판단**을 맡는 구조가 맞습니다.

---

## 16. Beginner Checklist

1. Google Cloud에서 Calendar API 활성화
2. backend에 OAuth 인증 설정
3. backend에서 freeBusy 기반 schedule API 구현
4. backend에서 예약 생성 시 events.insert 추가
5. agent는 backend schedule API만 호출하도록 유지
6. agent의 booking/change/cancel/payment 분기 테스트
7. 실제 캘린더에서 예약 생성/삭제/변경이 보이는지 확인


