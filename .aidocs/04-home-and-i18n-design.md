# Repoingest —— Home 落地页 + 多语言（i18n）设计方案

> 阶段：Phase 5 · 分析与设计
> 分支：`feat/home-and-i18n`
> 日期：2026-08-09
> 状态：待评审后实施

---

## 1. 背景与目标

用户反馈两个问题：

1. **多语言缺失（重点中文）**：当前站点全部为英文硬编码。主要受众在国内推广，中文用户无法获得中文界面，也缺少语言切换能力。
2. **缺少 Home 落地页**：当前 `/` 直接是工具表单（单页应用），对开源项目不熟悉的访客缺乏"这是什么、怎么用、对我有什么价值"的引导，难以产生使用冲动。

### 1.1 现状调研结论

- 模板均为 Jinja2（`src/server/templates/`），英文直接写死在模板里（base/navbar/footer/index/git_form/result/git）。
- 表单提交流程：JS（`git_form.js`）拦截 submit → `fetch('/api/ingest')` → 通过 JS 填充 `result.jinja`。HTML POST（`dynamic.py process_catch_all`）为遗留路径（与现有 `process_query` 签名不匹配，实际未使用）。
- 用户可见文案除模板外，还散落在 JS（`utils.js`：`Processing...`、`Copied!`、`Summary:`、`Error(s):` 等）。
- 视觉体系：Tailwind CDN + `tailwind_components.html` 自定义类（`.landing-page-title`、`.intro-text`、`.sparkle-*`、`.badge-new`、`.link-bounce`）；配色 `#FFFDF8` 米色底、`gray-900` 粗边框、`#FE4A60` 红、`#ffc480` 琥珀、偏移阴影卡片风。

---

## 2. 设计方案

### 2.1 多语言（i18n）——轻量 JSON 方案

不引入 Babel/gettext 等重依赖，采用**轻量 JSON 字典 + 模板函数**：

| 组件 | 说明 |
|------|------|
| `src/server/i18n.py` | 语言定义、字典加载、`t(key, lang)` 翻译（缺 key 回退 en→key）、`resolve_language(request)` |
| `src/server/i18n/en.json` | 英文文案字典（扁平化 `a.b.c` 键） |
| `src/server/i18n/zh-CN.json` | 简体中文文案字典 |
| `server_config.render_template()` | 统一构造模板上下文（注入 `request`/`lang`/`t`）+ 渲染，替代散落的 `templates.TemplateResponse` |
| `/lang/{code}?next=...` | 语言切换端点：写 `lang` cookie 后重定向回来源页 |

**语言解析优先级**：`?lang=` 查询参数 → `lang` cookie → `Accept-Language`（`zh*`→zh-CN、`en*`→en）→ 默认 `zh-CN`（对齐国内推广主战场，英文用户可用切换器）。

**JS 国际化**：`base.jinja` 内联注入 `window.I18N = { lang, messages }`；`utils.js` 改用 `I18N.t('key')`。

**后端错误消息**：API 返回英文错误（如 "Repository not found..."）。本次对 JS 层错误包裹文案（Error(s): / An error occurred 等）做本地化，并对常见错误（仓库不存在/无效 token）做**前缀匹配的最佳努力翻译**；完整"错误码化 + 全量翻译"列为后续项。

### 2.2 Home 落地页 + 工具路由拆分

| 路由 | 页面 | 说明 |
|------|------|------|
| `GET /` | **`home.jinja`**（新建） | 落地页：Hero 标题 + 标语 + CTA、工作原理（3 步）、功能特性、快速开始、二次 CTA |
| `GET /app` | `index.jinja`（工具，原首页） | 迁移后的 Ingest 工具（表单 + 结果） |
| `GET /{user/repo}` | `git.jinja` | slug 直达（"把 hub 换成 ingest"）保持不变 |
| `GET /lang/{code}` | 302 重定向 | 语言切换 |

**Home 页面结构**（沿用现有视觉语言）：

1. **Hero**：复用 `.landing-page-title` 大标题（"把任意 Git 仓库变成 LLM 友好的文本摘要"）+ 副标语 + 主 CTA 按钮 `开始使用` → `/app`。
2. **How it works（三步）**：粘贴仓库地址 → 生成摘要/目录/内容 → 复制或下载喂给 LLM。用偏移阴影卡片（与表单卡片同款）。
3. **Features**：文本摘要、Token 估算、include/exclude 过滤、私有仓库 PAT、一键复制/下载。
4. **Quick start**：示例 + "把 github.com 换成 repoingest.top" 说明 + 示例仓库按钮（跳转 `/app` 并预填）。
5. **二次 CTA** + 页脚。

> 路由注意：`index` 路由先于 `dynamic` 路由注册，`/app` 与 `/lang/{code}` 不会被 catch-all 截获。

### 2.3 视觉一致性要求

- 全部复用现有 Tailwind 自定义类与配色，**不引入新 UI 框架/字体**。
- 语言切换器：navbar 内一个紧凑下拉（🌐 中文 / English），样式与现有 `link-bounce` 导航链接协调。

---

## 3. 实施计划（分阶段）

| 阶段 | 内容 | 产出 |
|------|------|------|
| 1 | i18n 框架：`i18n.py` + `en.json` + `zh-CN.json` + `render_template` | 翻译能力 |
| 2 | 语言解析 + `/lang/{code}` cookie 路由 | 可切换 |
| 3 | `base.jinja`（lang/meta/I18N）+ navbar 切换器 + footer 翻译 | 全局骨架 |
| 4 | `home.jinja` 落地页 + `/` 与 `/app` 路由拆分 | 落地页 |
| 5 | 翻译工具页：`index.jinja`/`git.jinja`/`git_form.jinja`/`result.jinja` | 界面中文化 |
| 6 | JS 国际化（`utils.js` + 内联 `I18N` + 错误文案） | 前端中文化 |
| 7 | `dynamic.py` 上下文注入 + 双语言渲染验证 | 验收 |
| 8 | 更新 `.aidocs` 实施日志 + black 检查 | 文档 |

---

## 4. 验收标准

1. `/?lang=zh-CN` 与 `/?lang=en` 均能正确渲染对应语言页面。
2. 浏览器 `Accept-Language: zh-CN` 时默认进入中文；英文浏览器进入英文。
3. `/` 为落地页，`/app` 为工具，`/user/repo` slug 直达不受影响。
4. navbar 语言切换器可切换语言并记住（cookie）。
5. 工具表单、结果区、JS 文案（Processing/Error/Copied/Download 等）均随语言变化。
6. 新页面视觉与现有站点一致（同配色、同卡片、同字体）。
