# repoingest

> Convert any Git repository into a text digest optimized for Large Language Model (LLM) prompts — a self-hostable web service.

repoingest makes it easy to feed a codebase to an LLM: paste a Git repository URL (or `owner/repo`) and get a text digest containing the **directory structure** and **file contents**, along with a **token estimate** you can paste straight into a prompt.

- Live demo: <https://repoingest.top>
- Project home: <https://github.com/Xihaixin/repoingest>

> **GitHub shortcut**: using GitHub as the typical example, replace `github.com` in a repository URL with `repoingest.top` to jump straight to ingestion and start it automatically. For example:
> `https://github.com/Xihaixin/repoingest` → `https://repoingest.top/Xihaixin/repoingest`

> repoingest's core parsing capability is derived from the open-source project [gitingest](https://github.com/coderamp-labs/gitingest) (MIT License). See "Origin & Acknowledgements" below.

## ✨ Key Features

- **Web UI**: paste a repository URL or `owner/repo` and generate a digest in one click
- **LLM-friendly output**: directory structure + file contents + token estimate
- **Background jobs with resume**: leave the page and come back later to view results (includes a "recent jobs" list)
- **Bilingual UI** (zh-CN / en)
- **Private repository support**: provide a GitHub Personal Access Token
- **Flexible filtering**: include / exclude patterns and a file-size threshold
- **One-click copy / download** of the full digest
- **GitHub → repoingest.top**: replace `github.com` in a repository URL with `repoingest.top` to jump straight to ingestion and start it automatically
- **Production-ready**: structured logging with per-request `request_id` tracing, rate limiting, trusted-host validation, in-memory job store with cleanup
- **Optional analytics**: PostHog (frontend + backend, unified anonymous identity)
- **Python library API**: `from gitingest import ingest, ingest_async`

## 🌐 Web Usage

1. Open <https://repoingest.top/app>
2. Enter a repository address, for example:
   - `https://github.com/Xihaixin/repoingest`
   - `Xihaixin/repoingest`
3. Adjust the file-size threshold and include / exclude filters as needed; for private repos, enable the option and provide a PAT
4. Submit — processing runs in the background; you may leave the page and resume later from "recent jobs"
5. Copy or download individual sections or the whole digest

> **GitHub shortcut**: replace `github.com` in `https://github.com/<owner>/<repo>` with `repoingest.top` (i.e. `https://repoingest.top/<owner>/<repo>`) to jump straight to that repository and start ingestion.

## 📦 Installation

The core library and CLI are published on PyPI:

```bash
pip install repoingest
# pipx is recommended for an isolated CLI install
pipx install repoingest
```

## 💡 CLI Usage

The `repoingest` CLI tool analyzes code repositories and generates a text digest of their contents.

```bash
# Basic usage (local directory; writes digest.txt by default)
repoingest /path/to/directory

# From a URL
repoingest https://github.com/Xihaixin/repoingest

# Output to stdout
repoingest https://github.com/Xihaixin/repoingest -o -

# View more options
repoingest --help
```

After execution, the digest is written to a text file in the current working directory (default filename: `digest.txt`).

## 🐍 Python Library Usage

The core library exposes both synchronous and asynchronous APIs:

```python
# Synchronous usage
from repoingest import ingest

summary, tree, content = ingest("path/to/directory")
# Or from a URL
summary, tree, content = ingest("https://github.com/Xihaixin/repoingest")
```

```python
# Asynchronous usage
from repoingest import ingest_async
import asyncio

result = asyncio.run(ingest_async("path/to/directory"))
```

In a Jupyter Notebook you can `await ingest_async(...)` directly (Notebooks natively support async).

## 📚 Dependencies

- Python **3.11** or higher
- Git (for cloning remote repositories)

## 🚀 Local Development

```bash
# Get the code
git clone https://github.com/Xihaixin/repoingest.git
cd repoingest

# Install dependencies (including web-server deps; using uv, pinned by uv.lock)
uv sync --group server

# Start the server from the src directory
cd src
uvicorn server.main:app --host 127.0.0.1 --port 8001
```

Configuration is provided via `.env` in the project root (see the comments in that file). Common variables:

| Variable | Description |
|----------|-------------|
| `REPOINGEST_HOST` / `REPOINGEST_PORT` | Only effective when started via `python -m server.main` |
| `ALLOWED_HOSTS` | Trusted-host allowlist (comma-separated) |
| `GITINGEST_TMP_PATH` | Temporary clone directory (recommended on Windows) |

## 🖥️ Production Deployment

For production, **Linux + systemd + Nginx reverse proxy** is recommended. Key points:

- Start with `uvicorn server.main:app` and **run a single process** (the job store is in-process memory; do not add `--workers N`)
- Run `uv sync --group server` to install dependencies (including `posthog`)
- `ALLOWED_HOSTS` must include your domain
- See [`.aidocs/06-linux-deployment-update.md`](./.aidocs/06-linux-deployment-update.md) for the full walkthrough

## 📝 Logging

The logging system is built on [Loguru](https://github.com/Delgan/loguru). Every log line carries a **full timestamp** (`YYYY-MM-DD HH:mm:ss.SSS`), and logs rotate daily with 14-day retention.

Each HTTP request is assigned a unique `request_id` (also returned via the `X-Request-ID` response header). All logs for a request — parsing, cloning, summarization, response — carry this identifier, so **a failed request can be traced end-to-end by its `request_id`**.

Configurable via environment variables (defaults in parentheses):

| Variable | Default | Description |
|----------|---------|-------------|
| `REPOINGEST_LOG_LEVEL` | `INFO` | Global log level |
| `REPOINGEST_LOG_FILE` | `src/logs/repoingest.log` | Log file path (resolved relative to the code `src/` directory, independent of the process working directory) |
| `REPOINGEST_LOG_ROTATION` | `00:00` | Rotation rule (time / size) |
| `REPOINGEST_LOG_RETENTION` | `14 days` | Log retention |
| `REPOINGEST_LOG_COMPRESSION` | `gz` | Compression format for rotated files |
| `REPOINGEST_LOG_JSON` | `0` | Set to `1` for JSON lines |
| `REPOINGEST_LOG_TO_STDOUT` | `1` | Set to `0` to disable console output |
| `REPOINGEST_PROBE_TIMEOUT` | `10` | Repository existence probe timeout (seconds) |
| `REPOINGEST_SLOW_REQUEST_MS` | `30000` | Slow-request warning threshold (ms) |

## 📊 User Analytics (PostHog)

The project integrates [PostHog](https://posthog.com) for user behavior tracking and analytics. Analytics is controlled by environment variables and is disabled by default (no scripts loaded, no outbound requests in local development):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTHOG_ENABLED` | `0` | Master switch: `1` enabled, `0` disabled |
| `POSTHOG_API_KEY` | empty | PostHog project token (`phc_...`, a publishable key safe to embed in the frontend) |
| `POSTHOG_HOST` | `https://us.i.posthog.com` | Ingestion endpoint; point to a self-hosted instance if needed |
| `POSTHOG_AUTOCAPTURE` | `1` | Autocapture: set to `0` to keep only explicit events when quota is tight |
| `POSTHOG_SESSION_REPLAY` | `0` | Session Replay: disabled by default (privacy and quota) |

The frontend also honors the browser's Do Not Track / Global Privacy Control signals and opts out automatically when enabled.

The frontend uses the `repoingest_uid` browser cookie as the PostHog `distinct_id`, sharing the same identity as backend background-job events to build a full "visit → submit → complete" funnel. Analytics data never includes tokens, repository contents, or full private URLs.

## 🧬 Origin & Acknowledgements

repoingest's core repository parsing and summarization capability (under `src/repoingest/`, covering repository parsing, cloning, file traversal, token estimation and formatting) is **derived from the open-source project [gitingest](https://github.com/coderamp-labs/gitingest)**:

- Original author: [Romain Courtois](https://github.com/cyclotruc)
- Current maintainer: [coderamp-labs](https://github.com/coderamp-labs)
- License: **MIT License, Copyright © 2024 Romain Courtois**

We sincerely thank the original author and community, and we retain the original copyright notice in accordance with the MIT License (see [LICENSE](./LICENSE)).

**repoingest is not a simple copy or mirror of the original project.** On top of its core capability, we have independently extended and reworked it for a web service and production use, including:

- a full web frontend and interaction layer built with **FastAPI + Jinja2 + Tailwind**;
- **background async jobs with state resume** (leave the page and return later);
- a **bilingual (i18n)** UI;
- **structured logging**, per-request `request_id` tracing and slow-request warnings;
- production features such as rate limiting, trusted-host validation, and an in-memory job store with cleanup;
- **PostHog user analytics** (frontend + backend, based on a unified anonymous identity);
- product features such as private-repo support, example repositories, and the `github.com` → `repoingest.top` quick-ingest shortcut.

repoingest is therefore an independent **derivative work**, and we respect and comply with the original project's open-source license.

## 📄 License

This project is released under the **MIT License**. See [LICENSE](./LICENSE).

- Portions derived from [gitingest](https://github.com/coderamp-labs/gitingest): Copyright © 2024 Romain Courtois
- New and modified portions of repoingest: Copyright © 2025 haiShen

## 🤝 Contributing

### Non-Technical Contributions

- **Submit Issues**: If you find bugs or have feature requests, please [submit an issue](https://github.com/Xihaixin/repoingest/issues/new) on GitHub. This helps us track and prioritize your needs.
- **Spread the Word**: If you enjoy using repoingest, share it with friends, colleagues, and on social media. This helps us grow the community and make repoingest even better.
- **Use repoingest**: The most valuable feedback comes from real-world usage! If you encounter problems or have improvement suggestions, feel free to [submit an issue](https://github.com/Xihaixin/repoingest/issues/new) on GitHub.

### Technical Contributions

repoingest is committed to providing a friendly environment for first-time contributors. The codebase is built with simple Python and HTML. If you need help during development, reach out to us on [haishen](https://discord.gg/YsBgcuucBN) OR [xiaohongshu](https://xhslink.com/m/6l7fGLDntnI). Pull Requests and issues on GitHub are welcome.

## 🛠️ Tech Stack

- [Tailwind CSS](https://tailwindcss.com) - Frontend framework
- [FastAPI](https://fastapi.tiangolo.com) - Backend framework
- [Jinja2](https://jinja.palletsprojects.com) - HTML templating engine
- [tiktoken](https://github.com/openai/tiktoken) - Token counting tool
- [Loguru](https://github.com/Delgan/loguru) - Structured logging
- [PostHog](https://posthog.com) - User analytics
- [gitingest](https://github.com/coderamp-labs/gitingest) - Core repository parsing (MIT)
