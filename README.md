# Gitingest

将任何 Git 仓库转换为适合大型语言模型（LLMs）提示的文本输入。

你还可以在任何 GitHub 网址中，将 `hub` 替换为 `ingest`，以访问对应的摘要。

[gitingest.com](https://gitingest.com) · [Chrome 扩展](https://chromewebstore.google.com/detail/adfjahbijlkjfoicpjkhjicpjpjfaood) · [Firefox 插件](https://addons.mozilla.org/firefox/addon/gitingest)

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

Gitingest 可在 [PyPI](https://pypi.org/project/gitingest/) 上获取。
你可以使用 `pip` 安装：

```bash
pip install gitingest
```

不过，使用 `pipx` 安装可能是更优的选择。
你可以通过偏好的包管理器安装 `pipx`：

```bash
brew install pipx
apt install pipx
scoop install pipx
...
```

如果是首次使用 pipx，请运行以下命令：

```bash
pipx ensurepath
```

```bash
# 安装 gitingest
pipx install gitingest
```

## 💡 命令行使用方法

`gitingest` 命令行工具可用于分析代码库，并生成其内容的文本转储文件。

```bash
# 基本用法
gitingest /path/to/directory

# 从 URL 获取
gitingest https://github.com/cyclotruc/gitingest

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
summary, tree, content = ingest("https://github.com/cyclotruc/gitingest")
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
   docker build -t gitingest .
   ```

2. 运行容器：

   ``` bash
   docker run -d --name gitingest -p 8000:8000 gitingest
   ```

应用程序将在 `http://localhost:8000` 地址可用。

如果在域名上部署，可通过环境变量 `ALLOWED_HOSTS` 指定允许的主机名：

   ```bash
   # 默认值："gitingest.com, *.gitingest.com, localhost, 127.0.0.1"
   ALLOWED_HOSTS="example.com, localhost, 127.0.0.1"
   ```

## 🤝 贡献方式

### 非技术类贡献

- **提交问题（Issue）**：若发现漏洞或有新功能想法，请在 GitHub 上[提交问题](https://github.com/cyclotruc/gitingest/issues/new)。这有助于我们跟踪并优先处理你的需求。
- **传播分享**：如果你喜欢 Gitingest，欢迎分享给朋友、同事，并在社交媒体上推广。这将帮助我们扩大社区规模，让 Gitingest 变得更完善。
- **使用 Gitingest**：最有价值的反馈来自实际使用！若遇到问题或有改进建议，可通过在 GitHub 上[提交问题](https://github.com/cyclotruc/gitingest/issues/new)，或在 [Discord](https://discord.com/invite/zerRaGK9EC) 上联系我们反馈。

### 技术类贡献

Gitingest 致力于为首次贡献者提供友好的环境，代码库基于简单的 Python 和 HTML 构建。如果在代码开发过程中需要帮助，可在 [Discord](https://discord.com/invite/zerRaGK9EC) 上联系我们。关于提交拉取请求（Pull Request）的详细说明，请参考 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 🛠️ 技术栈

- [Tailwind CSS](https://tailwindcss.com) - 前端框架
- [FastAPI](https://github.com/fastapi/fastapi) - 后端框架
- [Jinja2](https://jinja.palletsprojects.com) - HTML 模板引擎
- [tiktoken](https://github.com/openai/tiktoken) - 令牌（Token）数量估算工具
- [posthog](https://github.com/PostHog/posthog) - 优质数据分析工具

### 正在寻找 JavaScript/FileSystemNode 相关的包？

可以了解 NPM 平台上的替代方案 📦 Repomix：<https://github.com/yamadashy/repomix>

## 🚀 项目发展情况

[![星标历史图表](https://api.star-history.com/svg?repos=cyclotruc/gitingest&type=Date)](https://star-history.com/#cyclotruc/gitingest&Date)