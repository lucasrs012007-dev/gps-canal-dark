/*
 * ep01_velocidade/scenes.js : Episodio 1 ("E se sua velocidade dobrasse todo dia?")
 * 16 cenarios originais animados quadro a quadro em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
 * Contrato: funcao pura do tempo t. Zero estado mutavel entre quadros, zero Math.random.
 */
(function (root) {
  'use strict';
  const W = 1080, H = 1920, F = 1 / 30;
  const B = root.Beto, HUD = root.HUD;
  const INK = B.INK, PAL = B.PAL;

  // ----------------------------------------------------------------- matematica
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  const eIO = k => k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  const eOut = k => 1 - Math.pow(1 - k, 3);
  const eIn = k => k * k * k;
  const eBack = k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
  const lin = k => k;
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

  // -------------------------------------------------------- poses de corrida
  const RUN_A = Object.assign({}, B.POSES.idle, {
    lean: 16, ua_r: 68, la_r: 112, ua_l: -42, la_l: 16,
    th_r: 58, sh_r: -6, th_l: -34, sh_l: 42, hand_r: 1, hand_l: 1, head: -5
  });
  const RUN_B = Object.assign({}, B.POSES.idle, {
    lean: 16, ua_r: -42, la_r: 16, ua_l: 68, la_l: 112,
    th_r: -34, sh_r: 42, th_l: 58, sh_l: -6, hand_r: 1, hand_l: 1, head: -5
  });
  const TURBO_A = Object.assign({}, B.POSES.idle, {
    lean: 30, ua_r: 86, la_r: 118, ua_l: -58, la_l: -12,
    th_r: 72, sh_r: -18, th_l: -48, sh_l: 56, hand_r: 1, hand_l: 1, head: -12
  });
  const TURBO_B = Object.assign({}, B.POSES.idle, {
    lean: 30, ua_r: -58, la_r: -12, ua_l: 86, la_l: 118,
    th_r: -48, sh_r: 56, th_l: 72, sh_l: -18, hand_r: 1, hand_l: 1, head: -12
  });
  function runPose(t, freq, turbo) {
    const k = 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * freq);
    return B.mixObj(turbo ? TURBO_A : RUN_A, turbo ? TURBO_B : RUN_B, k);
  }
  function waveRunPose(t, freq) {
    const p = runPose(t, freq, false);
    const wave = Math.sin(t * 26) * 16;
    return Object.assign({}, p, { ua_r: 116, la_r: 144 + wave, hand_r: 0, head: 6 });
  }

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
  /** Rajadas horizontais para corrida em alta velocidade (dir=-1 vai da direita p/ esquerda). */
  function speedHoriz(ctx, t, speed, n, color, alpha, seed, yMin, yMax) {
    ctx.save(); ctx.strokeStyle = color; ctx.lineCap = 'round';
    const ya = yMin === undefined ? 120 : yMin, yb = yMax === undefined ? 1760 : yMax;
    for (let i = 0; i < n; i++) {
      const y = ya + hash(i * 2.1 + seed) * (yb - ya);
      const len = 140 + hash(i * 4.3 + seed) * 440;
      const sp = speed * (0.65 + hash(i * 6.7 + seed) * 0.85);
      const span = W + len + 400;
      const x = W + 200 - ((hash(i * 9.3 + seed) * span + t * sp) % span);
      ctx.globalAlpha = alpha * (0.35 + hash(i * 3.7 + seed) * 0.65);
      ctx.lineWidth = 2.5 + hash(i * 5.1 + seed) * 6.5;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + len, y); ctx.stroke();
    }
    ctx.restore();
  }
  function cloud(ctx, x, y, s, top, bottom, alpha) {
    const puffs = [[-1.15, 0.12, 0.5], [-0.6, -0.22, 0.72], [0.05, -0.4, 0.92], [0.7, -0.15, 0.7], [1.2, 0.14, 0.48]];
    ctx.save(); ctx.globalAlpha = alpha === undefined ? 1 : alpha;
    ctx.beginPath();
    for (const p of puffs) {
      ctx.moveTo(x + (p[0] + p[2]) * s, y + p[1] * s);
      ctx.arc(x + p[0] * s, y + p[1] * s, p[2] * s, 0, Math.PI * 2);
    }
    ctx.rect(x - 1.5 * s, y, 3 * s, 0.42 * s);
    const g = ctx.createLinearGradient(0, y - 1.3 * s, 0, y + 0.45 * s);
    g.addColorStop(0, top); g.addColorStop(1, bottom);
    ctx.fillStyle = g; ctx.fill();
    ctx.restore();
  }
  function stars(ctx, t, n, seed, alpha, scrollX) {
    ctx.save();
    for (let i = 0; i < n; i++) {
      const span = W + 240;
      const x = ((hash(i * 1.3 + seed) * span - (scrollX || 0) * (0.3 + hash(i) * 0.7)) % span + span) % span - 120;
      const y = hash(i * 2.7 + seed) * H;
      const r = 0.9 + hash(i * 3.9 + seed) * 2.6;
      ctx.globalAlpha = alpha * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * (1 + hash(i) * 3) + i)));
      ctx.fillStyle = hash(i * 8.1) > 0.84 ? '#FFE7B8' : '#FFFFFF';
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  function dustPuffs(ctx, t, x0, y0, n, speed, color, alpha, seed) {
    ctx.save();
    for (let i = 0; i < n; i++) {
      const ph = (t * (2.2 + hash(i + seed) * 1.6) + hash(i * 3.7 + seed)) % 1;
      const x = x0 - ph * speed;
      const y = y0 - ph * (40 + hash(i * 5.3 + seed) * 90) + Math.sin(ph * 6 + i) * 10;
      const r = (12 + hash(i * 7.1 + seed) * 26) * (0.4 + ph * 1.1);
      ctx.globalAlpha = alpha * (1 - ph) * Math.min(1, ph * 5);
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  // ------------------------------------------------ velocimetro logaritmico HUD
  const SPEED_MARKS = [
    { v: 10, txt: '10' },
    { v: 100, txt: '100' },
    { v: 1235, txt: 'SOM' },
    { v: 10000, txt: '10k' },
    { v: 1000000, txt: '1M' },
    { v: 1079252848, txt: 'LUZ' }
  ];
  function fmtSpeed(kmh) {
    if (kmh >= 1000000000) return '300 mil km/s';
    if (kmh >= 1000000) return HUD.fmtNum(kmh / 1000000, 1) + ' M km/h';
    if (kmh >= 10000) return HUD.fmtNum(Math.round(kmh / 1000), 0) + ' mil km/h';
    return HUD.fmtNum(Math.round(kmh), 0) + ' km/h';
  }
  /** Barra vertical logaritmica de velocidade na borda direita (mesma faixa segura da regua). */
  function speedGauge(kmh, opts) {
    opts = opts || {};
    return function drawSpeedGauge(ctx) {
      const x = 1012, y0 = 1080, y1 = 360;
      const lmin = Math.log10(5), lmax = Math.log10(1.5e9);
      const yOf = v => y0 - (Math.log10(clamp(v, 5, 1.5e9)) - lmin) / (lmax - lmin) * (y0 - y1);
      ctx.save();
      rr(ctx, x - 14, y1 - 26, 28, y0 - y1 + 52, 14);
      ctx.fillStyle = 'rgba(11,15,25,0.68)'; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.78)'; ctx.stroke();
      const ym = yOf(kmh);
      rr(ctx, x - 7, ym, 14, Math.max(0, y0 + 12 - ym), 7);
      ctx.fillStyle = opts.light ? '#7FF0FF' : (opts.alert ? HUD.COLORS.alert : HUD.COLORS.accent);
      ctx.fill();
      ctx.font = `28px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const mk of SPEED_MARKS) {
        const yy = yOf(mk.v);
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
        ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
        ctx.strokeText(mk.txt, x - 32, yy + 1);
        ctx.fillStyle = mk.v >= 1e9 ? '#7FF0FF' : 'rgba(255,255,255,0.94)';
        ctx.fillText(mk.txt, x - 32, yy + 1);
      }
      // ponteiro losango assinatura Opus
      ctx.save(); ctx.translate(x, ym);
      ctx.beginPath(); ctx.moveTo(0, -19); ctx.lineTo(19, 0); ctx.lineTo(0, 19); ctx.lineTo(-19, 0); ctx.closePath();
      ctx.fillStyle = opts.light ? '#7FF0FF' : '#E8322A'; ctx.fill();
      ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
      ctx.restore();
      ctx.restore();
    };
  }

  // ------------------------------------------------ props reutilizaveis EP01
  /** Carro de Formula 1 estilizado, nariz para +x. */
  function drawF1Car(ctx, x, y, s, t) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    // sombra
    contactShadow(ctx, 0, 56, 250, 0.45);
    // chamas do escapamento
    const fl = 0.75 + 0.35 * Math.sin(t * 60);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    ctx.beginPath(); ctx.moveTo(-220, 8); ctx.quadraticCurveTo(-275 * fl, -6, -320 * fl, 8);
    ctx.quadraticCurveTo(-275 * fl, 22, -220, 16); ctx.closePath();
    ctx.fillStyle = 'rgba(255,150,40,0.88)'; ctx.fill();
    ctx.restore();
    // asa traseira
    ctx.beginPath(); ctx.moveTo(-245, -72); ctx.lineTo(-195, -72); ctx.lineTo(-185, 8); ctx.lineTo(-228, 8); ctx.closePath();
    outlined(ctx, '#D91E26', 6);
    rr(ctx, -252, -82, 68, 22, 6); outlined(ctx, '#FFFFFF', 5);
    // chassi principal aerodinamico
    ctx.beginPath();
    ctx.moveTo(-215, 22); ctx.lineTo(-195, -24); ctx.lineTo(-80, -34);
    ctx.quadraticCurveTo(35, -34, 145, -4); ctx.lineTo(252, 16);
    ctx.quadraticCurveTo(260, 28, 240, 34); ctx.lineTo(-212, 34); ctx.closePath();
    const cg = ctx.createLinearGradient(0, -34, 0, 34);
    cg.addColorStop(0, '#FF3B30'); cg.addColorStop(0.55, '#D91E26'); cg.addColorStop(1, '#8C0E14');
    outlined(ctx, cg, 7);
    // faixa branca + numero 1
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath(); ctx.moveTo(-165, 2); ctx.lineTo(150, 10); ctx.lineTo(140, 22); ctx.lineTo(-170, 16); ctx.closePath(); ctx.fill();
    // cockpit + halo + capacete do piloto
    ctx.beginPath(); ctx.arc(-20, -28, 22, Math.PI, 0); outlined(ctx, '#FFD400', 5);
    ctx.fillStyle = '#141B2D'; ctx.fillRect(-10, -36, 20, 10); // viseira
    ctx.beginPath(); ctx.moveTo(-58, -28); ctx.quadraticCurveTo(-10, -64, 42, -22);
    ctx.strokeStyle = INK; ctx.lineWidth = 10; ctx.stroke();
    ctx.strokeStyle = '#252C3E'; ctx.lineWidth = 4; ctx.stroke();
    // asa dianteira
    ctx.beginPath(); ctx.moveTo(212, 18); ctx.lineTo(274, 24); ctx.lineTo(268, 40); ctx.lineTo(205, 36); ctx.closePath();
    outlined(ctx, '#FFFFFF', 5);
    // rodas slick girando
    for (const [wx, wy, wr] of [[-155, 24, 42], [162, 26, 38]]) {
      ctx.save(); ctx.translate(wx, wy);
      ctx.beginPath(); ctx.arc(0, 0, wr, 0, Math.PI * 2); outlined(ctx, '#1B202C', 7);
      ctx.beginPath(); ctx.arc(0, 0, wr * 0.56, 0, Math.PI * 2); outlined(ctx, '#CFD6E4', 4);
      ctx.strokeStyle = '#E8322A'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.arc(0, 0, wr * 0.78, t * 28, t * 28 + Math.PI * 1.4); ctx.stroke();
      ctx.rotate(t * 32);
      ctx.strokeStyle = INK; ctx.lineWidth = 4;
      for (let k = 0; k < 5; k++) {
        const a = k * Math.PI * 2 / 5;
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a) * wr * 0.5, Math.sin(a) * wr * 0.5); ctx.stroke();
      }
      ctx.restore();
    }
    ctx.restore();
  }

  /** Caca supersonico estilizado (nariz para +x) com pos-combustor. */
  function drawFighterJet(ctx, x, y, s, rot, t) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    // pos-combustor pulsante
    const flame = 1 + 0.25 * Math.sin(t * 70);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    glow(ctx, -235, 4, 110 * flame, 'rgba(90,190,255,A)', 0.75);
    ctx.beginPath();
    ctx.moveTo(-210, -14); ctx.quadraticCurveTo(-320 * flame, 4, -390 * flame, 4);
    ctx.quadraticCurveTo(-320 * flame, 4, -210, 22); ctx.closePath();
    ctx.fillStyle = '#5CEEFF'; ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-210, -8); ctx.lineTo(-300 * flame, 4); ctx.lineTo(-210, 16); ctx.closePath();
    ctx.fillStyle = '#FFFFFF'; ctx.fill();
    ctx.restore();
    // asa distante
    ctx.beginPath(); ctx.moveTo(10, -14); ctx.lineTo(-140, -110); ctx.lineTo(-188, -110); ctx.lineTo(-110, -14); ctx.closePath();
    outlined(ctx, '#8A98B0', 6);
    // leme vertical duplo
    ctx.beginPath(); ctx.moveTo(-115, -16); ctx.lineTo(-195, -112); ctx.lineTo(-225, -112); ctx.lineTo(-200, -16); ctx.closePath();
    outlined(ctx, '#6E7D96', 6);
    // fuselagem afilada
    ctx.beginPath();
    ctx.moveTo(-210, -18); ctx.lineTo(135, -24); ctx.lineTo(285, 4);
    ctx.lineTo(135, 28); ctx.lineTo(-210, 24); ctx.closePath();
    const jg = ctx.createLinearGradient(0, -26, 0, 28);
    jg.addColorStop(0, '#DCE4F0'); jg.addColorStop(0.55, '#A6B4C8'); jg.addColorStop(1, '#6C7A90');
    outlined(ctx, jg, 7);
    // listra tatica amarela
    ctx.fillStyle = '#FFD400'; ctx.fillRect(-155, -8, 18, 22);
    // canopi de vidro com piloto
    ctx.beginPath(); ctx.moveTo(30, -22); ctx.quadraticCurveTo(95, -62, 160, -14); ctx.closePath();
    outlined(ctx, '#264E8A', 6);
    ctx.beginPath(); ctx.moveTo(58, -28); ctx.quadraticCurveTo(95, -48, 134, -22);
    ctx.strokeStyle = 'rgba(200,245,255,0.8)'; ctx.lineWidth = 6; ctx.lineCap = 'round'; ctx.stroke();
    // asa proxima delta
    ctx.beginPath(); ctx.moveTo(42, 8); ctx.lineTo(-145, 112); ctx.lineTo(-195, 112); ctx.lineTo(-115, 12); ctx.closePath();
    outlined(ctx, '#B9C6D8', 6);
    // bocal turbina
    rr(ctx, -224, -18, 24, 42, 6); outlined(ctx, '#333C4F', 5);
    ctx.restore();
  }

  /** Ciclista sofrendo na subida (dia2). */
  function drawCyclist(ctx, x, y, s, t, shock) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const ped = t * 9;
    // rodas da bicicleta
    for (const wx of [-74, 76]) {
      ctx.save(); ctx.translate(wx, 0);
      ctx.beginPath(); ctx.arc(0, 0, 46, 0, Math.PI * 2);
      ctx.lineWidth = 10; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 5; ctx.strokeStyle = '#3A4256'; ctx.stroke();
      ctx.rotate(ped);
      ctx.strokeStyle = '#9BA6BC'; ctx.lineWidth = 2.5;
      for (let i = 0; i < 6; i++) {
        const a = i * Math.PI / 3;
        ctx.beginPath(); ctx.moveTo(-Math.cos(a) * 40, -Math.sin(a) * 40); ctx.lineTo(Math.cos(a) * 40, Math.sin(a) * 40); ctx.stroke();
      }
      ctx.restore();
    }
    // quadro da bike
    ctx.strokeStyle = INK; ctx.lineWidth = 14;
    ctx.beginPath(); ctx.moveTo(-74, 0); ctx.lineTo(-10, -4); ctx.lineTo(48, -56); ctx.lineTo(-34, -54); ctx.closePath();
    ctx.moveTo(76, 0); ctx.lineTo(44, -74); ctx.lineTo(64, -76);
    ctx.moveTo(-34, -54); ctx.lineTo(-42, -72);
    ctx.stroke();
    ctx.strokeStyle = '#2B7CD3'; ctx.lineWidth = 7; ctx.stroke();
    // perna pedalando
    const px = -10 + Math.cos(ped) * 20, py = -4 + Math.sin(ped) * 20;
    ctx.strokeStyle = INK; ctx.lineWidth = 24;
    ctx.beginPath(); ctx.moveTo(-36, -84); ctx.lineTo(4, -42); ctx.lineTo(px, py); ctx.stroke();
    ctx.strokeStyle = '#1E2A4A'; ctx.lineWidth = 13; ctx.stroke();
    // tronco inclinado + braco no guidao
    ctx.beginPath(); ctx.moveTo(-48, -76); ctx.lineTo(22, -132); ctx.lineTo(52, -110); ctx.lineTo(-18, -56); ctx.closePath();
    outlined(ctx, '#2D8C6F', 6);
    ctx.strokeStyle = INK; ctx.lineWidth = 22;
    ctx.beginPath(); ctx.moveTo(22, -118); ctx.lineTo(54, -78); ctx.stroke();
    ctx.strokeStyle = '#E9B288'; ctx.lineWidth = 12; ctx.stroke();
    // cabeca + capacete + suor
    ctx.beginPath(); ctx.arc(46, -154, 34, 0, Math.PI * 2); outlined(ctx, '#E9B288', 6);
    ctx.beginPath(); ctx.arc(46, -162, 37, Math.PI * 1.05, Math.PI * 1.98); ctx.closePath(); outlined(ctx, '#FFD400', 6);
    // olho arregalado no choque
    ctx.beginPath(); ctx.arc(62, -152, shock ? 10 : 7, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 3);
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(64, -152, 3.5, 0, Math.PI * 2); ctx.fill();
    // boca ofegante / choque
    ctx.beginPath(); ctx.ellipse(60, -132, 9, shock ? 11 : 6, 0, 0, Math.PI * 2); outlined(ctx, '#4A0F12', 3);
    // gotas de suor
    for (let i = 0; i < 3; i++) {
      const ph = (t * 2.5 + i * 0.33) % 1;
      ctx.fillStyle = '#7FD6FF'; ctx.globalAlpha = 1 - ph;
      ctx.beginPath(); ctx.arc(20 - ph * 35, -168 - ph * 18 + ph * ph * 45, 5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /** Corredor campeao olimpico (dia3: uniforme amarelo e verde, bib 9.58). */
  function drawChampionRunner(ctx, x, y, s, t, shocked) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const ph = Math.sin(t * 20);
    const skin = '#7A482B', jersey = '#FFD400', trim = '#1B8A4C';
    // pernas alternando forte
    for (const [side, dir] of [[-1, -ph], [1, ph]]) {
      const kx = dir * 34, ky = 46 - Math.abs(dir) * 14;
      const fx = dir * 56 - 14, fy = 98 - Math.max(0, dir) * 26;
      ctx.strokeStyle = INK; ctx.lineWidth = 30;
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(kx, ky); ctx.lineTo(fx, fy); ctx.stroke();
      ctx.strokeStyle = skin; ctx.lineWidth = 18; ctx.stroke();
      ctx.beginPath(); ctx.ellipse(fx + 10, fy + 8, 22, 11, 0, 0, Math.PI * 2); outlined(ctx, '#FFD400', 5);
    }
    // shorts verde
    rr(ctx, -28, -14, 56, 36, 12); outlined(ctx, trim, 6);
    // tronco inclinado + camiseta amarela
    ctx.save(); ctx.rotate(0.22);
    ctx.beginPath(); ctx.moveTo(-30, -96); ctx.lineTo(32, -96); ctx.lineTo(26, -6); ctx.lineTo(-24, -6); ctx.closePath();
    outlined(ctx, jersey, 6);
    ctx.fillStyle = trim; ctx.fillRect(-26, -42, 52, 16);
    rr(ctx, -22, -78, 44, 28, 4); outlined(ctx, '#FFFFFF', 3);
    label(ctx, '9.58', 0, -64, 19, INK);
    // bracos abertos fora do peito para nao cobrir o numero 9.58
    for (const [sd, dir] of [[-1, ph], [1, -ph]]) {
      ctx.strokeStyle = INK; ctx.lineWidth = 24;
      ctx.beginPath(); ctx.moveTo(sd * 28, -84); ctx.lineTo(sd * 48 + dir * 20, -48); ctx.lineTo(sd * 56 + dir * 32, -76); ctx.stroke();
      ctx.strokeStyle = skin; ctx.lineWidth = 14; ctx.stroke();
    }
    // cabeca
    ctx.beginPath(); ctx.arc(4, -142, 46, 0, Math.PI * 2); outlined(ctx, skin, 6);
    ctx.beginPath(); ctx.arc(4, -156, 44, Math.PI * 1.12, Math.PI * 1.92); ctx.fillStyle = '#181414'; ctx.fill();
    // olhos olhando para a direita (onde o Beto passa voando!)
    for (const ex of [-8, 20]) {
      ctx.beginPath(); ctx.ellipse(ex, -144, 11, shocked ? 15 : 10, 0, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 4);
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(ex + 4, -144, shocked ? 4 : 5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.beginPath(); ctx.ellipse(8, -118, 12, shocked ? 14 : 6, 0, 0, Math.PI * 2); outlined(ctx, '#4A0F12', 4);
    ctx.restore();
    ctx.restore();
  }

  /** Planeta Terra visto de orbita (dia12). */
  function drawOrbitEarth(ctx, cx, cy, R, t) {
    // atmosfera luminosa
    const atm = ctx.createRadialGradient(cx, cy, R * 0.96, cx, cy, R + 120);
    atm.addColorStop(0, 'rgba(130,220,255,0.95)');
    atm.addColorStop(0.28, 'rgba(55,145,255,0.48)');
    atm.addColorStop(1, 'rgba(20,60,180,0)');
    ctx.fillStyle = atm; ctx.beginPath(); ctx.arc(cx, cy, R + 120, 0, Math.PI * 2); ctx.fill();

    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    const og = ctx.createRadialGradient(cx - R * 0.35, cy - R * 0.35, R * 0.1, cx, cy, R * 1.1);
    og.addColorStop(0, '#3D98F0'); og.addColorStop(0.55, '#1754AD'); og.addColorStop(1, '#081D4B');
    ctx.fillStyle = og; ctx.fillRect(cx - R - 10, cy - R - 10, R * 2 + 20, R * 2 + 20);
    // continentes girando
    for (let i = 0; i < 10; i++) {
      const ang = ((hash(i + 200) * Math.PI * 2 + t * 0.55) % (Math.PI * 2));
      const lat = (hash(i + 210) - 0.5) * 1.3;
      const sx = cx + Math.sin(ang) * R * 0.78 * Math.cos(lat);
      const sy = cy + Math.sin(lat) * R * 0.72;
      if (Math.cos(ang) > -0.25) {
        ctx.fillStyle = i % 3 === 0 ? '#C7A96B' : '#3C9B58';
        ctx.beginPath();
        ctx.ellipse(sx, sy, (65 + hash(i + 220) * 90) * Math.max(0.25, Math.cos(ang)), 42 + hash(i + 230) * 55, hash(i) * 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    // faixas de nuvens
    ctx.globalAlpha = 0.58; ctx.fillStyle = '#FFFFFF';
    for (let i = 0; i < 12; i++) {
      const ang = ((hash(i + 300) * Math.PI * 2 + t * 0.75) % (Math.PI * 2));
      const sy = cy + (hash(i + 310) - 0.5) * R * 1.45;
      const sx = cx + Math.sin(ang) * R * 0.85;
      if (Math.cos(ang) > -0.1) {
        ctx.beginPath(); ctx.ellipse(sx, sy, 95 * Math.max(0.3, Math.cos(ang)), 16, 0.1, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
    // sombra do terminador
    const sh = ctx.createRadialGradient(cx - R * 0.4, cy - R * 0.35, R * 0.35, cx, cy, R * 1.05);
    sh.addColorStop(0, 'rgba(0,0,0,0)'); sh.addColorStop(0.75, 'rgba(0,8,30,0.22)'); sh.addColorStop(1, 'rgba(0,5,25,0.62)');
    ctx.fillStyle = sh; ctx.fillRect(cx - R - 10, cy - R - 10, R * 2 + 20, R * 2 + 20);
    ctx.restore();
    ctx.strokeStyle = 'rgba(180,240,255,0.92)'; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
  }

  // ==================================================================== CENAS
  const SC = {};

  // ------------------------------------------------------------------ 1. HOOK
  SC.hook = {
    times(S) {
      return {
        tV: S.c('hook', 'Você'),
        tM: S.w('hook', 'mesmo').t0,
        tPol: S.c('hook', 'A') - 0.04,
        tMis: S.w('hook', 'míssil').t0,
        tRad: S.c('hook', 'radar')
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: 0, pose: 'shock_closeup', expr: 'scream' },
        { t: T.tV, pose: 'point_hook', expr: 'focus', dur: 0.14, ease: 'back' },
        { t: T.tM, expr: 'scream' },
        { t: T.tPol, pose: 'super_launch', expr: 'shock', dur: 0.05 },
        { t: T.tMis, pose: 'dodge_lean', expr: 'panic', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tV, T.tPol, T.tMis, T.tRad]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const T = this.times(S);
      // luzes de sirene azul/vermelho alternando nas bordas
      const strobe = Math.sin(t * 18) > 0;
      if (t < T.tPol) {
        // Plano A: close dramatico carmim com sirene e Beto apontando (braco real preso)
        const z = kf(t, [[0, 3.6], [T.tV, 3.6], [T.tV + 0.2, 2.55, eBack], [T.tM + 0.15, 2.35]]);
        const shake = hits(t, [{ t: 0, a: 40, d: 0.65 }, { t: T.tM, a: 24, d: 0.35 }]) + 4;
        radialBurst(ctx, t, 540, 760, '#B0141F', '#6E0B12', 22, 0.38);
        speedRadial(ctx, t, 540, 760, 68, '#FFE9D6', 0.55, 380, 11);
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        glow(ctx, strobe ? 180 : 900, 220, 620, strobe ? 'rgba(40,120,255,A)' : 'rgba(255,40,60,A)', 0.42);
        ctx.restore();
        const bx = 540, by = 1180;
        const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);
        ctx.save();
        camApply(ctx, { x: bx, y: headY + (960 - 760) / z, z, shake }, t);
        drawBeto(ctx, st, { x: bx, y: by, scale: 1, t, rim: { color: strobe ? '#70B8FF' : '#FFB25C', dir: [0.8, -0.6] }, wind: [0, -10] });
        ctx.restore();
        return;
      }
      // Plano B: radar policial na rodovia noturna confundindo o Beto com um missil
      const lt = t - T.tPol;
      const z = kf(t, [[T.tPol, 1.18], [T.tMis, 1.04], [T.tMis + 0.18, 1.16, eBack], [S.end('hook'), 1.12]]);
      const shake = hits(t, [{ t: T.tPol, a: 28, d: 0.35 }, { t: T.tMis, a: 32, d: 0.5 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, '#040915'], [0.55, '#0B1A33'], [1, '#121824']]));
      // giroflex policial no topo
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 210, 260, 560, 'rgba(30,115,255,A)', strobe ? 0.65 : 0.12);
      glow(ctx, 870, 260, 560, 'rgba(255,35,55,A)', strobe ? 0.12 : 0.65);
      ctx.restore();
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      // horizonte da rodovia noturna atras do radar
      ctx.fillStyle = '#18202E'; ctx.fillRect(-200, 960, W + 400, 1000);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.setLineDash([56, 46]); ctx.lineDashOffset = t * 1400;
      ctx.beginPath(); ctx.moveTo(-200, 1180); ctx.lineTo(W + 200, 1180); ctx.stroke(); ctx.setLineDash([]);
      speedHoriz(ctx, t, 3600, 32, '#80D8FF', 0.45, 7, 940, 1300);
      // Beto rasgando a pista ao fundo com rastro luminoso (sempre visivel sob o radar)
      const spanB = Math.max(1.8, S.end('hook') - T.tPol);
      const runX = lerp(160, 860, clamp(lt / spanB, 0, 1));
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      const trail = ctx.createLinearGradient(runX - 620, 0, runX, 0);
      trail.addColorStop(0, 'rgba(255,140,40,0)'); trail.addColorStop(1, 'rgba(255,212,0,0.9)');
      ctx.fillStyle = trail; ctx.fillRect(runX - 620, 1025, 620, 96);
      ctx.restore();
      drawBeto(ctx, st, { x: runX, y: 1095, scale: 0.74, t, pose: runPose(t, 6.5, true), rim: { color: '#FFD400', dir: [1, -0.3] }, wind: [-95, 0] });

      // tela do radar tatico policial em primeiro plano (centro-alto seguro)
      const rx = 140, ry = 320, rw = 800, rh = 610;
      rr(ctx, rx, ry, rw, rh, 34); outlined(ctx, '#071B15', 10);
      ctx.save(); rr(ctx, rx + 12, ry + 12, rw - 24, rh - 24, 24); ctx.clip();
      ctx.fillStyle = '#051510'; ctx.fillRect(rx, ry, rw, rh);
      // grade verde CRT
      ctx.strokeStyle = 'rgba(50,255,155,0.16)'; ctx.lineWidth = 2;
      for (let gx = rx; gx < rx + rw; gx += 48) { ctx.beginPath(); ctx.moveTo(gx, ry); ctx.lineTo(gx, ry + rh); ctx.stroke(); }
      for (let gy = ry; gy < ry + rh; gy += 48) { ctx.beginPath(); ctx.moveTo(rx, gy); ctx.lineTo(rx + rw, gy); ctx.stroke(); }
      // circulos do radar + varredura giratoria
      const rcx = rx + rw / 2, rcy = ry + rh / 2 + 25;
      ctx.strokeStyle = 'rgba(65,255,165,0.45)'; ctx.lineWidth = 3;
      for (const rad of [90, 180, 270]) { ctx.beginPath(); ctx.arc(rcx, rcy, rad, 0, Math.PI * 2); ctx.stroke(); }
      ctx.beginPath(); ctx.moveTo(rcx - 290, rcy); ctx.lineTo(rcx + 290, rcy); ctx.moveTo(rcx, rcy - 250); ctx.lineTo(rcx, rcy + 250); ctx.stroke();
      const ang = t * 4.2;
      ctx.save(); ctx.translate(rcx, rcy); ctx.rotate(ang);
      const sw = ctx.createLinearGradient(0, 0, 260, -140);
      sw.addColorStop(0, 'rgba(65,255,165,0.45)'); sw.addColorStop(1, 'rgba(65,255,165,0)');
      ctx.fillStyle = sw; ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, 280, -0.55, 0); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = '#6BFFB8'; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(280, 0); ctx.stroke();
      ctx.restore();
      // alvo vermelho piscando (mira de missil!)
      const tx = rcx + lerp(-190, 190, clamp(lt / 2.2, 0, 1)), ty = rcy - 32;
      const locked = t >= T.tMis - 0.08;
      const pulse = 0.5 + 0.5 * Math.sin(t * 28);
      glow(ctx, tx, ty, 85, 'rgba(255,46,59,A)', 0.55 + 0.35 * pulse);
      ctx.strokeStyle = '#FF2E3B'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.arc(tx, ty, 36 + (locked ? 0 : 24 * (1 - clamp(lt, 0, 1))), 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#FF2E3B'; ctx.beginPath(); ctx.arc(tx, ty, 12, 0, Math.PI * 2); ctx.fill();
      // cabecalho da tela radar
      ctx.fillStyle = 'rgba(10,36,28,0.92)'; ctx.fillRect(rx, ry, rw, 92);
      ctx.strokeStyle = '#3CFF9E'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(rx, ry + 92); ctx.lineTo(rx + rw, ry + 92); ctx.stroke();
      label(ctx, 'RADAR POLICIAL | SETOR 04', rcx, ry + 48, 38, '#55FFA8');
      if (locked) {
        rr(ctx, rcx - 255, ry + rh - 104, 510, 76, 18);
        outlined(ctx, pulse > 0.45 ? '#E61E2A' : '#9E121B', 5);
        label(ctx, 'ALERTA: MÍSSIL DETECTADO!', rcx, ry + rh - 65, 42, '#FFFFFF');
      } else {
        label(ctx, 'RASTREANDO ALVO SUPERSÔNICO...', rcx, ry + rh - 60, 34, '#6BFFB8');
      }
      ctx.restore();
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 2. PREMISSA
  const SPEED_BARS = [10, 20, 40, 80, 160, 320];
  SC.premissa = {
    keys(S) {
      const s0 = S.start('premissa');
      return [
        { t: s0, pose: 'crouch_charge', expr: 'focus', dur: 0.01 },
        { t: S.c('premissa', 'velocidade'), pose: 'super_launch', expr: 'amazed', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'dobra'), pose: 'flex', expr: 'smug', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'todo'), pose: 'point_hook', expr: 'determined', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('premissa', 'velocidade'), S.c('premissa', 'dobra'), S.c('premissa', 'dia')]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), tD = S.w('premissa', 'dobra').t0;
      const shake = hits(t, [{ t: tD, a: 24, d: 0.45 }, { t: s0, a: 14, d: 0.3 }]);
      const z = kf(t, [[s0, 1.08], [tD, 1.0], [S.end('premissa'), 1.05]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#0C1838'], [1, '#13285A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      const off = (t * 36) % 54;
      ctx.lineWidth = 2;
      for (let x = -54 + off; x < W + 54; x += 54) {
        ctx.strokeStyle = (Math.round((x - off) / 54) % 5 === 0) ? 'rgba(120,200,255,0.28)' : 'rgba(120,200,255,0.12)';
        ctx.beginPath(); ctx.moveTo(x, -200); ctx.lineTo(x, H + 200); ctx.stroke();
      }
      for (let y = -54 + off; y < H + 54; y += 54) {
        ctx.strokeStyle = (Math.round((y - off) / 54) % 5 === 0) ? 'rgba(120,200,255,0.28)' : 'rgba(120,200,255,0.12)';
        ctx.beginPath(); ctx.moveTo(-200, y); ctx.lineTo(W + 200, y); ctx.stroke();
      }
      const ground = 1260;
      ctx.strokeStyle = '#7FD0FF'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(40, ground); ctx.lineTo(1040, ground); ctx.stroke();
      const maxH = 740, pts = [];
      SPEED_BARS.forEach((v, i) => {
        const x = 395 + i * 104, w = 72;
        const k = clamp((t - (tD - 0.30 + i * 0.11)) / 0.28, 0, 1);
        const h = (v / 320) * maxH * (k > 0 ? eBack(k) : 0);
        if (h > 1) {
          rr(ctx, x - w / 2, ground - h, w, h, 12);
          const g = ctx.createLinearGradient(0, ground - h, 0, ground);
          g.addColorStop(0, i === 5 ? '#FFE86B' : '#FFD400'); g.addColorStop(1, '#DF9B00');
          outlined(ctx, g, 6);
        }
        if (k > 0.6) label(ctx, String(v), x, ground - h - 34, 38, '#FFFFFF');
        label(ctx, 'D' + (i + 1), x, ground + 40, 34, '#9FD8FF');
        pts.push([x, ground - (v / 320) * maxH, k]);
      });
      ctx.save(); ctx.setLineDash([16, 14]); ctx.lineDashOffset = -t * 70;
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 5; ctx.beginPath();
      let started = false;
      for (const p of pts) { if (p[2] <= 0.6) break; started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; }
      ctx.stroke(); ctx.restore();
      // carimbo x2 POR DIA
      const ks = clamp((t - (tD - 0.05)) / 0.22, 0, 1);
      if (ks > 0) {
        ctx.save(); ctx.translate(310, 580); ctx.rotate(-0.11);
        const sc = 2.3 - 1.3 * eBack(ks); ctx.scale(sc, sc);
        ctx.globalAlpha = clamp(ks * 2, 0, 1);
        label(ctx, 'x2', 0, 0, 230, '#FFD400', 'center', HUD.FONT_CAPTION);
        label(ctx, 'POR DIA', 0, 136, 68, '#FFFFFF', 'center', HUD.FONT_CAPTION);
        ctx.restore();
      }
      // Beto a esquerda pronto para disparar
      const s = 1.02;
      contactShadow(ctx, 175, ground, 92, 0.36);
      drawBeto(ctx, st, { x: 175, y: pelvisFromFeet(ground, s), scale: s, t, rim: { color: '#7FD0FF', dir: [1, -0.3] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 3. DIA 1
  SC.dia1 = {
    keys(S) {
      return [
        { t: S.start('dia1'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: S.c('dia1', 'Trote'), expr: 'smug' },
        { t: S.c('dia1', 'calçada'), expr: 'amazed' }
      ];
    },
    ev(S) { return [S.c('dia1', '10 quilômetros'), S.c('dia1', 'Trote'), S.c('dia1', 'calçada')]; },
    hud(S, t) {
      const s0 = S.start('dia1');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia1', 'hora').t1, 1, 10, 'lin');
      return {
        bar: { day: 1, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) },
        customHud: speedGauge(v),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia1'), lt = t - s0;
      const z = kf(t, [[s0, 1.04], [S.end('dia1'), 1.1]]);
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#4FAFFF'], [0.55, '#BBE5FF'], [1, '#EAF7FF']]));
      glow(ctx, 840, 320, 380, 'rgba(255,244,190,A)', 0.55);
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      for (let i = 0; i < 4; i++) {
        const cx = ((hash(i + 10) * 1500 - lt * 35) % 1500 + 1500) % 1500 - 200;
        cloud(ctx, cx, 360 + hash(i + 11) * 200, 75 + hash(i + 12) * 35, '#FFFFFF', '#D7ECFF', 0.92);
      }
      // predios e lojinhas passando devagar (parallax)
      const cols = ['#F0C997', '#E6A88A', '#BDD4E7', '#E4D8B4'];
      for (let i = 0; i < 7; i++) {
        const span = 1820;
        const bx = ((i * 260 - lt * 160) % span + span) % span - 260;
        const bh = 420 + (i % 3) * 110;
        rr(ctx, bx, 1080 - bh, 236, bh, 12); outlined(ctx, cols[i % 4], 6);
        for (let wy = 0; wy < 3; wy++) for (let wx = 0; wx < 2; wx++) {
          rr(ctx, bx + 28 + wx * 102, 1080 - bh + 44 + wy * 92, 74, 62, 8);
          outlined(ctx, '#7CC4F5', 4);
        }
        // toldo da loja
        rr(ctx, bx + 12, 955, 212, 46, 10); outlined(ctx, i % 2 ? '#D94B3D' : '#2D8A70', 5);
      }
      // arvores e postes
      for (let i = 0; i < 5; i++) {
        const span = 1650;
        const tx = ((i * 330 - lt * 260) % span + span) % span - 180;
        ctx.fillStyle = '#6E4A2E'; ctx.fillRect(tx - 14, 920, 28, 175);
        ctx.beginPath(); ctx.arc(tx, 880, 78, 0, Math.PI * 2); outlined(ctx, '#4AA455', 6);
      }
      // calcada e asfalto
      ctx.fillStyle = '#D9D4C8'; ctx.fillRect(-200, 1080, W + 400, 190);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1080); ctx.lineTo(W + 200, 1080); ctx.stroke();
      ctx.fillStyle = '#B8B2A4'; ctx.fillRect(-200, 1250, W + 400, 32);
      ctx.fillStyle = '#363C4A'; ctx.fillRect(-200, 1280, W + 400, 700);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.setLineDash([70, 55]); ctx.lineDashOffset = lt * 340;
      ctx.beginPath(); ctx.moveTo(-200, 1410); ctx.lineTo(W + 200, 1410); ctx.stroke(); ctx.setLineDash([]);
      // Beto trotando tranquilo na calcada
      const feet = 1230, s = 1.18, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 2.2)) * 22;
      contactShadow(ctx, 470, feet, 98 * (1 - bounce / 160), 0.35);
      dustPuffs(ctx, t, 420, feet - 10, 6, 160, '#EFECE6', 0.45, 19);
      drawBeto(ctx, st, {
        x: 470, y: pelvisFromFeet(feet, s) - bounce, scale: s, t,
        pose: runPose(t, 2.2, false),
        rim: { color: '#FFF2BF', dir: [0.8, -0.6] }, wind: [-16, 0]
      });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 4. DIA 2
  SC.dia2 = {
    times(S) { return { tPas: S.w('dia2', 'passa').t0, tCic: S.c('dia2', 'ciclista') }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia2'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tPas, expr: 'smug' },
        { t: T.tCic, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPas, T.tCic, S.c('dia2', 'subida')]; },
    hud(S, t) {
      const s0 = S.start('dia2');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia2', 'hora').t1, 10, 20);
      return { bar: { day: 2, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia2'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }, { t: T.tPas, a: 12, d: 0.3 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#3C9EFF'], [0.55, '#9BD7FF'], [1, '#DEF3FF']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tPas + 0.3, 1.12]]), shake }, t);
      for (let i = 0; i < 4; i++) {
        const cx = ((hash(i + 20) * 1500 - lt * 60) % 1500 + 1500) % 1500 - 200;
        cloud(ctx, cx, 310 + hash(i + 21) * 180, 82, '#FFFFFF', '#D2E8FF', 0.9);
      }
      // cena inclinada para representar subida real
      ctx.save(); ctx.translate(540, 1120); ctx.rotate(-0.16); ctx.translate(-540, -1120);
      // encosta verde + cercas + placa de inclinacao
      ctx.fillStyle = '#5EB254'; ctx.fillRect(-350, 860, W + 700, 320);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-350, 860); ctx.lineTo(W + 350, 860); ctx.stroke();
      for (let i = 0; i < 6; i++) {
        const span = 1800;
        const tx = ((i * 300 - lt * 340) % span + span) % span - 240;
        ctx.fillStyle = '#5D3E26'; ctx.fillRect(tx - 12, 740, 24, 150);
        ctx.beginPath(); ctx.arc(tx, 700, 74, 0, Math.PI * 2); outlined(ctx, '#3E9448', 6);
      }
      // placa SUBIDA 12%
      const sx = ((960 - lt * 260) % 1700 + 1700) % 1700 - 220;
      ctx.fillStyle = '#6A7285'; ctx.fillRect(sx - 6, 820, 12, 190);
      ctx.save(); ctx.translate(sx, 800); ctx.rotate(Math.PI / 4);
      rr(ctx, -46, -46, 92, 92, 10); outlined(ctx, '#FFD400', 5);
      ctx.restore();
      label(ctx, '12%', sx, 802, 34, INK);
      // pista asfaltada da subida
      ctx.fillStyle = '#383F4F'; ctx.fillRect(-350, 1010, W + 700, 760);
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 8; ctx.beginPath(); ctx.moveTo(-350, 1020); ctx.lineTo(W + 350, 1020); ctx.stroke();
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.setLineDash([74, 52]); ctx.lineDashOffset = lt * 640;
      ctx.beginPath(); ctx.moveTo(-350, 1185); ctx.lineTo(W + 350, 1185); ctx.stroke(); ctx.setLineDash([]);

      // ciclista na faixa superior sofrendo na subida, ficando claramente visivel atras do Beto
      const passK = clamp((t - (T.tPas - 0.55)) / 1.05, 0, 1);
      const cycX = lerp(680, 220, eIO(passK));
      const betoX = lerp(240, 670, eOut(passK));
      drawCyclist(ctx, cycX, 1055, 1.05, t, passK > 0.35);
      // Beto ultrapassando rindo na faixa da frente
      const feet = 1268, bs = 1.04, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 3.1)) * 22;
      contactShadow(ctx, betoX, feet, 90, 0.35);
      dustPuffs(ctx, t, betoX - 48, feet - 10, 8, 220, '#E8ECF2', 0.5, 27);
      drawBeto(ctx, st, {
        x: betoX, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t,
        pose: runPose(t, 3.1, false),
        rim: { color: '#FFF4C2', dir: [0.8, -0.6] }, wind: [-34, 0]
      });
      ctx.restore();
      speedHoriz(ctx, t, 1400, 16, '#FFFFFF', 0.3, 21, 350, 1350);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 5. DIA 3
  SC.dia3 = {
    times(S) { return { tTch: S.c('dia3', 'tchauzinho'), tUs: S.c('dia3', 'Usain'), tBo: S.w('dia3', 'Bolt').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia3'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tTch, expr: 'smug' },
        { t: T.tBo, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tTch, T.tUs, T.tBo]; },
    hud(S, t) {
      const s0 = S.start('dia3');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia3', 'hora').t1, 20, 40);
      return { bar: { day: 3, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia3'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tBo, a: 18, d: 0.4 }]);
      const z = kf(t, [[s0, 1.05], [T.tTch, 1.0], [T.tBo, 1.16, eBack]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#060A1D'], [0.45, '#13204E'], [1, '#1E316A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      stars(ctx, t, 45, 310, 0.5, lt * 12);
      // torres de holofotes
      for (const tx of [120, 920]) {
        ctx.fillStyle = '#19223B'; ctx.fillRect(tx - 12, 270, 24, 390);
        rr(ctx, tx - 80, 195, 160, 88, 10); outlined(ctx, '#283354', 5);
        for (let i = 0; i < 4; i++) { ctx.fillStyle = '#FFF7DA'; ctx.beginPath(); ctx.arc(tx - 54 + i * 36, 238, 13, 0, Math.PI * 2); ctx.fill(); }
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        glow(ctx, tx, 240, 290, 'rgba(255,245,205,A)', 0.45);
        ctx.restore();
      }
      // arquibancada + torcida vibrando
      const excite = clamp((t - T.tUs) / 0.25, 0, 1);
      ctx.fillStyle = '#151D36'; ctx.fillRect(-200, 620, W + 400, 380);
      const crowdCols = ['#3A4566', '#564166', '#2E5266', '#66503E', '#3A664C'];
      for (let row = 0; row < 6; row++) {
        const y = 665 + row * 52;
        ctx.fillStyle = row % 2 ? '#1A2442' : '#1F2B4D'; ctx.fillRect(-200, y + 14, W + 400, 28);
        for (let i = 0; i < 36; i++) {
          const x = -180 + i * 40 + (row % 2) * 18;
          const id = row * 100 + i;
          const jump = Math.max(0, Math.sin(t * (7 + hash(id) * 4) + id)) * (4 + excite * 18);
          ctx.fillStyle = crowdCols[(id * 7) % 5];
          ctx.beginPath(); ctx.arc(x, y - jump, 12, 0, Math.PI * 2); ctx.fill();
          ctx.fillRect(x - 13, y + 6 - jump, 26, 20);
        }
      }
      // flashes da torcida
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      const fr = Math.floor(t * 30);
      for (let i = 0; i < 32; i++) {
        if (hash(fr * 37 + i) < 0.05 + excite * 0.16) {
          const fx = -160 + hash(i * 11 + fr) * (W + 320), fy = 650 + hash(i * 17 + fr) * 320;
          glow(ctx, fx, fy, 56, 'rgba(255,255,255,A)', 0.9);
        }
      }
      ctx.restore();
      // placar olimpico (esquerda superior segura, abaixo do HUD)
      const flip = t >= T.tBo;
      rr(ctx, 70, 385, 360, 175, 16); outlined(ctx, '#0A0F1E', 7);
      ctx.strokeStyle = flip ? '#FFD400' : '#40E088'; ctx.lineWidth = 4; rr(ctx, 82, 397, 336, 151, 10); ctx.stroke();
      label(ctx, flip ? 'ULTRAPASSADO!' : '100m OLÍMPICO', 250, 434, 34, flip ? '#FFD400' : '#40E088');
      label(ctx, flip ? '40 km/h' : '9,58 s', 250, 498, 68, '#FFFFFF');

      // pista olimpica terracota correndo rapido para a esquerda
      ctx.fillStyle = vGrad(ctx, [[0, '#CC502D'], [1, '#98351C']], 1000, H); ctx.fillRect(-200, 1000, W + 400, 960);
      ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 6;
      for (const ly of [1020, 1110, 1215, 1340]) { ctx.beginPath(); ctx.moveTo(-200, ly); ctx.lineTo(W + 200, ly); ctx.stroke(); }
      // marcadores de metros passando rapido
      for (let i = 0; i < 6; i++) {
        const mx = ((i * 280 - lt * 1200) % 1680 + 1680) % 1680 - 200;
        ctx.fillStyle = 'rgba(255,255,255,0.55)'; ctx.fillRect(mx, 1020, 10, 320);
      }
      // campeao na raia de cima ficando para tras
      const passK = clamp((t - (T.tTch - 0.35)) / 1.45, 0, 1);
      const champX = lerp(690, 210, eIO(passK));
      const betoX = lerp(280, 620, eOut(passK));
      contactShadow(ctx, champX, 1155, 72, 0.35);
      drawChampionRunner(ctx, champX, 1045, 1.05, t, passK > 0.35);

      // Beto na raia da frente dando tchauzinho!
      const feet = 1275, bs = 1.06, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 4.0)) * 22;
      contactShadow(ctx, betoX, feet, 86, 0.38);
      dustPuffs(ctx, t, betoX - 55, feet - 10, 10, 320, '#F5C4A8', 0.45, 33);
      drawBeto(ctx, st, {
        x: betoX, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t,
        pose: t >= T.tTch ? waveRunPose(t, 4.0) : runPose(t, 4.0, false),
        rim: { color: '#FFE8A0', dir: [0.6, -0.8] }, wind: [-55, 0]
      });
      // confete dourado no Bolt
      if (t > T.tBo) {
        for (let i = 0; i < 55; i++) {
          const age = t - T.tBo, a = hash(i + 350) * Math.PI * 2, sp = 280 + hash(i + 351) * 620;
          const x = betoX + Math.cos(a) * sp * age, y = 840 + Math.sin(a) * sp * age + 480 * age * age;
          ctx.save(); ctx.translate(x, y); ctx.rotate(age * 9 + i);
          ctx.fillStyle = ['#FFD400', '#FFFFFF', '#40E088'][i % 3];
          ctx.globalAlpha = clamp(1.5 - age * 0.65, 0, 1);
          ctx.fillRect(-7, -4, 14, 8); ctx.restore();
        }
      }
      speedHoriz(ctx, t, 2200, 20, '#FFFFFF', 0.35, 39, 360, 1340);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 6. DIA 5
  SC.dia5 = {
    times(S) { return { tRad: S.c('dia5', 'radares'), tTr: S.w('dia5', 'travam').t0, tFum: S.c('dia5', 'fumaça') }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia5'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tRad, expr: 'focus' },
        { t: T.tTr, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tRad, T.tTr, T.tFum]; },
    hud(S, t) {
      const s0 = S.start('dia5');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia5', 'hora').t1, 40, 160);
      return { bar: { day: 5, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia5'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tTr, a: 22, d: 0.45 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#141133'], [0.48, '#53275E'], [0.85, '#C96548'], [1, '#F29F58']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tTr, 1.12, eBack]]), shake }, t);
      // skyline urbano rapido ao fundo
      for (let i = 0; i < 12; i++) {
        const span = 1800;
        const bx = ((i * 150 - lt * 420) % span + span) % span - 180;
        const bh = 260 + hash(i + 500) * 380;
        ctx.fillStyle = '#1E1A3D'; ctx.fillRect(bx, 1080 - bh, 128, bh);
        for (let wy = 30; wy < bh - 20; wy += 40) for (let wx = 16; wx < 110; wx += 32) {
          if (hash(i * 97 + wy + wx) > 0.55) { ctx.fillStyle = 'rgba(255,215,130,0.6)'; ctx.fillRect(bx + wx, 1080 - bh + wy, 14, 18); }
        }
      }
      // avenida asfaltada
      ctx.fillStyle = '#252B38'; ctx.fillRect(-200, 1080, W + 400, 900);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 12; ctx.setLineDash([90, 60]); ctx.lineDashOffset = lt * 2200;
      ctx.beginPath(); ctx.moveTo(-200, 1245); ctx.lineTo(W + 200, 1245); ctx.stroke(); ctx.setLineDash([]);

      // radares eletronicos travando e soltando fumaca
      const glitch = t >= T.tTr - 0.12;
      for (let k = 0; k < 2; k++) {
        const px = k === 0 ? 310 : 730;
        const py = 650;
        // poste
        ctx.fillStyle = '#566075'; ctx.fillRect(px - 12, py + 120, 24, 340);
        ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.strokeRect(px - 12, py + 120, 24, 340);
        // caixa do radar
        const jit = glitch ? Math.sin(t * 75 + k * 3) * 6 : 0;
        ctx.save(); ctx.translate(px + jit, py);
        rr(ctx, -95, -60, 190, 185, 16); outlined(ctx, '#D8DEE9', 6);
        // lente camera
        ctx.beginPath(); ctx.arc(0, -10, 26, 0, Math.PI * 2); outlined(ctx, '#182032', 5);
        ctx.beginPath(); ctx.arc(-6, -16, 8, 0, Math.PI * 2); ctx.fillStyle = '#70C8FF'; ctx.fill();
        // painel LED
        rr(ctx, -78, 36, 156, 68, 10); outlined(ctx, '#0A0F1A', 4);
        const flashOn = Math.abs(t - (T.tRad + k * 0.25)) < 0.16;
        if (glitch) {
          label(ctx, (Math.floor(t * 14 + k) % 2) ? 'ERRO!' : '999!', 0, 72, 46, '#FF2E3B');
          // fumaca + faiscas eletricas
          for (let sm = 0; sm < 7; sm++) {
            const ph = (t * 1.4 + sm * 0.14 + k * 0.3) % 1;
            ctx.globalAlpha = 0.72 * (1 - ph);
            ctx.fillStyle = sm % 2 ? '#7C8594' : '#4C5361';
            ctx.beginPath(); ctx.arc(Math.sin(ph * 6 + sm) * 28, -68 - ph * 170, 18 + ph * 34, 0, Math.PI * 2); ctx.fill();
          }
          ctx.globalAlpha = 1;
          ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 4;
          for (let sp = 0; sp < 4; sp++) {
            const ang = hash(Math.floor(t * 24) + sp * 13 + k) * Math.PI * 2;
            ctx.beginPath(); ctx.moveTo(Math.cos(ang) * 40, -50); ctx.lineTo(Math.cos(ang) * 95, -50 + Math.sin(ang) * 55); ctx.stroke();
          }
        } else {
          label(ctx, '160', 0, 72, 48, '#FFD400');
        }
        if (flashOn) {
          ctx.save(); ctx.globalCompositeOperation = 'lighter';
          glow(ctx, 0, -10, 260, 'rgba(255,255,255,A)', 0.95);
          ctx.restore();
        }
        ctx.restore();
      }
      // Beto rasgando a avenida
      const feet = 1230, bs = 1.04, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 5.2)) * 18;
      contactShadow(ctx, 510, feet, 95, 0.4);
      // rastro de movimento sutil atras do Beto
      ctx.save(); ctx.globalAlpha = 0.16;
      drawBeto(ctx, st, { x: 425, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t: t - 0.05, pose: runPose(t - 0.05, 5.2, true), wind: [-90, 0] });
      ctx.restore();
      drawBeto(ctx, st, {
        x: 520, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t,
        pose: runPose(t, 5.2, true),
        rim: { color: '#FFBE78', dir: [0.8, -0.5] }, wind: [-95, 0]
      });
      speedHoriz(ctx, t, 3400, 32, '#FFE8B8', 0.48, 55, 320, 1340);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 7. DIA 6
  SC.dia6 = {
    times(S) { return { tF1: S.c('dia6', 'Fórmula'), tPoe: S.w('dia6', 'poeira').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia6'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tF1, expr: 'focus' },
        { t: T.tPoe, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [S.c('dia6', 'carro'), T.tF1, T.tPoe]; },
    hud(S, t) {
      const s0 = S.start('dia6');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia6', 'hora').t1, 160, 320);
      return { bar: { day: 6, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia6'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: T.tF1, a: 20, d: 0.5 }, { t: T.tPoe, a: 16, d: 0.4 }]) + 4;
      fillScreen(ctx, vGrad(ctx, [[0, '#1B6FD4'], [0.48, '#6EC1FF'], [1, '#D8F1FF']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tF1, 1.08], [T.tPoe, 1.15, eBack]]), shake }, t);
      // arquibancadas cobertas de autodromo com torcida colorida e faixa quadriculada
      ctx.fillStyle = '#1E2A45'; ctx.fillRect(-200, 620, W + 400, 324);
      ctx.fillStyle = '#E6ECF5'; ctx.fillRect(-200, 608, W + 400, 26); // cobertura
      ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(-200, 634); ctx.lineTo(W + 200, 634); ctx.stroke();
      const f1Crowd = ['#E8322A', '#FFD400', '#FFFFFF', '#3FA7FF', '#44C767'];
      for (let row = 0; row < 4; row++) {
        const ry = 678 + row * 54;
        ctx.fillStyle = row % 2 ? '#253352' : '#2C3C5E'; ctx.fillRect(-200, ry + 12, W + 400, 26);
        for (let i = 0; i < 32; i++) {
          const sx = ((i * 52 - lt * 780) % 1664 + 1664) % 1664 - 200;
          ctx.fillStyle = f1Crowd[(i * 7 + row * 3) % f1Crowd.length];
          ctx.beginPath(); ctx.arc(sx, ry, 11, 0, Math.PI * 2); ctx.fill();
          ctx.fillRect(sx - 12, ry + 6, 24, 16);
        }
      }
      // muro quadriculado + patrocinio generico da pista
      for (let i = 0; i < 22; i++) {
        const px = ((i * 80 - lt * 1400) % 1760 + 1760) % 1760 - 200;
        ctx.fillStyle = i % 2 ? '#FFFFFF' : '#141923'; ctx.fillRect(px, 898, 80, 22);
        ctx.fillStyle = i % 2 ? '#141923' : '#FFFFFF'; ctx.fillRect(px, 920, 80, 22);
      }
      // grama + zebra vermelho e branco do circuito
      ctx.fillStyle = '#3B9C49'; ctx.fillRect(-200, 942, W + 400, 62);
      for (let i = 0; i < 16; i++) {
        const zx = ((i * 110 - lt * 2600) % 1760 + 1760) % 1760 - 220;
        ctx.fillStyle = i % 2 ? '#E8322A' : '#FFFFFF'; ctx.fillRect(zx, 996, 110, 32);
      }
      ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(-200, 1028); ctx.lineTo(W + 200, 1028); ctx.stroke();
      // pista de corrida
      ctx.fillStyle = '#2C313D'; ctx.fillRect(-200, 1028, W + 400, 900);
      ctx.strokeStyle = 'rgba(255,255,255,0.6)'; ctx.lineWidth = 8; ctx.setLineDash([120, 80]); ctx.lineDashOffset = lt * 3100;
      ctx.beginPath(); ctx.moveTo(-200, 1205); ctx.lineTo(W + 200, 1205); ctx.stroke(); ctx.setLineDash([]);

      // ultrapassagem do F1: carro na faixa superior esquerda, Beto dispara na frente direita!
      const passK = clamp((t - (T.tF1 - 0.95)) / 1.25, 0, 1);
      const carX = lerp(640, 235, eIO(passK));
      const betoX = lerp(210, 705, eOut(passK));
      drawF1Car(ctx, carX, 1072, 0.94, t);
      // nuvem de poeira atras do Beto jogando direto no F1
      if (passK > 0.22) {
        dustPuffs(ctx, t, betoX - 65, 1215, 18, 430, '#D9C8AE', 0.72, 62);
        dustPuffs(ctx, t, betoX - 85, 1170, 12, 370, '#BFA98A', 0.56, 67);
      }
      // Beto rasgando a pista na faixa da frente
      const feet = 1280, bs = 1.0, bounce = Math.abs(Math.sin(t * Math.PI * 2 * 6.0)) * 16;
      contactShadow(ctx, betoX, feet, 90, 0.42);
      drawBeto(ctx, st, {
        x: betoX, y: pelvisFromFeet(feet, bs) - bounce, scale: bs, t,
        pose: runPose(t, 6.0, true),
        rim: { color: '#FFF6C8', dir: [0.8, -0.5] }, wind: [-110, 0]
      });
      speedHoriz(ctx, t, 4200, 38, '#FFFFFF', 0.52, 69, 320, 1340);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 8. DIA 8
  SC.dia8 = {
    times(S) { return { tQ: S.w('dia8', 'quebra').t0, tEst: S.w('dia8', 'estilhaça').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia8'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tQ - 0.06, expr: 'scream' },
        { t: T.tEst, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tQ, S.c('dia8', 'som'), T.tEst]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia8');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia8', 'hora').t1, 320, 1280);
      const boom = t >= T.tQ - 0.06;
      return {
        bar: { day: 8, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v), alert: boom },
        customHud: speedGauge(v, { alert: boom }),
        alert: boom ? { text: 'BARREIRA DO SOM', t0: T.tQ - 0.06 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia8'), lt = t - s0;
      const boomAge = Math.max(0, t - T.tQ);
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: T.tQ, a: 38, d: 0.75 }, { t: T.tEst, a: 28, d: 0.5 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, '#0C1B3E'], [0.55, '#1D3E78'], [1, '#4A77B8']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tQ, 1.02], [T.tQ + 0.16, 1.18, eBack], [S.end('dia8'), 1.08]]), shake }, t);
      // fachada de predios envidracados ao longo da avenida (estilhaca logo apos o estouro sonico)
      const tBreak = T.tQ + 0.12;
      const broken = t >= tBreak;
      for (let i = 0; i < 6; i++) {
        const span = 1800;
        const bx = ((i * 300 - lt * 1600) % span + span) % span - 240;
        ctx.fillStyle = '#253452'; ctx.fillRect(bx, 380, 276, 710);
        ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.strokeRect(bx, 380, 276, 710);
        for (let wy = 0; wy < 5; wy++) for (let wx = 0; wx < 3; wx++) {
          const xw = bx + 20 + wx * 84, yw = 415 + wy * 124;
          ctx.fillStyle = broken ? '#0C1222' : '#8AD8FF';
          ctx.fillRect(xw, yw, 66, 94);
          ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(xw, yw, 66, 94);
          if (broken) {
            ctx.strokeStyle = '#E6FAFF'; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.moveTo(xw, yw); ctx.lineTo(xw + 24, yw + 30); ctx.lineTo(xw + 66, yw + 18);
            ctx.moveTo(xw + 66, yw + 94); ctx.lineTo(xw + 36, yw + 58); ctx.stroke();
          }
        }
      }
      // pista asfaltada
      ctx.fillStyle = '#1E2430'; ctx.fillRect(-200, 1090, W + 400, 900);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 12; ctx.setLineDash([120, 70]); ctx.lineDashOffset = lt * 3800;
      ctx.beginPath(); ctx.moveTo(-200, 1250); ctx.lineTo(W + 200, 1250); ctx.stroke(); ctx.setLineDash([]);

      // Beto + Cone de Mach luminoso
      const bx = 560, feet = 1245, bs = 1.04;
      contactShadow(ctx, bx, feet, 95, 0.42);
      if (t >= T.tQ - 0.05) {
        const coneK = clamp((t - (T.tQ - 0.05)) / 0.18, 0, 1);
        // aneis de onda de choque expandindo
        for (let r = 0; r < 3; r++) {
          const ra = (boomAge - r * 0.12);
          if (ra > 0 && ra < 0.85) {
            ctx.save(); ctx.globalAlpha = (1 - ra / 0.85) * 0.75;
            ctx.strokeStyle = '#E0FAFF'; ctx.lineWidth = 12 * (1 - ra / 0.85);
            ctx.beginPath(); ctx.ellipse(bx - ra * 140, 1010, 90 + ra * 320, 260 + ra * 540, 0, 0, Math.PI * 2); ctx.stroke();
            ctx.restore();
          }
        }
        // cone de condensacao (Mach cone) com ponta na frente do Beto
        ctx.save(); ctx.globalAlpha = 0.85 * coneK;
        const cg = ctx.createLinearGradient(bx + 110, 1020, bx - 360, 1020);
        cg.addColorStop(0, 'rgba(255,255,255,0.95)'); cg.addColorStop(0.4, 'rgba(155,235,255,0.62)'); cg.addColorStop(1, 'rgba(155,235,255,0)');
        ctx.fillStyle = cg;
        ctx.beginPath();
        ctx.moveTo(bx + 120, 1010);
        ctx.lineTo(bx - 340, 640);
        ctx.quadraticCurveTo(bx - 210, 1010, bx - 340, 1340);
        ctx.closePath(); ctx.fill();
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 6;
        ctx.beginPath(); ctx.moveTo(bx - 300, 680); ctx.lineTo(bx + 120, 1010); ctx.lineTo(bx - 300, 1300); ctx.stroke();
        ctx.restore();
      }
      drawBeto(ctx, st, {
        x: bx, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: runPose(t, 7.2, true),
        rim: { color: '#9CF4FF', dir: [1, -0.2] }, wind: [-130, 0]
      });
      // estilhacos de vidro voando na frente em chuva cintilante
      if (broken) {
        const age = t - tBreak;
        for (let i = 0; i < 46; i++) {
          const cyc = (age + hash(i + 805) * 0.45) % 1.4;
          const sx = ((hash(i + 800) * W - cyc * (320 + hash(i + 801) * 420)) % (W + 200) + (W + 200)) % (W + 200) - 100;
          const sy = 430 + hash(i + 802) * 560 + cyc * (180 + hash(i + 803) * 280);
          const sz = 14 + hash(i + 804) * 24;
          ctx.save(); ctx.translate(sx, sy); ctx.rotate(age * (5 + hash(i) * 7) + i);
          ctx.beginPath(); ctx.moveTo(-sz, -sz * 0.4); ctx.lineTo(sz * 0.9, -sz * 0.2); ctx.lineTo(0, sz * 0.9); ctx.closePath();
          outlined(ctx, i % 2 ? 'rgba(215,250,255,0.92)' : 'rgba(130,220,255,0.88)', 3);
          ctx.restore();
        }
      }
      speedHoriz(ctx, t, 5200, 44, '#D6F7FF', 0.55, 81, 300, 1360);
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 9. DIA 10
  SC.dia10 = {
    times(S) { return { tCac: S.c('dia10', 'caça'), tTr: S.w('dia10', 'trás').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia10'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tCac, expr: 'focus' },
        { t: T.tTr, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tCac, T.tTr]; },
    hud(S, t) {
      const s0 = S.start('dia10');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia10', 'hora').t1, 1280, 5120);
      return { bar: { day: 10, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia10'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: T.tCac, a: 22, d: 0.6 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, '#05153B'], [0.42, '#164CA8'], [0.8, '#5CA9F0'], [1, '#C5E6FF']]));
      glow(ctx, 880, 320, 440, 'rgba(255,244,210,A)', 0.5);
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.06], [T.tTr, 1.14]]), shake }, t);
      // mar de nuvens correndo em alta velocidade abaixo
      for (let i = 0; i < 8; i++) {
        const span = 1800;
        const cx = ((hash(i + 100) * span - lt * (1200 + (i % 3) * 500)) % span + span) % span - 220;
        const cy = 1150 + (i % 3) * 140;
        cloud(ctx, cx, cy, 130 + hash(i + 101) * 70, '#FFFFFF', '#C6DFF5', 0.92);
      }
      speedHoriz(ctx, t, 6000, 46, '#E4F5FF', 0.55, 102, 260, 1380);
      // caca supersonico acima e ficando para tras com folga limpa do cabelo do Beto
      const passK = clamp((t - (T.tCac - 0.5)) / 1.8, 0, 1);
      const jetX = lerp(640, -90, eIO(passK));
      const jetY = 635 + Math.sin(t * 7) * 12;
      drawFighterJet(ctx, jetX, jetY, 1.02, -0.04, t);
      // esteira supersonica sob os pes do Beto
      const betoX = lerp(310, 650, eOut(passK));
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      const wake = ctx.createLinearGradient(betoX - 700, 0, betoX + 80, 0);
      wake.addColorStop(0, 'rgba(120,220,255,0)'); wake.addColorStop(0.7, 'rgba(180,240,255,0.65)'); wake.addColorStop(1, 'rgba(255,255,255,0.95)');
      ctx.fillStyle = wake; ctx.beginPath();
      ctx.moveTo(betoX + 90, 1050); ctx.lineTo(betoX - 700, 920); ctx.lineTo(betoX - 700, 1170); ctx.closePath(); ctx.fill();
      ctx.restore();
      drawBeto(ctx, st, {
        x: betoX, y: 1050 + Math.sin(t * 14) * 8, scale: 1.0, t,
        pose: runPose(t, 7.8, true),
        rim: { color: '#A8ECFF', dir: [0.9, -0.4] }, wind: [-140, 0]
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. DIA 12
  SC.dia12 = {
    times(S) { return { tVol: S.c('dia12', 'Volta'), tTer: S.w('dia12', 'Terra').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia12'), pose: 'idle', expr: 'amazed', dur: 0.01 },
        { t: T.tVol, expr: 'determined' },
        { t: T.tTer, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tVol, T.tTer, S.c('dia12', 'horas')]; },
    hud(S, t) {
      const s0 = S.start('dia12');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia12', 'hora').t1, 5120, 20000);
      return { bar: { day: 12, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia12'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tVol, a: 16, d: 0.4 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#01030B'], [0.6, '#060E2A'], [1, '#0C1E4E']]));
      stars(ctx, t, 220, 1212, 0.92, lt * 22);
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.06], [T.tVol, 0.96], [S.end('dia12'), 1.04]]), shake }, t);
      const ecx = 500, ecy = 910, eR = 320;
      const orbitA = lt * 3.8;
      // metade de TRAS do anel orbital (passa por tras do planeta Terra em 3D!)
      ctx.save(); ctx.translate(ecx, ecy); ctx.rotate(-0.18);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      ctx.strokeStyle = 'rgba(255,140,40,0.42)'; ctx.lineWidth = 32;
      ctx.beginPath(); ctx.ellipse(0, 0, eR + 82, 120, 0, Math.PI, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 9;
      ctx.beginPath(); ctx.ellipse(0, 0, eR + 82, 120, 0, Math.PI, Math.PI * 2); ctx.stroke();
      ctx.restore();
      ctx.restore();

      drawOrbitEarth(ctx, ecx, ecy, eR, t);

      // metade da FRENTE do anel orbital + Beto circulando a Terra
      ctx.save(); ctx.translate(ecx, ecy); ctx.rotate(-0.18);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      ctx.strokeStyle = 'rgba(255,140,40,0.52)'; ctx.lineWidth = 34;
      ctx.beginPath(); ctx.ellipse(0, 0, eR + 82, 120, 0, 0, Math.PI); ctx.stroke();
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 11;
      ctx.beginPath(); ctx.ellipse(0, 0, eR + 82, 120, 0, 0, Math.PI); ctx.stroke();
      ctx.restore();
      const bx = Math.cos(orbitA) * (eR + 82), by = Math.sin(orbitA) * 120;
      const front = Math.sin(orbitA) >= 0;
      if (front) {
        drawBeto(ctx, st, {
          x: bx, y: by - 40, scale: 0.58, t,
          pose: runPose(t, 8.2, true),
          rim: { color: '#FFD400', dir: [0.8, -0.5] }, wind: [-90, 0]
        });
      }
      ctx.restore();
      // selo VOLTA NA TERRA: 2 HORAS (borda completa 4 lados, sempre nitido)
      const bk = clamp((t - (s0 + 0.35)) / 0.25, 0, 1);
      if (bk > 0) {
        ctx.save(); ctx.globalAlpha = bk;
        rr(ctx, 120, 395, 430, 76, 18); outlined(ctx, 'rgba(11,15,25,0.92)', 4);
        ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 3; rr(ctx, 128, 403, 414, 60, 12); ctx.stroke();
        label(ctx, 'VOLTA NA TERRA: 2 HORAS', 335, 435, 34, '#FFD400');
        ctx.restore();
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. DIA 15
  SC.dia15 = {
    times(S) { return { tCin: S.c('dia15', 'cinza'), tFog: S.w('dia15', 'fogo').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia15'), pose: 'idle', expr: 'focus', dur: 0.01 },
        { t: T.tCin, expr: 'shock' },
        { t: T.tFog, expr: 'scream' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tCin, T.tFog]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia15');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia15', 'hora').t1, 20000, 160000);
      const hot = t >= T.tCin - 0.05;
      return {
        bar: { day: 15, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v), alert: hot },
        customHud: speedGauge(v, { alert: hot }),
        alert: hot ? { text: 'ATRITO EXTREMO', t0: T.tCin - 0.05 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia15'), lt = t - s0;
      const heat = clamp((t - (s0 + 0.2)) / 0.8, 0.25, 1);
      const shake = hits(t, [{ t: s0, a: 16, d: 0.3 }, { t: T.tFog, a: 28, d: 0.6 }]) + 8;
      fillScreen(ctx, vGrad(ctx, [[0, '#140305'], [0.45, '#5E1108'], [0.8, '#C94112'], [1, '#FF8C24']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [T.tFog, 1.16, eBack]]), shake }, t);
      // chao incandescente
      ctx.fillStyle = vGrad(ctx, [[0, '#3D140E'], [1, '#1A0706']], 1160, H); ctx.fillRect(-200, 1160, W + 400, 800);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = 'rgba(255,120,25,0.55)'; ctx.fillRect(-200, 1152, W + 400, 20);
      ctx.restore();
      speedHoriz(ctx, t, 6800, 56, '#FFE39C', 0.62, 151, 260, 1340);

      const bx = 560, feet = 1230, bs = 1.06;
      // rastro de cinzas e brasas saindo dos tenis
      for (let i = 0; i < 48; i++) {
        const ph = (t * (2.6 + hash(i + 1500) * 1.8) + hash(i + 1501)) % 1;
        const px = bx - 30 - ph * 640;
        const py = feet - 16 - hash(i + 1502) * 120 * ph + Math.sin(ph * 8 + i) * 20;
        ctx.fillStyle = i % 3 === 0 ? `rgba(120,120,130,${(1 - ph) * 0.85})` : `rgba(255,${150 + (i % 100)},40,${1 - ph})`;
        ctx.beginPath(); ctx.arc(px, py, 4 + hash(i + 1503) * 10, 0, Math.PI * 2); ctx.fill();
      }
      // arco de plasma aerodinamico curvo envolvente (sem corte reto!)
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, bx + 65, 995, 360, 'rgba(255,115,20,A)', 0.55 * heat);
      glow(ctx, bx + 95, 995, 190, 'rgba(255,235,140,A)', 0.82 * heat);
      for (let i = 0; i < 14; i++) {
        const u = (i - 6.5) / 6.5;
        const y = 1000 + u * 210 + vnoise(t * 10 + i) * 14;
        const frontX = bx + 145 - u * u * 125 + vnoise(t * 14 + i * 2) * 12;
        const len = (360 + hash(i + 1550) * 340) * heat;
        const fg = ctx.createLinearGradient(frontX + 24, y, frontX - len, y);
        fg.addColorStop(0, 'rgba(255,235,150,0)');
        fg.addColorStop(0.15, 'rgba(255,220,115,0.88)');
        fg.addColorStop(0.55, 'rgba(255,95,25,0.52)');
        fg.addColorStop(1, 'rgba(220,30,10,0)');
        ctx.fillStyle = fg;
        ctx.beginPath();
        ctx.moveTo(frontX, y - 22);
        ctx.quadraticCurveTo(frontX - len * 0.5, y - 24 + vnoise(t * 9 + i) * 32, frontX - len, y);
        ctx.quadraticCurveTo(frontX - len * 0.5, y + 24 + vnoise(t * 8 + i) * 32, frontX, y + 22);
        ctx.quadraticCurveTo(frontX + 26, y, frontX, y - 22);
        ctx.fill();
      }
      ctx.restore();
      drawBeto(ctx, st, {
        x: bx, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: runPose(t, 8.8, true),
        rim: { color: '#FFC252', dir: [1, -0.2] }, wind: [-160, 0]
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 12. DIA 18
  SC.dia18 = {
    times(S) { return { tRaio: S.c('dia18', 'raio'), tCong: S.w('dia18', 'congelado').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia18'), pose: 'idle', expr: 'amazed', dur: 0.01 },
        { t: T.tRaio, expr: 'curious' },
        { t: T.tCong, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tRaio, T.tCong]; },
    hud(S, t) {
      const s0 = S.start('dia18');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia18', 'hora').t1, 160000, 1310720);
      return { bar: { day: 18, dayT: s0, label: 'VELOCIDADE', value: fmtSpeed(v) }, customHud: speedGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia18'), lt = t - s0;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tRaio, a: 22, d: 0.4 }]) + 1.5;
      fillScreen(ctx, vGrad(ctx, [[0, '#040818'], [0.45, '#0F1F48'], [0.85, '#1D376E'], [1, '#101B36']]));
      ctx.save();
      // camera lenta espacial sobre tempestade congelada
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tCong, 1.12]]), shake }, t);
      // nuvens pesadas de tempestade no topo (quase paradas!)
      for (let i = 0; i < 6; i++) {
        cloud(ctx, -60 + i * 240 - lt * 12, 340 + (i % 2) * 45, 160, '#2C3D66', '#162040', 0.95);
      }
      // grande raio eletrico CONGELADO no meio do ceu
      const boltPts = [[700, 320], [625, 470], [690, 560], [575, 730], [640, 825], [515, 1020], [565, 1140], [490, 1290]];
      const branch1 = [[625, 470], [490, 565], [440, 660]];
      const branch2 = [[575, 730], [740, 835], [810, 955]];
      const drawBolt = (pts, lw, col, a) => {
        ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = col; ctx.lineWidth = lw;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        ctx.stroke(); ctx.restore();
      };
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 610, 740, 440, 'rgba(90,225,255,A)', 0.35 + 0.08 * Math.sin(t * 6));
      for (const bp of [boltPts, branch1, branch2]) {
        const sc = bp === boltPts ? 1 : 0.6;
        drawBolt(bp, 42 * sc, 'rgba(70,210,255,0.28)', 1);
        drawBolt(bp, 22 * sc, 'rgba(130,240,255,0.62)', 1);
        drawBolt(bp, 9 * sc, '#FFFFFF', 1);
      }
      ctx.restore();
      // gotas de chuva totalmente congeladas no ar com brilho ciano
      for (let i = 0; i < 72; i++) {
        const dx = hash(i + 1800) * W - lt * 14;
        const dy = 360 + hash(i + 1801) * 940 + lt * 4; // movimento quase zero!
        const dr = 5 + hash(i + 1802) * 8;
        ctx.save(); ctx.translate(dx, dy); ctx.rotate(0.18);
        ctx.beginPath(); ctx.moveTo(0, -dr * 1.7); ctx.quadraticCurveTo(dr, 0, 0, dr); ctx.quadraticCurveTo(-dr, 0, 0, -dr * 1.7);
        outlined(ctx, 'rgba(160,235,255,0.85)', 2.5);
        ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(-dr * 0.25, -dr * 0.1, dr * 0.25, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
      // selo RAIO CONGELADO (aparece assim que o raio entra em cena)
      const ck = clamp((t - (T.tRaio - 0.1)) / 0.22, 0, 1);
      if (ck > 0) {
        ctx.save(); ctx.globalAlpha = ck;
        rr(ctx, 100, 420, 330, 74, 18); outlined(ctx, 'rgba(8,20,48,0.92)', 4);
        ctx.strokeStyle = '#7FF0FF'; ctx.lineWidth = 3; rr(ctx, 108, 428, 314, 58, 12); ctx.stroke();
        label(ctx, 'RAIO CONGELADO', 265, 459, 36, '#7FF0FF');
        ctx.restore();
      }
      // Beto observando o raio congelado enquanto corre tranquilo a esquerda
      drawBeto(ctx, st, {
        x: 325 + lt * 22, y: 1030 + Math.sin(t * 4) * 10, scale: 1.05, t,
        pose: runPose(t, 2.0, false),
        rim: { color: '#7FF0FF', dir: [0.9, -0.4] }, wind: [-40, 0]
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 13. DIA 28
  SC.dia28 = {
    times(S) { return { tLuz: S.c('dia28', 'luz'), tPar: S.w('dia28', 'para').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia28'), pose: 'super_launch', expr: 'amazed', dur: 0.01 },
        { t: T.tLuz, pose: 'soar_spread', expr: 'shock', dur: 0.25 },
        { t: T.tPar, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tLuz, T.tPar]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia28');
      const v = HUD.roll(t, s0 + 0.08, T.tLuz + 0.15, 1310720, 1079252848);
      const stopped = t >= T.tPar - 0.05;
      return {
        bar: { day: 28, dayT: s0, label: 'VELOCIDADE', value: t >= T.tLuz ? '300 mil km/s' : fmtSpeed(v), alert: stopped },
        customHud: speedGauge(v, { light: true }),
        alert: stopped ? { text: 'TEMPO CONGELADO', t0: T.tPar - 0.05 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia28'), lt = t - s0;
      const stopped = t >= T.tPar;
      const tAnim = stopped ? T.tPar : t;
      const shake = hits(t, [{ t: s0, a: 16, d: 0.35 }, { t: T.tPar, a: 24, d: 0.45 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#02010A'], [0.5, '#090726'], [1, '#040B24']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tPar, 1.15, eOut]]), shake }, t);
      // tunel relativistico Doppler arco-iris
      const warpCols = ['#5CEEFF', '#FFFFFF', '#A87BFF', '#FFD400', '#63B3FF'];
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 110; i++) {
        const a = hash(i + 2800) * Math.PI * 2;
        const ph = ((tAnim * (1.8 + hash(i + 2801) * 2.5) + hash(i + 2802)) % 1);
        const r0 = 140 + ph * 960, len = 120 + ph * 340;
        ctx.globalAlpha = 0.72 * Math.sin(ph * Math.PI);
        ctx.strokeStyle = warpCols[i % warpCols.length];
        ctx.lineWidth = 3 + ph * 8; ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(540 + Math.cos(a) * r0, 900 + Math.sin(a) * r0);
        ctx.lineTo(540 + Math.cos(a) * (r0 + len), 900 + Math.sin(a) * (r0 + len));
        ctx.stroke();
      }
      glow(ctx, 540, 900, 480, 'rgba(130,235,255,A)', 0.45);
      ctx.restore();
      // relogio cosmico amplo atras do Beto que TRAVA em tPar
      const cx = 520, cy = 875, cR = 295;
      ctx.save(); ctx.globalAlpha = 0.88;
      ctx.beginPath(); ctx.arc(cx, cy, cR, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(8,14,42,0.58)'; ctx.fill();
      ctx.lineWidth = 9; ctx.strokeStyle = stopped ? '#7FF0FF' : '#FFD400'; ctx.stroke();
      for (let h = 0; h < 12; h++) {
        const a = h * Math.PI / 6;
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = h % 3 === 0 ? 8 : 3.5;
        ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * (cR - 30), cy + Math.sin(a) * (cR - 30));
        ctx.lineTo(cx + Math.cos(a) * (cR - 10), cy + Math.sin(a) * (cR - 10)); ctx.stroke();
      }
      // ponteiros longos visiveis alem da silhueta do Beto
      const minA = (tAnim - s0) * 14;
      const hrA = (tAnim - s0) * 1.8 - 1.1;
      ctx.strokeStyle = '#FFFFFF'; ctx.lineCap = 'round';
      ctx.lineWidth = 12; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(hrA) * 185, cy + Math.sin(hrA) * 185); ctx.stroke();
      ctx.lineWidth = 8; ctx.strokeStyle = '#7FF0FF'; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(minA) * 245, cy + Math.sin(minA) * 245); ctx.stroke();
      ctx.restore();
      if (stopped) {
        const ring = clamp((t - T.tPar) / 0.45, 0, 1);
        ctx.save(); ctx.globalAlpha = 1 - ring;
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 14 * (1 - ring);
        ctx.beginPath(); ctx.arc(cx, cy, cR + ring * 380, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
      }
      drawBeto(ctx, st, {
        x: 520, y: 965 + Math.sin(tAnim * 4) * 10, scale: 1.02, t: tAnim,
        rim: { color: '#FFFFFF', dir: [0, -1] }, wind: [0, -30]
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
        { t: S.c('twist_a', 'contou'), pose: 'look_down', expr: 'panic', dur: 0.3 }
      ];
    },
    ev(S) { return [S.c('twist_a', 'detalhe'), S.c('twist_a', 'contou'), S.seg('twist_a').t1]; },
    hud(S) {
      return {
        bar: { day: 28, dayT: -9, label: 'VELOCIDADE', value: '300 mil km/s' },
        customHud: speedGauge(1079252848, { light: true }),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), tDet = S.c('twist_a', 'detalhe'), tEnd = S.seg('twist_a').t1;
      const z = kf(t, [[s0, 1.12], [tDet, 1.38], [tEnd, 1.2]]);
      const camY = kf(t, [[s0, 880], [tDet, 835], [tEnd, 990]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#070A16'], [0.6, '#131A33'], [1, '#080B14']]));
      ctx.save();
      camApply(ctx, { x: 540, y: camY, z, shake: 2 }, t);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 540, 720, 520, 'rgba(140,180,255,A)', 0.22);
      ctx.restore();
      // pista escura com folga segura acima das legendas
      ctx.fillStyle = '#141824'; ctx.fillRect(-200, 1110, W + 400, 910);
      ctx.strokeStyle = 'rgba(255,255,255,0.22)'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(-200, 1110); ctx.lineTo(W + 200, 1110); ctx.stroke();
      contactShadow(ctx, 540, 1150, 106, 0.45);
      drawBeto(ctx, st, { x: 540, y: pelvisFromFeet(1150, 1.06), scale: 1.06, t, rim: { color: '#9BB8FF', dir: [0, -1] } });
      ctx.restore();
      const hold = clamp((t - tDet) / 0.8, 0, 1);
      ctx.save(); ctx.globalAlpha = 0.5 * hold;
      const vg = ctx.createRadialGradient(540, 960, 260, 540, 960, 1180);
      vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,1)');
      ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H); ctx.restore();
    }
  };

  // -------------------------------------------------------------- 15. TWIST B
  SC.twist_b = {
    times(S) { return { tPed: S.w('twist_b', 'pedrinha').t0, tExp: S.c('twist_b', 'explosão'), tNuc: S.c('twist_b', 'nuclear') }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('twist_b'), pose: 'look_down', expr: 'panic', dur: 0.01 },
        { t: T.tExp, pose: 'freefall_scream', expr: 'scream', dur: 0.08 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPed, T.tExp, T.tNuc]; },
    hud(S, t) {
      const T = this.times(S), boom = t >= T.tExp;
      return {
        bar: { day: 28, dayT: -9, label: boom ? 'IMPACTO' : 'OBSTÁCULO', value: boom ? 'NUCLEAR' : '1 PEDRINHA', alert: true },
        customHud: speedGauge(1079252848, { alert: true }),
        alert: boom ? { text: 'ALERTA NUCLEAR', t0: T.tExp } : null
      };
    },
    draw(ctx, t, S) {
      const T = this.times(S), s0 = S.start('twist_b');
      if (t < T.tExp) {
        // Beat 1: close cinematografico na PEDRINHA inocente + tenis chegando em chamas pela esquerda!
        const k = clamp((t - s0) / Math.max(0.2, T.tExp - s0), 0, 1);
        const z = lerp(1.0, 1.32, eIn(k));
        const shake = hits(t, [{ t: s0, a: 20, d: 0.3 }]) + k * 14;
        fillScreen(ctx, vGrad(ctx, [[0, '#141B2E'], [0.48, '#283652'], [1, '#20242E']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 1020, z, shake }, t);
        // asfalto granulado em primeiro plano
        ctx.fillStyle = '#2A2F3B'; ctx.fillRect(-250, 960, W + 500, 1100);
        ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-250, 960); ctx.lineTo(W + 250, 960); ctx.stroke();
        for (let i = 0; i < 65; i++) {
          ctx.fillStyle = i % 2 ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.22)';
          ctx.beginPath(); ctx.arc(hash(i + 2000) * W, 990 + hash(i + 2001) * 520, 3 + hash(i) * 5, 0, Math.PI * 2); ctx.fill();
        }
        // a PEDRINHA solitaria na direita
        const px = 685, py = 1135;
        contactShadow(ctx, px, py + 24, 52, 0.5);
        ctx.beginPath();
        ctx.moveTo(px - 34, py + 12); ctx.lineTo(px - 22, py - 20); ctx.lineTo(px + 12, py - 26);
        ctx.lineTo(px + 36, py - 4); ctx.lineTo(px + 26, py + 20); ctx.closePath();
        outlined(ctx, '#8F96A3', 6);
        ctx.fillStyle = '#B8C0CC'; ctx.beginPath(); ctx.moveTo(px - 16, py - 12); ctx.lineTo(px + 8, py - 18); ctx.lineTo(px + 14, py - 2); ctx.closePath(); ctx.fill();
        // etiqueta PEDRINHA amarela (sem stroke preto no texto escuro!)
        rr(ctx, px - 108, py - 144, 216, 62, 16); outlined(ctx, '#FFD400', 5);
        label(ctx, 'PEDRINHA', px, py - 112, 40, INK);
        ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(px, py - 80); ctx.lineTo(px, py - 36); ctx.stroke();

        // tenis gigante do Beto ja entrando em quadro a velocidade da luz pela esquerda!
        const shoeX = lerp(175, px - 135, eOut(k));
        ctx.save(); ctx.translate(shoeX, py - 42); ctx.rotate(0.06);
        // rastro de chama aerodinamico suave atras do tenis (sem borda reta)
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        const stg = ctx.createLinearGradient(-560, 0, 120, 0);
        stg.addColorStop(0, 'rgba(255,80,20,0)'); stg.addColorStop(0.55, 'rgba(255,140,35,0.58)'); stg.addColorStop(1, 'rgba(255,230,130,0.88)');
        ctx.fillStyle = stg;
        ctx.beginPath();
        ctx.moveTo(110, 0);
        ctx.quadraticCurveTo(-180, -74, -560, -28);
        ctx.lineTo(-560, 38);
        ctx.quadraticCurveTo(-180, 74, 110, 0);
        ctx.closePath(); ctx.fill();
        glow(ctx, 130, 8, 190, 'rgba(255,190,70,A)', 0.72);
        ctx.restore();
        // perna/calca azul em passada de corrida saindo naturalmente pelo topo-esquerdo do quadro
        ctx.beginPath();
        ctx.moveTo(-290, -1100); ctx.lineTo(-175, -1100); ctx.lineTo(14, -40); ctx.lineTo(-76, -40); ctx.closePath();
        outlined(ctx, PAL.pants, 8);
        // tenis estilizado do Beto (fiel a character.js)
        ctx.beginPath(); ctx.ellipse(0, 0, 145, 72, 0, 0, Math.PI * 2); outlined(ctx, PAL.shoe, 8);
        ctx.beginPath(); ctx.moveTo(-120, 32); ctx.lineTo(120, 32); ctx.strokeStyle = PAL.shoeAccent; ctx.lineWidth = 18; ctx.lineCap = 'round'; ctx.stroke();
        ctx.restore();
        ctx.restore();
        return;
      }

      // Beat 2: EXPLOSAO NUCLEAR ESTILIZADA (silhueta limpa de cogumelo sem linhas internas + folga abaixo do alerta)
      const age = t - T.tExp;
      const rise = eOut(clamp(age / 0.85, 0, 1));
      const shake = hits(t, [{ t: T.tExp, a: 48, d: 1.1 }, { t: T.tNuc, a: 28, d: 0.6 }]) + 7;
      fillScreen(ctx, vGrad(ctx, [[0, '#1A0406'], [0.4, '#6B120B'], [0.75, '#D94B14'], [1, '#FFAC33']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: lerp(1.18, 0.98, rise), shake }, t);
      // horizonte da cidade em silhueta
      ctx.fillStyle = '#18080A'; ctx.fillRect(-250, 1225, W + 500, 800);
      for (let i = 0; i < 14; i++) {
        const bw = 55 + hash(i + 2500) * 70, bh = 55 + hash(i + 2501) * 165;
        ctx.fillStyle = '#240B0E'; ctx.fillRect(-100 + i * 92, 1225 - bh, bw, bh);
      }
      // brilho nuclear central
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 515, 1060 - rise * 230, 680 * (0.6 + rise * 0.55), 'rgba(255,210,100,A)', 0.85);
      ctx.restore();
      // coluna do cogumelo (centrada em x=515 para folga da barra direita)
      const mcx = 515;
      const stemH = 120 + rise * 395;
      const stemY = 1225 - stemH;
      ctx.beginPath();
      ctx.moveTo(mcx - 140, 1230);
      ctx.quadraticCurveTo(mcx - 62, stemY + stemH * 0.5, mcx - 84, stemY);
      ctx.lineTo(mcx + 84, stemY);
      ctx.quadraticCurveTo(mcx + 62, stemY + stemH * 0.5, mcx + 140, 1230);
      ctx.closePath();
      const sg = ctx.createLinearGradient(0, stemY, 0, 1230);
      sg.addColorStop(0, '#FFF2B2'); sg.addColorStop(0.5, '#FF8C24'); sg.addColorStop(1, '#B82A14');
      outlined(ctx, sg, 8);
      // anel de condensacao no meio da coluna
      ctx.beginPath(); ctx.ellipse(mcx, stemY + stemH * 0.45, 165 + rise * 75, 32, 0, 0, Math.PI * 2);
      outlined(ctx, 'rgba(255,244,210,0.9)', 5);
      // copa do cogumelo com contorno EXTERNO unificado (stroke primeiro, fill depois = zero riscos internos!)
      const capY = stemY - 22, capR = 115 + rise * 145;
      const puffs = [[-0.98, 0.14, 0.58], [-0.46, -0.22, 0.72], [0, -0.36, 0.82], [0.46, -0.22, 0.72], [0.98, 0.14, 0.58], [0, 0.08, 0.75]];
      const mg = ctx.createRadialGradient(mcx, capY - 15, 25, mcx, capY + 20, capR * 1.48);
      mg.addColorStop(0, '#FFFFFF'); mg.addColorStop(0.32, '#FFE066'); mg.addColorStop(0.7, '#FF5A1F'); mg.addColorStop(1, '#A61812');
      // passo 1: contorno grosso externo de cada lobo
      ctx.fillStyle = INK;
      for (const p of puffs) {
        ctx.beginPath(); ctx.arc(mcx + p[0] * capR, capY + p[1] * capR, p[2] * capR + 9, 0, Math.PI * 2); ctx.fill();
      }
      // passo 2: preenchimento continuo cobrindo todas as intersecoes internas
      ctx.fillStyle = mg;
      for (const p of puffs) {
        ctx.beginPath(); ctx.arc(mcx + p[0] * capR, capY + p[1] * capR, p[2] * capR, 0, Math.PI * 2); ctx.fill();
      }
      // faiscas e estilhacos subindo na explosao
      for (let i = 0; i < 36; i++) {
        const ang = hash(i + 2600) * Math.PI * 2;
        const dist = (180 + hash(i + 2601) * 420) * rise;
        const fx = mcx + Math.cos(ang) * dist, fy = capY + Math.sin(ang) * dist * 0.75;
        ctx.fillStyle = i % 2 ? '#FFF3B0' : '#FF7B29';
        ctx.globalAlpha = clamp(1 - age * 0.55, 0.25, 0.95);
        ctx.beginPath(); ctx.arc(fx, fy, 4 + hash(i + 2602) * 7, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      // onda de choque no chao expandindo
      ctx.save(); ctx.globalAlpha = clamp(1 - age * 0.65, 0.2, 0.9);
      ctx.strokeStyle = '#FFF6D6'; ctx.lineWidth = 14;
      ctx.beginPath(); ctx.ellipse(mcx, 1225, 160 + age * 640, 42 + age * 80, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
      ctx.restore();
      // flash branco cegante nos primeiros 0.28s da detonacao
      if (age < 0.28) {
        ctx.save(); ctx.globalAlpha = (1 - age / 0.28) * 0.92;
        ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H); ctx.restore();
      }
    }
  };

  // ---------------------------------------------------------------- 16. LOOP
  SC.loop = {
    keys(S) {
      return [
        { t: S.start('loop'), pose: 'shrug_question', expr: 'curious', dur: 0.18, ease: 'back' },
        { t: S.c('loop', 'você'), pose: 'point_hook', expr: 'focus', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'correr'), expr: 'smug' },
        { t: S.end('loop') - 0.32, pose: 'shock_closeup', expr: 'shock', dur: 0.2 }
      ];
    },
    ev(S) { return [S.c('loop', 'dia'), S.c('loop', 'você'), S.c('loop', 'correr'), S.end('loop') - 0.5]; },
    hud(S) {
      const s0 = S.start('loop');
      return { bar: { day: '?', dayT: s0, label: 'SUA RESPOSTA', value: 'COMENTE' }, ruler: null, alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop'), tV = S.c('loop', 'você');
      const z = kf(t, [[s0, 1.6], [s0 + 0.2, 1.9, eBack], [tV, 1.9], [tV + 0.2, 2.25, eBack], [s1 - 0.55, 2.45], [s1, 3.6, eIn]]);
      const shake = hits(t, [{ t: s0, a: 28, d: 0.5 }, { t: tV, a: 14, d: 0.3 }]) + 3;
      radialBurst(ctx, t, 540, 760, '#B0141F', '#6E0B12', 22, 0.38);
      speedRadial(ctx, t, 540, 760, 50, '#FFE9D6', 0.42, 380, 11);
      const bx = 540, by = 1180;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);
      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 60 / z, z, shake }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1, t, rim: { color: '#FFB25C', dir: [0.8, -0.6] } });
      ctx.restore();
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
