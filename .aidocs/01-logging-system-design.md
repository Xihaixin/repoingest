# Repoingest 日志系统重构 —— 设计方案

> 阶段：Phase 1 · 分析与设计
> 日期：2026-08-09
> 状态：待评审

---

## 1. 背景与问题分析

当前系统部署在服务器上后，由于日志系统功能薄弱，**用户的失败请求无法溯源**，排查问题耗时过长。用户的核心诉求是：**能够从日志中快速定位任意一次失败请求的完整链路**。

### 1.1 现状调研（代码基线）

当前日志系统位于 `src/gitingest/utils/logger.py`，基于 **Python 标准库 `logging`** 手工搭建，主要问题如下：

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P1 | **控制台日志没有日期**，`datefmt="%H:%M:%S"`，只有时间 | `logger.py:130` | 无法判断事件发生在哪一天，直接导致"溯源难" |
| P2 | **无请求关联标识（request_id）**，请求从 HTTP 进入 → 解析 → clone → 摘要，全程没有统一上下文 | 全局 | 一次失败请求散落在多行日志中，无法串成一条链路 |
| P3 | **单一日志文件无轮转**，`src/logs/repoingest.log` 无限增长 | `main.py:25` | 磁盘耗尽、日志难以检索 |
| P4 | **无结构化字段**（客户端 IP、方法、路径、状态码、耗时） | 全局 | 无法按用户/IP/URL 快速过滤 |
| P5 | 异常多使用 `logger.error("...%s", exc)`，**丢失堆栈** | `cloning.py`、`query_processor.py` 等 | 只见错误消息，不见调用链 |
| P6 | 标准库 `logging` 配置繁琐：手动 Formatter/Handler、颜色处理、重复初始化哨兵（`_initialized`） | `logger.py` | 维护成本高 |

### 1.2 日志现状示例（控制台）

```
14:32:05 | INFO  | repoingest.server | Query succeeded ...
14:32:09 | ERROR | repoingest.cloning | Repository not found: ...
```

**问题一眼可见：无日期、无请求上下文、无堆栈。**

---

## 2. 技术选型

### 2.1 候选对比

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 标准库 `logging`（现状） | 零依赖 | 配置繁琐、无轮转、无上下文绑定 | ❌ 保留现状无法解决问题 |
| `structlog` | 结构化日志强、适合大型事件系统 | 学习成本高、配置偏重、与第三方库桥接需要额外工作 | ⚠️ 可选 |
| **`loguru`** | **开箱即用、内置轮转/保留、`bind()`/`contextualize()` 上下文、`exception()` 自动堆栈、JSON 序列化、与 stdlib 无缝桥接** | 依赖库，需迁移调用点的 `%` 格式化 | ✅ **推荐** |

### 2.2 结论：采用 **Loguru**

用户记忆中的"比标准库更强大的库"即为 **Loguru**。选择理由：

1. **零样板配置**：无需手动编写 Formatter/Handler/Filter，`logger.add()` 一行即可。
2. **自动轮转**：内置 `rotation` / `retention` / `compression`，解决 P3。
3. **上下文绑定**：`logger.bind()` 与 `logger.contextualize()` 可将 `request_id`、IP 等贯穿整条请求链路，解决 P2。
4. **默认格式含日期**：`2026-08-09 14:32:05.123 | LEVEL | name | message`，解决 P1。
5. **异常自动堆栈**：`logger.exception()` 输出完整 traceback，解决 P5。
6. **stdlib 桥接**：将 uvicorn、aiohttp、gitpython 等第三方库的日志统一吸入 Loguru 管道，日志入口唯一。

---

## 3. 目标架构

```
                    ┌──────────────────────────────────────────┐
                    │           Loguru Logger (唯一入口)        │
                    └──────────────────────────────────────────┘
                       ▲                ▲               ▲
        ┌──────────────┴────┐   ┌───────┴──────┐   ┌────┴─────────┐
        │  Console Sink     │   │  File Sink   │   │ stdlib 桥接   │
        │  (带颜色+日期)      │   │ (每日轮转)    │   │ uvicorn/三方库│
        └───────────────────┘   └──────────────┘   └──────────────┘
                       ▲
        ┌──────────────┴───────────────┐
        │  RequestLoggingMiddleware    │
        │  · 生成 request_id           │
        │  · 绑定 client IP / method   │
        │  · 记录开始/结束 + 状态码+耗时 │
        └──────────────────────────────┘
```

### 3.1 模块职责

| 文件 | 职责 |
|------|------|
| `src/gitingest/utils/logger.py` | **重写**：Loguru 配置（console + 文件 + 轮转 + env 参数）、`get_logger()`、`setup_logging()`、stdlib `InterceptHandler` 桥接 |
| `src/server/middleware.py` | **新建**：`RequestLoggingMiddleware`，请求级关联 ID 与访问日志 |
| `src/server/main.py` | 注册中间件；`setup_logging()` 调用不变（保持 API 兼容） |
| 各业务模块 | 仅迁移 `%` → `{}` 格式化，`get_logger()` 调用不变 |

### 3.2 向后兼容策略

- `setup_logging(...)`、`get_logger(...)` **签名不变**，`main.py:27` 无需改动。
- `get_logger()` 返回绑定 `module` 上下文的 Loguru logger，格式中含模块名，行为与原 `repoingest.<name>` 一致。
- 通过 `InterceptHandler` + `logging.basicConfig(handlers=[...], force=True)`，第三方库日志进入 Loguru 管道，不产生重复日志（`logger.remove()` 清空默认 handler）。

---

## 4. 日志格式设计

### 4.1 格式模板（含日期）

```text
{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {extra[module]} | {message}
```

- **控制台**（`colorize=True`）：级别带颜色，human-readable。
- **文件**（可选 JSON）：`REPOINGEST_LOG_JSON=1` 时输出 JSON 行，便于后续接入日志平台（ELK/Loki）。

### 4.2 输出示例

```text
# 控制台（本次修复核心：日期）
2026-08-09 14:32:05.123 | INFO    | repoingest.server | request_id=9f3a2c1d ip=203.0.113.7 | Request started method=POST path=/api/ingest
2026-08-09 14:32:05.456 | DEBUG   | repoingest.cloning | request_id=9f3a2c1d | Starting clone for https://...
2026-08-09 14:32:05.789 | INFO    | repoingest.server | request_id=9f3a2c1d | Request completed 200 in 321.4ms
2026-08-09 14:32:09.001 | ERROR   | repoingest.cloning | request_id=9f3a2c1d ip=203.0.113.7 | Repository not found: ...
Traceback (most recent call last):
  ...
```

同一 `request_id` 即可串联一次请求的全部阶段——**失败溯源从此有迹可循**。

---

## 5. 请求溯源设计（核心）

### 5.1 `RequestLoggingMiddleware` 流程

1. 为每个请求生成 `request_id = uuid.uuid4().hex[:12]`。
2. `logger.contextualize(request_id=..., ip=..., method=..., path=...)` 进入上下文管理器，**同一请求内所有 `get_logger()` 输出自动携带这些字段**。
3. 记录请求开始（DEBUG）。
4. `await call_next(request)`，异常时 `logger.exception()` 输出完整堆栈后重新抛出。
5. 记录请求结束（INFO）：`status_code`、`duration_ms`。
6. 将 `X-Request-ID` 写入响应头，**便于用户上报问题时带回该 ID**，实现前后端联动溯源。

### 5.2 关键代码路径（将采集到的信息）

| 字段 | 来源 |
|------|------|
| `request_id` | 中间件生成 |
| `client_ip` | `request.client.host`（兼容反向代理时读取 `X-Forwarded-For`） |
| `method` / `path` | `request.method` / `request.url.path` |
| `status_code` / `duration_ms` | 中间件测量 |

---

## 6. 日志轮转与持久化策略

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `REPOINGEST_LOG_LEVEL` | `INFO` | 全局级别（DEBUG/INFO/WARNING/ERROR/CRITICAL） |
| `REPOINGEST_LOG_FILE` | `src/logs/repoingest.log` | 日志文件路径（`main.py` 现有默认值不变） |
| `REPOINGEST_LOG_ROTATION` | `00:00` | 每日 0 点轮转 |
| `REPOINGEST_LOG_RETENTION` | `14 days` | 保留 14 天，自动清理 |
| `REPOINGEST_LOG_COMPRESSION` | `gz` | 轮转文件压缩，节省磁盘 |
| `REPOINGEST_LOG_JSON` | `0` | `1` 时文件输出 JSON 行 |
| `REPOINGEST_LOG_TO_STDOUT` | `1` | `0` 时关闭控制台输出（生产环境可选） |

> 文件 handler 级别固定为 `DEBUG`（`main.py` 原有行为），控制台遵循 `REPOINGEST_LOG_LEVEL`。

---

## 7. 实施计划（分阶段）

| 阶段 | 内容 | 产出 |
|------|------|------|
| **1** | 依赖：`pyproject.toml` 加入 `loguru`，`uv sync` 安装 | 依赖就绪 |
| **2** | 重写 `logger.py`：Loguru 配置 + `setup_logging`/`get_logger` 兼容层 + stdlib 桥接 | 日志框架核心 |
| **3** | 新建 `src/server/middleware.py` 并在 `main.py` 注册 | 请求溯源能力 |
| **4** | 迁移全部 `%` 格式化调用点为 `{}`（约 40 处，10 个文件） | 日志输出正确 |
| **5** | 更新 `.env` / `.gitignore` / 文档 | 配置可追踪 |
| **6** | 验证：跑测试 + 启动服务器 smoke test（确认日期、轮转、request_id） | 验收 |

---

## 8. 验收标准

1. 控制台与文件日志**均含完整日期** `YYYY-MM-DD HH:mm:ss.SSS`。
2. 单次失败请求可通过 `request_id` 串联起 **HTTP 入口 → 解析 → clone → 摘要 → 响应** 全链路。
3. 异常日志包含完整 **traceback**。
4. 日志文件**每日轮转**，保留 14 天，不无限增长。
5. 第三方库（uvicorn 等）日志进入统一管道，无重复输出。
6. 既有 `setup_logging()` / `get_logger()` 调用点零改动或仅格式迁移。

---

*本设计文档完成后，进入 Phase 2 分阶段实施，实施过程记录于 `02-implementation-log.md`。*
