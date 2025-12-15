# Repoingest

Convert any Git repository into text input optimized for Large Language Models (LLMs) prompts.

You can also replace `hub` with `ingest` in any Gitee URL to access the corresponding summary.

## 🚀 Key Features

- **Convenient Code Context**: Retrieve text summaries from Git repository URLs or local directories
- **Intelligent Formatting**: Output optimized for LLM prompt compatibility
- **Included Statistics**:
  - File and directory structure
  - Extracted content size
  - Token count
- **Command-Line Interface (CLI)**: Run as a shell command
- **Python Package**: Import and use in your code

## 📚 Dependencies

- Python 3.7 or higher

### 📦 Installation

```bash
git clone https://gitee.com/xihaishen/repoingest.git
```

## 💡 CLI Usage

The `gitingest` CLI tool analyzes code repositories and generates a text file of their contents.

```bash
# Basic usage (local directory)
gitingest /path/to/directory

# From a URL
gitingest https://gitee.com/xihaishen/repoingest

# View more options
gitingest --help
```

After execution, the summary will be written to a text file in the current working directory (default filename: `digest.txt`).

## 🐍 Python Package Usage

```python
# Synchronous usage
from gitingest import ingest

summary, tree, content = ingest("path/to/directory")

# Or from a URL
summary, tree, content = ingest("https://gitee.com/xihaishen/repoingest")
```

By default, the above code does not generate a file, but you can enable file writing via the `output` parameter.

```python
# Asynchronous usage
from gitingest import ingest_async
import asyncio

result = asyncio.run(ingest_async("path/to/directory"))
```

### Jupyter Notebook Usage

```python
from gitingest import ingest_async

# Use await directly in Jupyter
summary, tree, content = await ingest_async("path/to/directory")
```

This works because Jupyter Notebooks natively support asynchronous operations.

## 🐳 Self-Hosted Deployment

1. Build the image:

   ```bash
   docker build -t repoingest .
   ```

2. Run the container:

   ```bash
   docker run -d --name repoingest -p 8000:8000 repoingest
   ```

The application will be available at `http://localhost:8000`.

If deploying on a domain, specify allowed hostnames via the `ALLOWED_HOSTS` environment variable:

   ```bash
   # Default: "repoingest.com, *.repoingest.com, localhost, 127.0.0.1"
   ALLOWED_HOSTS="example.com, localhost, 127.0.0.1"
   ```

## 🤝 Contributing

### Non-Technical Contributions

- **Submit Issues**: If you find bugs or have feature requests, please [submit an issue](https://gitee.com/xihaishen/repoingest/issues/new) on Gitee. This helps us track and prioritize your needs.
- **Spread the Word**: If you enjoy using repoingest, share it with friends, colleagues, and on social media. This helps us grow the community and make repoingest even better.
- **Use repoingest**: The most valuable feedback comes from real-world usage! If you encounter problems or have improvement suggestions, feel free to [submit an issue](https://gitee.com/xihaishen/repoingest/issues/new) on Gitee.

### Technical Contributions

repoingest is committed to providing a friendly environment for first-time contributors. The codebase is built with simple Python and HTML. If you need help during development, reach out to us on [Discord](https://discord.com/invite/zerRaGK9EC). For detailed instructions on submitting a Pull Request, please refer to [CONTRIBUTING.md](./CONTRIBUTING.md).

## 🛠️ Tech Stack

- [Tailwind CSS](https://tailwindcss.com) - Frontend framework
- [FastAPI](https://gitee.com/fastapi/fastapi) - Backend framework
- [Jinja2](https://jinja.palletsprojects.com) - HTML templating engine
- [tiktoken](https://gitee.com/openai/tiktoken) - Token counting tool
- [posthog](https://gitee.com/PostHog/posthog) - Advanced analytics tool
