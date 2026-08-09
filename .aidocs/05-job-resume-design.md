# Repoingest —— 处理任务状态保持与恢复（Job Resume）设计方案

> 阶段：Phase 6 · 分析与设计
> 分支：`feat/home-and-i18n`
> 日期：2026-08-10
> 状态：设计中（含待确认需求点）

---

## 1. 问题描述

在 `/app` 提交一个仓库后，处理通常需要数十秒。若用户中途跳转回首页（`/`）浏览，再返回 `/app` 时：

- 页面为全新加载，**没有任何痕迹**表明之前提交的处理任务；
- 用户可能期待看到两种情况之一：**① 仍在处理中；② 已完成并可直接查看结果**。

## 2. 现状与根因

| 现状 | 说明 |
|------|------|
| 结果只存在于浏览器内存 | `utils.js handleSubmit` 用 `fetch('/api/ingest')` 同步等待完整结果，完成后由 JS 填充 `result.jinja` |
| 处理与 HTTP 请求绑定 | `/api/ingest` 处理完全同步（最长可达 60s+）；用户跳转即卸载页面、中止 fetch |
| 无服务端任务状态 | 没有任务 ID / 进度 / 结果存储，返回 `/app` 无法恢复任何状态 |

## 3. 初步设计

### 3.1 服务端任务注册表（Job Store）

- 新增 `src/server/job_store.py`：内存字典 + `asyncio.Lock`，字段：
  `id` / `status`(`running|done|error`) / `result` / `error` / `created_at` / `updated_at` / `params`。
- 生命周期：任务完成或超过 TTL 后由清理任务回收（复用 `server_utils` 的后台任务模式）。
- 能力模型：`job_id = uuid4().hex`（不可猜测），作为访问凭证；无鉴权系统下够用。

### 3.2 处理改后台任务（解耦请求）

- `POST /api/ingest` → 校验入参后**立即返回** `202 {"job_id", "status":"running"}`，处理放入 `asyncio.create_task` 后台执行；任务完成/失败时回写 store。
- 新增 `GET /api/jobs/{job_id}` → 返回 `{"job_id","status","result"|null,"error"|null}`。
- 好处：用户跳转/断开连接不影响处理；也规避"客户端断开导致任务被取消"的不确定性。

### 3.3 前端恢复（cookie + 轮询）

- 提交成功拿到 `job_id` → 写入 cookie `repoingest_job=<id>`（JS 设置，`path=/`）。
- `/app` 加载时读取 cookie → 轮询 `GET /api/jobs/{id}`（每 2s）：
  - `running` → 显示"处理中"状态并继续轮询；
  - `done` → 用返回的 `result` 渲染结果；
  - `error` → 显示错误；
  - 404（过期/重启）→ 清除 cookie，回到空白表单。
- 结果仍保留 cookie，返回 `/app` 可再次看到上次结果（表单始终在页面上方，可随时发起新任务）。

## 4. 已确认需求点（用户决策）

| # | 问题 | 确认结论 |
|---|------|---------|
| Q1 | 用户中途离开时任务策略 | **后台继续处理**，直至完成/失败 |
| Q2 | 结果保留时长 | **2 小时**（完成与失败任务均保留，涉及仓库内容隐私） |
| Q3 | `/api/ingest` 兼容性 | **无外部调用方，可改为 202+job_id+轮询**（接口变更） |
| Q4 | 恢复策略 | **提供最近任务列表**（非仅最新一次） |

## 5. 细化设计（含"最近任务列表"）

### 5.1 浏览器伪身份（uid）

- JS 在 `/app` 首次加载时确保存在 `repoingest_uid` cookie（`crypto.randomUUID()`，非 HttpOnly）。
- 所有任务按 `uid` 归类；`GET /api/jobs` 仅返回当前 uid 的任务，避免跨用户泄露。

### 5.2 Job Store（内存 + TTL）

- `src/server/job_store.py`：`dict + asyncio.Lock`，字段：
  `id(uuid4.hex)` / `uid` / `status(running|done|error)` / `result` / `error` / `params` / `created_at` / `updated_at`。
- **TTL = 2 小时**；`cleanup()` 定期删除过期任务，并按 uid 限制保留最近 **20** 条（控制内存）。
- 结果含仓库内容，内存持有不超过 2h；服务重启即清空（文档注明限制）。

### 5.3 API（变更 + 新增）

| 端点 | 行为 |
|------|------|
| `POST /api/ingest` | 读 `repoingest_uid` cookie → 创建 job → `asyncio.create_task` 后台处理 → **立即 202** `{job_id,status:"running"}`（限流 10/min 保留） |
| `GET /api/jobs` | 按 uid（cookie）返回最近任务**元数据列表**（id/status/repo/created，不含大结果），限流 |
| `GET /api/jobs/{job_id}` | 能力凭证（uuid 不可猜测）获取**完整结果**（status/result/error），限流 |

### 5.4 前端恢复 UX（/app 加载时）

1. 确保 `repoingest_uid` cookie。
2. `GET /api/jobs` → 渲染「最近任务」列表（在表单下方）。
3. **自动恢复最新任务**：running → 显示处理中并轮询；done → 直接渲染结果；error → 显示错误。
4. 列表项可点选：running 项 → 接管并轮询；done 项 → 渲染其结果；error 项 → 显示错误。
5. 提交新任务 → 更新列表 + 轮询；过期(404) → 从列表移除。

### 5.5 轮询

- `GET /api/jobs/{id}` 每 2s 一次；running 持续轮询，done/error 停止并渲染。

## 6. 影响面

- 后端：`ingest.py`（改后台任务）、新增 `job_store.py`、新增 `routers/jobs.py`、`server_utils.lifespan` 加清理任务。
- 前端：`utils.js`（uid、提交改轮询、列表加载）、`index.jinja`（最近任务区块）、i18n 新增键。
- 文档：`.aidocs` 追加 Phase 6 实施记录。
