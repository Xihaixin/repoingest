# Repoingest —— PostHog 用户行为分析设计方案（配置化 + uid 身份打通）

> 阶段：Phase 7 · 分析与设计
> 域名：`repoingest.top`
> 平台：PostHog Cloud（免费版）
> 日期：2026-10-04
> 状态：设计中（暂未修改代码）

---

## 1. 背景与目标

### 1.1 现状

| 项 | 现状 | 位置 |
|----|------|------|
| 前端 SDK | 已内嵌 PostHog 官方 loader（`array.js` 引导器） | `src/static/js/posthog.js` |
| 初始化 | 在脚本内**硬编码** project token 与 host，`person_profiles: 'always'` | `src/static/js/posthog.js:72` |
| 加载方式 | 所有页面通过 base 模板全局加载 | `src/server/templates/base.jinja:74` |
| 自定义事件 | **无**，仅有默认 `$pageview` + autocapture | — |
| 后端埋点 | **无**，未引入 Python SDK | — |
| 用户身份 | 无；PostHog 使用自生成匿名 id（存浏览器 localStorage） | — |
| 已有可用身份 | `repoingest_uid` cookie（`crypto.randomUUID()`，非 HttpOnly，1 年有效） | `src/static/js/utils.js:157`、`src/server/job_store.py` |

### 1.2 目标

1. **配置化**：project token / host / 开关从硬编码改为环境变量 + 模板注入，支持多环境（本地/生产/未来自托管）。
2. **身份打通**：以 `repoingest_uid` 作为 PostHog `distinct_id`，使**同一个浏览器**的前端页面行为与后端任务事件归属到同一身份，从而构建端到端漏斗。
3. **可控降噪**：免费版事件额度有限，明确采集边界，避免无意义事件与隐私泄露。
4. **失败隔离**：分析系统任何异常都不得影响主业务（摄取流程）。

### 1.3 非目标

- 不做用户注册/登录体系（本项目无账号系统）。
- 不做跨设备身份识别（uid 是浏览器级，清 cookie 即新身份）。
- 不采集仓库内容、私有 token、完整私有仓库 URL 等敏感数据。

---

## 2. 为什么用 `repoingest_uid` 作为 distinct_id

### 2.1 核心矛盾

PostHog 前端默认生成的匿名 `distinct_id` 只存在于**浏览器**（localStorage/cookie `ph_*_posthog`），而真正有价值的业务结果（任务成功/失败/耗时）发生在**服务端后台任务**。后端拿不到浏览器 localStorage，因此默认情况下前后端是两条互不相干的身份链。

### 2.2 为什么 uid 是唯一合适的桥

`repoingest_uid` 是目前**唯一同时被浏览器 JS 与 FastAPI 服务端读写**的值：

- 前端：`getCookie('repoingest_uid')` / `ensureUid()`（`utils.js:143-168`）。
- 后端：`request.cookies.get("repoingest_uid", "")`（`ingest.py:47`、`jobs.py:20`）。
- 语义已一致：任务本身就是按 uid 归属的（`job_store.py` 的 `uid` 字段）。

因此把 uid 直接作为 PostHog 的 `distinct_id`，前后端天然对齐，无需额外传递机制。

### 2.3 方案对比

| 方案 | 前端可见 | 后端后台任务可见 | 是否引入新传递 | 结论 |
|------|:--------:|:---------------:|:--------------:|------|
| A. 用 PostHog 自生成匿名 id | 是 | 否（除非前端显式回传） | 需新建 header/字段 | 需额外同步逻辑 |
| B. 前端生成 id 存 localStorage 并回传后端 | 是 | 仅同步请求内 | 需改 API 协议 | 后台任务仍需持久化 |
| **C. 复用 `repoingest_uid` cookie** | **是** | **是（cookie 自动随请求）** | **无** | **采用** |

方案 C 无需新增任何接口字段，浏览器每次请求自动携带 cookie，后端后台任务也能从任务记录中取到 uid。

### 2.4 生命周期与边界

- **生成时机**：`ensureUid()` 在每次页面 `DOMContentLoaded` 时由 `utils.js` 调用（当前经 `loadRecentJobs` 间接触发），因此在首页与 `/app` 都会生成。
- **有效期**：1 年（`setCookie(..., 365)`）。
- **清 cookie**：视为新用户，新 uid → PostHog 新身份，属预期行为。
- **后端强制校验**：本项目**未对外开放 API**，API 仅供本站前端调用。因此无 `repoingest_uid` cookie 的请求（直接调用 API、爬虫、禁用 cookie）**一律拒绝、不做处理**，而非"跳过采集"（见 §6.4）。
- **一致性要求**：前端初始化 PostHog 必须在 `ensureUid()` **之后**，保证首个 `$pageview` 就带上 uid。

---

## 3. 身份打通总体架构

```
                    浏览器 (repoingest.top)
   ┌──────────────────────────────────────────────────────────┐
   │  utils.js  ensureUid() ──> cookie repoingest_uid=UUID     │
   │                                   │                       │
   │  analytics.js  bootstrap{distinctID: uid}                 │
   │        │                          │                       │
   │        ├─ posthog.capture(...) ──> PostHog Cloud          │
   │        │                                                  │
   │  fetch /api/ingest  ── 自动携带 cookie ──┐                │
   └──────────────────────────────────────────┼────────────────┘
                                               ▼
                        FastAPI（单进程，cookie 中的 uid）
   ┌──────────────────────────────────────────────────────────┐
   │  create_ingest_job: uid = cookies["repoingest_uid"]       │
   │        │                                                  │
   │        └─> job_store.create(uid, ...)                     │
   │                   │                                       │
   │  _run_job(job_id, uid)  ── posthog.capture(uid, event) ──>│──> PostHog Cloud
   └──────────────────────────────────────────────────────────┘
```

同一 uid 在 PostHog 中汇合为一条身份链：

```
$pageview ─┐
example_clicked ─┤
ingest_submitted ─┼─> distinct_id = <uid> ─> funnel: 访问 → 提交 → 完成
ingest_completed ─┘
```

---

## 4. 配置化设计

### 4.1 环境变量清单

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTHOG_ENABLED` | `0` | 总开关。`0` 时前后端均不采集（本地开发默认关闭，避免污染生产数据） |
| `POSTHOG_API_KEY` | 空 | PostHog **Project Token**（`phc_...`，公开可嵌入前端） |
| `POSTHOG_HOST` | `https://us.i.posthog.com` | 采集入口；未来自托管时改此值 |

> 说明：Project Token 是「可发布」密钥，设计上就允许出现在前端 HTML 中，**不是**秘密。真正的秘密是 Personal API Key（仅用于读取/管理 API），**绝不**引入本项目。配置化的目的是环境隔离与可替换，而非保密。

### 4.2 后端读取（`src/server/server_config.py`）

新增集中读取逻辑（与现有 `APP_VERSION` 等风格一致）：

```python
POSTHOG_ENABLED = os.getenv("POSTHOG_ENABLED", "0") == "1"
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")

def get_posthog_config() -> dict:
    return {
        "enabled": POSTHOG_ENABLED and bool(POSTHOG_API_KEY),
        "api_key": POSTHOG_API_KEY,
        "api_host": POSTHOG_HOST,
    }
```

### 4.3 模板注入（`src/server/templates/base.jinja`）

在注入 `window.I18N` 附近注入配置，**仅当启用时输出**（关闭时不留空对象、不加载脚本）：

```jinja
{% if posthog and posthog.enabled %}
<script>
    window.POSTHOG_CONFIG = {
        api_key: {{ posthog.api_key | tojson }},
        api_host: {{ posthog.api_host | tojson }},
    };
</script>
<script defer src="/static/js/posthog.js"></script>
<script defer src="/static/js/analytics.js"></script>
{% endif %}
```

`posthog` 变量通过 `server_config.render_template` 统一并入上下文（该函数是所有页面的单一注入点），确保 `/`、`/app` 等页面都能取到。`main.py` 中直接 `TemplateResponse("api.jinja", ...)` 的路径需一并补充（见 §9 影响面）。

### 4.4 前端读取（新增 `src/static/js/analytics.js`）

- 从 `window.POSTHOG_CONFIG` 读取配置；不存在则**直接 return**，所有 `track()` 调用降级为 no-op。
- 职责：确保 uid → 初始化 → 暴露 `window.track()`。
- `posthog.js` 回归为**纯 loader**（保留现有 array.js 引导器），删除其中硬编码的 `posthog.init(...)`。

### 4.5 关闭时的行为

- `POSTHOG_ENABLED=0` 或 key 为空：模板不输出配置、不加载 `posthog.js`/`analytics.js`；后端 `analytics` 模块 `enabled=False`，`capture()` 直接返回。
- 保证：关闭分析**不改变**任何业务行为与页面渲染。

---

## 5. 前端实现设计

### 5.1 脚本职责拆分

| 文件 | 变更 | 职责 |
|------|------|------|
| `static/js/posthog.js` | 修改 | 仅保留官方 loader（`array.js` 引导），删除硬编码 init |
| `static/js/analytics.js` | **新增** | 读配置、`ensureUid()`、bootstrap、`window.track()` 封装 |
| `static/js/utils.js` | 修改 | 在业务关键点调用 `window.track(...)`（可选，见 5.4） |
| `templates/base.jinja` | 修改 | 注入配置、按开关加载脚本 |

### 5.2 初始化与身份绑定

关键点：**用 `bootstrap.distinctID` 直接设定匿名 id，而非 `posthog.identify()`**。

```js
// analytics.js（示意）
(function () {
    const cfg = window.POSTHOG_CONFIG;
    if (!cfg || !cfg.api_key) { return; }

    const uid = ensureUid();               // utils.js 提供，先于 init
    posthog.init(cfg.api_key, {
        api_host: cfg.api_host,
        bootstrap: { distinctID: uid },    // 匿名身份即 uid，不触发 person profile
        person_profiles: 'identified_only',
        autocapture: true,                 // MVP 保留；额度紧张时再关
        capture_pageview: true,
        disable_session_recording: true,   // 暂不开会话回放
    });

    window.track = function (event, props) {
        try { posthog.capture(event, Object.assign({}, props)); } catch (e) {}
    };
})();
```

- `bootstrap.distinctID` 的好处：不调用 `identify`，因此 `person_profiles:'identified_only'` 下**不会**为匿名访客创建 person profile，节省免费额度、降低隐私面。
- `ensureUid()` 必须在 init 之前执行，确保首个 `$pageview` 携带 uid。
- 现有 `person_profiles:'always'` 改为 `'identified_only'`。

### 5.3 加载顺序

`base.jinja` 中脚本为 `defer`，按文档顺序执行。建议顺序：

```
index.js → utils.js（提供 ensureUid/getCookie）→ posthog.js（loader）→ analytics.js（init + track）
```

`utils.js` 定义函数后 `analytics.js` 才可调用，顺序不可颠倒。

### 5.4 前端事件与挂点

| 事件 | 触发点 | 建议属性 |
|------|--------|---------|
| `example_clicked` | `index.js submitExample()`（首页示例仓库） | `repo_host` |
| `language_switched` | 语言切换入口（`navbar`/`/lang/{code}`） | `lang` |
| `private_repo_toggled` | `git_form.js toggleAccessSettings()` | `enabled` |
| `ingest_submitted` | `utils.js handleSubmit()` 收到 202 后 | `job_id`、`repo_host`、`pattern_type`、`has_token`、`max_file_size_kb` |
| `digest_copied` | `utils.js copyFullDigest()` | `job_id` |
| `digest_downloaded` | `utils.js downloadFullDigest()` | `job_id` |

> 成功/失败结果**不在前端采集**（由后端权威采集，见 §6），避免与后端重复计数。前端只采集「用户意图 + UI 动作」。`ingest_submitted` 携带 `job_id`，用于在 PostHog 中与后端 `ingest_completed` 按 job 关联。

### 5.5 降级

`track()` 用 try/catch 包裹；PostHog 脚本被广告拦截器屏蔽时 `window.posthog` 可能不存在，所有调用静默失败，不影响提交/轮询等业务。

---

## 6. 后端实现设计

### 6.1 依赖

- `pyproject.toml` 新增 `posthog`（建议用 `uv add posthog` 同步 `uv.lock`）。
- 使用官方 `posthog-python` 的 `Posthog` 客户端（默认后台线程异步批量发送）。

### 6.2 新增 `src/server/analytics.py`

统一封装，业务代码只调用 `capture(...)`：

```python
# 示意
from posthog import Posthog
from server.server_config import POSTHOG_ENABLED, POSTHOG_API_KEY, POSTHOG_HOST

_client = None

def init() -> None:
    global _client
    if POSTHOG_ENABLED and POSTHOG_API_KEY:
        _client = Posthog(POSTHOG_API_KEY, host=POSTHOG_HOST)

def shutdown() -> None:
    if _client:
        _client.shutdown()   # flush 队列，避免退出时丢事件

def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    if not _client or not distinct_id:
        return
    try:
        _client.capture(distinct_id, event, properties or {})
    except Exception:
        pass  # 分析失败绝不影响业务
```

### 6.3 生命周期接入（`src/server/server_utils.py`）

在现有 `lifespan` 中初始化与关闭：

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    analytics.init()
    ...
    yield
    ...
    analytics.shutdown()
```

### 6.4 uid 强制校验（无 uid 的 API 请求一律拒绝）

**决策**：本项目未对外开放 API，API 仅服务于本站前端，而本站前端必然携带 `repoingest_uid` cookie。因此把 uid 作为 API 的准入凭证：**请求中取不到 uid 即拒绝，不进入任何业务处理**。

实现方式：新增 FastAPI 依赖 `require_uid(request) -> str`，缺失时抛 `HTTPException(400, detail="missing uid")`，挂载到所有需要 uid 的 API 路由：

| 路由 | 处理 |
|------|------|
| `POST /api/ingest` | 强制 uid |
| `POST /{full_path:path}`（无 JS 表单回退） | 强制 uid（见下方说明） |
| `GET /api/jobs` | 强制 uid |
| `GET /api/jobs/{job_id}` | 强制 uid（当前实现按 uid 归属，此处改为硬性要求） |

说明与影响：
- 前端提交前会调用 `ensureUid()`（`utils.js:457`），cookie 必然存在，正常用户不受影响。
- **无 JS 表单回退**（`dynamic.py` 的 `POST /{full_path:path}`）依赖 JS 设置的 cookie；由于该回退本身已返回 JSON 而非 HTML（无 JS 场景实际不可用），一并要求 uid 不构成新的功能损失。
- 静态页面（`GET /`、`/app`、`/{owner}/{repo}`）不要求 uid，uid 由前端 `ensureUid()` 生成。

### 6.5 uid 传递到后台任务

当前 `_run_job(job_id, ingest_request)` 没有 uid，而后台任务在请求结束后运行，拿不到 `request`。取法：

1. **推荐**：在 `create_ingest_job` 中把已校验的 uid 作为参数传入 `_run_job(job_id, uid, ingest_request)`；`spawn(...)` 相应调整。
2. 备选：`_run_job` 内从 `job_store.get(job_id)["uid"]` 读取（任务记录已存 uid）。

由于入口已强制 uid，`_run_job` 中的 uid 必非空，无需再做空值兜底。

### 6.6 后端事件与挂点

| 事件 | 挂点 | 建议属性 |
|------|------|---------|
| `ingest_started` | `_run_job` 开头 | `job_id`、`repo_host`、`pattern_type`、`max_file_size_kb`、`has_token` |
| `ingest_completed` | `_run_job` 成功分支 | `job_id`、`duration_ms`、`file_count`、`token_count`、`tree_bytes` |
| `ingest_failed` | `_run_job` 异常分支 | `job_id`、`duration_ms`、`error_type`（异常类名，非原始堆栈） |

- 计时：`_run_job` 内 `time.perf_counter()` 起止。
- `file_count` / `token_count`：从 `process_query` 返回的 `IngestSuccessResponse` 推导（`summary` 中已有 token 估算；文件数可由 `tree`/`content` 统计或后续在结果模型补充字段）。
- 属性中的 `repo_host`：仅保留主机名（如 `github.com` / `gitee.com`），**不**上报完整 URL 与私有路径。

### 6.7 失败隔离

`analytics.capture` 内部吞掉所有异常；`init/shutdown` 亦不抛错，确保 PostHog 故障时服务照常运行。

> 注意：`require_uid` 的拒绝是**业务准入**，与"分析失败隔离"是两回事——前者按设计拒绝非法请求，后者保证分析组件异常不影响合法请求。

---

## 7. 事件字典（前后端统一）

| 事件 | 来源 | 时机 | 关键属性 | 用途 |
|------|:----:|------|---------|------|
| `$pageview` | 前端 | 页面浏览（自动） | 默认 | 流量、来源 |
| `example_clicked` | 前端 | 点击示例仓库 | `repo_host` | 入口偏好 |
| `language_switched` | 前端 | 切换语言 | `lang` | i18n 使用 |
| `private_repo_toggled` | 前端 | 勾选私有仓库 | `enabled` | 私有场景占比 |
| `ingest_submitted` | 前端 | 提交成功拿到 job_id | `job_id`,`repo_host`,`repo_slug`,`pattern_type`,`has_token` | 漏斗起点 |
| `digest_copied` | 前端 | 复制完整摘要 | `job_id` | 结果价值验证 |
| `digest_downloaded` | 前端 | 下载完整摘要 | `job_id` | 结果价值验证 |
| `ingest_started` | 后端 | 后台任务开始 | `job_id`,`repo_host`,`repo_slug`,`pattern_type` | 权威开始 |
| `ingest_completed` | 后端 | 任务成功 | `job_id`,`repo_slug`,`duration_ms`,`file_count`,`token_count` | 漏斗终点、性能 |
| `ingest_failed` | 后端 | 任务失败 | `job_id`,`repo_host`,`repo_slug`,`duration_ms`,`error_type` | 失败归因 |

**核心漏斗**：`$pageview(/app)` → `ingest_submitted` → `ingest_completed`（按 `job_id` 关联前后端）。

---

## 8. 隐私、合规与免费版约束

### 8.1 绝不上报（硬性红线）

- `token`（GitHub PAT）——任何情况下不得作为属性。
- 仓库文件内容、`summary`/`tree`/`content` 正文。
- 完整仓库 URL 与 URL 中的凭据（userinfo）——**只上报 `repo_slug`（`owner/repo`）与 `repo_host`**。
- 原始异常堆栈（只上报 `error_type` 类名）。
- 用户 IP 可通过 PostHog 的 geoip 设置按需关闭（`$geoip_disable` / 项目配置）。

### 8.2 脱敏规则

- `repo_host` 只取 host；必要时可对 host 做白名单归一化。
- `repo_slug` 只取 `owner/repo`（剥离协议、主机、`.git`、凭据与 token）。**这是有意采集的**：用户提交的仓库名本身是分析价值所在；但私有仓库名也会随之被记录，需在隐私政策中说明。
- `job_id` 是随机 hex，不敏感，可上报用于关联。
- uid 是随机 UUID 的持久标识符，属伪匿名数据；需在隐私政策中说明（免费版下建议同时提供 opt-out）。
- **URL 查询串脱敏**：本站存在 `/app?repo=<仓库URL>` 路径，而 `$pageview` 默认携带 `$current_url`。前端在 `sanitize_properties` 中剥掉 `$current_url` / `$referrer` 的查询串，避免仓库地址经 URL 泄露。
- 遵循浏览器 **Do Not Track / Global Privacy Control**：命中时前端不初始化 PostHog（基础 opt-out）。

### 8.3 免费版额度与降噪

- 免费版每月事件额度有限（以 PostHog 官网当前额度为准）。控制手段：
  - `person_profiles: 'identified_only'`，且用 bootstrap 避免生成 profile。
  - autocapture 与 Session Replay 均已**环境变量化**，可按额度随时开关而无需改代码：
    - `POSTHOG_AUTOCAPTURE=0` → 只保留显式事件与 `$pageview`。
    - `POSTHOG_SESSION_REPLAY=0`（默认关闭）。
  - 本地开发 `POSTHOG_ENABLED=0`。
- 数据区域：Cloud 采集端点默认 US（`https://us.i.posthog.com`）；若有合规要求需改用 EU 或自托管，仅需改 `POSTHOG_HOST`。

### 8.4 用户退出

- 提供 `posthog.opt_out_capturing()` 入口（如隐私设置开关），并将选择持久化到 cookie；后端可读取该 cookie 决定是否采集（可选增强，MVP 可暂不做）。

---

## 9. 影响面与实施步骤

### 9.1 变更文件清单（预计）

| 文件 | 类型 | 说明 |
|------|------|------|
| `pyproject.toml` / `uv.lock` | 修改 | 新增 `posthog` 依赖 |
| `.env` | 修改 | 新增 `POSTHOG_*` 配置项（含注释） |
| `src/server/server_config.py` | 修改 | 读取配置、`get_posthog_config()` |
| `src/server/analytics.py` | **新增** | 后端 PostHog 封装（init/capture/shutdown） |
| `src/server/server_utils.py` | 修改 | `lifespan` 初始化/关闭 |
| `src/server/routers/ingest.py` | 修改 | uid 传入 `_run_job`；埋点 start/completed/failed |
| `src/server/templates/base.jinja` | 修改 | 注入配置、按开关加载脚本 |
| `src/static/js/posthog.js` | 修改 | 去掉硬编码 init，仅保留 loader |
| `src/static/js/analytics.js` | **新增** | 前端 init + `track()` |
| `src/static/js/utils.js` / `index.js` / `git_form.js` | 修改 | 业务点埋点 |
| `README.md` / `README_EN.md` | 修改 | 新增 PostHog 配置说明（可选） |
| `.aidocs/README.md` | 修改 | 索引追加本文档 |

> 注意：`main.py` 中 `api_docs` 直接使用 `TemplateResponse("api.jinja", {"request": request})`，未走 `render_template`；若该模板继承 base，需同步补充 `posthog` 上下文（或统一改走 `render_template`）。

### 9.2 建议分阶段实施

1. **Phase A —— 配置化**：环境变量 + `server_config` + 模板注入 + `posthog.js` 去硬编码 + `analytics.js` 骨架。此阶段完成后行为与现状等价（仍无自定义事件），但已可开关。
2. **Phase B —— 前端身份与事件**：`bootstrap` uid + `ingest_submitted` 等 UI 事件。
3. **Phase C —— 后端事件**：引入 SDK、`analytics.py`、lifespan、`ingest_started/completed/failed`。
4. **Phase D —— 验证与调优**：按 §11「测试与验证步骤」核对事件与漏斗，观察额度消耗，决定是否关闭 autocapture/回放。

---

## 10. 验收标准

- [ ] `POSTHOG_ENABLED=0` 时，页面不加载 PostHog 脚本、无任何网络请求到 PostHog；服务功能不受影响。
- [ ] `POSTHOG_ENABLED=1` 且配置 key 后，PostHog 后台可看到带 `distinct_id=<uid>` 的 `$pageview`。
- [ ] 前端 `ingest_submitted` 与后端 `ingest_started/completed/failed` 在 PostHog 中 `distinct_id` 完全一致。
- [ ] 可用 `job_id` 在 PostHog 中把 `ingest_submitted` 与 `ingest_completed` 关联成漏斗。
- [ ] 事件属性中**不含** token、仓库正文、完整私有 URL、异常堆栈。
- [ ] 后端 PostHog 故障（网络不可达）时，摄取任务仍正常完成。
- [ ] `person_profiles` 不再对纯匿名访客创建 profile。

---

## 11. 测试与验证步骤

以下步骤用于验证 PostHog 是否正常工作、前后端身份是否打通，以及 API 准入校验是否生效。

### 11.1 前置：确认配置

`.env` 中三项必须与 PostHog 项目一致：

```
POSTHOG_ENABLED=1
POSTHOG_API_KEY=phc_xxx          # 必须与 PostHog 项目的 Project Token 一致
POSTHOG_HOST=https://us.i.posthog.com
```

> 建议：为避免污染正式数据，可另建一个「测试 Project」，用其 token 覆盖 `POSTHOG_API_KEY` 做本地验证。

### 11.2 启动服务与启动日志

在 `src` 目录下运行（与生产一致，`server.main:app`、`WorkingDirectory=src`）：

```powershell
.\.venv\Scripts\Activate.ps1
$env:POSTHOG_ENABLED="1"                 # 临时覆盖；也可直接改 .env
uvicorn server.main:app --host 127.0.0.1 --port 8001
```

**先看启动日志**：

- 正常：`repoingest.analytics | PostHog analytics enabled | host=https://us.i.posthog.com`
- 若为 `PostHog analytics disabled` → 开关或 key 未生效，后续验证无意义。

### 11.3 前端验证

打开 `http://127.0.0.1:8001/app`，然后：

1. **DevTools → Network**，过滤 `posthog`，应看到对 `https://us.i.posthog.com/e/`（或 `/i/v0/e/`）的 POST，状态 200。
   - 若出现 `ERR_BLOCKED_BY_CLIENT` → 广告拦截器屏蔽了 PostHog，需关闭。
2. **Console 身份核对**（两者必须相等）：
   ```js
   getCookie('repoingest_uid')      // utils.js 暴露的全局函数，例：'6f3a...'
   posthog.get_distinct_id()        // 必须与上面相同
   posthog.debug()                  // 打开 SDK 调试日志
   ```
3. **PostHog 后台 → Activity → Live events**（保持打开），操作页面观察事件：
   - 打开页面 → `$pageview`
   - 点示例仓库 → `example_clicked`
   - 提交 → `ingest_submitted`
   - 复制 / 下载结果 → `digest_copied` / `digest_downloaded`
   - 切换语言 → `language_switched`
   - 勾选私有仓库 → `private_repo_toggled`

### 11.4 后端验证

在 `/app` 提交一个真实仓库，然后在 Live events 观察：

- `ingest_started` → `ingest_completed`（成功）或 `ingest_failed`（失败）。
- 属性应含 `job_id`、`repo_host`、`duration_ms`、`file_count`、`token_count`（失败为 `error_type`）。
- 服务端日志同时出现 `Job started` / `Job completed` / `Job failed`。

### 11.5 前后端身份打通（关键）

在 PostHog 中按某个 **distinct_id / person** 过滤，确认同一 uid 下同时出现：

- 前端 `ingest_submitted`（属性含 `job_id`）
- 后端 `ingest_started` / `ingest_completed`（同一 `job_id`）

若两者 distinct_id 不一致 → cookie 未生成或 `bootstrap` 未生效。

### 11.6 漏斗端到端验证

PostHog → **Insights → Funnel**：

```
Step1  $pageview          (path = /app)
Step2  ingest_submitted
Step3  ingest_completed
```

能连成漏斗，即代表配置化 + 前后端埋点整体正常。

### 11.7 API 准入校验

```powershell
# 期望 400 missing uid
curl.exe -i http://127.0.0.1:8001/api/jobs
# 期望 200 {"jobs":[]}
curl.exe -i -H "Cookie: repoingest_uid=test-uid" http://127.0.0.1:8001/api/jobs
```

### 11.8 常见问题排查

| 现象 | 原因 / 处理 |
|------|-------------|
| 完全没有事件 | `POSTHOG_ENABLED` 非 1、key 不匹配、host 错、被广告拦截 |
| 前端事件 id 为随机 UUID 而非 uid | `ensureUid()` 未生效 / 配置未注入（确认页面含 `window.POSTHOG_CONFIG`） |
| 后端无事件 | 启动日志为 disabled；或 `analytics.capture` 内部异常被静默（临时给 `Posthog(..., debug=True)` 看日志） |
| 前后端 distinct_id 不同 | cookie 被清 / 域名不同；核对 `getCookie('repoingest_uid')` 与后端收到的 cookie |
| 事件延迟 | Python SDK 默认批量、约 5s flush；关闭服务时 `shutdown()` 会 flush，稍等几秒再看 |

### 11.9 埋点质量核对（HogQL）

在 PostHog → **Data management → SQL / Insights → SQL editor** 中执行以下查询核对数据质量。

1. 事件量分布（近 24h），确认自定义事件都在：
   ```sql
   SELECT event, count() AS cnt
   FROM events
   WHERE timestamp > now() - INTERVAL 24 HOUR
   GROUP BY event
   ORDER BY cnt DESC
   ```

2. 前后端身份一致性：任取一个 `job_id`，确认所有事件同一 `distinct_id`：
   ```sql
   SELECT distinct_id, event, properties.job_id, timestamp
   FROM events
   WHERE properties.job_id = '<job_id>'
   ORDER BY timestamp
   ```
   `ingest_submitted`（前端）与 `ingest_started` / `ingest_completed`（后端）的 `distinct_id` 必须完全一致。

3. 敏感字段自查（结果应均为 0）：
   ```sql
   SELECT
     countIf(properties.token IS NOT NULL)     AS token_leak,
     countIf(properties.content IS NOT NULL)   AS content_leak,
     countIf(properties.repo_url IS NOT NULL)  AS repo_url_leak,
     countIf(properties.$current_url LIKE '%?%') AS url_query_leak
   FROM events
   WHERE timestamp > now() - INTERVAL 24 HOUR
   ```

4. autocapture 噪声占比（用于决定是否关闭 `POSTHOG_AUTOCAPTURE`）：
   ```sql
   SELECT event, count() AS cnt
   FROM events
   WHERE timestamp > now() - INTERVAL 24 HOUR AND event LIKE '$%'
   GROUP BY event
   ORDER BY cnt DESC
   ```

> 代码侧审计结论：所有自定义事件属性仅含 `job_id`、`repo_host`、`repo_slug`、`pattern_type`、`max_file_size_kb`、`has_token`、`duration_ms`、`file_count`、`token_count`、`error_type`、`enabled`、`lang`，不含 token / 正文 / 完整 URL（含凭据）/ 堆栈。查询 3 中 `repo_url_leak` 应为 0（仓库标识只走 `repo_slug`）。

---

## 12. 生产部署配置与检查

`.env` **未纳入版本控制**，因此生产环境必须手动配置，否则 PostHog 会静默 disabled。

### 12.1 服务器端 `.env`

在 `/opt/repoingest/.env`（仓库根目录）中确保存在：

```
POSTHOG_ENABLED=1
POSTHOG_API_KEY=phc_xxx                  # 与线上 PostHog 项目一致
POSTHOG_HOST=https://us.i.posthog.com
POSTHOG_AUTOCAPTURE=1
POSTHOG_SESSION_REPLAY=0
```

> `load_dotenv()` 会从进程工作目录（`/opt/repoingest/src`）逐级向上查找，能命中仓库根的 `.env`。

### 12.2 同步依赖（本次新增 `posthog`）

```bash
cd /opt/repoingest
uv sync --group server     # server 依赖组（含 posthog）
uv pip list | grep -i posthog
```

### 12.3 重启并检查

```bash
systemctl restart repoingest
systemctl status repoingest
journalctl -u repoingest -n 50 | grep -i posthog
# 期望：repoingest.analytics | PostHog analytics enabled | host=https://us.i.posthog.com
```

### 12.4 线上验证

- 浏览器打开 `https://repoingest.top/app`，确认：
  - cookie `repoingest_uid` 存在；
  - Console 中 `posthog.get_distinct_id()` 与 `getCookie('repoingest_uid')` 一致；
  - PostHog Live events 出现事件。
- API 准入校验：
  ```bash
  curl -i https://repoingest.top/api/jobs                                    # 400 missing uid
  curl -i -H "Cookie: repoingest_uid=test-uid" https://repoingest.top/api/jobs  # 200
  ```

### 12.5 注意事项

- 保持 uvicorn **单进程**（`job_store` 为进程内内存设计），勿加 `--workers N`。
- 前端 SDK 由**浏览器**直连 `us.i.posthog.com`（不受服务器出站限制）；后端 SDK 由**服务器**出站发送，需确保服务器可访问该域名。
- 换机 / 重部署时 `.env` 需重新配置。

---

## 13. 待确认问题

| # | 问题 | 结论 / 现状 |
|---|------|-------------|
| Q1 | 是否开启 Session Replay | **默认关闭**，已环境变量化（`POSTHOG_SESSION_REPLAY`），可随时开启评估 |
| Q2 | 是否保留 autocapture | **默认保留**，已环境变量化（`POSTHOG_AUTOCAPTURE=0` 可关闭降噪） |
| Q3 | uid 缺失时的 API 请求 | **拒绝请求**（未开放 API，uid 作为准入凭证，见 §6.4） |
| Q4 | 是否提供 opt-out 开关 | 已实现**基础 opt-out**（遵循 DNT / GPC，见 §8.2）；完整 UI 开关暂缓 |
| Q5 | `file_count`/`token_count` 来源 | 当前**解析 summary**；如后续需要更准，可扩展 `IngestSuccessResponse` |
