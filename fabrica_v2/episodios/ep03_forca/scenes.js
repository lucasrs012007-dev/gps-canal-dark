/*
 * ep03_forca/scenes.js : Episodio 3 ("E se a sua forca dobrasse todo dia?")
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
  const LIFT_ONE_HAND = Object.assign({}, B.POSES.idle, {
    lean: -4, head: -6, ua_r: 132, la_r: 158, hand_r: 0,
    ua_l: 28, la_l: -16, hand_l: 1, th_r: 12, sh_r: 2, th_l: 10, sh_l: 2
  });
  const LIFT_BOTH_UP = Object.assign({}, B.POSES.idle, {
    lean: 0, head: -6, ua_r: 126, la_r: 158, hand_r: 0,
    ua_l: 126, la_l: 158, hand_l: 0, th_r: 16, sh_r: 2, th_l: 16, sh_l: 2
  });
  const SHOULDER_HOLD = Object.assign({}, B.POSES.idle, {
    lean: -5, head: 6, ua_r: 108, la_r: 160, hand_r: 0,
    ua_l: 34, la_l: -20, hand_l: 1, th_r: 14, sh_r: 2, th_l: 12, sh_l: 2
  });
  const PULL_ROPE = Object.assign({}, B.POSES.idle, {
    lean: -16, head: 8, ua_r: 86, la_r: 118, hand_r: 1,
    ua_l: 52, la_l: 86, hand_l: 1, th_r: 30, sh_r: -12, th_l: -10, sh_l: 14
  });
  const PUSH_RIGHT = Object.assign({}, B.POSES.idle, {
    lean: 16, head: 6, ua_r: 92, la_r: 96, hand_r: 0,
    ua_l: -58, la_l: -74, hand_l: 0, th_r: 32, sh_r: -16, th_l: -16, sh_l: 22
  });
  const THROW_FOLLOW = Object.assign({}, B.POSES.idle, {
    lean: 14, head: -12, ua_r: 134, la_r: 146, hand_r: 0,
    ua_l: 48, la_l: 24, hand_l: 1, th_r: 24, sh_r: -8, th_l: -12, sh_l: 18
  });
  const CLAP_OPEN = Object.assign({}, B.POSES.idle, {
    lean: 0, head: 0, ua_r: 74, la_r: 96, hand_r: 0,
    ua_l: 74, la_l: 96, hand_l: 0, th_r: 10, sh_r: 2, th_l: 10, sh_l: 2
  });
  const CLAP_SHUT = Object.assign({}, B.POSES.idle, {
    lean: 2, head: 4, ua_r: -22, la_r: -56, hand_r: 0,
    ua_l: -22, la_l: -56, hand_l: 0, th_r: 12, sh_r: 2, th_l: 12, sh_l: 2
  });

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
  function groundCracks(ctx, x, y, r) {
    ctx.save(); ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.lineCap = 'round';
    const rays = [[-1, 0.25], [-0.65, 0.55], [-0.25, 0.72], [0.28, 0.7], [0.7, 0.52], [1, 0.22]];
    for (const [dx, dy] of rays) {
      ctx.beginPath(); ctx.moveTo(x, y);
      ctx.lineTo(x + dx * r * 0.52, y + dy * r * 0.42);
      ctx.lineTo(x + dx * r, y + dy * r * 0.65);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ------------------------------------------------ regua logaritmica de forca
  const FORCE_MARKS = [
    { kg: 100, txt: '100kg' },
    { kg: 1000, txt: '1t' },
    { kg: 1e5, txt: '100t' },
    { kg: 5e7, txt: '50kt' },
    { kg: 5e13, txt: '50Gt' },
    { kg: 7.35e22, txt: 'LUA' }
  ];
  function fmtForce(kg) {
    if (kg >= 1e20) return 'FORÇA LUNAR';
    if (kg >= 1e12) return HUD.fmtNum(Math.round(kg / 1e12), 0) + ' bi t';
    if (kg >= 1e9) return HUD.fmtNum(Math.round(kg / 1e9), 0) + ' mi t';
    if (kg >= 1e6) return HUD.fmtNum(Math.round(kg / 1e6), 0) + ' mil t';
    if (kg >= 5000) return HUD.fmtNum(Math.round(kg / 1000), 0) + ' t';
    return HUD.fmtNum(Math.round(kg), 0) + ' kg';
  }
  /** Regua vertical logaritmica de forca (100kg embaixo -> LUA no topo) na borda direita segura. */
  function strengthGauge(kg, opts) {
    opts = opts || {};
    return function drawStrengthGauge(ctx) {
      const x = 1012, y0 = 1080, y1 = 360;
      const lmin = Math.log10(100), lmax = Math.log10(1.2e23);
      const yOf = v => y0 - (Math.log10(clamp(v, 100, 1.2e23)) - lmin) / (lmax - lmin) * (y0 - y1);
      ctx.save();
      rr(ctx, x - 14, y1 - 26, 28, y0 - y1 + 52, 14);
      ctx.fillStyle = 'rgba(11,15,25,0.72)'; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.78)'; ctx.stroke();
      const ym = yOf(kg);
      rr(ctx, x - 7, ym, 14, Math.max(0, y0 + 12 - ym), 7);
      ctx.fillStyle = opts.cosmic ? '#7FF0FF' : (opts.alert ? HUD.COLORS.alert : HUD.COLORS.accent);
      ctx.fill();
      ctx.font = `21px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const mk of FORCE_MARKS) {
        const yy = yOf(mk.kg);
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
        ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
        ctx.strokeText(mk.txt, x - 32, yy + 1);
        ctx.fillStyle = mk.kg >= 1e20 ? '#7FF0FF' : 'rgba(255,255,255,0.94)';
        ctx.fillText(mk.txt, x - 32, yy + 1);
      }
      ctx.save(); ctx.translate(x, ym);
      ctx.beginPath(); ctx.moveTo(0, -19); ctx.lineTo(19, 0); ctx.lineTo(0, 19); ctx.lineTo(-19, 0); ctx.closePath();
      ctx.fillStyle = opts.cosmic ? '#7FF0FF' : '#E8322A'; ctx.fill();
      ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
      ctx.restore();
      ctx.restore();
    };
  }

  // --------------------------------------------------------- props de cenarios
  function drawCar(ctx, x, y, s, color, crush) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const c = crush || 0;
    // carroceria (quando crush > 0, amassa em V no centro como latinha!)
    ctx.beginPath();
    ctx.moveTo(-220, 48);
    ctx.lineTo(-220, -10);
    ctx.quadraticCurveTo(-180, -30, -120, -34 + c * 32);
    ctx.lineTo(-75, -105 + c * 52);
    ctx.lineTo(0, -108 + c * 92);
    ctx.lineTo(75, -105 + c * 52);
    ctx.lineTo(125, -34 + c * 32);
    ctx.quadraticCurveTo(195, -24, 220, -5);
    ctx.lineTo(220, 48);
    ctx.lineTo(0, 48 - c * 42);
    ctx.closePath();
    outlined(ctx, color, 8);
    // janelas
    ctx.beginPath();
    ctx.moveTo(-102, -32 + c * 28); ctx.lineTo(-66, -86 + c * 46);
    ctx.lineTo(-6, -86 + c * 74); ctx.lineTo(-6, -32 + c * 42); ctx.closePath();
    outlined(ctx, '#AEE6FF', 5);
    ctx.beginPath();
    ctx.moveTo(10, -32 + c * 42); ctx.lineTo(10, -86 + c * 74);
    ctx.lineTo(66, -86 + c * 46); ctx.lineTo(108, -32 + c * 28); ctx.closePath();
    outlined(ctx, '#AEE6FF', 5);
    // vincos de metal amassado
    if (c > 0.2) {
      ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(-26, -10); ctx.lineTo(4, 22); ctx.lineTo(30, -16);
      ctx.moveTo(-14, -46); ctx.lineTo(16, -24);
      ctx.stroke();
    }
    // farois
    rr(ctx, 198, -2, 24, 22, 6); outlined(ctx, '#FFE86B', 4);
    rr(ctx, -222, -2, 20, 22, 6); outlined(ctx, '#FF4A4A', 4);
    // rodas
    for (const wx of [-135 + c * 26, 135 - c * 26]) {
      ctx.beginPath(); ctx.arc(wx, 52 - c * 14, 44, 0, Math.PI * 2); outlined(ctx, '#1E2433', 8);
      ctx.beginPath(); ctx.arc(wx, 52 - c * 14, 20, 0, Math.PI * 2); outlined(ctx, '#DCE3F0', 5);
    }
    ctx.restore();
  }

  function drawElephant(ctx, x, y, s) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    // rabinho
    ctx.strokeStyle = INK; ctx.lineWidth = 9;
    ctx.beginPath(); ctx.moveTo(-165, -20); ctx.quadraticCurveTo(-205, 10, -195, 58); ctx.stroke();
    // 4 patas penduradas sobre a barra
    for (const px of [-115, -52, 48, 108]) {
      rr(ctx, px - 26, 20, 52, 92, 20); outlined(ctx, '#7E8898', 7);
    }
    // corpo arredondado
    ctx.beginPath(); ctx.ellipse(-10, -24, 165, 118, 0, 0, Math.PI * 2); outlined(ctx, '#949FAE', 8);
    // cabeca + tromba
    ctx.beginPath(); ctx.arc(140, -56, 82, 0, Math.PI * 2); outlined(ctx, '#9CA7B6', 8);
    // orelha grande
    ctx.beginPath(); ctx.ellipse(90, -58, 52, 74, -0.2, 0, Math.PI * 2); outlined(ctx, '#828D9C', 7);
    // tromba curvada para cima (surpreso!)
    ctx.beginPath();
    ctx.moveTo(205, -55); ctx.quadraticCurveTo(275, -35, 255, 36);
    ctx.quadraticCurveTo(240, 68, 208, 45); ctx.quadraticCurveTo(226, 22, 195, -18);
    ctx.closePath(); outlined(ctx, '#9CA7B6', 7);
    // presa branca
    ctx.beginPath(); ctx.moveTo(192, -16); ctx.quadraticCurveTo(234, 8, 252, -18); ctx.quadraticCurveTo(218, -4, 194, -30); ctx.closePath();
    outlined(ctx, '#FFFDF5', 5);
    // olho arregalado de susto
    ctx.beginPath(); ctx.arc(168, -76, 16, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(172, -76, 7, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function drawTruck(ctx, x, y, s, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    // bau metalico
    rr(ctx, -250, -145, 330, 175, 12); outlined(ctx, '#E9EEF5', 8);
    ctx.fillStyle = '#E8322A'; ctx.fillRect(-242, -55, 314, 34);
    ctx.strokeStyle = INK; ctx.lineWidth = 4;
    for (let gx = -210; gx <= 40; gx += 50) { ctx.beginPath(); ctx.moveTo(gx, -140); ctx.lineTo(gx, 24); ctx.stroke(); }
    // chassi
    rr(ctx, -255, 24, 490, 26, 8); outlined(ctx, '#353E52', 7);
    // cabine vermelha
    ctx.beginPath();
    ctx.moveTo(92, 26); ctx.lineTo(92, -112); ctx.lineTo(186, -112);
    ctx.lineTo(228, -50); ctx.lineTo(228, 26); ctx.closePath();
    outlined(ctx, '#D92B2B', 8);
    // para-brisa
    ctx.beginPath();
    ctx.moveTo(120, -96); ctx.lineTo(178, -96); ctx.lineTo(208, -48); ctx.lineTo(120, -48); ctx.closePath();
    outlined(ctx, '#9EE2FF', 5);
    // rodas
    for (const wx of [-190, -108, 168]) {
      ctx.beginPath(); ctx.arc(wx, 54, 38, 0, Math.PI * 2); outlined(ctx, '#1A202E', 7);
      ctx.beginPath(); ctx.arc(wx, 54, 16, 0, Math.PI * 2); outlined(ctx, '#CFD8E6', 5);
    }
    ctx.restore();
  }

  function drawAirliner(ctx, x, y, s) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    // cauda vertical azul
    ctx.beginPath();
    ctx.moveTo(-310, -28); ctx.lineTo(-370, -172); ctx.lineTo(-278, -172); ctx.lineTo(-215, -32); ctx.closePath();
    outlined(ctx, '#1B66D1', 8);
    // fuselagem branca colossal
    ctx.beginPath();
    ctx.moveTo(-350, -12);
    ctx.quadraticCurveTo(-340, -56, -240, -56);
    ctx.lineTo(255, -56);
    ctx.quadraticCurveTo(368, -44, 385, 8);
    ctx.quadraticCurveTo(365, 52, 245, 52);
    ctx.lineTo(-275, 42);
    ctx.quadraticCurveTo(-352, 34, -350, -12);
    ctx.closePath();
    outlined(ctx, '#F4F7FC', 8);
    // faixa azul + janelinhas de passageiros
    ctx.fillStyle = '#2574E6'; ctx.fillRect(-275, 6, 560, 18);
    ctx.fillStyle = '#182A4A';
    for (let wx = -235; wx <= 245; wx += 34) {
      rr(ctx, wx, -28, 18, 22, 7); ctx.fill();
    }
    // cockpit
    ctx.beginPath(); ctx.moveTo(286, -34); ctx.lineTo(340, -24); ctx.lineTo(334, -4); ctx.lineTo(286, -4); ctx.closePath();
    outlined(ctx, '#6FD8FF', 5);
    // asa em perspectiva + turbina sob a asa
    ctx.beginPath();
    ctx.moveTo(-45, 22); ctx.lineTo(95, 22); ctx.lineTo(-145, 118); ctx.lineTo(-205, 108); ctx.closePath();
    outlined(ctx, '#D4DFEE', 7);
    rr(ctx, -56, 62, 108, 52, 22); outlined(ctx, '#2574E6', 7);
    ctx.beginPath(); ctx.ellipse(48, 88, 14, 24, 0, 0, Math.PI * 2); outlined(ctx, '#182235', 5);
    ctx.restore();
  }

  function drawTitanic(ctx, x, y, s, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    // 4 chamines iconicas (amarelo ocre com topo preto!)
    for (let i = 0; i < 4; i++) {
      const fx = -145 + i * 86;
      ctx.save(); ctx.translate(fx, -125); ctx.rotate(-0.14);
      rr(ctx, -20, -68, 40, 82, 6); outlined(ctx, '#E5A93B', 6);
      ctx.fillStyle = '#161B26'; ctx.fillRect(-18, -66, 36, 24);
      ctx.restore();
    }
    // superestrutura branca (conveses)
    rr(ctx, -215, -96, 410, 56, 8); outlined(ctx, '#F7F9FC', 7);
    rr(ctx, -185, -126, 345, 36, 6); outlined(ctx, '#E6ECF5', 6);
    // janelinhas do conves
    ctx.fillStyle = '#FFD966';
    for (let wx = -195; wx <= 170; wx += 26) { ctx.fillRect(wx, -82, 12, 10); }
    // casco preto + linha vermelha de fundo
    ctx.beginPath();
    ctx.moveTo(-310, -44); ctx.lineTo(315, -48);
    ctx.lineTo(275, 58); ctx.lineTo(-278, 58); ctx.closePath();
    outlined(ctx, '#1B2130', 8);
    ctx.beginPath();
    ctx.moveTo(-290, 14); ctx.lineTo(292, 14); ctx.lineTo(275, 58); ctx.lineTo(-278, 58); ctx.closePath();
    outlined(ctx, '#B82525', 7);
    // vigias no casco
    ctx.fillStyle = '#FFE98A';
    for (let px = -240; px <= 235; px += 42) { ctx.beginPath(); ctx.arc(px, -16, 6, 0, Math.PI * 2); ctx.fill(); }
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
        tV3: S.c('hook', 'Você', 2) - 0.04,
        tAma: S.w('hook', 'amassar').t0,
        tLat: S.c('hook', 'latinha')
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: 0, pose: 'shock_closeup', expr: 'scream' },
        { t: T.tE, expr: 'shock' },
        { t: T.tV2, pose: 'point_hook', expr: 'focus', dur: 0.14, ease: 'back' },
        { t: T.tM, expr: 'scream' },
        { t: T.tV3, pose: 'flex', expr: 'amazed', dur: 0.04 },
        { t: T.tLat, pose: 'shock_closeup', expr: 'shock', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tV2, T.tV3, T.tAma, T.tLat]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const T = this.times(S);
      if (t < T.tV3) {
        // Plano A: explosao carmim + Beto apontando (braco preso real)
        const z = kf(t, [[0, 3.5], [T.tE, 3.5], [T.tE + 0.2, 2.85, eBack], [T.tV2, 2.85], [T.tV2 + 0.2, 2.35, eBack]]);
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
      // Plano B: rua ensolarada + Beto esmagando um carro no meio igual latinha!
      const lt = t - T.tV3;
      const crushK = eBack(clamp((t - T.tAma) / 0.38, 0, 1));
      const z = kf(t, [[T.tV3, 1.02], [T.tAma, 1.15, eBack], [S.end('hook'), 1.2]]);
      const shake = hits(t, [{ t: T.tV3, a: 22, d: 0.3 }, { t: T.tAma, a: 36, d: 0.5 }, { t: T.tLat, a: 26, d: 0.4 }]) + 4;
      fillScreen(ctx, vGrad(ctx, [[0, '#3D8BFF'], [0.45, '#9BD3FF'], [0.68, '#555E72'], [1, '#2B3140']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z, shake }, t);
      // predios estilizados ao fundo
      for (let i = 0; i < 6; i++) {
        const px = -60 + i * 205, ph = 320 + (i % 3) * 140;
        rr(ctx, px, 1020 - ph, 175, ph, 8); outlined(ctx, i % 2 ? '#5D7294' : '#4A5D7D', 6);
      }
      // asfalto + faixas
      ctx.fillStyle = '#383E4F'; ctx.fillRect(-200, 1020, W + 400, 960);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1020); ctx.lineTo(W + 200, 1020); ctx.stroke();
      ctx.fillStyle = '#FFD400'; for (let rx = -100; rx < W + 150; rx += 220) { ctx.fillRect(rx, 1185, 115, 18); }
      groundCracks(ctx, 520, 1210, 210);
      // anel de impacto + faiscas metalicas voando
      if (t >= T.tAma - 0.05) {
        const ring = clamp((t - T.tAma) / 0.55, 0, 1);
        ctx.save(); ctx.globalAlpha = (1 - ring) * 0.85;
        ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 14;
        ctx.beginPath(); ctx.arc(540, 740, 110 + ring * 360, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
      }
      // Beto segurando o carro amassado acima da cabeca!
      const feet = 1235, bs = 0.88;
      contactShadow(ctx, 540, feet, 98, 0.4);
      drawBeto(ctx, st, {
        x: 540, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_BOTH_UP,
        rim: { color: '#FFE880', dir: [0, -1] }
      });
      drawCar(ctx, 540, 850 - crushK * 12, 1.32, '#2B8EFF', clamp(crushK, 0, 1));
      // porcas e faiscas saltando
      for (let i = 0; i < 8; i++) {
        const a = hash(i + 77) * Math.PI * 2;
        const dist = 160 + ((lt * 320 + i * 40) % 240);
        ctx.fillStyle = i % 2 ? '#FFD400' : '#FFFFFF';
        ctx.beginPath(); ctx.arc(540 + Math.cos(a) * dist, 850 + Math.sin(a) * dist * 0.65, 9, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 2. PREMISSA
  const PWR_BARS = [
    { h: 0.14, lbl: '100kg' },
    { h: 0.22, lbl: '200kg' },
    { h: 0.34, lbl: '400kg' },
    { h: 0.50, lbl: '800kg' },
    { h: 0.72, lbl: '1,6t' },
    { h: 1.00, lbl: '3,2t' }
  ];
  SC.premissa = {
    keys(S) {
      const s0 = S.start('premissa');
      return [
        { t: s0, pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('premissa', 'dobra'), pose: 'flex', expr: 'determined', dur: 0.18, ease: 'back' },
        { t: S.c('premissa', 'dias'), expr: 'smug' }
      ];
    },
    ev(S) { return [S.c('premissa', 'força'), S.c('premissa', 'dobra'), S.c('premissa', 'dias')]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), tD = S.w('premissa', 'dobra').t0;
      const shake = hits(t, [{ t: tD, a: 24, d: 0.45 }, { t: s0, a: 12, d: 0.3 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#140B29'], [0.5, '#25124A'], [1, '#0F1838']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.05], [tD, 1.0], [S.end('premissa'), 1.05]]), shake }, t);
      // grade tecnica em perspectiva
      const off = (t * 36) % 54;
      ctx.lineWidth = 2;
      for (let x = -54 + off; x < W + 54; x += 54) {
        ctx.strokeStyle = 'rgba(255,195,90,0.14)';
        ctx.beginPath(); ctx.moveTo(x, -200); ctx.lineTo(x, H + 200); ctx.stroke();
      }
      for (let y = -54 + off; y < H + 54; y += 54) {
        ctx.strokeStyle = 'rgba(255,195,90,0.14)';
        ctx.beginPath(); ctx.moveTo(-200, y); ctx.lineTo(W + 200, y); ctx.stroke();
      }
      const ground = 1265, maxH = 700, pts = [];
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(40, ground); ctx.lineTo(1040, ground); ctx.stroke();
      PWR_BARS.forEach((b, i) => {
        const x = 395 + i * 104, w = 72;
        const k = clamp((t - (s0 + 0.22 + i * 0.14)) / 0.28, 0, 1);
        const h = b.h * maxH * (k > 0 ? eBack(k) : 0);
        if (h > 1) {
          rr(ctx, x - w / 2, ground - h, w, h, 12);
          const g = ctx.createLinearGradient(0, ground - h, 0, ground);
          g.addColorStop(0, i === 5 ? '#FF5E45' : '#FFE86B'); g.addColorStop(1, '#E07A00');
          outlined(ctx, g, 6);
        }
        if (k > 0.6) label(ctx, b.lbl, x, ground - h - 52, 30, '#FFFFFF');
        label(ctx, 'D' + (i + 1), x, ground + 40, 34, '#FFE299');
        pts.push([x, ground - b.h * maxH, k]);
      });
      ctx.save(); ctx.setLineDash([16, 14]); ctx.lineDashOffset = -t * 60;
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 5; ctx.beginPath();
      let started = false;
      for (const p of pts) { if (p[2] <= 0.6) break; started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; }
      ctx.stroke(); ctx.restore();
      // carimbo X2 POR DIA no quadrante superior esquerdo (livre acima das barras baixas!)
      const ks = clamp((t - (tD - 0.05)) / 0.22, 0, 1);
      if (ks > 0) {
        ctx.save(); ctx.translate(390, 560); ctx.rotate(-0.1);
        const sc = 2.2 - 1.2 * eBack(ks); ctx.scale(sc, sc);
        ctx.globalAlpha = clamp(ks * 2, 0, 1);
        label(ctx, 'X2', 0, 0, 220, '#FFD400', 'center', HUD.FONT_CAPTION);
        label(ctx, 'FORÇA / DIA', 0, 132, 60, '#FFFFFF', 'center', HUD.FONT_CAPTION);
        ctx.restore();
      }
      // aura dourada + Beto flexionando a esquerda
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 185, 1080, 240, 'rgba(255,195,50,A)', 0.34);
      ctx.restore();
      const bs = 0.94;
      contactShadow(ctx, 185, ground, 92, 0.36);
      drawBeto(ctx, st, { x: 185, y: pelvisFromFeet(ground, bs), scale: bs, t, rim: { color: '#FFD400', dir: [0.8, -0.5] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 3. DIA 1
  SC.dia1 = {
    times(S) { return { tLev: S.c('dia1', 'levanta'), tGel: S.w('dia1', 'geladeira').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia1'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: T.tLev, expr: 'smug' },
        { t: T.tGel, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tLev, T.tGel]; },
    hud(S, t) {
      const s0 = S.start('dia1');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia1', 'quilos').t1, 50, 100);
      return { bar: { day: 1, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia1');
      const liftK = eBack(clamp((t - T.tLev) / 0.45, 0, 1));
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }, { t: T.tLev, a: 14, d: 0.3 }]);
      fillScreen(ctx, '#E3F4EE');
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tGel, 1.08]]), shake }, t);
      // azulejos claros da cozinha
      ctx.strokeStyle = 'rgba(130,190,175,0.38)'; ctx.lineWidth = 3;
      for (let x = -120; x < W + 120; x += 90) { ctx.beginPath(); ctx.moveTo(x, -100); ctx.lineTo(x, 1180); ctx.stroke(); }
      for (let y = -100; y < 1180; y += 90) { ctx.beginPath(); ctx.moveTo(-120, y); ctx.lineTo(W + 120, y); ctx.stroke(); }
      // balcao ao fundo esquerdo
      rr(ctx, -40, 880, 310, 320, 8); outlined(ctx, '#D4A574', 6);
      rr(ctx, -50, 860, 330, 36, 8); outlined(ctx, '#F8F4EC', 6);
      // piso xadrez quente
      ctx.fillStyle = '#C99B6B'; ctx.fillRect(-150, 1180, W + 300, 820);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-150, 1180); ctx.lineTo(W + 150, 1180); ctx.stroke();
      // Beto erguendo a geladeira cheia com UMA UNICA MAO (mao direita erguida)
      const feet = 1245, bs = 0.92;
      contactShadow(ctx, 370, feet, 90, 0.36);
      drawBeto(ctx, st, {
        x: 370, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_ONE_HAND,
        rim: { color: '#FFFFFF', dir: [-0.6, -0.8] }
      });
      // GELADEIRA INOX CHEIA equilibrada na palma direita do Beto!
      const fy = lerp(955, 755, liftK) + Math.sin(t * 4) * 6;
      const fx = 548;
      ctx.save(); ctx.translate(fx, fy); ctx.rotate(-0.08 * liftK);
      rr(ctx, -125, -245, 250, 440, 22);
      const fg = ctx.createLinearGradient(-125, -245, 125, 195);
      fg.addColorStop(0, '#FFFFFF'); fg.addColorStop(0.55, '#DCE7F2'); fg.addColorStop(1, '#AABCC9');
      outlined(ctx, fg, 8);
      // divisao freezer / geladeira + puxadores cromados
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-125, -90); ctx.lineTo(125, -90); ctx.stroke();
      rr(ctx, -98, -195, 18, 74, 8); outlined(ctx, '#6F8296', 5);
      rr(ctx, -98, -56, 18, 120, 8); outlined(ctx, '#6F8296', 5);
      // imas coloridos na porta
      ctx.fillStyle = '#FF5C5C'; ctx.beginPath(); ctx.arc(42, -165, 16, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#FFD400'; ctx.fillRect(18, -32, 56, 44); ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(18, -32, 56, 44);
      pill(ctx, 0, 95, 175, 58, '#FFD400', null, '100 KG', INK, 34);
      ctx.restore();
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 4. DIA 3
  SC.dia3 = {
    times(S) { return { tMot: S.c('dia3', 'moto'), tBic: S.w('dia3', 'bicicleta').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia3'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tMot, expr: 'determined' },
        { t: T.tBic, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tMot, T.tBic]; },
    hud(S, t) {
      const s0 = S.start('dia3');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia3', 'quilos').t1, 100, 400);
      return { bar: { day: 3, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia3');
      const liftK = eBack(clamp((t - (s0 + 0.35)) / 0.5, 0, 1));
      const shake = hits(t, [{ t: s0, a: 10, d: 0.25 }, { t: T.tBic, a: 14, d: 0.3 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#4FA3FF'], [0.5, '#C4E7FF'], [0.68, '#545E73'], [1, '#2D3445']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tBic, 1.1]]), shake }, t);
      // nuvens e estrada
      for (const [cx, cy, r] of [[210, 430, 56], [760, 480, 48]]) {
        ctx.fillStyle = 'rgba(255,255,255,0.82)';
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.arc(cx + r * 0.85, cy + 8, r * 0.72, 0, Math.PI * 2); ctx.arc(cx - r * 0.8, cy + 12, r * 0.68, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = '#40485C'; ctx.fillRect(-200, 1140, W + 400, 860);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1140); ctx.lineTo(W + 200, 1140); ctx.stroke();
      // Beto equilibrando moto pesada no alto com uma mao
      const feet = 1245, bs = 0.92;
      contactShadow(ctx, 455, feet, 96, 0.38);
      drawBeto(ctx, st, {
        x: 455, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_ONE_HAND,
        rim: { color: '#FFF0A8', dir: [0.6, -0.8] }
      });
      // MOTO PESADA CRUISER vermelha e cromada equilibrada facil no ar!
      const mx = 515, my = lerp(910, 795, liftK) + Math.sin(t * 5) * 8;
      ctx.save(); ctx.translate(mx, my); ctx.rotate(Math.sin(t * 3.5) * 0.08 - 0.06);
      // rodas grossas
      for (const wx of [-168, 178]) {
        ctx.beginPath(); ctx.arc(wx, 68, 66, 0, Math.PI * 2); outlined(ctx, '#1A202E', 9);
        ctx.beginPath(); ctx.arc(wx, 68, 34, 0, Math.PI * 2); outlined(ctx, '#D4DCE8', 6);
      }
      // escapamento cromado + motor V-twin
      rr(ctx, -195, 42, 235, 28, 12); outlined(ctx, '#E2E9F2', 7);
      rr(ctx, -56, -24, 126, 86, 16); outlined(ctx, '#68748A', 7);
      // quadro e tanque vermelho esportivo
      ctx.beginPath();
      ctx.moveTo(-170, 6); ctx.quadraticCurveTo(-80, -35, -18, -32);
      ctx.quadraticCurveTo(45, -88, 138, -68); ctx.lineTo(155, -24); ctx.lineTo(-140, 26); ctx.closePath();
      outlined(ctx, '#E8322A', 8);
      // assento de couro + guidao + farol
      rr(ctx, -110, -48, 118, 30, 14); outlined(ctx, '#232836', 6);
      ctx.strokeStyle = INK; ctx.lineWidth = 14; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(178, 68); ctx.lineTo(116, -98); ctx.lineTo(72, -124); ctx.stroke();
      ctx.strokeStyle = '#DCE5F2'; ctx.lineWidth = 6; ctx.stroke();
      ctx.beginPath(); ctx.arc(165, -72, 24, 0, Math.PI * 2); outlined(ctx, '#FFE875', 6);
      ctx.restore();
      pill(ctx, 215, 595, 195, 60, '#FFD400', null, '400 KG', INK, 34);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 5. DIA 5
  SC.dia5 = {
    times(S) { return { tErg: S.c('dia5', 'ergue'), tCab: S.w('dia5', 'cabeça').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia5'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tErg, expr: 'smug' },
        { t: T.tCab, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tErg, T.tCab]; },
    hud(S, t) {
      const s0 = S.start('dia5');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia5', 'quilos').t1, 400, 1600);
      return { bar: { day: 5, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia5');
      const liftK = eBack(clamp((t - T.tErg) / 0.45, 0, 1));
      const shake = hits(t, [{ t: s0, a: 12, d: 0.25 }, { t: T.tErg, a: 22, d: 0.45 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#FFAE52'], [0.46, '#FFE3B0'], [0.68, '#555E70'], [1, '#292F3D']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tCab, 1.1]]), shake }, t);
      // predios da avenida
      for (let i = 0; i < 6; i++) {
        const bx = -40 + i * 200, bh = 360 + (i % 3) * 130;
        rr(ctx, bx, 1080 - bh, 165, bh, 8); outlined(ctx, i % 2 ? '#5A6785' : '#444F6B', 6);
        ctx.fillStyle = '#FFE999';
        for (let wy = 1080 - bh + 40; wy < 1030; wy += 64) {
          for (let wx = bx + 28; wx < bx + 135; wx += 44) { ctx.fillRect(wx, wy, 24, 34); }
        }
      }
      // rua + faixa de pedestre
      ctx.fillStyle = '#343A4A'; ctx.fillRect(-200, 1080, W + 400, 920);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1080); ctx.lineTo(W + 200, 1080); ctx.stroke();
      ctx.fillStyle = '#FFFFFF';
      for (let i = 0; i < 6; i++) { ctx.fillRect(100 + i * 155, 1180, 92, 42); }
      groundCracks(ctx, 490, 1235, 190);
      // Beto erguendo carro amarelo inteiro acima da cabeca!
      const feet = 1245, bs = 0.88;
      contactShadow(ctx, 490, feet, 98, 0.42);
      drawBeto(ctx, st, {
        x: 490, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: t >= T.tErg ? LIFT_BOTH_UP : st.pose,
        rim: { color: '#FFE899', dir: [0, -1] }
      });
      const cy = lerp(1035, 818, liftK) + Math.sin(t * 4) * 5;
      drawCar(ctx, 490, cy, 1.38, '#FFD400', 0);
      // flashes de celulares fotografando na rua!
      if (t >= T.tCab - 0.1) {
        for (let i = 0; i < 4; i++) {
          const fl = Math.max(0, Math.sin(t * 16 + i * 2.1));
          if (fl > 0.65) glow(ctx, 130 + i * 245, 1020 + (i % 2) * 90, 95, 'rgba(255,255,255,A)', (fl - 0.65) * 2.2);
        }
      }
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 6. DIA 7
  SC.dia7 = {
    times(S) { return { tEle: S.c('dia7', 'elefante'), tHal: S.w('dia7', 'haltere').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia7'), pose: 'flex', expr: 'determined', dur: 0.01 },
        { t: T.tEle, expr: 'smug' },
        { t: T.tHal, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tEle, T.tHal]; },
    hud(S, t) {
      const s0 = S.start('dia7');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia7', 'toneladas').t1, 1600, 6000);
      return { bar: { day: 7, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia7');
      const rep = Math.sin(t * 4.2) * 26;
      const shake = hits(t, [{ t: s0, a: 12, d: 0.25 }, { t: T.tEle, a: 18, d: 0.4 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#1B2238'], [0.55, '#2A3554'], [1, '#1A1F2E']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tHal, 1.08]]), shake }, t);
      // espelho grande de academia ao fundo
      rr(ctx, 85, 360, 770, 640, 18); outlined(ctx, '#384C72', 7);
      ctx.strokeStyle = 'rgba(255,255,255,0.22)'; ctx.lineWidth = 18;
      ctx.beginPath(); ctx.moveTo(150, 920); ctx.lineTo(420, 420); ctx.moveTo(270, 920); ctx.lineTo(540, 420); ctx.stroke();
      // tatame emborrachado preto
      ctx.fillStyle = '#222736'; ctx.fillRect(-200, 1140, W + 400, 860);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1140); ctx.lineTo(W + 200, 1140); ctx.stroke();
      groundCracks(ctx, 480, 1240, 175);
      // Beto fazendo supino/desenvolvimento com um ELEFANTE adulto na barra!
      const feet = 1245, bs = 0.88;
      contactShadow(ctx, 480, feet, 98, 0.42);
      drawBeto(ctx, st, {
        x: 480, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_BOTH_UP,
        rim: { color: '#9BD6FF', dir: [0, -1] }
      });
      const barY = 892 + rep * 0.45;
      // barra de ferro envergando levemente + anilhas nas pontas
      ctx.strokeStyle = INK; ctx.lineWidth = 22; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(155, barY + 14); ctx.quadraticCurveTo(480, barY - 12, 805, barY + 14); ctx.stroke();
      ctx.strokeStyle = '#D2DCE8'; ctx.lineWidth = 10; ctx.stroke();
      for (const ax of [165, 198, 762, 795]) {
        rr(ctx, ax - 14, barY - 46, 28, 120, 8); outlined(ctx, '#2D3448', 6);
      }
      // ELEFANTE ADULTO equilibrado em cima da barra!
      drawElephant(ctx, 470, barY - 102, 1.05);
      pill(ctx, 215, 520, 190, 58, '#FFD400', null, '6 TONELADAS', INK, 30);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 7. DIA 9
  SC.dia9 = {
    times(S) { return { tArr: S.c('dia9', 'arremessa'), tCam: S.w('dia9', 'caminhão').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia9'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tArr, expr: 'scream' },
        { t: T.tCam, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tArr, T.tCam]; },
    hud(S, t) {
      const s0 = S.start('dia9');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia9', 'toneladas').t1, 6000, 25000);
      return { bar: { day: 9, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia9');
      const throwK = eOut(clamp((t - (T.tArr - 0.1)) / 1.4, 0, 1));
      const shake = hits(t, [{ t: T.tArr, a: 30, d: 0.5 }, { t: T.tCam, a: 22, d: 0.4 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#2B7BFF'], [0.55, '#9BD7FF'], [0.75, '#596378'], [1, '#2D3444']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tCam, 1.12, eBack]]), shake }, t);
      // rodovia e montanhas ao fundo
      ctx.beginPath(); ctx.moveTo(-150, 1120); ctx.lineTo(220, 860); ctx.lineTo(540, 1120); ctx.lineTo(860, 830); ctx.lineTo(1250, 1120); ctx.closePath();
      outlined(ctx, '#6885A8', 6);
      ctx.fillStyle = '#3C4457'; ctx.fillRect(-200, 1120, W + 400, 880);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1120); ctx.lineTo(W + 200, 1120); ctx.stroke();
      // arco de lancamento no ceu
      ctx.save(); ctx.setLineDash([22, 16]); ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 8;
      ctx.beginPath(); ctx.moveTo(260, 960); ctx.quadraticCurveTo(460, 480, 740, 560); ctx.stroke(); ctx.restore();
      // CAMINHAO CARREGADO girando pelo ar igual brinquedo!
      const tx = lerp(385, 650, throwK), ty = lerp(830, 595, Math.sin(throwK * Math.PI * 0.65));
      drawTruck(ctx, tx, ty, 0.88, -0.35 - throwK * 0.72);
      // Beto em pose de arremesso heroico na esquerda
      const feet = 1245, bs = 0.84;
      groundCracks(ctx, 240, feet, 145);
      contactShadow(ctx, 240, feet, 85, 0.4);
      drawBeto(ctx, st, {
        x: 240, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: t >= T.tArr - 0.1 ? THROW_FOLLOW : st.pose,
        rim: { color: '#FFE58A', dir: [0.8, -0.6] }
      });
      pill(ctx, 225, 495, 200, 58, '#FFD400', null, '25 TONELADAS', INK, 30);
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 8. DIA 12
  SC.dia12 = {
    times(S) { return { tAvi: S.c('dia12', 'avião'), tOmb: S.w('dia12', 'ombro').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia12'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tAvi, expr: 'determined' },
        { t: T.tOmb, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tAvi, T.tOmb]; },
    hud(S, t) {
      const s0 = S.start('dia12');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia12', 'toneladas').t1, 25000, 200000);
      return { bar: { day: 12, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia12');
      const shake = hits(t, [{ t: s0, a: 12, d: 0.3 }, { t: T.tAvi, a: 20, d: 0.4 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#1D64CC'], [0.5, '#89C8FF'], [0.7, '#586274'], [1, '#2B3242']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tOmb, 1.09]]), shake }, t);
      // torre de controle de aeroporto ao fundo esquerdo
      rr(ctx, 115, 790, 54, 340, 6); outlined(ctx, '#C5D1E2', 6);
      rr(ctx, 84, 730, 116, 68, 10); outlined(ctx, '#4B5E80', 6);
      ctx.fillStyle = '#9CE4FF'; ctx.fillRect(96, 744, 92, 32);
      // pista do aeroporto
      ctx.fillStyle = '#384052'; ctx.fillRect(-200, 1120, W + 400, 880);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1120); ctx.lineTo(W + 200, 1120); ctx.stroke();
      ctx.fillStyle = '#FFFFFF'; for (let rx = -120; rx < W + 150; rx += 190) { ctx.fillRect(rx, 1200, 105, 16); }
      groundCracks(ctx, 470, 1240, 210);
      // Beto equilibrando AVIAO COMERCIAL inteiro no ombro direito!
      const feet = 1245, bs = 0.86;
      contactShadow(ctx, 470, feet, 98, 0.42);
      drawBeto(ctx, st, {
        x: 470, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: SHOULDER_HOLD,
        rim: { color: '#BCE8FF', dir: [0, -1] }
      });
      const bob = Math.sin(t * 3.5) * 6;
      ctx.save(); ctx.translate(465, 735 + bob); ctx.rotate(Math.sin(t * 2.4) * 0.025);
      drawAirliner(ctx, 0, 0, 1.08);
      ctx.restore();
      pill(ctx, 235, 510, 215, 58, '#FFD400', null, '200 TONELADAS', INK, 30);
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 9. DIA 16
  SC.dia16 = {
    times(S) { return { tFog: S.c('dia16', 'foguete'), tDec: S.w('dia16', 'decolagem').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia16'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tFog, expr: 'focus' },
        { t: T.tDec, expr: 'scream' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tFog, T.tDec]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia16');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia16', 'toneladas').t1, 200000, 3000000);
      const alert = t >= T.tFog - 0.05;
      return {
        bar: { day: 16, dayT: s0, label: 'FORÇA', value: fmtForce(kg), alert },
        customHud: strengthGauge(kg, { alert }),
        alert: alert ? { text: 'EMPUXO MÁXIMO', t0: T.tFog - 0.05 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia16');
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: T.tDec, a: 30, d: 0.6 }]) + 7;
      fillScreen(ctx, vGrad(ctx, [[0, '#10142B'], [0.45, '#3E2338'], [0.78, '#A63A1F'], [1, '#2D1A1C']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tDec, 1.12]]), shake }, t);
      // torre de lancamento metalica a esquerda
      ctx.strokeStyle = '#6C7A94'; ctx.lineWidth = 10;
      ctx.strokeRect(110, 440, 95, 760);
      for (let y = 440; y < 1180; y += 95) {
        ctx.beginPath(); ctx.moveTo(110, y); ctx.lineTo(205, y + 95); ctx.moveTo(205, y); ctx.lineTo(110, y + 95); ctx.stroke();
      }
      // plataforma de concreto
      ctx.fillStyle = '#3A4050'; ctx.fillRect(-200, 1170, W + 400, 830);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1170); ctx.lineTo(W + 200, 1170); ctx.stroke();
      // nuvens incandescentes de plasma e fumaca escapando para os lados!
      const rx = 530, ry = 945 + Math.sin(t * 28) * 4;
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, rx, 1110, 320, 'rgba(255,150,40,A)', 0.62);
      ctx.restore();
      for (let i = 0; i < 16; i++) {
        const sd = i % 2 ? 1 : -1;
        const ph = (t * 2.8 + i * 0.13) % 1;
        ctx.fillStyle = ph < 0.35 ? `rgba(255,215,90,${(1 - ph) * 0.85})` : `rgba(255,120,45,${(1 - ph) * 0.65})`;
        ctx.beginPath(); ctx.arc(rx + sd * (40 + ph * 420), 1140 - Math.sin(ph * Math.PI) * 55, 36 + ph * 54, 0, Math.PI * 2); ctx.fill();
      }
      // FOGUETE ESPACIAL COLOSSAL vibrando no centro (enquadrado limpo abaixo de EMPUXO MAXIMO!)
      ctx.save(); ctx.translate(rx, ry); ctx.scale(0.76, 0.76);
      // chama dos propulsores
      ctx.beginPath(); ctx.moveTo(-55, 85); ctx.lineTo(0, 260 + Math.sin(t * 45) * 28); ctx.lineTo(55, 85); ctx.closePath();
      outlined(ctx, '#FF7A1A', 7);
      ctx.fillStyle = '#FFF5A0'; ctx.beginPath(); ctx.moveTo(-32, 85); ctx.lineTo(0, 195 + Math.cos(t * 42) * 18); ctx.lineTo(32, 85); ctx.closePath(); ctx.fill();
      // aletas
      ctx.beginPath(); ctx.moveTo(-66, -15); ctx.lineTo(-125, 92); ctx.lineTo(-66, 72); ctx.closePath(); outlined(ctx, '#E8322A', 8);
      ctx.beginPath(); ctx.moveTo(66, -15); ctx.lineTo(125, 92); ctx.lineTo(66, 72); ctx.closePath(); outlined(ctx, '#E8322A', 8);
      // corpo principal do foguete
      ctx.beginPath();
      ctx.moveTo(-66, 82); ctx.lineTo(-66, -280);
      ctx.quadraticCurveTo(-66, -405, 0, -455);
      ctx.quadraticCurveTo(66, -405, 66, -280);
      ctx.lineTo(66, 82); ctx.closePath();
      outlined(ctx, '#F4F7FC', 9);
      // nariz vermelho + faixas negras + escotilha
      ctx.beginPath(); ctx.moveTo(-48, -360); ctx.quadraticCurveTo(0, -455, 48, -360); ctx.closePath(); outlined(ctx, '#E8322A', 7);
      ctx.fillStyle = '#1E2538'; ctx.fillRect(-64, -95, 128, 34); ctx.fillRect(-64, 24, 128, 28);
      ctx.beginPath(); ctx.arc(0, -235, 32, 0, Math.PI * 2); outlined(ctx, '#6FE2FF', 7);
      ctx.restore();
      // Beto plantado no concreto segurando a base do foguete para baixo!
      const feet = 1252, bs = 0.82;
      groundCracks(ctx, 385, feet, 165);
      contactShadow(ctx, 385, feet, 88, 0.45);
      drawBeto(ctx, st, {
        x: 385, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: PUSH_RIGHT,
        rim: { color: '#FFB85C', dir: [1, -0.3] }, wind: [-95, 0]
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. DIA 20
  SC.dia20 = {
    times(S) { return { tPux: S.c('dia20', 'puxa'), tTit: S.w('dia20', 'Titanic').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia20'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tPux, expr: 'focus' },
        { t: T.tTit, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPux, T.tTit]; },
    hud(S, t) {
      const s0 = S.start('dia20');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia20', 'toneladas').t1, 3000000, 50000000);
      return { bar: { day: 20, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia20');
      const pullK = eOut(clamp((t - (s0 + 0.35)) / 1.8, 0, 1));
      const shake = hits(t, [{ t: T.tPux, a: 18, d: 0.4 }, { t: T.tTit, a: 26, d: 0.5 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#0C2D52'], [0.46, '#266C9E'], [0.68, '#0D4B7A'], [1, '#041C34']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [T.tTit, 1.1]]), shake }, t);
      // TITANIC erguido para fora das ondas!
      const shipY = lerp(1080, 815, pullK) + Math.sin(t * 2.5) * 10;
      drawTitanic(ctx, 595, shipY, 0.96, -0.22);
      // agua escorrendo do casco + ondas espumantes na frente
      ctx.fillStyle = vGrad(ctx, [[0, '#1674B8'], [1, '#062646']], 1040, H);
      ctx.beginPath(); ctx.moveTo(-200, 1085);
      for (let x = -200; x <= W + 240; x += 90) {
        ctx.quadraticCurveTo(x + 45, 1045 + Math.sin(t * 5 + x * 0.02) * 18, x + 90, 1085);
      }
      ctx.lineTo(W + 240, H + 100); ctx.lineTo(-200, H + 100); ctx.closePath();
      outlined(ctx, ctx.fillStyle, 6);
      // penhasco rochoso a esquerda onde Beto firma os pes
      ctx.beginPath(); ctx.moveTo(-180, 1020); ctx.lineTo(315, 1035); ctx.lineTo(385, H + 120); ctx.lineTo(-180, H + 120); ctx.closePath();
      outlined(ctx, '#4C5568', 7);
      // corrente metalica tensa ligando as maos do Beto a proa do Titanic!
      ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(242, 842); ctx.lineTo(372, shipY - 12); ctx.stroke();
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 8; ctx.setLineDash([18, 12]); ctx.stroke(); ctx.setLineDash([]);
      // Beto inclinado para tras puxando o Titanic!
      const feet = 1045, bs = 0.78;
      contactShadow(ctx, 185, feet, 75, 0.4);
      drawBeto(ctx, st, {
        x: 185, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: PULL_ROPE,
        rim: { color: '#7FE6FF', dir: [0.8, -0.5] }
      });
      pill(ctx, 250, 495, 225, 58, '#FFD400', null, 'TITANIC: 50 MIL t', INK, 28);
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. DIA 27
  SC.dia27 = {
    times(S) { return { tArr: S.c('dia27', 'arranca'), tPir: S.w('dia27', 'pirâmide').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia27'), pose: 'crouch_charge', expr: 'determined', dur: 0.01 },
        { t: T.tArr, expr: 'scream' },
        { t: T.tPir, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tArr, T.tPir]; },
    hud(S, t) {
      const s0 = S.start('dia27');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia27', 'toneladas').t1, 50e6, 6e9);
      return { bar: { day: 27, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia27');
      const liftK = eBack(clamp((t - (T.tArr - 0.05)) / 0.65, 0, 1));
      const shake = hits(t, [{ t: T.tArr, a: 28, d: 0.5 }, { t: T.tPir, a: 24, d: 0.45 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#C44722'], [0.45, '#F59B3B'], [0.7, '#F0C473'], [1, '#B37834']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tPir, 1.1]]), shake }, t);
      // sol gigante no deserto
      ctx.fillStyle = '#FFF0B8'; ctx.beginPath(); ctx.arc(230, 560, 115, 0, Math.PI * 2); ctx.fill();
      // dunas e segunda piramide distante
      ctx.beginPath(); ctx.moveTo(-120, 1130); ctx.lineTo(70, 910); ctx.lineTo(260, 1130); ctx.closePath();
      outlined(ctx, '#C8893E', 6);
      ctx.fillStyle = '#D99C4A'; ctx.fillRect(-200, 1120, W + 400, 880);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1120); ctx.lineTo(W + 200, 1120); ctx.stroke();
      groundCracks(ctx, 495, 1245, 225);
      // PIRAMIDE COLOSSAL DO EGITO (enquadrada limpa sobre as maos do Beto!)
      const py = lerp(975, 938, liftK) + Math.sin(t * 3.5) * 5;
      ctx.save(); ctx.translate(495, py);
      // cascata de areia caindo da base arrancada (atras do Beto!)
      for (let i = 0; i < 10; i++) {
        const sx = -240 + i * 54;
        const ph = (t * 2.5 + i * 0.19) % 1;
        ctx.fillStyle = `rgba(240,196,115,${(1 - ph) * 0.72})`;
        ctx.beginPath(); ctx.arc(sx, 20 + ph * 260, 12 + ph * 16, 0, Math.PI * 2); ctx.fill();
      }
      // face iluminada + face sombreada da piramide
      ctx.beginPath(); ctx.moveTo(0, -430); ctx.lineTo(-300, 0); ctx.lineTo(130, 0); ctx.closePath();
      outlined(ctx, '#F2BE5C', 8);
      ctx.beginPath(); ctx.moveTo(0, -430); ctx.lineTo(130, 0); ctx.lineTo(300, -18); ctx.closePath();
      outlined(ctx, '#B87C2E', 8);
      // blocos horizontais de pedra
      ctx.strokeStyle = 'rgba(70,40,10,0.45)'; ctx.lineWidth = 4;
      for (let k = 1; k < 7; k++) {
        const yy = -430 + k * 62;
        const frac = k / 7;
        ctx.beginPath(); ctx.moveTo(-300 * frac, yy); ctx.lineTo(130 * frac, yy); ctx.lineTo(300 * frac, yy - 18 * frac); ctx.stroke();
      }
      // ponta dourada no apice
      ctx.beginPath(); ctx.moveTo(0, -430); ctx.lineTo(-56, -350); ctx.lineTo(56, -352); ctx.closePath();
      outlined(ctx, '#FFE854', 6);
      ctx.restore();
      // Beto arrancando a Piramide de Gize acima da cabeca!
      const feet = 1248, bs = 0.78;
      contactShadow(ctx, 495, feet, 90, 0.42);
      drawBeto(ctx, st, {
        x: 495, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_BOTH_UP,
        rim: { color: '#FFE88A', dir: [0, -1] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 12. DIA 40
  SC.dia40 = {
    times(S) { return { tMon: S.c('dia40', 'montanha'), tJoe: S.w('dia40', 'joelho').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia40'), pose: 'idle', expr: 'determined', dur: 0.01 },
        { t: T.tMon, expr: 'smug' },
        { t: T.tJoe, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tMon, T.tJoe]; },
    hud(S, t) {
      const s0 = S.start('dia40');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia40', 'toneladas').t1, 6e9, 5e13);
      return { bar: { day: 40, dayT: s0, label: 'FORÇA', value: fmtForce(kg) }, customHud: strengthGauge(kg), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia40');
      const liftK = eOut(clamp((t - (s0 + 0.35)) / 1.2, 0, 1));
      const shake = hits(t, [{ t: T.tMon, a: 28, d: 0.55 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#141B3E'], [0.48, '#3B497D'], [0.76, '#6E668A'], [1, '#262338']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tJoe, 1.1]]), shake }, t);
      // nuvens passando pela montanha elevada
      for (const [cx, cy, r] of [[180, 560, 54], [760, 620, 46]]) {
        ctx.fillStyle = 'rgba(255,255,255,0.45)';
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.arc(cx + r * 0.9, cy + 8, r * 0.72, 0, Math.PI * 2); ctx.fill();
      }
      // solo rochoso
      ctx.fillStyle = '#2E3042'; ctx.fillRect(-200, 1160, W + 400, 840);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1160); ctx.lineTo(W + 200, 1160); ctx.stroke();
      groundCracks(ctx, 490, 1245, 240);
      // MONTANHA NEVADA COLOSSAL erguida inteira do chao!
      const my = lerp(975, 935, liftK) + Math.sin(t * 2.8) * 5;
      ctx.save(); ctx.translate(490, my);
      // pedregulhos soltando da base (atras do Beto!)
      for (let i = 0; i < 8; i++) {
        const bx = -240 + i * 68;
        const ph = (t * 2.2 + i * 0.23) % 1;
        ctx.fillStyle = '#5D657A'; ctx.beginPath(); ctx.arc(bx, 30 + ph * 220, 10 + (i % 3) * 5, 0, Math.PI * 2); ctx.fill();
      }
      // corpo da montanha com base irregular arrancada
      ctx.beginPath();
      ctx.moveTo(-340, -10); ctx.lineTo(-165, -310); ctx.lineTo(-75, -240);
      ctx.lineTo(15, -455); ctx.lineTo(145, -245); ctx.lineTo(220, -310); ctx.lineTo(340, -10);
      ctx.lineTo(220, 32); ctx.lineTo(95, 10); ctx.lineTo(0, 42); ctx.lineTo(-120, 12); ctx.lineTo(-245, 36);
      ctx.closePath();
      outlined(ctx, '#68738A', 8);
      // sombra direita do pico principal
      ctx.beginPath(); ctx.moveTo(15, -455); ctx.lineTo(145, -245); ctx.lineTo(220, -310); ctx.lineTo(340, -10); ctx.lineTo(30, 12); ctx.closePath();
      ctx.fillStyle = 'rgba(20,26,48,0.34)'; ctx.fill();
      // cume de neve brilhante
      ctx.beginPath();
      ctx.moveTo(15, -455); ctx.lineTo(-65, -320); ctx.lineTo(-15, -342); ctx.lineTo(25, -310); ctx.lineTo(68, -342); ctx.lineTo(106, -310); ctx.closePath();
      outlined(ctx, '#F7FAFF', 6);
      // pinheirinhos minusculos na encosta dando nocao de escala gigante!
      ctx.fillStyle = '#256B3D';
      for (const [px, py] of [[-230, -30], [-195, -52], [-155, -24], [175, -35], [220, -24], [255, -45]]) {
        ctx.beginPath(); ctx.moveTo(px, py - 34); ctx.lineTo(px - 14, py); ctx.lineTo(px + 14, py); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
      // Beto de joelhos retos levantando uma MONTANHA inteira!
      const feet = 1252, bs = 0.74;
      contactShadow(ctx, 490, feet, 85, 0.45);
      drawBeto(ctx, st, {
        x: 490, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: LIFT_BOTH_UP,
        rim: { color: '#C2DBFF', dir: [0, -1] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 13. DIA 70
  SC.dia70 = {
    times(S) { return { tLua: S.c('dia70', 'Lua'), tEmp: S.w('dia70', 'empurra').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia70'), pose: 'soar_spread', expr: 'determined', dur: 0.01 },
        { t: T.tLua, expr: 'focus' },
        { t: T.tEmp, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tLua, T.tEmp, S.c('dia70', 'órbita')]; },
    hud(S, t) {
      const s0 = S.start('dia70');
      const kg = HUD.roll(t, s0 + 0.08, S.w('dia70', 'Lua').t1, 5e13, 7.35e22);
      return {
        bar: { day: 70, dayT: s0, label: 'FORÇA', value: 'FORÇA LUNAR' },
        customHud: strengthGauge(kg, { cosmic: true }),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia70');
      const pushK = eOut(clamp((t - T.tEmp) / 1.4, 0, 1));
      const shake = hits(t, [{ t: T.tEmp, a: 26, d: 0.55 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#02040D'], [0.55, '#070F29'], [1, '#04091B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia70'), 1.1]]), shake }, t);
      // estrelas nitidas
      for (let i = 0; i < 85; i++) {
        ctx.fillStyle = `rgba(255,255,255,${0.35 + hash(i + 700) * 0.65})`;
        ctx.beginPath(); ctx.arc(hash(i + 701) * W, 240 + hash(i + 702) * 1240, 1.5 + hash(i) * 3.5, 0, Math.PI * 2); ctx.fill();
      }
      // arco azul da Terra la embaixo no fundo
      ctx.beginPath(); ctx.arc(240, 1650, 520, 0, Math.PI * 2);
      const eg = ctx.createRadialGradient(240, 1520, 80, 240, 1650, 540);
      eg.addColorStop(0, '#59C7FF'); eg.addColorStop(0.7, '#1B66D1'); eg.addColorStop(1, '#082561');
      outlined(ctx, eg, 6);
      // linha pontilhada da orbita original da Lua
      ctx.save(); ctx.setLineDash([16, 14]); ctx.strokeStyle = 'rgba(127,240,255,0.55)'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.arc(240, 1650, 870, -1.35, -0.45); ctx.stroke(); ctx.restore();
      // LUA COLOSSAL sendo empurrada para a direita fora de orbita!
      const moonX = lerp(635, 725, pushK), moonY = lerp(855, 815, pushK);
      ctx.save(); ctx.translate(moonX, moonY);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 0, 0, 310, 'rgba(180,220,255,A)', 0.25);
      ctx.restore();
      ctx.beginPath(); ctx.arc(0, 0, 215, 0, Math.PI * 2);
      const mg = ctx.createRadialGradient(-65, -65, 25, 0, 0, 225);
      mg.addColorStop(0, '#FFFFFF'); mg.addColorStop(0.55, '#CED6E3'); mg.addColorStop(1, '#798499');
      outlined(ctx, mg, 9);
      // crateras separadas (beginPath individual!)
      for (const [cx, cy, cr] of [[-70, -55, 42], [65, -35, 34], [-25, 75, 48], [88, 68, 24], [-115, 32, 22]]) {
        ctx.beginPath(); ctx.arc(cx, cy, cr, 0, Math.PI * 2); outlined(ctx, '#A8B3C4', 5);
      }
      ctx.restore();
      // ondas de empuxo no ponto de contato entre a mao e a Lua!
      if (t >= T.tEmp - 0.1) {
        for (let k = 0; k < 3; k++) {
          const ph = (t * 2.5 + k * 0.33) % 1;
          ctx.strokeStyle = `rgba(127,240,255,${(1 - ph) * 0.85})`; ctx.lineWidth = 7;
          ctx.beginPath(); ctx.arc(moonX - 205, moonY, 35 + ph * 115, -0.8, 0.8); ctx.stroke();
        }
      }
      // Beto flutuando no espaco empurrando a Lua!
      drawBeto(ctx, st, {
        x: moonX - 310, y: moonY + 28 + Math.sin(t * 2.2) * 10, scale: 0.84, t,
        pose: PUSH_RIGHT,
        rim: { color: '#7FF0FF', dir: [1, -0.3] }
      });
      pill(ctx, 255, 450, 245, 62, 'rgba(8,18,45,0.92)', '#7FF0FF', 'FORA DE ÓRBITA', '#7FF0FF', 32);
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 14. TWIST A
  SC.twist_a = {
    keys(S) {
      return [
        { t: S.start('twist_a'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('twist_a', 'detalhe'), expr: 'shock' },
        { t: S.c('twist_a', 'contou'), pose: 'shock_closeup', expr: 'panic', dur: 0.28 }
      ];
    },
    ev(S) { return [S.c('twist_a', 'detalhe'), S.c('twist_a', 'contou'), S.seg('twist_a').t1]; },
    hud() {
      return {
        bar: { day: 70, dayT: -9, label: 'FORÇA', value: 'FORÇA LUNAR' },
        customHud: strengthGauge(7.35e22, { cosmic: true }),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), tDet = S.c('twist_a', 'detalhe'), tEnd = S.seg('twist_a').t1;
      const z = kf(t, [[s0, 1.12], [tDet, 1.38], [tEnd, 1.24]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#040610'], [0.55, '#131630'], [1, '#060712']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 920, z, shake: 2.5 }, t);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 540, 820, 480, 'rgba(255,190,80,A)', 0.25);
      ctx.restore();
      drawBeto(ctx, st, { x: 540, y: 960, scale: 1.06, t, rim: { color: '#FFD466', dir: [0, -1] } });
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
    times(S) {
      return {
        tPal: S.c('twist_b', 'palmas'),
        tOnd: S.c('twist_b', 'onda'),
        tPar: S.w('twist_b', 'parte').t0
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('twist_b'), pose: 'idle', expr: 'shock', dur: 0.01 },
        { t: T.tPal, expr: 'scream' },
        { t: T.tOnd, pose: 'freefall_scream', expr: 'scream', dur: 0.14 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPal, T.tOnd, T.tPar]; },
    hud(S, t) {
      const T = this.times(S), splitNow = t >= T.tOnd;
      return {
        bar: { day: 70, dayT: -9, label: splitNow ? 'PLANETA' : 'IMPACTO', value: splitNow ? 'PARTIDO AO MEIO' : 'ONDA DE CHOQUE', alert: true },
        customHud: strengthGauge(7.35e22, { alert: true }),
        alert: { text: splitNow ? 'PLANETA PARTIDO' : 'ONDA DE CHOQUE', t0: splitNow ? T.tOnd : S.start('twist_b') }
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('twist_b');
      if (t < T.tOnd) {
        // Beat 1: Beto bate palmas sem querer -> onda de choque dourada!
        const clapK = eBack(clamp((t - T.tPal) / 0.16, 0, 1));
        const pose = B.mixObj(CLAP_OPEN, CLAP_SHUT, clamp(clapK, 0, 1));
        const shake = hits(t, [{ t: s0, a: 20, d: 0.35 }, { t: T.tPal, a: 45, d: 0.6 }]) + 4;
        fillScreen(ctx, vGrad(ctx, [[0, '#1C090C'], [0.5, '#4A1219'], [1, '#17070D']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 920, z: lerp(1.08, 1.24, clamp((t - s0) / 2.0, 0, 1)), shake }, t);
        if (t >= T.tPal - 0.04) {
          const wave = clamp((t - T.tPal) / 0.75, 0, 1);
          ctx.save(); ctx.globalCompositeOperation = 'lighter';
          glow(ctx, 540, 880, 160 + wave * 640, 'rgba(255,220,110,A)', (1 - wave * 0.6) * 0.75);
          ctx.restore();
          for (let r = 0; r < 4; r++) {
            const rad = 80 + wave * 680 - r * 75;
            if (rad > 20) {
              ctx.strokeStyle = r % 2 ? '#FFFFFF' : '#FFD400';
              ctx.lineWidth = 14 - r * 2;
              ctx.globalAlpha = clamp(1 - wave * 0.7, 0.2, 1);
              ctx.beginPath(); ctx.arc(540, 880, rad, 0, Math.PI * 2); ctx.stroke();
            }
          }
          ctx.globalAlpha = 1;
        }
        drawBeto(ctx, st, {
          x: 540, y: 980, scale: 1.02, t, pose,
          rim: { color: '#FFE875', dir: [0, -1] }
        });
        ctx.restore();
        return;
      }
      // Beat 2: A ONDA DE CHOQUE PARTE O PLANETA TERRA NO MEIO!
      const age = t - T.tOnd;
      const split = eOut(clamp(age / 1.4, 0, 1));
      const shake = hits(t, [{ t: T.tOnd, a: 42, d: 0.7 }, { t: T.tPar, a: 38, d: 0.65 }]) + 7;
      fillScreen(ctx, vGrad(ctx, [[0, '#02020A'], [0.5, '#130721'], [1, '#040614']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: lerp(1.04, 1.18, split), shake }, t);
      // estrelas espaciais
      for (let i = 0; i < 65; i++) {
        ctx.fillStyle = 'rgba(255,255,255,0.65)';
        ctx.beginPath(); ctx.arc(hash(i + 2500) * W, 240 + hash(i + 2501) * 1240, 2 + hash(i) * 3, 0, Math.PI * 2); ctx.fill();
      }
      const ex = 510, ey = 875, er = 255, gap = 22 + split * 92;
      // feixe incandescente da onda de choque cortando o planeta (limpo abaixo do banner!)
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, ex, ey, 460, 'rgba(255,140,40,A)', 0.55);
      const beam = ctx.createLinearGradient(ex, ey - 375, ex, ey + 375);
      beam.addColorStop(0, 'rgba(255,230,120,0)'); beam.addColorStop(0.5, 'rgba(255,245,190,0.95)'); beam.addColorStop(1, 'rgba(255,120,40,0)');
      ctx.fillStyle = beam; ctx.fillRect(ex - 20, ey - 375, 40, 750);
      ctx.restore();
      // hemisferio esquerdo + hemisferio direito da Terra rachados com nucleo de magma!
      for (const sd of [-1, 1]) {
        ctx.save();
        ctx.translate(ex + sd * gap, ey);
        ctx.rotate(sd * (0.04 + split * 0.14));
        ctx.beginPath();
        if (sd < 0) {
          ctx.arc(0, 0, er, Math.PI * 0.5, Math.PI * 1.5);
          ctx.lineTo(14, -er * 0.45); ctx.lineTo(-14, 0); ctx.lineTo(12, er * 0.45);
        } else {
          ctx.arc(0, 0, er, -Math.PI * 0.5, Math.PI * 0.5);
          ctx.lineTo(-12, er * 0.45); ctx.lineTo(14, 0); ctx.lineTo(-14, -er * 0.45);
        }
        ctx.closePath();
        outlined(ctx, '#1E72DE', 9);
        // continentes verdes + nucleo de magma dentro da metade (clip)
        ctx.save(); ctx.clip();
        ctx.fillStyle = '#38B857';
        if (sd < 0) {
          ctx.beginPath(); ctx.ellipse(-115, -75, 85, 55, 0.3, 0, Math.PI * 2); ctx.fill();
          ctx.beginPath(); ctx.ellipse(-85, 85, 72, 90, -0.2, 0, Math.PI * 2); ctx.fill();
        } else {
          ctx.beginPath(); ctx.ellipse(105, -60, 95, 68, -0.2, 0, Math.PI * 2); ctx.fill();
          ctx.beginPath(); ctx.ellipse(90, 95, 65, 58, 0.3, 0, Math.PI * 2); ctx.fill();
        }
        // nucleo quente + manto alaranjado exposto na fenda
        const cg = ctx.createRadialGradient(0, 0, 12, 0, 0, 130);
        cg.addColorStop(0, '#FFF6A0'); cg.addColorStop(0.45, '#FF6A1A'); cg.addColorStop(0.85, '#B82518'); cg.addColorStop(1, 'rgba(184,37,24,0)');
        ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(0, 0, 135, 0, Math.PI * 2); ctx.fill();
        const mg = ctx.createLinearGradient(0, 0, -sd * 34, 0);
        mg.addColorStop(0, '#FFF08A'); mg.addColorStop(0.45, '#FF5C1A'); mg.addColorStop(1, 'rgba(255,90,20,0)');
        ctx.fillStyle = mg; ctx.fillRect(sd < 0 ? -34 : 0, -er, 34, er * 2);
        ctx.restore();
        ctx.restore();
      }
      // Beto minusculo flutuando em choque no canto inferior esquerdo!
      drawBeto(ctx, st, {
        x: 205, y: 1125 + Math.sin(t * 4) * 14, scale: 0.52, t,
        rot: -0.24, rim: { color: '#FFD466', dir: [1, -0.5] }
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
        { t: S.c('loop', 'Comenta'), pose: 'flex', expr: 'smug', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('loop', 'dia'), S.c('loop', 'você'), S.c('loop', 'Comenta')]; },
    hud(S) {
      const s0 = S.start('loop');
      return { bar: { day: '?', dayT: s0, label: 'SUA RESPOSTA', value: 'COMENTE' }, ruler: null, alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop'), tV = S.c('loop', 'você'), tCom = S.c('loop', 'Comenta');
      const z = kf(t, [[s0, 1.65], [s0 + 0.2, 1.95, eBack], [tV, 1.95], [tCom, 2.25, eBack], [s1, 2.55, eIn]]);
      const shake = hits(t, [{ t: s0, a: 28, d: 0.5 }, { t: tCom, a: 18, d: 0.3 }]) + 3;
      radialBurst(ctx, t, 540, 760, '#C4201B', '#730D14', 22, 0.36);
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
