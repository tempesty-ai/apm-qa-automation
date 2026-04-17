"""
APM Collector 부하 테스트
실행: locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 60s --host http://localhost:8080
대시보드: locust -f tests/load/locustfile.py --host http://localhost:8080  → http://localhost:8089
"""
import uuid
import random
from locust import HttpUser, task, between, events

AGENT_IDS = [f"load-agent-{i:02d}" for i in range(1, 11)]
URLS      = ["/api/login", "/api/order", "/api/product/list", "/api/user/profile"]


@events.test_start.add_listener
def register_agents(environment, **kwargs):
    """부하 시작 전 에이전트 일괄 등록"""
    import httpx
    base = environment.host or "http://localhost:8080"
    for agent_id in AGENT_IDS:
        try:
            httpx.post(f"{base}/api/agents/register", json={
                "agent_id": agent_id,
                "was_type": random.choice(["tomcat", "jeus"]),
                "host":     f"host-{agent_id}",
            }, timeout=3)
        except Exception:
            pass


class ApmAgentUser(HttpUser):
    """에이전트 10개가 동시에 데이터를 전송하는 시나리오"""
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.agent_id = random.choice(AGENT_IDS)

    @task(3)
    def send_metric_snapshot(self):
        """3초 주기 메트릭 (가장 빈번한 수집)"""
        cpu = round(random.uniform(10, 100), 2)
        self.client.post("/api/metrics/snapshot", json={
            "agent_id":         self.agent_id,
            "cpu_pct":          cpu,
            "mem_used_mb":      round(random.uniform(512, 3800), 2),
            "mem_total_mb":     4096.0,
            "jvm_cpu_pct":      round(random.uniform(5, 80), 2),
            "jvm_heap_used_mb": round(random.uniform(200, 2000), 2),
            "jvm_heap_max_mb":  2048.0,
            "thread_count":     random.randint(10, 300),
            "pool_active":      random.randint(0, 50),
            "pool_idle":        random.randint(0, 50),
            "pool_max":         50,
        }, name="/api/metrics/snapshot")

    @task(5)
    def send_transaction(self):
        """1초 주기 트랜잭션 (가장 많은 볼륨)"""
        elapsed = int(random.expovariate(1 / 300))
        self.client.post("/api/transactions", json={
            "agent_id":   self.agent_id,
            "txn_id":     str(uuid.uuid4()),
            "url":        random.choice(URLS),
            "method":     random.choice(["GET", "POST"]),
            "status_code": 500 if random.random() < 0.03 else 200,
            "elapsed_ms": elapsed,
            "sql_count":  random.randint(1, 10),
            "error_yn":   elapsed > 3000,
        }, name="/api/transactions")

    @task(2)
    def send_active_transactions(self):
        """액티브 트랜잭션 스냅샷"""
        self.client.post("/api/transactions/active", json=[
            {
                "agent_id":   self.agent_id,
                "txn_id":     str(uuid.uuid4()),
                "url":        random.choice(URLS),
                "elapsed_ms": random.randint(0, 5000),
                "status":     random.choice(["running", "waiting"]),
            }
            for _ in range(random.randint(1, 5))
        ], name="/api/transactions/active")

    @task(1)
    def send_sql_stats(self):
        """SQL 수행 정보"""
        self.client.post("/api/sql/stats", json=[{
            "agent_id":   self.agent_id,
            "sql_hash":   f"hash{random.randint(1, 20):02d}",
            "sql_text":   "select * from orders where id=?",
            "exec_count": random.randint(1, 100),
            "total_ms":   random.randint(10, 5000),
            "max_ms":     random.randint(50, 3000),
            "error_count": random.randint(0, 3),
        }], name="/api/sql/stats")

    @task(1)
    def send_alarm(self):
        """알람 (낮은 빈도)"""
        if random.random() < 0.15:
            self.client.post("/api/alarms", json={
                "agent_id":    self.agent_id,
                "alarm_type":  random.choice(["CPU_HIGH", "MEM_HIGH", "DB_POOL_FULL"]),
                "severity":    random.choice(["WARNING", "CRITICAL"]),
                "message":     "load test alarm",
                "threshold":   80.0,
                "actual_value": round(random.uniform(80, 100), 2),
            }, name="/api/alarms")
