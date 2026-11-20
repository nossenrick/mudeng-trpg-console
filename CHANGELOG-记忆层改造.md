# 2026-11-17 更新记录（二）：记忆层改造

借鉴腾讯混元 [Hy Memory 2.0](https://github.com/Tencent-Hunyuan/Hy-Memory) 的三个设计，落到现有架构里。**没有引入它的 SDK、没有新增依赖、没有新增数据库。**

## 一、事实版本化 + 冲突消解

### 问题

原来 `state.aiMemory.facts` 是 `string[]`，只增不减，80 条封顶。NPC 立场从"敌视"变"合作"之后，两条矛盾的事实一起进上下文，只能靠 system prompt 里那句「事实优先级」让模型自己猜。

实测你最近的自动存档（`auto_1003`）：facts 正好 80 条，已到上限，再写就开始丢最早的。

### 改法

`facts` 从字符串数组变成对象数组：

```js
{
  id: "fact_lx8f2_87",
  text: "加利：对玩家转为合作",
  subject: "加利",              // 从「主体：事实」里推断
  status: "active",             // active | superseded | dropped
  supersedes: "",
  supersededBy: "fact_lx8f2_88",
  turn: 43,
  createdAt: 1794899100000
}
```

写入规则（`rememberAiFacts`）：

- 同一 `subject` 写入新事实 → 旧的自动标 `superseded`，`supersededBy` 指向新条目
- 完全相同的文本 → 只刷新回合，不重复追加
- **没有主体的叙述型事实不参与消解**（"塞西莉亚下探时滑落"不会取代"塞西莉亚把绳子放下"）
- 上下文只注入 `active`；`superseded` / `dropped` 留档不占 token

容量：`active` 保留最近 60 条，超出的降级成 `dropped` 而不是删除，留档 240 条。**不再静默丢数据。**

### 要 AI 配合

`AI_TURN_SCHEMA_HINT` 里的 `memory` 说明改成了：

> 适合长期记忆的事实，短句；涉及某个角色、地点或线索的状态变化时写成「主体：事实」，例如「加利：对玩家转为合作」「地下室：已被放火」，同一主体的新状态会取代旧状态

不写主体也能用，只是那条事实不参与消解。

## 二、前瞻意图（剧情线带到期 + 触发词）

### 问题

`threads` 只有 `open / done / paused`，没有"什么时候该自己浮现"。伏笔躺在那儿，AI 想不起来。

### 改法

`threads` 新增三个字段：

```js
{ dueTurn: 12, triggerKeywords: ["地下室", "仪式"], pinned: false }
```

**不用改 UI**，直接在剧情线描述里写指令：

| 写法 | 含义 |
|---|---|
| `@t12 邪教徒会来回收遗物` | 第 12 回合到期，进入"已到期"状态 |
| `地下室的仪式 #地下室,仪式` | 玩家提到"地下室"或"仪式"时优先浮现 |
| `@t3 面具的来历 #面具,拍卖行` | 两个一起用 |

解析在 `parseThreadDirectives()`，`@tN` 和 `#词1,词2` 会从描述里剔除，存成独立字段。

召回（`buildMemoryContext`）优先级：

```
pinned(40) + 命中触发词(每个 30) + 已到期(20) + 即将到期(8)
```

上下文里会带上标记：

```
未解剧情线：
- 面具的来历：拍卖行的收货单（第3回合 · 已到期；本次提到：面具、拍卖行）
- 邪教徒的仪式：地下室（即将到期）
```

导演面板的剧情线列表也会显示这些标记。

## 三、跨战役画像（SCHEMA 层）

### 问题

每开一个新团，记忆从零开始。跑了五局，AI 还是不知道你喜欢什么节奏。

### 改法

存 `localStorage`（key `trpg_cross_campaign_profile_v1`），**不随单局存档走**——它属于"这个 KP + 这群玩家"，不属于某个模组。

```js
{ profile: "这一桌偏好…", campaigns: [{ title, campaign, at }], updatedAt }
```

- 导演记忆面板顶部新增一块「跨战役画像」+ 「生成跨战役画像」按钮
- 生成时把本局最近 8 条阶段摘要 + 未完成剧情线 + 角色列表喂给模型，产出 200–350 字画像
- 画像会自动注入 `buildAiTurnMessages` 的 system 末尾（`buildCrossCampaignSystemBlock()`）
- 前提是有摘要或剧情线，否则按钮会提示"先跑几局"

成本：一次几百 token，一局点一次，不用每回合跑。

## 兼容性

| 场景 | 行为 |
|---|---|
| 老存档 `facts: string[]` | 自动升级成对象，`subject` 从冒号推断，全部 `active` |
| 老存档 `threads` 缺新字段 | 补 `dueTurn: 0`、`triggerKeywords: []`、`pinned: false` |
| 80 条已满的老存档 | 首次写入时重排成 60 active + 21 dropped，**一条不丢** |
| `resetAll()` | `{facts:[], summaries:[], threads:[]}` 仍兼容，normalize 会补字段 |
| 存档导出/导入 | 整体 JSON 序列化，无需迁移脚本 |

## 回归测试

```powershell
node scripts\test_memory.js
```

14 条用例，覆盖：老存档迁移、80 条规模不丢数据、同主体取代、不同主体隔离、叙述型事实不误伤、去重、`@tN` / `#关键词` 解析、召回优先级、只注入 active 事实。

当前状态：**14 通过 / 0 失败**。

## 没做的

| 项 | 原因 |
|---|---|
| 引入 `hy-memory` SDK | 要接 embedding 服务（DeepSeek 没有 embedding API），pro/ultra 模式每回合多一次 LLM 调用，还要多一个向量库 |
| 语义检索（向量召回） | 现在还是 bigram 关键词。真要上，本地 bge-small-zh 比接整个框架轻 |
| 跨战役画像自动生成 | 结团流程的触发点目前只在 Python 脚本里，做成手动按钮更可控 |

## 回滚

```
backups/memory-layer-20261117-151858/{app.js, server.py}
backups/apiv2-20261117-150713/         # 今天所有改动之前的原始版本
```

只改了 `app.js` 一个文件（本轮），`server.py` 是上一轮文档解析的改动。
