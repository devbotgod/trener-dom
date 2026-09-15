// You vs You — Mini App
// Камера + MediaPipe Pose считает повторы, каждый повтор = удар по врагу.

// ---------------------------------------------------------------- config
const API = "/api";
const VENDOR = "./vendor";
const CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.12";

const tg = window.Telegram ? window.Telegram.WebApp : null;

function webApp() {
  try { return (window.Telegram && window.Telegram.WebApp) || tg || null; }
  catch (e) { return tg; }
}

/** Развернуть Mini App на весь экран (и держать развёрнутым). */
function expandWebApp() {
  const w = webApp();
  if (!w) return;
  try { w.ready(); } catch (e) {}
  try { w.expand(); } catch (e) {}
  try {
    if (typeof w.requestFullscreen === "function") w.requestFullscreen();
  } catch (e) {}
  try {
    if (typeof w.disableVerticalSwipes === "function") w.disableVerticalSwipes();
  } catch (e) {}
  try {
    if (w.themeParams && w.setHeaderColor) w.setHeaderColor("secondary_bg_color");
  } catch (e) {}
  try {
    if (w.setBackgroundColor) w.setBackgroundColor("#0b0e14");
  } catch (e) {}
}

expandWebApp();
try {
  const w0 = webApp();
  if (w0 && w0.onEvent) {
    w0.onEvent("viewportChanged", () => {
      try {
        if (w0.isExpanded === false) expandWebApp();
      } catch (e) {
        expandWebApp();
      }
    });
  }
} catch (e) {}

function getInitData() {
  try {
    const w = window.Telegram && window.Telegram.WebApp;
    const raw = (w && w.initData) ? String(w.initData) : "";
    if (raw) return raw;
  } catch (e) {}
  return "";
}

/** Персональный токен из кнопки бота (?s=...) — запасной вход, если initData пустой. */
function getLoginToken() {
  try {
    return new URLSearchParams(location.search).get("s") || "";
  } catch (e) {
    return "";
  }
}

function hasAuth() {
  return !!(getInitData() || getLoginToken());
}

const CONNECTIONS = [
  [11,12],[11,13],[13,15],[12,14],[14,16],
  [11,23],[12,24],[23,24],
  [23,25],[25,27],[24,26],[26,28],
  [27,31],[28,32],[15,17],[16,18],
];
const KEY_POINTS = [0,11,12,13,14,15,16,23,24,25,26,27,28];
const AVATARS = {
  ogre:"👹", ogre_boss:"👹", goblin:"👺", goblin_boss:"👺", troll:"🧌", troll_boss:"🧌",
  harpy:"🦅", harpy_boss:"🦅", undead:"💀", wolf:"🐺", wolf_boss:"🐺", lich:"☠️",
  demon:"😈", demon_boss:"🐉", hound:"🐕",
  slime:"🟢", orc:"👹", golem:"🗿", dragon:"🐉", spider:"🕷️",
};

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
const screens = { loading: $("screen-loading"), home: $("screen-home"), battle: $("screen-battle") };
function show(name) {
  Object.values(screens).forEach((s) => s.classList.remove("active"));
  screens[name].classList.add("active");
}
function apiUrl(p) {
  return API + p;
}
async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  const init = getInitData();
  const login = getLoginToken();
  // Шлём оба варианта: если initData битый, сервер возьмёт персональный ?s=
  if (init) {
    opts.headers["X-Telegram-Init-Data"] = init;
    opts.headers["Authorization"] = "tma " + init;
  }
  if (login) {
    opts.headers["X-YVY-Login"] = login;
  }
  if (!init && !login) {
    const err = new Error("no_init_data");
    err.status = 401;
    err.code = "no_init_data";
    throw err;
  }
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(apiUrl(path), opts);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const err = new Error((data && data.error) || ("API " + res.status));
    err.status = res.status;
    err.code = data && data.error;
    err.data = data;
    throw err;
  }
  return data;
}
function haptic(k = "light") { try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(k); } catch (e) {} }
function notify(t = "success") { try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(t); } catch (e) {} }
function hint(t) { $("b-hint").textContent = t; }
function pct(a, b) { return b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0; }

// ---------------------------------------------------------------- sound (WebAudio synth)
let actx = null;
let muted = localStorage.getItem("yvy_mute") === "1";          // звук боя
let uiMuted = localStorage.getItem("yvy_ui_mute") === "1";     // звук меню (независимо)
function audio() {
  if (!actx) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      actx = new AC({ latencyHint: "interactive" });
    } catch (e) {}
  }
  if (actx && actx.state === "suspended") actx.resume();
  return actx;
}
// --- мастер-шина: компрессор-лимитер + короткий reverb (объём вместо «писка») ---
let masterBus = null, reverbSend = null;
function buildBus(ac) {
  if (masterBus) return;
  masterBus = ac.createGain(); masterBus.gain.value = 0.85;
  const comp = ac.createDynamicsCompressor();
  comp.threshold.value = -16; comp.knee.value = 26; comp.ratio.value = 3.2;
  comp.attack.value = 0.003; comp.release.value = 0.2;
  masterBus.connect(comp).connect(ac.destination);
  // импульс для свёрточного реверба (экспоненциальный хвост)
  reverbSend = ac.createGain(); reverbSend.gain.value = 1;
  const conv = ac.createConvolver();
  const len = Math.floor(ac.sampleRate * 1.0), buf = ac.createBuffer(2, len, ac.sampleRate);
  for (let ch = 0; ch < 2; ch++) { const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.8); }
  conv.buffer = buf;
  reverbSend.connect(conv).connect(comp);
}
function voiceOut(g, wet) {
  g.connect(masterBus);
  if (wet > 0) { const s = actx.createGain(); s.gain.value = wet; g.connect(s); s.connect(reverbSend); }
}
function tone(freq, { type = "sine", dur = 0.15, gain = 0.2, slideTo = null, delay = 0, wet = 0.12, detune = 0 } = {}) {
  const ac = audio(); if (!ac || muted) return; buildBus(ac);
  const t0 = ac.currentTime + delay;
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, t0); if (detune) o.detune.value = detune;
  if (slideTo) o.frequency.exponentialRampToValueAtTime(Math.max(20, slideTo), t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.008);        // мягкая атака — нет щелчка
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g); voiceOut(g, wet); o.start(t0); o.stop(t0 + dur + 0.05);
}
function noise({ dur = 0.12, gain = 0.25, delay = 0, cutoff = 1400, wet = 0.1 } = {}) {
  const ac = audio(); if (!ac || muted) return; buildBus(ac);
  const t0 = ac.currentTime + delay;
  const buf = ac.createBuffer(1, Math.floor(ac.sampleRate * dur), ac.sampleRate);
  const d = buf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const n = ac.createBufferSource(); n.buffer = buf;
  const g = ac.createGain(); g.gain.setValueAtTime(gain, t0); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  const f = ac.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = cutoff;
  n.connect(f).connect(g); voiceOut(g, wet); n.start(t0); n.stop(t0 + dur);
}
function sfxHit(combo = 0) {                              // засчитанный повтор — сочный «панч»
  const c = Math.min(combo, 12), base = 165 + c * 10;
  tone(base, { type: "triangle", dur: 0.12, gain: 0.20, slideTo: base * 0.5, wet: 0.10 });
  tone(base * 2.01, { type: "sine", dur: 0.08, gain: 0.07, slideTo: base, wet: 0.06 });
  tone(64, { type: "sine", dur: 0.10, gain: 0.16, slideTo: 42, wet: 0 });   // низовой «тумк»
  noise({ dur: 0.045, gain: 0.09, cutoff: 1300, wet: 0.05 });
}
function sfxKill() {                                      // добивание врага
  tone(300, { type: "sawtooth", dur: 0.36, gain: 0.20, slideTo: 60, wet: 0.28 });
  tone(150, { type: "square", dur: 0.30, gain: 0.13, slideTo: 40, wet: 0.22 });
  tone(58, { type: "sine", dur: 0.24, gain: 0.22, slideTo: 30, wet: 0 });
  noise({ dur: 0.26, gain: 0.16, cutoff: 1700, wet: 0.12 });
}
function sfxLevel() {                                     // новый уровень — колокольчики
  [523, 659, 784, 1046].forEach((f, i) => {
    tone(f, { type: "triangle", dur: 0.5, gain: 0.14, delay: i * 0.09, wet: 0.3 });
    tone(f * 2, { type: "sine", dur: 0.4, gain: 0.045, delay: i * 0.09, wet: 0.3 });
  });
}
function sfxVictory() {                                   // победа над боссом — фанфары
  [523, 659, 784, 1046, 1318].forEach((f, i) => tone(f, { type: "triangle", dur: 0.5, gain: 0.16, delay: i * 0.11, wet: 0.32 }));
  tone(131, { type: "sine", dur: 1.2, gain: 0.13, wet: 0.2 });
  tone(196, { type: "sine", dur: 1.1, gain: 0.10, delay: 0.22, wet: 0.2 });
}
function sfxDefeat() {
  tone(220, { type: "sine", dur: 1.0, gain: 0.22, slideTo: 55, wet: 0.3 });
  tone(110, { type: "sine", dur: 1.1, gain: 0.13, slideTo: 40, wet: 0.3 });
}
function sfxClick() { tone(680, { type: "sine", dur: 0.05, gain: 0.08, wet: 0 }); }  // звук боя
function uiClick() {                                                                // звук меню (свой флаг)
  try { tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged(); } catch (e) {}
  const ac = audio(); if (!ac || uiMuted) return; buildBus(ac);
  const t0 = ac.currentTime;
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = "sine"; o.frequency.setValueAtTime(760, t0); o.frequency.exponentialRampToValueAtTime(620, t0 + 0.05);
  g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.07, t0 + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.06);
  o.connect(g).connect(masterBus); o.start(t0); o.stop(t0 + 0.08);
}

// ---------------------------------------------------------------- music (procedural loop)
let musicOn = localStorage.getItem("yvy_music") !== "0";
let musicTimer = null, musicStep = 0, musicStyle = "epic";  // epic (бой) | soft (простой режим)
const BASS = [110.0, 110.0, 146.83, 130.81, 110.0, 110.0, 98.0, 130.81]; // A A D C A A G C (минор, эпик)
const LEAD = [440, 523.25, 659.25, 587.33, 523.25, 440, 392, 493.88];
// мягкий мажор для женского/простого режима (спокойно, sine)
const SOFT_BASS = [130.81, 164.81, 196.00, 164.81, 146.83, 174.61, 220.00, 174.61];
const SOFT_LEAD = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.00, 698.46];
function musicNote(freq, dur, gain, type) {
  const ac = audio(); if (!ac || !musicOn) return; buildBus(ac);
  const t0 = ac.currentTime;
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = type; o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(gain, t0 + 0.03);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g); voiceOut(g, 0.25); o.start(t0); o.stop(t0 + dur + 0.05);
}
function musicTick() {
  if (!musicOn) { stopMusic(); return; }
  const ac = audio(); if (!ac || ac.state !== "running") return;
  if (musicStyle === "soft") {
    const bar = Math.floor(musicStep / 8) % SOFT_BASS.length;
    if (musicStep % 8 === 0) musicNote(SOFT_BASS[bar], 1.1, 0.06, "sine");
    if (musicStep % 4 === 0) musicNote(SOFT_LEAD[(musicStep / 4) % SOFT_LEAD.length | 0], 0.5, 0.03, "triangle");
  } else {
    const bar = Math.floor(musicStep / 4) % BASS.length;
    if (musicStep % 4 === 0) musicNote(BASS[bar], 0.55, 0.09, "triangle");
    if (musicStep % 2 === 0) musicNote(LEAD[(musicStep / 2) % LEAD.length | 0], 0.16, 0.035, "sawtooth");
  }
  musicStep++;
}
function startMusic() { if (!musicOn) return; audio(); stopMusic(); musicStep = 0; musicTimer = setInterval(musicTick, 155); }
function stopMusic() { if (musicTimer) { clearInterval(musicTimer); musicTimer = null; } }

// ---------------------------------------------------------------- visual fx
function flash(cls) {
  const el = $("fx-flash"); el.classList.remove("fx-red", "fx-gold");
  void el.offsetWidth; el.classList.add(cls);
}
function shake(strong) {
  const w = $("cam-wrap"), c = strong ? "shake-strong" : "shake";
  w.classList.remove("shake", "shake-strong"); void w.offsetWidth; w.classList.add(c);
  setTimeout(() => w.classList.remove(c), strong ? 480 : 220);
}
let combo = 0, comboT = null;
function bumpCombo() {
  combo++;
  if (combo >= 3) {
    const el = $("combo"); el.textContent = `COMBO ×${combo}`;
    el.classList.add("show"); el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop");
  }
  clearTimeout(comboT); comboT = setTimeout(resetCombo, 2600);
}
function resetCombo() { combo = 0; $("combo").classList.remove("show"); }

// ---------------------------------------------------------------- state
let state = null, enemy = null;
let localEnemyHp = 0, localYouHp = 0, repsThisEnemy = 0, displayCount = 0;
let fighting = false, flushing = false, paused = false;
let poseLandmarker = null;
let facingMode = "user";
let detector = null;
let skelColor = "#39e67e";
let lastExercise = null;
const shownHow = new Set();
// train mode
let trainMode = false, trainExercise = null, trainPending = 0, trainSessionXp = 0;

/* --- Арена 1v1 --- */
let duelMode = false;
let duelState = null;       // последний снимок дуэли
let duelMeta = null;
let duelExKey = "any";
let duelPollT = null;
let duelTimerT = null;
let duelSyncing = false;
let duelFinishedShown = false;
let arenaFriendLink = "";
let pendingDuelId = null;
let trainTarget = null, trainDoneKey = null;   // для «Тренировки дня» (простой режим)

// ---------------------------------------------------------------- errors
function showError(title, text, retry) {
  $("err-title").textContent = title;
  $("err-text").textContent = text;
  const box = $("error-box"); box.classList.add("show");
  $("err-btn").onclick = () => { box.classList.remove("show"); retry && retry(); };
}

// ---------------------------------------------------------------- load pose
async function loadPose() {
  let mod;
  try { mod = await import(`${VENDOR}/vision_bundle.mjs`); }
  catch (e) { mod = await import(`${CDN}/vision_bundle.mjs`); }
  const { FilesetResolver, PoseLandmarker } = mod;
  let fileset;
  try { fileset = await FilesetResolver.forVisionTasks(`${VENDOR}/wasm`); }
  catch (e) { fileset = await FilesetResolver.forVisionTasks(`${CDN}/wasm`); }
  const models = [
    `${VENDOR}/pose_landmarker_lite.task`,   // лёгкая — выше FPS, меньше лага (особенно боком)
    `${VENDOR}/pose_landmarker_full.task`,
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
  ];
  let lastErr;
  for (const mp of models) {
    try {
      poseLandmarker = await PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: mp, delegate: "GPU" },
        runningMode: "VIDEO", numPoses: 1,
        minPoseDetectionConfidence: 0.5, minPosePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
      });
      return;
    } catch (e) { lastErr = e; }
  }
  throw lastErr;
}

// ---------------------------------------------------------------- home / map
function renderHome() {
  const p = state.player;
  $("pl-level").textContent = p.level;
  $("pl-rank").textContent = state.gate.rank;
  $("pl-hp-bar").style.width = pct(p.hp, p.max_hp) + "%";
  $("pl-hp-text").textContent = `${p.hp} / ${p.max_hp}`;
  $("pl-xp-text").textContent = `${p.xp_this_level} / ${p.xp_next_level}`;
  $("pl-xp-bar").style.width = pct(p.xp_this_level, p.xp_next_level) + "%";
  $("train-left").textContent = p.train_left;
  $("streak-hdr").textContent = p.streak || 0;

  const kick = $("home-kicker");
  const kickSub = $("home-kicker-sub");
  const kickEye = $("home-kicker-eye");
  if (kick && kickSub) {
    if (p.mode === "simple") {
      kick.textContent = "Тренировка";
      kickSub.textContent = "сделай упражнения дня";
      if (kickEye) kickEye.textContent = "на сегодня";
    } else {
      kick.textContent = "Приключение";
      kickSub.textContent = "выбери уровень — и в бой";
      if (kickEye) kickEye.textContent = "сегодня";
    }
  }
  const sc = $("streak-chip");
  if (sc) sc.classList.toggle("on", (p.streak || 0) > 0);

  renderQuests();
  renderProfile();
  const simple = state.player.mode === "simple";
  $("screen-home").classList.toggle("simple", simple);
  $("pohod-adventure").style.display = simple ? "none" : "";
  $("pohod-simple").style.display = simple ? "" : "none";
  $("home-tip").style.display = localStorage.getItem("yvy_tip_seen") === "1" ? "none" : "";
  show("home");
  if (simple) renderWorkout(); else buildMap();
}

// ---------------------------------------------------------------- простой режим: тренировка дня
function renderWorkout() {
  const wk = state.workout || [];
  const doneN = wk.filter((w) => w.done).length;
  const day = new Date().getDate();
  const heroes = ["./img/hero_soft.jpg", "./img/hero_soft2.jpg"];
  $("wh-hero").style.backgroundImage = `url(${heroes[day % heroes.length]})`;
  const caps = ["Ты становишься лучше 🌸", "Каждый повтор — к цели ✨", "Сияй и работай над собой 💗", "Немного сегодня — сильнее завтра 🌷"];
  $("wh-cap").textContent = caps[day % caps.length];
  $("workout-sub").textContent = (wk.length && doneN >= wk.length)
    ? "🎉 Тренировка выполнена! Возвращайся завтра"
    : `Выполнено ${doneN}/${wk.length} · камера считает повторы`;
  const list = $("workout-list"); list.innerHTML = "";
  wk.forEach((w) => {
    const unit = w.mode === "hold" ? "сек" : "повт.";
    const el = document.createElement("div");
    el.className = "wk-item" + (w.done ? " done" : "");
    el.innerHTML = `
      <div class="wk-ic">${w.done ? "✅" : w.icon}</div>
      <div class="wk-body"><div class="wk-name">${w.name}</div>
        <div class="wk-meta">${w.target} ${unit}${w.mode === "manual" ? " · вручную" : ""}</div></div>
      <div class="wk-go">${w.done ? "✓" : "▶"}</div>`;
    if (!w.done) el.onclick = () => maybeWarmup(() => startSimpleExercise(w));
    list.appendChild(el);
  });
}

function startSimpleExercise(w) {
  uiClick();
  trainMode = true; trainExercise = w; trainTarget = w.target; trainDoneKey = w.key;
  trainPending = 0; trainSessionXp = 0; displayCount = 0; lastExercise = w.key;
  musicStyle = "soft";
  $("screen-battle").classList.add("train", "soft");
  $("b-gate-tag").textContent = "ТРЕНИРОВКА ДНЯ";
  $("t-ex-chip").textContent = `${w.icon} ${w.name}`;
  $("b-count-label").textContent = w.mode === "hold" ? "СЕК" : "ПОВТОРЫ";
  $("b-count").textContent = "0";
  $("t-xp-line").textContent = `Цель: ${w.target} ${w.mode === "hold" ? "сек" : "повт."}`;
  detector = w.mode === "manual" ? null : makeDetector(w.detector);
  show("battle");
  if (tg && tg.BackButton) tg.BackButton.show();
  startCamera();
  if (w.mode === "manual") { hint("Считай вручную — жми по кругу-счётчику"); $("b-counter").onclick = manualTap; }
  else { $("b-counter").onclick = null; }
  if (!shownHow.has(w.key)) { shownHow.add(w.key); showHow(w); }
}

function manualTap() {
  if (!trainMode || !trainDoneKey) return;
  onRep();
}

async function completeSimple() {
  const key = trainDoneKey; trainDoneKey = null; trainTarget = null;
  stopCamera();
  // дождаться in-flight flush, затем дослать остаток
  for (let i = 0; i < 40 && flushing; i++) await sleep(50);
  try { await flushTrain(); } catch (e) {}
  for (let i = 0; i < 20 && trainPending > 0; i++) {
    try { await flushTrain(); } catch (e) { break; }
  }
  try { state = await api("/workout_done", "POST", { exercise: key }); handleEvents(state.events || []); } catch (e) {}
  notify("success"); sfxKill(); flash("fx-gold"); confetti();
  const all = (state.workout || []).every((w) => w.done);
  showResult("✅", all ? "Тренировка выполнена!" : "Упражнение готово!",
    trainExercise.name, all ? "+бонус XP" : "+XP", () => { goHome(); switchTab("pohod"); });
}

// ---------------------------------------------------------------- вкладки
function switchTab(name) {
  uiClick();
  document.querySelectorAll(".tabpanel").forEach((el) => el.classList.toggle("active", el.id === "tab-" + name));
  document.querySelectorAll(".tabbtn").forEach((el) => el.classList.toggle("active", el.dataset.tab === name));
  if (name === "pohod") { const c = $("roadmap").querySelector(".map-node.open"); if (c) c.scrollIntoView({ block: "center" }); }
  if (name === "top") renderLeaderboard();
  if (name === "arena") {
    resumeArena().catch(() => {});
  }
}

function renderQuests() {
  const d = state.daily || { quests: [] };
  const p = state.player;
  $("streak-big").textContent = p.streak || 0;
  $("freeze-n").textContent = p.freezes || 0;
  $("streak-sub").textContent = (p.streak > 0)
    ? `🛡️ Дни отдыха (${p.freezes || 0}) спасут серию при пропуске`
    : "Сделай сегодня хоть один подход, чтобы начать серию";
  const list = $("quests-list"); list.innerHTML = "";
  (d.quests || []).forEach((q) => {
    const el = document.createElement("div");
    el.className = "quest" + (q.done ? " done" : "");
    el.innerHTML = `
      <div class="qic">${q.done ? "✅" : q.icon}</div>
      <div class="qbody">
        <div class="qtext">${q.text}</div>
        <div class="qbar"><i style="width:${pct(q.progress, q.target)}%"></i></div>
        <div class="qmeta">${q.progress} / ${q.target}</div>
      </div>
      <div class="qreward">${q.done ? "+" + q.reward + " ✓" : "+" + q.reward + " XP"}</div>`;
    list.appendChild(el);
  });
}

function renderProfile() {
  const p = state.player;
  $("pf-level").textContent = p.level;
  $("pf-rank").textContent = state.gate.rank;
  $("pf-title").textContent = p.title || "Новобранец";
  $("pf-avatar").textContent = p.avatar_emoji || "🧑";

  // график повторов по дням (пустое состояние в первый день)
  const hist = state.history || [];
  if (!hist.some((h) => h.reps > 0)) {
    $("chart").innerHTML = `<div class="chart-empty">📊 Тут появится твой прогресс по дням.<br>Начни первую тренировку!</div>`;
  } else {
    const maxR = Math.max(1, ...hist.map((h) => h.reps));
    $("chart").innerHTML = hist.map((h) => {
      const hpct = Math.round((h.reps / maxR) * 100);
      return `<div class="chart-col">
        <div class="chart-val">${h.reps || ""}</div>
        <div class="chart-bar" style="height:${Math.max(3, hpct)}%"></div>
        <div class="chart-lbl">${h.label}</div>
      </div>`;
    }).join("");
  }

  const wkDone = (state.workout || []).filter((w) => w.done).length;
  const wkTotal = (state.workout || []).length;
  const stats = (p.mode === "simple") ? [
    ["🔥", p.total_reps, "Всего повторов"],
    ["🔥", (p.streak || 0), "Стрик, дней"],
    ["⭐", p.level, "Уровень"],
    ["✅", `${wkDone}/${wkTotal}`, "Сегодня"],
  ] : [
    ["🔥", p.total_reps, "Всего повторов"],
    ["💀", p.total_kills, "Убийств"],
    ["🏰", p.gates_cleared, "Врат зачищено"],
    ["⚔️", p.damage, "Урон за повтор"],
    ["🔥", (p.streak || 0), "Стрик, дней"],
    ["⭐", p.level, "Уровень"],
  ];
  $("prof-stats").innerHTML = stats.map(
    (s) => `<div class="pstat"><div class="pv">${s[0]} ${s[1]}</div><div class="pl">${s[2]}</div></div>`
  ).join("");

  renderPremiumCard();
  renderDonateCard();

  // аватары
  $("avatar-grid").innerHTML = (state.avatars || []).map((a) =>
    `<div class="avatar-cell${a === p.avatar_emoji ? " sel" : ""}" data-av="${a}">${a}</div>`
  ).join("");
  $("avatar-grid").querySelectorAll(".avatar-cell").forEach((el) =>
    (el.onclick = () => doCustomize(null, el.dataset.av)));

  // титулы
  $("titles-list").innerHTML = (state.titles || []).map((t) => {
    const cls = t.selected ? " sel" : t.unlocked ? "" : " locked";
    const right = t.selected ? "✓" : t.unlocked ? "Выбрать" : "🔒 " + t.desc;
    return `<div class="title-row${cls}" data-title="${t.id}" data-open="${t.unlocked ? 1 : 0}">
      <span class="tr-name">${t.name}</span><span class="tr-right">${right}</span></div>`;
  }).join("");
  $("titles-list").querySelectorAll('.title-row[data-open="1"]').forEach((el) =>
    (el.onclick = () => doCustomize(el.dataset.title, null)));

  // ник в рейтинге
  $("nick-current").innerHTML =
    `<div class="prog-cur"><span class="pc-ic">🏷️</span><span class="pc-name">${p.nickname || "Охотник"}</span></div>
     <button class="set-mini" id="nick-change">Изменить</button>`;
  $("nick-change").onclick = openNickEdit;

  // цели тренировок
  const gmap = {}; (state.goal_groups || []).forEach((g) => (gmap[g.id] = g));
  const gchips = (p.goals || []).map((id) => gmap[id] ? `<span class="goal-chip mini">${gmap[id].icon} ${gmap[id].name}</span>` : "").join("");
  $("goals-current").innerHTML =
    `<div class="goals-chips">${gchips || '<span class="pl">не выбраны</span>'}</div>
     <button class="set-mini" id="goals-change">Изменить</button>`;
  $("goals-change").onclick = openGoalsEdit;

  // режим игры (сегментный переключатель)
  const curMode = p.mode || "adventure";
  document.querySelectorAll("#mode-seg .seg-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === curMode);
    b.onclick = async () => {
      if (b.dataset.mode === state.player.mode) return;
      uiClick();
      try { state = await api("/setup", "POST", { mode: b.dataset.mode }); renderHome(); switchTab("profile"); } catch (e) {}
    };
  });

  // сложность (сегментный переключатель)
  const curProg = p.program || "medium";
  document.querySelectorAll("#prog-seg .seg-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.prog === curProg);
    b.onclick = async () => {
      uiClick();
      try { state = await api("/program", "POST", { program: b.dataset.prog }); renderHome(); switchTab("profile"); } catch (e) {}
    };
  });
  const pinfo = (state.programs || []).find((x) => x.id === curProg);
  $("prog-desc").textContent = pinfo ? pinfo.desc : "";

  $("set-reminders-v").textContent = (p.reminders === false) ? "Выкл" : "Вкл";
  $("set-uisound-v").textContent = uiMuted ? "Выкл" : "Вкл";
  $("set-sound-v").textContent = muted ? "Выкл" : "Вкл";
  $("set-music-v").textContent = musicOn ? "Вкл" : "Выкл";
  renderRemindTime();
}

function pad2(n) { return String(n).padStart(2, "0"); }

function ensureRemindSelects() {
  const hourEl = $("remind-hour");
  const minEl = $("remind-minute");
  if (!hourEl || !minEl) return;
  if (!hourEl.options.length) {
    for (let h = 0; h < 24; h++) {
      const o = document.createElement("option");
      o.value = String(h);
      o.textContent = pad2(h);
      hourEl.appendChild(o);
    }
  }
  if (!minEl.options.length) {
    for (let m = 0; m < 60; m++) {
      const o = document.createElement("option");
      o.value = String(m);
      o.textContent = pad2(m);
      minEl.appendChild(o);
    }
  }
}

function renderRemindTime() {
  const box = $("remind-time");
  if (!box) return;
  const on = state.player.reminders !== false;
  box.hidden = !on;
  if (!on) return;
  ensureRemindSelects();
  const h = Number(state.player.reminder_hour ?? 19);
  const m = Number(state.player.reminder_minute ?? 0);
  const hourEl = $("remind-hour");
  const minEl = $("remind-minute");
  if (hourEl) hourEl.value = String(Math.max(0, Math.min(23, h)));
  if (minEl) minEl.value = String(Math.max(0, Math.min(59, m)));
  const lastH = (h + 2) % 24;
  const hint = $("remind-hint");
  if (hint) {
    hint.textContent = `Основное в ${pad2(h)}:${pad2(m)} МСК · ещё раз около ${pad2(lastH)}:${pad2(m)}, если не потренируешься`;
  }
}

async function setReminderTime(hour, minute) {
  const h = Math.max(0, Math.min(23, Math.floor(Number(hour))));
  const m = Math.max(0, Math.min(59, Math.floor(Number(minute))));
  if (!Number.isFinite(h) || !Number.isFinite(m)) {
    toast("Укажи корректное время");
    return;
  }
  const btn = $("remind-save");
  if (btn) { btn.disabled = true; btn.textContent = "…"; }
  try {
    state = await api("/reminders", "POST", {
      on: state.player.reminders !== false,
      hour: h,
      minute: m,
    });
    renderProfile();
    toast(`🔔 Напомню в ${pad2(h)}:${pad2(m)} МСК`);
  } catch (e) {
    toast("Не удалось сохранить время");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Сохранить"; }
  }
}

// ---------------------------------------------------------------- онбординг
let onbGender = null, onbGoals = new Set(), onbEdit = false, onbMode = "adventure";
function startOnboarding() { onbEdit = false; onbGender = null; onbGoals = new Set(); onbMode = "adventure"; onbStepGender(); $("onboard-modal").classList.add("show"); }
function openGoalsEdit() {
  uiClick(); onbEdit = true; onbGender = state.player.gender || "male"; onbMode = state.player.mode || "adventure";
  onbGoals = new Set(state.player.goals || []); onbStepGoals(); $("onboard-modal").classList.add("show");
}
function onbStepGender() {
  $("onboard-card").innerHTML = `
    <div class="modal-emoji">👋</div><h3>Кто ты?</h3>
    <p class="modal-tip">Подберём тренировки под тебя.</p>
    <div class="onb-genders">
      <button class="onb-g" data-g="male">🧑<span>Парень</span></button>
      <button class="onb-g" data-g="female">👩<span>Девушка</span></button>
    </div>`;
  $("onboard-card").querySelectorAll(".onb-g").forEach((b) => (b.onclick = () => {
    uiClick(); onbGender = b.dataset.g;
    onbMode = onbGender === "female" ? "simple" : "adventure";
    onbGoals = new Set(onbGender === "female" ? ["booty", "belly"] : ["chest", "back", "triceps"]);
    onbStepMode();
  }));
}
function onbStepMode() {
  $("onboard-card").innerHTML = `
    <div class="modal-emoji">🎮</div><h3>Как тренируемся?</h3>
    <p class="modal-tip">Можно сменить в профиле.</p>
    <div class="prog-list">
      <div class="ex-item${onbMode === "adventure" ? " sel" : ""}" data-m="adventure"><div class="ei">⚔️</div><div><div class="en">Приключение</div><div class="ed">RPG: врата, боссы, карта</div></div></div>
      <div class="ex-item${onbMode === "simple" ? " sel" : ""}" data-m="simple"><div class="ei">🎯</div><div><div class="en">Простая тренировка</div><div class="ed">Спокойный список — тренировка дня</div></div></div>
    </div>
    <button class="btn" id="onb-mode-next">Дальше</button>`;
  $("onboard-card").querySelectorAll(".ex-item").forEach((it) => (it.onclick = () => {
    uiClick(); onbMode = it.dataset.m;
    $("onboard-card").querySelectorAll(".ex-item").forEach((x) => x.classList.toggle("sel", x === it));
  }));
  $("onb-mode-next").onclick = () => { uiClick(); onbStepGoals(); };
}
function onbStepGoals() {
  const groups = state.goal_groups || [];
  const chip = (g) => `<button class="goal-chip${onbGoals.has(g.id) ? " sel" : ""}" data-id="${g.id}"><span class="gi">${g.icon}</span><span class="gn">${g.name}</span></button>`;
  const goalG = groups.filter((g) => g.kind === "goal");
  const muscleG = groups.filter((g) => g.kind !== "goal");
  $("onboard-card").innerHTML = `
    <div class="modal-emoji">🎯</div><h3>Твоя цель?</h3>
    <p class="modal-tip">Выбери цель или конкретные мышцы (можно несколько). Тренировки подстроятся.</p>
    <div class="goal-sub">Цели</div>
    <div class="goal-grid two">${goalG.map(chip).join("")}</div>
    <div class="goal-sub">Или по мышцам</div>
    <div class="goal-grid two">${muscleG.map(chip).join("")}</div>
    <div class="goal-legend" id="goal-legend"></div>
    <button class="btn" id="onb-done">${onbEdit ? "Сохранить" : "Начать"}</button>`;
  $("onboard-card").querySelectorAll(".goal-chip").forEach((c) => (c.onclick = () => {
    uiClick(); const id = c.dataset.id;
    if (onbGoals.has(id)) onbGoals.delete(id); else onbGoals.add(id);
    refreshGoalChips();
  }));
  refreshGoalChips();
  $("onb-done").onclick = finishOnboarding;
}

// подсветка мышц, задействованных выбранными целями
function onbEngagedMuscles() {
  const gmap = {}; (state.goal_groups || []).forEach((g) => (gmap[g.id] = g));
  const eng = new Set();
  onbGoals.forEach((id) => { const g = gmap[id]; if (g && g.expand) g.expand.forEach((m) => eng.add(m)); });
  return eng;
}
function refreshGoalChips() {
  const eng = onbEngagedMuscles();
  $("onboard-card").querySelectorAll(".goal-chip").forEach((c) => {
    const id = c.dataset.id;
    c.classList.toggle("sel", onbGoals.has(id));
    c.classList.toggle("hint", !onbGoals.has(id) && eng.has(id));
  });
  const lg = $("goal-legend");
  if (lg) lg.textContent = eng.size ? "🔵 Подсвечены мышцы, которые задействует твоя цель" : "";
}
async function finishOnboarding() {
  uiClick();
  if (onbGoals.size === 0) { toast("Выбери хотя бы одну группу"); return; }
  try { state = await api("/setup", "POST", { gender: onbGender, mode: onbMode, goals: [...onbGoals] }); } catch (e) {}
  $("onboard-modal").classList.remove("show");
  renderHome();
  if (!onbEdit && state.player.needs_program) openProgram();
}

function openProgram() {
  uiClick();
  const list = $("prog-list"); list.innerHTML = "";
  (state.programs || []).forEach((pr) => {
    const it = document.createElement("div");
    it.className = "ex-item" + (pr.selected ? " sel" : "");
    it.innerHTML = `<div class="ei">${pr.icon}</div><div><div class="en">${pr.name}</div><div class="ed">${pr.desc}</div></div>`;
    it.onclick = () => setProgram(pr.id);
    list.appendChild(it);
  });
  $("program-modal").classList.add("show");
}
async function setProgram(id) {
  uiClick();
  try { state = await api("/program", "POST", { program: id }); } catch (e) {}
  $("program-modal").classList.remove("show");
  renderHome();
}

async function doCustomize(title, avatar) {
  uiClick();
  try {
    const body = {};
    if (title) body.title = title;
    if (avatar) body.avatar = avatar;
    state = await api("/customize", "POST", body);
    renderProfile();
  } catch (e) {}
}

const SEG = 165;               // расстояние между узлами по вертикали (px)
const TOP_PAD = 64;            // отступ сверху, чтобы карта не лезла под меню
const _XS = [30, 50, 70, 50];  // плавная змейка: лево-центр-право-центр
function mapX(i) { return _XS[i % 4]; }
function mapY(i) { return TOP_PAD + i * SEG; }        // px

function buildMap() {
  const gates = state.gates;
  const road = $("roadmap");
  const last = gates.length - 1;
  const H = mapY(last) + TOP_PAD;
  road.style.height = H + "px";

  const prem = state.premium || {};
  const banner = $("premium-banner");
  if (banner) {
    if (prem.premium) {
      banner.style.display = "none";
    } else {
      banner.style.display = "";
      banner.innerHTML = `<div class="prem-ic">⭐</div><div class="prem-body"><b>Premium</b> · первые ${prem.free_biome_count || 2} локации бесплатно, дальше — ${prem.stars_price || 150} Stars</div><div class="prem-go">Открыть</div>`;
      banner.onclick = () => { uiClick(); showPremiumPaywall(); };
    }
  }

  // биом-полосы: плотно стыкуются по серединам между узлами (без наездов и щелей)
  // названия — отдельным слоем поверх (чтобы фильтр полосы их не гасил)
  let bands = "", labels = "";
  let gi = 0;
  while (gi < gates.length) {
    const biome = gates[gi].biome;
    let end = gi;
    while (end + 1 < gates.length && gates[end + 1].biome === biome) end++;
    const top = gi === 0 ? 0 : (mapY(gi - 1) + mapY(gi)) / 2;
    const bottom = end === last ? H : (mapY(end) + mapY(end + 1)) / 2;
    const unlocked = gates[gi].unlocked;
    const premLock = !!gates[gi].premium_locked;
    bands += `<div class="map-band ${unlocked ? "" : "band-locked"}${premLock ? " band-premium" : ""}" style="top:${top}px;height:${bottom - top}px;background-image:url(./img/biome_${biome}.jpg)"></div>`;
    labels += `<div class="biome-chip${premLock ? " prem" : ""}" style="top:${top + 12}px;border-color:${gates[gi].color}">${premLock ? "⭐ " : ""}${gates[gi].biome_name}</div>`;
    gi = end + 1;
  }

  // путь (SVG) в реальных пикселях — сплошная тропа, плавная змейка через центры узлов
  const W = road.clientWidth || (window.innerWidth - 32);
  const PX = (i) => (mapX(i) / 100) * W;
  let d = "";
  gates.forEach((g, i) => {
    const x = PX(i), y = mapY(i);
    if (i === 0) d = `M ${x} ${y}`;
    else {
      const px = PX(i - 1), py = mapY(i - 1);
      d += ` C ${px} ${py + SEG * 0.5} ${x} ${y - SEG * 0.5} ${x} ${y}`;
    }
  });
  const svg = `<svg class="map-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <path d="${d}" fill="none" stroke="rgba(0,0,0,0.45)" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${d}" fill="none" stroke="#e6c78e" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${d}" fill="none" stroke="#fff4d8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
  </svg>`;

  // узлы
  let nodes = "";
  gates.forEach((g, i) => {
    const x = mapX(i), y = mapY(i);
    const stateCls = g.cleared ? "done" : g.unlocked ? "open" : (g.premium_locked ? "premium" : "locked");
    const boss = g.is_biome_boss ? "boss" : "";
    const overlay = g.cleared ? `<span class="node-badge done">✓</span>`
      : g.premium_locked ? `<span class="node-badge lock">⭐</span>`
      : !g.unlocked ? `<span class="node-badge lock">🔒</span>` : "";
    const crown = g.is_biome_boss ? `<span class="node-crown">👑</span>` : "";
    nodes += `<div class="map-node ${stateCls} ${boss}" data-gate="${g.id}" data-open="${g.unlocked ? 1 : 0}" data-premium="${g.premium_locked ? 1 : 0}"
        style="left:${x}%;top:${y}px">
      ${crown}
      <div class="node-circle" style="--gc:${g.color}">
        <img src="./img/${g.node_avatar}.jpg" onerror="this.replaceWith(document.createTextNode('👾'))">
        ${overlay}
        <span class="node-rank" style="background:${g.color}">${i + 1}</span>
      </div>
      <div class="node-label">${g.name}</div>
    </div>`;
  });

  road.innerHTML = bands + svg + nodes + labels;
  road.querySelectorAll('.map-node[data-open="1"]').forEach((el) => {
    el.onclick = () => { uiClick(); maybeWarmup(() => enterGate(el.dataset.gate)); };
  });
  road.querySelectorAll('.map-node[data-premium="1"]').forEach((el) => {
    // paywall только если до локации уже дошли по прогрессу
    const g = (state.gates || []).find((x) => x.id === el.dataset.gate);
    if (g && g.progression_unlocked) {
      el.onclick = () => { uiClick(); showPremiumPaywall(); };
    }
  });
  // проскроллить к текущему уровню
  const cur = road.querySelector(".map-node.open");
  if (cur) setTimeout(() => cur.scrollIntoView({ block: "center", behavior: "smooth" }), 60);
}

// ---------------------------------------------------------------- how-to modal
let howFig = null;
function showHow(ex) {
  if (!ex) return;
  $("how-icon").textContent = ex.icon || "🔥";
  $("how-title").textContent = ex.name || "Упражнение";
  $("how-text").textContent = ex.how || "";
  $("how-tip").textContent = ex.tip ? "📷 " + ex.tip : "";
  if (howFig) { howFig.stop(); howFig = null; }
  document.body.classList.toggle("simple-mode", !!(state && state.player && state.player.mode === "simple"));
  const fc = $("how-fig");
  if (fc && ex.key && window.YvyFig && YvyFig.has(ex.key)) {
    fc.style.display = ""; $("how-icon").style.display = "none";
    howFig = YvyFig.makeInto(fc, ex.key);
  } else if (fc) {
    fc.style.display = "none"; $("how-icon").style.display = "";
  }
  $("how-modal").classList.add("show");
  syncBack();
}
$("how-close").onclick = () => { $("how-modal").classList.remove("show"); if (howFig) { howFig.stop(); howFig = null; } syncBack(); };

function currentExerciseInfo() {
  if (duelMode && duelState && duelState.exercise) return duelState.exercise;
  if (trainMode && trainExercise) return trainExercise;
  if (enemy) return { key: enemy.exercise, icon: enemy.exercise_icon, name: enemy.exercise_name, how: enemy.how, tip: enemy.tip };
  return null;
}

// ---------------------------------------------------------------- gate
async function enterGate(gateId) {
  const g = (state.gates || []).find((x) => x.id === gateId);
  if (g && g.premium_locked) { showPremiumPaywall(); return; }
  trainMode = false;
  musicStyle = "epic";
  $("screen-battle").classList.remove("train", "soft");
  try { state = await api("/gate", "POST", { gate_id: gateId }); }
  catch (e) {
    if (e && e.code === "premium_required") { showPremiumPaywall(); return; }
    showError("Ошибка", "Не удалось открыть Врата.", () => enterGate(gateId));
    return;
  }
  enemy = state.enemy; localYouHp = state.player.hp;
  displayCount = 0; repsThisEnemy = 0; lastExercise = null;
  $("b-gate-tag").textContent = state.gate.subtitle;
  if (enemy) loadEnemy(enemy);
  updateYouHp();
  $("b-count").textContent = "0";
  show("battle");
  if (tg && tg.BackButton) tg.BackButton.show();
  startCamera();
}

function loadEnemy(en) {
  if (fighting && lastExercise && lastExercise !== en.exercise) {
    toast(`Смена: ${en.exercise_icon} ${en.exercise_name}`, 2600);
  }
  lastExercise = en.exercise;
  enemy = en;
  localEnemyHp = en.hp; repsThisEnemy = 0;
  const av = $("b-avatar");
  av.className = "enemy-avatar" + (en.kind === "boss" ? " boss" : "");
  av.textContent = "";
  const img = new Image();
  img.onerror = () => { av.textContent = AVATARS[en.avatar] || "👹"; };
  img.src = `./img/${en.avatar}.jpg`;
  av.appendChild(img);
  av.classList.add("spawn"); setTimeout(() => av.classList.remove("spawn"), 420);
  $("b-enemy-name").textContent = en.name;
  $("b-ex-chip").textContent = `${en.exercise_icon} ${en.exercise_name}`;
  $("b-count-label").textContent = en.exercise_type === "hold" ? "СЕК" : "ПОВТОРЫ";
  updateEnemyHp();
  const dots = $("b-wave-dots"); dots.innerHTML = "";
  for (let i = 0; i < en.total; i++) {
    const d = document.createElement("i");
    d.className = i < en.index ? "dead" : i === en.index ? "cur" : "";
    dots.appendChild(d);
  }
  detector = makeDetector(en.detector);
  if (!detector && en.detector && en.detector.kind === "manual") {
    $("b-counter").onclick = () => { if (fighting) onRep(); };
    hint("Ручной счёт: жми по кругу-счётчику после каждого повтора");
  } else {
    if (!trainMode) $("b-counter").onclick = null;
    hint(en.tip || "Готов? Погнали.");
  }
  // авто-инструкция при первом появлении упражнения
  if (!shownHow.has(en.exercise)) { shownHow.add(en.exercise); showHow(currentExerciseInfo()); }
}

function updateEnemyHp() {
  const hp = Math.max(0, Math.round(localEnemyHp));
  $("b-enemy-hp-bar").style.width = pct(hp, enemy.max_hp) + "%";
  $("b-enemy-hp-text").textContent = `HP ${hp} / ${enemy.max_hp}`;
}
function updateYouHp() {
  const hp = Math.max(0, Math.round(localYouHp));
  $("b-you-hp-bar").style.width = pct(hp, state.player.max_hp) + "%";
  $("b-you-hp-text").textContent = `${hp} / ${state.player.max_hp}`;
}

// ---------------------------------------------------------------- training
function openExPicker() {
  const list = $("ex-list"); list.innerHTML = "";
  (state.exercises || []).forEach((ex) => {
    const it = document.createElement("div");
    it.className = "ex-item";
    it.innerHTML = `<div class="ei">${ex.icon}</div>
      <div><div class="en">${ex.name}</div><div class="ed">${ex.type === "hold" ? "удержание" : "повторы"} · +XP</div></div>`;
    it.onclick = () => { $("ex-modal").classList.remove("show"); startTraining(ex); };
    list.appendChild(it);
  });
  $("ex-modal").classList.add("show");
  syncBack();
}
$("ex-cancel").onclick = () => { $("ex-modal").classList.remove("show"); syncBack(); };

function startTraining(ex) {
  trainMode = true; trainExercise = ex; trainPending = 0; trainSessionXp = 0;
  trainTarget = null; trainDoneKey = null; $("b-counter").onclick = null;
  musicStyle = "epic"; $("screen-battle").classList.remove("soft");
  displayCount = 0; lastExercise = ex.key;
  $("screen-battle").classList.add("train");
  $("b-gate-tag").textContent = "СВОБОДНАЯ ТРЕНИРОВКА";
  $("t-ex-chip").textContent = `${ex.icon} ${ex.name}`;
  $("b-count-label").textContent = ex.type === "hold" ? "СЕК" : "ПОВТОРЫ";
  $("b-count").textContent = "0";
  updateTrainLine();
  detector = makeDetector(ex.detector);
  if (!detector && ex.detector && ex.detector.kind === "manual") {
    $("b-counter").onclick = () => { if (trainMode) onRep(); };
    hint("Ручной счёт: жми по кругу-счётчику после каждого повтора");
  } else { $("b-counter").onclick = null; }
  show("battle");
  if (tg && tg.BackButton) tg.BackButton.show();
  startCamera();
  if (!shownHow.has(ex.key)) { shownHow.add(ex.key); showHow(ex); }
}

function updateTrainLine() {
  const left = state.player.train_left;
  $("t-xp-line").textContent = `+${trainSessionXp} XP · осталось ${left}`;
  if (left <= 0) $("t-xp-line").textContent = `Лимит опыта на сегодня набран (${trainSessionXp} XP). Красава!`;
}

async function flushTrain() {
  if (flushing || trainPending <= 0) return;
  flushing = true;
  const reps = trainPending; trainPending = 0;
  try {
    const snap = await api("/train", "POST", { reps });
    state = snap;
    for (const ev of (snap.events || [])) if (ev.type === "train") trainSessionXp += ev.xp;
    handleEvents(snap.events || []);
    updateTrainLine();
  } catch (e) {
    trainPending += reps; // вернуть несохранённые повторы
    toast("🔁 Связь пропала — сохраню чуть позже");
  }
  finally { flushing = false; }
}

// ---------------------------------------------------------------- toast
let toastT = null;
function toast(text, ms = 1600) {
  const global = $("app-toast");
  const battle = $("status-pill");
  const inBattle = $("screen-battle") && $("screen-battle").classList.contains("active");
  const p = (inBattle && battle) ? battle : (global || battle);
  if (!p) {
    try {
      const w = webApp();
      if (w && w.showAlert) w.showAlert(String(text));
    } catch (e) {}
    return;
  }
  p.textContent = text;
  p.classList.add("show");
  clearTimeout(toastT);
  toastT = setTimeout(() => p.classList.remove("show"), ms);
}

/** Открыть именно нативное окно Stars в Mini App (не уводить в чат). */
function openStarsInvoice(invoiceUrl, onStatus) {
  const w = webApp();
  if (!w || typeof w.openInvoice !== "function") return false;
  try {
    w.openInvoice(String(invoiceUrl), (status) => {
      try { if (typeof onStatus === "function") onStatus(status); } catch (e) {}
    });
    return true;
  } catch (e) {
    console.warn("openInvoice failed", e);
    return false;
  }
}

let premiumBusy = false;

async function sendPremiumInvoiceToChat() {
  const inv = await api("/premium/invoice", "POST", { send_to_chat: true });
  if (inv.already) {
    state = inv;
    renderHome();
    toast("⭐ Premium уже активен");
    return true;
  }
  return !!inv.sent;
}

async function buyPremiumStars() {
  uiClick();
  if (premiumBusy) return;
  premiumBusy = true;
  const btn = $("prem-buy");
  if (btn) { btn.disabled = true; btn.textContent = "Готовлю счёт…"; }
  try {
    const inv = await api("/premium/invoice", "POST", {});
    if (inv.already) {
      state = inv;
      hidePremiumPaywall();
      renderHome();
      toast("⭐ Premium уже активен");
      return;
    }
    if (!inv.invoice_url) throw new Error("no invoice");

    toast("Открываю оплату…");
    const opened = openStarsInvoice(inv.invoice_url, async (status) => {
      if (status === "paid") {
        hidePremiumPaywall();
        try { state = await api("/premium/confirm", "POST", {}); } catch (e) {}
        let ok = false;
        for (let i = 0; i < 15; i++) {
          await sleep(500);
          try {
            state = await api("/state");
            if (state.premium && state.premium.premium) { ok = true; break; }
          } catch (e) {}
        }
        renderHome();
        notify("success");
        toast(ok ? "🎉 Premium активирован!" : "Оплата прошла — обновляю Premium…", 2800);
        if (!ok) {
          setTimeout(async () => {
            try {
              state = await api("/state");
              renderHome();
              if (state.premium && state.premium.premium) toast("🎉 Premium активирован!", 2400);
            } catch (e) {}
          }, 2500);
        }
      } else if (status === "cancelled") {
        toast("Оплата отменена");
      } else if (status === "failed") {
        // Не шлём второй счёт в чат сами — есть кнопка «Отправить счёт в чат бота»
        toast("Не открылось. Нажми «Отправить счёт в чат бота»", 3200);
      }
    });

    if (opened) {
      hidePremiumPaywall();
    } else {
      toast("В этом Telegram нет окна оплаты. Жми «Отправить счёт в чат бота»", 3400);
    }
  } catch (e) {
    showError(
      "Оплата",
      "Не удалось создать счёт Stars. Попробуй ещё раз или отправь счёт в чат бота.",
      buyPremiumStars
    );
  } finally {
    premiumBusy = false;
    if (btn) {
      btn.disabled = false;
      const price = ($("prem-price") && $("prem-price").textContent) || "150";
      btn.textContent = `⭐ Купить · ${price} Stars`;
    }
  }
}

(() => {
  const buy = $("prem-buy");
  const cancel = $("prem-cancel");
  const chat = $("prem-chat");
  if (buy) buy.onclick = buyPremiumStars;
  if (cancel) cancel.onclick = () => { uiClick(); hidePremiumPaywall(); };
  if (chat) {
    chat.onclick = async () => {
      uiClick();
      chat.disabled = true;
      try {
        await sendPremiumInvoiceToChat();
        hidePremiumPaywall();
        toast("⭐ Счёт в чате с ботом — открой и оплати", 3200);
      } catch (e) {
        toast("Не удалось отправить счёт");
      } finally {
        chat.disabled = false;
      }
    };
  }
})();

// ---------------------------------------------------------------- premium (Stars)
function renderPremiumCard() {
  const box = $("premium-card");
  if (!box) return;
  const prem = state.premium || {};
  if (prem.premium) {
    box.className = "premium-card on";
    box.innerHTML = `<div class="pc-ic">⭐</div><div class="pc-body"><b>Premium активен</b><span>${prem.vip ? "VIP-доступ" : "Все локации открыты"}</span></div>`;
    box.onclick = null;
  } else {
    box.className = "premium-card";
    box.innerHTML = `<div class="pc-ic">⭐</div><div class="pc-body"><b>Открыть Premium</b><span>Все локации · ${prem.stars_price || 150} Stars</span></div><div class="pc-go">→</div>`;
    box.onclick = () => { uiClick(); showPremiumPaywall(); };
  }
}

function showPremiumPaywall() {
  const prem = (state && state.premium) || {};
  if (prem.premium) { toast("Premium уже активен"); return; }
  const names = (prem.free_biome_names || ["Зелёные земли", "Выжженная пустошь"]).join(" и ");
  $("prem-price").textContent = String(prem.stars_price || 150);
  $("prem-free").textContent = names;
  $("premium-modal").classList.add("show");
  if (typeof syncBack === "function") syncBack();
}

function hidePremiumPaywall() {
  $("premium-modal").classList.remove("show");
  if (typeof syncBack === "function") syncBack();
}

// ---------------------------------------------------------------- donate (Stars)
const DONATE_MIN = 1;
const DONATE_MAX = 10000;

function renderDonateCard() {
  const box = $("donate-card");
  if (!box) return;
  const donated = ((state && state.premium) || {}).donated_stars || 0;
  const sub = $("donate-sub");
  if (sub) {
    sub.textContent = donated > 0
      ? `Ты уже поддержал на ${donated} ⭐ — спасибо!`
      : "Любая сумма Stars — спасибо за поддержку";
  }
  box.onclick = () => { uiClick(); showDonateModal(); };
}

function showDonateModal() {
  const input = $("donate-amount");
  if (input && !input.value) input.value = "50";
  const amt = Number((input && input.value) || 50);
  syncDonateChips(amt);
  $("donate-modal").classList.add("show");
  if (typeof syncBack === "function") syncBack();
  if (Number.isFinite(amt)) prefetchDonateInvoice(amt);
}

function hideDonateModal() {
  $("donate-modal").classList.remove("show");
  if (typeof syncBack === "function") syncBack();
}

function showDonateThanks(amount) {
  const el = $("donate-thanks-text");
  if (el) {
    el.textContent =
      "Спасибо, что помогаете развиваться проекту — мы это очень ценим. "
      + "Благодаря такой поддержке YOU vs YOU становится лучше.";
  }
  const m = $("donate-thanks-modal");
  if (m) m.classList.add("show");
  if (typeof syncBack === "function") syncBack();
  try {
    const w = webApp();
    if (w && w.HapticFeedback) w.HapticFeedback.notificationOccurred("success");
  } catch (e) {}
}

function hideDonateThanks() {
  const m = $("donate-thanks-modal");
  if (m) m.classList.remove("show");
  if (typeof syncBack === "function") syncBack();
}

function syncDonateChips(amount) {
  document.querySelectorAll(".donate-chip").forEach((el) => {
    el.classList.toggle("on", Number(el.dataset.amt) === amount);
  });
}

let donateInvoiceCache = { amount: 0, url: "", at: 0 };
let donatePrefetchSeq = 0;

async function prefetchDonateInvoice(amount) {
  if (!amount || amount < DONATE_MIN || amount > DONATE_MAX) return;
  const seq = ++donatePrefetchSeq;
  try {
    const inv = await api("/donate/invoice", "POST", { amount });
    if (seq !== donatePrefetchSeq) return;
    if (inv && inv.invoice_url) {
      donateInvoiceCache = { amount, url: inv.invoice_url, at: Date.now() };
    }
  } catch (e) {}
}

function readDonateAmount() {
  const raw = ($("donate-amount") && $("donate-amount").value) || "";
  const n = Math.floor(Number(raw));
  if (!Number.isFinite(n) || n < DONATE_MIN || n > DONATE_MAX) return null;
  return n;
}

let donateBusy = false;

async function payDonateStars() {
  uiClick();
  if (donateBusy) return;
  const amount = readDonateAmount();
  if (amount == null) {
    toast(`Укажи сумму от ${DONATE_MIN} до ${DONATE_MAX} ⭐`);
    return;
  }
  const btn = $("donate-pay");
  donateBusy = true;
  if (btn) { btn.disabled = true; btn.textContent = "Готовлю счёт…"; }

  const cacheFresh = (
    donateInvoiceCache.amount === amount
    && donateInvoiceCache.url
    && (Date.now() - donateInvoiceCache.at) < 45000
  );

  try {
    let invoiceUrl = cacheFresh ? donateInvoiceCache.url : "";
    if (!invoiceUrl) {
      const inv = await api("/donate/invoice", "POST", { amount });
      if (!inv.invoice_url) throw new Error("no invoice");
      invoiceUrl = inv.invoice_url;
      donateInvoiceCache = { amount, url: invoiceUrl, at: Date.now() };
    }
    toast("Открываю оплату…");
    const opened = openStarsInvoice(invoiceUrl, async (status) => {
      if (status === "paid") {
        hideDonateModal();
        donateInvoiceCache = { amount: 0, url: "", at: 0 };
        try { state = await api("/premium/confirm", "POST", {}); } catch (e) {}
        for (let i = 0; i < 6; i++) {
          await sleep(350);
          try {
            state = await api("/state");
            break;
          } catch (e) {}
        }
        renderHome();
        notify("success");
        showDonateThanks(amount);
      } else if (status === "cancelled") {
        toast("Пожертвование отменено");
      } else if (status === "failed") {
        toast("Не открылось. Нажми «Отправить счёт в чат бота»", 3200);
      }
    });
    if (opened) {
      hideDonateModal();
    } else {
      toast("В этом Telegram нет окна оплаты. Жми «Отправить счёт в чат бота»", 3400);
    }
  } catch (e) {
    showError("Пожертвование", "Не удалось создать счёт Stars. Попробуй ещё раз или отправь счёт в чат.", payDonateStars);
  } finally {
    donateBusy = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = "⭐ Пожертвовать";
    }
  }
}

async function sendDonateToChat() {
  uiClick();
  const amount = readDonateAmount();
  if (amount == null) {
    toast(`Укажи сумму от ${DONATE_MIN} до ${DONATE_MAX} ⭐`);
    return;
  }
  const btn = $("donate-chat");
  if (btn) { btn.disabled = true; btn.textContent = "Отправляю…"; }
  try {
    await api("/donate/invoice", "POST", { amount, send_to_chat: true });
    hideDonateModal();
    toast("⭐ Счёт в чате с ботом — после оплаты там же будет «спасибо»", 3400);
  } catch (e) {
    toast("Не удалось отправить счёт");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Отправить счёт в чат бота";
    }
  }
}

(() => {
  const pay = $("donate-pay");
  const cancel = $("donate-cancel");
  const chat = $("donate-chat");
  const thanksOk = $("donate-thanks-ok");
  const input = $("donate-amount");
  if (pay) pay.onclick = payDonateStars;
  if (chat) chat.onclick = sendDonateToChat;
  if (cancel) cancel.onclick = () => { uiClick(); hideDonateModal(); };
  if (thanksOk) thanksOk.onclick = () => { uiClick(); hideDonateThanks(); };
  document.querySelectorAll(".donate-chip").forEach((el) => {
    el.onclick = () => {
      uiClick();
      const amt = Number(el.dataset.amt);
      if (input) input.value = String(amt);
      syncDonateChips(amt);
      prefetchDonateInvoice(amt);
    };
  });
  if (input) {
    let t = null;
    input.addEventListener("input", () => {
      const n = Math.floor(Number(input.value));
      syncDonateChips(Number.isFinite(n) ? n : -1);
      clearTimeout(t);
      t = setTimeout(() => {
        const a = readDonateAmount();
        if (a != null) prefetchDonateInvoice(a);
      }, 350);
    });
  }
})();

// ---------------------------------------------------------------- pose helpers
function vis(lm, i) { return lm[i] && (lm[i].visibility === undefined || lm[i].visibility > 0.4); }
function avgY(lm, idxs) { let s = 0, n = 0; for (const i of idxs) { if (!vis(lm, i)) return null; s += lm[i].y; n++; } return n ? s / n : null; }
function avgX(lm, idxs) { let s = 0, n = 0; for (const i of idxs) { if (!vis(lm, i)) return null; s += lm[i].x; n++; } return n ? s / n : null; }
const JOINT_IDX = { nose: [0], shoulders: [11, 12], hips: [23, 24], knees: [25, 26], wrists: [15, 16], ankles: [27, 28] };
function jointsY(lm, joints) { let s = 0, n = 0; for (const j of joints) { const y = avgY(lm, JOINT_IDX[j]); if (y === null) return null; s += y; n++; } return n ? s / n : null; }

// ---------------------------------------------------------------- detectors
const DECAY = 0.0006;
let lastRejectToast = 0;
function makeDetector(cfg) {
  if (!cfg) cfg = { kind: "vertical", joints: ["shoulders"], amp: 0.05 };
  if (cfg.kind === "manual") return null;   // ручной счёт — тап по счётчику
  if (cfg.kind === "hold") return makeHold();
  if (cfg.kind === "jumpingjack") return makeJack();
  return makeVertical(cfg.joints || ["shoulders"], cfg.amp || 0.05, cfg.posture || "any", cfg.strict !== false);
}
function makeVertical(joints, amp, posture = "any", strict = true) {
  // считаем только «правильные» повторы: достаточная глубина (≥60% амплитуды) и темп (≥380 мс)
  let sMin = 1, sMax = 0, phase = "up", ema = null, downT = 0, deep = 0, standEMA = 0.5;
  const MIN_MS = 380;
  return {
    process(lm) {
      // проверка позы — не даём «читерить» другим упражнением (сглаженно, чтобы не мешать честным)
      if (posture !== "any") {
        const sy = avgY(lm, [11, 12]), hy = avgY(lm, [23, 24]);
        const sx = avgX(lm, [11, 12]), hx = avgX(lm, [23, 24]);
        if (sy !== null && hy !== null && sx !== null && hx !== null) {
          const dy = Math.abs(hy - sy), dx = Math.abs(hx - sx);
          const st = ((hy - sy) > 0.12 && dy > dx * 1.1) ? 1 : 0;   // торс вертикальный, таз ниже плеч
          standEMA = standEMA * 0.85 + st * 0.15;
          if (posture === "stand" && standEMA < 0.35) { hint("Встань в полный рост 🧍"); skelColor = "#ffcf33"; return; }
          if (posture === "floor" && standEMA > 0.7) { hint("Прими упор лёжа / ляг на пол 🧎"); skelColor = "#ffcf33"; return; }
        }
      }
      let s = jointsY(lm, joints);
      if (s === null) { hint("Не вижу тело — поправь камеру"); return; }
      ema = ema === null ? s : ema * 0.6 + s * 0.4; s = ema;
      sMin = Math.min(s, sMin + DECAY); sMax = Math.max(s, sMax - DECAY);
      const range = sMax - sMin;
      if (range < amp) { hint("Двигайся с полной амплитудой — калибрую…"); skelColor = "#39e67e"; return; }
      const down = sMin + range * 0.60, up = sMin + range * 0.32;
      if (phase === "up") {
        hint("Опускайся глубже 🔽");
        if (s > down) { phase = "down"; downT = performance.now(); deep = s; skelColor = "#ff5a4d"; }
      } else {
        deep = Math.max(deep, s);
        hint("И вверх! 🔼");
        if (s < up) {
          phase = "up"; skelColor = "#39e67e";
          if (!strict) {
            const dur = performance.now() - downT;
            if (dur >= 250) onRep();  // даже «носки» — не чаще чем раз в 250мс
            return;
          }
          const depth = deep - sMin, dur = performance.now() - downT;
          if (depth >= range * 0.6 && dur >= MIN_MS) onRep();
          else {
            const nw = performance.now();
            if (nw - lastRejectToast > 2500) {   // не спамить предупреждениями
              lastRejectToast = nw;
              toast(depth < range * 0.6 ? "⚠️ Опускайся глубже" : "⚠️ Чуть медленнее", 1000);
            }
          }
        }
      }
    },
  };
}
function makeJack() {
  let up = false;
  return {
    process(lm) {
      const sh = avgY(lm, [11, 12]), wr = avgY(lm, [15, 16]);
      if (sh === null || wr === null) { hint("Встань в полный рост в кадр"); return; }
      hint("Руки вверх — вниз! 🤸");
      const m = sh - wr;
      if (!up && m > 0.05) { up = true; skelColor = "#ff5a4d"; }
      else if (up && m < -0.02) { up = false; skelColor = "#39e67e"; onRep(); }
    },
  };
}
function makeHold() {
  // считаем секунды, пока поза удерживается (тело видно в кадре) — подходит для планки,
  // боковой планки, стенки, супермена, «птица-собака» (без требования горизонтали)
  let acc = 0, last = null;
  return {
    process(lm, now) {
      const present = avgY(lm, [11, 12]) !== null && avgY(lm, [23, 24]) !== null;
      if (!present) { hint("Держи позу — тебя плохо видно в кадре"); last = now; skelColor = "#ffcf33"; return; }
      skelColor = "#39e67e"; hint("Держись! 💪 Секунды капают");
      if (last != null) acc += now - last;
      last = now;
      while (acc >= 1000) { acc -= 1000; onRep(); }
    },
  };
}

// ---------------------------------------------------------------- combat / rep
function onRep() {
  if (flushing && !trainMode && !duelMode) return;
  if (duelMode) {
    if (!duelCanCount()) return;
    displayCount++;
    $("b-count").textContent = displayCount;
    const c = $("b-counter"); c.classList.add("pop"); setTimeout(() => c.classList.remove("pop"), 90);
    haptic("medium");
    sfxHit(combo); bumpCombo();
    floatDmg("+1", "#ffcf33");
    if ($("duel-me-reps")) $("duel-me-reps").textContent = displayCount;
    if (displayCount % 3 === 0) syncDuelReps();
    return;
  }
  displayCount++;
  $("b-count").textContent = displayCount;
  const c = $("b-counter"); c.classList.add("pop"); setTimeout(() => c.classList.remove("pop"), 90);
  haptic("medium");
  sfxHit(combo); bumpCombo();

  if (trainMode) {
    trainPending++;
    floatDmg("+1", "#ffcf33");
    if (trainTarget && displayCount >= trainTarget) { completeSimple(); return; }
    if (trainPending >= 5) flushTrain();
    return;
  }
  if (!enemy) return;
  repsThisEnemy++;
  const dmg = state.player.damage;
  localEnemyHp -= dmg;
  localYouHp = Math.max(0, localYouHp - (Number(enemy.attack) || 0));
  const av = $("b-avatar"); av.classList.add("hurt"); setTimeout(() => av.classList.remove("hurt"), 180);
  floatDmg("-" + dmg, "#ffcf33");
  updateEnemyHp(); updateYouHp();
  if (localYouHp <= 0 || localEnemyHp <= 0) flushSet(localEnemyHp <= 0);
}

function floatDmg(txt, color) {
  const el = document.createElement("div");
  el.className = "float-dmg"; el.textContent = txt; el.style.color = color || "#ffcf33";
  el.style.left = (45 + Math.random() * 10) + "%"; el.style.top = "34%";
  $("cam-wrap").appendChild(el);
  setTimeout(() => el.remove(), 800);
}

async function flushSet(killed) {
  if (flushing) return;
  const reps = repsThisEnemy;
  if (reps <= 0 && !killed) return;
  flushing = true;
  try {
    const snap = await api("/attack", "POST", { reps });
    repsThisEnemy = 0;
    state = snap; localYouHp = snap.player.hp; updateYouHp();
    const events = snap.events || [];
    const wasKill = events.some((e) => e.type === "enemy_defeated");
    const defeated = events.some((e) => e.type === "player_defeated");
    const gateCleared = events.some((e) => e.type === "gate_cleared");
    handleEvents(events);
    if (!defeated && !gateCleared && snap.enemy && !snap.gate_cleared) {
      if (wasKill) { deathAnim(); await sleep(430); loadEnemy(snap.enemy); }
      else loadEnemy(snap.enemy);
    }
  } catch (e) {
    toast("🔁 Связь пропала — синхронизирую…");
    try {
      const snap = await api("/state");
      state = snap;
      localYouHp = snap.player.hp;
      repsThisEnemy = 0;
      displayCount = 0;
      if (snap.enemy && !snap.gate_cleared) loadEnemy(snap.enemy);
      else updateYouHp();
    } catch (_) {
      // не даём каскад flush при localEnemyHp <= 0
      if (localEnemyHp <= 0) localEnemyHp = Math.max(1, Math.round((enemy && enemy.max_hp) ? enemy.max_hp * 0.15 : 1));
      updateEnemyHp();
    }
  }
  finally { flushing = false; }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function deathAnim() {
  const av = $("b-avatar"); av.classList.add("die");
}

function handleEvents(events) {
  for (const ev of events) {
    if (ev.type === "enemy_defeated") { notify("success"); sfxKill(); shake(true); flash("fx-red"); resetCombo(); toast(`💀 ${ev.name} повержен! +${ev.xp} XP`); }
    else if (ev.type === "level_up") { notify("success"); sfxLevel(); flash("fx-gold"); toast(`⭐ LVL ${ev.level}! Урон ${ev.damage}, HP ${ev.max_hp}`, 2200); }
    else if (ev.type === "gate_unlocked") { toast(`🔓 Открыты Врата ${ev.rank}: ${ev.gate}`, 2400); }
    else if (ev.type === "premium_gate_ahead") { toast(`⭐ Дальше «${ev.biome_name || ev.gate}» — нужен Premium`, 2800); setTimeout(showPremiumPaywall, 900); }
    else if (ev.type === "rate_limited") { toast("⏳ Слишком быстро — подожди секунду", 1800); }
    else if (ev.type === "reps_capped") { /* тихо режем чит-пакеты */ }
    else if (ev.type === "quest_done") { notify("success"); sfxLevel(); flash("fx-gold"); toast(`🎯 Задание: ${ev.text} · +${ev.reward} XP`, 2600); }
    else if (ev.type === "streak") { if (ev.count > 1) toast(`🔥 Серия ${ev.count} дней подряд!`, 2000); }
    else if (ev.type === "freeze_gained") { toast(`🛡️ +1 день отдыха (всего ${ev.left})`, 2200); }
    else if (ev.type === "freeze_used") { toast(`🛡️ День отдыха спас серию (осталось ${ev.left})`, 2400); }
    else if (ev.type === "gate_cleared") {
      stopCamera(); sfxVictory();
      const boss = state.gate.is_biome_boss;
      if (boss) { flash("fx-gold"); shake(true); }
      const img = boss ? `./img/${state.gate.node_avatar}.jpg` : null;
      showResult(boss ? "🏆" : "✅",
        boss ? "БИОМ ПРОЙДЕН!" : "Уровень зачищен!",
        boss ? `${state.gate.biome_name} повержен!` : state.gate.name,
        ev.first_clear ? `+${ev.reward_xp} XP` : "", () => goHome(), { img, epic: boss });
    } else if (ev.type === "player_defeated") {
      stopCamera(); sfxDefeat(); flash("fx-red"); shake(true);
      showResult("💀", "Ты пал...", "Враги оказались сильнее. Отдохни и вернись.",
        "Возрождение с половиной HP", () => goHome());
    }
  }
}

function showResult(emoji, title, sub, reward, onNext, opts = {}) {
  const img = opts.img;
  $("r-img").style.display = img ? "block" : "none";
  if (img) $("r-img").src = img;
  $("r-emoji").style.display = img ? "none" : "block";
  $("r-emoji").textContent = emoji;
  $("r-title").textContent = title;
  $("r-sub").textContent = sub; $("r-reward").textContent = reward || "";
  const r = $("result"); r.classList.toggle("epic", !!opts.epic); r.classList.add("show");
  if (opts.epic) confetti();
  $("r-btn").onclick = () => { r.classList.remove("show"); onNext(); };
}
function confetti() {
  const box = $("confetti"); box.innerHTML = "";
  const colors = ["#ffcf33", "#e04a3f", "#3ddc84", "#5bb6e0", "#9a5cff", "#ffffff"];
  for (let i = 0; i < 28; i++) {
    const p = document.createElement("i");
    p.style.left = Math.random() * 100 + "%";
    p.style.background = colors[i % colors.length];
    p.style.animationDelay = (Math.random() * 0.5) + "s";
    p.style.animationDuration = (1.2 + Math.random() * 0.9) + "s";
    box.appendChild(p);
  }
}

// ---------------------------------------------------------------- camera + loop
let stream = null, rafId = null, lastVideoTime = -1;
let smoothDraw = null;
function smoothForDraw(lm) {
  if (!smoothDraw || smoothDraw.length !== lm.length) {
    smoothDraw = lm.map((p) => ({ x: p.x, y: p.y, visibility: p.visibility }));
    return smoothDraw;
  }
  const a = 0.45;   // лёгкое сглаживание — убирает дрожь, почти без задержки
  for (let i = 0; i < lm.length; i++) {
    smoothDraw[i].x = smoothDraw[i].x * (1 - a) + lm[i].x * a;
    smoothDraw[i].y = smoothDraw[i].y * (1 - a) + lm[i].y * a;
    smoothDraw[i].visibility = lm[i].visibility;
  }
  return smoothDraw;
}
async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
    });
  } catch (e) {
    showError("Нет доступа к камере 📷",
      "Разреши камеру в Telegram: кнопка «⋯» вверху → Разрешения → Камера. Потом жми «Повторить».",
      () => startCamera());
    return;
  }
  $("cam-wrap").classList.toggle("mirror", facingMode === "user");
  const video = $("cam"); video.srcObject = stream; await video.play();
  resizeCanvas();
  fighting = true; paused = false; smoothDraw = null;
  audio(); resetCombo(); startMusic();
  $("btn-pause").textContent = "⏸ Пауза";
  rebuildDetector();
  loop();
}
function rebuildDetector() {
  if (trainMode && trainExercise) detector = makeDetector(trainExercise.detector);
  else if (enemy) detector = makeDetector(enemy.detector);
}
function togglePause() {
  if (!stream) return;
  paused = !paused;
  $("btn-pause").textContent = paused ? "▶️ Продолжить" : "⏸ Пауза";
  if (paused) { fighting = false; if (rafId) cancelAnimationFrame(rafId); resetCombo(); hint("Пауза"); }
  else { fighting = true; rebuildDetector(); loop(); }
}
async function flipCamera() {
  facingMode = facingMode === "user" ? "environment" : "user";
  if (fighting || stream) {
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    if (rafId) cancelAnimationFrame(rafId);
    await startCamera();
  }
  toast(facingMode === "user" ? "Фронтальная камера" : "Задняя камера");
}
function resizeCanvas() { const cv = $("overlay"); cv.width = cv.clientWidth; cv.height = cv.clientHeight; }

function loop() {
  if (!fighting) return;
  const video = $("cam"), cv = $("overlay"), ctx = cv.getContext("2d");
  if (video.currentTime !== lastVideoTime && video.readyState >= 2) {
    lastVideoTime = video.currentTime;
    const now = performance.now();
    const res = poseLandmarker.detectForVideo(video, now);
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (res && res.landmarks && res.landmarks.length) {
      const lm = res.landmarks[0];
      drawSkeleton(ctx, cv, video, smoothForDraw(lm));   // отрисовка сглажена
      // счёт по «сырым» точкам — НО не во время отдыха и не когда открыто окно (инструкция/результат)
      if (detector && !resting && !detectionBlocked()) detector.process(lm, now);
      else if (detectionBlocked()) hint("Читаешь инструкцию — счёт на паузе");
    } else { smoothDraw = null; hint("Не вижу тебя — встань в кадр"); }
  }
  rafId = requestAnimationFrame(loop);
}
function containRect(cv, video) {
  const vw = video.videoWidth || 16, vh = video.videoHeight || 9;
  const cw = cv.width, ch = cv.height;
  const scale = Math.min(cw / vw, ch / vh);
  const dw = vw * scale, dh = vh * scale;
  return { ox: (cw - dw) / 2, oy: (ch - dh) / 2, dw, dh };
}
function drawSkeleton(ctx, cv, video, lm) {
  const { ox, oy, dw, dh } = containRect(cv, video);
  const X = (p) => ox + p.x * dw, Y = (p) => oy + p.y * dh;
  ctx.lineWidth = 4; ctx.strokeStyle = skelColor; ctx.lineCap = "round";
  for (const [a, b] of CONNECTIONS) {
    if (!vis(lm, a) || !vis(lm, b)) continue;
    ctx.beginPath(); ctx.moveTo(X(lm[a]), Y(lm[a])); ctx.lineTo(X(lm[b]), Y(lm[b])); ctx.stroke();
  }
  ctx.fillStyle = "#ffffff";
  for (const i of KEY_POINTS) { if (!vis(lm, i)) continue; ctx.beginPath(); ctx.arc(X(lm[i]), Y(lm[i]), 5, 0, Math.PI * 2); ctx.fill(); }
}
function stopCamera() {
  fighting = false;
  closeRest();
  stopMusic();
  if (rafId) cancelAnimationFrame(rafId);
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
}
async function exitBattle() {
  stopCamera();
  try {
    if (duelMode && duelState && !duelFinishedShown && duelState.status !== "finished") {
      await api("/duel/" + duelState.id + "/forfeit", "POST", {});
    } else if (!duelMode && trainMode) await flushTrain();
    else if (!duelMode && repsThisEnemy > 0) await flushSet(false);
  } catch (e) {}
  stopDuelTimers();
  duelMode = false;
  duelState = null;
  $("screen-battle").classList.remove("duel");
  goHome();
}
async function goHome() {
  stopCamera();
  stopDuelTimers();
  trainMode = false;
  duelMode = false;
  $("screen-battle").classList.remove("train", "soft", "duel");
  if (tg && tg.BackButton) tg.BackButton.hide();
  try { state = await api("/state"); } catch (e) {}
  renderHome();
}

// ---------------------------------------------------------------- arena 1v1
function stopDuelTimers() {
  if (duelPollT) { clearInterval(duelPollT); duelPollT = null; }
  if (duelTimerT) { clearInterval(duelTimerT); duelTimerT = null; }
}

function duelCanCount() {
  if (!duelState || duelState.status !== "active" || duelFinishedShown) return false;
  if (duelState.me && duelState.me.finished) return false;
  const now = Math.floor(Date.now() / 1000);
  const skew = (duelState._skew || 0);
  const serverNow = now + skew;
  if (duelState.starts_at && serverNow < duelState.starts_at) return false;
  if (duelState.ends_at && serverNow >= duelState.ends_at) return false;
  return true;
}

function applyDuelSkew(d) {
  if (d && d.server_now) {
    d._skew = d.server_now - Math.floor(Date.now() / 1000);
  }
  return d;
}

async function renderArena() {
  try {
    duelMeta = await api("/duel/meta");
  } catch (e) {
    toast("Не удалось загрузить арену");
    return;
  }
  arenaFriendLink = duelMeta.invite_friend_link || "";
  const st = duelMeta.stats || {};
  if ($("as-w")) $("as-w").textContent = st.wins || 0;
  if ($("as-d")) $("as-d").textContent = st.draws || 0;
  if ($("as-l")) $("as-l").textContent = st.losses || 0;

  const list = $("arena-ex-list");
  if (list) {
    list.innerHTML = "";
    const anyBtn = document.createElement("button");
    anyBtn.type = "button";
    anyBtn.className = "arena-ex" + (duelExKey === "any" ? " on" : "");
    anyBtn.dataset.key = "any";
    anyBtn.innerHTML = `<span class="ae-ic">🎲</span><span>Любое</span>`;
    anyBtn.onclick = () => { duelExKey = "any"; renderArenaExSelection(); };
    list.appendChild(anyBtn);
    (duelMeta.exercises || []).forEach((ex) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "arena-ex" + (duelExKey === ex.key ? " on" : "");
      b.dataset.key = ex.key;
      b.innerHTML = `<span class="ae-ic">${ex.icon}</span><span>${ex.name}</span>`;
      b.onclick = () => { duelExKey = ex.key; renderArenaExSelection(); };
      list.appendChild(b);
    });
  }

  const inv = $("arena-invites");
  if (inv) {
    inv.innerHTML = "";
    const invites = duelMeta.invites || [];
    if (!invites.length) {
      inv.innerHTML = `<div class="arena-empty">Нет входящих вызовов</div>`;
    } else {
      invites.forEach((d) => {
        const row = document.createElement("div");
        row.className = "af-row";
        const from = d.opponent || d.me;
        row.innerHTML = `
          <div class="af-av">${(from && from.avatar) || "⚔️"}</div>
          <div class="af-body">
            <div class="af-name">${(from && from.name) || "Игрок"}</div>
            <div class="af-sub">${(d.exercise && d.exercise.name) || "Бой"} · 60 сек</div>
          </div>
          <button type="button" class="af-act" data-act="accept">Принять</button>
          <button type="button" class="af-act ghost" data-act="decline">✕</button>`;
        row.querySelector('[data-act="accept"]').onclick = () => acceptDuelInvite(d.id);
        row.querySelector('[data-act="decline"]').onclick = () => declineDuelInvite(d.id);
        inv.appendChild(row);
      });
    }
  }

  const fr = $("arena-friends");
  if (fr) {
    fr.innerHTML = "";
    const friends = duelMeta.friends || [];
    if (!friends.length) {
      fr.innerHTML = `<div class="arena-empty">Позови друзей ссылкой — и вызывай их на бой</div>`;
    } else {
      friends.forEach((f) => {
        const row = document.createElement("div");
        row.className = "af-row";
        row.innerHTML = `
          <div class="af-av">${f.avatar || "🧑"}</div>
          <div class="af-body">
            <div class="af-name">${f.name}</div>
            <div class="af-sub">LVL ${f.level}${f.busy ? " · в бою" : ""}</div>
          </div>
          <button type="button" class="af-act" ${f.busy ? "disabled" : ""}>Вызов</button>`;
        const btn = row.querySelector(".af-act");
        if (!f.busy) btn.onclick = () => challengeFriend(f.tid);
        fr.appendChild(row);
      });
    }
  }

  updateArenaActive(duelMeta.active);
}

function renderArenaExSelection() {
  document.querySelectorAll(".arena-ex").forEach((el) => {
    const key = el.dataset.key || "any";
    el.classList.toggle("on", key === duelExKey);
  });
}

function setArenaSetupVisible(show) {
  const setup = $("arena-setup");
  if (setup) setup.classList.toggle("is-hidden", !show);
}

function markArenaTabDuel(on) {
  document.querySelectorAll('.tabbtn[data-tab="arena"]').forEach((b) => b.classList.toggle("has-duel", !!on));
}

function updateArenaActive(d) {
  const status = $("arena-status");
  const lobby = $("arena-lobby");
  const cancelQ = $("arena-cancel-q");
  const randomBtn = $("arena-random");
  if (!d || ["finished", "cancelled", "expired"].includes(d.status)) {
    stopDuelPoll();
    if (status) status.style.display = "none";
    if (lobby) {
      lobby.style.display = "none";
      lobby.classList.remove("is-open");
    }
    if (cancelQ) cancelQ.style.display = "none";
    if (randomBtn) randomBtn.style.display = "";
    setArenaSetupVisible(true);
    markArenaTabDuel(false);
    duelState = null;
    return;
  }
  duelState = applyDuelSkew(d);
  try { sessionStorage.setItem("yvy_duel", String(d.id)); } catch (e) {}
  markArenaTabDuel(true);

  if (d.status === "waiting" && d.mode === "random" && !d.opponent) {
    setArenaSetupVisible(false);
    if (status) {
      status.style.display = "";
      status.className = "arena-status searching";
      status.textContent = "Ищем соперника…";
    }
    if (lobby) {
      lobby.style.display = "none";
      lobby.classList.remove("is-open");
    }
    if (cancelQ) cancelQ.style.display = "";
    if (randomBtn) randomBtn.style.display = "none";
    startDuelPoll(d.id);
    return;
  }
  if (d.status === "waiting" && d.mode === "friend") {
    if (!d.i_am_p1) {
      setArenaSetupVisible(false);
      if (status) status.style.display = "none";
      if (cancelQ) cancelQ.style.display = "none";
      if (randomBtn) randomBtn.style.display = "none";
      showArenaLobby(d, "Тебя вызвали на бой");
      const readyBtn = $("arena-ready");
      if (readyBtn) {
        readyBtn.disabled = false;
        readyBtn.textContent = "Принять бой";
        readyBtn.onclick = () => acceptDuelInvite(d.id);
      }
      const leaveBtn = $("arena-leave");
      if (leaveBtn) leaveBtn.onclick = () => declineDuelInvite(d.id);
      return;
    }
    setArenaSetupVisible(false);
    if (status) {
      status.style.display = "";
      status.className = "arena-status";
      status.textContent = "Ждём ответа друга…";
    }
    if (lobby) {
      lobby.style.display = "none";
      lobby.classList.remove("is-open");
    }
    if (cancelQ) cancelQ.style.display = "";
    if (randomBtn) randomBtn.style.display = "none";
    startDuelPoll(d.id);
    return;
  }
  if (d.status === "matched" || d.status === "active") {
    setArenaSetupVisible(false);
    if (status) status.style.display = "none";
    if (cancelQ) cancelQ.style.display = "none";
    if (randomBtn) randomBtn.style.display = "none";
    showArenaLobby(d, d.status === "matched" ? "Соперник найден!" : "Бой идёт");
    if (d.status === "active" && !duelMode) enterDuelBattle(d);
    else startDuelPoll(d.id);
  }
}

function showArenaLobby(d, title) {
  const lobby = $("arena-lobby");
  if (!lobby) return;
  lobby.style.display = "flex";
  lobby.classList.add("is-open");
  const me = d.me || {};
  const opp = d.opponent || {};
  if ($("al-title")) $("al-title").textContent = title || "Соперник найден";
  if ($("al-me-av")) $("al-me-av").textContent = me.avatar || "🧑";
  if ($("al-me-name")) $("al-me-name").textContent = me.name || "Ты";
  if ($("al-opp-av")) $("al-opp-av").textContent = opp.avatar || "❓";
  if ($("al-opp-name")) $("al-opp-name").textContent = opp.name || "Соперник";
  const mr = $("al-me-ready");
  const orr = $("al-opp-ready");
  if (mr) {
    mr.textContent = me.ready ? "Готов ✓" : "Не готов";
    mr.className = "al-ready" + (me.ready ? " ok" : "");
  }
  if (orr) {
    orr.textContent = opp.ready ? "Готов ✓" : "Не готов";
    orr.className = "al-ready" + (opp.ready ? " ok" : "");
  }
  if ($("al-ex")) {
    const ex = d.exercise || {};
    $("al-ex").textContent = `${ex.icon || ""} ${ex.name || ""} · ${d.duration_sec || 60} сек`;
  }
  const readyBtn = $("arena-ready");
  if (readyBtn) {
    readyBtn.onclick = readyDuel;
    readyBtn.disabled = !!me.ready;
    readyBtn.textContent = me.ready ? "Ждём соперника…" : "Готов!";
  }
  const leaveBtn = $("arena-leave");
  if (leaveBtn) leaveBtn.onclick = leaveDuelLobby;

  try {
    lobby.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {}
  if (d.status === "matched" && !me.ready) {
    toast("Соперник найден — жми «Готов!»", 2800);
  }
}

function startDuelPoll(id) {
  stopDuelPoll();
  duelPollT = setInterval(() => pollDuel(id), 1500);
}

function stopDuelPoll() {
  if (duelPollT) { clearInterval(duelPollT); duelPollT = null; }
}

async function pollDuel(id) {
  try {
    const d = applyDuelSkew(await api("/duel/" + id));
    duelState = d;
    if (duelMode) {
      updateDuelHud(d);
      if (d.status === "finished" && !duelFinishedShown) showDuelResult(d);
      return;
    }
    const onArena = $("tab-arena") && $("tab-arena").classList.contains("active");
    if ((d.status === "matched" || d.status === "active") && !onArena) {
      await openArenaMatch(d.id);
      return;
    }
    updateArenaActive(d);
    if (d.status === "finished") {
      stopDuelPoll();
      try { sessionStorage.removeItem("yvy_duel"); } catch (e) {}
      renderArena();
    }
  } catch (e) {}
}

async function queueRandom() {
  uiClick();
  try {
    const d = applyDuelSkew(await api("/duel/queue", "POST", { exercise: duelExKey }));
    updateArenaActive(d);
  } catch (e) {
    toast((e && e.message) || "Не удалось найти бой");
  }
}

async function cancelQueue() {
  uiClick();
  try {
    await api("/duel/cancel", "POST", {});
    stopDuelPoll();
    await renderArena();
  } catch (e) {}
}

async function challengeFriend(friendTid) {
  uiClick();
  try {
    const d = applyDuelSkew(await api("/duel/challenge", "POST", {
      friend_tid: friendTid,
      exercise: duelExKey === "any" ? null : duelExKey,
    }));
    toast("Вызов отправлен!");
    updateArenaActive(d);
  } catch (e) {
    const code = (e && e.message) || "";
    if (code === "not_friend") toast("Сначала подружитесь по ссылке");
    else if (code === "busy") toast("Ты уже в бою");
    else if (code === "opponent_busy") toast("Друг сейчас занят");
    else toast("Не удалось вызвать");
  }
}

async function acceptDuelInvite(id) {
  uiClick();
  try {
    const d = applyDuelSkew(await api("/duel/" + id + "/accept", "POST", {}));
    updateArenaActive(d);
  } catch (e) {
    toast("Вызов уже недействителен");
    renderArena();
  }
}

async function declineDuelInvite(id) {
  uiClick();
  try {
    await api("/duel/" + id + "/decline", "POST", {});
    renderArena();
  } catch (e) {}
}

async function readyDuel() {
  uiClick();
  if (!duelState) return;
  try {
    const d = applyDuelSkew(await api("/duel/" + duelState.id + "/ready", "POST", {}));
    duelState = d;
    showArenaLobby(d);
    if (d.status === "active") enterDuelBattle(d);
    else startDuelPoll(d.id);
  } catch (e) {
    toast("Не удалось подтвердить готовность");
  }
}

async function leaveDuelLobby() {
  uiClick();
  if (!duelState) return;
  try {
    await api("/duel/" + duelState.id + "/forfeit", "POST", {});
  } catch (e) {}
  stopDuelPoll();
  duelState = null;
  renderArena();
}

function enterDuelBattle(d) {
  stopDuelPoll();
  duelFinishedShown = false;
  duelMode = true;
  trainMode = false;
  duelState = applyDuelSkew(d);
  // ВАЖНО: не тащить счётчик из прошлой тренировки/боя
  displayCount = (d.me && d.me.reps) || 0;
  repsThisEnemy = 0;
  trainPending = 0;
  musicStyle = "epic";
  $("screen-battle").classList.remove("train", "soft");
  $("screen-battle").classList.add("duel");
  const ex = d.exercise || {};
  $("b-gate-tag").textContent = "АРЕНА 1 НА 1";
  if ($("duel-ex-chip")) $("duel-ex-chip").textContent = `${ex.icon || ""} ${ex.name || ""}`;
  if ($("duel-me-name")) $("duel-me-name").textContent = (d.me && d.me.name) || "Ты";
  if ($("duel-opp-name")) $("duel-opp-name").textContent = (d.opponent && d.opponent.name) || "Соперник";
  if ($("duel-me-reps")) $("duel-me-reps").textContent = displayCount;
  if ($("duel-opp-reps")) $("duel-opp-reps").textContent = (d.opponent && d.opponent.reps) || 0;
  $("b-count-label").textContent = ex.type === "hold" ? "СЕК" : "ПОВТОРЫ";
  $("b-count").textContent = String(displayCount);
  detector = makeDetector(ex.detector);
  if (!detector && ex.detector && ex.detector.kind === "manual") {
    $("b-counter").onclick = () => { if (duelMode) onRep(); };
    hint("Ручной счёт: жми по кругу после каждого повтора");
  } else {
    $("b-counter").onclick = null;
    hint(ex.tip || "Жди старта — и жги!");
  }
  show("battle");
  if (tg && tg.BackButton) tg.BackButton.show();
  startCamera();
  startDuelClock();
  startDuelPoll(d.id);
  if (ex.key && ex.key !== "any" && !shownHow.has(ex.key)) {
    shownHow.add(ex.key);
    showHow(ex);
  }
}

function updateDuelHud(d) {
  if (!d) return;
  if ($("duel-opp-reps")) $("duel-opp-reps").textContent = (d.opponent && d.opponent.reps) || 0;
  if ($("duel-me-reps") && (d.me && d.me.reps) > displayCount) {
    displayCount = d.me.reps;
    $("duel-me-reps").textContent = displayCount;
    $("b-count").textContent = displayCount;
  }
}

function startDuelClock() {
  if (duelTimerT) clearInterval(duelTimerT);
  duelTimerT = setInterval(() => {
    if (!duelState) return;
    const el = $("duel-timer");
    if (!el) return;
    const now = Math.floor(Date.now() / 1000) + (duelState._skew || 0);
    if (duelState.starts_at && now < duelState.starts_at) {
      const left = Math.max(1, duelState.starts_at - now);
      el.className = "duel-timer cd";
      el.textContent = String(left);
      hint("Старт через " + left + "…");
      return;
    }
    if (duelState.ends_at) {
      const left = Math.max(0, duelState.ends_at - now);
      el.className = "duel-timer" + (left <= 10 ? " low" : "");
      el.textContent = String(left);
      if (left <= 0) {
        clearInterval(duelTimerT);
        duelTimerT = null;
        finishDuelClient();
      }
    }
  }, 200);
}

async function syncDuelReps() {
  if (!duelMode || !duelState || duelSyncing) return;
  duelSyncing = true;
  try {
    const d = applyDuelSkew(await api("/duel/" + duelState.id + "/reps", "POST", { reps: displayCount }));
    duelState = d;
    updateDuelHud(d);
    if (d.status === "finished" && !duelFinishedShown) showDuelResult(d);
  } catch (e) {}
  finally { duelSyncing = false; }
}

async function finishDuelClient() {
  if (!duelState) return;
  try {
    const d = applyDuelSkew(await api("/duel/" + duelState.id + "/finish", "POST", { reps: displayCount }));
    duelState = d;
    if (d.status === "finished") showDuelResult(d);
  } catch (e) {
    try {
      const d = applyDuelSkew(await api("/duel/" + duelState.id));
      if (d.status === "finished") showDuelResult(d);
    } catch (e2) {}
  }
}

function showDuelResult(d) {
  if (duelFinishedShown) return;
  duelFinishedShown = true;
  stopCamera();
  stopDuelTimers();
  const result = d.result;
  let title = "Ничья!";
  let emoji = "🤝";
  if (result === "win") { title = "Победа!"; emoji = "🏆"; }
  else if (result === "lose") { title = "Поражение"; emoji = "😤"; }
  const meR = (d.me && d.me.reps) || 0;
  const oppR = (d.opponent && d.opponent.reps) || 0;
  const xp = (d.me && d.me.xp) || 0;
  const sub = `${meR} : ${oppR} · ${(d.opponent && d.opponent.name) || "соперник"}`;
  $("r-emoji").textContent = emoji;
  $("r-title").textContent = title;
  $("r-sub").textContent = sub;
  $("r-reward").textContent = xp ? ("+" + xp + " XP") : "";
  $("r-img").style.display = "none";
  $("result").classList.add("show");
  $("r-btn").onclick = async () => {
    $("result").classList.remove("show");
    duelMode = false;
    duelState = null;
    $("screen-battle").classList.remove("duel");
    try { state = await api("/state"); } catch (e) {}
    renderHome();
    switchTab("arena");
  };
}

function shareArenaFriend() {
  const link = arenaFriendLink || (duelMeta && duelMeta.invite_friend_link) || "";
  if (!link) return;
  const w = webApp();
  if (w && w.openTelegramLink) {
    try {
      w.openTelegramLink("https://t.me/share/url?url=" + encodeURIComponent(link) + "&text=" + encodeURIComponent("Давай в YOU vs YOU — арена 1 на 1!"));
      return;
    } catch (e) {}
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => toast("Ссылка скопирована"));
  } else toast(link);
}

function peekPendingDuel() {
  try {
    const q = new URLSearchParams(location.search);
    const fromUrl = parseInt(q.get("duel") || "", 10);
    if (fromUrl > 0) {
      try { sessionStorage.setItem("yvy_duel", String(fromUrl)); } catch (e) {}
      return fromUrl;
    }
  } catch (e) {}
  try {
    const w = webApp();
    const sp = w && w.initDataUnsafe && w.initDataUnsafe.start_param;
    if (sp && /^du_?\d+$/i.test(String(sp))) {
      const n = parseInt(String(sp).replace(/^du_?/i, ""), 10);
      if (n > 0) return n;
    }
  } catch (e) {}
  try {
    const saved = parseInt(sessionStorage.getItem("yvy_duel") || "", 10);
    if (saved > 0) return saved;
  } catch (e) {}
  return null;
}

async function resumeArena() {
  await renderArena();
  const pd = peekPendingDuel();
  if (!pd) return;
  try {
    const d = applyDuelSkew(await api("/duel/" + pd));
    if (d && !["finished", "cancelled", "expired"].includes(d.status)) {
      updateArenaActive(d);
      return;
    }
    try { sessionStorage.removeItem("yvy_duel"); } catch (e) {}
  } catch (e) {
    // если дуэль чужая/пропала — просто покажем meta.active из renderArena
  }
}

async function openArenaMatch(duelId) {
  if (!duelId) return;
  try { sessionStorage.setItem("yvy_duel", String(duelId)); } catch (e) {}
  // переключить вкладку без повторного uiClick-рекурсии
  document.querySelectorAll(".tabpanel").forEach((el) => el.classList.toggle("active", el.id === "tab-arena"));
  document.querySelectorAll(".tabbtn").forEach((el) => el.classList.toggle("active", el.dataset.tab === "arena"));
  await resumeArena();
}

// ---------------------------------------------------------------- boot
async function boot() {
  expandWebApp();
  $("loading-text").textContent = "Проверяю вход…";
  for (let i = 0; i < 40 && !getInitData(); i++) {
    expandWebApp();
    try {
      const w = webApp();
      if (w && w.ready) w.ready();
    } catch (e) {}
    // если есть персональный токен из кнопки — можно не ждать initData вечно
    if (getLoginToken()) break;
    await sleep(75);
  }
  expandWebApp();
  if (!hasAuth()) {
    showError(
      "Нужен вход через Telegram",
      "Напиши боту /start и открой игру новой кнопкой «Войти в игру». Старая кнопка без входа больше не работает.",
      () => boot()
    );
    return;
  }

  $("loading-text").textContent = "Загружаю снаряжение…";
  try { state = await api("/state"); }
  catch (e) {
    const msg = (e && (e.status === 401 || e.code === "no_init_data"))
      ? "Сессия не прошла. Напиши боту /start и открой игру новой кнопкой «Войти в игру»."
      : "Похоже, пропал интернет. Проверь соединение и жми «Повторить».";
    showError("Не могу подключиться 🔌", msg, () => boot());
    return;
  }
  expandWebApp();
  $("loading-text").textContent = "Готовлю распознавание позы…";
  try { await loadPose(); }
  catch (e) { showError("ИИ-камера не загрузилась 🤖", "Обычно помогает стабильный интернет. Переподключись и попробуй снова.", () => boot()); return; }
  expandWebApp();
  renderHome();
  const pd = peekPendingDuel();
  if (state.player.needs_onboarding) {
    startOnboarding();
  } else if (pd) {
    // кнопка «В бой!» из бота — сразу лобби, даже если не выбрана программа
    await openArenaMatch(pd);
  } else if (state.player.needs_program) {
    openProgram();
  }
}

// ---------------------------------------------------------------- рейтинг
let lbPeriod = "week";
let lbInviteLink = "";

async function renderLeaderboard() {
  const list = $("lb-list");
  list.innerHTML = `<div class="lb-loading">Загружаю…</div>`;
  document.querySelectorAll(".lb-tab").forEach((b) => b.classList.toggle("on", b.dataset.period === lbPeriod));
  let d;
  try { d = await api("/leaderboard?period=" + encodeURIComponent(lbPeriod)); }
  catch (e) { list.innerHTML = `<div class="lb-loading">Не удалось загрузить</div>`; return; }

  lbInviteLink = d.invite_link || "";
  const inviteBtn = $("lb-invite");
  if (inviteBtn) {
    inviteBtn.style.display = (lbPeriod === "friends") ? "block" : "none";
  }

  const sub = $("lb-sub");
  if (sub) {
    if (lbPeriod === "season") sub.textContent = `Сезон «${d.season || ""}» — повторы за месяц`;
    else if (lbPeriod === "friends") sub.textContent = "Только вы и друзья по ссылке-приглашению";
    else sub.textContent = "Больше всех повторов за 7 дней";
  }

  const medal = (r) => r === 1 ? "🥇" : r === 2 ? "🥈" : r === 3 ? "🥉" : "#" + r;
  const row = (r) => `<div class="lb-row${r.me ? " me" : ""}">
      <div class="lb-rank">${medal(r.rank)}</div>
      <div class="lb-name">${r.name}${r.me ? " · ты" : ""}<div class="lb-sub">ур. ${r.level} · 🔥${r.streak}</div></div>
      <div class="lb-reps">${r.reps}<small> повт.</small></div></div>`;

  if (lbPeriod === "friends" && (!d.top || d.top.length <= 1) && !(d.friends_count > 0)) {
    list.innerHTML = `<div class="lb-loading">Пока нет друзей.<br>Жми «Пригласить друга» и соревнуйтесь вместе 🏆</div>`;
  } else {
    list.innerHTML = (d.top && d.top.length) ? d.top.map(row).join("")
      : `<div class="lb-loading">Пока пусто — стань первым! 🏆</div>`;
  }
  $("lb-me").innerHTML = (d.me && d.me.rank > 20) ? row(d.me) : "";
}

function shareFriendInvite() {
  uiClick();
  if (!lbInviteLink) {
    toast("Ссылка ещё не готова");
    return;
  }
  const text = "Давай посоревнуемся в YOU vs YOU 🏆";
  const w = webApp();
  try {
    if (w && typeof w.openTelegramLink === "function") {
      // Share via Telegram share URL
      const share = "https://t.me/share/url?url=" + encodeURIComponent(lbInviteLink) + "&text=" + encodeURIComponent(text);
      w.openTelegramLink(share);
      return;
    }
  } catch (e) {}
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(lbInviteLink).then(() => toast("Ссылка скопирована"));
      return;
    }
  } catch (e) {}
  toast(lbInviteLink, 4000);
}

// ---------------------------------------------------------------- разминка (перед тренировкой)
let sessionWarmed = false, warmTimer = null;
const WARM_MOVES = ["Марш на месте", "Круги руками вперёд-назад", "Наклоны в стороны", "Вращения корпусом", "Махи ногами"];
function maybeWarmup(next) {
  if (sessionWarmed) { next(); return; }
  let t = 45, mi = 0;
  const done = () => { clearInterval(warmTimer); warmTimer = null; $("warmup").classList.remove("show"); sessionWarmed = true; next(); };
  $("warmup-count").textContent = t; $("warmup-instr").textContent = WARM_MOVES[0];
  $("warmup").classList.add("show"); audio();
  $("warmup-skip").onclick = () => { uiClick(); done(); };
  $("warmup-ready").onclick = () => { uiClick(); done(); };
  clearInterval(warmTimer);
  warmTimer = setInterval(() => {
    t--; $("warmup-count").textContent = Math.max(0, t);
    if (t > 0 && t % 9 === 0) { mi = (mi + 1) % WARM_MOVES.length; $("warmup-instr").textContent = WARM_MOVES[mi]; sfxClick(); }
    if (t <= 0) { notify("success"); done(); }
  }, 1000);
}

// детекция на паузе, пока открыто любое окно поверх боя
function detectionBlocked() {
  const ids = ["how-modal", "ex-modal", "program-modal", "onboard-modal", "nick-modal", "fb-modal", "premium-modal", "donate-modal", "donate-thanks-modal", "reset-modal", "result", "warmup", "rest"];
  return ids.some((id) => { const el = document.getElementById(id); return el && el.classList.contains("show"); });
}

// ---------------------------------------------------------------- таймер отдыха
let resting = false, restTimer = null, restT = 30;
function openRest() {
  if (!stream) return;
  uiClick(); restT = 30; $("rest-count").textContent = restT; resting = true;
  $("rest").classList.add("show");
  clearInterval(restTimer);
  restTimer = setInterval(() => {
    restT--; $("rest-count").textContent = Math.max(0, restT);
    if (restT <= 3 && restT > 0) sfxClick();
    if (restT <= 0) { notify("success"); closeRest(); }
  }, 1000);
}
function closeRest() { clearInterval(restTimer); restTimer = null; resting = false; $("rest").classList.remove("show"); }

// Telegram «Назад»: закрыть модалку → выйти из боя → ничего
function onBack() {
  for (const m of ["how-modal", "ex-modal", "premium-modal", "donate-modal", "donate-thanks-modal", "reset-modal"]) {
    const el = $(m);
    if (el && el.classList.contains("show")) { el.classList.remove("show"); syncBack(); return; }
  }
  if ($("screen-battle").classList.contains("active")) exitBattle();
}
function syncBack() {
  if (!tg || !tg.BackButton) return;
  const modalOpen = ["how-modal", "ex-modal", "premium-modal", "donate-modal", "donate-thanks-modal", "reset-modal"].some((id) => {
    const el = $(id); return el && el.classList.contains("show");
  });
  if ($("screen-battle").classList.contains("active") || modalOpen) tg.BackButton.show();
  else tg.BackButton.hide();
}
if (tg && tg.BackButton) tg.BackButton.onClick(onBack);

$("btn-pause").onclick = togglePause;
$("btn-exit").onclick = exitBattle;
$("btn-flip").onclick = flipCamera;
$("btn-info").onclick = () => { sfxClick(); showHow(currentExerciseInfo()); };
$("btn-mute").textContent = muted ? "🔇" : "🔊";
$("btn-mute").onclick = () => {
  muted = !muted; localStorage.setItem("yvy_mute", muted ? "1" : "0");
  $("btn-mute").textContent = muted ? "🔇" : "🔊";
  if (!muted) { audio(); sfxClick(); }
};
$("btn-music").textContent = musicOn ? "🎵" : "🎵̶";
$("btn-music").style.opacity = musicOn ? "1" : "0.4";
$("btn-music").onclick = () => {
  musicOn = !musicOn; localStorage.setItem("yvy_music", musicOn ? "1" : "0");
  $("btn-music").style.opacity = musicOn ? "1" : "0.4";
  if (musicOn && fighting) startMusic(); else stopMusic();
};
$("btn-cal").onclick = () => { rebuildDetector(); toast("🎯 Калибровка сброшена"); };
function manualUndo() {
  if (displayCount <= 0) return;
  haptic("light");
  displayCount--; $("b-count").textContent = displayCount;
  if (duelMode) {
    if ($("duel-me-reps")) $("duel-me-reps").textContent = displayCount;
    return;
  }
  if (trainMode) { if (trainPending > 0) trainPending--; }
  else if (enemy) {
    if (repsThisEnemy > 0) {
      repsThisEnemy--;
      localEnemyHp = Math.min(enemy.max_hp, localEnemyHp + state.player.damage);
      localYouHp = Math.min(state.player.max_hp, localYouHp + (Number(enemy.attack) || 0));
      updateEnemyHp(); updateYouHp();
    }
  }
}
let lastPlusAt = 0;
$("btn-plus").onclick = () => {
  if (!fighting || detectionBlocked()) return;
  // Если камера считает сама — «+» не даём (это был главный обход)
  if (detector) { toast("Повторы считает камера 📷"); return; }
  const now = performance.now();
  if (now - lastPlusAt < 380) return;
  lastPlusAt = now;
  haptic("light");
  onRep();
};
$("btn-minus").onclick = () => { if (fighting) manualUndo(); };

function openNickEdit() {
  uiClick();
  $("nick-input").value = (state.player.nickname || "").startsWith("Охотник-") ? "" : (state.player.nickname || "");
  $("nick-modal").classList.add("show");
  setTimeout(() => $("nick-input").focus(), 50);
}
$("nick-cancel").onclick = () => { uiClick(); $("nick-modal").classList.remove("show"); };
$("nick-save").onclick = async () => {
  uiClick();
  const v = $("nick-input").value.trim();
  if (!v) { toast("Введи ник"); return; }
  try { state = await api("/nickname", "POST", { nickname: v }); } catch (e) {}
  $("nick-modal").classList.remove("show");
  renderProfile();
};
let fbTopic = "";
function fbCount() { $("fb-count").textContent = `${$("fb-input").value.length} / 800`; }
$("btn-feedback").onclick = () => {
  uiClick(); fbTopic = ""; $("fb-input").value = ""; fbCount();
  document.querySelectorAll(".fb-topic").forEach((b) => b.classList.remove("sel"));
  $("fb-modal").classList.add("show");
  setTimeout(() => $("fb-input").focus(), 50);
};
document.querySelectorAll(".fb-topic").forEach((b) => (b.onclick = () => {
  uiClick();
  const on = b.classList.contains("sel");
  document.querySelectorAll(".fb-topic").forEach((x) => x.classList.remove("sel"));
  if (!on) { b.classList.add("sel"); fbTopic = b.dataset.t; } else fbTopic = "";
}));
$("fb-input").oninput = fbCount;
$("fb-cancel").onclick = () => { uiClick(); $("fb-modal").classList.remove("show"); };
$("fb-send").onclick = async () => {
  uiClick();
  const t = $("fb-input").value.trim();
  if (t.length < 3) { toast("Напиши чуть подробнее"); return; }
  const text = fbTopic ? `[${fbTopic}] ${t}` : t;
  try {
    const headers = { "Content-Type": "application/json" };
    const init = getInitData();
    const login = getLoginToken();
    if (init) {
      headers["X-Telegram-Init-Data"] = init;
      headers["Authorization"] = "tma " + init;
    } else if (login) {
      headers["X-YVY-Login"] = login;
    }
    const uu = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
    const body = { text, tg_name: [uu.first_name, uu.last_name].filter(Boolean).join(" "), tg_username: uu.username || "" };
    const r = await fetch(apiUrl("/feedback"), { method: "POST", headers, body: JSON.stringify(body) });
    if (r.status === 429) { toast("🙏 Лимит отзывов на сегодня. Спасибо!"); $("fb-modal").classList.remove("show"); return; }
    if (!r.ok) throw new Error();
    toast("🙌 Спасибо! Отправлено"); $("fb-modal").classList.remove("show");
  } catch (e) { toast("Не отправилось, попробуй позже"); }
};
$("btn-rest").onclick = openRest;
$("rest-skip").onclick = () => { uiClick(); closeRest(); };
$("rest-minus").onclick = () => { uiClick(); restT = Math.max(5, restT - 15); $("rest-count").textContent = restT; };
$("rest-plus").onclick = () => { uiClick(); restT += 15; $("rest-count").textContent = restT; };
$("train-card").onclick = openExPicker;
$("btn-reset").onclick = () => {
  uiClick();
  $("reset-modal").classList.add("show");
  if (typeof syncBack === "function") syncBack();
};
$("reset-cancel").onclick = () => {
  uiClick();
  $("reset-modal").classList.remove("show");
  if (typeof syncBack === "function") syncBack();
};
$("reset-confirm").onclick = async () => {
  uiClick();
  $("reset-modal").classList.remove("show");
  if (typeof syncBack === "function") syncBack();
  try {
    state = await api("/reset", "POST");
    renderHome();
    switchTab("pohod");
    toast("Прогресс сброшен");
  } catch (e) {
    toast("Не удалось сбросить");
  }
};
document.querySelectorAll(".tabbtn").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
$("home-tip-x").onclick = () => { uiClick(); $("home-tip").style.display = "none"; localStorage.setItem("yvy_tip_seen", "1"); };
$("set-reminders").onclick = async () => {
  uiClick();
  const next = state.player.reminders === false;
  try {
    state = await api("/reminders", "POST", {
      on: next,
      hour: state.player.reminder_hour ?? 19,
      minute: state.player.reminder_minute ?? 0,
    });
    renderProfile();
    toast(next ? "🔔 Напоминания включены" : "🔕 Напоминания выключены");
  } catch (e) {}
};
const remindSave = $("remind-save");
if (remindSave) {
  remindSave.onclick = () => {
    uiClick();
    if (state.player.reminders === false) {
      toast("Сначала включи напоминания");
      return;
    }
    const h = Number(($("remind-hour") && $("remind-hour").value) || 19);
    const m = Number(($("remind-minute") && $("remind-minute").value) || 0);
    setReminderTime(h, m);
  };
}
const moreToggle = $("more-toggle");
const morePanel = $("more-panel");
if (moreToggle && morePanel) {
  moreToggle.onclick = () => {
    uiClick();
    const open = morePanel.hasAttribute("hidden");
    if (open) morePanel.removeAttribute("hidden");
    else morePanel.setAttribute("hidden", "");
    moreToggle.textContent = open ? "Ещё настройки ▴" : "Ещё настройки ▾";
  };
}
document.querySelectorAll(".lb-tab").forEach((b) => {
  b.onclick = () => {
    uiClick();
    lbPeriod = b.dataset.period || "week";
    renderLeaderboard();
  };
});
const lbInvite = $("lb-invite");
if (lbInvite) lbInvite.onclick = shareFriendInvite;

const arenaRandom = $("arena-random");
if (arenaRandom) arenaRandom.onclick = queueRandom;
const arenaCancelQ = $("arena-cancel-q");
if (arenaCancelQ) arenaCancelQ.onclick = cancelQueue;
const arenaReady = $("arena-ready");
if (arenaReady) arenaReady.onclick = readyDuel;
const arenaLeave = $("arena-leave");
if (arenaLeave) arenaLeave.onclick = leaveDuelLobby;
const arenaInviteFr = $("arena-invite-fr");
if (arenaInviteFr) arenaInviteFr.onclick = shareArenaFriend;

// Вернулись из чата бота по кнопке «В бой!» — подтянуть матч
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || duelMode) return;
  const pd = peekPendingDuel();
  if (pd) openArenaMatch(pd).catch(() => {});
});
try {
  const w = webApp();
  if (w && w.onEvent) {
    w.onEvent("viewportChanged", () => {
      if (duelMode) return;
      const pd = peekPendingDuel();
      if (pd && !($("arena-lobby") && $("arena-lobby").classList.contains("is-open"))) {
        openArenaMatch(pd).catch(() => {});
      }
    });
  }
} catch (e) {}

$("set-uisound").onclick = () => {
  uiMuted = !uiMuted; localStorage.setItem("yvy_ui_mute", uiMuted ? "1" : "0");
  if (!uiMuted) uiClick();
  renderProfile();
};
$("set-sound").onclick = () => {
  muted = !muted; localStorage.setItem("yvy_mute", muted ? "1" : "0");
  $("btn-mute").textContent = muted ? "🔇" : "🔊";
  if (!muted) { audio(); sfxClick(); }
  renderProfile();
};
$("set-music").onclick = () => {
  musicOn = !musicOn; localStorage.setItem("yvy_music", musicOn ? "1" : "0");
  $("btn-music").style.opacity = musicOn ? "1" : "0.4";
  if (musicOn && fighting) startMusic(); else stopMusic();
  renderProfile();
};
let resizeT = null;
window.addEventListener("resize", () => {
  if (fighting) { resizeCanvas(); return; }
  clearTimeout(resizeT);
  resizeT = setTimeout(() => {
    if (screens.home.classList.contains("active") && state && state.player.mode !== "simple") buildMap();
  }, 200);
});

boot();
