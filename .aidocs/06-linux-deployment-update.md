# 06 Linux 服务器部署更新全流程记录

> 场景：Linux 服务器上已有 systemd 托管的 repoingest 服务，原配置存在多处问题，
> 本次执行了一次完整的「代码更新 + 配置修复 + 验证」操作。本文档记录了全部服务器端
> 命令与处理过程，可直接按序复现。

## 一、背景

- 服务器：2 核，CentOS 系（Python 3.6.8 为系统自带，项目使用独立 venv）
- 部署路径：`/opt/repoingest`（git 仓库，远程与本地一致）
- 服务管理：systemd（`repoingest.service`），Nginx 反向代理域名 `repoingest.top`
- 项目要求：Python >= 3.11，依赖由 `uv` + `uv.lock` 锁定版本管理

## 二、原配置存在的问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | unit 中 `--workers 4` 多 worker | `job_store` 为**单进程内存设计**，任务创建与轮询落到不同 worker 会互相找不到 → 404/任务丢失；2 核资源也不足 |
| 2 | 服务 `disabled` | 服务器重启后服务不自动启动 |
| 3 | 运行中直接 `git pull` 且未同步依赖 | 旧进程代码 + 磁盘新模板混装 → Jinja2 `'t' is undefined` 模板错误 |
| 4 | `.venv` 缺少新版依赖 `loguru` | 新版日志模块无法导入 |
| 5 | 误建文件 `'t -f'`（误敲命令残留） | 垃圾文件 |
| 6 | `.env` 中 `PYTHONPATH=./src` | 实际不生效（`.env` 内 PYTHONPATH 不影响解释器启动 sys.path），误导排查 |
| 7 | `User=root` 运行 | 安全风险（本轮保留，列为遗留项） |

## 三、第一步：侦察现状（只读，不影响运行）

```bash
# 1. 找到服务名
systemctl list-unit-files | grep -iE 'repo|ingest|repoingest'
# 输出：repoingest.service  disabled

# 2. 查看服务状态
systemctl status repoingest
# 关键信息：Active: active (running)；Main PID 为 uvicorn 主进程；
# 存在 multiprocessing.spawn 子进程 → 判定为多 worker 运行

# 3. 查看 unit 文件
systemctl cat repoingest

# 4. 环境依赖版本
python3 --version          # 3.6.8（系统自带，不影响）
git --version              # 2.43.7
uv --version               # 0.9.18

# 5. 确认部署目录结构
ls -la /opt/repoingest
ls -la /opt/repoingest/src
# 注意 /opt/repoingest 下存在误建文件 't -f'

# 6. 系统信息
cat /etc/os-release
```

**判断要点**：`status` 输出中出现 `multiprocessing.spawn` 子进程，
即 uvicorn 使用了 `--workers N`；该项目的任务存储为进程内内存，
多 worker 下前后端任务关联会不稳定，此为「轮询 404 / 任务丢失」类问题的根源。

## 四、第二步：更新前核查与备份

```bash
# 1. 确认代码目录干净、与远端一致
cd /opt/repoingest && git status && git log --oneline -5

# 2. 查看服务器 .env
cat /opt/repoingest/src/.env

# 3. 确认 venv 的 Python 版本
/opt/repoingest/.venv/bin/python3 --version
# 输出：Python 3.11.13

# 说明：uv 创建的 venv 默认无 pip，因此 `pip list` 无输出属正常，依赖统一用 uv 管理

# 4. 查看 Nginx 反代配置（如 grep 无输出，可稍后通过外网访问验证）
grep -rn "repoingest\|8001\|proxy_pass" /etc/nginx/ 2>/dev/null | grep -v "Binary"

# 5. 备份（可选，本项目 .env 不在 git 中，建议保留副本）
mkdir -p /root/repoingest_backup
cp -a /opt/repoingest/src/.env /root/repoingest_backup/env_backup_$(date +%Y%m%d_%H%M%S)
cp -a /etc/systemd/system/repoingest.service /root/repoingest_backup/service_backup_$(date +%Y%m%d_%H%M%S)
```

## 五、第三步：修正 systemd unit 文件

覆盖 `/etc/systemd/system/repoingest.service`，核心改动：`ExecStart` 去掉 `--workers 4`。

```bash
cat > /etc/systemd/system/repoingest.service <<'EOF'
[Unit]
Description=Repoingest FastAPI Application
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/repoingest/src
Environment="PATH=/opt/repoingest/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git"
ExecStart=/opt/repoingest/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl cat repoingest   # 确认 ExecStart 已无 --workers 4
```

**关键说明**：
- `WorkingDirectory=/opt/repoingest/src` 是 `server.main:app` 能被 import 的原因
- 本项目为单事件循环 + `asyncio.Lock` 保护内存 `job_store` 的设计，**必须单 worker 运行**

## 六、第四步：停服 + uv 同步依赖

```bash
# 1. 停止服务
systemctl stop repoingest
systemctl status repoingest --no-pager | head -5   # 确认 inactive (dead)

# 2. 同步依赖（按 uv.lock 锁定版本，不装 dev 依赖，需要联网访问 PyPI）
cd /opt/repoingest && uv sync --frozen --no-dev

# 3. 确认关键依赖版本
cd /opt/repoingest && uv pip list | grep -iE 'fastapi|uvicorn|jinja2|tiktoken|slowapi'
```

**本次同步结果示例**：
```
Uninstalled 10 packages（black/flake8 等 dev 依赖）
Installed 1 package：loguru==0.7.3   ← 新版代码的新增依赖
```

## 七、第五步：启动 + 开机自启 + 健康检查

```bash
# 1. 启动并设置开机自启
systemctl start repoingest
systemctl enable repoingest
systemctl status repoingest --no-pager | head -12
# 预期：Active: active (running)，Enabled: enabled，单 PID（无 spawn 子进程）

# 2. 本地健康检查
sleep 3
curl -s http://127.0.0.1:8001/health
echo
curl -s -o /dev/null -w "首页 HTTP 状态码: %{http_code}\n" http://127.0.0.1:8001/

# 3. 查看启动日志
journalctl -u repoingest -n 30 --no-pager
# 预期无 Traceback / ModuleNotFoundError / 't' is undefined
```

## 八、第六步：端到端验证

```bash
# 1. 外网域名健康检查（走 Nginx 反代）
curl -s https://repoingest.top/health
echo
curl -s -o /dev/null -w "外网首页: %{http_code}\n" https://repoingest.top/

# 2. 提交一个真实摄取任务（小仓库，-c/-b 保持 cookie 模拟浏览器身份）
curl -s -c /tmp/ri_cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"input_text":"https://github.com/octocat/Hello-World","max_file_size":50}' \
  https://repoingest.top/api/ingest
# 预期：202 + {"job_id":"...","status":"running"}，记下 job_id

# 3. 轮询任务直到 done/error（<JOBID> 替换为上一步的 job_id）
for i in $(seq 1 15); do
  R=$(curl -s -b /tmp/ri_cookies.txt https://repoingest.top/api/jobs/<JOBID>)
  echo "[$i] $(echo "$R" | grep -o '"status": *"[^"]*"')"
  echo "$R" | grep -q '"done"\|"error"' && { echo "$R" | head -c 600; echo; break; }
  sleep 2
done
```

也可直接在浏览器访问 `https://repoingest.top` 实测页面与任务流程。

## 九、第七步：清理与收尾

```bash
# 1. 删除误建文件（文件名含空格，注意引号）
rm -f -- '/opt/repoingest/t -f'
ls -la /opt/repoingest

# 2. 查看 git 未跟踪文件，确认无遗漏
cd /opt/repoingest && git status --short

# 3. 清理 .env 中无效 PYTHONPATH 行（先留副本）
cp /opt/repoingest/src/.env /opt/repoingest/src/.env.bak.$(date +%Y%m%d)
sed -i '/^PYTHONPATH=/d' /opt/repoingest/src/.env
cat /opt/repoingest/src/.env
```

## 十、问题原因回顾

`'t' is undefined` 模板错误根源：Jinja2 模板按请求从磁盘加载（或 mtime 变化后重编译），
而 Python 进程内仍是旧代码。磁盘上已是新模板（调用 i18n 翻译函数 `t()`），
但旧进程没把 `t` 注入模板上下文 → 渲染失败。修复路径即：**停服 → 同步依赖 → 重启**。

## 十一、最终配置

- 服务：单进程 uvicorn `0.0.0.0:8001`，`Restart=always`，`enabled` 开机自启
- 运行：Python 3.11.13（`/opt/repoingest/.venv`），uv 0.9.18 管理依赖
- 反代：Nginx → `repoingest.top` → `127.0.0.1:8001`
- 数据：`job_store` 内存存储（2h TTL，每 uid 上限 20 条），重启即清空（可接受）

## 十二、以后安全更新代码的标准流程

```bash
cd /opt/repoingest
git pull                                    # 1. 拉取新代码
systemctl stop repoingest                   # 2. 停服
uv sync --frozen --no-dev                   # 3. 同步依赖（有新依赖才真正下载）
systemctl start repoingest                  # 4. 重启
journalctl -u repoingest -n 30 --no-pager   # 5. 看日志确认无异常
curl -s http://127.0.0.1:8001/health        # 6. 健康检查
```

## 十三、遗留建议（可选加固）

1. **去掉 `User=root`**：改跑非 root 用户，需调整 `src/logs` 与临时目录属主权限
2. **清理 `src/history.txt`**：确认无用后删除
3. **监控内存**：摄取大仓库时内存峰值较高，单进程下关注 OOM
4. **定期 `uv sync --frozen --no-dev`**：保持 `.venv` 与 `uv.lock` 一致
