# .aidocs —— 日志系统重构记录

本目录记录了 Repoingest 日志系统重构的设计与实施过程，供后续跟进与审核。

## 文档索引

| 文件 | 内容 |
|------|------|
| [`01-logging-system-design.md`](./01-logging-system-design.md) | 设计方案：问题分析、技术选型（Loguru）、目标架构、日志格式、请求溯源设计、轮转策略、验收标准 |
| [`02-implementation-log.md`](./02-implementation-log.md) | 实施日志：7 个阶段逐项记录（依赖 → logger.py → 中间件 → 桥接 → 格式化迁移 → 配置 → 验证） |

## 变更文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `pyproject.toml` | 修改 | 新增依赖 `loguru==0.7.3` |
| `src/gitingest/utils/logger.py` | 重写 | 基于 Loguru 的日志配置（日期、轮转、上下文、stdlib 桥接） |
| `src/server/middleware.py` | **新增** | `RequestLoggingMiddleware`，请求级 `request_id` 溯源 |
| `src/server/main.py` | 修改 | 注册中间件；uvicorn `access_log=False`、`log_config=None` |
| `src/server/query_processor.py` | 修改 | `%`→`{}`；失败日志升级为 `logger.exception` |
| `src/server/routers_utils.py` | 修改 | 同上 |
| `src/server/server_utils.py` | 修改 | 同上 |
| `src/gitingest/cloning.py` | 修改 | `%`→`{}` |
| `src/gitingest/ingestion.py` | 修改 | `%`→`{}` |
| `src/gitingest/output_formatters.py` | 修改 | `%`→`{}` |
| `src/gitingest/utils/git_utils.py` | 修改 | `%`→`{}`；失败日志升级为 `logger.exception` |
| `.env` | 修改 | 新增日志配置项 |
| `README.md` | 修改 | 新增「📝 日志系统」章节 |
