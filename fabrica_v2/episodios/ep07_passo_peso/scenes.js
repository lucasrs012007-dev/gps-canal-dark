/*
 * ep07_passo_peso/scenes.js : Episodio 7 ("E se cada passo do Zeca dobrasse o peso dele?")
 * 12 cenarios originais de ritmo ultra-rapido (~63s) em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
 * Protagonista oficial do canal: Zeca (moletom vermelho).
 * Traz HUD de massa exponencial (70 KG -> 2,3 MI TON) com barra de gravidade em 10 blocos,
 * regua logaritmica vertical na borda direita e 12 cenarios comicos de alto impacto visual.
 * Contrato: funcao pura do tempo t. Zero estado mutavel, zero Math.random, zero emoji/travessao.
 */
(function (root) {
  'use strict';
  const W = 1080, H = 1920;
  const B = root.Beto, HUD = root.HUD;
  const INK = B.INK;

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
      if (t < b[0]) {
        const k = (t - a[0]) / Math.max(1e-6, b[0] - a[0]);
        return lerp(a[1], b[1], (b[2] || ef)(k));
      }
    }
    return pts[pts.length - 1][1];
  }
  function hits(t, list) {
    let a = 0;
    for (const h of list) {
      const k = (t - h.t) / h.d;
      if (k >= 0 && k < 1) a += h.a * (1 - k) * (1 - k);
    }
    return a;
  }
  function camApply(ctx, c, t) {
    const s = c.shake || 0;
    ctx.translate(W / 2 + s * vnoise(t * 26 + 3.1), H / 2 + s * vnoise(t * 26 + 17.7));
    ctx.rotate((c.r || 0) + s * 0.0012 * vnoise(t * 19 + 9.3));
    ctx.scale(c.z, c.z);
    ctx.translate(-c.x, -c.y);
  }
  function drawZeca(ctx, st, o) {
    B.draw(ctx, Object.assign({ pose: st.pose, expr: st.expr, blink: st.blinkBoost }, o));
  }
  const pelvisFromFeet = (feetY, s) => feetY - B.STAND_PELVIS * s;

  // ------------------------------------------------------- poses customizadas
  B.POSES.stomp_step = Object.assign({}, B.POSES.idle, {
    crouch: 14, lean: 12, head: 14, headDY: 4,
    ua_r: 72, la_r: 95, ua_l: -36, la_l: -18,
    th_r: 42, sh_r: -18, th_l: -22, sh_l: 16
  });
  B.POSES.statue_freeze = Object.assign({}, B.POSES.idle, {
    crouch: 0, lean: 0, head: 0,
    ua_r: 8, la_r: 4, ua_l: 8, la_l: 4,
    th_r: 2, sh_r: 0, th_l: 2, sh_l: 0, hand_r: 1, hand_l: 1
  });
  B.POSES.run_panic = Object.assign({}, B.POSES.idle, {
    crouch: 12, lean: 24, head: -8,
    ua_r: 118, la_r: 148, ua_l: -48, la_l: 22,
    th_r: 56, sh_r: -64, th_l: -42, sh_l: 52
  });
  B.POSES.meteor_drop = Object.assign({}, B.POSES.freefall_scream, {
    lean: 6, head: 16, ua_r: 142, la_r: 164, ua_l: 142, la_l: 164,
    th_r: 26, sh_r: 52, th_l: 22, sh_l: 64
  });

  const STOMP_STEP = 'stomp_step';
  const STATUE_FREEZE = 'statue_freeze';
  const RUN_PANIC = 'run_panic';
  const METEOR_DROP = 'meteor_drop';

  // -------------------------------------------------------- pinceis e helpers
  function vGrad(ctx, stops, y0, y1) {
    const g = ctx.createLinearGradient(0, y0 === undefined ? 0 : y0, 0, y1 === undefined ? H : y1);
    stops.forEach(s => g.addColorStop(s[0], s[1]));
    return g;
  }
  function fillScreen(ctx, style) { ctx.fillStyle = style; ctx.fillRect(-100, -100, W + 200, H + 200); }
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
  function pill(ctx, x, y, w, h, bg, borderCol, txt, txtCol, size) {
    ctx.save();
    rr(ctx, x - w / 2, y - h / 2, w, h, 18);
    outlined(ctx, bg, 6);
    if (borderCol) {
      ctx.strokeStyle = borderCol; ctx.lineWidth = 3;
      rr(ctx, x - w / 2 + 6, y - h / 2 + 6, w - 12, h - 12, 12); ctx.stroke();
    }
    label(ctx, txt, x, y + 2, size || 36, txtCol);
    ctx.restore();
  }
  function speedLines(ctx, cx, cy, count, innerR, outerR, col, alpha, rot) {
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot || 0);
    ctx.globalAlpha = alpha; ctx.strokeStyle = col; ctx.lineCap = 'round';
    for (let i = 0; i < count; i++) {
      const ang = (i / count) * Math.PI * 2 + hash(i * 11) * 0.12;
      const r0 = innerR + hash(i * 19) * 90;
      const r1 = outerR + hash(i * 23) * 140;
      ctx.lineWidth = 4 + (i % 3) * 3;
      ctx.beginPath();
      ctx.moveTo(Math.cos(ang) * r0, Math.sin(ang) * r0);
      ctx.lineTo(Math.cos(ang) * r1, Math.sin(ang) * r1);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ---------------------------------------- HUD custom (Peso do Zeca: 70kg -> 2,3 MI TON)
  const MASS_MARKS = [
    { kg: 70, txt: '70kg' },
    { kg: 1000, txt: '1t' },
    { kg: 100000, txt: '100t' },
    { kg: 10000000, txt: '10k t' },
    { kg: 2300000000, txt: '2 MI t' }
  ];
  function massColor(kg) {
    if (kg >= 2000000) return '#FF2E3B';
    if (kg >= 50000) return '#FF7A29';
    if (kg >= 500) return '#FFD400';
    return '#2ED573';
  }
  function fmtWeight(kg) {
    if (kg < 1000) return Math.round(kg) + ' KG';
    const ton = kg / 1000;
    if (ton < 10) return HUD.fmtNum(ton, 1) + ' TON';
    if (ton < 10000) return HUD.fmtNum(Math.round(ton), 0) + ' TON';
    if (ton < 1000000) return HUD.fmtNum(Math.round(ton / 1000), 0) + ' MIL TON';
    return HUD.fmtNum(ton / 1000000, 1) + ' MI TON';
  }
  function weightHud(opts) {
    return function drawWeightHud(ctx, t) {
      const kg = Math.max(70, typeof opts.kg === 'function' ? opts.kg(t) : opts.kg);
      const isAlert = !!opts.alert || kg >= 2000000;
      const pulse = isAlert ? 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 2.6) : 0;

      // 1. PAINEL SUPERIOR (y=124, h=158, borda completa nos 4 lados)
      if (!opts.hideTop) {
        const y = 124, h = 158, padX = 24, gap = 22;
        const badgeTxt = opts.badge || 'PASSO 1';
        const labTxt = opts.label || 'PESO DO ZECA';
        const valTxt = opts.value !== undefined
          ? (typeof opts.value === 'function' ? opts.value(t) : opts.value)
          : fmtWeight(kg);

        ctx.save();
        ctx.font = `54px ${HUD.FONT_DISPLAY}`;
        const bw = Math.max(ctx.measureText('PASSO 25').width, ctx.measureText(badgeTxt).width) + 42;
        ctx.font = `30px ${HUD.FONT_DISPLAY}`;
        const lw = ctx.measureText(labTxt).width;
        ctx.font = `64px ${HUD.FONT_DISPLAY}`;
        const vw = Math.max(ctx.measureText(valTxt).width, 280);
        const rightW = Math.max(lw, vw, 310);
        const totalW = Math.min(960, padX + bw + gap + rightW + padX);
        const x = (W - totalW) / 2;

        rr(ctx, x, y, totalW, h, 28);
        ctx.fillStyle = 'rgba(11,15,25,0.86)'; ctx.fill();
        ctx.lineWidth = isAlert ? 6 : 4;
        ctx.strokeStyle = isAlert ? `rgba(255,46,59,${0.65 + 0.35 * pulse})` : 'rgba(255,255,255,0.88)';
        ctx.stroke();

        // selo esquerdo com pop
        const pk = clamp((t - (opts.badgeT || -9)) / 0.26, 0, 1);
        const ps = pk < 1 ? 0.65 + 0.35 * eBack(pk) : 1;
        const bx = x + padX, by = y + 20, bh = h - 40;
        ctx.save();
        ctx.translate(bx + bw / 2, by + bh / 2); ctx.scale(ps, ps);
        rr(ctx, -bw / 2, -bh / 2, bw, bh, 18);
        ctx.fillStyle = opts.badgeCol || (isAlert ? '#FF2E3B' : '#FFD400'); ctx.fill();
        ctx.lineWidth = 4; ctx.strokeStyle = INK; ctx.stroke();
        ctx.fillStyle = isAlert && !opts.badgeCol ? '#FFFFFF' : INK;
        ctx.font = `52px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(badgeTxt, 0, 3);
        ctx.restore();

        // coluna direita: rotulo + valor + barra logaritmica de massa em 10 blocos
        const rx = bx + bw + gap;
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        ctx.font = `28px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? '#FF8A92' : '#A9BCE0';
        ctx.fillText(labTxt, rx, y + 40);

        ctx.font = `62px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? (pulse > 0.5 ? '#FFFFFF' : '#FFD0D4') : '#FFFFFF';
        ctx.fillText(valTxt, rx, y + 104);

        const segs = 10, segGap = 6, barW = rightW - 6, segW = (barW - segGap * (segs - 1)) / segs;
        const barY = y + 122, barH = 18;
        const lMin = Math.log10(70), lMax = Math.log10(2350000000);
        const normM = clamp((Math.log10(kg) - lMin) / (lMax - lMin), 0, 1);
        const activeCount = Math.max(1, Math.round(normM * segs));
        for (let i = 0; i < segs; i++) {
          const sx = rx + i * (segW + segGap);
          const col = i < 3 ? '#2ED573' : (i < 6 ? '#FFD400' : (i < 8 ? '#FF7A29' : '#FF2E3B'));
          rr(ctx, sx, barY, segW, barH, 4);
          ctx.fillStyle = i < activeCount ? col : 'rgba(255,255,255,0.14)';
          ctx.fill();
        }
        ctx.restore();
      }

      // 2. REGUA LOGARITMICA VERTICAL DE PESO (borda direita x=1012, y=420..1080)
      if (!opts.hideGauge) {
        const x = 1012, y0 = 1080, y1 = 420;
        const lMin = Math.log10(70), lMax = Math.log10(2500000000);
        const yOf = v => y0 - ((clamp(Math.log10(Math.max(70, v)), lMin, lMax) - lMin) / (lMax - lMin)) * (y0 - y1);
        const vib = (opts.vibrate && kg >= 500) ? vnoise(t * 46) * clamp(Math.log10(kg / 100), 1, 6.5) : 0;

        ctx.save();
        ctx.translate(vib, 0);
        rr(ctx, x - 14, y1 - 24, 28, y0 - y1 + 48, 14);
        ctx.fillStyle = 'rgba(11,15,25,0.78)'; ctx.fill();
        ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.82)'; ctx.stroke();

        const ym = yOf(kg);
        const fillH = Math.max(4, y0 + 10 - ym);
        rr(ctx, x - 7, ym, 14, fillH, 7);
        ctx.fillStyle = massColor(kg); ctx.fill();

        ctx.font = `22px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (const mk of MASS_MARKS) {
          const yy = yOf(mk.kg);
          ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
          ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
          ctx.strokeText(mk.txt, x - 32, yy + 1);
          ctx.fillStyle = mk.kg >= 10000000 ? '#FF6B6B' : 'rgba(255,255,255,0.96)';
          ctx.fillText(mk.txt, x - 32, yy + 1);
        }

        // losango indicador
        ctx.save(); ctx.translate(x, ym);
        ctx.beginPath(); ctx.moveTo(0, -18); ctx.lineTo(18, 0); ctx.lineTo(0, 18); ctx.lineTo(-18, 0); ctx.closePath();
        ctx.fillStyle = massColor(kg); ctx.fill();
        ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
        ctx.restore();
        ctx.restore();
      }
    };
  }

  // ------------------------------------------------ props e efeitos 2D tematicos
  /** Ondas de choque sismicas no chao. */
  function drawImpactRings(ctx, x, y, t, tStart, col, maxR) {
    const dt = t - tStart;
    if (dt < 0 || dt > 1.2) return;
    ctx.save();
    for (let i = 0; i < 3; i++) {
      const local = dt - i * 0.09;
      if (local < 0) continue;
      const r = 30 + local * (maxR || 760);
      if (r > (maxR || 760)) continue;
      const a = clamp(1 - r / (maxR || 760), 0, 1);
      ctx.globalAlpha = a * 0.9;
      ctx.beginPath(); ctx.ellipse(x, y, r, r * 0.24, 0, 0, Math.PI * 2);
      ctx.lineWidth = 14; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 7; ctx.strokeStyle = i % 2 === 0 ? (col || '#FFD400') : '#FFFFFF'; ctx.stroke();
    }
    ctx.restore();
  }

  /** Rachaduras radiais no piso ou asfalto. */
  function drawCracks(ctx, x, y, radius, k, glowCol) {
    if (k <= 0.01) return;
    ctx.save();
    ctx.translate(x, y);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const rays = 8;
    for (let i = 0; i < rays; i++) {
      const ang = (i / rays) * Math.PI * 2 + hash(i * 19) * 0.35;
      const len = radius * k * (0.65 + 0.35 * hash(i * 29));
      const midX = Math.cos(ang + 0.14) * len * 0.52;
      const midY = Math.sin(ang + 0.14) * len * 0.22;
      const endX = Math.cos(ang) * len;
      const endY = Math.sin(ang) * len * 0.32;
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(midX, midY); ctx.lineTo(endX, endY);
      ctx.strokeStyle = INK; ctx.lineWidth = 11; ctx.stroke();
      if (glowCol) {
        ctx.strokeStyle = glowCol; ctx.lineWidth = 4; ctx.stroke();
      }
    }
    ctx.restore();
  }

  /** Planeta Terra rachando sob o peso do Zeca (Hook). */
  function drawEarthGlobe(ctx, cx, cy, r, crackK, t) {
    ctx.save(); ctx.translate(cx, cy);
    glow(ctx, 0, 0, r * 1.35, 'rgba(56,189,248,A)', 0.32);
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); outlined(ctx, '#0284C7', 9);
    ctx.save(); ctx.beginPath(); ctx.arc(0, 0, r - 4, 0, Math.PI * 2); ctx.clip();
    // continentes estilizados
    ctx.fillStyle = '#22C55E'; ctx.strokeStyle = INK; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.ellipse(-r * 0.35, -r * 0.22, r * 0.36, r * 0.24, -0.3, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(r * 0.38, r * 0.12, r * 0.32, r * 0.38, 0.25, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(-r * 0.18, r * 0.48, r * 0.26, r * 0.18, 0.1, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    // rachaduras de magma descendo do polo norte
    if (crackK > 0.02) {
      const pulse = 0.75 + 0.25 * Math.sin(t * 22);
      ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.lineCap = 'round';
      for (const path of [
        [[0, -r], [-28, -r * 0.55], [16, -r * 0.18], [-22, r * 0.22], [8, r * 0.65]],
        [[0, -r], [48, -r * 0.62], [88, -r * 0.22], [120, r * 0.12]],
        [[0, -r], [-66, -r * 0.58], [-115, -r * 0.15]]
      ]) {
        ctx.beginPath();
        const maxIdx = Math.max(1, Math.floor(crackK * (path.length - 1)));
        ctx.moveTo(path[0][0], path[0][1]);
        for (let i = 1; i <= maxIdx; i++) ctx.lineTo(path[i][0], path[i][1]);
        ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.stroke();
        ctx.strokeStyle = `rgba(255,${Math.round(120 + 90 * pulse)},20,1)`; ctx.lineWidth = 8; ctx.stroke();
      }
    }
    ctx.restore();
    ctx.restore();
  }

  /** Vizinho assustado de pijama no andar de baixo. */
  function drawNeighbor(ctx, x, y, s, panic) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    // pernas e corpo de pijama azul listrado
    rr(ctx, -46, -42, 92, 102, 22); outlined(ctx, '#60A5FA', 7);
    ctx.strokeStyle = '#1D4ED8'; ctx.lineWidth = 5;
    for (const sx of [-24, 0, 24]) {
      ctx.beginPath(); ctx.moveTo(sx, -38); ctx.lineTo(sx, 56); ctx.stroke();
    }
    // bracos levantados em susto
    ctx.strokeStyle = INK; ctx.lineWidth = 26; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(-42, -20); ctx.lineTo(-82, panic ? -74 : 18);
    ctx.moveTo(42, -20); ctx.lineTo(82, panic ? -74 : 18);
    ctx.stroke();
    ctx.strokeStyle = '#60A5FA'; ctx.lineWidth = 15;
    ctx.beginPath();
    ctx.moveTo(-42, -20); ctx.lineTo(-82, panic ? -74 : 18);
    ctx.moveTo(42, -20); ctx.lineTo(82, panic ? -74 : 18);
    ctx.stroke();
    // cabeca + touca/cabelo despenteado
    ctx.beginPath(); ctx.arc(0, -92, 48, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 7);
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.arc(side * 18, -96, panic ? 14 : 10, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
      ctx.beginPath(); ctx.arc(side * 18, -98, 4.5, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
    }
    // bigode + boca aberta em choque
    ctx.beginPath(); ctx.ellipse(0, -68, panic ? 18 : 12, panic ? 16 : 6, 0, 0, Math.PI * 2);
    outlined(ctx, '#5E1117', 5);
    ctx.restore();
  }

  /** Onibus urbano brasileiro dobrando em V no meio! */
  function drawBendingBus(ctx, cx, cy, bendK) {
    const ang = bendK * 0.44;
    const dropY = bendK * 74;
    ctx.save(); ctx.translate(cx, cy + dropY);

    // metade esquerda do onibus inclinada para cima na esquerda
    ctx.save(); ctx.rotate(-ang);
    rr(ctx, -350, -145, 355, 165, 22); outlined(ctx, '#FACC15', 8);
    ctx.fillStyle = '#1D4ED8'; ctx.fillRect(-344, -46, 344, 34);
    for (const wx of [-315, -215, -115]) {
      rr(ctx, wx, -124, 80, 66, 10); outlined(ctx, '#BAE6FD', 5);
    }
    // roda esquerda
    ctx.beginPath(); ctx.arc(-240, 22, 44, 0, Math.PI * 2); outlined(ctx, '#1F2937', 7);
    ctx.beginPath(); ctx.arc(-240, 22, 18, 0, Math.PI * 2); outlined(ctx, '#CBD5E1', 5);
    ctx.restore();

    // metade direita do onibus inclinada para cima na direita
    ctx.save(); ctx.rotate(ang);
    rr(ctx, -5, -145, 355, 165, 22); outlined(ctx, '#FACC15', 8);
    ctx.fillStyle = '#1D4ED8'; ctx.fillRect(0, -46, 344, 34);
    for (const wx of [35, 135, 235]) {
      rr(ctx, wx, -124, 80, 66, 10); outlined(ctx, '#BAE6FD', 5);
    }
    // farol frontal direito
    rr(ctx, 326, -42, 22, 34, 6); outlined(ctx, '#FFFFFF', 4);
    // roda direita
    ctx.beginPath(); ctx.arc(240, 22, 44, 0, Math.PI * 2); outlined(ctx, '#1F2937', 7);
    ctx.beginPath(); ctx.arc(240, 22, 18, 0, Math.PI * 2); outlined(ctx, '#CBD5E1', 5);
    ctx.restore();

    // faiscas e estalo metalico na dobra central
    if (bendK > 0.1) {
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 7; ctx.lineCap = 'round';
      for (let i = 0; i < 6; i++) {
        const a = -Math.PI + (i / 5) * Math.PI;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * 28, -20 + Math.sin(a) * 28);
        ctx.lineTo(Math.cos(a) * 78, -20 + Math.sin(a) * 78);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  /** Carro compacto cartoon com ondas de alarme piscando. */
  function drawCar(ctx, x, y, s, rot, col, alarmOn, t) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    // chassi
    rr(ctx, -86, -34, 172, 56, 18); outlined(ctx, col || '#3B82F6', 6);
    // teto + janelas
    ctx.beginPath();
    ctx.moveTo(-54, -34); ctx.lineTo(-34, -76); ctx.lineTo(36, -76); ctx.lineTo(58, -34); ctx.closePath();
    outlined(ctx, col || '#3B82F6', 6);
    rr(ctx, -38, -68, 34, 30, 6); outlined(ctx, '#BAE6FD', 4);
    rr(ctx, 4, -68, 34, 30, 6); outlined(ctx, '#BAE6FD', 4);
    // rodas
    for (const rx of [-50, 50]) {
      ctx.beginPath(); ctx.arc(rx, 24, 22, 0, Math.PI * 2); outlined(ctx, '#111827', 5);
      ctx.beginPath(); ctx.arc(rx, 24, 9, 0, Math.PI * 2); outlined(ctx, '#E2E8F0', 3);
    }
    // farol + ondas de alarme
    if (alarmOn) {
      const blink = Math.sin((t || 0) * 28) > 0;
      if (blink) {
        glow(ctx, 84, -12, 42, 'rgba(255,212,0,A)', 0.85);
        ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 6; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.arc(0, -86, 26, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
        ctx.beginPath(); ctx.arc(0, -86, 44, Math.PI * 1.2, Math.PI * 1.8); ctx.stroke();
      }
    }
    ctx.restore();
  }

  /** Barata voadora cartoon (o terror absoluto do Zeca!). */
  function drawCockroach(ctx, x, y, s, rot, flying, t) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    const flap = flying ? Math.sin((t || 0) * 58) * 0.55 : 0.08;
    // perninhas articuladas
    ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.lineCap = 'round';
    for (const side of [-1, 1]) {
      for (const py of [-14, 4, 22]) {
        ctx.beginPath();
        ctx.moveTo(side * 16, py);
        ctx.lineTo(side * 38, py - 8);
        ctx.lineTo(side * 46, py + 10);
        ctx.stroke();
      }
    }
    // asas abertas vibrando quando voa
    for (const side of [-1, 1]) {
      ctx.save(); ctx.translate(side * 6, -12); ctx.rotate(side * (0.32 + flap));
      ctx.beginPath(); ctx.ellipse(side * 22, 16, 18, 36, side * 0.2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(217,119,6,0.72)'; ctx.fill();
      ctx.lineWidth = 4; ctx.strokeStyle = INK; ctx.stroke();
      ctx.restore();
    }
    // casco marrom brilhante
    ctx.beginPath(); ctx.ellipse(0, 6, 24, 38, 0, 0, Math.PI * 2); outlined(ctx, '#7C2D12', 6);
    ctx.beginPath(); ctx.ellipse(0, -24, 15, 13, 0, 0, Math.PI * 2); outlined(ctx, '#5C1E0B', 5);
    // olhos brancos comicos
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.arc(side * 7, -28, 5, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 3);
      ctx.beginPath(); ctx.arc(side * 7, -29, 2, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
    }
    // antenas longas balancando
    const antW = Math.sin((t || 0) * 18) * 6;
    ctx.strokeStyle = INK; ctx.lineWidth = 4.5;
    ctx.beginPath();
    ctx.moveTo(-6, -34); ctx.quadraticCurveTo(-24, -62, -38 + antW, -72);
    ctx.moveTo(6, -34); ctx.quadraticCurveTo(24, -62, 38 - antW, -72);
    ctx.stroke();
    ctx.restore();
  }

  /** Balao de texto explosivo estilo quadrinho. */
  function drawBalloon(ctx, x, y, txt, scale, bgCol, txtCol) {
    if (scale <= 0.02) return;
    ctx.save(); ctx.translate(x, y); ctx.scale(scale, scale);
    ctx.font = `48px ${HUD.FONT_DISPLAY}`;
    const bw = ctx.measureText(txt).width + 64, bh = 84;
    rr(ctx, -bw / 2, -bh / 2, bw, bh, 22);
    outlined(ctx, bgCol || '#FFD400', 7);
    label(ctx, txt, 0, 3, 44, txtCol || INK);
    ctx.restore();
  }

  // ============================================================== 12 CENAS
  const SC = {};

  // ----------------------------------------------------------------- 1. HOOK
  SC.hook = {
    keys(S) {
      return [
        { t: S.start('hook'), pose: STOMP_STEP, expr: 'curious', dur: 0.14, ease: 'back' },
        { t: S.c('hook', 'afunda'), pose: 'land', expr: 'shock', dur: 0.12, ease: 'back' },
        { t: S.c('hook', 'Terra'), pose: 'freefall_scream', expr: 'panic', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('hook', 'passo'), S.c('hook', 'Zeca'), S.c('hook', 'afunda'), S.c('hook', 'Terra')]; },
    hud(S) {
      const s0 = S.start('hook'), tAfu = S.c('hook', 'afunda'), tTer = S.c('hook', 'Terra');
      return {
        bar: null, ruler: null,
        alert: { t0: tAfu, text: 'MASSA FORA DE CONTROLE!' },
        customHud: weightHud({
          badge: 'ZECA', badgeT: s0,
          label: 'PESO DO ZECA',
          kg: t => t < tAfu ? 70 : HUD.roll(t, tAfu, tTer + 0.5, 70, 2300000000),
          alert: false, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('hook'), s1 = S.end('hook');
      const tAfu = S.c('hook', 'afunda'), tTer = S.c('hook', 'Terra');
      const hit = t >= tAfu;
      const shake = hits(t, [{ t: tAfu, a: 38, d: 0.55 }, { t: tTer, a: 34, d: 0.6 }]) + (hit ? 8 : 0);

      fillScreen(ctx, vGrad(ctx, [[0, '#020617'], [0.55, '#0F172A'], [1, '#1E1B4B']]));
      // estrelas no espaco
      ctx.fillStyle = '#FFFFFF';
      for (let i = 0; i < 36; i++) {
        const sx = hash(i * 17) * W, sy = hash(i * 29) * 1450;
        ctx.globalAlpha = 0.35 + 0.55 * hash(i * 41);
        ctx.beginPath(); ctx.arc(sx, sy, 2 + hash(i * 53) * 3, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;

      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tAfu, 1.18, eBack], [s1, 1.06]]), shake }, t);

      if (hit) speedLines(ctx, 510, 950, 32, 200, 1100, '#FF7A29', 0.45, t * 1.4);

      // Planeta Terra afundando e rachando sob o passo do Zeca
      const crackK = clamp((t - tAfu) / 0.65, 0, 1);
      const earthY = 1090 + crackK * 65;
      drawEarthGlobe(ctx, 510, earthY, 265, crackK, t);

      // Zeca pisando no topo do planeta
      const zY = pelvisFromFeet(earthY - 245, 0.92);
      drawZeca(ctx, st, { x: 510, y: zY, scale: 0.92, t, rim: { color: hit ? '#FF7A29' : '#38BDF8', dir: [0, -1] } });
      drawImpactRings(ctx, 510, earthY - 245, t, tAfu, '#FFD400', 540);
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 2. REGRA
  SC.regra = {
    keys(S) {
      return [
        { t: S.start('regra'), pose: 'point_hook', expr: 'amazed', dur: 0.16, ease: 'back' },
        { t: S.c('regra', 'quilos'), pose: 'flex', expr: 'smug', dur: 0.16, ease: 'back' },
        { t: S.c('regra', 'dobra'), pose: STOMP_STEP, expr: 'shock', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('regra', 'Zeca'), S.c('regra', 'quilos'), S.c('regra', 'passo'), S.c('regra', 'dobra')]; },
    hud(S) {
      const s0 = S.start('regra'), tDob = S.c('regra', 'dobra');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'ZECA', badgeT: s0, badgeCol: '#2ED573',
          label: 'PESO INICIAL',
          kg: t => t < tDob ? 70 : HUD.roll(t, tDob, tDob + 0.4, 70, 140)
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('regra'), s1 = S.end('regra');
      const tDob = S.c('regra', 'dobra');

      fillScreen(ctx, vGrad(ctx, [[0, '#1E293B'], [0.6, '#334155'], [1, '#0F172A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tDob, 1.12, eBack], [s1, 1.04]]), shake: hits(t, [{ t: tDob, a: 20, d: 0.3 }]) }, t);

      ctx.fillStyle = '#0F172A'; ctx.fillRect(-100, 1215, W + 200, 800);

      // balanca digital estilizada sob os pes do Zeca
      rr(ctx, 355, 1185, 310, 48, 14); outlined(ctx, '#E2E8F0', 7);
      rr(ctx, 435, 1196, 150, 26, 6); outlined(ctx, '#0B0F19', 4);
      label(ctx, t < tDob ? '70 KG' : '140 KG', 510, 1210, 22, '#2ED573');

      // cracha de apresentacao "ZECA" + regra carimbada
      pill(ctx, 510, 465, 520, 88, '#0B0F19', '#FFD400', t < tDob ? 'ESSE É O ZECA!' : '1 PASSO = PESO x2', '#FFD400', 44);

      drawZeca(ctx, st, { x: 510, y: pelvisFromFeet(1188, 1.12), scale: 1.12, t, rim: { color: '#FFD400', dir: [-0.7, -0.7] } });
      if (t >= tDob) {
        drawCracks(ctx, 510, 1218, 165, clamp((t - tDob) / 0.25, 0, 1));
        drawImpactRings(ctx, 510, 1210, t, tDob, '#FFD400', 380);
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 3. PASSO 1 (140 KG - QUARTO + CHINELO)
  SC.passo1 = {
    keys(S) {
      return [
        { t: S.start('passo1'), pose: 'idle', expr: 'neutral', dur: 0.14, ease: 'inout' },
        { t: S.c('passo1', 'chinelo'), pose: STOMP_STEP, expr: 'curious', dur: 0.14, ease: 'back' },
        { t: S.c('passo1', 'trinca'), pose: 'look_down', expr: 'shock', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo1', 'cama'), S.c('passo1', 'chinelo'), S.c('passo1', 'trinca'), S.c('passo1', 'piso')]; },
    hud(S) {
      const s0 = S.start('passo1'), tTri = S.c('passo1', 'trinca');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'PASSO 1', badgeT: s0, badgeCol: '#2ED573',
          label: 'PESO DO ZECA',
          kg: t => HUD.roll(t, s0, tTri, 70, 140)
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo1'), s1 = S.end('passo1');
      const tTri = S.c('passo1', 'trinca');

      fillScreen(ctx, vGrad(ctx, [[0, '#312E81'], [0.6, '#4338CA'], [1, '#1E1B4B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tTri, 1.14, eBack], [s1, 1.08]]), shake: hits(t, [{ t: tTri, a: 26, d: 0.35 }]) }, t);

      // piso de ceramica quadriculada do quarto
      ctx.fillStyle = '#E2E8F0'; ctx.fillRect(-100, 1170, W + 200, 800);
      ctx.strokeStyle = '#94A3B8'; ctx.lineWidth = 4;
      for (let gx = -40; gx <= W + 40; gx += 110) {
        ctx.beginPath(); ctx.moveTo(gx, 1170); ctx.lineTo(gx - 80, 1480); ctx.stroke();
      }
      ctx.beginPath(); ctx.moveTo(-100, 1170); ctx.lineTo(W + 100, 1170); ctx.stroke();

      // cama aconchegante a esquerda
      rr(ctx, 50, 860, 320, 320, 18); outlined(ctx, '#7C2D12', 7);
      rr(ctx, 64, 980, 292, 130, 16); outlined(ctx, '#38BDF8', 6);
      rr(ctx, 84, 930, 110, 62, 18); outlined(ctx, '#F8FAFC', 6); // travesseiro

      // chinelo azul no chao ao lado do pe do Zeca
      const fx = 570;
      ctx.beginPath(); ctx.ellipse(fx + 22, 1218, 42, 15, 0, 0, Math.PI * 2); outlined(ctx, '#2563EB', 5);
      // rachadura explodindo sob o chinelo
      const crk = clamp((t - tTri) / 0.25, 0, 1);
      drawCracks(ctx, fx, 1215, 240, crk);
      drawImpactRings(ctx, fx, 1215, t, tTri, '#FFD400', 420);

      contactShadow(ctx, fx, 1220, 126, 0.3);
      drawZeca(ctx, st, { x: fx, y: pelvisFromFeet(1218, 1.08), scale: 1.08, t, rim: { color: '#FDE047', dir: [-0.8, -0.5] } });

      if (t >= tTri) {
        drawBalloon(ctx, 560, 560, 'CREEEEC!!', eBack(clamp((t - tTri) / 0.16, 0, 1)), '#FFD400', '#0B0F19');
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 4. PASSO 3 (560 KG - CAI NO VIZINHO!)
  SC.passo3 = {
    keys(S) {
      return [
        { t: S.start('passo3'), pose: STOMP_STEP, expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('passo3', 'cai'), pose: 'freefall_scream', expr: 'panic', dur: 0.12, ease: 'back' },
        { t: S.c('passo3', 'vizinho'), pose: 'land', expr: 'shock', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo3', 'chão'), S.c('passo3', 'racha'), S.c('passo3', 'cai'), S.c('passo3', 'vizinho')]; },
    hud(S) {
      const s0 = S.start('passo3'), tCai = S.c('passo3', 'cai');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'PASSO 3', badgeT: s0, badgeCol: '#FFD400',
          label: 'PESO DO ZECA',
          kg: t => HUD.roll(t, s0, tCai, 140, 560),
          vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo3'), s1 = S.end('passo3');
      const tRac = S.c('passo3', 'racha'), tCai = S.c('passo3', 'cai'), tViz = S.c('passo3', 'vizinho');
      const shake = hits(t, [{ t: tRac, a: 24, d: 0.3 }, { t: tViz, a: 34, d: 0.45 }]);

      fillScreen(ctx, vGrad(ctx, [[0, '#475569'], [0.45, '#64748B'], [1, '#1E293B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tCai, 1.06], [tViz, 1.14, eBack], [s1, 1.06]]), shake }, t);

      // corte de dois andares! Laje dividindo y = 780
      ctx.fillStyle = '#334155'; ctx.fillRect(-100, 380, W + 200, 400); // andar de cima
      ctx.fillStyle = '#FEF3C7'; ctx.fillRect(-100, 825, W + 200, 410); // sala do vizinho embaixo
      ctx.fillStyle = '#78350F'; ctx.fillRect(-100, 1215, W + 200, 720); // piso de madeira embaixo

      // laje de concreto quebrando no meio!
      const broken = t >= tCai;
      rr(ctx, -60, 775, broken ? 410 : 1200, 56, 8); outlined(ctx, '#94A3B8', 7);
      if (broken) {
        rr(ctx, 640, 775, 500, 56, 8); outlined(ctx, '#94A3B8', 7);
        // pedacos de reboco caindo
        for (let i = 0; i < 8; i++) {
          const dt = clamp((t - tCai) / 0.85, 0, 1);
          const rx = 380 + hash(i * 19) * 260;
          const ry = 805 + dt * (360 + hash(i * 31) * 140);
          rr(ctx, rx, ry, 34, 24, 6); outlined(ctx, '#CBD5E1', 4);
        }
      }

      // sofa + vizinho assustado a esquerda no andar de baixo
      rr(ctx, 110, 1085, 290, 130, 20); outlined(ctx, '#DC2626', 7);
      drawNeighbor(ctx, 250, 1075, 1.02, t >= tCai);

      // Zeca atravessando o teto e aterrissando na sala do vizinho!
      const zY = kf(t, [
        [s0, pelvisFromFeet(775, 0.86)],
        [tCai, pelvisFromFeet(775, 0.86)],
        [tViz, pelvisFromFeet(1215, 0.98), eIn],
        [s1, pelvisFromFeet(1215, 0.98)]
      ]);
      drawZeca(ctx, st, { x: 525, y: zY, scale: t >= tViz ? 0.98 : 0.88, t, rim: { color: '#FFD400', dir: [0, -1] } });
      drawImpactRings(ctx, 525, 1215, t, tViz, '#FFD400', 460);
      if (t >= tViz) {
        drawBalloon(ctx, 515, 520, 'OI VIZINHO!!', eBack(clamp((t - tViz) / 0.16, 0, 1)), '#FFFFFF', '#DC2626');
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 5. PASSO 6 (4,5 TON - ASFALTO MANTEIGA)
  SC.passo6 = {
    keys(S) {
      return [
        { t: S.start('passo6'), pose: STOMP_STEP, expr: 'focus', dur: 0.14, ease: 'back' },
        { t: S.c('passo6', 'afunda'), pose: 'look_down', expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('passo6', 'manteiga'), pose: 'shrug_question', expr: 'panic', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo6', 'pé'), S.c('passo6', 'afunda'), S.c('passo6', 'asfalto'), S.c('passo6', 'manteiga')]; },
    hud(S) {
      const s0 = S.start('passo6'), tAfu = S.c('passo6', 'afunda');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'PASSO 6', badgeT: s0, badgeCol: '#FFD400',
          label: 'PESO DO ZECA',
          kg: t => HUD.roll(t, s0, tAfu + 0.35, 560, 4500),
          vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo6'), s1 = S.end('passo6');
      const tAfu = S.c('passo6', 'afunda'), tMan = S.c('passo6', 'manteiga');

      fillScreen(ctx, vGrad(ctx, [[0, '#0284C7'], [0.55, '#7DD3FC'], [1, '#1E293B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tAfu, 1.15, eBack], [s1, 1.08]]), shake: hits(t, [{ t: tAfu, a: 28, d: 0.38 }]) }, t);

      // predios simples no horizonte da rua
      ctx.fillStyle = '#334155';
      for (const [bx, bw, bh] of [[60, 170, 420], [250, 150, 340], [670, 190, 450], [880, 160, 320]]) {
        rr(ctx, bx, 1080 - bh, bw, bh, 10); outlined(ctx, '#475569', 6);
      }

      // asfalto escuro com faixa amarela
      ctx.fillStyle = '#1E293B'; ctx.fillRect(-100, 1080, W + 200, 860);
      ctx.strokeStyle = '#FACC15'; ctx.lineWidth = 14; ctx.setLineDash([70, 45]);
      ctx.beginPath(); ctx.moveTo(-100, 1180); ctx.lineTo(W + 100, 1180); ctx.stroke();
      ctx.setLineDash([]);

      // Zeca afundando os pes no asfalto derretido
      const sinkK = clamp((t - tAfu) / 0.45, 0, 1);
      const sinkY = sinkK * 68;
      drawCracks(ctx, 515, 1210, 260, sinkK, '#F59E0B');
      drawZeca(ctx, st, { x: 515, y: pelvisFromFeet(1205, 1.06) + sinkY, scale: 1.06, t, rim: { color: '#FFD400', dir: [0, -1] } });

      // borda frontal de asfalto amassado cobrindo os tenis (efeito manteiga real!)
      if (sinkK > 0.05) {
        ctx.beginPath();
        ctx.ellipse(515, 1218, 125 + sinkK * 45, 34 + sinkK * 14, 0, 0, Math.PI);
        outlined(ctx, '#0F172A', 7);
        // gotas de asfalto subindo
        for (let i = 0; i < 6; i++) {
          const ang = -Math.PI + (i / 5) * Math.PI;
          const d = 80 + sinkK * 110;
          ctx.beginPath(); ctx.arc(515 + Math.cos(ang) * d, 1190 + Math.sin(ang) * d * 0.6, 12, 0, Math.PI * 2);
          outlined(ctx, '#1E293B', 4);
        }
      }
      if (t >= tMan) {
        pill(ctx, 510, 480, 450, 82, '#78350F', '#FFD400', 'ASFALTO = MANTEIGA!', '#FFD400', 40);
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 6. PASSO 10 (71 TON - BUSAO DOBRA NO MEIO!)
  SC.passo10 = {
    keys(S) {
      return [
        { t: S.start('passo10'), pose: STOMP_STEP, expr: 'curious', dur: 0.14, ease: 'back' },
        { t: S.c('passo10', 'dobra'), pose: 'shock_closeup', expr: 'scream', dur: 0.12, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo10', 'sobe'), S.c('passo10', 'ônibus'), S.c('passo10', 'busão'), S.c('passo10', 'dobra'), S.c('passo10', 'meio')]; },
    hud(S) {
      const s0 = S.start('passo10'), tDob = S.c('passo10', 'dobra');
      return {
        bar: null, ruler: null,
        alert: { t0: tDob, text: 'BUSÃO PARTIDO NO MEIO!' },
        customHud: weightHud({
          badge: 'PASSO 10', badgeT: s0, badgeCol: '#FF7A29',
          label: 'PESO DO ZECA',
          kg: t => HUD.roll(t, s0, tDob + 0.35, 4500, 71000),
          alert: false, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo10'), s1 = S.end('passo10');
      const tDob = S.c('passo10', 'dobra'), tMei = S.c('passo10', 'meio');
      const bendK = eBack(clamp((t - tDob) / 0.32, 0, 1));
      const shake = hits(t, [{ t: tDob, a: 36, d: 0.45 }, { t: tMei, a: 28, d: 0.4 }]);

      fillScreen(ctx, vGrad(ctx, [[0, '#1E3A8A'], [0.55, '#3B82F6'], [1, '#0F172A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tDob, 1.14, eBack], [s1, 1.06]]), shake }, t);

      // rua asfaltada
      ctx.fillStyle = '#1E293B'; ctx.fillRect(-100, 1110, W + 200, 860);
      contactShadow(ctx, 510, 1150, 360, 0.38);

      // onibus dobrando em V no centro!
      drawBendingBus(ctx, 510, 1045, Math.max(0, bendK));

      // Zeca em cima / no meio do onibus afundando o chassi!
      const zY = pelvisFromFeet(910 + Math.max(0, bendK) * 86, 0.86);
      drawZeca(ctx, st, { x: 510, y: zY, scale: 0.86, t, rim: { color: '#FFD400', dir: [0, -1] } });
      drawCracks(ctx, 510, 1150, 320, clamp(bendK, 0, 1));
      drawImpactRings(ctx, 510, 1145, t, tDob, '#FF7A29', 620);
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 7. PASSO 15 (2.300 TON - TERREMOTO + ALARMES!)
  SC.passo15 = {
    keys(S) {
      return [
        { t: S.start('passo15'), pose: STOMP_STEP, expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('passo15', 'terremoto'), pose: 'land', expr: 'panic', dur: 0.12, ease: 'back' },
        { t: S.c('passo15', 'alarmes'), pose: 'shock_closeup', expr: 'scream', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo15', 'passo'), S.c('passo15', 'terremoto'), S.c('passo15', 'dispara'), S.c('passo15', 'alarmes')]; },
    hud(S) {
      const s0 = S.start('passo15'), tTer = S.c('passo15', 'terremoto');
      return {
        bar: null, ruler: null,
        alert: { t0: tTer, text: 'TERREMOTO MAGNITUDE 7!' },
        customHud: weightHud({
          badge: 'PASSO 15', badgeT: s0,
          label: 'GRAVIDADE CRÍTICA',
          kg: t => HUD.roll(t, s0, tTer + 0.4, 71000, 2300000),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo15'), s1 = S.end('passo15');
      const tTer = S.c('passo15', 'terremoto'), tAla = S.c('passo15', 'alarmes');
      const quake = t >= tTer;
      const shake = hits(t, [{ t: tTer, a: 42, d: 0.6 }, { t: tAla, a: 28, d: 0.5 }]) + (quake ? 16 : 3);

      fillScreen(ctx, vGrad(ctx, [[0, '#450A0A'], [0.55, '#991B1B'], [1, '#18181B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tTer, 1.12, eBack], [s1, 1.06]]), shake }, t);

      // predios balancando no fundo
      for (const [bx, bw, bh, tilt] of [[40, 185, 560, -0.05], [250, 170, 490, 0.04], [640, 180, 540, -0.04], [835, 175, 480, 0.05]]) {
        ctx.save();
        ctx.translate(bx + bw / 2, 1180);
        ctx.rotate(quake ? Math.sin(t * 28 + bx) * tilt : 0);
        rr(ctx, -bw / 2, -bh, bw, bh, 12); outlined(ctx, '#334155', 7);
        for (let wy = -bh + 42; wy < -60; wy += 76) {
          for (const wx of [-46, 12]) {
            rr(ctx, wx, wy, 34, 42, 6); outlined(ctx, quake && (Math.floor(t * 8 + wy) % 2) ? '#FDE047' : '#64748B', 3);
          }
        }
        ctx.restore();
      }

      // avenida rachando
      ctx.fillStyle = '#18181B'; ctx.fillRect(-100, 1170, W + 200, 780);
      drawCracks(ctx, 510, 1205, 420, clamp((t - tTer) / 0.35, 0, 1), '#FF7A29');
      drawImpactRings(ctx, 510, 1205, t, tTer, '#FF2E3B', 760);

      // carros pulando com alarme disparando dos dois lados
      const carJump = quake ? -Math.abs(Math.sin(t * 24)) * 28 : 0;
      drawCar(ctx, 210, 1175 + carJump, 0.92, quake ? -0.1 : 0, '#3B82F6', t >= tAla, t);
      drawCar(ctx, 800, 1175 + carJump * 0.8, 0.92, quake ? 0.1 : 0, '#EF4444', t >= tAla, t);

      drawZeca(ctx, st, { x: 510, y: pelvisFromFeet(1205, 0.96), scale: 0.96, t, rim: { color: '#FF2E3B', dir: [0, -1] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 8. PASSO 18 (18 MIL TON - CRATERA + CARROS DESLIZAM!)
  SC.passo18 = {
    keys(S) {
      return [
        { t: S.start('passo18'), pose: 'shock_closeup', expr: 'panic', dur: 0.14, ease: 'back' },
        { t: S.c('passo18', 'deslizam'), pose: 'freefall_scream', expr: 'scream', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('passo18', 'rua'), S.c('passo18', 'cratera'), S.c('passo18', 'carros'), S.c('passo18', 'deslizam')]; },
    hud(S) {
      const s0 = S.start('passo18'), tCra = S.c('passo18', 'cratera');
      return {
        bar: null, ruler: null,
        alert: { t0: tCra, text: 'CRATERA GRAVITACIONAL!' },
        customHud: weightHud({
          badge: 'PASSO 18', badgeT: s0,
          label: 'GRAVIDADE CRÍTICA',
          kg: t => HUD.roll(t, s0, tCra + 0.45, 2300000, 18000000),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('passo18'), s1 = S.end('passo18');
      const tCra = S.c('passo18', 'cratera'), tDes = S.c('passo18', 'deslizam');
      const depthK = eOut(clamp((t - tCra) / 0.45, 0, 1));
      const slideK = eIn(clamp((t - tDes) / Math.max(0.3, s1 - tDes), 0, 1));
      const shake = hits(t, [{ t: tCra, a: 40, d: 0.5 }, { t: tDes, a: 24, d: 0.4 }]) + 10;

      fillScreen(ctx, vGrad(ctx, [[0, '#2E1065'], [0.5, '#7F1D1D'], [1, '#09090B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tCra, 1.1, eBack], [s1, 1.16]]), shake }, t);

      speedLines(ctx, 510, 1140, 26, 200, 980, '#FF7A29', 0.32, t * 1.1);

      // rua colapsando em uma cratera profunda em V
      const pitY = 1040 + depthK * 200;
      ctx.beginPath();
      ctx.moveTo(-100, 1020); ctx.lineTo(130, 1020);
      ctx.lineTo(510, pitY);
      ctx.lineTo(890, 1020); ctx.lineTo(W + 100, 1020);
      ctx.lineTo(W + 100, H + 100); ctx.lineTo(-100, H + 100); ctx.closePath();
      outlined(ctx, '#27272A', 9);
      // linhas de fratura nas paredes da cratera
      drawCracks(ctx, 510, pitY - 12, 340, depthK, '#FF2E3B');

      // carros deslizando pelas encostas em direcao ao Zeca!
      const c1x = lerp(175, 360, slideK), c1y = lerp(995, pitY - 82, slideK);
      const c2x = lerp(845, 660, slideK), c2y = lerp(995, pitY - 82, slideK);
      drawCar(ctx, c1x, c1y, 0.88, 0.36 * depthK, '#F59E0B', true, t);
      drawCar(ctx, c2x, c2y, 0.88, -0.36 * depthK, '#10B981', true, t);

      // Zeca no fundo da cratera
      drawZeca(ctx, st, { x: 510, y: pelvisFromFeet(pitY - 10, 0.84), scale: 0.84, t, rim: { color: '#FF2E3B', dir: [0, -1] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 9. ESTATUA (ZECA TRAVADO!)
  SC.estatua = {
    keys(S) {
      return [
        { t: S.start('estatua'), pose: 'shock_closeup', expr: 'panic', dur: 0.14, ease: 'back' },
        { t: S.c('estatua', 'estátua'), pose: STATUE_FREEZE, expr: 'focus', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('estatua', 'pânico'), S.c('estatua', 'Zeca'), S.c('estatua', 'estátua'), S.c('estatua', 'andar')]; },
    hud(S) {
      const s0 = S.start('estatua'), tEst = S.c('estatua', 'estátua');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'MODO ESTÁTUA', badgeT: tEst, badgeCol: '#38BDF8',
          label: '0 PASSOS / TRAVADO', value: '18 MIL TON',
          kg: 18000000, alert: false, hideGauge: false
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('estatua'), s1 = S.end('estatua');
      const tEst = S.c('estatua', 'estátua');

      fillScreen(ctx, vGrad(ctx, [[0, '#082F49'], [0.6, '#0E7490'], [1, '#0F172A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.05], [tEst, 1.14, eBack], [s1, 1.08]]), shake: hits(t, [{ t: tEst, a: 14, d: 0.25 }]) }, t);

      ctx.fillStyle = '#1E293B'; ctx.fillRect(-100, 1210, W + 200, 750);

      // pedestal de concreto sob os pes travados do Zeca
      rr(ctx, 325, 1140, 370, 82, 16); outlined(ctx, '#64748B', 7);
      label(ctx, 'NÃO SE MEXA!', 510, 1182, 34, '#E2E8F0');

      // aura de travamento azul ao redor do Zeca estatua
      if (t >= tEst) {
        glow(ctx, 510, 920, 320, 'rgba(56,189,248,A)', 0.36);
        pill(ctx, 510, 465, 420, 80, '#082F49', '#7DD3FC', 'ZERO PASSOS!', '#7DD3FC', 40);
      }

      drawZeca(ctx, st, { x: 510, y: pelvisFromFeet(1145, 1.04), scale: 1.04, t, rim: { color: '#7DD3FC', dir: [0, -1] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. BARATA (VOADORA NO NARIZ!)
  SC.barata = {
    keys(S) {
      return [
        { t: S.start('barata'), pose: STATUE_FREEZE, expr: 'determined', dur: 0.14, ease: 'inout' },
        { t: S.c('barata', 'barata'), pose: STATUE_FREEZE, expr: 'shock', dur: 0.12, ease: 'back' },
        { t: S.c('barata', 'nariz'), pose: 'shock_closeup', expr: 'panic', dur: 0.12, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('barata', 'salvo'), S.c('barata', 'barata'), S.c('barata', 'voadora'), S.c('barata', 'pousar'), S.c('barata', 'nariz')]; },
    hud(S) {
      const s0 = S.start('barata'), tBar = S.c('barata', 'barata');
      return {
        bar: null, ruler: null,
        alert: { t0: tBar, text: 'BARATA VOADORA DETECTADA!' },
        customHud: weightHud({
          badge: 'PERIGO', badgeT: tBar,
          label: 'AMEAÇA AÉREA', value: 'BARATA!!',
          kg: 18000000, alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('barata'), s1 = S.end('barata');
      const tBar = S.c('barata', 'barata'), tNar = S.c('barata', 'nariz');

      fillScreen(ctx, vGrad(ctx, [[0, '#1C1917'], [0.55, '#451A03'], [1, '#09090B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 920, z: kf(t, [[s0, 1.04], [tBar, 1.14], [tNar, 1.28, eIn], [s1, 1.34]]), shake: t >= tNar ? 10 : (t >= tBar ? 3 : 0) }, t);

      // Zeca enquadrado com folga acima da legenda em close-up de terror!
      const bx = 520, by = 1045;
      const scZ = 1.08;
      const noseY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82) * scZ + 18;
      drawZeca(ctx, st, { x: bx, y: by, scale: scZ, t, rim: { color: '#FFD400', dir: [-0.8, -0.5] } });

      // barata voadora pousando de lado na ponta do nariz (olhos e boca 100% nitidos!)
      if (t >= tBar - 0.15) {
        const flyK = clamp((t - (tBar - 0.15)) / Math.max(0.2, tNar - (tBar - 0.15)), 0, 1);
        const landed = t >= tNar;
        const rx = landed ? bx + 16 : lerp(130, bx + 16, eIO(flyK)) + Math.sin(t * 22) * 30 * (1 - flyK);
        const ry = landed ? noseY + 4 : lerp(560, noseY + 4, eIO(flyK)) + Math.cos(t * 18) * 26 * (1 - flyK);
        const rRot = landed ? 1.15 : 0.9 + Math.sin(t * 30) * 0.25;
        if (!landed) {
          ctx.strokeStyle = 'rgba(255,212,0,0.65)'; ctx.lineWidth = 6; ctx.setLineDash([14, 14]);
          ctx.beginPath(); ctx.moveTo(130, 560); ctx.quadraticCurveTo(320, 740, rx, ry); ctx.stroke();
          ctx.setLineDash([]);
        }
        if (landed) {
          glow(ctx, rx, ry, 86, 'rgba(255,46,59,A)', 0.52);
          ctx.strokeStyle = '#FF2E3B'; ctx.lineWidth = 5; ctx.setLineDash([10, 8]);
          ctx.beginPath(); ctx.arc(rx, ry, 46, 0, Math.PI * 2); ctx.stroke();
          ctx.setLineDash([]);
        }
        drawCockroach(ctx, rx, ry, landed ? 0.54 : 0.78, rRot, !landed, t);
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. NUCLEO (PASSO 25: 2 MI TON -> NUCLEO DA TERRA!)
  SC.nucleo = {
    keys(S) {
      return [
        { t: S.start('nucleo'), pose: RUN_PANIC, expr: 'scream', dur: 0.12, ease: 'back' },
        { t: S.c('nucleo', 'rasgando'), pose: METEOR_DROP, expr: 'scream', dur: 0.12, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('nucleo', 'surta'), S.c('nucleo', 'corre'), S.c('nucleo', 'passos'), S.c('nucleo', 'rasgando'), S.c('nucleo', 'núcleo')]; },
    hud(S) {
      const s0 = S.start('nucleo'), tRas = S.c('nucleo', 'rasgando');
      return {
        bar: null, ruler: null,
        alert: { t0: tRas, text: 'NÚCLEO DA TERRA ATINGIDO!' },
        customHud: weightHud({
          badge: 'PASSO 25', badgeT: tRas,
          label: 'MASSA PLANETÁRIA',
          kg: t => HUD.roll(t, s0, tRas + 0.4, 18000000, 2300000000),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('nucleo'), s1 = S.end('nucleo');
      const tCor = S.c('nucleo', 'corre'), tRas = S.c('nucleo', 'rasgando'), tNuc = S.c('nucleo', 'núcleo');
      const plunging = t >= tRas;
      const shake = hits(t, [{ t: tCor, a: 32, d: 0.45 }, { t: tRas, a: 44, d: 0.6 }, { t: tNuc, a: 48, d: 0.6 }]) + 14;

      if (!plunging) {
        // Beat 1: Zeca surta correndo 7 passos desesperado fugindo da barata!
        fillScreen(ctx, vGrad(ctx, [[0, '#7F1D1D'], [0.55, '#DC2626'], [1, '#18181B']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [tRas, 1.24, eBack]]), shake }, t);
        speedLines(ctx, 510, 960, 32, 160, 1100, '#FFD400', 0.48, t * 2.2);
        ctx.fillStyle = '#18181B'; ctx.fillRect(-100, 1200, W + 200, 760);
        const runX = 360 + Math.sin((t - s0) * 18) * 140;
        drawCracks(ctx, runX, 1210, 360, 1, '#FF7A29');
        drawZeca(ctx, st, { x: runX, y: pelvisFromFeet(1205, 0.96), scale: 0.96, t, rim: { color: '#FFD400', dir: [0, -1] } });
        drawCockroach(ctx, runX - 180, 920 + Math.sin(t * 28) * 35, 1.0, 0.6, true, t);
        drawBalloon(ctx, 510, 560, 'SAI BARATA!!', eBack(clamp((t - s0) / 0.16, 0, 1)), '#FFD400', '#DC2626');
        ctx.restore();
        return;
      }

      // Beat 2: Rasgando a crosta e mergulhando ate o nucleo incandescente da Terra!
      fillScreen(ctx, vGrad(ctx, [[0, '#450A0A'], [0.4, '#DC2626'], [0.78, '#F97316'], [1, '#FEF08A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tRas, 1.12], [tNuc, 1.26, eBack], [s1, 1.14]]), shake }, t);

      // paredes rochosas do tunel descendo em alta velocidade
      const scroll = ((t - tRas) * 1200) % 240;
      ctx.fillStyle = '#292524';
      ctx.fillRect(-100, -100, 290, H + 200);
      ctx.fillRect(W - 190, -100, 290, H + 200);
      ctx.strokeStyle = '#FF7A29'; ctx.lineWidth = 10;
      ctx.beginPath(); ctx.moveTo(190, -100); ctx.lineTo(190, H + 100); ctx.moveTo(W - 190, -100); ctx.lineTo(W - 190, H + 100); ctx.stroke();
      for (let ry = -240; ry <= H + 240; ry += 240) {
        rr(ctx, 40, ry - scroll, 130, 80, 14); outlined(ctx, '#44403C', 5);
        rr(ctx, W - 170, ry - scroll + 90, 130, 80, 14); outlined(ctx, '#44403C', 5);
      }

      // nucleo incandescente brilhando na base!
      glow(ctx, 540, 1450, 580, 'rgba(254,240,138,A)', 0.78);
      ctx.beginPath(); ctx.arc(540, 1520, 310, 0, Math.PI * 2); outlined(ctx, '#FEF08A', 8);

      // rastro de fogo vertical atras do Zeca meteoro
      speedLines(ctx, 540, 920, 30, 110, 980, '#FEF08A', 0.55, t * 2.4);
      ctx.beginPath();
      ctx.moveTo(410, 920); ctx.lineTo(540, 430); ctx.lineTo(670, 920); ctx.closePath();
      ctx.fillStyle = 'rgba(255,212,0,0.48)'; ctx.fill();

      drawZeca(ctx, st, { x: 540, y: 980, scale: 0.94, t, wind: [0, -80], rim: { color: '#FEF08A', dir: [0, 1] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 12. CTA ZECA (ENCERRAMENTO PERMANENTE!)
  SC.cta_zeca = {
    keys(S) {
      return [
        { t: S.start('cta_zeca'), pose: 'shrug_question', expr: 'curious', dur: 0.16, ease: 'back' },
        { t: S.c('cta_zeca', 'comentários'), pose: 'point_hook', expr: 'smug', dur: 0.16, ease: 'back' },
        { t: S.c('cta_zeca', 'próximo'), pose: 'flex', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('cta_zeca', 'Coitado'), S.c('cta_zeca', 'comentários'), S.c('cta_zeca', 'fazer'), S.c('cta_zeca', 'próximo')]; },
    hud(S) {
      const s0 = S.start('cta_zeca');
      return {
        bar: null, ruler: null, alert: null,
        customHud: weightHud({
          badge: 'ZECA', badgeT: s0, badgeCol: '#FFD400',
          label: 'PRÓXIMO EPISÓDIO', value: 'COMENTE AÍ!',
          kg: 70, alert: false, hideGauge: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('cta_zeca'), s1 = S.end('cta_zeca');
      const tCom = S.c('cta_zeca', 'comentários'), tPro = S.c('cta_zeca', 'próximo');

      // fundo radial vibrante focado no Zeca
      fillScreen(ctx, vGrad(ctx, [[0, '#1D4ED8'], [0.55, '#1E3A8A'], [1, '#0F172A']]));
      speedLines(ctx, 540, 920, 28, 200, 1080, '#FFD400', 0.25, t * 0.7);

      const z = kf(t, [[s0, 1.24], [tCom, 1.38, eBack], [tPro, 1.48, eBack], [s1, 1.54]]);
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: tCom, a: 18, d: 0.3 }]) + 2;
      const bx = 540, by = 1170;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);

      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 150 / z, z, shake }, t);
      glow(ctx, bx, by - 120, 340, 'rgba(255,212,0,A)', 0.34);
      drawZeca(ctx, st, { x: bx, y: by, scale: 1.0, t, rim: { color: '#FFD400', dir: [0.8, -0.6] } });
      ctx.restore();

      // placa central de chamada pros comentarios abaixo do HUD e acima da cabeca do Zeca
      pill(ctx, 540, 365, 720, 84, '#0B0F19', '#FFD400', 'O QUE O ZECA FAZ NO PRÓXIMO?', '#FFD400', 38);

      // dois elementos comicos nos flancos lembrando o episodio (peso + barata)
      ctx.save();
      ctx.translate(165, 1050 + Math.sin(t * 6) * 20);
      rr(ctx, -64, -44, 128, 88, 16); outlined(ctx, '#334155', 6);
      label(ctx, '2 MI t', 0, 2, 34, '#FFD400');
      ctx.restore();
      drawCockroach(ctx, 910, 1040 + Math.cos(t * 7) * 20, 1.05, -0.35, true, t);
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
