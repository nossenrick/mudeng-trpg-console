// 记忆层回归测试
//   node scripts\test_memory.js
// 从 app.js 里抽取纯函数，在 stub 环境里跑，不启动服务、不访问网络。
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP_JS = path.join(__dirname, "..", "app.js");
const src = fs.readFileSync(APP_JS, "utf8");

function slice(from, to) {
  const start = src.indexOf(from);
  const end = src.indexOf(to);
  if (start < 0 || end < 0 || end <= start) throw new Error(`切片失败: ${from} -> ${to}`);
  return src.slice(start, end);
}

const parts = [
  slice("const AI_CONTEXT_LIMITS", "function aiTextTerms"),
  slice("function aiTextTerms", "function buildContextQuery"),
  slice("const FACT_SUBJECT_RE", "function rememberAiSummary"),
  slice("function buildMemoryContext", "// 跨战役画像（对应 Hy Memory 的 SCHEMA 层）"),
  slice("const THREAD_DUE_RE", "function addMemoryThread"),
];

const stub = `
var state = { aiTurnCount: 7, aiMemory: null, players: [], npcs: [] };
function clampNumber(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}
let __idSeq = 0;
function nextId(prefix) { return prefix + (++__idSeq); }
`;

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(stub + parts.join("\n"), ctx);

let pass = 0;
let fail = 0;
function check(name, fn) {
  try {
    fn();
    pass += 1;
    console.log("  PASS  " + name);
  } catch (error) {
    fail += 1;
    console.log("  FAIL  " + name + " -> " + error.message);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

console.log("== 1. 旧存档迁移 ==");
check("字符串事实自动升级成对象，并推断出主体", () => {
  const memory = ctx.normalizeAiMemory(["加利：敌视玩家", "地下室有仪式痕迹"]);
  assert(memory.facts.length === 2, "条数不对");
  assert(memory.facts[0].subject === "加利", "主体推断失败: " + memory.facts[0].subject);
  assert(memory.facts[0].status === "active", "默认状态应为 active");
  assert(memory.facts[1].subject === "", "无冒号的事实不应有主体");
});

check("真实存档规模（80 条）写入时一条都不丢", () => {
  const legacy = Array.from({ length: 80 }, (_, i) => "叙述型事实第" + i + "条");
  ctx.state.aiMemory = ctx.normalizeAiMemory(legacy);
  ctx.rememberAiFacts(["加利：转为合作"]);
  const all = ctx.state.aiMemory.facts;
  assert(all.length === 81, "总数应保持 81，实际 " + all.length);
  assert(all.filter((f) => f.status === "active").length === 60, "active 应压到 60");
  assert(all.filter((f) => f.status === "dropped").length === 21, "溢出应降级为 dropped 而不是删除");
});

console.log("== 2. 冲突消解 ==");
check("同一主体写入新事实时，旧事实被标记 superseded", () => {
  ctx.state.aiMemory = ctx.normalizeAiMemory(["加利：敌视玩家"]);
  ctx.rememberAiFacts([{ text: "加利：转为合作" }]);
  const facts = ctx.state.aiMemory.facts;
  const oldOne = facts.find((f) => f.text === "加利：敌视玩家");
  const newOne = facts.find((f) => f.text === "加利：转为合作");
  assert(oldOne.status === "superseded", "旧事实没被取代");
  assert(oldOne.supersededBy === newOne.id, "supersededBy 没指向新事实");
  assert(newOne.status === "active", "新事实应为 active");
});

check("不同主体互不影响", () => {
  ctx.state.aiMemory = ctx.normalizeAiMemory(["加利：敌视玩家", "乔：信任玩家"]);
  ctx.rememberAiFacts([{ text: "加利：转为合作" }]);
  const facts = ctx.state.aiMemory.facts;
  assert(facts.find((f) => f.text === "乔：信任玩家").status === "active", "无关主体被误伤");
});

check("叙述型事实（无主体）不会被误取代", () => {
  ctx.state.aiMemory = ctx.normalizeAiMemory([]);
  ctx.rememberAiFacts(["塞西莉亚下探时滑落，跌进塌口底部", "塞西莉亚把绳子放下塌口"]);
  assert(ctx.state.aiMemory.facts.filter((f) => f.status === "active").length === 2, "叙述型事实互相取代了");
});

check("重复写入同一条事实不会膨胀", () => {
  ctx.state.aiMemory = ctx.normalizeAiMemory([]);
  ctx.rememberAiFacts(["玩家持有银钥匙"]);
  ctx.rememberAiFacts(["玩家持有银钥匙"]);
  ctx.rememberAiFacts(["玩家持有银钥匙"]);
  assert(ctx.state.aiMemory.facts.filter((f) => f.status === "active").length === 1, "重复写入产生多条");
});

console.log("== 3. 前瞻意图解析 ==");
check("@t12 解析成回合数并从描述中剔除", () => {
  const parsed = ctx.parseThreadDirectives("@t12 邪教徒会来回收遗物");
  assert(parsed.dueTurn === 12, "dueTurn=" + parsed.dueTurn);
  assert(parsed.detail === "邪教徒会来回收遗物", "detail 没清干净: " + parsed.detail);
});
check("#关键词 解析成数组", () => {
  const parsed = ctx.parseThreadDirectives("地下室的仪式 #地下室,仪式");
  assert(parsed.triggerKeywords.join(",") === "地下室,仪式", "关键词错");
  assert(parsed.detail === "地下室的仪式", "detail 没清干净: " + parsed.detail);
});
check("两个指令同时出现", () => {
  const parsed = ctx.parseThreadDirectives("@t3 面具的来历 #面具,拍卖行");
  assert(parsed.dueTurn === 3 && parsed.triggerKeywords.join(",") === "面具,拍卖行", "指令解析错");
  assert(parsed.detail === "面具的来历", "detail 没清干净: " + parsed.detail);
});
check("没有指令时原样保留", () => {
  const parsed = ctx.parseThreadDirectives("普通的剧情线描述");
  assert(parsed.dueTurn === 0 && parsed.triggerKeywords.length === 0, "不该产生指令");
  assert(parsed.detail === "普通的剧情线描述", "detail 被改动");
});

console.log("== 4. 线程归一化 ==");
check("老存档的 threads 补上新字段", () => {
  const memory = ctx.normalizeAiMemory({ threads: [{ id: "t1", title: "旧线索", detail: "以前存的", status: "open" }] });
  const thread = memory.threads[0];
  assert(thread.dueTurn === 0 && Array.isArray(thread.triggerKeywords) && thread.pinned === false, "字段没补齐");
});

console.log("== 5. 召回优先级（关键词 / 到期） ==");
check("本次提到的剧情线排第一，到期的排第二", () => {
  ctx.state.aiTurnCount = 10;
  ctx.state.aiMemory = ctx.normalizeAiMemory({
    threads: [
      { id: "t1", title: "普通线", status: "open" },
      { id: "t2", title: "到期线", status: "open", dueTurn: 5 },
      { id: "t3", title: "关键词线", status: "open", triggerKeywords: ["地下室"] },
    ],
  });
  const action = "我去地下室看看";
  const out = ctx.buildMemoryContext(ctx.aiTextTerms(action), action);
  assert(out.threads[0].id === "t3", "关键词命中应排第一，实际 " + out.threads[0].id);
  assert(out.threads[1].id === "t2", "到期应排第二，实际 " + out.threads[1].id);
  assert(out.text.includes("本次提到：地下室"), "缺少提及标记");
  assert(out.text.includes("已到期"), "缺少到期标记");
});

check("未到期的剧情线不打到期标记", () => {
  ctx.state.aiTurnCount = 3;
  ctx.state.aiMemory = ctx.normalizeAiMemory({ threads: [{ id: "t1", title: "未来的线", status: "open", dueTurn: 30 }] });
  const out = ctx.buildMemoryContext(ctx.aiTextTerms("随便走走"), "随便走走");
  assert(!out.text.includes("已到期") && !out.text.includes("即将到期"), "不该有到期标记");
});

check("只输出 active 事实，superseded 不进上下文", () => {
  ctx.state.aiTurnCount = 10;
  ctx.state.aiMemory = ctx.normalizeAiMemory(["加利：敌视玩家"]);
  ctx.rememberAiFacts([{ text: "加利：转为合作" }]);
  const out = ctx.buildMemoryContext(ctx.aiTextTerms("加利"), "加利");
  assert(!out.text.includes("敌视玩家"), "被取代的事实仍在上下文中");
  assert(out.text.includes("转为合作"), "新事实没进上下文");
});

console.log(`\n结果: ${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
