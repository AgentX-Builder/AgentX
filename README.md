# AgentX — Terminal AI Agent

**v0.2.0**

**Local-first terminal AI agent.** Defaults to Ollama, compatible with any OpenAI-style API. Supports multi-turn tool calling, task planning (2.0), and **dynamic tool generation** — the model can create and register new tools at runtime.

**本地优先的终端 AI 智能体。** 默认对接 Ollama，兼容任意 OpenAI 风格接口。支持多轮工具调用、任务规划（2.0）以及**动态工具生成**——模型可以在运行时自己创建并注册新工具。

---

## Changelog / 更新日志

### v0.2.0
- **Tiered permissions / 权限分级**: read-only commands (`ls` / `cat` / `grep` / `find` / `echo`) now run automatically; only destructive ops (`write_file`, `rm`, `mv`, `>` redirect, etc.) ask for confirmation. 只读命令自动执行，仅写文件、`rm`、`mv`、`>` 重定向等破坏性操作才弹确认。
- **Custom persona / 自定义人设**: new `/prompt` command edits the system persona in-chat (multi-line, takes effect immediately); `/prompt clear` resets to default. 新增 `/prompt` 命令，聊天内多行编辑系统人设并立即生效，`/prompt clear` 恢复默认。
- **Auto context compression / 上下文自动压缩**: sessions exceeding `[context] max_tokens` (default 100K) auto-summarize old messages — no more degraded, stuttering answers on long chats. 会话超过 `[context] max_tokens`（默认 100K）自动摘要压缩旧消息，长对话不再退化、断断续续。
- **Live thinking chain / 思维链实时展示**: any model streaming `reasoning_content` (DeepSeek V4, Ollama DeepSeek R1 / Qwen3) shows its thinking in real time before answering. 所有流式输出 `reasoning_content` 的模型（DeepSeek V4、Ollama 的 DeepSeek R1 / Qwen3 等）都会实时展示思维链，再输出答案干活。
- Version bumped 0.1.0 → 0.2.0. 版本号 0.1.0 → 0.2.0。

### v0.1.0
- Initial release: multi-turn tool calling, task planning 2.0, dynamic tool generation, session persistence, gacha pets, AGPL-3.0. 初始版本：多轮工具调用、任务规划 2.0、动态工具生成、会话持久化、抽卡宠物、AGPL-3.0。

---

## Features / 功能特性

| 功能 | 说明 |
| --- | --- |
| **Multi-turn tool calling / 多轮工具调用** | The model calls tools on demand, continues reasoning with results, until a final answer. 模型按需调用工具、拿到结果后继续推理，直到给出最终答案 |
| **8 built-in tools / 8 个内置工具** | Read file, write file, list dir, recursive list, run shell, HTTP GET, grep code, find files. 读文件、写文件、列目录、递归列目录、执行 shell 命令、HTTP GET、代码搜索、文件名查找 |
| **Dynamic tool generation / 动态工具生成** | The model writes Python code via `register_tool` and registers a brand-new tool at runtime. 模型通过调用 `register_tool` 直接写 Python 代码，把新工具注册进系统，注册后即可像内置工具一样被调用 |
| **Task planning 2.0 / 任务规划（2.0）** | Complex tasks are split into subtask lists, executed item by item, then summarized. 复杂任务先拆成子任务清单，逐项执行再汇总报告 |
| **Tiered permissions / 权限分级** | Read-only commands (list / read / grep / find / echo) run automatically; only destructive ops — writing files, risky shell commands (`rm`, `mv`, `> redirect`, etc.) — ask for confirmation. 只读命令（列出/读取/搜索/查找/echo）自动执行，不再弹确认；只有会修改文件或系统的危险操作（写入文件、`rm`、`mv`、`>` 重定向等）才要求确认 |
| **Custom persona / 自定义人设** | Set a system persona via `/prompt` (multi-line, takes effect immediately). 通过 `/prompt` 设置系统人设（支持多行，保存即生效） |
| **Auto context compression / 上下文自动压缩** | When the conversation exceeds 100K tokens, old messages are auto-summarized to keep the model sharp and prevent degraded / stuttering replies. 对话超过 100K token 时自动把旧消息摘要压缩，防止上下文膨胀导致回答退化、断断续续 |
| **Live thinking chain / 思维链实时展示** | Any model that streams `reasoning_content` (DeepSeek V4, Ollama's DeepSeek R1 / Qwen3) shows its thinking in real time (dim italic) before the answer. 任何流式输出 `reasoning_content` 的模型（DeepSeek V4、Ollama 上的 DeepSeek R1 / Qwen3 等）都会先实时灰字滚动展示思维链，再输出答案干活 |
| **Unified result truncation / 工具结果统一截断** | Large outputs are truncated by tool type to avoid overflowing the LLM context. 大输出按工具类型截断首尾，防止塞爆 LLM 上下文 |
| **Session persistence / 会话持久化** | History auto-saves to `~/.agentx/sessions/`; resume with `--resume`. 历史自动保存到 `~/.agentx/sessions/`，支持 `--resume` 恢复 |
| **Streaming anti-repeat / 流式防复读** | Detects trailing repeated blocks and cleans up model repetition loops. 检测尾部重复段落，自动清理模型复读循环 |
| **Rich terminal UI / Rich 终端 UI** | Pet status, streaming render, result panel, status bar. 宠物状态、流式渲染、结果面板、状态栏 |

---

## Model Selection Guide / 模型选择指南

AgentX's provider uses the OpenAI-compatible protocol, so it works with Ollama local models, DeepSeek, and various API relay services.

AgentX 的 provider 使用 OpenAI 兼容协议，因此可以对接 Ollama 本地模型、DeepSeek，以及各类 API 中转站。

### Main language model families / 主力语言模型家族

| 家族 | 强项 | 适合场景 |
| --- | --- | --- |
| gpt | Code / reasoning / tool calling all-rounder. 代码 / 推理 / 工具调用全能主力 | General agents, programming, complex task fallback. 通用 Agent、编程、复杂任务兜底 |
| claude | Top-tier code / deep reasoning / long-form writing. 代码 / 深度推理 / 长文写作天花板 | Claude Code-style agents, code-heavy tasks. Claude Code 类 Agent、重代码任务 |
| gemini | Multimodal / 1M+ context / frontend polish. 多模态理解 / 超长上下文 / 前端美化 | Image understanding, long docs, UI visual analysis. 看图、1M 长文、UI 视觉分析 |
| qwen | Native Chinese / math / balanced coding. 中文母语级 / 数学 / 代码均衡 | Chinese scenarios, math, retrieval (incl. embeddings). 中文场景、数学题、检索（含嵌入） |
| deepseek | Best Chinese value / strong reasoning. 中文性价比之王 / 推理强 | High-frequency Chinese calls, cheap and big. 高频中文调用、便宜大碗 |
| kimi | Super long context / document reading. 超长上下文 / 文档论文阅读 | Hundreds of thousands of chars contracts / papers / meeting notes. 几十万字合同 / 论文 / 会议纪要 |
| glm | Chinese agents / tool calling / free tiers. 中文 Agent / 工具调用 / 免费线多 | Chinese automation, free-line fallback. 中文自动化、白嫖线兜底 |
| doubao | Fast Chinese / cheap / video gen (seedance). 中文快 / 便宜 / 视频生成（seedance） | High-frequency Chinese, video generation. 中文高频、视频生成 |
| grok | Punchy delivery. 交付汇报 / 犀利 | Long-form / creative copy, grok-imagine image gen. 长文 / 创意文案、grok-imagine 出图 |
| llama / gemma / mistral (open-source) | Zero-cost free tiers. 免费线零成本 | Low-cost fallback, test environments. 低价兜底、测试环境 |

### Tool models / 工具类模型

| 类别 | 家族 | 强项 |
| --- | --- | --- |
| Image / 图像 | flux | Quality ceiling / detail. 质量天花板 / 细节好 |
| Image / 图像 | nano-banana | Fast / cheap (~$0.3/image). 快 / 便宜（按张约 $0.3） |
| Image / 图像 | stable | Classic controllable / stylized. 经典可控 / 风格化 |
| Image / 图像 | grok-imagine | Creative image gen. 创意出图 |
| Video / 视频 | doubao seedance / jimeng / sora | Chinese video gen (5-10s clips). 中文视频生成（5-10s 短视频） |
| Voice / 语音 | azure-tts / SenseVoiceSmall | Microsoft TTS / Chinese ASR. 微软音质 TTS / 中文识别 |
| Embedding / 嵌入检索 | bge / qwen3-embedding / text-embedding | RAG vector retrieval, strong zh bilingual. RAG 向量检索、中文双语效果好 |

### One-line picks / 一句话选型建议

- General agent / programming → `gpt` or `claude`. 通用 Agent / 编程 → `gpt` 或 `claude`
- High-frequency Chinese, value → `deepseek` or `qwen`. 中文高频、追求性价比 → `deepseek` 或 `qwen`
- Very long documents → `kimi` / `gemini`. 超长文档阅读 → `kimi` / `gemini`
- Local privacy / zero cost / testing → Ollama open-source (`llama3`, `phi4-mini`, etc.). 本地隐私 / 零成本 / 测试环境 → Ollama 开源系（`llama3`、`phi4-mini` 等）

---

## Installation / 安装

```bash
git clone <your-repo-url>
cd agentx
pip install -e .
```

Or run directly from source without installing:

或直接以源码方式运行（无需安装）：

```bash
cd agentx
PYTHONPATH=src python3 -m agentx.cli.main --help
```

Dependencies: `typer`, `rich`, `httpx`, `requests`, `tomli-w` (Python >= 3.10).

依赖：`typer`、`rich`、`httpx`、`requests`、`tomli-w`（Python >= 3.10）。

---

## Quick Start / 快速开始

### Local Ollama / 本地 Ollama

```bash
ollama serve
ollama pull phi4-mini

# Start agentx / 启动 agentx
agentx chat
```

### Remote OpenAI-compatible endpoint (DeepSeek etc.) / 远程 OpenAI 兼容接口（DeepSeek 等）

Edit `~/.agentx/config.toml`:

编辑 `~/.agentx/config.toml`：

```toml
[llm]
provider = "openai"
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
api_key = "your-api-key"
```

```bash
agentx chat
```

---

## Commands / 命令说明

| 命令 | 说明 |
| --- | --- |
| `agentx chat` | Interactive chat (default). 交互式对话（默认） |
| `agentx chat --resume <session-id>` | Resume a past session. 恢复历史会话 |
| `agentx run "task"` | One-shot, non-interactive. 单次执行，非交互 |
| `agentx run --plan "task"` | Plan mode: split subtasks, run each, summarize. 规划模式：先拆子任务，逐项执行，汇总报告 |
| `agentx tools` | List all registered tools. 列出全部已注册工具 |
| `agentx config list` | Show current config (API key masked). 查看当前配置（API Key 打码） |
| `agentx config setup` | Interactive wizard: fill provider / base_url / model / api_key. 交互式配置向导：只需填服务商、接口地址、模型名、API Key |
| `agentx config get --key llm.model` | Read one config key. 读取单个配置项 |
| `agentx config set --key llm.model --value llama3` | Write a config key. 写入配置项 |

### In-chat commands / chat 内置指令

| 指令 | 说明 |
| --- | --- |
| `/exit` | Exit and save the session. 退出并保存会话 |
| `/clear` | Clear session history. 清空会话历史 |
| `/tools` | List tools. 列出工具 |
| `/model` | Show current model. 显示当前模型 |
| `/config` | Show current config (API key masked). 显示当前配置（API Key 打码） |
| `/prompt` | Edit the system persona in-chat (multi-line, takes effect immediately); `/prompt clear` resets to default. 在聊天内编辑系统人设（多行输入，保存即生效）；`/prompt clear` 清空恢复默认 |
| `/sessions` | List & switch past sessions. 列出并切换历史会话 |
| `/work` | Show file operations in current session. 查看当前会话文件操作记录 |
| `/memory` | Browse memory / jump to a session. 查看记忆库并跳转会话 |
| `/gacha` | Gacha a pet (10 free draws/day). 抽卡领养宠物（每天 10 次免费） |
| `/collection` | View gacha collection. 查看宠物收藏 |

### Configuration wizard / 配置向导

Run `agentx config setup` to configure interactively — you only need to fill in the provider, base URL, model name and API key. Ollama works out of the box with defaults. The API key is masked everywhere in the UI (e.g. `sk-t**********bc`), never shown in plain text.

运行 `agentx config setup` 交互式配置：只需填写服务商、接口地址、模型名和 API Key。Ollama 用默认值即可直接使用。API Key 在界面中一律打码显示（如 `sk-t**********bc`），不明文暴露。

---

## Configuration / 配置

Config lives at `~/.agentx/config.toml`; environment variables override it (`AGENTX_LLM_PROVIDER`, `AGENTX_LLM_MODEL`, `AGENTX_LLM_BASE_URL`, `AGENTX_LLM_API_KEY`).

配置文件位于 `~/.agentx/config.toml`，支持环境变量覆盖（`AGENTX_LLM_PROVIDER`、`AGENTX_LLM_MODEL`、`AGENTX_LLM_BASE_URL`、`AGENTX_LLM_API_KEY`）。

```toml
[llm]
provider = "ollama"            # ollama | openai
model = "phi4-mini"
base_url = "http://127.0.0.1:11434"
api_key = ""

[agent]
persona = ""                   # custom system persona, e.g. "你是傲娇猫娘, 说话带喵。" / 自定义人设

[tools]
confirm_level = "auto"         # auto(仅危险命令确认) / strict(所有 shell 都确认) / off(全自动)

[context]
max_tokens = 100000            # 超过此 token 数自动压缩旧消息 / auto-compress old messages above this

[ui]
pet = true                     # pet status animation / 宠物状态动画
color_theme = "default"

[session]
auto_save = true               # auto-save session history / 自动保存会话历史
save_dir = "~/.agentx/sessions"
```

---

## Tool Mechanism / 工具机制

Tools are managed by `ToolRegistry`; `ToolSpec` describes a tool's name, description, input schema and implementation. Built-in tools are defined and registered via the `@tool` decorator.

Permission tiering: read-only tools (`read_file`, `list_dir`, `grep_code`, `find_files`, `list_cwd`, `http_get_url`) always run without confirmation. `write_file` always asks. `run_shell_cmd` auto-runs for ordinary read commands and only asks when the command is destructive (`rm`, `mv`, `dd`, `kill`, `chmod`, `apt-get`, `git push`, output redirection to a file, etc.). Tune with `[tools] confirm_level`.

工具统一由 `ToolRegistry` 管理，`ToolSpec` 描述工具的名称、说明、输入 schema 与实现函数。内置工具通过 `@tool` 装饰器定义并注册。

权限分级：只读工具（`read_file`、`list_dir`、`grep_code`、`find_files`、`list_cwd`、`http_get_url`）一律自动执行不确认；`write_file` 总是确认；`run_shell_cmd` 对普通只读命令自动执行，仅当命令具有破坏性（`rm`、`mv`、`dd`、`kill`、`chmod`、`apt-get`、`git push`、输出重定向写入文件等）时才弹确认。可用 `[tools] confirm_level` 调整。

### Built-in tools / 内置工具

| 工具 | 说明 | 需确认 |
| --- | --- | --- |
| `read_file` | Read file text. 读取文件文本 | No / 否 |
| `write_file` | Write file (auto-create parent dirs). 写入文件（自动建父目录） | Yes / 是 |
| `list_dir` | List directory entries. 列出目录条目 | No / 否 |
| `list_cwd` | Recursively list all levels of the current dir. 递归列出当前目录全部层级 | No / 否 |
| `run_shell_cmd` | Run a shell command (30s timeout). 执行 shell 命令（30s 超时） | Auto / 自动 |
| `http_get_url` | HTTP GET to fetch page text. HTTP GET 拉取网页文本 | No / 否 |
| `grep_code` | Regex search over code content. 按正则搜索代码内容 | No / 否 |
| `find_files` | Find files by name pattern. 按文件名模式查找文件 | No / 否 |
| `register_tool` | Dynamically register a new tool. 动态注册新工具 | No / 否 |

### Dynamic tool generation / 动态工具生成

When the built-in tools can't cover a need, the model can call `register_tool` directly, passing Python source code as an argument; the system compiles and registers it as a formal tool:

模型遇到内置工具覆盖不到的需求时，可直接调用 `register_tool`，把 Python 函数源码作为参数传入，系统编译并注册为正式工具：

```
register_tool(
  name="count_py",
  description="统计目录下的 Python 文件数量",
  code='def count_py(path: str) -> str:\n    n = 0\n    for root, _, files in os.walk(path):\n        for f in files:\n            if f.endswith(".py"):\n                n += 1\n    return f"py 文件数: {n}"'
)
```

After registration, the tool can be called like any built-in. The execution environment preloads common stdlib (`os`, `sys`, `json`, `re`, `math`, `random`, `datetime`, `pathlib.Path`), and protects against duplicate registration, compile failures, and missing function definitions.

注册成功后即可像内置工具一样被调用。动态工具的代码执行环境预置了 `os`、`sys`、`json`、`re`、`math`、`random`、`datetime`、`pathlib.Path` 等常用标准库，并对重复注册、编译失败、缺少函数定义等场景做了保护。

### Tool result truncation / 工具结果截断

To keep whole-file / huge shell outputs from overflowing the LLM context and causing empty replies, tool results are truncated by type (head + tail kept):

为防止整文件、超长 shell 输出塞爆 LLM 上下文导致空回复，工具结果按类型统一截断（保留首尾）：

| 工具 | 上限 |
| --- | --- |
| `read_file` | 12000 chars / 字符 |
| `http_get_url` / `grep_code` | 6000 chars / 字符 |
| `run_shell_cmd` etc. / 等默认 | 4000 chars / 字符 |
| `find_files` / `list_dir` / `list_cwd` | 3000 chars / 字符 |
| `write_file` | 1000 chars / 字符 |

---

## Architecture / 架构

```
src/agentx/
├── cli/
│   ├── main.py        # Typer entry: chat / run / config / tools commands
│   └── ui.py          # Rich rendering: pet, panels, status bar
├── llm/
│   ├── base.py        # Message / ToolSpec / LLMResponse abstractions
│   ├── ollama.py      # Ollama provider (streaming + tool calling)
│   ├── openai.py      # OpenAI-compatible provider (streaming anti-repeat)
│   └── registry.py    # provider factory
├── session/
│   └── session.py     # Session history, truncation-boundary hardening, persistence
├── tools/
│   ├── base.py        # ToolSpec / ToolRegistry / result truncation
│   └── dynamic.py     # Dynamic tool generation (register_tool)
├── agent.py           # Agent core loop (run / plan_and_run)
├── planner.py         # Planning 2.0: decompose -> execute -> summarize
├── config.py          # Config loading (TOML + env vars)
└── events.py          # Event enums (reserved)
```

---

## Stability / 稳定性

- **Auto-retry on empty replies** / 空回复自动重试: when a cloud API returns an empty response (e.g. DeepSeek transient hiccups / timeouts), agentx automatically retries up to 3 times with increasing delays instead of showing a blank screen.
- **Thinking mode support** / 思考模式支持: for models with `reasoning_content` (DeepSeek V4 thinking mode, Ollama R1/Qwen3 distill series), agentx reads, relays and falls back to the reasoning chain — no more blank replies on second turn. The thinking chain is also streamed live in dim italic so you can watch it "think" before it works.
- **Explicit errors** / 错误显性化: streamed HTTP errors are surfaced instead of being silently swallowed.
- **Auto context compression** / 上下文自动压缩: once a session exceeds `[context] max_tokens` (default 100K), agentx summarizes the old messages into one compact digest (keeping the most recent ~40% verbatim, with safe tool-call boundaries) so long chats don't degrade into stuttering, repeated answers.

稳定性特性：云端 API 空回复自动重试（最多 3 次，间隔递增）；DeepSeek V4 等思考模式模型的 `reasoning_content` 全链路读取与回传；流式 HTTP 错误显性报出，不再静默吞掉；会话超过 `[context] max_tokens`（默认 100K）时自动把旧消息压缩为一条摘要（最近约 40% 原样保留，并保证 tool 调用边界安全），长对话不再退化成断断续续的重复回答。

---

## License / 许可证

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)
