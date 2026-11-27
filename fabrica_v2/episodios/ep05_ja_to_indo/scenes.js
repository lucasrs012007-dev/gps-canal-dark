/*
 * ep05_ja_to_indo/scenes.js : Episodio 5 ("E se cada 'JA TO INDO!' ficasse 2x mais alto?")
 * 12 cenarios originais de ritmo ultra-rapido (61s-65s) em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
 * Traz ondas sonoras visiveis saindo da boca, baloes de impacto, barra VU segmentada
 * e regua vertical de decibeis (60dB -> 120dB -> 150dB -> 194dB -> CHOQUE).
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
  function drawBeto(ctx, st, o) {
    B.draw(ctx, Object.assign({ pose: st.pose, expr: st.expr, blink: st.blinkBoost }, o));
  }
  const pelvisFromFeet = (feetY, s) => feetY - B.STAND_PELVIS * s;

  // ------------------------------------------------------- poses customizadas
  B.POSES.sit_phone = Object.assign({}, B.POSES.idle, {
    crouch: 18, lean: 6, head: 10, ua_r: 36, la_r: -55, hand_r: 1,
    ua_l: 36, la_l: -55, hand_l: 1, th_r: 68, sh_r: -64, th_l: 68, sh_l: -64
  });
  B.POSES.yell_wide = Object.assign({}, B.POSES.shock_closeup, {
    lean: -10, head: -14, headDY: -4, ua_r: 132, la_r: 158, ua_l: 132, la_l: 158,
    hand_r: 0, hand_l: 0, th_r: 16, sh_r: 2, th_l: 16, sh_l: 2
  });
  B.POSES.cover_mouth = Object.assign({}, B.POSES.idle, {
    crouch: 6, lean: -4, head: 2, ua_r: 42, la_r: -125, hand_r: 0,
    ua_l: 42, la_l: -125, hand_l: 0
  });
  B.POSES.shush_pose = Object.assign({}, B.POSES.idle, {
    lean: 2, head: -2, ua_r: 48, la_r: -130, hand_r: 2, ua_l: 22, la_l: 8
  });
  const SIT_PHONE = 'sit_phone';
  const YELL_WIDE = 'yell_wide';
  const COVER_MOUTH = 'cover_mouth';
  const SHUSH_POSE = 'shush_pose';

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

  // ------------------------------------------------ HUD custom (Topo + Regua dB)
  const DB_MARKS = [
    { v: 60, txt: '60dB' },
    { v: 120, txt: '120dB' },
    { v: 150, txt: '150dB' },
    { v: 194, txt: '194dB' },
    { v: 265, txt: 'CHOQUE' }
  ];
  function dbColor(db) {
    if (db >= 194) return '#FF2E3B';
    if (db >= 150) return '#FF7A29';
    if (db >= 110) return '#FFD400';
    return '#2ED573';
  }
  /**
   * HUD dedicado do ep05:
   *  - Painel superior estilo Opus com badge dinamico ("GRITO 1", "SILENCIO", etc.),
   *    leitura em dB e barra VU segmentada de 10 blocos (inspirada no concorrente #2).
   *  - Regua vertical de decibeis na borda direita segura (60dB -> CHOQUE).
   */
  function soundHud(opts) {
    return function drawSoundHud(ctx, t) {
      const db = typeof opts.db === 'function' ? opts.db(t) : opts.db;
      const isAlert = !!opts.alert || db >= 194;
      const pulse = isAlert ? 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 2.6) : 0;

      // 1. PAINEL SUPERIOR (y=124, h=158, 4 lados com borda completa)
      if (!opts.hideTop) {
        const y = 124, h = 158, padX = 24, gap = 22;
        const badgeTxt = opts.badge || 'GRITO 1';
        const labTxt = opts.label || 'VOLUME';
        const valTxt = opts.value !== undefined ? (typeof opts.value === 'function' ? opts.value(t) : opts.value) : (Math.round(db) + ' dB');

        ctx.save();
        ctx.font = `58px ${HUD.FONT_DISPLAY}`;
        const bw = Math.max(ctx.measureText('GRITO 8').width, ctx.measureText(badgeTxt).width) + 42;
        ctx.font = `30px ${HUD.FONT_DISPLAY}`;
        const lw = ctx.measureText(labTxt).width;
        ctx.font = `68px ${HUD.FONT_DISPLAY}`;
        const vw = Math.max(ctx.measureText(valTxt).width, 280);
        const rightW = Math.max(lw, vw, 310);
        const totalW = Math.min(960, padX + bw + gap + rightW + padX);
        const x = (W - totalW) / 2;

        rr(ctx, x, y, totalW, h, 28);
        ctx.fillStyle = 'rgba(11,15,25,0.84)'; ctx.fill();
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
        ctx.font = `56px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(badgeTxt, 0, 3);
        ctx.restore();

        // coluna direita: rotulo + valor + barra VU segmentada (10 blocos)
        const rx = bx + bw + gap;
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        ctx.font = `28px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? '#FF8A92' : '#A9BCE0';
        ctx.fillText(labTxt, rx, y + 40);

        ctx.font = `66px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? (pulse > 0.5 ? '#FFFFFF' : '#FFD0D4') : '#FFFFFF';
        ctx.fillText(valTxt, rx, y + 106);

        // barra VU segmentada de 10 blocos na base do painel
        const segs = 10, segGap = 6, barW = rightW - 6, segW = (barW - segGap * (segs - 1)) / segs;
        const barY = y + 122, barH = 18;
        const normDb = clamp((db - 20) / 245, 0, 1);
        const activeCount = db <= 0 ? 0 : Math.max(1, Math.round(normDb * segs));
        for (let i = 0; i < segs; i++) {
          const sx = rx + i * (segW + segGap);
          const col = i < 3 ? '#2ED573' : (i < 6 ? '#FFD400' : (i < 8 ? '#FF7A29' : '#FF2E3B'));
          rr(ctx, sx, barY, segW, barH, 4);
          ctx.fillStyle = i < activeCount ? col : 'rgba(255,255,255,0.14)';
          ctx.fill();
        }
        ctx.restore();
      }

      // 2. REGUA VERTICAL DE DECIBEIS (borda direita segura x=1012, y=420..1080)
      if (!opts.hideGauge) {
        const x = 1012, y0 = 1080, y1 = 420;
        const dMin = 40, dMax = 275;
        const yOf = v => y0 - ((clamp(v, dMin, dMax) - dMin) / (dMax - dMin)) * (y0 - y1);
        const vib = (opts.vibrate && db > 100) ? vnoise(t * 48) * clamp((db - 90) / 24, 1, 7) : 0;

        ctx.save();
        ctx.translate(vib, 0);
        rr(ctx, x - 14, y1 - 24, 28, y0 - y1 + 48, 14);
        ctx.fillStyle = 'rgba(11,15,25,0.78)'; ctx.fill();
        ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.82)'; ctx.stroke();

        const ym = yOf(Math.max(dMin, db));
        const fillH = Math.max(0, y0 + 10 - ym);
        if (db > 0 && fillH > 2) {
          rr(ctx, x - 7, ym, 14, fillH, 7);
          ctx.fillStyle = dbColor(db); ctx.fill();
        }

        ctx.font = `22px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (const mk of DB_MARKS) {
          const yy = yOf(mk.v);
          ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
          ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
          ctx.strokeText(mk.txt, x - 32, yy + 1);
          ctx.fillStyle = mk.v >= 194 ? '#FF6B6B' : 'rgba(255,255,255,0.96)';
          ctx.fillText(mk.txt, x - 32, yy + 1);
        }

        // losango indicador
        ctx.save(); ctx.translate(x, ym);
        ctx.beginPath(); ctx.moveTo(0, -18); ctx.lineTo(18, 0); ctx.lineTo(0, 18); ctx.lineTo(-18, 0); ctx.closePath();
        ctx.fillStyle = db <= 0 ? '#74B9FF' : dbColor(db); ctx.fill();
        ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
        ctx.restore();
        ctx.restore();
      }
    };
  }

  // ------------------------------------------------ props e efeitos sonoros 2D
  /** Aneis concentricos de onda sonora saindo de um ponto (som visivel no mudo!). */
  function drawShockwaves(ctx, x, y, t, tStart, o) {
    o = o || {};
    const dt = t - tStart;
    if (dt < 0) return;
    const rings = o.rings || 4;
    const speed = o.speed || 920;
    const maxR = o.maxR || 950;
    const col = o.color || '#FFD400';
    const lw0 = o.lw || 16;
    ctx.save();
    for (let i = 0; i < rings; i++) {
      const localT = o.loop ? ((dt + i * (o.period || 0.28)) % (o.cycle || 1.1)) : (dt - i * (o.stagger || 0.11));
      if (localT < 0) continue;
      const r = 32 + localT * speed;
      if (r > maxR) continue;
      const a = clamp(1 - r / maxR, 0, 1);
      ctx.globalAlpha = a * (o.alpha || 0.92);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.lineWidth = Math.max(4, lw0 * a + 4); ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = Math.max(2, lw0 * a); ctx.strokeStyle = i % 2 === 0 ? col : '#FFFFFF'; ctx.stroke();
    }
    ctx.restore();
  }

  /** Balao de fala explosivo estilo quadrinho (inspirado no "!A COMEEER!" do concorrente). */
  function drawSpeechBurst(ctx, x, y, txt, scale, bgCol, txtCol, tailDir) {
    if (scale <= 0.02) return;
    ctx.save();
    ctx.translate(x, y); ctx.scale(scale, scale);
    ctx.font = `50px ${HUD.FONT_DISPLAY}`;
    const tw = ctx.measureText(txt).width;
    const bw = tw + 66, bh = 86;
    // linhas radiais de impacto atras do balao
    ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.lineCap = 'round';
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2 + 0.2;
      const rx0 = Math.cos(ang) * (bw * 0.56), ry0 = Math.sin(ang) * (bh * 0.65);
      const rx1 = Math.cos(ang) * (bw * 0.72), ry1 = Math.sin(ang) * (bh * 0.98);
      ctx.beginPath(); ctx.moveTo(rx0, ry0); ctx.lineTo(rx1, ry1); ctx.stroke();
    }
    // corpo do balao + rabicho
    rr(ctx, -bw / 2, -bh / 2, bw, bh, 22);
    outlined(ctx, bgCol || '#FFFFFF', 7);
    if (tailDir) {
      const tx = tailDir === 'left' ? -bw * 0.28 : (tailDir === 'right' ? bw * 0.28 : 0);
      ctx.beginPath();
      ctx.moveTo(tx - 16, bh / 2 - 4);
      ctx.lineTo(tx + (tailDir === 'left' ? -28 : (tailDir === 'right' ? 28 : 0)), bh / 2 + 28);
      ctx.lineTo(tx + 18, bh / 2 - 4);
      ctx.closePath();
      outlined(ctx, bgCol || '#FFFFFF', 7);
      // tampa linha interna do rabicho
      ctx.fillStyle = bgCol || '#FFFFFF';
      ctx.fillRect(tx - 15, bh / 2 - 8, 32, 10);
    }
    label(ctx, txt, 0, 3, 46, txtCol || INK);
    ctx.restore();
  }

  /** Mae do Beto em estilo Opus 2D (coque castanho, blusa rosa-magenta, expressoes vivas). */
  function drawMom(ctx, x, y, s, o) {
    o = o || {};
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    const yell = !!o.yell;
    const angry = !!o.angry;
    const holdPot = !!o.holdPot;
    // pernas
    ctx.strokeStyle = INK; ctx.lineWidth = 14; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-18, 44); ctx.lineTo(-22, 118); ctx.moveTo(18, 44); ctx.lineTo(22, 118); ctx.stroke();
    // chinelinhos
    ctx.beginPath(); ctx.ellipse(-26, 122, 22, 11, 0, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
    ctx.beginPath(); ctx.ellipse(26, 122, 22, 11, 0, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
    // tronco (blusa rosa + avental creme)
    rr(ctx, -44, -46, 88, 96, 28); outlined(ctx, '#E5507D', 7);
    rr(ctx, -26, -12, 52, 62, 14); outlined(ctx, '#FFF3DC', 5);
    // bracos
    ctx.strokeStyle = '#E5507D'; ctx.lineWidth = 22; ctx.lineCap = 'round';
    if (yell) {
      // braco esquerdo na cintura (ou segurando bule se holdPot), direito levantado chamando
      ctx.strokeStyle = INK; ctx.lineWidth = 28;
      ctx.beginPath(); ctx.moveTo(-40, -28); ctx.lineTo(-70, 6); ctx.lineTo(-42, 34); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(40, -28); ctx.lineTo(78, -74); ctx.stroke();
      ctx.strokeStyle = '#E5507D'; ctx.lineWidth = 16;
      ctx.beginPath(); ctx.moveTo(-40, -28); ctx.lineTo(-70, 6); ctx.lineTo(-42, 34); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(40, -28); ctx.lineTo(78, -74); ctx.stroke();
      ctx.beginPath(); ctx.arc(82, -78, 13, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 5);
      if (holdPot) {
        // bule de cafe fumegante na mao erguida
        rr(ctx, 64, -124, 48, 52, 10); outlined(ctx, '#C0392B', 6);
        rr(ctx, 72, -134, 32, 12, 5); outlined(ctx, '#922B21', 5);
        ctx.strokeStyle = INK; ctx.lineWidth = 6;
        ctx.beginPath(); ctx.moveTo(112, -108); ctx.lineTo(132, -120); ctx.stroke();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(88, -138); ctx.quadraticCurveTo(96, -158, 84, -174); ctx.stroke();
      }
    } else if (holdPot) {
      ctx.strokeStyle = INK; ctx.lineWidth = 28;
      ctx.beginPath(); ctx.moveTo(-40, -24); ctx.lineTo(-68, 18); ctx.moveTo(40, -24); ctx.lineTo(84, -4); ctx.stroke();
      ctx.strokeStyle = '#E5507D'; ctx.lineWidth = 16;
      ctx.beginPath(); ctx.moveTo(-40, -24); ctx.lineTo(-68, 18); ctx.moveTo(40, -24); ctx.lineTo(84, -4); ctx.stroke();
      // bule de cafe soltando fumaca
      rr(ctx, 76, -34, 48, 52, 10); outlined(ctx, '#C0392B', 6);
      ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(124, -18); ctx.lineTo(142, -28); ctx.stroke();
    } else {
      ctx.strokeStyle = INK; ctx.lineWidth = 28;
      ctx.beginPath(); ctx.moveTo(-40, -24); ctx.lineTo(-64, 24); ctx.moveTo(40, -24); ctx.lineTo(64, 24); ctx.stroke();
      ctx.strokeStyle = '#E5507D'; ctx.lineWidth = 16;
      ctx.beginPath(); ctx.moveTo(-40, -24); ctx.lineTo(-64, 24); ctx.moveTo(40, -24); ctx.lineTo(64, 24); ctx.stroke();
    }
    // coque + cabelo atras
    ctx.beginPath(); ctx.arc(0, -162, 28, 0, Math.PI * 2); outlined(ctx, '#4E2C1B', 7);
    ctx.beginPath(); ctx.arc(0, -104, 62, 0, Math.PI * 2); outlined(ctx, '#4E2C1B', 7);
    // rosto
    ctx.beginPath(); ctx.arc(0, -100, 52, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 7);
    // franja dividida
    ctx.beginPath();
    ctx.arc(0, -106, 52, Math.PI * 1.05, Math.PI * 1.95);
    ctx.lineTo(24, -124); ctx.lineTo(0, -138); ctx.lineTo(-24, -124); ctx.closePath();
    outlined(ctx, '#4E2C1B', 6);
    // olhos grandes expressivos
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.arc(side * 19, -102, 14, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
      ctx.beginPath(); ctx.arc(side * 19 + (o.lookX || 0), -101, 5.5, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
      // sobrancelhas
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.lineCap = 'round';
      ctx.beginPath();
      if (angry || yell) {
        ctx.moveTo(side * 33, -124); ctx.lineTo(side * 7, -116);
      } else {
        ctx.moveTo(side * 32, -121); ctx.lineTo(side * 8, -122);
      }
      ctx.stroke();
    }
    // boca
    if (yell) {
      ctx.beginPath(); ctx.ellipse(0, -72, 18, 16, 0, 0, Math.PI * 2); outlined(ctx, '#5E1117', 5);
      ctx.beginPath(); ctx.ellipse(0, -64, 10, 6, 0, 0, Math.PI * 2); ctx.fillStyle = '#E5646A'; ctx.fill();
    } else if (o.confused) {
      ctx.beginPath(); ctx.arc(0, -72, 9, 0, Math.PI * 2); outlined(ctx, '#5E1117', 5);
    } else {
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(-14, -74); ctx.quadraticCurveTo(0, angry ? -82 : -66, 14, -74); ctx.stroke();
    }
    ctx.restore();
  }

  /** Vira-lata caramelo brasileiro (senta no sofa e voa em 120 dB!). */
  function drawDog(ctx, x, y, s, rot, panic, t) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    const flap = panic ? Math.sin((t || 0) * 32) * 0.55 : 0;
    // rabinho
    ctx.strokeStyle = INK; ctx.lineWidth = 14; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-48, 4); ctx.quadraticCurveTo(-74, -22 + flap * 18, -62, -40); ctx.stroke();
    ctx.strokeStyle = '#C98338'; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.moveTo(-48, 4); ctx.quadraticCurveTo(-74, -22 + flap * 18, -62, -40); ctx.stroke();
    // corpo
    ctx.beginPath(); ctx.ellipse(-10, 12, 44, 30, 0, 0, Math.PI * 2); outlined(ctx, '#D99142', 6);
    // patinhas
    for (const px of [-34, -14, 12, 28]) {
      rr(ctx, px - 8, 28, 16, 28, 8); outlined(ctx, '#C98338', 5);
    }
    // cabeca
    ctx.beginPath(); ctx.arc(32, -16, 30, 0, Math.PI * 2); outlined(ctx, '#D99142', 6);
    // orelhas caindo/batendo
    ctx.save(); ctx.translate(10, -30); ctx.rotate(-0.35 - flap);
    ctx.beginPath(); ctx.ellipse(-8, 18, 12, 24, 0.2, 0, Math.PI * 2); outlined(ctx, '#8F531D', 5);
    ctx.restore();
    ctx.save(); ctx.translate(50, -30); ctx.rotate(0.35 + flap);
    ctx.beginPath(); ctx.ellipse(8, 18, 12, 24, -0.2, 0, Math.PI * 2); outlined(ctx, '#8F531D', 5);
    ctx.restore();
    // focinho + olhos
    ctx.beginPath(); ctx.ellipse(42, -6, 16, 12, 0, 0, Math.PI * 2); outlined(ctx, '#F7D7A8', 4);
    ctx.beginPath(); ctx.ellipse(47, -10, 6, 4.5, 0, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
    for (const ex of [24, 42]) {
      ctx.beginPath(); ctx.arc(ex, -24, panic ? 10 : 7, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 4);
      ctx.beginPath(); ctx.arc(ex + 1, -24, panic ? 3.5 : 3, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
    }
    if (panic) {
      ctx.beginPath(); ctx.ellipse(40, 4, 8, 11, 0.1, 0, Math.PI * 2); outlined(ctx, '#FF758F', 4);
    }
    ctx.restore();
  }

  /** Sofa vermelho vibrante da sala brasileira (referencia direta ao visual vibrante do concorrente). */
  function drawRedSofa(ctx, x, y, w, h) {
    ctx.save(); ctx.translate(x, y);
    contactShadow(ctx, 0, h * 0.52, w * 0.52, 0.35);
    // encosto
    rr(ctx, -w / 2 + 26, -h * 0.56, w - 52, h * 0.68, 34); outlined(ctx, '#D62839', 8);
    // almofada amarela + azul
    rr(ctx, -w / 2 + 54, -h * 0.34, 86, 78, 18); outlined(ctx, '#FFD400', 6);
    rr(ctx, w / 2 - 140, -h * 0.34, 86, 78, 18); outlined(ctx, '#38B6FF', 6);
    // assento
    rr(ctx, -w / 2 + 20, -h * 0.04, w - 40, h * 0.44, 24); outlined(ctx, '#E8322A', 8);
    // bracos laterais
    rr(ctx, -w / 2, -h * 0.2, 58, h * 0.64, 24); outlined(ctx, '#B81D2B', 8);
    rr(ctx, w / 2 - 58, -h * 0.2, 58, h * 0.64, 24); outlined(ctx, '#B81D2B', 8);
    ctx.restore();
  }

  /** Janela da sala inteira ou estourada + cacos de vidro voando. */
  function drawWindow(ctx, x, y, w, h, broken, t, tBreak) {
    ctx.save(); ctx.translate(x, y);
    // fundo ceu azul
    rr(ctx, -w / 2, -h / 2, w, h, 10);
    outlined(ctx, broken ? '#5AA9E6' : '#8AD4FF', 8);
    if (!broken) {
      // brilho do vidro + grades
      ctx.fillStyle = 'rgba(255,255,255,0.45)';
      ctx.beginPath(); ctx.moveTo(-w * 0.35, -h * 0.42); ctx.lineTo(-w * 0.1, -h * 0.42);
      ctx.lineTo(-w * 0.42, h * 0.1); ctx.lineTo(-w * 0.42, -h * 0.15); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 10;
      ctx.beginPath(); ctx.moveTo(0, -h / 2); ctx.lineTo(0, h / 2); ctx.moveTo(-w / 2, 0); ctx.lineTo(w / 2, 0); ctx.stroke();
      ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(-w / 2, -h / 2, w, h);
    } else {
      // bordas dentadas de vidro quebrado na moldura
      ctx.fillStyle = '#D9F4FF'; ctx.strokeStyle = INK; ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.moveTo(-w / 2, -h / 2); ctx.lineTo(-w * 0.18, -h / 2); ctx.lineTo(-w * 0.32, -h * 0.25); ctx.lineTo(-w / 2, -h * 0.18); ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(w / 2, h / 2); ctx.lineTo(w * 0.14, h / 2); ctx.lineTo(w * 0.3, h * 0.22); ctx.lineTo(w / 2, h * 0.12); ctx.closePath();
      ctx.fill(); ctx.stroke();
    }
    ctx.restore();
    if (broken && t >= tBreak) {
      drawGlassShards(ctx, x, y, t, tBreak, 22);
    }
  }

  function drawGlassShards(ctx, cx, cy, t, tBreak, count) {
    const dt = t - tBreak;
    if (dt < 0) return;
    ctx.save();
    for (let i = 0; i < count; i++) {
      const ang = hash(i * 31 + 3) * Math.PI * 2;
      const spd = 280 + hash(i * 47 + 9) * 780;
      const sx = cx + Math.cos(ang) * spd * dt;
      const sy = cy + Math.sin(ang) * spd * dt + 520 * dt * dt;
      const rot = dt * (5 + (i % 5) * 2.4) * (i % 2 ? 1 : -1) + i;
      const sz = 16 + hash(i * 13) * 28;
      ctx.save(); ctx.translate(sx, sy); ctx.rotate(rot);
      ctx.beginPath(); ctx.moveTo(-sz, -sz * 0.4); ctx.lineTo(sz * 0.9, -sz * 0.2); ctx.lineTo(sz * 0.1, sz * 0.8); ctx.closePath();
      outlined(ctx, i % 2 === 0 ? '#D9F4FF' : '#9CE5FF', 4);
      ctx.restore();
    }
    ctx.restore();
  }

  /** Carro na rua pulando com alarme piscando. */
  function drawCar(ctx, x, y, s, col, alarmOn, t, seed) {
    ctx.save();
    const bounce = alarmOn ? Math.abs(Math.sin(t * 20 + seed)) * -18 : 0;
    ctx.translate(x, y + bounce); ctx.scale(s, s);
    contactShadow(ctx, 0, 54 - bounce * 0.4, 130, 0.32);
    // carroceria
    rr(ctx, -125, -24, 250, 62, 18); outlined(ctx, col, 7);
    ctx.beginPath(); ctx.moveTo(-76, -24); ctx.lineTo(-48, -74); ctx.lineTo(54, -74); ctx.lineTo(88, -24); ctx.closePath();
    outlined(ctx, col, 7);
    // janelas quebradas ou trincadas
    ctx.beginPath(); ctx.moveTo(-62, -26); ctx.lineTo(-42, -64); ctx.lineTo(46, -64); ctx.lineTo(72, -26); ctx.closePath();
    outlined(ctx, '#A5E3FF', 5);
    // farol piscando
    const flash = alarmOn && Math.sin(t * 24 + seed) > 0;
    ctx.beginPath(); ctx.arc(114, -4, 14, 0, Math.PI * 2); outlined(ctx, flash ? '#FFD400' : '#FFE899', 4);
    ctx.beginPath(); ctx.arc(-114, -4, 14, 0, Math.PI * 2); outlined(ctx, flash ? '#FF2E3B' : '#992028', 4);
    if (flash) {
      glow(ctx, 132, -4, 72, 'rgba(255,212,0,A)', 0.65);
      glow(ctx, -132, -4, 72, 'rgba(255,46,59,A)', 0.65);
      // ondas de alarme BIP
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.arc(0, -86, 36 + (t * 90 + seed * 20) % 46, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
    }
    // rodas
    for (const wx of [-74, 74]) {
      ctx.beginPath(); ctx.arc(wx, 38, 28, 0, Math.PI * 2); outlined(ctx, '#1E2430', 6);
      ctx.beginPath(); ctx.arc(wx, 38, 12, 0, Math.PI * 2); outlined(ctx, '#D8DEE9', 4);
    }
    ctx.restore();
  }

  /** Casa brasileira de bairro (com telhado de ceramica que pode levantar!). */
  function drawHouse(ctx, x, y, s, opts) {
    opts = opts || {};
    const lift = opts.roofLift || 0;
    const tilt = opts.roofTilt || 0;
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    // paredes
    rr(ctx, -180, -100, 360, 230, 8); outlined(ctx, '#F5DEC0', 8);
    // porta
    rr(ctx, -38, 18, 76, 112, 8); outlined(ctx, '#8C4A22', 7);
    ctx.beginPath(); ctx.arc(22, 76, 6, 0, Math.PI * 2); ctx.fillStyle = '#FFD400'; ctx.fill();
    // janelas laterais
    for (const wx of [-115, 115]) {
      rr(ctx, wx - 36, -48, 72, 68, 6); outlined(ctx, opts.broken ? '#1E293B' : '#7DD3FC', 6);
    }
    // rachaduras na fachada
    if (opts.cracks) {
      ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(-140, -90); ctx.lineTo(-105, -20); ctx.lineTo(-125, 40); ctx.lineTo(-90, 110); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(90, -95); ctx.lineTo(68, -10); ctx.lineTo(98, 55); ctx.stroke();
    }
    // telhado de ceramica levantando
    if (!opts.hideRoof) {
      ctx.save(); ctx.translate(0, -100 - lift); ctx.rotate(tilt);
      ctx.beginPath(); ctx.moveTo(-215, 10); ctx.lineTo(0, -125); ctx.lineTo(215, 10); ctx.closePath();
      outlined(ctx, '#C84B24', 8);
      // linhas de telha
      ctx.strokeStyle = '#8A2D12'; ctx.lineWidth = 5;
      for (let k = -3; k <= 3; k++) {
        ctx.beginPath(); ctx.moveTo(k * 45, 6); ctx.lineTo(k * 20, -68); ctx.stroke();
      }
      ctx.restore();
    }
    ctx.restore();
  }

  /** Helicoptero da Defesa Civil com helice girando e holofote. */
  function drawHelicopter(ctx, x, y, s, t, flip) {
    ctx.save(); ctx.translate(x, y); ctx.scale(flip ? -s : s, s);
    // cone de holofote
    const g = ctx.createLinearGradient(40, 30, 110, 420);
    g.addColorStop(0, 'rgba(255,244,180,0.45)'); g.addColorStop(1, 'rgba(255,244,180,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(30, 34); ctx.lineTo(-40, 430); ctx.lineTo(220, 430); ctx.closePath(); ctx.fill();
    // cauda
    ctx.beginPath(); ctx.moveTo(-48, 0); ctx.lineTo(-165, -16); ctx.lineTo(-165, 6); ctx.lineTo(-48, 18); ctx.closePath();
    outlined(ctx, '#E67E22', 6);
    // rotor de cauda
    ctx.save(); ctx.translate(-165, -8); ctx.rotate(t * 28);
    ctx.strokeStyle = INK; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.moveTo(0, -24); ctx.lineTo(0, 24); ctx.stroke();
    ctx.restore();
    // cabine
    ctx.beginPath(); ctx.ellipse(0, 8, 72, 42, 0, 0, Math.PI * 2); outlined(ctx, '#E67E22', 7);
    ctx.beginPath(); ctx.ellipse(26, -2, 38, 24, 0, -Math.PI * 0.5, Math.PI * 0.35); ctx.lineTo(26, 20); ctx.closePath();
    outlined(ctx, '#93E1FF', 5);
    // faixa branca + esquis
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(-52, 8, 86, 12);
    ctx.strokeStyle = INK; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.moveTo(-36, 48); ctx.lineTo(-36, 64); ctx.moveTo(32, 48); ctx.lineTo(32, 64);
    ctx.moveTo(-64, 64); ctx.lineTo(66, 64); ctx.stroke();
    // helice principal borrada girando
    const bladeW = 140 * Math.abs(Math.cos(t * 36)) + 30;
    ctx.strokeStyle = INK; ctx.lineWidth = 9;
    ctx.beginPath(); ctx.moveTo(0, -34); ctx.lineTo(0, -52); ctx.moveTo(-bladeW, -52); ctx.lineTo(bladeW, -52); ctx.stroke();
    ctx.restore();
  }

  /** Chinela brasileira classica (sola branca + tira azul) para a CTA do loop! */
  function drawChinela(ctx, x, y, s, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    // sola formato pe
    ctx.beginPath();
    ctx.moveTo(-36, -65);
    ctx.bezierCurveTo(-48, -110, 48, -110, 42, -55);
    ctx.bezierCurveTo(46, 20, 34, 95, 0, 102);
    ctx.bezierCurveTo(-36, 98, -42, 20, -36, -65);
    ctx.closePath();
    outlined(ctx, '#FFFFFF', 8);
    // friso azul na borda
    ctx.strokeStyle = '#1D6FD8'; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.ellipse(0, 0, 26, 78, 0, 0, Math.PI * 2); ctx.stroke();
    // tiras em V
    ctx.strokeStyle = INK; ctx.lineWidth = 22; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-34, 6); ctx.lineTo(0, -54); ctx.lineTo(34, 6); ctx.stroke();
    ctx.strokeStyle = '#1D6FD8'; ctx.lineWidth = 12;
    ctx.beginPath(); ctx.moveTo(-34, 6); ctx.lineTo(0, -54); ctx.lineTo(34, 6); ctx.stroke();
    ctx.restore();
  }

  // ================================================================= CENAS (12)
  const SC = {};

  // ----------------------------------------------------------------- 1. HOOK
  SC.hook = {
    keys(S) {
      return [
        { t: S.start('hook'), pose: SIT_PHONE, expr: 'smug', dur: 0.14, ease: 'back' },
        { t: S.c('hook', 'gritou'), pose: YELL_WIDE, expr: 'scream', dur: 0.14, ease: 'back' },
        { t: S.c('hook', 'explodiu'), pose: 'shock_closeup', expr: 'panic', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) {
      return [S.c('hook', 'almoço'), S.c('hook', 'gritou'), S.c('hook', 'janela'), S.c('hook', 'explodiu')];
    },
    hud(S) {
      const s0 = S.start('hook'), tG = S.c('hook', 'gritou'), tE = S.c('hook', 'explodiu');
      return {
        bar: null, ruler: null,
        alert: { t0: tE, text: 'VIDRO ESTOURADO' },
        customHud: soundHud({
          badge: 'GRITO X2', badgeT: s0, label: 'VOLUME DA VOZ',
          db: t => t < tG ? 60 : HUD.roll(t, tG, tE + 0.35, 60, 150, 'lin'),
          alert: false, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('hook'), s1 = S.end('hook');
      const tAlm = S.c('hook', 'almoço'), tGri = S.c('hook', 'gritou'), tJan = S.c('hook', 'janela'), tExp = S.c('hook', 'explodiu');
      const broken = t >= tJan;
      const shake = hits(t, [
        { t: tAlm, a: 10, d: 0.25 },
        { t: tGri, a: 22, d: 0.35 },
        { t: tJan, a: 38, d: 0.55 },
        { t: tExp, a: 34, d: 0.5 }
      ]);

      // sala brasileira quente (paleta creme acolhedora -> claridade de impacto no estouro)
      fillScreen(ctx, vGrad(ctx, [[0, '#FCE0B8'], [0.62, '#F4C68D'], [1, '#B88450']]));
      ctx.save();
      const z = kf(t, [[s0, 1.0], [tGri, 1.06], [tJan, 1.24, eBack], [s1, 1.12]]);
      const cx = kf(t, [[s0, 540], [tGri, 520], [tJan, 560], [s1, 540]]);
      const cy = kf(t, [[s0, 960], [tGri, 980], [tJan, 900], [s1, 950]]);
      camApply(ctx, { x: cx, y: cy, z, shake }, t);

      // piso + rodape + tapete azul vibrante
      ctx.fillStyle = '#C9975B'; ctx.fillRect(-160, 1080, W + 320, 920);
      ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(-160, 1080); ctx.lineTo(W + 160, 1080); ctx.stroke();
      ctx.beginPath(); ctx.ellipse(500, 1340, 420, 155, 0, 0, Math.PI * 2); outlined(ctx, '#2D6CDF', 8);
      ctx.beginPath(); ctx.ellipse(500, 1340, 360, 120, 0, 0, Math.PI * 2); ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 9; ctx.stroke();

      // batente da porta a esquerda + mae chamando pro almoco
      rr(ctx, 70, 580, 220, 500, 6); outlined(ctx, '#FFF7EA', 8);
      rr(ctx, 90, 600, 180, 480, 4); outlined(ctx, '#D8B48A', 5);
      drawMom(ctx, 180, 920, 1.02, { yell: t >= tAlm - 0.1, angry: true });

      // janela grande a direita que explode em cacos!
      drawWindow(ctx, 760, 740, 310, 290, broken, t, tJan);

      // sofa vermelho + caramelo + Beto
      drawRedSofa(ctx, 480, 1140, 560, 240);
      if (t >= tGri) {
        drawShockwaves(ctx, 500, 910, t, tGri, { rings: 5, speed: 1050, maxR: 980, color: '#FFD400', lw: 18 });
      }
      const dogFly = broken ? clamp((t - tJan) / 0.55, 0, 1) : 0;
      drawDog(ctx, 305 + dogFly * 45, 1062 - dogFly * 175, 0.92, -dogFly * 0.45, broken, t);
      drawBeto(ctx, st, {
        x: 500, y: 1085, scale: 0.94, t,
        rim: { color: broken ? '#FF5252' : '#FFE08A', dir: [0.8, -0.5] }
      });

      // baloes de quadrinho
      if (t < tGri + 0.15) {
        const scA = eBack(clamp((t - s0) / 0.22, 0, 1));
        drawSpeechBurst(ctx, 265, 620, 'ALMOÇO!', scA, '#FFFFFF', '#E8322A', 'left');
      }
      if (t >= tGri) {
        const scG = eBack(clamp((t - tGri) / 0.2, 0, 1));
        drawSpeechBurst(ctx, 500, 650, 'JÁ TÔ INDO!', scG, '#FFD400', INK, 'center');
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 2. PREMISSA
  SC.premissa = {
    keys(S) {
      return [
        { t: S.start('premissa'), pose: 'point_hook', expr: 'determined', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'responde'), pose: YELL_WIDE, expr: 'amazed', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'dobra'), pose: 'flex', expr: 'shock', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('premissa', 'responde'), S.c('premissa', 'volume'), S.c('premissa', 'dobra')]; },
    hud(S) {
      const s0 = S.start('premissa'), tD = S.c('premissa', 'dobra');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({
          badge: 'REGRA X2', badgeT: s0, label: 'ESCALA DE SOM',
          value: t => t < tD ? 'X2 POR GRITO' : 'DOBRA SEMPRE',
          db: t => HUD.roll(t, s0, S.end('premissa'), 60, 194, 'lin'),
          vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), tResp = S.c('premissa', 'responde'), tDob = S.c('premissa', 'dobra');
      const shake = hits(t, [{ t: tResp, a: 12, d: 0.25 }, { t: tDob, a: 26, d: 0.45 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#101830'], [0.6, '#1B2A52'], [1, '#0C1224']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tDob, 1.1, eBack]]), shake }, t);

      // barras de equalizador atras crescendo exponencialmente
      const bars = 13;
      for (let i = 0; i < bars; i++) {
        const bx = 78 + i * 62;
        const amp = (0.35 + 0.65 * Math.pow(i / (bars - 1), 1.4)) * (0.65 + 0.35 * Math.sin(t * 14 + i * 0.7));
        const bh = amp * (t >= tDob ? 520 : 310);
        rr(ctx, bx, 1220 - bh, 44, bh, 10);
        ctx.fillStyle = i < 4 ? '#2ED573' : (i < 8 ? '#FFD400' : (i < 11 ? '#FF7A29' : '#FF2E3B'));
        ctx.globalAlpha = 0.36; ctx.fill(); ctx.globalAlpha = 1;
        ctx.lineWidth = 4; ctx.strokeStyle = INK; ctx.stroke();
      }

      // linha de onda sonora atravessando a tela (limpa a esquerda da regua dB)
      ctx.save();
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 9;
      ctx.beginPath();
      for (let x = 40; x <= 855; x += 12) {
        const k = (x - 40) / 815;
        const env = Math.pow(k, 1.5) * (t >= tDob ? 145 : 75);
        const y = 740 + Math.sin(x * 0.045 - t * 18) * env;
        if (x === 40) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();

      // badges X2 -> X4 -> X8 -> X16 surgindo em cascata
      const mults = [
        { txt: 'X2', x: 185, y: 530, t0: s0 + 0.15, col: '#2ED573' },
        { txt: 'X4', x: 375, y: 500, t0: tResp, col: '#FFD400' },
        { txt: 'X8', x: 565, y: 470, t0: tDob - 0.15, col: '#FF7A29' },
        { txt: 'X16!', x: 755, y: 440, t0: tDob, col: '#FF2E3B' }
      ];
      for (const m of mults) {
        const sc = eBack(clamp((t - m.t0) / 0.22, 0, 1));
        if (sc > 0.02) {
          ctx.save(); ctx.translate(m.x, m.y); ctx.scale(sc, sc);
          pill(ctx, 0, 0, 152, 86, m.col, '#FFFFFF', m.txt, m.col === '#FF2E3B' ? '#FFFFFF' : INK, 46);
          ctx.restore();
        }
      }

      contactShadow(ctx, 480, 1260, 130, 0.38);
      if (t >= tDob) {
        drawShockwaves(ctx, 480, 920, t, tDob, { rings: 3, speed: 820, maxR: 720, color: '#FF2E3B', lw: 14 });
      }
      drawBeto(ctx, st, { x: 480, y: pelvisFromFeet(1260, 1.0), scale: 1.0, t, rim: { color: '#FFD400', dir: [0.6, -0.8] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 3. GRITO 1
  SC.grito1 = {
    keys(S) {
      return [
        { t: S.start('grito1'), pose: SIT_PHONE, expr: 'neutral', dur: 0.16, ease: 'inout' },
        { t: S.c('grito1', 'normal'), pose: SIT_PHONE, expr: 'smug', dur: 0.16, ease: 'back' },
        { t: S.c('grito1', 'mãe'), pose: 'shrug_question', expr: 'curious', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('grito1', '60'), S.c('grito1', 'normal'), S.c('grito1', 'mãe'), S.c('grito1', 'escuta')]; },
    hud(S) {
      const s0 = S.start('grito1');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({ badge: 'GRITO 1', badgeT: s0, label: 'CONVERSA NORMAL', db: 60 })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito1'), tMae = S.c('grito1', 'mãe'), tEsc = S.c('grito1', 'escuta');
      if (t < tMae) {
        // Plano A: Beto de boa no sofa soltando ondinha verde minuscula (60 dB)
        fillScreen(ctx, vGrad(ctx, [[0, '#FCE4C2'], [0.65, '#F3C790'], [1, '#BE8A52']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tMae, 1.1]]), shake: 0 }, t);
        ctx.fillStyle = '#C9975B'; ctx.fillRect(-140, 1100, W + 280, 900);
        drawWindow(ctx, 760, 720, 290, 260, false, t, 999);
        drawRedSofa(ctx, 470, 1140, 560, 240);
        // ondinha timida verde atras do Beto
        drawShockwaves(ctx, 495, 920, t, s0 + 0.1, { rings: 3, speed: 240, maxR: 320, color: '#2ED573', lw: 8, loop: true, period: 0.45, cycle: 1.35 });
        drawDog(ctx, 290, 1068, 0.9, 0, false, t);
        drawBeto(ctx, st, { x: 495, y: 1085, scale: 0.94, t, rim: { color: '#9BFFB8', dir: [0.7, -0.6] } });
        pill(ctx, 455, 650, 265, 74, '#FFFFFF', '#2ED573', 'já tô indo...', INK, 34);
        ctx.restore();
        return;
      }
      // Plano B: Corte para a cozinha (mae mexendo panela no fogao nem ouve!)
      fillScreen(ctx, vGrad(ctx, [[0, '#E8F4FA'], [0.65, '#CBE2EE'], [1, '#9EB8C7']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tMae, 1.05], [S.end('grito1'), 1.15]]), shake: hits(t, [{ t: tEsc, a: 6, d: 0.2 }]) }, t);
      // azulejos leves da cozinha
      ctx.strokeStyle = 'rgba(255,255,255,0.45)'; ctx.lineWidth = 3;
      for (let gx = 0; gx < W; gx += 90) { ctx.beginPath(); ctx.moveTo(gx, 360); ctx.lineTo(gx, 1120); ctx.stroke(); }
      for (let gy = 360; gy < 1120; gy += 90) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke(); }
      // fogao brasileiro completo (4 botoes + puxador de forno + bocas + panela com tampa)
      rr(ctx, 520, 920, 330, 340, 14); outlined(ctx, '#F3F4F6', 8);
      ctx.fillStyle = '#1F2937'; ctx.fillRect(524, 924, 322, 16);
      // 4 botoes do fogao
      for (let k = 0; k < 4; k++) {
        ctx.beginPath(); ctx.arc(575 + k * 72, 962, 12, 0, Math.PI * 2); outlined(ctx, '#374151', 4);
      }
      // visor do forno + puxador metalico
      rr(ctx, 560, 1005, 250, 200, 12); outlined(ctx, '#374151', 6);
      rr(ctx, 600, 1020, 170, 16, 8); outlined(ctx, '#D1D5DB', 4);
      // chama azul da boca + panela de pressao/arroz com alcas e tampa
      glow(ctx, 685, 920, 44, 'rgba(56,189,248,A)', 0.65);
      rr(ctx, 595, 845, 180, 74, 14); outlined(ctx, '#9CA3AF', 7);
      rr(ctx, 575, 862, 24, 16, 6); outlined(ctx, '#1F2937', 4);
      rr(ctx, 771, 862, 24, 16, 6); outlined(ctx, '#1F2937', 4);
      rr(ctx, 658, 826, 54, 18, 8); outlined(ctx, '#1F2937', 5);
      // vapor subindo
      ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 8; ctx.lineCap = 'round';
      for (let k = 0; k < 3; k++) {
        const vx = 640 + k * 48;
        ctx.beginPath();
        ctx.moveTo(vx, 825);
        ctx.quadraticCurveTo(vx + Math.sin(t * 7 + k) * 20, 760, vx - Math.sin(t * 7 + k) * 18, 690);
        ctx.stroke();
      }
      // mae na cozinha olhando pro lado confusa
      drawMom(ctx, 370, 990, 1.38, { confused: true, lookX: -5 });
      const scQ = eBack(clamp((t - tMae) / 0.22, 0, 1));
      drawSpeechBurst(ctx, 360, 615, 'QUÊ?!', scQ, '#FFFFFF', '#0B0F19', 'center');
      label(ctx, 'NEM ESCUTOU', 680, 615, 40, '#FFD400');
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 4. GRITO 2
  SC.grito2 = {
    keys(S) {
      return [
        { t: S.start('grito2'), pose: YELL_WIDE, expr: 'scream', dur: 0.14, ease: 'back' },
        { t: S.c('grito2', 'cachorro'), pose: 'shock_closeup', expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('grito2', 'sofá'), pose: 'dodge_lean', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('grito2', '120'), S.c('grito2', 'decibéis'), S.c('grito2', 'turbina'), S.c('grito2', 'cachorro'), S.c('grito2', 'voa')]; },
    hud(S) {
      const s0 = S.start('grito2');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({
          badge: 'GRITO 2', badgeT: s0, label: 'TURBINA DE AVIÃO',
          db: t => HUD.roll(t, s0, s0 + 0.5, 60, 120, 'lin'), vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito2'), s1 = S.end('grito2');
      const tDb = S.c('grito2', 'decibéis'), tTurb = S.c('grito2', 'turbina'), tCach = S.c('grito2', 'cachorro'), tVoa = S.c('grito2', 'voa');
      if (t < tCach) {
        // Plano A: Comparacao instantanea com turbina de aviao rugindo!
        const shake = hits(t, [{ t: s0, a: 16, d: 0.35 }, { t: tDb, a: 14, d: 0.3 }, { t: tTurb, a: 22, d: 0.45 }]) + 4;
        fillScreen(ctx, vGrad(ctx, [[0, '#1B2D4F'], [0.55, '#34598A'], [1, '#12203A']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tCach, 1.14]]), shake }, t);
        speedLines(ctx, 260, 900, 26, 180, 950, '#FFD400', 0.35, t * 0.5);
        // turbina de jato estilizada a esquerda
        ctx.save(); ctx.translate(280, 900);
        ctx.beginPath(); ctx.arc(0, 0, 210, 0, Math.PI * 2); outlined(ctx, '#94A3B8', 9);
        ctx.beginPath(); ctx.arc(0, 0, 172, 0, Math.PI * 2); outlined(ctx, '#1E293B', 7);
        // pas girando em alta velocidade
        ctx.save(); ctx.rotate(t * 28);
        for (let i = 0; i < 12; i++) {
          ctx.rotate(Math.PI / 6);
          ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(162, -18); ctx.lineTo(162, 18); ctx.closePath();
          ctx.fillStyle = i % 2 ? '#64748B' : '#CBD5E1'; ctx.fill();
        }
        ctx.restore();
        ctx.beginPath(); ctx.arc(0, 0, 44, 0, Math.PI * 2); outlined(ctx, '#FFD400', 6);
        ctx.restore();
        // ondas saindo da turbina
        drawShockwaves(ctx, 280, 900, t, s0, { rings: 4, speed: 880, maxR: 860, color: '#FFD400', lw: 14, loop: true, period: 0.3, cycle: 1.0 });
        drawBeto(ctx, st, { x: 700, y: pelvisFromFeet(1260, 0.96), scale: 0.96, t, rim: { color: '#FFD400', dir: [-1, 0] } });
        pill(ctx, 510, 560, 420, 86, '#FFD400', '#FFFFFF', '120 dB = TURBINA!', INK, 42);
        ctx.restore();
        return;
      }
      // Plano B: O caramelo VOA do sofa com almofadas (limpo a esquerda da regua dB!)
      const dt = t - tCach;
      const fly = eOut(clamp((t - tVoa + 0.12) / 0.85, 0, 1));
      const shake = hits(t, [{ t: tCach, a: 26, d: 0.45 }, { t: tVoa, a: 28, d: 0.45 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#FCE0B8'], [0.6, '#F4C68D'], [1, '#B88450']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tCach, 1.04], [s1, 1.12]]), shake }, t);
      ctx.fillStyle = '#C9975B'; ctx.fillRect(-160, 1120, W + 320, 900);
      drawRedSofa(ctx, 410, 1150, 510, 230);
      drawShockwaves(ctx, 360, 920, t, tCach, { rings: 4, speed: 950, maxR: 850, color: '#FFD400', lw: 16 });
      drawBeto(ctx, st, { x: 345, y: 1090, scale: 0.94, t, rim: { color: '#FFD400', dir: [1, -0.4] } });
      // almofada voando (mantida a esquerda de x=700)
      ctx.save(); ctx.translate(500 + fly * 190, 985 - fly * 220); ctx.rotate(fly * 4.5);
      rr(ctx, -42, -38, 84, 76, 18); outlined(ctx, '#38B6FF', 6);
      ctx.restore();
      // caramelo voando em arco com orelhas batendo (limpo a esquerda da regua dB!)
      const dx = lerp(470, 735, fly);
      const dy = lerp(1030, 685, fly) - Math.sin(fly * Math.PI) * 140;
      drawDog(ctx, dx, dy, 1.02, -0.45 + fly * 1.1, true, t);
      drawSpeechBurst(ctx, 355, 650, 'JÁ TÔ INDO!', eBack(clamp(dt / 0.2, 0, 1)), '#FFD400', INK, 'left');
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 5. GRITO 3
  SC.grito3 = {
    keys(S) {
      return [
        { t: S.start('grito3'), pose: YELL_WIDE, expr: 'scream', dur: 0.14, ease: 'back' },
        { t: S.c('grito3', 'estouram'), pose: 'shock_closeup', expr: 'panic', dur: 0.14, ease: 'back' },
        { t: S.c('grito3', 'alarmes'), pose: 'dodge_lean', expr: 'shock', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('grito3', '150'), S.c('grito3', 'decibéis'), S.c('grito3', 'estouram'), S.c('grito3', 'alarmes'), S.c('grito3', 'disparam')]; },
    hud(S) {
      const s0 = S.start('grito3'), tAl = S.c('grito3', 'alarmes');
      return {
        bar: null, ruler: null,
        alert: { t0: tAl, text: 'ALARMES NA RUA' },
        customHud: soundHud({
          badge: 'GRITO 3', badgeT: s0, label: 'VIDROS ESTOURANDO',
          db: t => HUD.roll(t, s0, s0 + 0.5, 120, 150, 'lin'), vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito3'), s1 = S.end('grito3');
      const tDb = S.c('grito3', 'decibéis'), tEst = S.c('grito3', 'estouram'), tAla = S.c('grito3', 'alarmes');
      if (t < tAla) {
        // Plano A: Fachada da casa estourando todas as janelas em cacos com ondas sonoras!
        const shake = hits(t, [{ t: s0, a: 18, d: 0.35 }, { t: tDb, a: 14, d: 0.3 }, { t: tEst, a: 34, d: 0.55 }]) + 4;
        fillScreen(ctx, vGrad(ctx, [[0, '#3C7EC2'], [0.55, '#86C5F4'], [1, '#4C566A']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tEst, 1.18, eBack]]), shake }, t);
        ctx.fillStyle = '#4A5568'; ctx.fillRect(-160, 1180, W + 320, 820);
        drawHouse(ctx, 510, 980, 1.55, { broken: t >= tEst, cracks: t >= tEst });
        drawShockwaves(ctx, 510, 920, t, s0, { rings: 5, speed: 920, maxR: 980, color: '#FFD400', lw: 16, loop: true, period: 0.32, cycle: 1.1 });
        if (t >= tEst) {
          drawGlassShards(ctx, 330, 910, t, tEst, 14);
          drawGlassShards(ctx, 690, 910, t, tEst, 14);
        }
        ctx.restore();
        return;
      }
      // Plano B: Carros na rua quicando com alarmes disparados (BIP! BIP!)
      const shake = hits(t, [{ t: tAla, a: 26, d: 0.45 }]) + 6;
      fillScreen(ctx, vGrad(ctx, [[0, '#2A4069'], [0.55, '#5979A8'], [1, '#2D3442']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tAla, 1.0], [s1, 1.12]]), shake }, t);
      // asfalto + faixa amarela
      ctx.fillStyle = '#333A48'; ctx.fillRect(-160, 980, W + 320, 1020);
      ctx.fillStyle = '#FFD400';
      for (let rx = -40; rx < W + 100; rx += 160) { ctx.fillRect(rx, 1170, 90, 18); }
      // 3 carros pulando com alarme
      drawCar(ctx, 250, 1020, 0.92, '#E8322A', true, t, 1.1);
      drawCar(ctx, 730, 1030, 0.92, '#3B82F6', true, t, 2.7);
      drawCar(ctx, 490, 1210, 1.06, '#F59E0B', true, t, 4.3);
      // Beto atras com as maos na cabeca
      drawBeto(ctx, st, { x: 490, y: 895, scale: 0.72, t, rim: { color: '#FFD400', dir: [0, -1] } });
      if (Math.sin(t * 20) > -0.2) {
        drawSpeechBurst(ctx, 250, 810, 'BIP! BIP!', 0.85, '#FF2E3B', '#FFFFFF');
        drawSpeechBurst(ctx, 740, 825, 'BIP! BIP!', 0.85, '#FFD400', INK);
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 6. GRITO 4
  SC.grito4 = {
    keys(S) {
      return [
        { t: S.start('grito4'), pose: YELL_WIDE, expr: 'scream', dur: 0.14, ease: 'back' },
        { t: S.c('grito4', 'vizinhos'), pose: 'shock_closeup', expr: 'panic', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('grito4', '180'), S.c('grito4', 'decibéis'), S.c('grito4', 'telhado'), S.c('grito4', 'vizinhos'), S.c('grito4', 'terremoto')]; },
    hud(S) {
      const s0 = S.start('grito4'), tTer = S.c('grito4', 'terremoto');
      return {
        bar: null, ruler: null,
        alert: { t0: tTer, text: 'FALSO TERREMOTO' },
        customHud: soundHud({
          badge: 'GRITO 4', badgeT: s0, label: 'TELHADO VOANDO',
          db: t => HUD.roll(t, s0, s0 + 0.5, 150, 180, 'lin'), vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito4'), s1 = S.end('grito4');
      const tDb = S.c('grito4', 'decibéis'), tTel = S.c('grito4', 'telhado'), tViz = S.c('grito4', 'vizinhos');
      if (t < tViz) {
        // Plano A: Telhado inteiro levanta igual tampa de panela!
        const liftK = eBack(clamp((t - tTel + 0.1) / 0.55, 0, 1));
        const shake = hits(t, [{ t: s0, a: 20, d: 0.35 }, { t: tDb, a: 15, d: 0.3 }, { t: tTel, a: 34, d: 0.5 }]) + 8;
        fillScreen(ctx, vGrad(ctx, [[0, '#FF8C42'], [0.45, '#FFB86C'], [1, '#4A332D']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 940, z: kf(t, [[s0, 1.0], [tViz, 1.14]]), shake }, t);
        ctx.fillStyle = '#3D3540'; ctx.fillRect(-160, 1180, W + 320, 820);
        // luz dourada saindo por baixo do telhado levantado
        glow(ctx, 510, 820, 380, 'rgba(255,212,0,A)', 0.55 * liftK);
        drawHouse(ctx, 510, 1020, 1.5, { broken: true, cracks: true, roofLift: liftK * 145, roofTilt: -liftK * 0.14 });
        // telhas soltas girando no ar
        for (let i = 0; i < 8; i++) {
          const tx = 240 + i * 80 + Math.sin(t * 5 + i) * 35;
          const ty = 650 - liftK * (120 + (i % 3) * 90) + Math.cos(t * 7 + i) * 20;
          ctx.save(); ctx.translate(tx, ty); ctx.rotate(t * 6 * (i % 2 ? 1 : -1) + i);
          rr(ctx, -28, -12, 56, 24, 6); outlined(ctx, '#C84B24', 5);
          ctx.restore();
        }
        drawShockwaves(ctx, 510, 920, t, tTel, { rings: 4, speed: 940, maxR: 980, color: '#FFD400', lw: 18 });
        ctx.restore();
        return;
      }
      // Plano B: Rua rachando e vizinhos bem espacados correndo em panico + Beto na calcada!
      const shake = hits(t, [{ t: tViz, a: 28, d: 0.5 }]) + 10;
      fillScreen(ctx, vGrad(ctx, [[0, '#5E2C3E'], [0.5, '#A84B4B'], [1, '#2B2229']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tViz, 1.02], [s1, 1.1]]), shake }, t);
      // calcada + asfalto
      ctx.fillStyle = '#5B6270'; ctx.fillRect(-160, 960, W + 320, 80);
      ctx.fillStyle = '#383E4C'; ctx.fillRect(-160, 1040, W + 320, 960);
      ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(-160, 1040); ctx.lineTo(W + 160, 1040); ctx.stroke();
      // rachadura gigante ziguezague no asfalto
      ctx.strokeStyle = INK; ctx.lineWidth = 14; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(80, 1220); ctx.lineTo(290, 1160); ctx.lineTo(460, 1245); ctx.lineTo(680, 1165); ctx.lineTo(890, 1250); ctx.stroke();
      // Beto aterrado na calcada a esquerda em choque
      contactShadow(ctx, 210, 1015, 76, 0.35);
      drawBeto(ctx, st, { x: 210, y: pelvisFromFeet(1015, 0.78), scale: 0.78, t, rim: { color: '#FFD400', dir: [0.8, -0.6] } });
      // vizinhos bem espacados com olhos, cabelo e expressao de panico
      const runT = clamp(t - tViz, 0, 2.5);
      const runners = [
        { x: 420 + runT * 65, dir: 1, col: '#38BDF8', hair: '#2C1B10', y: 1125, s: 0.92 },
        { x: 760 - runT * 55, dir: -1, col: '#4ADE80', hair: '#5C3A21', y: 1145, s: 0.96 }
      ];
      for (let i = 0; i < runners.length; i++) {
        const r = runners[i];
        const bob = Math.abs(Math.sin(t * 16 + i * 2)) * -20;
        ctx.save(); ctx.translate(r.x, r.y + bob); ctx.scale(r.dir * r.s, r.s);
        const leg = Math.sin(t * 16 + i * 2) * 32;
        ctx.strokeStyle = INK; ctx.lineWidth = 16; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(0, 20); ctx.lineTo(leg, 86); ctx.moveTo(0, 20); ctx.lineTo(-leg, 86); ctx.stroke();
        rr(ctx, -28, -56, 56, 82, 18); outlined(ctx, r.col, 7);
        ctx.strokeStyle = INK; ctx.lineWidth = 14;
        ctx.beginPath(); ctx.moveTo(-22, -40); ctx.lineTo(-56, -98); ctx.moveTo(22, -40); ctx.lineTo(56, -98); ctx.stroke();
        ctx.beginPath(); ctx.arc(0, -96, 36, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 7);
        // cabelo + olhos arregalados + boca gritando
        ctx.beginPath(); ctx.arc(0, -104, 35, Math.PI * 1.05, Math.PI * 1.95); outlined(ctx, r.hair, 5);
        for (const ex of [-4, 16]) {
          ctx.beginPath(); ctx.arc(ex, -100, 9, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 4);
          ctx.beginPath(); ctx.arc(ex + 2, -100, 3.5, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
        }
        ctx.beginPath(); ctx.ellipse(10, -76, 11, 13, 0, 0, Math.PI * 2); outlined(ctx, '#4A0F12', 4);
        ctx.restore();
      }
      drawSpeechBurst(ctx, 575, 760, 'TERREMOTO?!', eBack(clamp(runT / 0.24, 0, 1)), '#FFD400', '#E8322A', 'center');
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 7. GRITO 5 (194 dB CLIMAX FISICO)
  SC.grito5 = {
    keys(S) {
      return [
        { t: S.start('grito5'), pose: YELL_WIDE, expr: 'scream', dur: 0.14, ease: 'back' },
        { t: S.c('grito5', 'choque'), pose: 'super_launch', expr: 'scream', dur: 0.12, ease: 'back' },
        { t: S.c('grito5', 'parede'), pose: 'freefall_scream', expr: 'panic', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('grito5', '194'), S.c('grito5', 'decibéis'), S.c('grito5', 'limite'), S.c('grito5', 'choque'), S.c('grito5', 'parede')]; },
    hud(S) {
      const s0 = S.start('grito5'), tCh = S.c('grito5', 'choque');
      return {
        bar: null, ruler: null,
        alert: { t0: tCh, text: 'LIMITE DO AR: 194 dB' },
        customHud: soundHud({
          badge: 'GRITO 5', badgeT: s0, label: 'ONDA DE CHOQUE',
          db: t => HUD.roll(t, s0, tCh + 0.25, 180, 194, 'lin'), alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito5'), s1 = S.end('grito5');
      const tDb = S.c('grito5', 'decibéis'), tCh = S.c('grito5', 'choque'), tPar = S.c('grito5', 'parede');
      const hitWall = t >= tPar;
      const shake = hits(t, [
        { t: s0, a: 22, d: 0.35 },
        { t: tDb, a: 16, d: 0.3 },
        { t: tCh, a: 42, d: 0.55 },
        { t: tPar, a: 44, d: 0.6 }
      ]) + 8;

      // ceu dramatico vermelho-carmim de climax fisico
      fillScreen(ctx, vGrad(ctx, [[0, '#2B0710'], [0.5, '#7A1121'], [1, '#1A060B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [tCh, 1.18, eBack], [tPar, 1.08], [s1, 1.18]]), shake }, t);
      speedLines(ctx, 290, 960, 32, 120, 1100, '#FF4757', 0.45, t * 0.8);

      // parede de tijolos a direita (limpa a esquerda da regua dB!)
      if (!hitWall) {
        rr(ctx, 600, 480, 225, 820, 10); outlined(ctx, '#A93A2B', 8);
        ctx.strokeStyle = INK; ctx.lineWidth = 5;
        for (let by = 520; by < 1280; by += 56) {
          ctx.beginPath(); ctx.moveTo(600, by); ctx.lineTo(825, by); ctx.stroke();
        }
        // linha de limite fisico 194 dB vibrando
        if (t >= tCh - 0.15) {
          ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 10;
          ctx.beginPath(); ctx.moveTo(582, 460); ctx.lineTo(582, 1320); ctx.stroke();
          glow(ctx, 582, 920, 220, 'rgba(255,212,0,A)', 0.55);
        }
      } else {
        // tijolos voando em explosao!
        const dt = t - tPar;
        for (let i = 0; i < 20; i++) {
          const ang = -0.75 + hash(i * 17) * 1.5;
          const spd = 300 + hash(i * 29) * 560;
          const bx = 635 + Math.cos(ang) * spd * dt;
          const by = 560 + (i % 10) * 68 + Math.sin(ang) * spd * dt + 480 * dt * dt;
          ctx.save(); ctx.translate(bx, by); ctx.rotate(dt * (6 + (i % 4) * 2) + i);
          rr(ctx, -36, -19, 72, 38, 6); outlined(ctx, i % 3 === 0 ? '#D9533F' : '#A93A2B', 5);
          ctx.restore();
        }
        glow(ctx, 635, 920, 420, 'rgba(255,120,40,A)', clamp(0.75 - dt * 0.5, 0.1, 0.75));
      }

      // cone supersonico e ondas atras do Beto
      drawShockwaves(ctx, 305, 945, t, s0, { rings: 6, speed: 1200, maxR: 1100, color: '#FFD400', lw: 20, loop: true, period: 0.25, cycle: 0.9 });
      if (t >= tCh) {
        ctx.save();
        ctx.globalAlpha = 0.78;
        ctx.fillStyle = '#FFFFFF';
        ctx.beginPath(); ctx.moveTo(310, 945); ctx.lineTo(715, 630); ctx.lineTo(715, 1210); ctx.closePath(); ctx.fill();
        ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.stroke();
        ctx.restore();
      }
      drawBeto(ctx, st, { x: 280, y: pelvisFromFeet(1260, 0.96), scale: 0.96, t, rim: { color: '#FFD400', dir: [1, -0.3] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 8. GRITO 7 (DEFESA CIVIL + HELICOPTERO)
  SC.grito7 = {
    keys(S) {
      return [
        { t: S.start('grito7'), pose: 'shock_closeup', expr: 'panic', dur: 0.14, ease: 'back' },
        { t: S.c('grito7', 'helicópteros'), pose: 'look_down', expr: 'shock', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) {
      const tDb = S.c('grito7', 'decibéis'), tDef = S.c('grito7', 'Defesa');
      return [S.c('grito7', '260'), tDb, (tDb + tDef) / 2, tDef, S.c('grito7', 'evacua'), S.c('grito7', 'helicópteros')];
    },
    hud(S) {
      const s0 = S.start('grito7'), tDef = S.c('grito7', 'Defesa');
      return {
        bar: null, ruler: null,
        alert: { t0: tDef, text: 'BAIRRO EVACUADO' },
        customHud: soundHud({
          badge: 'GRITO 7', badgeT: s0, label: 'ALERTA MÁXIMO',
          db: t => HUD.roll(t, s0, s0 + 0.6, 194, 260, 'lin'), alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('grito7'), s1 = S.end('grito7'), tDb = S.c('grito7', 'decibéis'), tHel = S.c('grito7', 'helicópteros');
      const shake = hits(t, [{ t: s0, a: 28, d: 0.45 }, { t: tDb, a: 16, d: 0.3 }, { t: tHel, a: 22, d: 0.45 }]) + 5;
      // ceu noturno de emergencia com sirene azul/vermelha
      fillScreen(ctx, vGrad(ctx, [[0, '#091024'], [0.55, '#1B254B'], [1, '#0F1322']]));
      const sir = Math.sin(t * 16) > 0;
      glow(ctx, sir ? 200 : 840, 560, 440, sir ? 'rgba(255,46,59,A)' : 'rgba(56,189,248,A)', 0.32);

      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tHel, 1.08], [s1, 1.14]]), shake }, t);

      // silhueta de predios do bairro atras
      ctx.fillStyle = '#121A33';
      const bldgs = [[40, 860, 140, 360], [190, 790, 150, 430], [720, 820, 160, 400], [890, 880, 150, 340]];
      for (const b of bldgs) { rr(ctx, b[0], b[1], b[2], b[3], 6); ctx.fill(); }

      // dois helicopteros da Defesa Civil circulando no topo
      drawHelicopter(ctx, 270 + Math.sin(t * 2.5) * 36, 565 + Math.cos(t * 3.2) * 18, 0.92, t, false);
      drawHelicopter(ctx, 760 + Math.cos(t * 2.2) * 32, 615 + Math.sin(t * 2.9) * 16, 0.84, t + 1.3, true);

      // asfalto + casa sem telhado no centro (hideRoof: true evita triangulo atras do HUD!)
      ctx.fillStyle = '#252B3B'; ctx.fillRect(-160, 1140, W + 320, 860);
      drawHouse(ctx, 510, 1020, 1.05, { broken: true, cracks: true, hideRoof: true });
      drawBeto(ctx, st, { x: 510, y: 1120, scale: 0.72, t, rim: { color: sir ? '#FF4757' : '#38BDF8', dir: [0, -1] } });

      // cavalete + faixa amarela DEFESA CIVIL no primeiro plano
      ctx.fillStyle = '#FFD400'; ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.fillRect(60, 1215, 920, 48); ctx.strokeRect(60, 1215, 920, 48);
      for (let sx = 90; sx < 940; sx += 90) {
        ctx.fillStyle = INK; ctx.beginPath();
        ctx.moveTo(sx, 1215); ctx.lineTo(sx + 34, 1215); ctx.lineTo(sx + 10, 1263); ctx.lineTo(sx - 24, 1263); ctx.closePath(); ctx.fill();
      }
      pill(ctx, 510, 1239, 340, 56, '#0B0F19', '#FFD400', 'DEFESA CIVIL', '#FFD400', 34);
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 9. PACTO (SILENCIO ABSOLUTO)
  SC.pacto = {
    keys(S) {
      return [
        { t: S.start('pacto'), pose: COVER_MOUTH, expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('pacto', 'fita'), pose: COVER_MOUTH, expr: 'focus', dur: 0.14, ease: 'back' },
        { t: S.c('pacto', 'silêncio'), pose: SHUSH_POSE, expr: 'determined', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('pacto', 'pânico'), S.c('pacto', 'fita'), S.c('pacto', 'silêncio'), S.c('pacto', 'absoluto')]; },
    hud(S) {
      const s0 = S.start('pacto'), tSil = S.c('pacto', 'silêncio');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({
          badge: 'SILÊNCIO', badgeT: s0, badgeCol: '#74B9FF', label: 'VOLUME TRAVADO',
          value: t => t >= tSil ? '0 dB (MUDO)' : 'TRAVANDO...',
          db: t => t >= tSil ? 0 : HUD.roll(t, s0, tSil, 80, 0, 'lin')
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('pacto'), tFit = S.c('pacto', 'fita'), tSil = S.c('pacto', 'silêncio');
      const shake = hits(t, [{ t: s0, a: 14, d: 0.3 }, { t: tFit, a: 16, d: 0.28 }]);
      // quarto azul-gelo calmo e silencioso (contraste brutal apos o caos!)
      fillScreen(ctx, vGrad(ctx, [[0, '#0E1C36'], [0.6, '#173057'], [1, '#091224']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 940, z: kf(t, [[s0, 1.15], [tFit, 1.38, eBack], [S.end('pacto'), 1.48]]), shake }, t);
      glow(ctx, 500, 860, 360, 'rgba(116,185,255,A)', 0.25);

      const bx = 500, by = 1110;
      drawBeto(ctx, st, { x: bx, y: by, scale: 1.05, t, rim: { color: '#74B9FF', dir: [0.6, -0.7] } });

      // fita adesiva prateada em X colada exatamente sobre a boca (olhos 100% livres!)
      if (t >= tFit - 0.05) {
        const tk = eBack(clamp((t - tFit + 0.05) / 0.22, 0, 1));
        const mouthY = by - 118 * 1.05;
        ctx.save(); ctx.translate(bx, mouthY); ctx.scale(tk, tk);
        for (const ang of [-0.24, 0.24]) {
          ctx.save(); ctx.rotate(ang);
          rr(ctx, -44, -10, 88, 20, 4); outlined(ctx, '#D1D5DB', 4);
          ctx.strokeStyle = '#9CA3AF'; ctx.lineWidth = 2.5;
          ctx.beginPath(); ctx.moveTo(-32, 0); ctx.lineTo(32, 0); ctx.stroke();
          ctx.restore();
        }
        ctx.restore();
      }
      if (t >= tSil) {
        const scS = eBack(clamp((t - tSil) / 0.24, 0, 1));
        ctx.save(); ctx.translate(500, 560); ctx.scale(scS, scS);
        pill(ctx, 0, 0, 360, 82, '#0B162C', '#74B9FF', 'SHHH! 0 dB', '#74B9FF', 42);
        ctx.restore();
      }
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. TWIST A (SUSPENSE)
  SC.twist_a = {
    keys(S) {
      return [
        { t: S.start('twist_a'), pose: COVER_MOUTH, expr: 'focus', dur: 0.18, ease: 'inout' },
        { t: S.c('twist_a', 'reflexo'), pose: COVER_MOUTH, expr: 'panic', dur: 0.22, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('twist_a', 'existe'), S.c('twist_a', 'reflexo'), S.c('twist_a', 'controlar')]; },
    hud(S) {
      const s0 = S.start('twist_a');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({ badge: 'CUIDADO', badgeT: s0, badgeCol: '#FF2E3B', label: 'REFLEXO HUMANO', value: 'ARMADILHA', db: 0, alert: true, hideGauge: true })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), s1 = S.end('twist_a');
      const k = clamp((t - s0) / Math.max(0.1, s1 - s0), 0, 1);
      // noir dramatico fechando foco no Beto com fita na boca
      fillScreen(ctx, vGrad(ctx, [[0, '#07090F'], [0.55, '#190D16'], [1, '#05060A']]));
      const pulse = 0.5 + 0.5 * Math.sin(t * 14);
      glow(ctx, 540, 860, 420, 'rgba(255,46,59,A)', 0.16 + 0.22 * k * pulse);

      ctx.save();
      const z = kf(t, [[s0, 1.45], [s1, 1.85, eIn]]);
      const bx = 540, by = 1140;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.78);
      camApply(ctx, { x: bx, y: headY + 110 / z, z, shake: 2 + k * 9 }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1.0, t, rim: { color: '#FF2E3B', dir: [0, -1] } });
      // fita em X exatamente sobre a boca (olhos arregalados 100% visiveis!)
      const mouthY = by - 118;
      ctx.save(); ctx.translate(bx + vnoise(t * 35) * 2, mouthY);
      for (const ang of [-0.24, 0.24]) {
        ctx.save(); ctx.rotate(ang);
        rr(ctx, -42, -9.5, 84, 19, 4); outlined(ctx, '#D1D5DB', 4);
        ctx.restore();
      }
      ctx.restore();
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. TWIST B (PAYOFF COMICO NUCLEAR!)
  SC.twist_b = {
    keys(S) {
      return [
        { t: S.start('twist_b'), pose: 'idle', expr: 'neutral', dur: 0.14, ease: 'inout' },
        { t: S.c('twist_b', 'automático'), pose: 'shock_closeup', expr: 'shock', dur: 0.12, ease: 'back' },
        { t: S.c('twist_b', 'berra'), pose: YELL_WIDE, expr: 'scream', dur: 0.12, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('twist_b', 'mãe'), S.c('twist_b', 'café'), S.c('twist_b', 'automático'), S.c('twist_b', 'berra'), S.c('twist_b', 'INDO')]; },
    hud(S) {
      const s0 = S.start('twist_b'), tBer = S.c('twist_b', 'berra');
      return {
        bar: null, ruler: null,
        alert: { t0: tBer, text: 'REFLEXO FATAL' },
        customHud: soundHud({
          badge: 'GRITO 8', badgeT: tBer, label: 'ONDA SUPERSÔNICA',
          value: t => t < tBer ? '0 dB -> ???' : '320 dB!',
          db: t => t < tBer ? 40 : HUD.roll(t, tBer, tBer + 0.35, 60, 275, 'lin'),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_b'), s1 = S.end('twist_b');
      const tAuto = S.c('twist_b', 'automático'), tBer = S.c('twist_b', 'berra'), tIndo = S.c('twist_b', 'INDO');

      if (t < tAuto) {
        // Beat 1: Manha ensolarada: mae aparece na porta com bule de cafe gritando!
        fillScreen(ctx, vGrad(ctx, [[0, '#FFF1C9'], [0.6, '#FFD28E'], [1, '#C98A54']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tAuto, 1.15]]), shake: hits(t, [{ t: s0, a: 14, d: 0.25 }]) }, t);
        // porta + corredor claro
        rr(ctx, 210, 520, 380, 680, 10); outlined(ctx, '#FFF9EE', 9);
        rr(ctx, 236, 546, 328, 654, 6); outlined(ctx, '#F5DEC0', 6);
        drawMom(ctx, 410, 960, 1.45, { yell: true, holdPot: true });
        const scC = eBack(clamp((t - s0) / 0.22, 0, 1));
        drawSpeechBurst(ctx, 560, 585, 'O CAFÉ ESFRIOU!', scC, '#FFFFFF', '#E8322A', 'left');
        ctx.restore();
        return;
      }

      // Beat 2 & 3: Fita rasga no automatico e Beto solta o JÁ TÔ INDO apocaliptico!
      const blasted = t >= tBer;
      const shake = hits(t, [
        { t: tAuto, a: 18, d: 0.3 },
        { t: tBer, a: 42, d: 0.55 },
        { t: tIndo, a: 46, d: 0.7 }
      ]) + (blasted ? 14 : 4);

      fillScreen(ctx, blasted
        ? vGrad(ctx, [[0, '#FF4757'], [0.45, '#FF9F1A'], [1, '#2D070F']])
        : vGrad(ctx, [[0, '#1B2845'], [0.6, '#274060'], [1, '#0B132B']])
      );
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[tAuto, 1.15], [tBer, 1.32, eBack], [tIndo, 1.05], [s1, 1.22]]), shake }, t);

      if (blasted) {
        speedLines(ctx, 500, 900, 38, 120, 1250, '#FFFFFF', 0.58, t * 1.4);
        glow(ctx, 500, 900, 560, 'rgba(255,255,255,A)', 0.55);
        // ondas sonoras atras do Beto para manter o rosto 100% nitido!
        drawShockwaves(ctx, 490, 960, t, tBer, { rings: 7, speed: 1380, maxR: 1300, color: '#FFD400', lw: 24, loop: true, period: 0.22, cycle: 0.88 });
      }

      // fita adesiva rasgada voando pro lado (limpa a esquerda da regua dB)
      const ripDt = clamp((t - tAuto) / 0.45, 0, 1);
      ctx.save();
      ctx.translate(540 + ripDt * 220, 860 - ripDt * 185);
      ctx.rotate(ripDt * 5.2);
      rr(ctx, -46, -12, 92, 24, 5); outlined(ctx, '#D1D5DB', 5);
      ctx.restore();

      drawBeto(ctx, st, { x: 490, y: 1120, scale: 1.06, t, rim: { color: '#FFFFFF', dir: [0, -1] } });

      if (blasted) {
        // caneca de cafe com alca e liquido escuro voando a esquerda da regua!
        const fly = clamp((t - tBer) / 0.9, 0, 1);
        ctx.save(); ctx.translate(215 - fly * 85, 860 - fly * 165); ctx.rotate(-fly * 4.2);
        ctx.strokeStyle = INK; ctx.lineWidth = 10;
        ctx.beginPath(); ctx.arc(28, 0, 16, -Math.PI * 0.5, Math.PI * 0.5); ctx.stroke();
        rr(ctx, -28, -28, 56, 56, 10); outlined(ctx, '#FFFFFF', 6);
        ctx.fillStyle = '#4A2511'; ctx.fillRect(-20, -22, 40, 12);
        ctx.restore();
        const scB = eBack(clamp((t - tBer) / 0.18, 0, 1));
        drawSpeechBurst(ctx, 490, 575, 'JÁ TÔ INDO!!', scB * 1.18, '#FFD400', '#E8322A', 'center');
      }
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 12. LOOP (CTA FALADA!)
  SC.loop = {
    keys(S) {
      return [
        { t: S.start('loop'), pose: 'shrug_question', expr: 'curious', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'chinela'), pose: 'dodge_lean', expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'Comenta'), pose: 'point_hook', expr: 'smug', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('loop', 'gritos'), S.c('loop', 'mãe'), S.c('loop', 'chinela'), S.c('loop', 'Comenta')]; },
    hud(S) {
      const s0 = S.start('loop');
      return {
        bar: null, ruler: null, alert: null,
        customHud: soundHud({
          badge: 'SUA VEZ', badgeT: s0, badgeCol: '#FFD400',
          label: 'DESAFIO DA CHINELA', value: 'COMENTE AÍ', db: 150, hideGauge: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop');
      const tChi = S.c('loop', 'chinela'), tCom = S.c('loop', 'Comenta');
      // fundo dividido vibrante: ESQUERDA DOURADO-LARANJA (1 GRITO) vs DIREITA CARMIM (5 GRITOS)
      ctx.fillStyle = vGrad(ctx, [[0, '#D97706'], [1, '#78350F']]); ctx.fillRect(0, 0, W / 2, H);
      ctx.fillStyle = vGrad(ctx, [[0, '#C81E2B'], [1, '#5B0B14']]); ctx.fillRect(W / 2, 0, W / 2, H);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();

      const z = kf(t, [[s0, 1.38], [tChi, 1.56, eBack], [tCom, 1.72, eBack], [s1, 1.85, eIn]]);
      const shake = hits(t, [{ t: s0, a: 18, d: 0.35 }, { t: tChi, a: 26, d: 0.4 }, { t: tCom, a: 16, d: 0.3 }]) + 2;
      const bx = 540, by = 1170;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);

      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 150 / z, z, shake }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1.0, t, rim: { color: '#FFD400', dir: [0.8, -0.6] } });
      ctx.restore();

      // chinelas voando nos flancos em espaco de tela (100% abaixo das placas de escolha!)
      const chSpin = t * 5.2;
      drawChinela(ctx, 180, 1080 + Math.sin(t * 7) * 26, 1.05, -0.45 + Math.sin(chSpin) * 0.35);
      drawChinela(ctx, 900, 1080 + Math.cos(t * 7) * 26, 1.05, 0.45 - Math.sin(chSpin) * 0.35);

      // duas placas de escolha limpas no topo (100% sem sobreposicao!)
      pill(ctx, 270, 355, 360, 78, '#2E1504', '#FFD400', '1 GRITO: CHINELA', '#FFD400', 34);
      pill(ctx, 810, 355, 360, 78, '#2D070C', '#FFFFFF', '5 GRITOS: CAOS', '#FFFFFF', 34);
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
