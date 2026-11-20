/**
 * AI 主持回归测试。
 *
 * 前置：本地后端已启动（http://127.0.0.1:8000），并且服务端已配置 API Key。
 * 运行：node scripts/regression_ai.mjs
 *
 * 它会启动一个临时的无头 Chrome，加载真实页面和真实 prompt，跑一组固定场景，
 * 校验：JSON 结构、是否替玩家做决定、判定角色是否存在、状态目标是否存在。
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const BASE_URL = process.env.TRPG_BASE_URL || "http://127.0.0.1:8000";
const CDP_PORT = Number(process.env.TRPG_CDP_PORT || 9333);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function findChrome() {
  const candidates = [
    path.join(process.env.ProgramFiles || "", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env["ProgramFiles(x86)"] || "", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.ProgramFiles || "", "Microsoft/Edge/Application/msedge.exe"),
  ];
  return candidates.find((candidate) => candidate && fs.existsSync(candidate)) || "";
}

async function waitFor(check, timeout = 20000, interval = 300) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try {
      if (await check()) return true;
    } catch {
      // retry
    }
    await sleep(interval);
  }
  return false;
}

async function connect(port) {
  const target = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(`${BASE_URL}/`)}`, { method: "PUT" }).then((response) => response.json());
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  const pending = new Map();
  const events = [];
  let seq = 0;
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    } else {
      events.push(message);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  const evaluate = async (expression) => {
    const result = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result?.value;
  };
  return { send, evaluate, events, close: () => ws.close() };
}

const SCENARIOS = [
  {
    name: "调查铁箱",
    focus: "玩家刚打开铁箱，仓库外传来三短一长的敲击声。",
    action: "我蹲下检查铁箱夹层。",
    chat: ["主持人：铁箱被撬开了，里面只有半截蜡烛和一张湿地图。"],
  },
  {
    name: "和线人交涉",
    focus: "阿雁在酒馆角落等玩家开价。",
    action: "我把口袋里的钱推到桌上，问阿雁昨晚谁搬走了铁箱。",
    chat: ["阿雁：先谈价，再谈消息。"],
  },
  {
    name: "潜行接近",
    focus: "码头仓库后门有人守着。",
    action: "我贴着墙摸到后门，尽量不发出声音。",
    chat: [],
  },
  {
    name: "进入战斗",
    focus: "两个码头帮成员堵住了巷口。",
    action: "许临拔枪瞄准最近的人，警告他让开。",
    chat: ["主持人：巷口的人把手伸进外套里。"],
  },
  {
    name: "失败与压力",
    focus: "玩家在废弃诊所里翻找病历。",
    action: "我强行撬开上锁的档案柜。",
    chat: [],
    pressure: 5,
  },
  {
    name: "无明确行动",
    focus: "雨声盖住了码头的动静，玩家停在仓库门口。",
    action: "",
    chat: ["主持人：你们站在门口，里面没有灯。"],
  },
  {
    name: "模组原文检索",
    focus: "玩家问起钟楼的传说。",
    action: "我问阿雁：钟楼那边为什么晚上不能去？",
    chat: [],
    moduleText: "北岸钟楼：每逢涨潮，钟楼底层的旧水道会被海水灌满。当地人说，潮水会带走留在钟楼里的人。林澈最后一次被人看见，就在钟楼附近的石阶上。",
  },
  {
    name: "长对话上下文",
    focus: "玩家和码头帮对峙了很久。",
    action: "我盯着领头的人，问他到底想要什么。",
    chat: Array.from({ length: 18 }, (_, index) => `玩家${(index % 2) + 1}：这是第 ${index + 1} 句试探，对方没有立刻回答。`),
  },
];

function validateResult(turn, debug, players) {
  const failures = [];
  const publicText = String(turn?.publicText || "");
  if (!publicText.trim() && !String(turn?.gmNote || "").trim()) {
    failures.push("publicText 和 gmNote 都为空");
  }
  if (/(我替你|自动为你|代替玩家决定|你决定|你选择)/.test(publicText)) {
    failures.push("publicText 里出现替玩家做决定的表达");
  }
  (turn?.checks || []).forEach((check, index) => {
    if (check.actor && !players.includes(check.actor)) {
      failures.push(`checks[${index}].actor 不是玩家：${check.actor}`);
    }
  });
  if ((turn?.choices || []).length > 4) failures.push("choices 超过 4 个");
  if (debug?.errors?.length) {
    failures.push(`校验错误：${debug.errors.slice(0, 2).join("；")}`);
  }
  if (debug?.turn && debug.turn.checks && debug.turn.checks.length > 5) {
    failures.push("checks 超过 5 个");
  }
  return failures;
}

const chrome = findChrome();
if (!chrome) {
  console.error("找不到 Chrome / Edge，无法运行回归测试。");
  process.exit(2);
}
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "trpg-regression-"));
const browser = spawn(
  chrome,
  [
    "--headless=new",
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "about:blank",
  ],
  { stdio: "ignore" },
);

let page = null;
let passed = 0;
let failed = 0;
let repaired = 0;
let warningsTotal = 0;

try {
  const ready = await waitFor(async () => {
    const response = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`);
    return response.ok;
  }, 20000);
  if (!ready) throw new Error("Chrome CDP 没有启动");

  page = await connect(CDP_PORT);
  await page.send("Page.navigate", { url: `${BASE_URL}/` });
  const appReady = await waitFor(() => page.evaluate(`typeof state !== "undefined" && typeof requestAiTurn === "function"`), 30000);
  if (!appReady) {
    console.log("PAGE_EVENTS", JSON.stringify(page.events.filter((event) => event.method === "Runtime.exceptionThrown" || event.method === "Log.entryAdded").slice(-8), null, 2).slice(0, 6000));
    throw new Error("页面没有初始化，后端是否已启动？");
  }

  const health = await fetch(`${BASE_URL}/api/health`).then((response) => response.json());
  if (!health.ok) throw new Error("后端健康检查失败");
  const aiConfig = await fetch(`${BASE_URL}/api/ai/config`).then((response) => response.json());
  if (!aiConfig.hasKey) throw new Error("服务端没有配置 AI Key");

  const isolation = await page.evaluate(`(() => {
    const player = state.players[0];
    state.aiPlayer = { ...getAiPlayer(), persona: "测试人设：说话短促，绝不主动开战", goals: "测试目标：找到钟楼入口" };
    const text = buildAiPlayerMessages(player).map((message) => message.content).join("\\n");
    return {
      chars: text.length,
      hasPersona: text.includes("测试人设：说话短促，绝不主动开战"),
      hasGoals: text.includes("测试目标：找到钟楼入口"),
      hasCanon: text.includes("铁箱原本属于失踪的考古学家林澈"),
      hasGmNotes: text.includes("关键线索可以分散在不同场景中"),
      hasNpcSecret: text.includes("他并非完全被绑架"),
      hasHiddenClue: text.includes("蜡烛燃烧后会留下类似盐霜的粉末"),
      hasModuleChunk: text.includes("【模组原文摘录】"),
    };
  })()`);
  const leaks = ["hasCanon", "hasGmNotes", "hasNpcSecret", "hasHiddenClue", "hasModuleChunk"].filter((key) => isolation[key]);
  if (leaks.length || isolation.chars > 5000 || !isolation.hasPersona || !isolation.hasGoals) {
    console.log(`AI 玩家信息隔离检查：FAIL（泄漏 ${leaks.join(",") || "无"}，人设 ${isolation.hasPersona ? "有" : "缺失"}，目标 ${isolation.hasGoals ? "有" : "缺失"}，${isolation.chars} 字符）`);
    failed += 1;
  } else {
    console.log(`AI 玩家信息隔离检查：PASS（${isolation.chars} 字符，人设/目标已注入，无 GM 秘密）`);
  }

  const filterCheck = await page.evaluate(`(() => {
    const samples = [
      "夜色压下来。（主持人提示：这里可以触发侦查）",
      "【GM】门后有人。",
      "系统提示：请玩家进行判定。",
      "（等待玩家行动）雨停了。",
      "雨停了。作为主持人，我建议你们检查箱子。",
      "你们检查箱子。判定结果：成功，发现线索。",
    ];
    const cleaned = samples.map((sample) => filterPublicNarration(sample));
    const metaPattern = /主持|GM|系统提示|作为AI|玩家|判定结果|等待玩家|提示|本回合|骰值/;
    return {
      cleaned,
      bad: cleaned.filter((text) => metaPattern.test(text)),
    };
  })()`);
  if (filterCheck.bad.length) {
    console.log(`公开叙述过滤检查：FAIL（残留 ${JSON.stringify(filterCheck.bad)}）`);
    failed += 1;
  } else {
    console.log("公开叙述过滤检查：PASS（主持提示/系统/判定/等待玩家已清除）");
  }

  console.log(`模型：${aiConfig.model} · 场景：${SCENARIOS.length} 个\n`);

  for (let index = 0; index < SCENARIOS.length; index += 1) {
    const scenario = SCENARIOS[index];
    await page.evaluate(`(() => {
      state = structuredClone(defaultState);
      restoreLocalAiSettings();
      state.session.focus = ${JSON.stringify(scenario.focus)};
      state.scene.title = ${JSON.stringify(scenario.name)};
      state.scene.location = "雾港";
      state.scene.plot = ${JSON.stringify(scenario.focus)};
      state.chatMessages = ${JSON.stringify((scenario.chat || []).map((text, i) => ({
        id: `m${i}`,
        speakerId: i % 2 === 0 ? "gm" : "p1",
        speakerName: i % 2 === 0 ? "主持人" : "沈砚",
        role: i % 2 === 0 ? "gm" : "player",
        visibility: "public",
        text,
        time: "测试",
      })))};
      state.session.pressure = ${Number(scenario.pressure ?? 2)};
      if (${JSON.stringify(scenario.moduleText || "")}) {
        state.module.content.chunks = buildModuleChunks(${JSON.stringify(scenario.moduleText || "")});
      }
      fillForm(forms.ai, state.ai);
      localStorage.removeItem(AI_DEBUG_KEY);
      aiDebugLog = [];
      return true;
    })()`);

    const started = Date.now();
    const retrievalFailures = [];
    if (scenario.moduleText) {
      const retrieved = await page.evaluate(`retrieveModuleChunks(aiTextTerms("钟楼"), 4).map((chunk) => chunk.index)`);
      if (!retrieved.length) retrievalFailures.push("模组原文检索为空（RAG 未命中）");
    }
    let turn = null;
    let error = "";
    try {
      turn = await page.evaluate(`requestAiTurn(${JSON.stringify(scenario.action || "")})`);
    } catch (caught) {
      error = caught.message || String(caught);
    }
    const elapsed = Date.now() - started;
    const debug = await page.evaluate(`aiDebugLog[aiDebugLog.length - 1] || null`);
    if (debug?.repaired) repaired += 1;
    const skipped = debug?.initialWarnings?.length || 0;
    warningsTotal += skipped;
    const players = await page.evaluate(`state.players.map((player) => player.name)`);
    const failures = error ? [error] : [...retrievalFailures, ...validateResult(turn, debug, players)];
    const tokens = debug?.call?.usage?.total_tokens || 0;
    const status = failures.length ? "FAIL" : "PASS";
    if (failures.length) failed += 1;
    else passed += 1;
    console.log(
      `[${index + 1}/${SCENARIOS.length}] ${scenario.name.padEnd(8, " ")} ${status}  ${(elapsed / 1000).toFixed(1)}s  ${tokens}tok${debug?.repaired ? "  repaired" : ""}${skipped ? `  skipped=${skipped}` : ""}`,
    );
    if (failures.length) {
      failures.slice(0, 3).forEach((failure) => console.log(`    - ${failure}`));
    } else {
      console.log(`    ${String(turn.publicText || turn.gmNote || "").replace(/\s+/g, " ").slice(0, 90)}`);
    }
    if (debug?.repaired && debug.initialErrors?.length) {
      console.log(`    repair: ${debug.initialErrors.slice(0, 3).join("；")}`);
    }
    if (skipped && debug.initialWarnings?.length) {
      console.log(`    skipped: ${debug.initialWarnings.slice(0, 3).join("；")}`);
    }
  }

  const exceptions = page.events.filter((event) => event.method === "Runtime.exceptionThrown").length;
  console.log(`\n结果：${passed} 通过，${failed} 失败，${repaired} 次自动修复，${warningsTotal} 条已跳过问题，页面异常 ${exceptions} 次`);
  process.exitCode = failed ? 1 : 0;
} finally {
  try {
    page?.close();
  } catch {}
  spawnSync("taskkill", ["/PID", String(browser.pid), "/T", "/F"], { stdio: "ignore" });
  await sleep(400);
  try {
    fs.rmSync(profile, { recursive: true, force: true });
  } catch {}
}
