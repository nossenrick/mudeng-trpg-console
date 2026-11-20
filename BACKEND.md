# Backend

FastAPI + SQLite。前端是静态文件，AI 调用通过后端代理，密钥不进入浏览器。

## 首次安装

```powershell
.\start_server.ps1
```

脚本会在缺失时创建 `.venv` 并安装 `requirements.txt`。手动方式：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

打开 <http://localhost:8000/>。

## AI 配置

服务端按以下顺序读取配置：

1. 环境变量 `TRPG_AI_ENDPOINT`、`TRPG_AI_MODEL`、`TRPG_AI_API_KEY`、`TRPG_AI_TEMPERATURE`
2. `ai_config.json`

如果访问模型接口必须经过代理，设置 `TRPG_AI_PROXY`（例如 `http://127.0.0.1:7897`）。
代理只用于 AI 请求；服务端默认不读取系统代理环境，避免 `NO_PROXY` 中的 IPv6 写法导致 httpx 解析失败。

`ai_config.json` 结构：

```json
{
  "endpoint": "https://api.deepseek.com",
  "model": "deepseek-flash",
  "apiKey": "sk-...",
  "temperature": 0.7
}
```

界面里的「保存 AI 设置」会通过 `PUT /api/ai/config` 写入该文件；该接口只接受本机回环地址。
`GET /api/ai/config` 只返回 `hasKey` 和末四位提示，绝不返回完整 Key。

静态资源使用白名单路由，只有 `.js/.css/.png/...` 会被提供；
`server.py`、`trpg.sqlite3`、`ai_config.json` 均返回 404。

## 存档 API

- `GET /api/saves` — 存档列表（不含完整 state）
- `POST /api/saves` — 保存；`auto: true` 覆盖自动存档，否则新建手动存档
- `GET /api/saves/{id}` — 读取完整 state
- `DELETE /api/saves/{id}` — 删除存档

请求：

```json
{
  "name": "雾港档案 · 第一章",
  "summary": "雾港档案 · 15号仓库 · 42 条记录",
  "state": { "…": "前端 getPersistedState() 的结果" },
  "auto": false
}
```

存档写入 SQLite 的 `campaign_saves` 表，单份上限 12 MB；自动存档固定 id 为 `auto`，
手动存档最多保留 50 份。存档不包含 API Key（`state.ai.apiKey` 会被清空）。

## AI API

- `GET /api/ai/config` — provider 配置（无密钥）
- `PUT /api/ai/config` — 保存配置（仅本机）
- `POST /api/ai/chat` — OpenAI 兼容 chat completions 代理
- `POST /api/ai/chat/stream` — SSE 流式代理，请求体相同

请求：

```json
{
  "messages": [{ "role": "system|user|assistant", "content": "..." }],
  "model": "deepseek-flash",
  "temperature": 0.7,
  "jsonMode": true,
  "maxTokens": 3000
}
```

响应：

```json
{
  "content": "…",
  "model": "deepseek-flash",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0},
  "elapsedMs": 4123,
  "finishReason": "stop"
}
```

流式接口会把 provider 的 SSE 原样转发，并附带 `stream_options.include_usage`，
最后一个 chunk 会包含 token 用量。客户端按 `data:` 行解析 `delta.content`，
忽略 `delta.reasoning_content`，只把思考字数显示在状态栏。

代理行为：

- 90 秒超时（连接 15 秒）；流式读取上限 180 秒
- 429 / 5xx 自动重试 3 次，指数退避
- 上下文超过 180000 字符返回 413
- provider 错误返回 502（流式为 `event: error`），并截断错误体（不泄露 Key）
- 日志会打印上下文缓存命中情况：`ai ok model=… cache=8192/12288(66%)`，
  命中部分按缓存价计费，命中率越高越省钱

## 文档解析 API

- `POST /api/doc/extract` — 把模组 / 规则书 / 扫描件转成文本（仅本机调用）

请求用 base64 JSON，和 `/api/map-assets` 一致，不需要 multipart：

```json
{ "filename": "模组.pdf", "data": "JVBERi0xLjQK...", "purpose": "text_recognition" }
```

`purpose`：

- `text_recognition`（默认）— 纯文本提取，图表丢弃，适合以文字为主的模组
- `rich_layout_recognition` — 图文混排，图表按原位置裁出来，适合带地图/表格的模组

响应：

```json
{
  "text": "…",
  "pageCount": 45,
  "chars": 45817,
  "purpose": "text_recognition",
  "engine": "deepseek-ocr",
  "elapsedMs": 15658,
  "chunks": 3
}
```

行为：

- 支持 PDF、Word（doc/docx）、PowerPoint（ppt/pptx）、PNG/JPEG/WebP/GIF/BMP/TIFF
- 单文件上限 25 MB
- **PDF 按 20 页一段自动切片**再逐段调 `/v1/tools/ocr`，最后拼回整篇。423 页规则书约 21 段
- 识别结果里的 `<｜ref｜>`、`<｜box｜>` 标记和 `[[x1,y1,x2,y2]]` 坐标会被清掉
- 按页计费（1.5 元 / 1000 页，45 页约 0.07 元），**不占用对话 token**
- 前端 `extractModuleFileText` 优先走这里，失败时静默回退到本地 pdf.js / JSZip

> `endpoint` 指向中转站且不支持 `/v1/tools/ocr` 时，接口返回 502 并说明原因，前端自动回退本地解析，不会卡住导入。

## 房间 API

- `GET /api/health`
- `POST /api/devices/bootstrap`
- `POST /api/rooms`
- `POST /api/rooms/{room_id}/join`
- `GET /api/rooms/{room_id}/state?participant_id=...`
- `GET /api/rooms/{room_id}/members?participant_id=...`
- `PATCH /api/rooms/{room_id}/members/{member_id}`
- `DELETE /api/rooms/{room_id}/members/{member_id}`
- `PUT /api/rooms/{room_id}/state`
- `POST /api/rooms/{room_id}/events`
- `GET /api/rooms/{room_id}/events`
- `GET /api/rooms/{room_id}/action-requests`
- `POST /api/rooms/{room_id}/action-requests`
- `PATCH /api/rooms/{room_id}/action-requests/{request_id}`
- `WS /ws/rooms/{room_id}?participant_id=...`

数据库：`trpg.sqlite3`。

WebSocket 是首选实时通道；轮询仍然保留，用于重连后恢复完整快照。

## AI 主持数据流

```text
玩家发言 / 行动请求
  → enqueueAiAction
  → processAiQueue
  → buildAiTurnMessages（世界、角色、NPC、线索、记忆、聊天）
  → POST /api/ai/chat（后端代理）
  → parseAiJson → normalizeAiTurn
  → confirmAiTurnPreview
      ├─ publicText / gmNote → chatMessages
      ├─ updates → 应用 NPC / 线索 / 场景 / 玩家（可关闭）
      ├─ checks → playerCheckRequests
      └─ sceneAdvance / memory / choices → playFlow / aiMemory
  → 玩家掷骰
  → completeAiQueueForPlayerCheck
  → 结果回传 AI，继续叙述
```

## 记忆层

`state.aiMemory` 和主状态机分开：**状态**（当前场景、线索状态、NPC 位置、HP）走 `state`，
**历史与事实**走 `aiMemory`。两者不要混，混了 AI 会把三回合前的场景当成现在。

| 字段 | 形状 | 说明 |
|---|---|---|
| `facts` | `{id, text, subject, status, supersedes, supersededBy, turn, createdAt}[]` | 同一 `subject` 的新事实会取代旧事实；`active` 留 60 条，超出的降级 `dropped` 留档 |
| `summaries` | `string[]` | 每 8 条公开消息自动生成，最多 20 条 |
| `threads` | `{id, title, detail, status, dueTurn, triggerKeywords, pinned, updatedAt}[]` | 前瞻意图；`dueTurn` 是回合数，`triggerKeywords` 命中就优先浮现 |

写入用 `rememberAiFacts()` / `rememberAiSummary()` / `addMemoryThread()`，
召回用 `buildMemoryContext(queryTerms, query)`，只注入 `status === "active"` 的事实。

事实文本写成 `主体：事实`（如 `加利：对玩家转为合作`）就会参与冲突消解；没有主体的
叙述型事实照常记录，但不会互相取代。

剧情线描述支持内联指令：`@t12` 表示第 12 回合到期，`#地下室,仪式` 表示触发词，
两个可以同时写，解析后从描述里剔除。

跨战役画像（主持习惯 + 玩家偏好）存在 `localStorage` 的
`trpg_cross_campaign_profile_v1`，不随单局存档走，生成后注入 system prompt 末尾。

回归测试：

```powershell
node scripts\test_memory.js
```

## 设备身份

浏览器首次使用时生成随机设备 ID 并保存在本地。服务端用它恢复该设备加入过的房间，
不需要密码或个人信息。清理浏览器站点数据会生成新的设备身份。

## 房间成员

主持人可以查看成员、在线状态、分配玩家角色、移除玩家设备。
被移除的玩家会在下一次同步时失效并回到本地模式。

## 质量检查

```powershell
# 健康检查 + 密钥 + 最小 JSON 请求
.\.venv\Scripts\python.exe scripts\check_ai.py

# 8 个固定场景的 AI 主持回归（需要后端已启动）
node scripts\regression_ai.mjs
```

回归脚本会启动临时无头 Chrome，加载真实页面和真实 prompt，检查 JSON 结构、
是否替玩家做决定、判定角色、状态目标、模组原文检索是否命中，以及
AI 玩家 prompt 是否泄漏主持备注、NPC 秘密或隐藏线索。

## 已知安全边界

- 房间接口目前只校验 `participant_id`，`token` 字段已存储但尚未强制校验
- AI 代理未做房间级鉴权；默认只监听 `127.0.0.1`
- 如需局域网多人，请自行限制端口访问，后续版本会补 token 鉴权和 CORS 白名单
