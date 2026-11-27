/*
 * ep02_encolher/scenes.js : Episodio 2 ("E se voce encolhesse pela metade todo dia?")
 * 16 cenarios originais animados quadro a quadro em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
 * Contrato: funcao pura do tempo t. Zero estado mutavel, zero Math.random, zero emoji/travessao.
 */
(function (root) {
  'use strict';
  const W = 1080, H = 1920;
  const B = root.Beto, HUD = root.HUD;
  const INK = B.INK, PAL = B.PAL;

  // ----------------------------------------------------------------- matematica
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  const eIO = k => k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  const eOut = k => 1 - Math.pow(1 - k, 3);
  const eIn = k => k * k * k;
  const eBack = k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
  function hash(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }
  function vnoise(x) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u) * 2 - 1; }

  function kf(t, pts, ef) {
    ef = ef || eIO;
    if (t <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      if (t < b[0]) { const k = (t - a[0]) / Math.max(1e-6, b[0] - a[0]); return lerp(a[1], b[1], (b[2] || ef)(k)); }
    }
    return pts[pts.length - 1][1];
  }
  function hits(t, list) {
    let a = 0;
    for (const h of list) { const k = (t - h.t) / h.d; if (k >= 0 && k < 1) a += h.a * (1 - k) * (1 - k); }
    return a;
  }
  function camApply(ctx, c, t) {
    const s = c.shake || 0;
    ctx.translate(W / 2 + s * vnoise(t * 23 + 3.1), H / 2 + s * vnoise(t * 23 + 17.7));
    ctx.rotate((c.r || 0) + s * 0.0011 * vnoise(t * 17 + 9.3));
    ctx.scale(c.z, c.z);
    ctx.translate(-c.x, -c.y);
  }
  function drawBeto(ctx, st, o) {
    B.draw(ctx, Object.assign({ pose: st.pose, expr: st.expr, blink: st.blinkBoost }, o));
  }
  const pelvisFromFeet = (feetY, s) => feetY - B.STAND_PELVIS * s;

  // ------------------------------------------------------- poses customizadas
  const RUN_A = Object.assign({}, B.POSES.idle, {
    lean: -18, ua_r: -44, la_r: 18, ua_l: 72, la_l: 118,
    th_r: -36, sh_r: 44, th_l: 60, sh_l: -8, hand_r: 1, hand_l: 1, head: 6
  });
  const RUN_B = Object.assign({}, B.POSES.idle, {
    lean: -18, ua_r: 72, la_r: 118, ua_l: -44, la_l: 18,
    th_r: 60, sh_r: -8, th_l: -36, sh_l: 44, hand_r: 1, hand_l: 1, head: 6
  });
  const CLIMB_A = Object.assign({}, B.POSES.idle, {
    lean: 10, ua_r: 132, la_r: 152, ua_l: 76, la_l: 118,
    th_r: 22, sh_r: -18, th_l: 64, sh_l: -56, hand_r: 1, hand_l: 1, head: -14
  });
  const CLIMB_B = Object.assign({}, B.POSES.idle, {
    lean: 10, ua_r: 76, la_r: 118, ua_l: 132, la_l: 152,
    th_r: 64, sh_r: -56, th_l: 22, sh_l: -18, hand_r: 1, hand_l: 1, head: -14
  });
  const REACH_UP = Object.assign({}, B.POSES.idle, {
    lean: 6, ua_r: 136, la_r: 158, ua_l: 28, la_l: 12,
    th_r: 8, sh_r: -4, th_l: 12, sh_l: 6, hand_r: 0, hand_l: 0, head: -18
  });
  const runLeftPose = (t, freq) => B.mixObj(RUN_A, RUN_B, 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * freq));
  const climbPose = (t, freq) => B.mixObj(CLIMB_A, CLIMB_B, 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * freq));

  // -------------------------------------------------------- pinceis e helpers
  function vGrad(ctx, stops, y0, y1) {
    const g = ctx.createLinearGradient(0, y0 === undefined ? 0 : y0, 0, y1 === undefined ? H : y1);
    stops.forEach(s => g.addColorStop(s[0], s[1]));
    return g;
  }
  function fillScreen(ctx, style) { ctx.fillStyle = style; ctx.fillRect(-60, -60, W + 120, H + 120); }
  function rr(ctx, x, y, w, h, r) { HUD.roundRect(ctx, x, y, w, h, r); }
  function outlined(ctx, fill, lw) {
    ctx.fillStyle = fill; ctx.fill();
    ctx.lineWidth = lw || 6; ctx.strokeStyle = INK; ctx.lineJoin = 'round'; ctx.stroke();
  }
  function label(ctx, txt, x, y, size, fill, align, font) {
    ctx.save();
    ctx.font = `${size}px ${font || HUD.FONT_DISPLAY}`;
    ctx.textAlign = align || 'center'; ctx.textBaseline = 'middle';
    if (fill !== INK) {
      ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(6, size * 0.16);
      ctx.strokeStyle = INK; ctx.strokeText(txt, x, y);
    }
    ctx.fillStyle = fill; ctx.fillText(txt, x, y);
    ctx.restore();
  }
  function glow(ctx, x, y, r, color, a) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, color.replace('A', String(a)));
    g.addColorStop(1, color.replace('A', '0'));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  function contactShadow(ctx, x, y, w, a) {
    ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = '#000000';
    ctx.beginPath(); ctx.ellipse(x, y, w, w * 0.18, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
  function radialBurst(ctx, t, cx, cy, c1, c2, rays, spin) {
    fillScreen(ctx, c2);
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(t * (spin || 0.25));
    ctx.fillStyle = c1;
    for (let i = 0; i < rays; i++) {
      const a0 = i / rays * Math.PI * 2, a1 = a0 + Math.PI / rays;
      ctx.beginPath(); ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(a0) * 2600, Math.sin(a0) * 2600);
      ctx.lineTo(Math.cos(a1) * 2600, Math.sin(a1) * 2600);
      ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    const g = ctx.createRadialGradient(cx, cy, 40, cx, cy, 900);
    g.addColorStop(0, 'rgba(255,190,120,0.52)'); g.addColorStop(1, 'rgba(255,120,80,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
  function speedRadial(ctx, t, cx, cy, n, color, alpha, inner, seed) {
    ctx.save(); ctx.strokeStyle = color; ctx.lineCap = 'round';
    for (let i = 0; i < n; i++) {
      const a = hash(i + (seed || 0)) * Math.PI * 2;
      const ph = (t * (2.2 + hash(i * 3.1) * 2) + hash(i * 7.7)) % 1;
      const r0 = (inner || 420) + (1 - ph) * 900, len = 140 + hash(i * 5.3) * 380;
      ctx.globalAlpha = alpha * Math.sin(ph * Math.PI);
      ctx.lineWidth = 3 + hash(i * 2.9) * 9;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
      ctx.stroke();
    }
    ctx.restore();
  }
  function pill(ctx, x, y, w, h, bg, borderCol, txt, txtCol, size) {
    ctx.save();
    rr(ctx, x - w / 2, y - h / 2, w, h, 16);
    outlined(ctx, bg, 5);
    if (borderCol) {
      ctx.strokeStyle = borderCol; ctx.lineWidth = 3;
      rr(ctx, x - w / 2 + 6, y - h / 2 + 6, w - 12, h - 12, 11); ctx.stroke();
    }
    label(ctx, txt, x, y + 2, size || 34, txtCol);
    ctx.restore();
  }

  // ------------------------------------------------ regua logaritmica de escala
  const SIZE_MARKS = [
    { m: 1.8, txt: '1,8m' },
    { m: 0.1, txt: '10cm' },
    { m: 0.01, txt: '1cm' },
    { m: 1e-3, txt: '1mm' },
    { m: 1e-6, txt: '1µm' },
    { m: 1e-10, txt: 'ÁTOMO' }
  ];
  function fmtSize(m) {
    if (m >= 1.0) return HUD.fmtNum(m, 2) + ' m';
    if (m >= 0.01) return HUD.fmtNum(Math.round(m * 100), 0) + ' cm';
    if (m >= 1e-3) return HUD.fmtNum(Math.round(m * 1000), 0) + ' mm';
    if (m >= 1e-6) return HUD.fmtNum(Math.round(m * 1e6), 0) + ' µm';
    if (m >= 1e-9) return HUD.fmtNum(Math.round(m * 1e9), 0) + ' nm';
    return '0,1 nm';
  }
  /** Regua vertical logaritmica (1,8m no topo -> ATOMO embaixo) na borda direita segura. */
  function sizeGauge(meters, opts) {
    opts = opts || {};
    return function drawSizeGauge(ctx) {
      const x = 1012, y0 = 1080, y1 = 360;
      const lmin = Math.log10(5e-11), lmax = Math.log10(2.2);
      const yOf = m => y0 - (Math.log10(clamp(m, 5e-11, 2.2)) - lmin) / (lmax - lmin) * (y0 - y1);
      ctx.save();
      rr(ctx, x - 14, y1 - 26, 28, y0 - y1 + 52, 14);
      ctx.fillStyle = 'rgba(11,15,25,0.68)'; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.78)'; ctx.stroke();
      const ym = yOf(meters);
      // barra preenchida do topo ate a altura atual (mostrando o encolhimento descendo)
      rr(ctx, x - 7, ym, 14, Math.max(0, y0 + 12 - ym), 7);
      ctx.fillStyle = opts.quantum ? '#A87BFF' : (opts.alert ? HUD.COLORS.alert : HUD.COLORS.accent);
      ctx.fill();
      ctx.font = `26px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const mk of SIZE_MARKS) {
        const yy = yOf(mk.m);
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
        ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
        ctx.strokeText(mk.txt, x - 32, yy + 1);
        ctx.fillStyle = mk.m <= 1e-10 ? '#7FF0FF' : 'rgba(255,255,255,0.94)';
        ctx.fillText(mk.txt, x - 32, yy + 1);
      }
      ctx.save(); ctx.translate(x, ym);
      ctx.beginPath(); ctx.moveTo(0, -19); ctx.lineTo(19, 0); ctx.lineTo(0, 19); ctx.lineTo(-19, 0); ctx.closePath();
      ctx.fillStyle = opts.quantum ? '#A87BFF' : '#E8322A'; ctx.fill();
      ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
      ctx.restore();
      ctx.restore();
    };
  }

  // ------------------------------------------------ props biologicos e macro
  /** Cabeca colossal de formiga vista de perto (hook Plan B). */
  function drawGiantAntHead(ctx, x, y, s, t) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const snap = 0.5 + 0.5 * Math.sin(t * 14);
    // antenas articuladas
    for (const sd of [-1, 1]) {
      const tw = Math.sin(t * 9 + sd) * 14;
      ctx.strokeStyle = INK; ctx.lineWidth = 22;
      ctx.beginPath(); ctx.moveTo(sd * 70, -100); ctx.lineTo(sd * 155, -240 + tw); ctx.lineTo(sd * 280, -190 + tw * 1.4); ctx.stroke();
      ctx.strokeStyle = '#6E1818'; ctx.lineWidth = 10; ctx.stroke();
    }
    // mandibulas serrilhadas abrindo e fechando
    for (const sd of [-1, 1]) {
      ctx.save(); ctx.translate(sd * 75, 110); ctx.rotate(sd * (0.28 - snap * 0.22));
      ctx.beginPath();
      ctx.moveTo(0, 0); ctx.quadraticCurveTo(sd * 65, 95, -sd * 22, 185);
      ctx.lineTo(-sd * 42, 145); ctx.lineTo(-sd * 15, 118); ctx.lineTo(-sd * 38, 86); ctx.lineTo(-sd * 10, 56);
      ctx.closePath();
      outlined(ctx, '#3A0C0C', 8);
      ctx.restore();
    }
    // cranio brilhante de formiga
    ctx.beginPath(); ctx.ellipse(0, -10, 175, 155, 0, 0, Math.PI * 2);
    const hg = ctx.createRadialGradient(-45, -60, 25, 0, 0, 190);
    hg.addColorStop(0, '#B5322A'); hg.addColorStop(0.55, '#6B1515'); hg.addColorStop(1, '#2D090B');
    outlined(ctx, hg, 10);
    // olhos compostos gigantes com brilho feroz
    for (const sd of [-1, 1]) {
      ctx.beginPath(); ctx.ellipse(sd * 112, -26, 46, 62, sd * 0.22, 0, Math.PI * 2);
      outlined(ctx, '#12080E', 7);
      ctx.fillStyle = '#FF3B3B'; ctx.beginPath(); ctx.ellipse(sd * 102, -32, 16, 22, sd * 0.2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(sd * 96, -46, 9, 0, Math.PI * 2); ctx.fill();
    }
    // reflexo especular na carapaca
    ctx.fillStyle = 'rgba(255,210,190,0.3)';
    ctx.beginPath(); ctx.ellipse(-52, -88, 52, 22, -0.35, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  /** Formiga gigante corpo inteiro do tamanho de um cavalo correndo para a esquerda (dia8). */
  function drawHorseAnt(ctx, x, y, s, t) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const step = t * 18;
    // 3 pernas do lado distante
    for (let i = 0; i < 3; i++) {
      const ph = Math.sin(step + i * 2.1);
      const bx = -30 + i * 55;
      ctx.strokeStyle = INK; ctx.lineWidth = 22;
      ctx.beginPath(); ctx.moveTo(bx, 18); ctx.lineTo(bx + ph * 26 - 10, -25); ctx.lineTo(bx + ph * 44 - 28, 130); ctx.stroke();
      ctx.strokeStyle = '#3B0C0E'; ctx.lineWidth = 10; ctx.stroke();
    }
    // abdomen (gaster) grande com faixas
    ctx.beginPath(); ctx.ellipse(175, -18, 128, 92, 0.16, 0, Math.PI * 2);
    const ag = ctx.createRadialGradient(145, -52, 20, 175, -18, 135);
    ag.addColorStop(0, '#A82E26'); ag.addColorStop(0.6, '#5A1111'); ag.addColorStop(1, '#260708');
    outlined(ctx, ag, 9);
    // torax musculoso
    ctx.beginPath(); ctx.ellipse(16, -4, 72, 54, -0.1, 0, Math.PI * 2);
    outlined(ctx, '#731818', 8);
    // cabeca furiosa voltada para a esquerda (-x)
    ctx.save(); ctx.translate(-108, -28); ctx.rotate(-0.14);
    // mandibulas
    const snap = Math.sin(t * 22) * 0.16;
    for (const sd of [-1, 1]) {
      ctx.save(); ctx.translate(-68, 22); ctx.rotate(sd * (0.28 + snap));
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(-48, sd * 24, -84, -sd * 8); ctx.lineTo(-42, -sd * 14); ctx.closePath();
      outlined(ctx, '#2E0909', 6);
      ctx.restore();
    }
    ctx.beginPath(); ctx.ellipse(0, 0, 74, 62, 0, 0, Math.PI * 2); outlined(ctx, '#8A2020', 8);
    // olho furioso
    ctx.beginPath(); ctx.ellipse(-28, -14, 22, 26, -0.2, 0, Math.PI * 2); outlined(ctx, '#14080C', 5);
    ctx.fillStyle = '#FF3838'; ctx.beginPath(); ctx.arc(-32, -16, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(-36, -21, 4, 0, Math.PI * 2); ctx.fill();
    // sobrancelha furiosa
    ctx.strokeStyle = INK; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(-54, -42); ctx.lineTo(-6, -24); ctx.stroke();
    // antenas
    ctx.strokeStyle = INK; ctx.lineWidth = 14;
    ctx.beginPath(); ctx.moveTo(-42, -48); ctx.lineTo(-92, -110 + Math.sin(t * 14) * 8); ctx.lineTo(-155, -82); ctx.stroke();
    ctx.strokeStyle = '#731818'; ctx.lineWidth = 6; ctx.stroke();
    ctx.restore();
    // 3 pernas do lado proximo
    for (let i = 0; i < 3; i++) {
      const ph = Math.sin(step + i * 2.1 + Math.PI);
      const bx = -42 + i * 58;
      ctx.strokeStyle = INK; ctx.lineWidth = 26;
      ctx.beginPath(); ctx.moveTo(bx, 22); ctx.lineTo(bx + ph * 34, -18); ctx.lineTo(bx + ph * 56 - 12, 142); ctx.stroke();
      ctx.strokeStyle = '#6E1818'; ctx.lineWidth = 12; ctx.stroke();
    }
    ctx.restore();
  }

  /** Virus bacteriofago estilizado como nave alienigena (dia20). */
  function drawPhageShip(ctx, x, y, s, t, seed) {
    ctx.save(); ctx.translate(x, y + Math.sin(t * 2.6 + seed) * 14); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    // feixe alienigena abaixo da nave
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    const bg = ctx.createLinearGradient(0, 75, 0, 290);
    bg.addColorStop(0, 'rgba(92,238,255,0.45)'); bg.addColorStop(1, 'rgba(92,238,255,0)');
    ctx.fillStyle = bg; ctx.beginPath(); ctx.moveTo(-26, 75); ctx.lineTo(26, 75); ctx.lineTo(95, 290); ctx.lineTo(-95, 290); ctx.closePath(); ctx.fill();
    ctx.restore();
    // 6 pernas aracnideas de pouso
    for (const sd of [-1, 1]) {
      for (let k = 0; k < 3; k++) {
        const sp = 0.65 + k * 0.35;
        const w = Math.sin(t * 5 + seed + k) * 6;
        ctx.strokeStyle = INK; ctx.lineWidth = 14;
        ctx.beginPath(); ctx.moveTo(sd * 16, 68); ctx.lineTo(sd * 78 * sp, 102 + w); ctx.lineTo(sd * 116 * sp, 178 + w); ctx.stroke();
        ctx.strokeStyle = '#5CEEFF'; ctx.lineWidth = 5; ctx.stroke();
      }
    }
    // haste helicoidal
    rr(ctx, -18, -14, 36, 92, 8); outlined(ctx, '#4B368A', 6);
    ctx.strokeStyle = '#7FF0FF'; ctx.lineWidth = 4;
    for (let yk = 0; yk < 5; yk++) { ctx.beginPath(); ctx.moveTo(-14, 2 + yk * 16); ctx.lineTo(14, 2 + yk * 16); ctx.stroke(); }
    // cabeca icosaedrica facetada
    ctx.beginPath();
    ctx.moveTo(0, -150); ctx.lineTo(76, -104); ctx.lineTo(76, -34);
    ctx.lineTo(0, 8); ctx.lineTo(-76, -34); ctx.lineTo(-76, -104); ctx.closePath();
    const pg = ctx.createLinearGradient(-76, -150, 76, 8);
    pg.addColorStop(0, '#B988FF'); pg.addColorStop(0.5, '#6C3CE0'); pg.addColorStop(1, '#311B78');
    outlined(ctx, pg, 7);
    // facetas internas luminosas
    ctx.strokeStyle = 'rgba(155,245,255,0.72)'; ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(0, -150); ctx.lineTo(0, 8);
    ctx.moveTo(-76, -104); ctx.lineTo(0, -70); ctx.lineTo(76, -104);
    ctx.moveTo(-76, -34); ctx.lineTo(0, -70); ctx.lineTo(76, -34);
    ctx.stroke();
    glow(ctx, 0, -70, 58, 'rgba(130,245,255,A)', 0.55);
    ctx.restore();
  }

  // ==================================================================== CENAS
  const SC = {};

  // ------------------------------------------------------------------ 1. HOOK
  SC.hook = {
    times(S) {
      return {
        tE: S.c('hook', 'É'),
        tV2: S.c('hook', 'você', 1),
        tM: S.w('hook', 'mesmo').t0,
        tUma: S.c('hook', 'Uma') - 0.04,
        tFor: S.w('hook', 'formiga').t0,
        tAlm: S.c('hook', 'almoço')
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: 0, pose: 'shock_closeup', expr: 'scream' },
        { t: T.tE, expr: 'shock' },
        { t: T.tV2, pose: 'point_hook', expr: 'focus', dur: 0.14, ease: 'back' },
        { t: T.tM, expr: 'scream' },
        { t: T.tUma, pose: 'shock_closeup', expr: 'shock', dur: 0.04 },
        { t: T.tAlm, pose: 'dodge_lean', expr: 'panic', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tV2, T.tUma, T.tFor, T.tAlm]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const T = this.times(S);
      if (t < T.tUma) {
        // Plano A: explosao carmim + Beto apontando (braco real preso)
        const z = kf(t, [[0, 3.6], [T.tE, 3.6], [T.tE + 0.2, 2.9, eBack], [T.tV2, 2.9], [T.tV2 + 0.2, 2.35, eBack]]);
        const shake = hits(t, [{ t: 0, a: 40, d: 0.7 }, { t: T.tM, a: 24, d: 0.35 }]) + 4;
        radialBurst(ctx, t, 540, 760, '#B0141F', '#6E0B12', 22, 0.36);
        speedRadial(ctx, t, 540, 760, 68, '#FFE9D6', 0.55, 380, 11);
        const bx = 540, by = 1180;
        const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);
        ctx.save();
        camApply(ctx, { x: bx, y: headY + (960 - 760) / z, z, shake }, t);
        drawBeto(ctx, st, { x: bx, y: by, scale: 1, t, rim: { color: '#FFB25C', dir: [0.8, -0.6] }, wind: [0, -10] });
        ctx.restore();
        return;
      }
      // Plano B: cabeca colossal da formiga baixando sobre o Beto minusculo no quintal!
      const lt = t - T.tUma;
      const z = kf(t, [[T.tUma, 1.05], [T.tAlm, 1.24, eBack], [S.end('hook'), 1.3]]);
      const shake = hits(t, [{ t: T.tUma, a: 26, d: 0.35 }, { t: T.tAlm, a: 30, d: 0.5 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, '#1D4D26'], [0.45, '#3E8F43'], [1, '#7D5432']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      // folhas gigantes de grama atras
      for (let i = 0; i < 9; i++) {
        const gx = -120 + i * 165;
        ctx.beginPath(); ctx.moveTo(gx, 1450); ctx.quadraticCurveTo(gx + (i % 2 ? 90 : -90), 820, gx + (i % 2 ? 40 : -40), 180);
        ctx.lineTo(gx + 85, 1450); ctx.closePath();
        outlined(ctx, i % 2 ? '#2B7D38' : '#3E9B47', 6);
      }
      // chao de terra + sombra ameaçadora da formiga
      ctx.fillStyle = vGrad(ctx, [[0, '#8A5B36'], [1, '#4F301A']], 1060, H); ctx.fillRect(-250, 1060, W + 500, 960);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-250, 1060); ctx.lineTo(W + 250, 1060); ctx.stroke();
      contactShadow(ctx, 560, 1210, 420, 0.45);
      // cabeca da formiga descendo por cima!
      const antY = lerp(390, 565, eOut(clamp(lt / 1.4, 0, 1)));
      drawGiantAntHead(ctx, 575, antY, 1.55, t);
      // Beto minusculo recuando em panico
      const feet = 1235, bs = 0.66;
      contactShadow(ctx, 430, feet, 58, 0.4);
      drawBeto(ctx, st, {
        x: 430 - lt * 18, y: pelvisFromFeet(feet, bs), scale: bs, t,
        rim: { color: '#FF7060', dir: [0.6, -0.8] }
      });
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 2. PREMISSA
  const HALF_BARS = [180, 90, 45, 22, 11, 5];
  SC.premissa = {
    keys(S) {
      const s0 = S.start('premissa');
      return [
        { t: s0, pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('premissa', 'metade'), pose: 'shock_closeup', expr: 'shock', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'dias'), pose: 'shrug_question', expr: 'panic', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('premissa', 'altura'), S.c('premissa', 'metade'), S.c('premissa', 'dias')]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), tM = S.w('premissa', 'metade').t0;
      const shake = hits(t, [{ t: tM, a: 24, d: 0.45 }, { t: s0, a: 12, d: 0.3 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#0C1838'], [1, '#13285A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.06], [tM, 1.0], [S.end('premissa'), 1.04]]), shake }, t);
      const off = (t * 32) % 54;
      ctx.lineWidth = 2;
      for (let x = -54 + off; x < W + 54; x += 54) {
        ctx.strokeStyle = (Math.round((x - off) / 54) % 5 === 0) ? 'rgba(120,200,255,0.28)' : 'rgba(120,200,255,0.12)';
        ctx.beginPath(); ctx.moveTo(x, -200); ctx.lineTo(x, H + 200); ctx.stroke();
      }
      for (let y = -54 + off; y < H + 54; y += 54) {
        ctx.strokeStyle = (Math.round((y - off) / 54) % 5 === 0) ? 'rgba(120,200,255,0.28)' : 'rgba(120,200,255,0.12)';
        ctx.beginPath(); ctx.moveTo(-200, y); ctx.lineTo(W + 200, y); ctx.stroke();
      }
      const ground = 1265, maxH = 700, pts = [];
      ctx.strokeStyle = '#7FD0FF'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(40, ground); ctx.lineTo(1040, ground); ctx.stroke();
      HALF_BARS.forEach((cm, i) => {
        const x = 395 + i * 104, w = 72;
        const k = clamp((t - (s0 + 0.25 + i * 0.16)) / 0.28, 0, 1);
        const h = (cm / 180) * maxH * (k > 0 ? eBack(k) : 0);
        if (h > 1) {
          rr(ctx, x - w / 2, ground - h, w, h, 12);
          const g = ctx.createLinearGradient(0, ground - h, 0, ground);
          g.addColorStop(0, i === 0 ? '#FFE86B' : '#FFD400'); g.addColorStop(1, '#DF9B00');
          outlined(ctx, g, 6);
        }
        if (k > 0.6) label(ctx, cm + 'cm', x, ground - h - 32, 32, '#FFFFFF');
        label(ctx, 'D' + i, x, ground + 40, 34, '#9FD8FF');
        pts.push([x, ground - (cm / 180) * maxH, k]);
      });
      ctx.save(); ctx.setLineDash([16, 14]); ctx.lineDashOffset = -t * 60;
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 5; ctx.beginPath();
      let started = false;
      for (const p of pts) { if (p[2] <= 0.6) break; started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; }
      ctx.stroke(); ctx.restore();
      // carimbo ÷2 POR DIA no topo-direito livre (acima das barras menores!)
      const ks = clamp((t - (tM - 0.05)) / 0.22, 0, 1);
      if (ks > 0) {
        ctx.save(); ctx.translate(740, 560); ctx.rotate(0.1);
        const sc = 2.2 - 1.2 * eBack(ks); ctx.scale(sc, sc);
        ctx.globalAlpha = clamp(ks * 2, 0, 1);
        label(ctx, '÷2', 0, 0, 220, '#FFD400', 'center', HUD.FONT_CAPTION);
        label(ctx, 'POR DIA', 0, 134, 66, '#FFFFFF', 'center', HUD.FONT_CAPTION);
        ctx.restore();
      }
      // Beto a esquerda encolhendo pela metade em tempo real!
      const shrinkK = clamp((t - tM) / 0.45, 0, 1);
      const bs = lerp(1.06, 0.56, eBack(shrinkK));
      contactShadow(ctx, 180, ground, 95 * bs, 0.36);
      drawBeto(ctx, st, { x: 180, y: pelvisFromFeet(ground, bs), scale: bs, t, rim: { color: '#7FD0FF', dir: [1, -0.3] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 3. DIA 1
  SC.dia1 = {
    times(S) { return { tAlc: S.c('dia1', 'alcançar'), tMac: S.w('dia1', 'maçaneta').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia1'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: T.tAlc, pose: 'jump_up', expr: 'focus', dur: 0.16 },
        { t: T.tMac, expr: 'panic' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tAlc, T.tMac]; },
    hud(S, t) {
      const s0 = S.start('dia1');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia1', 'centímetros').t1, 1.8, 0.9);
      return { bar: { day: 1, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia1');
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }]);
      fillScreen(ctx, '#EDD5B2');
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tMac, 1.08]]), shake }, t);
      // papel de parede listrado
      for (let x = -150; x < W + 150; x += 72) { ctx.fillStyle = 'rgba(205,160,110,0.24)'; ctx.fillRect(x, -100, 28, 1280); }
      // piso de madeira + rodape
      ctx.fillStyle = '#FFFDF7'; ctx.fillRect(-150, 1140, W + 300, 50);
      ctx.fillStyle = vGrad(ctx, [[0, '#BD7B46'], [1, '#844F2A']], 1190, H); ctx.fillRect(-150, 1190, W + 300, 800);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-150, 1190); ctx.lineTo(W + 150, 1190); ctx.stroke();
      // batente e porta gigante de madeira ocupando a metade direita
      rr(ctx, 415, 290, 495, 920, 10); outlined(ctx, '#6E3F20', 8);
      rr(ctx, 445, 320, 435, 880, 6); outlined(ctx, '#995E36', 7);
      // almofadas decorativas da porta
      rr(ctx, 490, 365, 345, 250, 8); outlined(ctx, '#854E2A', 5);
      rr(ctx, 490, 745, 345, 390, 8); outlined(ctx, '#854E2A', 5);
      // macaneta dourada lá no alto (1,05 m do chao!)
      const kx = 525, ky = 685;
      rr(ctx, kx - 26, ky - 56, 52, 118, 18); outlined(ctx, '#D49A28', 6);
      rr(ctx, kx - 12, ky - 14, 106, 28, 14); outlined(ctx, '#FFD400', 6);
      ctx.beginPath(); ctx.arc(kx, ky, 18, 0, Math.PI * 2); outlined(ctx, '#FFE97D', 5);
      // marca de altura da macaneta
      ctx.save(); ctx.setLineDash([12, 10]); ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.moveTo(220, ky); ctx.lineTo(kx - 36, ky); ctx.stroke(); ctx.restore();
      pill(ctx, 180, ky, 142, 58, '#FFD400', null, '1,05 m', INK, 34);
      // Beto pulando na ponta dos pes tentando (sem conseguir!) alcancar a macaneta
      const feet = 1245, bs = 0.88;
      const reachHop = Math.max(0, Math.sin((t - T.tAlc) * 7.5)) * (t > T.tAlc ? 54 : 0);
      contactShadow(ctx, 375, feet, 80 * (1 - reachHop / 180), 0.35);
      drawBeto(ctx, st, {
        x: 375, y: pelvisFromFeet(feet, bs) - reachHop, scale: bs, t,
        pose: t > T.tAlc ? REACH_UP : st.pose,
        rim: { color: '#FFE8B0', dir: [-0.8, -0.5] }
      });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 4. DIA 2
  SC.dia2 = {
    times(S) { return { tTen: S.c('dia2', 'tênis'), tLan: S.w('dia2', 'lancha').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia2'), pose: 'idle', expr: 'amazed', dur: 0.01 },
        { t: T.tTen, pose: 'flex', expr: 'smug', dur: 0.16, ease: 'back' },
        { t: T.tLan, pose: 'soar_spread', expr: 'amazed', dur: 0.2, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tTen, T.tLan]; },
    hud(S, t) {
      const s0 = S.start('dia2');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia2', 'centímetros').t1, 0.9, 0.45);
      return { bar: { day: 2, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia2');
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }, { t: T.tLan, a: 14, d: 0.3 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#D7ECFF'], [0.48, '#F7EFE1'], [1, '#C48A58']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [T.tLan, 1.12, eBack]]), shake }, t);
      // parede e piso do quarto
      ctx.fillStyle = '#F2DFC2'; ctx.fillRect(-200, -100, W + 400, 1080);
      ctx.fillStyle = vGrad(ctx, [[0, '#C98A54'], [1, '#8C5932']], 980, H); ctx.fillRect(-200, 980, W + 400, 1000);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 980); ctx.lineTo(W + 200, 980); ctx.stroke();
      // ondas estilizadas de "lancha" surgindo ao redor do tenis em tLan!
      const rock = Math.sin(t * 4.5) * 0.04;
      const sx = 490, sy = 1090;
      contactShadow(ctx, sx, sy + 130, 390, 0.4);
      ctx.save(); ctx.translate(sx, sy); ctx.rotate(rock);
      // parte de tras da boca do tenis (atras do Beto)
      ctx.beginPath(); ctx.ellipse(-105, -92, 118, 46, -0.08, 0, Math.PI * 2); outlined(ctx, '#28324A', 8);
      // Beto minusculo de pe dentro do proprio tenis como capitao de lancha!
      drawBeto(ctx, st, { x: -100, y: -152, scale: 0.56, t, rim: { color: '#FFF0B8', dir: [0.7, -0.7] } });
      // corpo gigante do tenis (fiel ao estilo do tenis do Beto!)
      ctx.beginPath();
      ctx.moveTo(-285, 70); ctx.lineTo(-270, -82); ctx.quadraticCurveTo(-210, -135, -150, -96);
      ctx.quadraticCurveTo(-55, -75, 48, -110); ctx.quadraticCurveTo(185, -80, 325, -8);
      ctx.quadraticCurveTo(368, 28, 345, 86); ctx.lineTo(-275, 86); ctx.closePath();
      outlined(ctx, PAL.shoe, 9);
      // sola grossa + faixa vermelha esportiva
      rr(ctx, -295, 70, 650, 52, 24); outlined(ctx, '#DCD6C8', 8);
      ctx.fillStyle = PAL.shoeAccent; ctx.fillRect(-275, 88, 610, 18);
      // cadarcos grossos como cabos nauticos
      ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.lineCap = 'round';
      for (let i = 0; i < 4; i++) {
        ctx.beginPath(); ctx.moveTo(45 + i * 44, -84 + i * 16); ctx.lineTo(88 + i * 44, -46 + i * 16); ctx.stroke();
      }
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 8;
      for (let i = 0; i < 4; i++) {
        ctx.beginPath(); ctx.moveTo(45 + i * 44, -84 + i * 16); ctx.lineTo(88 + i * 44, -46 + i * 16); ctx.stroke();
      }
      ctx.restore();
      if (t >= T.tLan - 0.15) {
        // ondinhas comicas de lancha na base do tenis
        ctx.strokeStyle = '#7FD6FF'; ctx.lineWidth = 7; ctx.lineCap = 'round';
        for (let i = 0; i < 4; i++) {
          const wy = sy + 115 + (i % 2) * 20;
          const wx = 130 + i * 210 + Math.sin(t * 7 + i) * 16;
          ctx.beginPath(); ctx.moveTo(wx, wy); ctx.quadraticCurveTo(wx + 55, wy - 22, wx + 110, wy); ctx.stroke();
        }
        pill(ctx, 725, 800, 230, 66, '#FFD400', null, 'LANCHA 45cm', INK, 34);
      }
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 5. DIA 4
  SC.dia4 = {
    times(S) { return { tSub: S.c('dia4', 'Subir'), tEsc: S.w('dia4', 'escalada').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia4'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tSub, expr: 'focus' },
        { t: T.tEsc, expr: 'panic' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tSub, T.tEsc]; },
    hud(S, t) {
      const s0 = S.start('dia4');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia4', 'centímetros').t1, 0.45, 0.11);
      return { bar: { day: 4, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia4'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.25 }, { t: T.tEsc, a: 16, d: 0.35 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#FFF1D4'], [0.42, '#D9A773'], [1, '#7D4E2A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tEsc, 1.12]]), shake }, t);
      // paredao vertical de UM UNICO DEGRAU de madeira gigante (altura 18cm = paredao alpino!)
      const stepTop = 490, stepBot = 1280;
      // luz do topo do degrau
      ctx.fillStyle = '#FFE5B4'; ctx.fillRect(-150, 260, W + 300, stepTop - 260);
      // espelho vertical do degrau (enorme penhasco de madeira)
      ctx.fillStyle = vGrad(ctx, [[0, '#A6693E'], [1, '#6E3E1F']], stepTop, stepBot);
      ctx.fillRect(190, stepTop, 740, stepBot - stepTop);
      ctx.strokeStyle = INK; ctx.lineWidth = 8; ctx.strokeRect(190, stepTop, 740, stepBot - stepTop);
      // veios da madeira
      ctx.strokeStyle = 'rgba(55,28,12,0.35)'; ctx.lineWidth = 4;
      for (let y = stepTop + 65; y < stepBot; y += 72) {
        ctx.beginPath(); ctx.moveTo(205, y); ctx.quadraticCurveTo(560, y + (y % 2 ? 14 : -14), 915, y); ctx.stroke();
      }
      // quina saliente do degrau no topo
      rr(ctx, 145, stepTop - 52, 820, 74, 18); outlined(ctx, '#C88550', 8);
      // chao inferior
      ctx.fillStyle = '#5E381E'; ctx.fillRect(-150, stepBot, W + 300, 700);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-150, stepBot); ctx.lineTo(W + 150, stepBot); ctx.stroke();
      // cota de medida do degrau (esquerda limpa)
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 5; ctx.setLineDash([14, 10]);
      ctx.beginPath(); ctx.moveTo(152, stepTop); ctx.lineTo(152, stepBot); ctx.stroke(); ctx.setLineDash([]);
      pill(ctx, 186, 860, 172, 60, '#FFD400', null, '1 DEGRAU', INK, 32);
      // corda de alpinismo ancorada na quina superior
      const climbY = lerp(1110, 760, eIO(clamp((t - (s0 + 0.35)) / 3.4, 0, 1)));
      ctx.strokeStyle = '#F5E6C4'; ctx.lineWidth = 8;
      ctx.beginPath(); ctx.moveTo(520, stepTop + 12); ctx.quadraticCurveTo(500, (stepTop + climbY) / 2, 510, climbY); ctx.stroke();
      // Beto minusculo escalando o paredao com suor e esforco
      drawBeto(ctx, st, {
        x: 505, y: climbY, scale: 0.46, t,
        pose: climbPose(t, 2.8),
        rim: { color: '#FFE6A8', dir: [0, -1] }
      });
      // nuvenzinhas de po de magnesio
      for (let i = 0; i < 6; i++) {
        const ph = (t * 2 + i * 0.17) % 1;
        ctx.fillStyle = `rgba(255,255,255,${(1 - ph) * 0.55})`;
        ctx.beginPath(); ctx.arc(505 + (hash(i + 40) - 0.5) * 90, climbY + 30 + ph * 90, 8 + ph * 14, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 6. DIA 6
  SC.dia6 = {
    times(S) { return { tGra: S.c('dia6', 'grama'), tFlo: S.w('dia6', 'floresta').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia6'), pose: 'look_down', expr: 'curious', dur: 0.01 },
        { t: T.tGra, pose: 'shock_closeup', expr: 'amazed', dur: 0.2 },
        { t: T.tFlo, pose: 'dodge_lean', expr: 'shock', dur: 0.2, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tGra, T.tFlo]; },
    hud(S, t) {
      const s0 = S.start('dia6');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia6', 'centímetros').t1, 0.11, 0.02);
      return { bar: { day: 6, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia6');
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tFlo, a: 18, d: 0.4 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#0D2915'], [0.45, '#1D5C2B'], [0.85, '#133A1D'], [1, '#08180C']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [T.tFlo, 1.14]]), shake }, t);
      // raios de sol atravessando a selva de grama
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 4; i++) {
        const rx = 180 + i * 240;
        const g = ctx.createLinearGradient(rx, 240, rx - 220, 1400);
        g.addColorStop(0, 'rgba(220,255,150,0.22)'); g.addColorStop(1, 'rgba(220,255,150,0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.moveTo(rx - 40, 200); ctx.lineTo(rx + 85, 200); ctx.lineTo(rx - 120, 1450); ctx.lineTo(rx - 280, 1450); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
      // folhas de grama gigantes ao fundo (balancando ao vento)
      for (let i = 0; i < 12; i++) {
        const bx = -100 + i * 110;
        const sway = Math.sin(t * 2.2 + i * 0.9) * 32;
        const lean = (i % 2 ? 1 : -1) * (110 + hash(i + 60) * 140) + sway;
        ctx.beginPath();
        ctx.moveTo(bx - 42, 1450);
        ctx.quadraticCurveTo(bx + lean * 0.4, 780, bx + lean, 160 + hash(i + 61) * 180);
        ctx.quadraticCurveTo(bx + lean * 0.4 + 55, 780, bx + 48, 1450);
        ctx.closePath();
        outlined(ctx, i % 3 === 0 ? '#1E692D' : (i % 3 === 1 ? '#328E3E' : '#45AA4B'), 6);
      }
      // solo de terra escura da floresta
      ctx.fillStyle = '#2B1F16'; ctx.fillRect(-200, 1210, W + 400, 800);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1210); ctx.lineTo(W + 200, 1210); ctx.stroke();
      // joaninha gigante subindo uma folha na direita (escala surreal!)
      const lby = 780 - (t - s0) * 36;
      ctx.save(); ctx.translate(770, lby); ctx.rotate(-0.2);
      ctx.beginPath(); ctx.ellipse(0, 0, 56, 72, 0, 0, Math.PI * 2); outlined(ctx, '#E82E26', 6);
      ctx.beginPath(); ctx.arc(0, -68, 28, 0, Math.PI * 2); outlined(ctx, '#161820', 5);
      ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(0, -45); ctx.lineTo(0, 72); ctx.stroke();
      ctx.fillStyle = INK;
      for (const [dx, dy] of [[-24, -14], [24, -10], [-20, 26], [22, 30]]) { ctx.beginPath(); ctx.arc(dx, dy, 11, 0, Math.PI * 2); ctx.fill(); }
      ctx.restore();
      // Beto minusculo perdido na floresta de grama
      const feet = 1248, bs = 0.54;
      contactShadow(ctx, 490, feet, 55, 0.45);
      drawBeto(ctx, st, { x: 490, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#C6FF8A', dir: [0.5, -0.8] } });
      // polen brilhante flutuando
      for (let i = 0; i < 32; i++) {
        const px = (hash(i + 620) * W + Math.sin(t + i) * 30);
        const py = 320 + ((hash(i + 621) * 960 + t * 28) % 960);
        ctx.fillStyle = 'rgba(240,255,170,0.72)'; ctx.beginPath(); ctx.arc(px, py, 3 + hash(i) * 4, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 7. DIA 8
  SC.dia8 = {
    times(S) { return { tFor: S.c('dia8', 'formiga'), tCav: S.w('dia8', 'cavalo').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia8'), pose: 'idle', expr: 'shock', dur: 0.01 },
        { t: T.tFor, expr: 'panic' },
        { t: T.tCav, expr: 'scream' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tFor, T.tCav, S.c('dia8', 'furioso')]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia8');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia8', 'milímetros').t1, 0.02, 0.007);
      const alert = t >= T.tFor;
      return {
        bar: { day: 8, dayT: s0, label: 'ALTURA', value: fmtSize(m), alert },
        customHud: sizeGauge(m, { alert }),
        alert: alert ? { text: 'PREDADOR GIGANTE', t0: T.tFor } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia8'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: T.tFor, a: 24, d: 0.5 }, { t: T.tCav, a: 22, d: 0.5 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, '#5FA8FF'], [0.45, '#B8DFB5'], [0.75, '#C89462'], [1, '#7D4E2B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tCav, 1.12, eBack]]), shake }, t);
      // pedregulhos gigantes (como montanhas) ao fundo
      for (let i = 0; i < 6; i++) {
        const px = ((i * 290 + lt * 340) % 1740) - 260;
        ctx.beginPath(); ctx.arc(px, 1080, 120 + (i % 3) * 55, Math.PI, 0); outlined(ctx, '#8F7A65', 6);
      }
      // solo poeirento correndo para a direita (Beto fugindo para a esquerda!)
      ctx.fillStyle = vGrad(ctx, [[0, '#BA8552'], [1, '#754927']], 1050, H); ctx.fillRect(-250, 1050, W + 500, 960);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-250, 1050); ctx.lineTo(W + 250, 1050); ctx.stroke();
      // formiga do tamanho de um cavalo furioso perseguindo pela direita!
      const antX = lerp(830, 620, clamp(lt / 3.8, 0, 1));
      contactShadow(ctx, antX + 20, 1215, 240, 0.42);
      drawHorseAnt(ctx, antX, 1065, 1.12, t);
      // poeira levantada pelas patas da formiga
      for (let i = 0; i < 10; i++) {
        const ph = (t * 2.4 + i * 0.1) % 1;
        ctx.fillStyle = `rgba(218,180,132,${(1 - ph) * 0.65})`;
        ctx.beginPath(); ctx.arc(antX + 60 + ph * 260, 1205 - ph * 95, 16 + ph * 34, 0, Math.PI * 2); ctx.fill();
      }
      // Beto fugindo desesperado na frente esquerda
      const feet = 1248, bs = 0.66, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 5.2)) * 18;
      contactShadow(ctx, 245, feet, 60, 0.38);
      drawBeto(ctx, st, {
        x: 245, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t,
        pose: runLeftPose(t, 5.2),
        rim: { color: '#FFE6A8', dir: [0.8, -0.5] }, wind: [85, 0]
      });
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 8. DIA 10
  SC.dia10 = {
    times(S) { return { tGot: S.c('dia10', 'gota'), tEsm: S.w('dia10', 'esmagar').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia10'), pose: 'shock_closeup', expr: 'shock', dur: 0.01 },
        { t: T.tGot, expr: 'panic' },
        { t: T.tEsm, pose: 'dodge_lean', expr: 'scream', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tGot, T.tEsm]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia10');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia10', 'milímetro').t1, 0.007, 0.001);
      const danger = t >= T.tGot - 0.05;
      return {
        bar: { day: 10, dayT: s0, label: 'ALTURA', value: fmtSize(m), alert: danger },
        customHud: sizeGauge(m, { alert: danger }),
        alert: danger ? { text: 'PERIGO DE IMPACTO', t0: T.tGot - 0.05 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia10');
      const dropK = clamp((t - (T.tGot - 0.5)) / Math.max(0.8, T.tEsm - T.tGot + 0.9), 0, 1);
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tEsm, a: 36, d: 0.7 }]) + dropK * 6;
      fillScreen(ctx, vGrad(ctx, [[0, '#101B32'], [0.45, '#2A4268'], [0.85, '#4A698E'], [1, '#263042']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tEsm, 1.14, eBack]]), shake }, t);
      // gotas menores caindo ao fundo
      ctx.strokeStyle = 'rgba(180,230,255,0.35)'; ctx.lineWidth = 4; ctx.lineCap = 'round';
      for (let i = 0; i < 28; i++) {
        const rx = hash(i + 1000) * W;
        const ry = ((hash(i + 1001) * 1600 + t * 1400) % 1600) - 200;
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(rx - 14, ry + 75); ctx.stroke();
      }
      // asfalto molhado + sombra gigante da gota crescendo sobre o Beto!
      ctx.fillStyle = '#242B3A'; ctx.fillRect(-200, 1170, W + 400, 820);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1170); ctx.lineTo(W + 200, 1170); ctx.stroke();
      contactShadow(ctx, 505, 1255, 80 + dropK * 240, 0.28 + dropK * 0.42);
      // Beto minusculo olhando para cima em pavor
      const feet = 1255, bs = 0.66;
      drawBeto(ctx, st, {
        x: 505 + (t >= T.tEsm ? 165 * eOut(clamp((t - T.tEsm) / 0.3, 0, 1)) : 0),
        y: pelvisFromFeet(feet, bs), scale: bs, t,
        rim: { color: '#9BE4FF', dir: [0, -1] }
      });
      // GOTA DE CHUVA COLOSSAL (tamanho de um meteoro de agua de 3mm sobre um Beto de 1mm!)
      const gy = lerp(635, 925, eIn(dropK));
      const gr = 148;
      ctx.save(); ctx.translate(505, gy);
      // linhas de ar atras da gota
      ctx.strokeStyle = 'rgba(200,245,255,0.65)'; ctx.lineWidth = 6; ctx.lineCap = 'round';
      for (const ox of [-98, 0, 98]) { ctx.beginPath(); ctx.moveTo(ox, -gr - 10); ctx.lineTo(ox, -gr - 62); ctx.stroke(); }
      ctx.beginPath();
      ctx.moveTo(0, -gr * 1.45);
      ctx.bezierCurveTo(gr * 1.05, -gr * 0.25, gr * 1.15, gr * 0.95, 0, gr);
      ctx.bezierCurveTo(-gr * 1.15, gr * 0.95, -gr * 1.05, -gr * 0.25, 0, -gr * 1.45);
      ctx.closePath();
      const dg = ctx.createRadialGradient(-55, -20, 20, 0, 10, gr * 1.35);
      dg.addColorStop(0, '#FFFFFF'); dg.addColorStop(0.28, '#B8F0FF'); dg.addColorStop(0.72, '#3D9AE8'); dg.addColorStop(1, '#1B5299');
      outlined(ctx, dg, 9);
      // reflexo de lente brilhante
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath(); ctx.ellipse(-62, -25, 24, 52, 0.3, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 9. DIA 13
  SC.dia13 = {
    times(S) { return { tPoe: S.c('dia13', 'poeira'), tFlu: S.w('dia13', 'flutuando').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia13'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tPoe, pose: 'space_float_panic', expr: 'curious', dur: 0.3 },
        { t: T.tFlu, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPoe, T.tFlu]; },
    hud(S, t) {
      const s0 = S.start('dia13');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia13', 'micrômetros').t1, 1e-3, 200e-6);
      return { bar: { day: 13, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia13'), lt = t - s0;
      fillScreen(ctx, vGrad(ctx, [[0, '#1D140B'], [0.45, '#4A341C'], [1, '#1E150C']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [S.end('dia13'), 1.1]]), shake: 1.5 }, t);
      // feixe diagonal de luz solar atravessando o ar empoeirado
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      const sun = ctx.createLinearGradient(120, 120, 920, 1480);
      sun.addColorStop(0, 'rgba(255,230,155,0.45)'); sun.addColorStop(0.6, 'rgba(255,205,110,0.22)'); sun.addColorStop(1, 'rgba(255,190,90,0)');
      ctx.fillStyle = sun;
      ctx.beginPath(); ctx.moveTo(-100, 120); ctx.lineTo(620, 0); ctx.lineTo(1200, 1650); ctx.lineTo(260, 1850); ctx.closePath(); ctx.fill();
      ctx.restore();
      // particulas distantes e fibras microscopicas flutuando
      for (let i = 0; i < 24; i++) {
        const px = hash(i + 1300) * W + Math.sin(t * 0.9 + i) * 35;
        const py = 320 + hash(i + 1301) * 980 + Math.cos(t * 0.7 + i) * 28;
        const r = 10 + hash(i + 1302) * 26;
        ctx.fillStyle = 'rgba(255,232,175,0.28)';
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
      }
      // GRAO DE POEIRA GIGANTE flutuando ao lado do Beto (mesmo tamanho!)
      const dx = 675 + Math.sin(lt * 1.4) * 22, dy = 890 + Math.cos(lt * 1.1) * 24;
      ctx.save(); ctx.translate(dx, dy); ctx.rotate(lt * 0.18);
      ctx.beginPath();
      ctx.moveTo(-115, -45); ctx.lineTo(-42, -125); ctx.lineTo(76, -98); ctx.lineTo(128, -12);
      ctx.lineTo(92, 102); ctx.lineTo(-24, 124); ctx.lineTo(-118, 68); ctx.closePath();
      const dg = ctx.createRadialGradient(-30, -35, 18, 0, 0, 145);
      dg.addColorStop(0, '#FFF1CC'); dg.addColorStop(0.55, '#CFA974'); dg.addColorStop(1, '#7A5B36');
      outlined(ctx, dg, 8);
      ctx.fillStyle = 'rgba(90,62,32,0.4)';
      for (const [cx, cy, cr] of [[-28, -20, 22], [46, 28, 18], [-18, 56, 14]]) {
        ctx.beginPath(); ctx.arc(cx, cy, cr, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
      pill(ctx, dx, dy - 165, 240, 58, '#FFD400', null, 'POEIRA: 200 µm', INK, 32);
      // Beto flutuando sem gravidade ao lado da poeira
      drawBeto(ctx, st, {
        x: 340 + Math.cos(lt * 1.2) * 18, y: 940 + Math.sin(lt * 1.6) * 24,
        scale: 0.88, t, rot: Math.sin(lt * 1.1) * 0.16,
        rim: { color: '#FFE7A3', dir: [-0.7, -0.7] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. DIA 16
  SC.dia16 = {
    times(S) { return { tBac: S.c('dia16', 'bactéria'), tMon: S.w('dia16', 'monstro').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia16'), pose: 'space_float_panic', expr: 'curious', dur: 0.01 },
        { t: T.tBac, expr: 'shock' },
        { t: T.tMon, pose: 'dodge_lean', expr: 'panic', dur: 0.2, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tBac, T.tMon]; },
    hud(S, t) {
      const s0 = S.start('dia16');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia16', 'micrômetros').t1, 200e-6, 25e-6);
      return { bar: { day: 16, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia16'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tMon, a: 22, d: 0.5 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#041A19'], [0.5, '#0B3E3B'], [1, '#062422']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tMon, 1.12, eBack]]), shake }, t);
      // micro-bolhas bioluminescentes ao fundo
      for (let i = 0; i < 34; i++) {
        const bx = hash(i + 1600) * W + Math.sin(t + i) * 20;
        const by = 280 + ((hash(i + 1601) * 1100 - t * 25) % 1100 + 1100) % 1100;
        ctx.fillStyle = 'rgba(110,255,195,0.16)'; ctx.beginPath(); ctx.arc(bx, by, 10 + hash(i) * 32, 0, Math.PI * 2); ctx.fill();
      }
      // BACTERIA MONSTRO GIGANTE a direita (capsula verde brilhante com flagelos chicoteando!)
      const mx = 610 + Math.sin(t * 2.2) * 16, my = 890 + Math.cos(t * 1.8) * 16;
      ctx.save(); ctx.translate(mx, my); ctx.rotate(-0.18);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 0, 0, 340, 'rgba(65,245,145,A)', 0.36);
      ctx.restore();
      // flagelos ondulando atras
      for (let f = -1; f <= 1; f++) {
        ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(155, f * 48);
        ctx.bezierCurveTo(215, f * 74 + Math.sin(t * 11 + f) * 48, 270, f * 28 - Math.sin(t * 11 + f) * 48, 325, f * 56);
        ctx.stroke();
        ctx.strokeStyle = '#6BFF9E'; ctx.lineWidth = 8; ctx.stroke();
      }
      // cilios ao redor da membrana
      ctx.strokeStyle = '#7CFFA8'; ctx.lineWidth = 5;
      for (let c = 0; c < 18; c++) {
        const a = c / 18 * Math.PI * 2;
        const x1 = Math.cos(a) * 185, y1 = Math.sin(a) * 118;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 * 1.18 + Math.sin(t * 8 + c) * 6, y1 * 1.24); ctx.stroke();
      }
      // capsula da bacteria (silhueta limpa)
      rr(ctx, -185, -118, 370, 236, 116);
      const bg = ctx.createRadialGradient(-45, -35, 25, 0, 0, 220);
      bg.addColorStop(0, '#8AFFA8'); bg.addColorStop(0.55, '#24B55E'); bg.addColorStop(1, '#0D5C31');
      outlined(ctx, bg, 9);
      // nucleoide interno espiralado + ribossomos
      ctx.strokeStyle = 'rgba(180,255,205,0.65)'; ctx.lineWidth = 10; ctx.lineCap = 'round';
      ctx.beginPath();
      for (let s = -110; s <= 110; s += 10) {
        const yy = Math.sin(s * 0.08 + t * 3) * 42;
        s === -110 ? ctx.moveTo(s, yy) : ctx.lineTo(s, yy);
      }
      ctx.stroke();
      ctx.fillStyle = 'rgba(220,255,230,0.75)';
      for (let r = 0; r < 9; r++) { ctx.beginPath(); ctx.arc(-110 + hash(r + 1610) * 220, -60 + hash(r + 1611) * 120, 7, 0, Math.PI * 2); ctx.fill(); }
      ctx.restore();
      // Beto flutuando recuado a esquerda em susto
      drawBeto(ctx, st, {
        x: 270, y: 955 + Math.sin(lt * 2.8) * 14, scale: 0.82, t,
        rot: -0.1, rim: { color: '#7CFFA8', dir: [1, -0.2] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. DIA 20
  SC.dia20 = {
    times(S) { return { tVir: S.c('dia20', 'vírus'), tAli: S.w('dia20', 'alienígenas').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia20'), pose: 'space_float_panic', expr: 'amazed', dur: 0.01 },
        { t: T.tVir, expr: 'shock' },
        { t: T.tAli, pose: 'shock_closeup', expr: 'panic', dur: 0.25 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tVir, T.tAli]; },
    hud(S, t) {
      const s0 = S.start('dia20');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia20', 'micrômetro').t1, 25e-6, 1e-6);
      return { bar: { day: 20, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia20'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tAli, a: 18, d: 0.4 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#07051A'], [0.5, '#1B124C'], [1, '#2D1A6B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tAli, 1.1]]), shake }, t);
      // particulas neon espaciais
      for (let i = 0; i < 65; i++) {
        const px = hash(i + 2000) * W, py = 260 + hash(i + 2001) * 1140;
        ctx.fillStyle = i % 2 ? 'rgba(130,240,255,0.55)' : 'rgba(200,130,255,0.55)';
        ctx.beginPath(); ctx.arc(px, py, 2 + hash(i) * 4, 0, Math.PI * 2); ctx.fill();
      }
      // frota de 3 virus bacteriofagos descendo como naves alienigenas!
      const dropIn = eOut(clamp(lt / 1.1, 0, 1));
      drawPhageShip(ctx, 215, lerp(340, 610, dropIn), 0.78, t, 1.1);
      drawPhageShip(ctx, 760, lerp(320, 665, dropIn), 0.96, t, 3.7);
      drawPhageShip(ctx, 520, lerp(280, 505, dropIn), 0.62, t, 5.4);
      // Beto flutuando cercado pelas naves-virus
      drawBeto(ctx, st, {
        x: 475, y: 1020 + Math.sin(lt * 2.5) * 16, scale: 0.86, t,
        rot: Math.sin(lt * 1.4) * 0.08,
        rim: { color: '#7FF0FF', dir: [0.3, -1] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 12. DIA 26
  SC.dia26 = {
    times(S) { return { tDna: S.c('dia26', 'DNA'), tArr: S.w('dia26', 'arranha-céu').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia26'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tDna, expr: 'amazed' },
        { t: T.tArr, pose: 'shock_closeup', expr: 'shock', dur: 0.25 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tDna, T.tArr]; },
    hud(S, t) {
      const s0 = S.start('dia26');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia26', 'nanômetros').t1, 1e-6, 25e-9);
      return { bar: { day: 26, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia26'), lt = t - s0;
      fillScreen(ctx, vGrad(ctx, [[0, '#02081B'], [0.5, '#091E4D'], [1, '#0F3272']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia26'), 1.1]]), shake: 1.5 }, t);
      // brilho molecular por tras da torre de DNA
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 645, 860, 520, 'rgba(85,220,255,A)', 0.3);
      ctx.restore();
      // TORRE GIGANTE DE HELICE DUPLA DE DNA girando em 3D (enquadrada limpa entre HUD e legenda!)
      const hx = 645, amp = 148;
      // degraus de pares de bases (conectando as duas fitas)
      for (let i = 0; i < 17; i++) {
        const y = 380 + i * 56;
        const ph = i * 0.52 + t * 2.1;
        const x1 = hx + Math.sin(ph) * amp;
        const x2 = hx - Math.sin(ph) * amp;
        const depth = Math.cos(ph);
        ctx.strokeStyle = i % 2 ? '#5CEEFF' : '#FFD400';
        ctx.lineWidth = 10 + depth * 2; ctx.lineCap = 'round';
        ctx.globalAlpha = 0.55 + 0.45 * Math.abs(Math.sin(ph));
        ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      // as duas fitas principais (ciano e dourada) com contorno preto grosso
      for (const [offset, col] of [[0, '#5CEEFF'], [Math.PI, '#FFD400']]) {
        ctx.beginPath();
        for (let y = 365; y <= 1305; y += 16) {
          const ph = (y - 380) / 56 * 0.52 + t * 2.1 + offset;
          const x = hx + Math.sin(ph) * amp;
          y === 365 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.strokeStyle = INK; ctx.lineWidth = 32; ctx.stroke();
        ctx.strokeStyle = col; ctx.lineWidth = 18; ctx.stroke();
      }
      pill(ctx, 275, 435, 250, 66, 'rgba(8,20,48,0.92)', '#5CEEFF', 'HÉLICE DNA', '#5CEEFF', 36);
      // Beto minusculo flutuando a esquerda admirando o arranha-ceu de DNA!
      drawBeto(ctx, st, {
        x: 270, y: 980 + Math.sin(lt * 2.1) * 16, scale: 0.72, t,
        rot: -0.06, rim: { color: '#7FF0FF', dir: [1, -0.3] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 13. DIA 34
  SC.dia34 = {
    times(S) { return { tEnc: S.c('dia34', 'encolheu'), tAto: S.w('dia34', 'átomo').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia34'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tEnc, pose: 'space_float_panic', expr: 'shock', dur: 0.25 },
        { t: T.tAto, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tEnc, T.tAto]; },
    hud(S, t) {
      const s0 = S.start('dia34');
      const m = HUD.roll(t, s0 + 0.08, S.w('dia34', 'nanômetro').t1, 25e-9, 1e-10);
      return { bar: { day: 34, dayT: s0, label: 'ALTURA', value: fmtSize(m) }, customHud: sizeGauge(m, { quantum: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia34'), lt = t - s0;
      fillScreen(ctx, vGrad(ctx, [[0, '#02020A'], [0.55, '#0A0826'], [1, '#040618']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia34'), 1.12]]), shake: 1.5 }, t);
      const ax = 610, ay = 860;
      // 3 orbitais de eletrons luminosos girando ao redor do nucleo
      const orbs = [[-0.55, '#5CEEFF', 4.2], [0.55, '#B37BFF', 3.5], [1.55, '#FFD400', 4.9]];
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, ax, ay, 360, 'rgba(130,180,255,A)', 0.34);
      orbs.forEach(([rot, col, spd], idx) => {
        ctx.save(); ctx.translate(ax, ay); ctx.rotate(rot);
        ctx.strokeStyle = col; ctx.globalAlpha = 0.62; ctx.lineWidth = 6;
        ctx.beginPath(); ctx.ellipse(0, 0, 265, 92, 0, 0, Math.PI * 2); ctx.stroke();
        const ea = t * spd + idx * 2.1;
        const ex = Math.cos(ea) * 265, ey = Math.sin(ea) * 92;
        ctx.globalAlpha = 1;
        glow(ctx, ex, ey, 44, 'rgba(255,255,255,A)', 0.9);
        ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(ex, ey, 11, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      });
      ctx.restore();
      // nucleo atomico compacto (protons e neutrons)
      const nuc = [[-16, -12, '#FF4757'], [16, -10, '#6EC1FF'], [0, 14, '#FF4757'], [-12, 12, '#6EC1FF'], [14, 14, '#FF4757'], [0, -18, '#6EC1FF']];
      for (const [nx, ny, nc] of nuc) {
        ctx.beginPath(); ctx.arc(ax + nx, ay + ny, 20, 0, Math.PI * 2); outlined(ctx, nc, 5);
      }
      pill(ctx, 250, 440, 248, 66, 'rgba(8,12,38,0.92)', '#A87BFF', '1 ÁTOMO (0,1 nm)', '#D2B3FF', 32);
      // Beto flutuando ao lado do atomo
      drawBeto(ctx, st, {
        x: 255, y: 975 + Math.sin(lt * 2.2) * 16, scale: 0.78, t,
        rot: Math.sin(lt * 1.2) * 0.1,
        rim: { color: '#A87BFF', dir: [1, -0.3] }
      });
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 14. TWIST A
  SC.twist_a = {
    keys(S) {
      return [
        { t: S.start('twist_a'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('twist_a', 'detalhe'), expr: 'shock' },
        { t: S.c('twist_a', 'contou'), pose: 'freezing_hug', expr: 'panic', dur: 0.28 }
      ];
    },
    ev(S) { return [S.c('twist_a', 'detalhe'), S.c('twist_a', 'contou'), S.seg('twist_a').t1]; },
    hud() {
      return {
        bar: { day: 34, dayT: -9, label: 'ALTURA', value: '0,1 nm' },
        customHud: sizeGauge(1e-10, { quantum: true }),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), tDet = S.c('twist_a', 'detalhe'), tEnd = S.seg('twist_a').t1;
      const z = kf(t, [[s0, 1.12], [tDet, 1.38], [tEnd, 1.24]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#040610'], [0.55, '#0F152D'], [1, '#050712']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 920, z, shake: 2 }, t);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 540, 780, 480, 'rgba(130,150,255,A)', 0.24);
      ctx.restore();
      drawBeto(ctx, st, { x: 540, y: 960, scale: 1.06, t, rim: { color: '#9BB8FF', dir: [0, -1] } });
      ctx.restore();
      const hold = clamp((t - tDet) / 0.8, 0, 1);
      ctx.save(); ctx.globalAlpha = 0.55 * hold;
      const vg = ctx.createRadialGradient(540, 960, 240, 540, 960, 1180);
      vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,1)');
      ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H); ctx.restore();
    }
  };

  // -------------------------------------------------------------- 15. TWIST B
  SC.twist_b = {
    times(S) { return { tAr: S.c('twist_b', 'ar'), tVaz: S.c('twist_b', 'vazio'), tQua: S.w('twist_b', 'quântico').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('twist_b'), pose: 'freezing_hug', expr: 'panic', dur: 0.01 },
        { t: T.tVaz, pose: 'freefall_scream', expr: 'scream', dur: 0.14 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tAr, T.tVaz, T.tQua]; },
    hud(S, t) {
      const T = this.times(S), voidNow = t >= T.tVaz;
      return {
        bar: { day: 34, dayT: -9, label: voidNow ? 'DESTINO' : 'OXIGÊNIO', value: voidNow ? 'VAZIO QUÂNTICO' : '0%', alert: true },
        customHud: sizeGauge(1e-10, { alert: true }),
        alert: { text: voidNow ? 'VAZIO QUÂNTICO' : 'SEM OXIGÊNIO', t0: voidNow ? T.tVaz : S.start('twist_b') }
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('twist_b');
      if (t < T.tVaz) {
        // Beat 1: moleculas GIGANTES de O2/N2 maiores que o Beto batendo fora do nariz dele!
        const lt = t - s0;
        const shake = hits(t, [{ t: s0, a: 24, d: 0.4 }]) + 4;
        fillScreen(ctx, vGrad(ctx, [[0, '#070E24'], [0.55, '#132752'], [1, '#08122A']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: lerp(1.04, 1.16, clamp(lt / 2.2, 0, 1)), shake }, t);
        // 3 moleculas duplas gigantes de O2 / N2 flutuando e quicando
        const mols = [
          [235, 680, '#4FAFFF', 'O2', 0.3],
          [755, 760, '#FF5C6C', 'O2', -0.4],
          [720, 1110, '#6B8EFF', 'N2', 0.25]
        ];
        mols.forEach(([mx, my, col, tag, rot], idx) => {
          ctx.save(); ctx.translate(mx + Math.sin(t * 3 + idx) * 26, my + Math.cos(t * 2.5 + idx) * 22); ctx.rotate(rot + Math.sin(t * 1.6 + idx) * 0.15);
          // contorno externo unificado (duas esferas coladas sem risco interno feio)
          ctx.fillStyle = INK;
          ctx.beginPath(); ctx.arc(-44, 0, 74, 0, Math.PI * 2); ctx.arc(44, 0, 74, 0, Math.PI * 2); ctx.fill();
          for (const ox of [-44, 44]) {
            const g = ctx.createRadialGradient(ox - 18, -22, 10, ox, 0, 68);
            g.addColorStop(0, '#FFFFFF'); g.addColorStop(0.35, col); g.addColorStop(1, '#1A2444');
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(ox, 0, 66, 0, Math.PI * 2); ctx.fill();
          }
          label(ctx, tag, 0, 4, 44, '#FFFFFF');
          ctx.restore();
        });
        // Beto sem ar no meio das moleculas gigantes
        drawBeto(ctx, st, {
          x: 475, y: 960 + Math.sin(t * 6) * 8, scale: 0.9, t,
          rim: { color: '#7FF0FF', dir: [0.5, -0.8] }
        });
        ctx.restore();
        return;
      }
      // Beat 2: QUEDA NO VAZIO QUANTICO (vortice roxo/ciano engolindo o Beto girando!)
      const age = t - T.tVaz;
      const fall = clamp(age / Math.max(0.6, S.end('twist_b') - T.tVaz), 0, 1);
      const shake = hits(t, [{ t: T.tVaz, a: 36, d: 0.6 }, { t: T.tQua, a: 28, d: 0.5 }]) + 7;
      fillScreen(ctx, vGrad(ctx, [[0, '#020108'], [0.5, '#130730'], [1, '#03081C']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: lerp(1.05, 1.25, fall), shake }, t);
      // vortice quantico concentrico pulsante
      const vcx = 520, vcy = 900;
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, vcx, vcy, 540, 'rgba(150,70,255,A)', 0.45);
      for (let r = 0; r < 11; r++) {
        const ph = (r / 11 + t * 0.9) % 1;
        const rad = 45 + Math.pow(ph, 1.7) * 760;
        ctx.globalAlpha = (1 - ph) * 0.85;
        ctx.strokeStyle = r % 2 ? '#A86BFF' : '#5CEEFF';
        ctx.lineWidth = 4 + (1 - ph) * 10;
        ctx.beginPath(); ctx.arc(vcx, vcy, rad, 0, Math.PI * 2); ctx.stroke();
      }
      // espuma quantica piscando
      for (let i = 0; i < 60; i++) {
        const a = hash(i + 3000) * Math.PI * 2 + t * (1.2 + hash(i) * 1.5);
        const rad = 80 + ((hash(i + 3001) * 650 - t * 240) % 650 + 650) % 650;
        ctx.globalAlpha = 0.65;
        ctx.fillStyle = i % 3 === 0 ? '#FFFFFF' : (i % 3 === 1 ? '#5CEEFF' : '#C885FF');
        ctx.beginPath(); ctx.arc(vcx + Math.cos(a) * rad, vcy + Math.sin(a) * rad, 3 + hash(i) * 6, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
      // nucleo negro do vazio no centro
      ctx.fillStyle = '#010105'; ctx.beginPath(); ctx.arc(vcx, vcy, 110, 0, Math.PI * 2); ctx.fill();
      // Beto girando e encolhendo para dentro do vazio quantico!
      const bScale = lerp(0.95, 0.24, eIn(fall));
      drawBeto(ctx, st, {
        x: vcx, y: vcy, scale: bScale, t, rot: age * 4.8,
        rim: { color: '#C885FF', dir: [0, -1] }, wind: [0, -80]
      });
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 16. LOOP
  SC.loop = {
    keys(S) {
      return [
        { t: S.start('loop'), pose: 'shrug_question', expr: 'curious', dur: 0.18, ease: 'back' },
        { t: S.c('loop', 'você'), pose: 'point_hook', expr: 'focus', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'encolhendo'), expr: 'smug' },
        { t: S.end('loop') - 0.32, pose: 'shock_closeup', expr: 'shock', dur: 0.2 }
      ];
    },
    ev(S) { return [S.c('loop', 'dia'), S.c('loop', 'você'), S.c('loop', 'encolhendo'), S.end('loop') - 0.5]; },
    hud(S) {
      const s0 = S.start('loop');
      return { bar: { day: '?', dayT: s0, label: 'SUA RESPOSTA', value: 'COMENTE' }, ruler: null, alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop'), tV = S.c('loop', 'você');
      const z = kf(t, [[s0, 1.6], [s0 + 0.2, 1.9, eBack], [tV, 1.9], [tV + 0.2, 2.25, eBack], [s1 - 0.55, 2.45], [s1, 3.6, eIn]]);
      const shake = hits(t, [{ t: s0, a: 28, d: 0.5 }, { t: tV, a: 14, d: 0.3 }]) + 3;
      radialBurst(ctx, t, 540, 760, '#B0141F', '#6E0B12', 22, 0.36);
      speedRadial(ctx, t, 540, 760, 50, '#FFE9D6', 0.42, 380, 11);
      const bx = 540, by = 1180;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);
      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 155 / z, z, shake }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1, t, rim: { color: '#FFB25C', dir: [0.8, -0.6] } });
      ctx.restore();
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
