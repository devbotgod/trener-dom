/* YvyFig v4 — детальные фигурки упражнений.
   IK с фиксированными костями; позвоночник из 2 сегментов (изгиб груди «c»),
   шея, кисти, стопы, реквизит. Интерполяция углов — кратчайшим путём
   (без «360» на бёрпи). Профиль смотрит влево; front-вид для сумо/выпадов вбок.
   viewBox 100x94, пол y=86. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const L = { seg: 11, neck: 6, head: 15, uarm: 12, farm: 11, thigh: 15, shin: 15, foot: 7 };
  const RAD = Math.PI / 180;

  function P(o, len, deg) { const r = deg * RAD; return [o[0] + len * Math.sin(r), o[1] - len * Math.cos(r)]; }
  function IK(root, target, l1, l2, sign) {
    let dx = target[0] - root[0], dy = target[1] - root[1], d = Math.hypot(dx, dy);
    d = Math.min(d, l1 + l2 - 0.01); d = Math.max(d, Math.abs(l1 - l2) + 0.01);
    const base = Math.atan2(dy, dx);
    let ca = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d); ca = Math.max(-1, Math.min(1, ca));
    const a = Math.acos(ca), j = base + sign * a;
    return [[root[0] + l1 * Math.cos(j), root[1] + l1 * Math.sin(j)],
            [root[0] + Math.cos(base) * d, root[1] + Math.sin(base) * d]];
  }

  // --- вид сбоку: pel → waist → sh (грудь гнётся углом c) -------------------
  function solveSide(p) {
    const eS = p.eS == null ? -1 : p.eS, kS = p.kS == null ? 1 : p.kS, c = p.c || 0;
    const pel = [p.x, p.y];
    const waist = P(pel, L.seg, p.t);
    const sh = P(waist, L.seg, p.t + c);
    const hdir = p.t + c + (p.h || 0);
    const neckEnd = P(sh, L.neck, hdir), head = P(sh, L.head, hdir);
    function arm(ah, aU, aF) {
      if (ah) { const [e, w] = IK(sh, ah, L.uarm, L.farm, eS); return [sh, e, w]; }
      const e = P(sh, L.uarm, aU); return [sh, e, P(e, L.farm, aU + aF)];
    }
    function leg(lf, lU, lF, ks) {
      let ptsL;
      if (lf) { const [k, a] = IK(pel, lf, L.thigh, L.shin, ks); ptsL = [pel, k, a]; }
      else { const k = P(pel, L.thigh, lU); ptsL = [pel, k, P(k, L.shin, lU + lF)]; }
      if (p.foot) ptsL.push([ptsL[2][0] - L.foot, 86]);
      return ptsL;
    }
    const pk = (a, b) => (a == null ? b : a);
    return {
      torso: [pel, waist, sh], neck: [sh, neckEnd], head,
      armN: arm(p.ah, p.aU, p.aF),
      armF: arm(pk(p.ah2, p.ah), pk(p.aU2, p.aU), pk(p.aF2, p.aF)),
      legN: leg(p.lf, p.lU, p.lF, kS),
      legF: leg(pk(p.lf2, p.lf), pk(p.lU2, p.lU), pk(p.lF2, p.lF), p.kS2 == null ? kS : p.kS2),
      far: 3,
    };
  }
  // --- вид спереди ----------------------------------------------------------
  function solveFront(p) {
    const pel = [p.x, p.y], t = p.t || 0;
    const waist = P(pel, L.seg, t), sh = P(waist, L.seg, t + (p.c || 0));
    const hdir = t + (p.c || 0) + (p.h || 0);
    const neckEnd = P(sh, L.neck, hdir), head = P(sh, L.head, hdir);
    const shL = [sh[0] - 7, sh[1]], shR = [sh[0] + 7, sh[1]];
    const hipL = [p.x - 4.5, p.y], hipR = [p.x + 4.5, p.y];
    function limb(root, tgt, ang, l1, l2, sign) {
      if (tgt) { const [j, e] = IK(root, tgt, l1, l2, sign); return [root, j, e]; }
      const j = P(root, l1, ang[0]); return [root, j, P(j, l2, ang[0] + ang[1])];
    }
    const legL = limb(hipL, p.alkL, null, L.thigh, L.shin, p.kL == null ? 1 : p.kL);
    const legR = limb(hipR, p.alkR, null, L.thigh, L.shin, p.kR == null ? -1 : p.kR);
    if (p.foot) { legL.push([legL[2][0] - 5, legL[2][1] + 1.5]); legR.push([legR[2][0] + 5, legR[2][1] + 1.5]); }
    return {
      torso: [pel, waist, sh], neck: [sh, neckEnd], head,
      armN: limb(shL, p.ahL, p.aL || [187, 5], L.uarm, L.farm, 1),
      armF: limb(shR, p.ahR, p.aR || [173, -5], L.uarm, L.farm, -1),
      legN: legL, legF: legR, far: 0,
    };
  }

  const smooth = (t) => t * t * (3 - 2 * t);
  const lerp = (a, b, t) => a + (b - a) * t;
  function alerp(a, b, t) { const d = ((b - a + 540) % 360) - 180; return a + d * t; } // кратчайший путь
  const AK = ["t", "h", "c", "aU", "aF", "aU2", "aF2", "lU", "lF", "lU2", "lF2"];     // углы
  const NKn = ["x", "y", "foot", "kL", "kR"];                                          // линейные
  const VK = ["ah", "ah2", "lf", "lf2", "alkL", "alkR", "aL", "aR", "ahL", "ahR"];
  const RK = ["hd", "to", "aN", "aF2r", "lN", "lF2r"];                                 // raw-кадры
  function lerpPts(a, b, t) {
    if (typeof a[0] === "number") return [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];
    return a.map((p, i) => [lerp(p[0], b[i][0], t), lerp(p[1], b[i][1], t)]);
  }
  function lerpPose(a, b, t) {
    const o = { eS: a.eS, kS: a.kS, kS2: a.kS2, kind: a.kind };
    for (const k of AK) o[k] = (a[k] != null && b[k] != null) ? alerp(a[k], b[k], t) : (a[k] != null ? a[k] : b[k]);
    for (const k of NKn) o[k] = (a[k] != null && b[k] != null) ? lerp(a[k], b[k], t) : (a[k] != null ? a[k] : b[k]);
    for (const k of VK) o[k] = (a[k] && b[k]) ? [lerp(a[k][0], b[k][0], t), lerp(a[k][1], b[k][1], t)] : (a[k] || b[k]);
    for (const k of RK) o[k] = (a[k] && b[k]) ? lerpPts(a[k], b[k], t) : (a[k] || b[k]);
    return o;
  }

  // --- библиотека -----------------------------------------------------------
  const ST = { x: 50, y: 56, t: -3, aU: 187, aF: 6, lf: [48, 86], foot: 1 };
  const SQD = { x: 56, y: 68, t: -35, c: 8, aU: 268, aF: 2, lf: [48, 86], foot: 1 };
  const LGD = { x: 44, y: 70, t: -6, aU: 190, aF: 6, lf: [32, 86], lf2: [50, 86], foot: 1 };
  const CRO = { x: 53, y: 70, t: -32, c: 4, aU: 176, aF: 6, lf: [48, 86], foot: 1 };
  const QUAD = { x: 60, y: 70, t: 290, ah: [36, 85], aU2: 178, aF2: 2, lU: 165, lF: -100, lU2: 165, lF2: -100 };

  const A = {
    pushup: { dur: 1.5, mode: "pp", f: [
      { x: 60, y: 70, t: 283, ah: [36, 85], lf: [85, 84], foot: 1 },
      { x: 60, y: 76, t: 277, ah: [36, 85], lf: [86, 85], foot: 1 } ] },
    // отжимания, вид спереди: видно постановку рук
    pushwide: { dur: 1.5, mode: "pp", raw: 1, f: [
      { hd: [50, 70], to: [[50, 63], [50, 50]], aN: [[41, 63], [31, 70], [24, 83]], aF2r: [[59, 63], [69, 70], [76, 83]], lN: [[50, 50], [45, 40]], lF2r: [[50, 50], [55, 40]] },
      { hd: [50, 78], to: [[50, 71], [50, 57]], aN: [[41, 71], [27, 71], [24, 83]], aF2r: [[59, 71], [73, 71], [76, 83]], lN: [[50, 57], [45, 46]], lF2r: [[50, 57], [55, 46]] } ] },
    // алмазные — обычное отжимание сбоку + схема «ладони ромбом» в углу
    pushdiamond: { dur: 1.5, mode: "pp", badge: "diamond", f: [
      { x: 60, y: 70, t: 283, ah: [36, 85], lf: [85, 84], foot: 1 },
      { x: 60, y: 76, t: 277, ah: [36, 85], lf: [86, 85], foot: 1 } ] },
    incline: { dur: 1.5, mode: "pp", props: [[30, 66, 52, 66], [32, 66, 32, 86], [50, 66, 50, 86]], f: [
      { x: 66, y: 60, t: 294, ah: [38, 65], lf: [82, 86], foot: 1 },
      { x: 66, y: 63, t: 290, ah: [38, 65], lf: [82, 86], foot: 1 } ] },
    decline: { dur: 1.5, mode: "pp", props: [[64, 70, 88, 70], [66, 70, 66, 86], [86, 70, 86, 86]], f: [
      { x: 58, y: 64, t: 282, ah: [36, 85], lf: [78, 68] },
      { x: 58, y: 69, t: 278, ah: [36, 85], lf: [78, 68] } ] },
    hipthrust: { dur: 1.6, mode: "pp", props: [[56, 72, 84, 72], [58, 72, 58, 86], [82, 72, 82, 86]], f: [
      { x: 48, y: 80, t: 70, aU: 95, aF: 0, lf: [34, 84] },
      { x: 48, y: 72, t: 90, aU: 95, aF: 0, lf: [34, 84] } ] },
    rlunge: { dur: 1.9, mode: "pp", f: [
      { x: 50, y: 56, t: -3, aU: 187, aF: 6, lf: [48, 86], lf2: [48, 86], foot: 1 },
      { x: 48, y: 70, t: -6, aU: 190, aF: 6, lf: [44, 86], lf2: [66, 86], foot: 1 } ] },
    kneepush: { dur: 1.5, mode: "pp", f: [
      { x: 62, y: 68, t: 285, ah: [38, 85], lU: 165, lF: -100 },
      { x: 62, y: 75, t: 279, ah: [38, 85], lU: 165, lF: -100 } ] },
    pike: { dur: 1.6, mode: "pp", f: [
      { x: 62, y: 50, t: 238, ah: [40, 84], lf: [84, 84] },
      { x: 62, y: 54, t: 232, ah: [40, 84], lf: [84, 84] } ] },
    dip: { dur: 1.5, mode: "pp", props: [[62, 70, 88, 70], [64, 70, 64, 86], [86, 70, 86, 86]], f: [
      { x: 56, y: 72, t: 12, ah: [64, 70], lf: [28, 86], foot: 1 },
      { x: 56, y: 78, t: 12, ah: [64, 70], lf: [28, 86], foot: 1 } ] },
    plank: { dur: 3.4, mode: "hold", f: [
      { x: 60, y: 71, t: 268, ah: [30, 85], lf: [87, 84], foot: 1 } ] },
    sideplank: { dur: 3.4, mode: "hold", f: [
      { x: 59, y: 77, t: 284, ah: [28, 84], ah2: false, aU2: 14, aF2: 0, lf: [88, 84.5], lf2: [88, 84.5] } ] },
    superman: { dur: 1.8, mode: "pp", f: [
      { x: 56, y: 82, t: 269, c: 0, h: -10, ah: [12, 82], lf: [85, 84] },
      { x: 56, y: 81, t: 266, c: 9, h: -14, ah: [11, 74], lf: [86, 78] } ] },
    birddog: { dur: 2.0, mode: "pp", f: [
      { x: 60, y: 70, t: 290, ah: [36, 85], ah2: false, aU2: 178, aF2: 2, lU: 165, lF: -100, lU2: 165, lF2: -100 },
      { x: 60, y: 70, t: 290, ah: [36, 85], ah2: false, aU2: 272, aF2: 0, lU: 165, lF: -100, lU2: 78, lF2: -8 } ] },
    donkey: { dur: 1.6, mode: "pp", f: [
      QUAD,
      { x: 60, y: 70, t: 290, ah: [36, 85], aU2: 178, aF2: 2, lU: 95, lF: -80, lU2: 165, lF2: -100 } ] },
    squat: { dur: 1.7, mode: "pp", f: [ST, SQD] },
    pulse: { dur: 0.9, mode: "pp", f: [
      { x: 56, y: 66, t: -33, c: 8, aU: 268, aF: 2, lf: [48, 86], foot: 1 },
      { x: 56, y: 71, t: -36, c: 8, aU: 268, aF: 2, lf: [48, 86], foot: 1 } ] },
    jumpsquat: { dur: 2.0, mode: "loop", f: [
      ST, SQD, { x: 50, y: 40, t: 0, aU: 15, aF: 0, lf: [48, 74] }, SQD ] },
    wallsit: { dur: 3.4, mode: "hold", props: [[60, 28, 60, 86]], f: [
      { x: 52, y: 71, t: 2, aU: 200, aF: 90, lf: [37, 86], foot: 1 } ] },
    lunge: { dur: 1.9, mode: "pp", f: [ST, LGD] },
    lungejump: { dur: 1.7, mode: "loop", f: [
      LGD, { x: 50, y: 44, t: 0, aU: 350, aF: -4, lf: [40, 78], lf2: [62, 78] }, LGD ] },
    gm: { dur: 1.9, mode: "pp", f: [
      { x: 50, y: 56, t: -3, aU: 210, aF: 130, lf: [48, 86], foot: 1 },
      { x: 56, y: 58, t: -82, aU: 250, aF: 140, lf: [48, 86], foot: 1 } ] },
    toetouch: { dur: 1.9, mode: "pp", f: [
      { x: 50, y: 56, t: -2, ah: [52, 12], lf: [48, 86], foot: 1 },
      { x: 54, y: 58, t: -95, c: -8, ah: [46, 82], lf: [48, 86], foot: 1 } ] },
    calf: { dur: 1.1, mode: "pp", f: [
      ST, { x: 50, y: 50, t: -1, aU: 187, aF: 6, lf: [48, 80], foot: 1 } ] },
    crunch: { dur: 1.5, mode: "pp", f: [
      { x: 48, y: 79, t: 96, c: 0, h: -28, aU: 60, aF: -95, lf: [30, 84] },
      { x: 48, y: 79, t: 78, c: -28, h: -24, aU: 30, aF: -95, lf: [30, 84] } ] },
    situp: { dur: 1.7, mode: "pp", f: [
      { x: 48, y: 79, t: 96, c: 0, h: -26, ah: [60, 80], lf: [30, 84] },
      { x: 48, y: 79, t: 32, c: -14, h: -16, ah: [36, 76], lf: [30, 84] } ] },
    revcrunch: { dur: 1.5, mode: "pp", f: [
      { x: 48, y: 80, t: 96, aU: 255, aF: -5, lf: [30, 84] },
      { x: 50, y: 76, t: 99, aU: 255, aF: -5, lf: [38, 64] } ] },
    bicycle: { dur: 1.1, mode: "pp", f: [
      { x: 48, y: 78, t: 84, c: -22, h: -26, aU: 35, aF: -95, lf: [36, 64], lf2: [16, 78] },
      { x: 48, y: 78, t: 80, c: -22, h: -26, aU: 35, aF: -95, lf: [16, 78], lf2: [36, 64] } ] },
    heeltouch: { dur: 1.2, mode: "pp", f: [
      { x: 48, y: 79, t: 90, c: -12, h: -24, ah: [40, 82], ah2: [56, 74], lf: [32, 84] },
      { x: 48, y: 79, t: 86, c: -12, h: -24, ah: [56, 74], ah2: [40, 82], lf: [32, 84] } ] },
    twist: { dur: 1.3, mode: "pp", f: [
      { x: 50, y: 74, t: 38, c: -10, h: -16, ah: [28, 58], lf: [30, 72] },
      { x: 50, y: 74, t: 30, c: -10, h: -16, ah: [64, 78], lf: [30, 72] } ] },
    // ноги ведутся углами — остаются прямыми всю траекторию
    legraise: { dur: 1.6, mode: "pp", f: [
      { x: 48, y: 80, t: 94, aU: 80, aF: 0, lU: 268, lF: 1 },
      { x: 48, y: 80, t: 94, aU: 80, aF: 0, lU: 344, lF: 1 } ] },
    flutter: { dur: 0.7, mode: "pp", f: [
      { x: 48, y: 80, t: 94, aU: 80, aF: 0, lU: 258, lF: 1, lU2: 274, lF2: 1 },
      { x: 48, y: 80, t: 94, aU: 80, aF: 0, lU: 274, lF: 1, lU2: 258, lF2: 1 } ] },
    vup: { dur: 1.7, mode: "pp", f: [
      { x: 50, y: 80, t: 94, c: 0, ah: [86, 78], lU: 267, lF: 1 },
      { x: 50, y: 78, t: 44, c: -12, ah: [40, 58], lU: 325, lF: 1 } ] },
    bridge: { dur: 1.6, mode: "pp", f: [
      { x: 50, y: 81, t: 97, ah: [56, 84], lf: [34, 84] },
      { x: 50, y: 68, t: 115, c: 6, ah: [58, 84], lf: [34, 84] } ] },
    slbridge: { dur: 1.7, mode: "pp", f: [
      { x: 50, y: 81, t: 97, ah: [56, 84], lf: [34, 84], lf2: [20, 80] },
      { x: 50, y: 68, t: 115, c: 6, ah: [58, 84], lf: [34, 84], lf2: [22, 56] } ] },
    highknees: { dur: 0.75, mode: "pp", f: [
      { x: 50, y: 54, t: -4, aU: 205, aF: 100, aU2: 160, aF2: 100, lf: [46, 86], lf2: [52, 62], foot: 1 },
      { x: 50, y: 52, t: -4, aU: 160, aF: 100, aU2: 205, aF2: 100, lf: [46, 62], lf2: [52, 86], foot: 1 } ] },
    climber: { dur: 0.72, mode: "pp", f: [
      { x: 57, y: 58, t: 272, ah: [34, 85], lf: [50, 66], lf2: [82, 85] },
      { x: 57, y: 58, t: 272, ah: [34, 85], lf: [82, 85], lf2: [50, 66] } ] },
    burpee: { dur: 3.6, mode: "loop", f: [
      ST, CRO,
      { x: 60, y: 72, t: 282, ah: [36, 85], lf: [85, 84], foot: 1 },
      { x: 60, y: 78, t: 277, ah: [36, 85], lf: [86, 85], foot: 1 },
      { x: 60, y: 72, t: 282, ah: [36, 85], lf: [85, 84], foot: 1 },
      CRO, { x: 50, y: 42, t: 0, aU: 352, aF: -4, lf: [48, 76] } ] },
    sumo: { dur: 1.7, mode: "pp", front: 1, f: [
      { x: 50, y: 58, t: 0, aL: [196, 12], aR: [164, -12], alkL: [36, 86], alkR: [64, 86], foot: 1 },
      { x: 50, y: 70, t: 0, aL: [200, 16], aR: [160, -16], alkL: [36, 86], alkR: [64, 86], foot: 1 } ] },
    sidelunge: { dur: 1.8, mode: "pp", front: 1, f: [
      { x: 50, y: 56, t: 0, alkL: [44, 86], alkR: [56, 86], foot: 1 },
      { x: 46, y: 68, t: -6, alkL: [38, 86], alkR: [74, 86], foot: 1 } ] },
    curtsy: { dur: 1.8, mode: "pp", front: 1, f: [
      { x: 50, y: 56, t: 0, alkL: [46, 86], alkR: [54, 86], foot: 1 },
      { x: 50, y: 68, t: 5, alkL: [47, 86], alkR: [30, 82], kR: -1, foot: 1 } ] },
  };

  const MAP = {
    pushup: "pushup", widepushup: "pushwide", inclinepushup: "incline", declinepushup: "decline",
    diamondpushup: "pushdiamond", kneepushup: "kneepush", pikepushup: "pike", tricepdip: "dip",
    superman: "superman", birddog: "birddog", donkeykick: "donkey",
    plank: "plank", sideplank: "sideplank", wallsit: "wallsit",
    situp: "situp", crunch: "crunch", vup: "vup", reversecrunch: "revcrunch",
    bicyclecrunch: "bicycle", heeltouches: "heeltouch", russiantwist: "twist",
    legraise: "legraise", flutterkicks: "flutter",
    squat: "squat", jumpsquat: "jumpsquat", squatpulse: "pulse", sumosquat: "sumo",
    lunge: "lunge", reverselunge: "rlunge", curtsylunge: "curtsy", sidelunge: "sidelunge", lungejump: "lungejump",
    glutebridge: "bridge", hipthrust: "hipthrust", singlelegbridge: "slbridge",
    goodmorning: "gm", toetouch: "toetouch",
    calfraise: "calf", highknees: "highknees", mountainclimber: "climber", burpee: "burpee",
  };

  function playlist(anim, frames) {
    if (anim.mode === "loop" || frames.length === 1) return frames;
    const pl = frames.slice();
    for (let i = frames.length - 2; i >= 1; i--) pl.push(frames[i]);
    return pl;
  }
  function el(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }
  function pts(arr, dx) { return arr.map((p) => (p[0] + dx) + "," + p[1]).join(" "); }

  function makeInto(container, exKey, freeze) {
    const anim = A[MAP[exKey]] || A.squat;
    const base = { eS: anim.eS, kS: anim.kS, kS2: anim.kS2, kind: anim.raw ? "raw" : anim.front ? "front" : "side" };
    const frames = anim.f.map((f) => Object.assign({}, base, f));
    const pl = playlist(anim, frames), M = pl.length;
    container.innerHTML = "";
    const svg = el("svg", { viewBox: "0 0 100 94", class: "yfig-svg" });
    (anim.props || []).forEach((pr) => svg.appendChild(el("line", { class: "yfig-prop", x1: pr[0], y1: pr[1], x2: pr[2], y2: pr[3] })));
    svg.appendChild(el("line", { class: "yfig-ground", x1: 8, y1: 88, x2: 92, y2: 88 }));
    if (anim.badge === "diamond") {
      // схема постановки рук: две ладони, указательные+большие пальцы образуют ромб
      svg.appendChild(el("circle", { class: "yfig-badge-bg", cx: 76, cy: 20, r: 15 }));
      svg.appendChild(el("polygon", { class: "yfig-badge", points: "76,12 82,20 76,28 70,20" }));
      svg.appendChild(el("ellipse", { class: "yfig-badge-hand", cx: 66.5, cy: 20, rx: 4.2, ry: 6.5 }));
      svg.appendChild(el("ellipse", { class: "yfig-badge-hand", cx: 85.5, cy: 20, rx: 4.2, ry: 6.5 }));
    }
    const legF = el("polyline", { class: "yfig-far", fill: "none" });
    const armF = el("polyline", { class: "yfig-far", fill: "none" });
    const handF = el("circle", { class: "yfig-hand-far", r: 3 });
    const torso = el("polyline", { class: "yfig-body", fill: "none" });
    const neck = el("line", { class: "yfig-neck" });
    const legN = el("polyline", { class: "yfig-limb", fill: "none" });
    const armN = el("polyline", { class: "yfig-limb", fill: "none" });
    const handN = el("circle", { class: "yfig-hand", r: 3 });
    const head = el("circle", { class: "yfig-head", r: 7.5 });
    [legF, armF, handF, torso, neck, legN, armN, handN, head].forEach((n) => svg.appendChild(n));
    container.appendChild(svg);

    function draw(p) {
      const s = p.kind === "raw"
        ? { torso: p.to, neck: [p.to[0], p.to[0]], head: p.hd, armN: p.aN, armF: p.aF2r, legN: p.lN, legF: p.lF2r, far: 0 }
        : p.kind === "front" ? solveFront(p) : solveSide(p);
      torso.setAttribute("points", pts(s.torso, 0));
      neck.setAttribute("x1", s.neck[0][0]); neck.setAttribute("y1", s.neck[0][1]);
      neck.setAttribute("x2", s.neck[1][0]); neck.setAttribute("y2", s.neck[1][1]);
      armF.setAttribute("points", pts(s.armF, s.far));
      legF.setAttribute("points", pts(s.legF, s.far));
      armN.setAttribute("points", pts(s.armN, 0));
      legN.setAttribute("points", pts(s.legN, 0));
      const wN = s.armN[2], wF = s.armF[2];
      handN.setAttribute("cx", wN[0]); handN.setAttribute("cy", wN[1]);
      handF.setAttribute("cx", wF[0] + s.far); handF.setAttribute("cy", wF[1]);
      head.setAttribute("cx", s.head[0]); head.setAttribute("cy", s.head[1]);
    }

    if (typeof freeze === "number") { draw(frames[freeze % frames.length]); return { stop() { container.innerHTML = ""; } }; }
    let raf = 0, start = 0;
    function frame(now) {
      if (!start) start = now;
      const t = (((now - start) / 1000) / anim.dur) % 1;
      let pose;
      if (M === 1) { pose = Object.assign({}, pl[0]); pose.y += Math.sin((now - start) / 900) * 0.8; }
      else { const x = t * M, i = Math.floor(x) % M, j = (i + 1) % M; pose = lerpPose(pl[i], pl[j], smooth(x - Math.floor(x))); }
      draw(pose);
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    return { stop() { if (raf) cancelAnimationFrame(raf); container.innerHTML = ""; } };
  }

  window.YvyFig = { makeInto, has: (k) => !!MAP[k] };
})();
