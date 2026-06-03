# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered nail salon reservation chatbot. Processes Kakao Talk messages through a LangGraph state machine, extracts booking intent/slots via GPT-4o, and manages reservations through a backend API.

## Environment Variables

Required in `.env`:
```
OPENAI_API_KEY=...
BACKEND_BASE_URL=https://nailagent.shop   # defaults to http://localhost:8080
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=reservia
USE_MOCK_BACKEND=true   # set to true to skip real backend calls
```

## Commands

```bash
# Run server
uvicorn main:server --reload

# Run tests (always use mock backend)
USE_MOCK_BACKEND=true pytest tests/test_agent_full_suite.py -v

# Run a single test
USE_MOCK_BACKEND=true pytest tests/test_agent_full_suite.py -k "test_name" -v
```

## Architecture

LangGraph `StateGraph` with `InMemorySaver` checkpointer. Nodes: `intake → booking | change | cancel | payment | response`.

- **State**: `ReservationState` TypedDict in `agent/graph/state.py`
- **Routing**: `route_after_intake()` in `agent/graph/router.py` — reads `intent` and `missing_fields`
- **Intake**: GPT-4o via `intake_agent.py`; falls back to keyword regex in `intake_agent_deterministic.py`
- **Backend**: `BackendClient` in `agent/tools/backend_client.py` — falls back to mock JSON on any HTTP error
- **Mock data**: `agent/data/mock_backend/*.json`

## Key Constraints

- Business hours: 10:00–22:00, closed Mondays (`CLOSED_DAYS = [0]`)
- Service codes: `GEL_BASIC` (30min), `GEL_NAIL` (60min), `PEDICURE` (60min); `off_removal=true` adds 30min
- Relative date parsing (`오늘`, `내일`, `모레`) is hardcoded in `nodes.py` — be careful with timezone/midnight edge cases
- `FastAPI` and `uvicorn` are used in `main.py` but **not listed in `requirements.txt`** — install separately if needed
- `ReservationState` is a `TypedDict`, not a class — state is a plain dict at runtime
- Kakao webhook expects: `POST /chat` with `{"userRequest": {"user": {"id": "..."}, "utterance": "..."}}`

## Testing Notes

- Tests use `run_graph(message, thread_id="test")` helper to invoke the workflow
- `USE_MOCK_BACKEND=true` must be set; otherwise tests may attempt real backend calls
- Mock responses are loaded from `agent/data/mock_backend/`

## Git Rules
- Do NOT run any git commands
- Do NOT commit, push, or modify git history
- Only suggest code changes, never apply git operations