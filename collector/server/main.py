import os
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

DB_DSN = (
    f"postgresql://{os.getenv('DB_USER','apm_user')}:{os.getenv('DB_PASS','apm_pass')}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','apm_db')}"
)

pool: asyncpg.Pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10)
    yield
    await pool.close()


app = FastAPI(title="APM Mock DataGather", version="1.0.0", lifespan=lifespan)


# ── 요청 모델 ──────────────────────────────────────────────

class AgentRegister(BaseModel):
    agent_id: str
    was_type: str
    host: str

class MetricSnapshot(BaseModel):
    agent_id: str
    cpu_pct: float
    mem_used_mb: float
    mem_total_mb: float
    jvm_cpu_pct: float
    jvm_heap_used_mb: float
    jvm_heap_max_mb: float
    thread_count: int
    pool_active: int
    pool_idle: int
    pool_max: int

class Transaction(BaseModel):
    agent_id: str
    txn_id: str
    url: str
    method: str
    status_code: int
    elapsed_ms: int
    sql_count: int
    error_yn: bool = False
    client_ip: Optional[str] = None

class ActiveTransaction(BaseModel):
    agent_id: str
    txn_id: str
    url: str
    elapsed_ms: int
    status: str = "running"

class SqlStat(BaseModel):
    agent_id: str
    sql_hash: str
    sql_text: str
    exec_count: int
    total_ms: int
    max_ms: int
    error_count: int = 0

class Alarm(BaseModel):
    agent_id: str
    alarm_type: str
    severity: str
    message: str
    threshold: float
    actual_value: float


# ── 엔드포인트 ─────────────────────────────────────────────

@app.post("/api/agents/register", status_code=201)
async def register_agent(body: AgentRegister):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agents (agent_id, was_type, host, last_seen_at)
               VALUES ($1, $2, $3, NOW())
               ON CONFLICT (agent_id) DO UPDATE SET last_seen_at = NOW()""",
            body.agent_id, body.was_type, body.host,
        )
    return {"result": "ok", "agent_id": body.agent_id}


@app.post("/api/metrics/snapshot", status_code=201)
async def ingest_snapshot(body: MetricSnapshot):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO metrics_snapshot
               (agent_id, cpu_pct, mem_used_mb, mem_total_mb,
                jvm_cpu_pct, jvm_heap_used_mb, jvm_heap_max_mb,
                thread_count, pool_active, pool_idle, pool_max)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
            body.agent_id, body.cpu_pct, body.mem_used_mb, body.mem_total_mb,
            body.jvm_cpu_pct, body.jvm_heap_used_mb, body.jvm_heap_max_mb,
            body.thread_count, body.pool_active, body.pool_idle, body.pool_max,
        )
        await conn.execute(
            "UPDATE agents SET last_seen_at = NOW() WHERE agent_id = $1", body.agent_id
        )
    return {"result": "ok"}


@app.post("/api/transactions", status_code=201)
async def ingest_transaction(body: Transaction):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO transactions
               (agent_id, txn_id, url, method, status_code,
                elapsed_ms, sql_count, error_yn, client_ip)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            body.agent_id, body.txn_id, body.url, body.method,
            body.status_code, body.elapsed_ms, body.sql_count,
            body.error_yn, body.client_ip,
        )
    return {"result": "ok"}


@app.post("/api/transactions/active", status_code=201)
async def ingest_active_transactions(body: list[ActiveTransaction]):
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO active_transactions (agent_id, txn_id, url, elapsed_ms, status)
               VALUES ($1,$2,$3,$4,$5)""",
            [(t.agent_id, t.txn_id, t.url, t.elapsed_ms, t.status) for t in body],
        )
    return {"result": "ok", "count": len(body)}


@app.post("/api/sql/stats", status_code=201)
async def ingest_sql_stats(body: list[SqlStat]):
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO sql_stats
               (agent_id, sql_hash, sql_text, exec_count, total_ms, max_ms, error_count)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            [(s.agent_id, s.sql_hash, s.sql_text, s.exec_count,
              s.total_ms, s.max_ms, s.error_count) for s in body],
        )
    return {"result": "ok", "count": len(body)}


@app.post("/api/alarms", status_code=201)
async def ingest_alarm(body: Alarm):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO alarms
               (agent_id, alarm_type, severity, message, threshold, actual_value)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            body.agent_id, body.alarm_type, body.severity,
            body.message, body.threshold, body.actual_value,
        )
    return {"result": "ok"}


# ── 조회 API (QA 검증용) ───────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM agents ORDER BY registered_at DESC")
    return [dict(r) for r in rows]


@app.get("/api/metrics/latest/{agent_id}")
async def latest_metrics(agent_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM metrics_snapshot WHERE agent_id=$1 ORDER BY collected_at DESC LIMIT 1",
            agent_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="agent not found")
    return dict(row)


@app.get("/api/alarms/{agent_id}")
async def get_alarms(agent_id: str, limit: int = 20):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM alarms WHERE agent_id=$1 ORDER BY occurred_at DESC LIMIT $2",
            agent_id, limit,
        )
    return [dict(r) for r in rows]


@app.get("/health")
async def health():
    return {"status": "ok"}
