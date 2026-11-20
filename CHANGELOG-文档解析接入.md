# 2026-11-17 更新记录：接入 DeepSeek 文档解析

## 一句话

把"模组导入时文件读不全"这件事，从**前端自己用 pdf.js 硬啃**改成**后端调 DeepSeek 的 `/v1/tools/ocr`**。同时给 AI 日志加了上下文缓存命中率，让省钱这件事看得见。

## 改了什么

### 1. 后端新增 `POST /api/doc/extract`（server.py）

- 收 base64 JSON（和 `/api/map-assets` 同一套风格，不需要 multipart / 新依赖）
- 转发到 `https://api.deepseek.com/v1/tools/ocr`
- **PDF 自动按 20 页切片**：`/v1/tools/ocr` 单次有总时长上限，整本 400 页会 504，切段后能跑完整本
- 清洗 OCR 输出里的 `<｜ref｜>` / `<｜box｜>` 标记和 `[[x1,y1,x2,y2]]` 坐标框
- 只允许本机调用（`is_loopback`），和其它写接口一致
- 支持 `TRPG_AI_PROXY`，和 AI 请求走同一条代理
- 单文件上限 25 MB

### 2. 前端 `extractModuleFileText` 优先走服务端（app.js）

- 新增 `extractDocTextViaServer()` + `fileToBase64()`
- PDF / Word / PPT / 图片 → 先走后端；**失败静默回退**到原来的 pdf.js / JSZip，导入流程不会卡住
- 新增支持：旧版 `.doc`、`.ppt`、扫描版 PDF（原来直接报错让用户自己 OCR）
- 解析超时放宽到 15 分钟（大文件分 21 段需要时间）

### 3. 缓存命中率进日志（server.py）

AI 代理日志从

```
ai ok model=deepseek-flash elapsed=4123ms prompt=12000 completion=800
```

变成

```
ai ok model=deepseek-flash elapsed=4123ms prompt=12000 completion=800 cache=8192/12288(66%)
```

命中部分按 0.02 元/百万计费，未命中按 2 元/百万，差 100 倍。有了这个数字才知道前缀稳不稳定、要不要继续优化。

### 4. BACKEND.md 补充文档解析章节

## 实测数据

| 项目 | 结果 |
|---|---|
| 1 页 PDF（规则书第 10 页） | 4.5 秒 / 1077 字 |
| 45 页 PDF（3 段切片） | **15.7 秒 / 45817 字**，分段日志正常 |
| 403 页规则书切片 | 21 段，页数合计 403，无丢失（单元测试） |
| 文本质量 | 段落、标题层级（`##`）、页码引用都在；表格内容可读 |
| 花费 | 45 页 ≈ 0.07 元 |

## 没做的，以及为什么

| 项 | 为什么不做 |
|---|---|
| 上下文重排（把稳定内容提到 user 最前） | `system` 前缀本来就是稳定的，已经吃到缓存。重排会改动模型看到的顺序，有把 AI 主持"改笨"的风险，收益不值这个风险。先用日志里的 `cache=` 观察几局再说。 |
| 接 `deepseek_web_search` | 声明服务端工具后 `temperature` 会被服务端接管，项目里的 AI 配置面板会失效；而且 KP 联网会剧透模组、破坏沉浸感。 |
| 开 `safety_check: high` | CoC 是恐怖题材，血腥和精神污染描写是标配，中途 `refusal` 会毁掉一局游戏。自己人和朋友局不需要。 |
| TTS 朗读 KP 叙述 | 体验上是好加分（1.5 元/万字符，一场团几毛钱），但要动前端播放器和回合队列，属于独立一轮工作，不适合和解析改造混在一起。下轮可以做。 |

## 怎么回滚

改动前的原件在：

```
backups/apiv2-20261117-150713/{server.py, app.js, BACKEND.md, requirements.txt}
```

整份覆盖回去即可，无需改数据库。

## 怎么验证

```powershell
# 1. 起服务
.\start_server.ps1

# 2. 打开 http://localhost:8000/
# 3. 模组导入 → 选一个 PDF/Word/图片
#    状态栏应显示「正在解析文档「xxx.pdf」（长文件会按 20 页一段分批处理…）」
# 4. 看后端日志
Get-Content .\uvicorn.out.log -Tail 30 | Select-String "doc extract"
```

期望日志：

```
INFO doc extract chunk 1/3 from_page=1 file=模组.pdf
INFO doc extract chunk 2/3 from_page=21 file=模组.pdf
INFO doc extract chunk 3/3 from_page=41 file=模组.pdf
INFO doc extract ok file=模组.pdf pages=45 chars=45817 elapsed=15658ms purpose=text_recognition chunks=3
```

## 已知边界

- 25 MB 以上文件不走服务端，回退本地解析（会丢图表）
- 中转站 endpoint 如果不支持 `/v1/tools/ocr`，会 502 并回退本地
- `rich_layout_recognition` 已在后端支持，但前端默认传 `text_recognition`（模组以文字为主，图文模式更贵）
- OCR 按页计费，重复传同一份文件会重复扣费。前端的 localStorage 解析缓存（8 条）仍然有效，但只缓存最终 JSON，不缓存原文文本
