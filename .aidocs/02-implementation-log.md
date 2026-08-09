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

---

# Phase 3 · 运行期分析优化（2026-08-09）

> 分析文档：`03-log-analysis-and-proposal.md`

## 问题清单（对应阶段 A–E）

| # | 问题 | 修复 |
|---|------|------|
| L1 | 日志路径 cwd 相关，写入 `src/src/logs/` | Stage A |
| L2 | `run_in_executor` 线程内日志丢失 `rid` | Stage B |
| L3 | 60s 探测超时拖垮请求（66s） | Stage D |
| L4 | 兜底日志误用 ERROR | Stage C |
| L5 | `Git is available` 每请求 INFO | Stage C |
| L6 | `size=0kb` 单位错误 | Stage C |
| L7 | 内容裁剪/慢请求无日志 | Stage E |

## Stage A · 日志路径 cwd 无关化

**文件**：`src/server/main.py`、`.env`、`README.md`

- 新增 `_PKG_DIR = Path(__file__).resolve().parent.parent`（代码 `src/` 目录）作为相对基准。
- `REPOINGEST_LOG_FILE` 相对值 → 相对 `_PKG_DIR` 解析为绝对路径；绝对路径原样使用；未设则用 `_PKG_DIR/logs/repoingest.log`（绝对，cwd 无关）。
- `.env` 移除相对值 `REPOINGEST_LOG_FILE=src/logs/repoingest.log`（保留注释说明 + 新增 `REPOINGEST_PROBE_TIMEOUT`、`REPOINGEST_SLOW_REQUEST_MS`）。

**验证**：从 `src/` cwd 启动 `import server.main`，日志写入 `src/logs/`（不再是 `src/src/logs/`）。

## Stage B · 请求上下文跨线程传播

**文件**：`src/gitingest/cloning.py`

```python
ctx = contextvars.copy_context()
await loop.run_in_executor(None, lambda: ctx.run(_clone_repo_sync, config))
```

`_clone_repo_sync` 内日志（缓存命中、sparse、commit、cloned）恢复携带 `rid`。

**验证**：直接测试证明 `contextvars.copy_context().run()` 后线程内日志含 `rid`。

## Stage C · 级别与内容修订

**文件**：`cloning.py`、`git_utils.py`、`query_processor.py`

- `Repository existence check failed ... (will attempt clone anyway)`：ERROR → **WARNING**（已兜底恢复）。
- `Timeout probing repository`：ERROR → **WARNING**；超时值改读实际配置。
- `Git is available in the environment.`：INFO → **DEBUG**。
- `_build_query_details`：`max_file_size` 实为 KB，直接显示 `size={max_file_size}kb`，默认 50 省略（修复 `size=0kb`）。

## Stage D · 探测超时可配置

**文件**：`git_utils.py`、`.env`、`README.md`

- 新增 `_probe_timeout()`，读取 `REPOINGEST_PROBE_TIMEOUT`（默认 **10s**，原硬编码 60s）。
- 超时日志输出实际超时值：`(2.02s, timeout=2.0s)`。

**验证**：`REPOINGEST_PROBE_TIMEOUT=2` 时探测 2.02s 后 WARNING 并抛出 `RuntimeError`，`cloning` 捕获后 WARNING 兜底。

## Stage E · 新增日志点

**文件**：`src/server/middleware.py`、`query_processor.py`

- 中间件慢请求告警：`duration >= REPOINGEST_SLOW_REQUEST_MS`（默认 30000ms）→ WARNING `Slow request completed | status={} | duration={:.1f}ms | threshold={:.0f}ms`。
- 内容裁剪告警：content > `MAX_DISPLAY_SIZE` → WARNING `Content cropped for {}: {} -> {} characters`。

## Stage F · 验证结果

1. `_build_query_details` 单元验证：`243 → size=243kb`；`50 → 省略` ✅
2. 日志路径 cwd 无关（从 `src/` 启动仍写 `src/logs/`）✅
3. 慢请求 WARNING 触发（阈值 1ms）✅
4. 失败请求全链路含 `rid`（probe → clone fail → Query failed → 500）✅
5. 探测超时：2s 配置生效，WARNING + 实际超时值 ✅
6. `black --check`：`middleware.py`、`logger.py`（新增/重写文件）通过 ✅

## 遗留事项 / 建议（Phase 3）

1. **可进一步优化**：可评估完全移除仓库存在性预检（clone 本身对不存在仓库 2-3s 内即报 exit 128），或将探测与 clone 并发执行。
2. **部署提醒**：部署环境若设置 `REPOINGEST_LOG_FILE`，请使用绝对路径或相对代码 `src/` 目录的路径（不再依赖 cwd）。
3. **清理**：`src/src/` 目录为修复前的遗留（cwd 错误产生），确认后可手动删除。

---

# Phase 4 · 静态资源请求去噪（2026-08-09）

## 问题

`/static/*` 静态资源（SVG/JS/icon/favicon）每次页面加载拉取十几个，每条都生成 `rid` 并输出 INFO 访问日志，造成日志混乱与臃肿；且此类请求几乎不会失败、溯源价值趋近于零。

## 方案

**文件**：`src/server/middleware.py`

- 新增 `_QUIET_PREFIXES = ("/static/",)` 与 `_should_trace(path)`。
- `dispatch` 中对命中前缀的请求**直接透传**：不生成 `rid`、不绑定上下文、不输出 `Request started/completed`（含慢请求告警），仅在 DEBUG 级别输出一行 `Static asset request: {path}`（默认 INFO 级别完全不可见）。

## 验证（TestClient，INFO 级别）

| 请求 | X-Request-ID | INFO 访问日志 |
|------|--------------|---------------|
| `GET /static/svg/github-star.svg` | **None** | 无 `Request completed`（仅 DEBUG `Static asset request`） |
| `GET /health` | `fe3d5d85bddf` | 有（含 rid） |
| `GET /` | `57efffb8b2e2` | 有（含 rid） |

`black --check` 通过。

> 权衡说明：静态资源失败（罕见 404）不再记录，但浏览器侧即可自明，对排查影响可忽略；如需追踪可在 `_QUIET_PREFIXES` 中移除对应前缀。

---

# Phase 5 · Home 落地页 + 多语言（i18n）（2026-08-09）

> 设计文档：`04-home-and-i18n-design.md`；分支：`feat/home-and-i18n`

## Stage 1 · i18n 框架

**新增**：`src/server/i18n.py`、`src/server/i18n/en.json`、`src/server/i18n/zh-CN.json`

- `LANGUAGES = {"en", "zh-CN"}`，`DEFAULT_LANGUAGE = "zh-CN"`（对齐国内推广）。
- `translate(key, lang)`：缺 key 回退 en → 原 key。
- `get_language(request)`：`?lang=` → cookie → `Accept-Language`（zh*→zh-CN、en*→en）→ 默认。
- `i18n_context(request)`：注入 `request/lang/t/messages`（messages = en 合并当前语言，供 JS 使用）。

**修改**：`src/server/server_config.py` 新增 `render_template(name, request, **context)`，统一注入 i18n 上下文并渲染，替代散落的 `templates.TemplateResponse`。

## Stage 2 · 路由拆分

**修改**：`src/server/routers/index.py`

| 路由 | 页面 |
|------|------|
| `GET /` | `home.jinja`（落地页） |
| `GET /app` | `index.jinja`（工具），支持 `?repo=` 预填 |
| `GET /lang/{code}?next=` | 写 `lang` cookie（HttpOnly、max-age 1 年）后 302 回 `next`（`_safe_next` 防开放重定向） |

## Stage 3 · 全局骨架

**修改**：`base.jinja`（`<html lang>`、meta 标题/描述本地化、内联 `window.I18N = {messages}` + `I18N.t()`）、`navbar.jinja`（新增「首页/工具」链接 + 语言切换 `<select>`，沿用原视觉）、`footer.jinja`（版本/Chrome/Python/Discord 文案本地化）。

## Stage 4 · Home 落地页

**新增**：`src/server/templates/home.jinja`

- Hero（复用 `.landing-page-title` + sparkles）+ 主 CTA → `/app`。
- 工作原理三步卡片（复用偏移阴影卡片风）。
- 功能特性网格、快速开始、示例仓库按钮（链到 `/app?repo=`）、二次 CTA。
- 全部复用原 Tailwind 配色/类，未引入新 UI 框架。

## Stage 5 · 工具页翻译

**修改**：`index.jinja`、`git.jinja`、`components/git_form.jinja`（表单各控件、PAT 提示、示例）、`components/result.jinja`（Loading/Summary/Directory/Content/Copy/Download）。

## Stage 6 · JS 国际化

**修改**：`src/static/js/utils.js`

- `Processing...`、`Error(s):`、`An error occurred.`、`Copied!`、`Failed to copy`、`Downloading...`、`Downloaded!`、`Summary:` 等改用 `I18N.t('js.*')`。
- 新增 `translateError()`：对常见后端英文错误（repository not found、invalid token）做前缀匹配翻译（最佳努力）。

## Stage 7 · dynamic 路由 + 验证

**修改**：`dynamic.py` 改用 `render_template`（slug 页同样获得 i18n 上下文）。

**验证（TestClient）**：

| 用例 | 结果 |
|------|------|
| `/`（en） | 200，含 Prompt-friendly/How it works |
| `/?lang=zh-CN` | 200，含 对提示词友好/工作原理/快速开始 |
| `/app`（en/zh） | 200，含 Ingest/生成摘要 |
| `/user/repo`（en/zh） | 200，slug 直达正常 |
| `/lang/zh-CN?next=/app` | 302 + `Set-Cookie: lang=zh-CN` |
| cookie 持久化 / Accept-Language zh | 均命中中文 |
| `/app?repo=...` 预填 | 输入框 value 正确 |
| `window.I18N` 注入 | 存在，含 `form.submit` 键 |

`black` 格式化通过（i18n.py / server_config.py / index.py / dynamic.py）。

## 遗留事项 / 建议（Phase 5）

1. **后端错误全量 i18n**：当前 API 错误消息保持英文，前端仅对常见错误做最佳努力翻译；如需彻底中文，可改为"错误码化 + 前端映射"。
2. **更多语言**：新增语言只需复制 `en.json` 并翻译，然后在 `LANGUAGES` 与 navbar `<select>` 增加条目。
3. **SEO**：`og:image` 仍为英文默认图，后续可补充中文版宣传图。
4. **注意**：`GET /api`（`api.jinja`）模板不存在为**既有问题**（非本次引入），建议后续修复或改用 `swagger_ui.jinja`。
