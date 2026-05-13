# `apm-qa-automation` — APM 수집 서버 QA 자동화 환경

> APM 수집 서버의 데이터 수집 흐름을 검증하는 자동화 테스트 환경.
> 핵심은 "테스트 케이스를 많이 만드는 것"이 아니라, **"실제 수집 스펙을 Mock으로 정의해 누구나 동일하게 재현 가능한 QA 환경을 코드로 박제하는 것"** 입니다.

---

## 한 줄 가치

> **"수집 흐름이 정말 맞게 동작하는가?"** 라는 질문을 매 PR마다 자동으로 답하는 저장소.
> 환경 세팅 1분, 15개 API 케이스 + 30초 부하 테스트가 GitHub Actions에서 자동 회귀됩니다.

---

## 배경

APM QA 업무에서 수집 서버를 테스트하려면 실제 에이전트 환경이 필요했지만,
환경 세팅에 시간이 걸리고 테스트 결과 재현이 어려운 문제가 있었습니다.
이를 해결하기 위해 실제 수집 스펙 기반의 **Mock 환경을 코드로 정의**했습니다.

---

## 발견한 크리티컬 리스크

| # | 리스크 | 의미 |
| --- | --- | --- |
| R1 | **재현 불가능한 환경** | 실제 JSPD 에이전트 환경은 세팅이 길고 결과 재현이 어려워 회귀 검증이 사실상 매번 다름 → 결함 재현 불가 |
| R2 | **수집 흐름 검증 공백** | 1초 / 3초 주기, 5종 수집 타입(완료 트랜잭션, 액티브 트랜잭션, 메트릭 스냅샷, SQL, 알람)이 모두 정상 도달·저장되는지 자동 검증 부재 |
| R3 | **부하 한계 미파악** | 에이전트가 10개로 늘었을 때 수집 서버가 버티는지 데이터로 모름 → 운영 사고가 일어나야 알게 됨 |

→ 그래서 실제 수집 스펙(1초/3초 주기, 5가지 수집 타입)을 Mock으로 구현하여 Docker 환경에서 **누구나 동일하게 재현 가능한 QA 환경**을 구축했습니다.

---

## 아키텍처

```
[Mock JSPD Agent]
  Tomcat / JEUS 에이전트 모방
  - 1초 주기: 완료 트랜잭션, 액티브 트랜잭션
  - 3초 주기: CPU/Memory/JVM, Pool, SQL, 알람
        │
        ▼ HTTP POST
[Mock DataGather - FastAPI]
  수집 서버 역할
  - 에이전트 등록 및 관리
  - 수집 데이터 수신 및 저장
  - QA 검증용 조회 API 제공
        │
        ▼
[PostgreSQL]
  metrics_snapshot / transactions / active_transactions
  sql_stats / alarms / agents
```

---

## 테스트 설계

### Docker Compose 원클릭 환경

PostgreSQL + Mock 수집 서버(FastAPI) + Mock JSPD 에이전트가 한 번에 기동됩니다.

### API 테스트 (pytest, 15 케이스)

| 클래스 | 케이스 수 | 검증 포인트 |
| --- | --- | --- |
| TestHealth | 1 | 서버 정상 기동 확인 |
| TestAgentRegister | 3 | 신규 등록, 중복 등록(upsert), 목록 조회 |
| TestMetrics | 3 | 스냅샷 수집, 최신값 조회, 미등록 에이전트 404 |
| TestTransactions | 3 | 정상/에러 트랜잭션 수집, 액티브 배치 수집 |
| TestSqlStats | 2 | 단건 수집, 배치 수집 |
| TestAlarms | 3 | CRITICAL/WARNING 알람 수집 및 조회 |

### 부하 테스트 (Locust)

- 에이전트 10개 동시 접속
- `metrics/snapshot` (3초 주기), `transactions` (1초 주기)를 **실제 비율**로 부하 생성
- 결과: **실패율 0%**, **평균 응답시간 47ms**

### CI/CD (GitHub Actions)

```
push / PR → docker compose up → health check → pytest → locust 30s
```

결과 리포트는 Actions Artifacts에서 CSV로 다운로드 가능합니다.

---

## 자동화의 비즈니스 임팩트

| 임팩트 | 어떻게 발생하는가 |
| --- | --- |
| **회귀 검증 환경의 표준화** | 누가 어디서 돌려도 동일 결과 → 결함 재현 / 공유 / PR 리뷰가 즉시 가능 |
| **변경의 안전성 보증** | 수집 스펙 변경 PR마다 자동으로 15 케이스 + 부하 30초가 돈다 → 운영 배포 전에 회귀 차단 |
| **성능 회귀 가시화** | 평균 응답시간이 47ms에서 변하면 즉시 보임 → 성능 저하를 코드 머지 단계에서 잡음 |
| **온보딩 비용 감소** | `docker compose up -d --build` 한 줄로 신규 인력 환경 구축 완료 → QA 합류 시간 단축 |

---

## 기술 스택

| 구분 | 기술 |
| --- | --- |
| Mock 수집 서버 | Python, FastAPI, asyncpg |
| Mock 에이전트 | Python, httpx |
| DB | PostgreSQL 15 |
| API 테스트 | pytest, httpx |
| 부하 테스트 | Locust |
| 환경 구성 | Docker, Docker Compose |
| CI | GitHub Actions |

---

## 실행 방법

### 사전 요구사항

- Docker Desktop
- Python 3.11+

### 환경 기동 (원클릭)

```
docker compose up -d --build
```

컨테이너 3개가 기동됩니다:

- `apm-postgres` : PostgreSQL DB (port 5432)
- `apm-collector` : Mock 수집 서버 (port 8080)
- `apm-agent-tomcat` : Mock JSPD 에이전트

### 기동 확인

```
# 헬스체크
curl http://localhost:8080/health

# 에이전트 등록 확인
curl http://localhost:8080/api/agents

# 최신 메트릭 확인
curl http://localhost:8080/api/metrics/latest/tomcat-agent-01

# 알람 확인
curl http://localhost:8080/api/alarms/tomcat-agent-01
```

### API 문서

```
http://localhost:8080/docs
```

---

## 테스트 실행

### API 테스트 (pytest)

```
pip install pytest httpx
pytest tests/api/ -v
```

### 부하 테스트 (Locust)

```
pip install locust

# 웹 대시보드 모드
locust -f tests/load/locustfile.py --host http://localhost:8080
# → http://localhost:8089 접속
```

### 원클릭 전체 실행

```
bash scripts/run_test.sh
```

---

## DB 스키마

| 테이블 | 설명 | 수집 주기 |
| --- | --- | --- |
| `agents` | 에이전트 등록 정보 | 기동 시 1회 |
| `metrics_snapshot` | CPU/Memory/JVM/Pool 스냅샷 | 3초 |
| `transactions` | 완료 트랜잭션 | 1초 |
| `active_transactions` | 액티브 트랜잭션 스냅샷 | 1초 |
| `sql_stats` | SQL 수행 정보 | 3초 |
| `alarms` | 임계치 초과 알람 | 3초 |

---

## 프로젝트 구조

```
apm-qa-automation/
├── .github/workflows/ci.yml     # GitHub Actions CI
├── docker-compose.yml           # 전체 환경 정의
├── collector/
│   ├── server/
│   │   ├── main.py              # Mock DataGather API (FastAPI)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── db/
│       └── init.sql             # PostgreSQL 스키마
├── agents/
│   └── tomcat/
│       ├── agent.py             # Mock JSPD 에이전트
│       └── Dockerfile
├── tests/
│   ├── api/
│   │   └── test_collector.py    # pytest API 테스트 (15 케이스)
│   └── load/
│       └── locustfile.py        # Locust 부하 테스트
└── scripts/
    └── run_test.sh              # 원클릭 실행 스크립트
```
