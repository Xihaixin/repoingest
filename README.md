# repoingest

> 将任意 Git 仓库转换为适合大型语言模型（LLM）提示的文本摘要 —— 一个可自托管的 Web 服务。

repoingest 让「把代码库喂给大语言模型」变得简单：粘贴一个 Git 仓库地址（或 `owner/repo`），即可获得包含**目录结构**与**文件内容**的文本摘要，并估算 **token 数量**，可直接粘贴进 LLM 提示。

- 在线体验：<https://repoingest.top>
- 项目主页：<https://github.com/Xihaixin/repoingest>

> **GitHub 快捷方式**：以 GitHub 为典型示例，把仓库网址中的 `github.com` 替换为 `repoingest.top`，即可快捷跳转并自动开始摄取。例如：
> `https://github.com/Xihaixin/repoingest` → `https://repoingest.top/Xihaixin/repoingest`

> repoingest 的核心解析能力衍生自开源项目 [gitingest](https://github.com/coderamp-labs/gitingest)（MIT 许可证）。两者渊源详见下文「项目渊源与致谢」。

## ✨ 功能特点

- **Web 界面**：粘贴仓库 URL 或 `owner/repo`，一键生成摘要
- **面向 LLM 的输出**：目录结构 + 文件内容 + token 估算
- **后台任务与恢复**：提交后可离开页面，稍后回来继续查看结果（含「最近任务」列表）
- **中英双语界面**（zh-CN / en）
- **私有仓库支持**：可填写 GitHub Personal Access Token
- **灵活过滤**：include / exclude 模式，文件大小阈值
- **一键复制 / 下载**完整 digest
- **GitHub → repoingest.top**：把仓库网址中的 `github.com` 换成 `repoingest.top`，即可快捷跳转并自动开始摄取
- **生产化能力**：结构化日志与请求级 `request_id` 溯源、限流、可信主机校验、任务内存存储与清理
- **可选行为分析**：PostHog（前端 + 后端，统一匿名身份）
- **Python 库 API**：`from gitingest import ingest, ingest_async`

## 🌐 Web 使用方法

1. 打开 <https://repoingest.top/app>
2. 输入仓库地址，例如：
   - `https://github.com/Xihaixin/repoingest`
   - `Xihaixin/repoingest`
3. 按需调整文件大小阈值与 include / exclude 过滤；私有仓库可勾选并填写 PAT
4. 提交后进入后台处理，可离开页面，稍后回来在「最近任务」中继续查看
5. 结果支持分别或整体**复制 / 下载**

> **GitHub 快捷方式**：把 `https://github.com/<owner>/<repo>` 中的 `github.com` 替换为 `repoingest.top`（即 `https://repoingest.top/<owner>/<repo>`），即可直接跳转并开始摄取该仓库。

## 📦 安装

核心库与命令行工具已发布到 PyPI：

```bash
pip install repoingest
# 推荐用 pipx 隔离安装命令行工具
pipx install repoingest
```

## 💡 命令行使用方法

`repoingest` 命令行工具可用于分析代码库，并生成其内容的文本摘要。

```bash
# 基本用法（本地目录，默认写入 digest.txt）
repoingest /path/to/directory

# 从 URL 获取
repoingest https://github.com/Xihaixin/repoingest

# 输出到标准输出
repoingest https://github.com/Xihaixin/repoingest -o -

# 查看更多选项
repoingest --help
```

运行后，摘要会写入当前工作目录下的文本文件（默认文件名为 `digest.txt`）。

## 🐍 Python 库使用方法

核心库同时提供同步与异步 API：

```python
# 同步使用
from repoingest import ingest

summary, tree, content = ingest("path/to/directory")
# 或从 URL 获取
summary, tree, content = ingest("https://github.com/Xihaixin/repoingest")
```

```python
# 异步使用
from repoingest import ingest_async
import asyncio

result = asyncio.run(ingest_async("path/to/directory"))
```

在 Jupyter Notebook 中可直接 `await ingest_async(...)`（Notebook 原生支持异步）。

## 📚 依赖要求

- Python **3.11** 及以上版本
- Git（用于克隆远程仓库）

## 🚀 本地运行

```bash
# 获取代码
git clone https://github.com/Xihaixin/repoingest.git
cd repoingest

# 安装依赖（含 Web 服务依赖；使用 uv，按 uv.lock 锁定版本）
uv sync --group server

# 在 src 目录下启动服务
cd src
uvicorn server.main:app --host 127.0.0.1 --port 8001
```

配置通过项目根目录的 `.env` 提供（字段含义见该文件内注释）。常用变量：

| 变量 | 说明 |
|------|------|
| `REPOINGEST_HOST` / `REPOINGEST_PORT` | 仅在以 `python -m server.main` 方式启动时生效 |
| `ALLOWED_HOSTS` | 可信主机白名单（逗号分隔） |
| `GITINGEST_TMP_PATH` | 临时克隆目录（Windows 建议显式设置） |

## 🖥️ 生产部署

生产环境推荐 **Linux + systemd + Nginx 反向代理**，关键点：

- 使用 `uvicorn server.main:app` 启动，**必须单进程**（任务存储为进程内内存设计，勿加 `--workers N`）
- 用 `uv sync --group server` 同步依赖（含 `posthog`）
- `ALLOWED_HOSTS` 需包含你的域名
- 完整流程见 [`.aidocs/06-linux-deployment-update.md`](./.aidocs/06-linux-deployment-update.md)

## 📝 日志系统

日志系统基于 [Loguru](https://github.com/Delgan/loguru)，日志行均包含**完整日期与时间**（`YYYY-MM-DD HH:mm:ss.SSS`），并按天自动轮转、保留 14 天。

每个 HTTP 请求都会被分配唯一 `request_id`（同时通过响应头 `X-Request-ID` 返回给客户端），同一请求在解析、克隆、摘要、响应全过程的日志均带该标识，**失败请求可按 `request_id` 一键溯源**。

可通过环境变量配置（默认值见括号）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REPOINGEST_LOG_LEVEL` | `INFO` | 全局日志级别 |
| `REPOINGEST_LOG_FILE` | `src/logs/repoingest.log` | 日志文件路径（相对代码 `src/` 目录解析，与进程工作目录无关） |
| `REPOINGEST_LOG_ROTATION` | `00:00` | 轮转规则（时间/大小） |
| `REPOINGEST_LOG_RETENTION` | `14 days` | 日志保留时长 |
| `REPOINGEST_LOG_COMPRESSION` | `gz` | 轮转文件压缩格式 |
| `REPOINGEST_LOG_JSON` | `0` | 设为 `1` 输出 JSON 行 |
| `REPOINGEST_LOG_TO_STDOUT` | `1` | 设为 `0` 关闭控制台输出 |
| `REPOINGEST_PROBE_TIMEOUT` | `10` | 仓库存在性探测超时（秒） |
| `REPOINGEST_SLOW_REQUEST_MS` | `30000` | 慢请求告警阈值（毫秒） |

## 📊 用户行为分析（PostHog）

项目集成 [PostHog](https://posthog.com) 做用户行为检测与分析。分析功能通过环境变量控制，默认关闭（本地开发不采集、不加载脚本）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTHOG_ENABLED` | `0` | 总开关：`1` 启用，`0` 关闭（关闭时不加载任何 PostHog 脚本、无外部请求） |
| `POSTHOG_API_KEY` | 空 | PostHog 项目 Token（`phc_...`，可公开嵌入前端的发布密钥） |
| `POSTHOG_HOST` | `https://us.i.posthog.com` | 采集入口，自托管时改为自建地址 |
| `POSTHOG_AUTOCAPTURE` | `1` | 自动捕获：额度紧张时可设为 `0`，仅保留显式事件 |
| `POSTHOG_SESSION_REPLAY` | `0` | 会话回放：默认关闭（隐私与额度） |

此外，前端会遵循浏览器的 Do Not Track / Global Privacy Control：开启时自动退出采集。

前端以浏览器 cookie `repoingest_uid` 作为 PostHog `distinct_id`，与后端后台任务事件共用同一身份，从而构建「访问 → 提交 → 完成」的完整漏斗。分析数据不包含 token、仓库正文与完整私有 URL。

## 🧬 项目渊源与致谢

repoingest 的核心仓库解析与摘要能力（位于 `src/repoingest/`，涵盖仓库解析、克隆、文件遍历、token 估算与格式化等）**衍生自开源项目 [gitingest](https://github.com/coderamp-labs/gitingest)**：

- 原作者：[Romain Courtois](https://github.com/cyclotruc)
- 现维护方：[coderamp-labs](https://github.com/coderamp-labs)
- 许可证：**MIT License，Copyright © 2024 Romain Courtois**

我们向原作者与社区致以诚挚的感谢，并遵循 MIT 许可证保留原始版权声明（见 [LICENSE](./LICENSE)）。

**repoingest 并非原项目的简单搬运或镜像**，而是在其核心能力之上、面向 Web 服务与生产环境做了独立的扩展与重构，例如：

- 基于 **FastAPI + Jinja2 + Tailwind** 的完整 Web 前端与交互；
- **后台异步任务与状态恢复**（离开页面后可回来继续查看结果）；
- **中英双语（i18n）** 界面；
- **结构化日志**、请求级 `request_id` 溯源与慢请求告警；
- 限流、可信主机校验、任务内存存储与清理等生产化能力；
- **PostHog 用户行为分析**（前端 + 后端，基于统一匿名身份）；
- 私有仓库支持、示例仓库、`github.com` → `repoingest.top` 快捷摄取等产品化功能。

因此，repoingest 是一个独立的**衍生作品（derivative work）**，我们尊重并遵守原项目的开源许可。

## 📄 许可证

本项目采用 **MIT 许可证**，详见 [LICENSE](./LICENSE)。

- 衍生自 [gitingest](https://github.com/coderamp-labs/gitingest) 的部分：Copyright © 2024 Romain Courtois
- repoingest 新增与修改的部分：Copyright © 2025 溪海莘

## 🤝 贡献方式

### 非技术类贡献

- **提交问题（Issue）**：若发现漏洞或有新功能想法，请在 GitHub 上[提交问题](https://github.com/Xihaixin/repoingest/issues/new)。这有助于我们跟踪并优先处理你的需求。
- **传播分享**：如果你喜欢 repoingest，欢迎分享给朋友、同事，并在社交媒体上推广。这将帮助我们扩大社区规模，让 repoingest 变得更完善。
- **使用 repoingest**：最有价值的反馈来自实际使用！若遇到问题或有改进建议，可通过在 GitHub 上[提交问题](https://github.com/Xihaixin/repoingest/issues/new)

### 技术类贡献

repoingest 致力于为首次贡献者提供友好的环境，代码库基于简单的 Python 和 HTML 构建。如果在代码开发过程中需要帮助，可在 [Discord](https://discord.gg/YsBgcuucBN) OR [小红书](https://xhslink.com/m/6l7fGLDntnI)上联系我们。欢迎在 GitHub 上提交 Pull Request 或 Issue 参与贡献。

## 🛠️ 技术栈

- [Tailwind CSS](https://tailwindcss.com) - 前端框架
- [FastAPI](https://fastapi.tiangolo.com) - 后端框架
- [Jinja2](https://jinja.palletsprojects.com) - HTML 模板引擎
- [tiktoken](https://github.com/openai/tiktoken) - 令牌（Token）数量估算工具
- [Loguru](https://github.com/Delgan/loguru) - 结构化日志
- [PostHog](https://posthog.com) - 用户行为分析
- [gitingest](https://github.com/coderamp-labs/gitingest) - 核心仓库解析能力（MIT）
