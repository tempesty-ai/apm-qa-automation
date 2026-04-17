# APM QA Automation

APM 수집 서버의 데이터 수집 흐름을 검증하는 자동화 테스트 환경입니다.  
실제 JSPD 에이전트의 수집 스펙(1초/3초 주기, 5가지 수집 타입)을 Mock으로 구현하여  
Docker 환경에서 누구나 동일하게 재현 가능한 QA 환경을 구축했습니다.

---

## 배경

APM QA 업무에서 수집 서버를 테스트하려면 실제 에이전트 환경이 필요했지만,  
환경 세팅에 시간이 걸리고 테스트 결과 재현이 어려운 문제가 있었습니다.  
이를 해결하기 위해 실제 수집 스펙 기반의 Mock 환경을 코드로 정의했습니다.

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

## 기술 스택

| 구분 | 기술 |
|---|---|
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

```bash
docker compose up -d --build
```

컨테이너 3개가 기동됩니다:
- `apm-postgres` : PostgreSQL DB (port 5432)
- `apm-collector` : Mock 수집 서버 (port 8080)
- `apm-agent-tomcat` : Mock JSPD 에이전트

### 기동 확인

```bash
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

```bash
pip install pytest httpx
pytest tests/api/ -v
```

**테스트 케이스 15개**

| 클래스 | 케이스 | 검증 포인트 |
|---|---|---|
| TestHealth | 1 | 서버 정상 기동 확인 |
| TestAgentRegister | 3 | 신규 등록, 중복 등록(upsert), 목록 조회 |
| TestMetrics | 3 | 스냅샷 수집, 최신값 조회, 미등록 에이전트 404 |
| TestTransactions | 3 | 정상/에러 트랜잭션 수집, 액티브 배치 수집 |
| TestSqlStats | 2 | 단건 수집, 배치 수집 |
| TestAlarms | 3 | CRITICAL/WARNING 알람 수집 및 조회 |

### 부하 테스트 (Locust)

```bash
pip install locust

# 웹 대시보드 모드
locust -f tests/load/locustfile.py --host http://localhost:8080
# → http://localhost:8089 접속
```

**부하 테스트 시나리오**
- 에이전트 10개 동시 접속
- metrics/snapshot (3초 주기), transactions (1초 주기) 실제 비율로 부하 생성
- 실패율 0%, 평균 응답시간 47ms 확인

### 원클릭 전체 실행

```bash
bash scripts/run_test.sh
```

---

## DB 스키마

| 테이블 | 설명 | 수집 주기 |
|---|---|---|
| `agents` | 에이전트 등록 정보 | 기동 시 1회 |
| `metrics_snapshot` | CPU/Memory/JVM/Pool 스냅샷 | 3초 |
| `transactions` | 완료 트랜잭션 | 1초 |
| `active_transactions` | 액티브 트랜잭션 스냅샷 | 1초 |
| `sql_stats` | SQL 수행 정보 | 3초 |
| `alarms` | 임계치 초과 알람 | 3초 |

---

## CI/CD

GitHub Actions를 통해 PR 생성 시 자동으로 실행됩니다.

```
push / PR → docker compose up → health check → pytest → locust 30s
```

결과 리포트는 Actions Artifacts에서 CSV로 다운로드 가능합니다.

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
│   │   └── test_collector.py    # pytest API 테스트 (15케이스)
│   └── load/
│       └── locustfile.py        # Locust 부하 테스트
└── scripts/
    └── run_test.sh              # 원클릭 실행 스크립트
```
