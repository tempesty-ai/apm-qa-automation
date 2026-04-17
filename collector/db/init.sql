-- 에이전트 등록 정보
CREATE TABLE IF NOT EXISTS agents (
    id          SERIAL PRIMARY KEY,
    agent_id    VARCHAR(64) UNIQUE NOT NULL,
    was_type    VARCHAR(32),        -- tomcat, jeus
    host        VARCHAR(128),
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ
);

-- CPU / Memory / JVM 메트릭 (3초 주기 스냅샷)
CREATE TABLE IF NOT EXISTS metrics_snapshot (
    id          BIGSERIAL PRIMARY KEY,
    agent_id    VARCHAR(64) NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_pct     NUMERIC(5,2),
    mem_used_mb NUMERIC(10,2),
    mem_total_mb NUMERIC(10,2),
    jvm_cpu_pct  NUMERIC(5,2),
    jvm_heap_used_mb  NUMERIC(10,2),
    jvm_heap_max_mb   NUMERIC(10,2),
    thread_count INT,
    pool_active  INT,
    pool_idle    INT,
    pool_max     INT
);

-- 완료 트랜잭션 (1초 주기 누적)
CREATE TABLE IF NOT EXISTS transactions (
    id           BIGSERIAL PRIMARY KEY,
    agent_id     VARCHAR(64) NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    txn_id       VARCHAR(64),
    url          VARCHAR(512),
    method       VARCHAR(16),
    status_code  INT,
    elapsed_ms   INT,
    sql_count    INT,
    error_yn     BOOLEAN DEFAULT FALSE,
    client_ip    VARCHAR(64)
);

-- 액티브 트랜잭션 스냅샷 (1초 주기)
CREATE TABLE IF NOT EXISTS active_transactions (
    id           BIGSERIAL PRIMARY KEY,
    agent_id     VARCHAR(64) NOT NULL,
    snapshot_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    txn_id       VARCHAR(64),
    url          VARCHAR(512),
    elapsed_ms   INT,
    status       VARCHAR(32)   -- running, waiting
);

-- SQL 수행 정보 (3초 주기 누적)
CREATE TABLE IF NOT EXISTS sql_stats (
    id           BIGSERIAL PRIMARY KEY,
    agent_id     VARCHAR(64) NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sql_hash     VARCHAR(64),
    sql_text     TEXT,
    exec_count   INT,
    total_ms     INT,
    max_ms       INT,
    error_count  INT
);

-- 알람 (3초 주기, 임계치 초과 시)
CREATE TABLE IF NOT EXISTS alarms (
    id           BIGSERIAL PRIMARY KEY,
    agent_id     VARCHAR(64) NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alarm_type   VARCHAR(64),   -- CPU_HIGH, MEM_HIGH, SLOW_TXN, DB_POOL_FULL
    severity     VARCHAR(16),   -- WARNING, CRITICAL
    message      TEXT,
    threshold    NUMERIC,
    actual_value NUMERIC
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_metrics_agent_time ON metrics_snapshot (agent_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_txn_agent_time ON transactions (agent_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_alarm_agent_time ON alarms (agent_id, occurred_at DESC);
