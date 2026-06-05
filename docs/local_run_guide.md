# Local Run Guide

이 문서는 `agent`와 `backend`를 로컬에서 함께 띄우고, 종료하는 방법을 초보자 기준으로 정리한 메모입니다.

## 0. 먼저 기억할 것

- `backend`와 `agent`는 **서로 다른 레포**입니다.
- `agent`는 대화/오케스트레이션을 담당하고, `backend`는 DB와 업무 데이터를 담당합니다.
- `backend`는 먼저 실행되어 있어야 `agent`가 정상적으로 API를 호출할 수 있습니다.

## 1. backend 실행 순서

### 1-1. MySQL 컨테이너 실행

`backend` 폴더에서 실행합니다.

```bash
cd /home/sallysooo/Desktop/Nailgent/backend
sudo docker compose up -d mysql
```

확인하고 싶으면:

```bash
sudo docker compose ps
```

### 1-2. backend 환경변수 준비

최소한 아래 값이 필요합니다.

- `DB_URL`
- `DB_USERNAME`
- `DB_PASSWORD`

예시:

```bash
export DB_URL='jdbc:mysql://localhost:3306/nailagent?serverTimezone=Asia/Seoul&characterEncoding=UTF-8'
export DB_USERNAME='nailagent'
export DB_PASSWORD='1234'
```

### 1-3. Spring Boot 서버 실행

`backend` 폴더에서 실행합니다.

```bash
cd /home/sallysooo/Desktop/Nailgent/backend
./gradlew bootRun
```

기본 서버 주소:

- `http://localhost:8080`

자주 보는 주소:

- Swagger: `http://localhost:8080/swagger-ui.html`
- OpenAPI JSON: `http://localhost:8080/api-docs`

## 2. agent 실행 순서

### 2-1. conda 환경 활성화

```bash
conda activate agent
```

### 2-2. backend 주소 지정

`agent`가 backend를 바라보도록 설정합니다.

```bash
export BACKEND_BASE_URL='http://localhost:8080'
```

### 2-3. FastAPI 서버 실행

`agent` 폴더에서 실행합니다.

```bash
cd /home/sallysooo/Desktop/Nailgent/agent
uvicorn server:server --reload
```

기본 서버 주소:

- `http://127.0.0.1:8000`

자주 보는 주소:

- FastAPI docs: `http://127.0.0.1:8000/docs`

## 3. 실행 후 확인 방법

### backend 확인

```bash
curl http://localhost:8080/swagger-ui.html
```

또는 브라우저에서 Swagger 페이지를 열어도 됩니다.

### agent 확인

```bash
curl http://127.0.0.1:8000/docs
```

## 4. 종료 방법

### 4-1. agent 서버 종료

`uvicorn`을 띄운 터미널에서:

```bash
Ctrl + C
```

### 4-2. backend 서버 종료

`./gradlew bootRun`을 띄운 터미널에서:

```bash
Ctrl + C
```

### 4-3. MySQL 컨테이너 정지

`backend` 폴더에서:

```bash
sudo docker compose stop mysql
```

### 4-4. MySQL 컨테이너와 네트워크 정리

`backend` 폴더에서:

```bash
sudo docker compose down
```

### 4-5. DB 데이터까지 완전히 삭제하고 싶을 때만

```bash
sudo docker compose down -v
```

이 명령은 DB 데이터도 지우므로, 정말 필요할 때만 사용합니다.

## 5. 추천 실행 순서 요약

1. `sudo docker compose up -d mysql`
2. `./gradlew bootRun`
3. `conda activate agent`
4. `export BACKEND_BASE_URL='http://localhost:8080'`
5. `uvicorn server:server --reload`
6. 필요하면 `/docs` 와 `/swagger-ui.html` 로 확인

## 6. 참고

- `backend`는 Docker만 `sudo`가 필요한 경우가 많습니다.
- `agent`의 `uvicorn` 실행은 보통 `sudo`가 필요하지 않습니다.
- 로컬 테스트용으로는 서버를 계속 켜둬도 되지만, 작업이 끝나면 `Ctrl + C`로 종료하는 것이 깔끔합니다.
