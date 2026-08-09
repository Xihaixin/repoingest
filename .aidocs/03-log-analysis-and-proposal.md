# Repoingest 日志系统 —— 运行期分析与优化提案

> 阶段：Phase 3 · 运行期分析 + 日志点提案
> 日期：2026-08-09
> 对应文档：`01-logging-system-design.md`、`02-implementation-log.md`
> 数据来源：用户提供的日志片段 + `src/src/logs/repoingest.log`（约 23KB 完整日志）

---

## 1. 运行期日志分析

### 1.1 问题清单

| # | 严重度 | 问题 | 根因 | 涉及位置 |
|---|--------|------|------|---------|
| L1 | 🔴 高 | **日志路径不一致**：本应写入 `src/logs/`，实际写入 `src/src/logs/` | `.env` 中 `REPOINGEST_LOG_FILE=src/logs/repoingest.log` 为**相对路径**，按进程工作目录（cwd）解析；且 `gitingest/config.py:20` 在 import 阶段即 `load_dotenv(override=True)`，早于 `main.py` 读取该变量 | `main.py`、`.env` |
| L2 | 🔴 高 | **线程池内日志丢失请求上下文**：`Repository cloned successfully to ...` 一行无 `rid` | `clone_repo` 用 `run_in_executor` 执行 `_clone_repo_sync`，工作线程不继承 `contextvars`，Loguru `contextualize` 上下文丢失 | `cloning.py:92` |
| L3 | 🟠 中 | **60s 探测超时拖垮请求**：单请求总耗时 66.2s，其中 60.97s 浪费在"仓库是否存在"探测上，而真正的 clone 仅 4.2s | `git_utils.py` 硬编码 `aiohttp.ClientTimeout(total=60)` | `git_utils.py:70` |
| L4 | 🟠 中 | **兜底日志级别不当**：`Repository existence check failed ... (will attempt clone anyway)` 是**预期内兜底**却用 `ERROR` | 级别语义选择错误 | `cloning.py:70` |
| L5 | 🟢 低 | **噪音**：`Git is available in the environment.` 每个请求都输出 `INFO` | 级别过高 | `git_utils.py:221` |
| L6 | 🟢 低 | **日志内容错误**：`Query succeeded [... | size=0kb]` | `_build_query_details` 按"字节"计算 `int(max_file_size/1024)`，而 `max_file_size` 实为 **KB**（滑杆 0-500） | `query_processor.py:20` |
| L7 | 🟢 低 | **缺失关键事件**：内容被裁剪（>300k 字符）无任何记录；慢请求（>30s）无告警 | 无对应日志点 | `query_processor.py:107`、`middleware.py` |

### 1.2 逐条取证

**L1 —— 路径不一致（截图自完整日志首行）**

```text
INFO | repoingest.server | Logging to file: ...\repoingest\src\logs\repoingest.log   # 启动时打印
# 但实际日志被写到 ...\repoingest\src\src\logs\repoingest.log                       # 磁盘事实
```

根因链：`.env` 中相对值 `src/logs/repoingest.log` → 用户从 `src/` 目录启动进程 → cwd 为 `...\repoingest\src` → 相对路径拼成 `...\repoingest\src\src\logs`。

**L2 —— 上下文丢失（同一请求，两行对比）**

```text
23:07:29.285 | INFO  | repoingest.cloning | rid=2da91e000203 | ... | Starting clone for https://github.com/xihaixin/patlas
23:07:29.486 | INFO  | repoingest.cloning | Repository cloned successfully to D:\tmp\gitingest\...   ← 无 rid！
23:07:29.487 | INFO  | repoingest.cloning | rid=2da91e000203 | ... | Clone completed in 4.20s ...
```

`_clone_repo_sync` 内所有日志（含 `Repository cache found`、`Sparse checkout`、`Checked out commit`）都会丢失 rid，破坏"单请求全链路"的溯源承诺。

**L3 —— 66 秒的请求**（用户反馈重点）

```text
23:06:24.238 | INFO  | ... | Probing repository existence via Git smart protocol: .../info/refs...
23:07:25.218 | ERROR | ... | Timeout probing repository [...] (60.97s, timeout=60s)   ← 空耗 60s
23:07:25.219 | ERROR | ... | Repository existence check failed ... (will attempt clone anyway)
23:07:25.285 | INFO  | ... | Starting clone for ...
23:07:29.487 | INFO  | ... | Clone completed in 4.20s ...
23:07:30.388 | INFO  | ... | Request completed | status=200 | duration=66167.7ms      ← 全程 66s
```

探测预检的价值是"快速发现仓库不存在"，但 60s 超时让其反成拖累；且 clone 本身失败时（exit 128）几秒内即有清晰报错，预检并非必需。

**L4 —— 级别误用**

`will attempt clone anyway` 是**已处理的可恢复兜底**，ERROR 会触发误报/告警疲劳。应降为 WARNING。

**L5 —— 噪音**

`Git is available in the environment.` 每次请求都输出。应降为 DEBUG（或在启动时只打一次）。

**L6 —— `size=0kb`**

`max_file_size` 为滑杆值（KB），`int(243/1024)=0` → 打印 `size=0kb`，误导排查。应直接显示 KB。

**L7 —— 缺失事件**

- `query_processor.py:107`：content 超过 `MAX_DISPLAY_SIZE` 被裁剪时**静默**，用户看到截断内容却无日志可循。
- 无"慢请求"告警：66s 请求只显示为普通 INFO。

---

## 2. 日志记录点与记录信息提案

### 2.1 级别规范（统一语义）

| 级别 | 语义 | 判定 |
|------|------|------|
| `ERROR` / `exception` | **不可恢复**或**必须人工介入**的失败 | clone 失败、5xx、未处理异常 |
| `WARNING` | 预期内但需注意；**已兜底恢复** | 探测超时后继续 clone、内容裁剪、慢请求、限流、仓库不存在/私有 |
| `INFO` | 请求/任务级**关键里程碑** | 请求完成、clone 开始/结束、查询成功/失败、探测目标 |
| `DEBUG` | 细粒度过程 | 每文件节点、git 命令细节、git 可用性 |

### 2.2 日志点评估表（保留/调整/新增）

**RequestLoggingMiddleware**

| 日志点 | 级别 | 内容 | 处置 |
|--------|------|------|------|
| Request started | DEBUG | — | 保留 |
| Request completed | INFO | `status={} duration={:.1f}ms` | 保留 |
| **慢请求** | **WARNING** | `Slow request completed status={} duration={:.1f}ms threshold={}ms` | **新增**（`duration > REPOINGEST_SLOW_REQUEST_MS`，默认 30000） |
| Unhandled exception | ERROR | 完整 traceback | 保留 |

**git_utils.check_repo_exists**

| 日志点 | 级别 | 处置 |
|--------|------|------|
| `Probing repository existence ...` | INFO | 保留 |
| `Repository probe responded [...]` | DEBUG | 保留 |
| `Repository EXISTS / returned 302 / access denied / NOT FOUND` | INFO / WARNING | 保留 |
| `Rate limited while probing` | ERROR | 保留（真实异常） |
| `Git host server error` / `Unexpected HTTP status` | ERROR | 保留 |
| `Timeout probing repository [...] (…, timeout={}s)` | ERROR → **WARNING** | **级别下调**（会继续 clone）+ 超时值改读配置 |
| `Connection failed probing` / `HTTP client error probing` | ERROR | 保留 |

**git_utils**

| 日志点 | 级别 | 处置 |
|--------|------|------|
| `Git is available in the environment.` | INFO → **DEBUG** | **级别下调**（噪音） |
| `Git check failed` | ERROR（exception） | 保留 |
| `Fetching remote branch list ...` / `Fetched N branches ...` | INFO | 保留 |
| `Parsed N branches` / `Raw ls-remote output` | DEBUG | 保留 |
| `Git ls-remote failed` | ERROR（exception） | 保留 |

**cloning**

| 日志点 | 级别 | 处置 |
|--------|------|------|
| `Failed to create parent directory ...` | ERROR | 保留 |
| `Repository not found: {}` | ERROR | 保留 |
| `Repository existence check failed ... (will attempt clone anyway)` | ERROR → **WARNING** | **级别下调** |
| `Starting clone for ...` | INFO | 保留 |
| `Clone completed in {:.2f}s for ...` | INFO | 保留 |
| `Repository cache found at ...` | INFO | 保留 |
| `Sparse checkout configured / Checked out commit / Repository cloned successfully` | INFO | 保留 + **修复 rid**（上下文传播） |
| `Git operation FAILED ...` | ERROR | 保留 |

**query_processor**

| 日志点 | 级别 | 处置 |
|--------|------|------|
| `Query failed [...]` | ERROR（exception） | 保留 |
| `Query succeeded [...] | tokens=` | INFO | 保留 + **修复 size 单位** |
| **内容裁剪** | **WARNING** | **新增**：`Content cropped to N characters (full digest available via download)` |

**routers_utils / server_utils**：现有日志点级别均已合理，保留。

---

## 3. 设计

### 3.1 日志路径解析（修复 L1）

- 定义 `_PKG_DIR = Path(__file__).resolve().parent.parent`（即 `src/` 代码目录）作为相对基准。
- 默认日志目录：`_PKG_DIR / "logs"`（绝对路径，**与 cwd 无关**）。
- 若 `REPOINGEST_LOG_FILE` 为相对路径 → 相对 `_PKG_DIR` 解析为绝对路径；绝对路径原样使用。
- `.env` 中**移除** `REPOINGEST_LOG_FILE` 的相对值（保留为注释说明），恢复"原来项目"写入 `src/logs/repoingest.log` 的行为。

### 3.2 请求上下文跨线程传播（修复 L2）

`cloning.clone_repo` 中：

```python
ctx = contextvars.copy_context()
await loop.run_in_executor(None, lambda: ctx.run(_clone_repo_sync, config))
```

`_clone_repo_sync` 内所有日志（缓存命中、sparse、commit、cloned）恢复携带 `rid`。

### 3.3 探测超时（修复 L3）

- 新增环境变量 `REPOINGEST_PROBE_TIMEOUT`，默认 **10** 秒（原 60s）。
- `check_repo_exists` 读取该值构造 `aiohttp.ClientTimeout(total=...)`。
- 超时日志输出**实际超时值**（不再硬编码 60s）。

### 3.4 级别与内容修订（L4–L6）

- `cloning.py`：`will attempt clone anyway` → WARNING。
- `git_utils.py`：`Git is available` → DEBUG；`Timeout probing` → WARNING。
- `query_processor._build_query_details`：`max_file_size` 已是 KB，直接打印 `size={max_file_size}kb`（默认值 50 时省略）。

### 3.5 新增日志点（L7）

- 中间件慢请求告警：`duration > REPOINGEST_SLOW_REQUEST_MS`（默认 30000）→ WARNING。
- `query_processor` 内容裁剪 → WARNING。
- 新增环境变量 `REPOINGEST_SLOW_REQUEST_MS`。

### 3.6 环境变量汇总（新增/变更）

| 变量 | 默认 | 说明 |
|------|------|------|
| `REPOINGEST_PROBE_TIMEOUT` | `10` | 仓库存在性探测超时（秒） |
| `REPOINGEST_SLOW_REQUEST_MS` | `30000` | 慢请求告警阈值（毫秒） |
| `REPOINGEST_LOG_FILE` | （未设） | 日志路径；相对值相对代码 `src/` 目录解析 |

---

## 4. 实施计划

| 阶段 | 内容 |
|------|------|
| A | 修复日志路径（`main.py` + `.env` + `README`） |
| B | 修复上下文跨线程传播（`cloning.py`） |
| C | 级别与内容修订（`cloning.py`、`git_utils.py`、`query_processor.py`） |
| D | 探测超时可配置 + 默认 10s（`git_utils.py`） |
| E | 新增日志点：慢请求告警 + 内容裁剪（`middleware.py`、`query_processor.py`） |
| F | 验证：冒烟测试（慢路径 + 失败路径 + 线程上下文）+ black 检查 |
| G | 更新 `.aidocs` 实施日志 |

---

## 5. 验收标准

1. 无论从哪个 cwd 启动，日志均写入 `src/logs/repoingest.log`。
2. 全链路日志（含 `_clone_repo_sync` 内）均携带同一 `rid`。
3. 探测超时默认 10s，单请求最坏耗时显著下降。
4. `Query succeeded` 中 `size` 单位正确；内容被裁剪、慢请求有对应 WARNING。
5. 兜底场景使用 WARNING，不再误报 ERROR。
