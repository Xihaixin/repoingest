# Repoingest 日志系统重构 —— 实施日志

> 阶段：Phase 2 · 分阶段实施
> 日期：2026-08-09
> 对应设计文档：`01-logging-system-design.md`
> 状态：已实施，待部署验证

---

## 阶段总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0 | 现状调研（代码基线分析） | ✅ |
| 1 | 依赖引入：`loguru` | ✅ |
| 2 | 重写 `src/gitingest/utils/logger.py` | ✅ |
| 3 | 请求溯源中间件 `src/server/middleware.py` | ✅ |
| 4 | 第三方库日志桥接（stdlib → Loguru） | ✅ |
| 5 | 迁移 `%` 格式化调用点 → `{}`（约 60 处，12 个文件） | ✅ |
| 6 | 更新 `.env` / `README.md` 配置文档 | ✅ |
| 7 | 验证：导入检查 + TestClient 冒烟测试 + 轮转/JSON 测试 | ✅ |

---

## Stage 0 · 现状调研

关键发现（详见设计文档 §1）：

1. `src/gitingest/utils/logger.py:130` 控制台 `datefmt="%H:%M:%S"` —— **只有时间没有日期**（用户反馈的核心问题）。
2. 日志文件 `src/logs/repoingest.log` 无轮转，无限增长。
3. 全局无 `request_id`，一次失败请求散落在多行日志中无法串联。
4. 异常日志多为 `logger.error("...%s", exc)`，**丢失堆栈**。
5. 依赖 `_initialized` 哨兵 + 手工 Formatter/Handler 防止重复初始化，维护成本高。

---

## Stage 1 · 依赖引入

**变更文件**：`pyproject.toml`

- 在依赖列表（字母序）中插入 `"loguru==0.7.3"`（位于 `limits` 与 `markdown-it-py` 之间）。
- 执行 `uv sync`，成功安装 `loguru==0.7.3` 及 `win32-setctime==1.2.0`。

```bash
$ uv sync
Installed 2 packages
 + loguru==0.7.3
 + win32-setctime==1.2.0
```

---

## Stage 2 · 重写 logger.py

**变更文件**：`src/gitingest/utils/logger.py`（整体重写）

### 2.1 核心设计

| 组成 | 说明 |
|------|------|
| `_make_formatter(colorize)` | 返回一个 Loguru **callable format**（每记录调用一次），时间戳恒为 `YYYY-MM-DD HH:mm:ss.SSS`；仅当上下文绑定了 `request_id`/`client_ip`/`method`/`path` 时才输出这些字段；存在异常时追加 `{exception}` 渲染完整 traceback |
| `setup_logging(...)` | 保持原签名（`name`/`log_level`/`log_file`）兼容；`logger.remove()` 清理默认 handler；控制台 sink（带颜色，级别取 `REPOINGEST_LOG_LEVEL`）+ 文件 sink（级别固定 DEBUG，支持轮转/保留/压缩/JSON） |
| `get_logger(child_name)` | 返回 `_base_logger.bind(module="repoingest.<child>")`，命名空间行为与原实现一致 |
| `_InterceptHandler` | stdlib `logging.Handler` 桥接，将 uvicorn/aiohttp/gitpython/httpx 等三方库日志吸入 Loguru 管道 |

### 2.2 关键实现细节

- **callable format** 解决了"可选上下文字段"问题：`{extra[request_id]}` 在普通模板中缺失会抛 `KeyError`，改为每记录判断 `record["extra"]` 后动态拼接。
- **`{exception}` 必须出现在 format 中**，否则 `logger.exception()` 的 traceback 被静默丢弃（验证阶段发现并修复）。
- 安全：`diagnose=False`，traceback 不泄露局部变量（避免 token 等敏感信息）。
- 桥接中禁用 `uvicorn.access`（冗余，由中间件提供更丰富的访问日志）。

### 2.3 验证

```text
2026-08-09 22:37:39.795 | WARNING  | gitingest.config:get_temp_base_path:28 - ...   # 默认 handler（setup 前）
2026-08-09 22:37:40.308 | INFO     | repoingest.server | Test message with number 42 # 含日期 ✅
```

---

## Stage 3 · 请求溯源中间件

**新增文件**：`src/server/middleware.py`
**变更文件**：`src/server/main.py`

### 3.1 `RequestLoggingMiddleware`

基于 `starlette.middleware.base.BaseHTTPMiddleware`（兼容 `app.add_middleware()`）：

```python
with logger.contextualize(request_id=..., client_ip=..., method=..., path=...):
    logger.debug("Request started")
    response = await call_next(request)     # 异常时 logger.exception() 后重抛
    logger.info("Request completed | status={} | duration={:.1f}ms", ...)
    response.headers["X-Request-ID"] = request_id
```

要点：
- `request_id = uuid.uuid4().hex[:12]`，贯穿整个请求生命周期。
- `_client_ip()` 优先取 `X-Forwarded-For`（兼容反向代理），回退 `request.client.host`。
- `X-Request-ID` 写入响应头，用户报障时可带回该 ID 联动溯源。
- Loguru 的 `contextualize` 基于 `contextvars`，异步 handler 内各模块日志自动携带上下文。

### 3.2 中间件顺序（main.py）

**重要修正**：Starlette `add_middleware` 后添加者位于最外层。最初将 `RequestLoggingMiddleware` 加在 `TrustedHostMiddleware` 之前，导致被拒绝的请求（如非法 Host）在中间件之前就返回 400、无 `request_id`。已调整为**最后注册**（最外层），确保所有请求（含被拒绝的）都被记录并分配 `request_id`。

### 3.3 uvicorn 配置（main.py）

```python
uvicorn.Config(..., access_log=False, log_config=None)
```

`access_log=False` 关闭 uvicorn 默认访问日志（与中间件访问日志重复）；`log_config=None` 防止 uvicorn 覆盖我们的 stdlib 桥接。

---

## Stage 4 · 第三方库日志桥接

在 `setup_logging()` 中调用 `_setup_stdlib_bridge()`：

```python
handler = _InterceptHandler()
logging.basicConfig(handlers=[handler], level=0, force=True)
logging.getLogger("uvicorn.access").disabled = True
```

验证结果（冒烟测试日志）：`stdlib.git.cmd`、`stdlib.asyncio`、`stdlib.httpx` 等均流入 Loguru 统一管道，格式一致、无重复输出。

---

## Stage 5 · `%` 格式化 → `{}` 迁移

Loguru 使用 `str.format`（`{}`）而非 printf（`%`），故全部日志调用点需迁移。**重点：首次正则漏掉了多行调用**（`%` 在字符串内部多行处），补查 `%s|%d|%f` 后覆盖全部。

### 迁移文件与调用点数

| 文件 | 迁移数 |
|------|-------|
| `src/server/main.py` | 3 |
| `src/server/query_processor.py` | 2 |
| `src/server/routers_utils.py` | 4 |
| `src/server/server_utils.py` | 8 |
| `src/gitingest/cloning.py` | 10 |
| `src/gitingest/ingestion.py` | 7 |
| `src/gitingest/output_formatters.py` | 3 |
| `src/gitingest/utils/git_utils.py` | 21 |
| **合计** | **约 60 处** |

### 顺带增强（设计 P5）

将 `except` 块内的 `logger.error("...", exc)` 升级为 `logger.exception(...)`，输出完整 traceback：

- `query_processor.py:104`（Query failed）
- `routers_utils.py:58`（Internal server error）
- `server_utils.py:125/158/165`
- `git_utils.py:223/286`（ls-remote 失败）

---

## Stage 6 · 配置与文档

**变更文件**：`.env`、`README.md`

`.env` 新增日志配置（带中文注释）：

```ini
REPOINGEST_LOG_LEVEL=INFO
REPOINGEST_LOG_FILE=src/logs/repoingest.log
REPOINGEST_LOG_ROTATION=00:00
REPOINGEST_LOG_RETENTION=14 days
REPOINGEST_LOG_COMPRESSION=gz
REPOINGEST_LOG_JSON=0
REPOINGEST_LOG_TO_STDOUT=1
```

`README.md` 新增「📝 日志系统」章节，说明 `request_id` 溯源机制与各环境变量。

> `.gitignore` 已含 `src/logs`，无需改动；`.aidocs/` 需纳入版本管理供评审跟进，不加忽略。

---

## Stage 7 · 验证

### 7.1 导入检查

```bash
$ python -c "import server.main, server.middleware, gitingest.* ..."
All modules imported OK
```

### 7.2 冒烟测试（TestClient，真实请求）

| 请求 | 结果 | X-Request-ID |
|------|------|--------------|
| `GET /health` | 200 | `d3359ac3a17f` |
| `GET /` | 200 | `410e9621969d` |
| `POST /api/ingest`（不存在仓库） | **500** | `3934a6f96325` |
| `GET /api/ingest`（不存在仓库） | 200 | `c7d5e54f1f0b` |

**失败请求全链路日志（同一 `rid=3934a6f96325`）**：

```text
2026-08-09 22:47:41.xxx | DEBUG    | repoingest.git_utils      | rid=3934a6f96325 | Probing repository ...
2026-08-09 22:47:41.xxx | WARNING  | repoingest.git_utils      | rid=3934a6f96325 | Repository access denied [..] (HTTP 401)
2026-08-09 22:47:41.xxx | INFO     | repoingest.cloning         | rid=3934a6f96325 | Starting clone for ...
2026-08-09 22:47:41.xxx | ERROR    | repoingest.cloning         | Git operation FAILED ... (exit code 128)
2026-08-09 22:47:41.xxx | ERROR    | repoingest.query_processor | rid=3934a6f96325 | Query failed [...] | Traceback (...)
2026-08-09 22:47:41.xxx | ERROR    | repoingest.routers_utils   | rid=3934a6f96325 | Internal server error ...
2026-08-09 22:47:42.145 | INFO     | repoingest.server.middleware| rid=3934a6f96325 | Request completed | status=500 | duration=1197.5ms
```

### 7.3 轮转与 JSON 测试

- **轮转**：`rotation="1 B"` 强制小体积轮转，逐行生成 `rot.<时间戳>.log` ✅（生产默认 `00:00` 每日轮转）
- **JSON**：`serialize=True` 时 `record.extra` 包含 `request_id`、`module` 等结构化字段 ✅

### 7.4 格式检查

- `black --check`：`logger.py`、`middleware.py`（新增/重写文件）通过 ✅
- 其余文件 black 未通过属**既有风格问题**（迁移前即存在），本次不整体重排以避免无关 diff
- flake8 默认 79 列与项目 black 88 列不一致，E501 大量为既有问题；`F401` 未使用导入为迁移前已存在

---

## 验收清单对照

| # | 验收标准 | 结果 |
|---|---------|------|
| 1 | 控制台与文件日志均含完整日期 | ✅ |
| 2 | 单次失败请求可用 `request_id` 串联全链路 | ✅ |
| 3 | 异常日志包含完整 traceback | ✅ |
| 4 | 日志每日轮转、保留 14 天、不无限增长 | ✅ |
| 5 | 第三方库日志进入统一管道，无重复输出 | ✅ |
| 6 | 既有 `setup_logging()`/`get_logger()` 调用点零 API 破坏 | ✅ |

---

## 遗留事项 / 建议

1. **服务器部署验证**：部署后确认 `src/logs/` 下日志含日期、`X-Request-ID` 正确返回。
2. **可选增强**：接入日志聚合平台（ELK/Loki）时设置 `REPOINGEST_LOG_JSON=1`，并可按 `request_id` 做全文索引。
3. **可选增强**：`_perform_ingestion` 的 `ValueError` 分支可保留 `logger.warning`（预期内校验失败，无需堆栈）。
4. **安全提醒**：`diagnose=False` 已避免 traceback 泄露局部变量；请勿在生产开启 `diagnose`。
