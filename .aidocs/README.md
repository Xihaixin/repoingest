# .aidocs —— 日志系统重构记录

本目录记录了 Repoingest 日志系统重构的设计与实施过程，供后续跟进与审核。

## 文档索引

| 文件 | 内容 |
|------|------|
| [`01-logging-system-design.md`](./01-logging-system-design.md) | 设计方案：问题分析、技术选型（Loguru）、目标架构、日志格式、请求溯源设计、轮转策略、验收标准 |
| [`02-implementation-log.md`](./02-implementation-log.md) | 实施日志：Phase 2–6（日志重构、运行期优化、静态去噪、Home+i18n、任务状态恢复） |
| [`03-log-analysis-and-proposal.md`](./03-log-analysis-and-proposal.md) | 运行期日志分析（7 个问题）+ 日志记录点/记录信息提案 |
| [`04-home-and-i18n-design.md`](./04-home-and-i18n-design.md) | Home 落地页 + 多语言（i18n）设计方案 |
| [`05-job-resume-design.md`](./05-job-resume-design.md) | 处理任务状态保持与恢复（Job Resume）设计方案 |
| [`06-linux-deployment-update.md`](./06-linux-deployment-update.md) | Linux 服务器部署更新全流程：问题诊断、systemd 配置修复、uv 依赖同步、验证与收尾 |

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
| `src/gitingest/cloning.py` | 修改 | `%`→`{}`；**Phase 3**：上下文跨线程传播、兜底级别 WARNING |
| `src/gitingest/ingestion.py` | 修改 | `%`→`{}` |
| `src/gitingest/output_formatters.py` | 修改 | `%`→`{}` |
| `src/gitingest/utils/git_utils.py` | 修改 | `%`→`{}`；**Phase 3**：探测超时可配置（默认 10s）、级别下调 |
| `.env` | 修改 | 新增日志配置项；**Phase 3**：移除相对日志路径、新增探测/慢请求阈值 |
| `README.md` | 修改 | 新增「📝 日志系统」章节；**Phase 3**：补充新配置项 |

**Phase 3 说明**：`src/server/middleware.py`（慢请求告警）、`src/server/query_processor.py`（`size` 单位修复、裁剪告警）、`src/server/main.py`（日志路径 cwd 无关化）。
