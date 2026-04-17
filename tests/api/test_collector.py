"""
APM Collector API 테스트
실행: pytest tests/api/ -v --base-url=http://localhost:8080
"""
import pytest
import httpx
import time

BASE_URL   = "http://localhost:8080"
AGENT_ID   = "test-agent-pytest"
HEADERS    = {"Content-Type": "application/json"}


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=5) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def register_agent(client):
    r = client.post("/api/agents/register", json={
        "agent_id": AGENT_ID,
        "was_type": "tomcat",
        "host":     "pytest-host",
    })
    assert r.status_code == 201


# ── Health ──────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── Agent 등록 ───────────────────────────────────────────────

class TestAgentRegister:
    def test_register_new_agent(self, client):
        r = client.post("/api/agents/register", json={
            "agent_id": "new-agent-001",
            "was_type": "jeus",
            "host":     "jeus-host",
        })
        assert r.status_code == 201
        assert r.json()["agent_id"] == "new-agent-001"

    def test_register_duplicate_upsert(self, client):
        """중복 등록 시 upsert — 에러 없이 처리되어야 함"""
        for _ in range(3):
            r = client.post("/api/agents/register", json={
                "agent_id": AGENT_ID,
                "was_type": "tomcat",
                "host":     "pytest-host",
            })
            assert r.status_code == 201

    def test_agent_list_contains_registered(self, client):
        r = client.get("/api/agents")
        assert r.status_code == 200
        ids = [a["agent_id"] for a in r.json()]
        assert AGENT_ID in ids


# ── 메트릭 수집 ─────────────────────────────────────────────

class TestMetrics:
    PAYLOAD = {
        "agent_id":         AGENT_ID,
        "cpu_pct":          45.2,
        "mem_used_mb":      1024.0,
        "mem_total_mb":     4096.0,
        "jvm_cpu_pct":      30.1,
        "jvm_heap_used_mb": 512.0,
        "jvm_heap_max_mb":  2048.0,
        "thread_count":     80,
        "pool_active":      10,
        "pool_idle":        40,
        "pool_max":         50,
    }

    def test_snapshot_ingest(self, client):
        r = client.post("/api/metrics/snapshot", json=self.PAYLOAD)
        assert r.status_code == 201
        assert r.json()["result"] == "ok"

    def test_latest_metrics_returned(self, client):
        client.post("/api/metrics/snapshot", json=self.PAYLOAD)
        r = client.get(f"/api/metrics/latest/{AGENT_ID}")
        assert r.status_code == 200
        data = r.json()
        assert data["agent_id"] == AGENT_ID
        assert data["cpu_pct"] == 45.2

    def test_unknown_agent_404(self, client):
        r = client.get("/api/metrics/latest/not-exist-agent")
        assert r.status_code == 404


# ── 트랜잭션 수집 ────────────────────────────────────────────

class TestTransactions:
    def test_completed_txn_ingest(self, client):
        r = client.post("/api/transactions", json={
            "agent_id":   AGENT_ID,
            "txn_id":     "txn-001",
            "url":        "/api/login",
            "method":     "POST",
            "status_code": 200,
            "elapsed_ms": 120,
            "sql_count":  2,
            "error_yn":   False,
            "client_ip":  "10.0.1.1",
        })
        assert r.status_code == 201

    def test_error_txn_ingest(self, client):
        """에러 트랜잭션도 정상 수집되어야 함"""
        r = client.post("/api/transactions", json={
            "agent_id":   AGENT_ID,
            "txn_id":     "txn-error-001",
            "url":        "/api/order",
            "method":     "POST",
            "status_code": 500,
            "elapsed_ms": 3500,
            "sql_count":  1,
            "error_yn":   True,
        })
        assert r.status_code == 201

    def test_active_txn_batch_ingest(self, client):
        r = client.post("/api/transactions/active", json=[
            {"agent_id": AGENT_ID, "txn_id": "atxn-1", "url": "/api/search", "elapsed_ms": 200, "status": "running"},
            {"agent_id": AGENT_ID, "txn_id": "atxn-2", "url": "/api/product/list", "elapsed_ms": 800, "status": "waiting"},
        ])
        assert r.status_code == 201
        assert r.json()["count"] == 2


# ── SQL 수집 ─────────────────────────────────────────────────

class TestSqlStats:
    def test_sql_stat_ingest(self, client):
        r = client.post("/api/sql/stats", json=[{
            "agent_id":   AGENT_ID,
            "sql_hash":   "abc123",
            "sql_text":   "select * from orders where user_id=?",
            "exec_count": 15,
            "total_ms":   750,
            "max_ms":     200,
            "error_count": 0,
        }])
        assert r.status_code == 201
        assert r.json()["count"] == 1

    def test_sql_stat_batch(self, client):
        r = client.post("/api/sql/stats", json=[
            {"agent_id": AGENT_ID, "sql_hash": f"hash{i}",
             "sql_text": f"select {i}", "exec_count": i,
             "total_ms": i * 10, "max_ms": i * 5, "error_count": 0}
            for i in range(1, 6)
        ])
        assert r.status_code == 201
        assert r.json()["count"] == 5


# ── 알람 수집 ────────────────────────────────────────────────

class TestAlarms:
    def test_alarm_ingest(self, client):
        r = client.post("/api/alarms", json={
            "agent_id":    AGENT_ID,
            "alarm_type":  "CPU_HIGH",
            "severity":    "CRITICAL",
            "message":     "CPU_HIGH: 92.5% (threshold 80.0%)",
            "threshold":   80.0,
            "actual_value": 92.5,
        })
        assert r.status_code == 201

    def test_alarm_list_returned(self, client):
        r = client.get(f"/api/alarms/{AGENT_ID}")
        assert r.status_code == 200
        alarms = r.json()
        assert len(alarms) >= 1
        assert alarms[0]["alarm_type"] == "CPU_HIGH"

    def test_warning_severity(self, client):
        r = client.post("/api/alarms", json={
            "agent_id":    AGENT_ID,
            "alarm_type":  "MEM_HIGH",
            "severity":    "WARNING",
            "message":     "MEM_HIGH: 87.0%",
            "threshold":   85.0,
            "actual_value": 87.0,
        })
        assert r.status_code == 201
