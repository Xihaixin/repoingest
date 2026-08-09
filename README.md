# Repoingest

将任何 Git 仓库转换为适合大型语言模型（LLMs）提示的文本输入。

你还可以在任何 Gitee 网址中，将 `hub` 替换为 `ingest`，以访问对应的摘要。

## 🚀 功能特点

- **便捷的代码上下文**：从 Git 仓库 URL 或目录获取文本摘要
- **智能格式化**：针对 LLM 提示优化的输出格式
- **包含以下统计信息**：
  - 文件与目录结构
  - 提取内容的大小
  - 令牌（Token）数量
- **命令行工具（CLI）**：可作为 Shell 命令运行
- **Python 包**：可在代码中导入使用

## 📚 依赖要求

- Python 3.7 及以上版本

### 📦 安装方式

```bash
git clone https://gitee.com/xihaishen/repoingest.git

```


## 💡 命令行使用方法

`gitingest` 命令行工具可用于分析代码库，并生成其内容的文本转成文件。

```bash
# 基本用法
gitingest /path/to/directory

# 从 URL 获取
gitingest https://gitee.com/xihaishen/repoingest

# 查看更多选项
gitingest --help
```

运行后，摘要会写入当前工作目录下的文本文件（默认文件名为 `digest.txt`）。

## 🐍 Python 包使用方法

```python
# 同步使用
from gitingest import ingest

summary, tree, content = ingest("path/to/directory")

# 或从 URL 获取
summary, tree, content = ingest("https://gitee.com/xihaishen/repoingest")
```

默认情况下，上述代码不会生成文件，但可通过 `output` 参数启用文件写入功能。

```python
# 异步使用
from gitingest import ingest_async
import asyncio

result = asyncio.run(ingest_async("path/to/directory"))
```

### Jupyter 笔记本使用方法

```python
from gitingest import ingest_async

# 在 Jupyter 中直接使用 await
summary, tree, content = await ingest_async("path/to/directory")

```

之所以能这样使用，是因为 Jupyter 笔记本默认支持异步操作。

## 🐳 自托管部署

1. 构建镜像：

   ``` bash
   docker build -t repoingest .
   ```

2. 运行容器：

   ``` bash
   docker run -d --name repoingest -p 8000:8000 repoingest
   ```

应用程序将在 `http://localhost:8000` 地址可用。

如果在域名上部署，可通过环境变量 `ALLOWED_HOSTS` 指定允许的主机名：

   ```bash
   # 默认值："repoingest.com, *.repoingest.com, localhost, 127.0.0.1"
   ALLOWED_HOSTS="example.com, localhost, 127.0.0.1"
   ```

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

## 🤝 贡献方式

### 非技术类贡献

- **提交问题（Issue）**：若发现漏洞或有新功能想法，请在 Gitee 上[提交问题](https://gitee.com/xihaishen/repoingest/issues/new)。这有助于我们跟踪并优先处理你的需求。
- **传播分享**：如果你喜欢 repoingest，欢迎分享给朋友、同事，并在社交媒体上推广。这将帮助我们扩大社区规模，让 repoingest 变得更完善。
- **使用 repoingest**：最有价值的反馈来自实际使用！若遇到问题或有改进建议，可通过在 Gitee 上[提交问题](https://gitee.com/xihaishen/repoingest/issues/new)
  
### 技术类贡献

repoingest 致力于为首次贡献者提供友好的环境，代码库基于简单的 Python 和 HTML 构建。如果在代码开发过程中需要帮助，可在 [Discord](https://discord.gg/YsBgcuucBN) OR [小红书]( https://xhslink.com/m/6l7fGLDntnI)上联系我们。关于提交拉取请求（Pull Request）的详细说明，请参考 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 🛠️ 技术栈

- [Tailwind CSS](https://tailwindcss.com) - 前端框架
- [FastAPI](https://Gitee.com/fastapi/fastapi) - 后端框架
- [Jinja2](https://jinja.palletsprojects.com) - HTML 模板引擎
- [tiktoken](https://Gitee.com/openai/tiktoken) - 令牌（Token）数量估算工具
- [posthog](https://Gitee.com/PostHog/posthog) - 优质数据分析工具
