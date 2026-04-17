"""
Mock JSPD Agent — Tomcat
실제 JSPD 수집 주기를 모방하여 DataGather(Mock Collector)로 데이터 전송
"""
import os
import time
import uuid
import random
import hashlib
import httpx

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://localhost:8080")
AGENT_ID      = os.getenv("AGENT_ID", "tomcat-agent-01")
WAS_TYPE      = os.getenv("WAS_TYPE", "tomcat")
HOST          = os.getenv("HOSTNAME", "tomcat-host")

URLS = ["/api/login", "/api/order", "/api/product/list", "/api/user/profile", "/api/search"]
SQLS = [
    ("select * from orders where user_id=?", "a1b2c3"),
    ("select * from products limit 100",     "d4e5f6"),
    ("insert into sessions values(?)",        "g7h8i9"),
    ("update users set last_login=? where id=?", "j0k1l2"),
]

ALARM_RULES = [
    ("CPU_HIGH",      "CRITICAL", 80.0,  "cpu_pct"),
    ("MEM_HIGH",      "WARNING",  85.0,  "mem_pct"),
    ("DB_POOL_FULL",  "CRITICAL", 90.0,  "pool_pct"),
]


def post(path: str, payload):
    try:
        r = httpx.post(f"{COLLECTOR_URL}{path}", json=payload, timeout=3)
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] {path} failed: {e}")


def register():
    post("/api/agents/register", {"agent_id": AGENT_ID, "was_type": WAS_TYPE, "host": HOST})
    print(f"[INFO] Agent registered: {AGENT_ID}")


def make_snapshot() -> dict:
    cpu      = round(random.gauss(40, 20), 2)
    mem_used = round(random.uniform(512, 3500), 2)
    mem_tot  = 4096.0
    jvm_cpu  = round(random.gauss(30, 15), 2)
    heap_max = 2048.0
    heap_used= round(random.uniform(200, 1800), 2)
    pool_max = 50
    pool_act = random.randint(0, pool_max)

    # 가끔 이상 수치 발생 (10% 확률)
    if random.random() < 0.10:
        cpu = round(random.uniform(85, 100), 2)
    if random.random() < 0.05:
        heap_used = round(random.uniform(1900, 2048), 2)

    return {
        "agent_id":        AGENT_ID,
        "cpu_pct":         max(0, min(100, cpu)),
        "mem_used_mb":     mem_used,
        "mem_total_mb":    mem_tot,
        "jvm_cpu_pct":     max(0, min(100, jvm_cpu)),
        "jvm_heap_used_mb": heap_used,
        "jvm_heap_max_mb":  heap_max,
        "thread_count":    random.randint(10, 200),
        "pool_active":     pool_act,
        "pool_idle":       pool_max - pool_act,
        "pool_max":        pool_max,
    }


def make_transaction() -> dict:
    url       = random.choice(URLS)
    elapsed   = int(random.expovariate(1/200))   # 평균 200ms
    is_slow   = elapsed > 2000
    is_error  = random.random() < 0.03            # 3% 에러율
    return {
        "agent_id":    AGENT_ID,
        "txn_id":      str(uuid.uuid4()),
        "url":         url,
        "method":      "GET" if "list" in url or "profile" in url else "POST",
        "status_code": 500 if is_error else 200,
        "elapsed_ms":  elapsed,
        "sql_count":   random.randint(1, 10),
        "error_yn":    is_error,
        "client_ip":   f"10.0.{random.randint(0,255)}.{random.randint(1,254)}",
    }


def make_active_transactions() -> list:
    count = random.randint(0, 8)
    return [
        {
            "agent_id":   AGENT_ID,
            "txn_id":     str(uuid.uuid4()),
            "url":        random.choice(URLS),
            "elapsed_ms": random.randint(0, 5000),
            "status":     random.choice(["running", "waiting"]),
        }
        for _ in range(count)
    ]


def make_sql_stats() -> list:
    return [
        {
            "agent_id":   AGENT_ID,
            "sql_hash":   sql_hash,
            "sql_text":   sql_text,
            "exec_count": random.randint(1, 50),
            "total_ms":   random.randint(10, 5000),
            "max_ms":     random.randint(50, 3000),
            "error_count": random.randint(0, 2),
        }
        for sql_text, sql_hash in random.sample(SQLS, k=random.randint(1, len(SQLS)))
    ]


def check_alarms(snapshot: dict):
    mem_pct  = snapshot["mem_used_mb"] / snapshot["mem_total_mb"] * 100
    pool_pct = snapshot["pool_active"] / snapshot["pool_max"] * 100 if snapshot["pool_max"] else 0
    values   = {"cpu_pct": snapshot["cpu_pct"], "mem_pct": mem_pct, "pool_pct": pool_pct}

    for alarm_type, severity, threshold, key in ALARM_RULES:
        actual = values[key]
        if actual >= threshold:
            post("/api/alarms", {
                "agent_id":    AGENT_ID,
                "alarm_type":  alarm_type,
                "severity":    severity,
                "message":     f"{alarm_type}: {actual:.1f}% (threshold {threshold}%)",
                "threshold":   threshold,
                "actual_value": round(actual, 2),
            })


def main():
    time.sleep(3)   # collector 기동 대기
    register()

    tick_3s  = 0
    tick_1s  = 0

    while True:
        time.sleep(1)
        tick_1s  += 1
        tick_3s  += 1

        # 1초 주기
        txn = make_transaction()
        post("/api/transactions", txn)
        post("/api/transactions/active", make_active_transactions())

        # 3초 주기
        if tick_3s >= 3:
            tick_3s = 0
            snapshot = make_snapshot()
            post("/api/metrics/snapshot", snapshot)
            post("/api/sql/stats", make_sql_stats())
            check_alarms(snapshot)
            print(f"[{AGENT_ID}] cpu={snapshot['cpu_pct']}% heap={snapshot['jvm_heap_used_mb']}MB txn={txn['url']} {txn['elapsed_ms']}ms")


if __name__ == "__main__":
    main()
