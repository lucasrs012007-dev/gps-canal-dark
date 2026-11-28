/*
 * ep06_espirro_idade/scenes.js : Episodio 6 ("E se cada espirro te deixasse 1 ano mais jovem?")
 * 12 cenarios originais de ritmo ultra-rapido (61s-65s) em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
 * Traz HUD de idade biologica regressiva (30 ANOS -> 0 ANOS) com barra de vida em 10 blocos,
 * regua vertical de idade na borda direita, rajadas visiveis de espirro, nuvens de polen,
 * transformacao fisica de escala do Beto ate desaparecer deixando o moletom vazio no chao.
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
  B.POSES.back_ache = Object.assign({}, B.POSES.idle, {
    crouch: 14, lean: 18, head: 14, headDY: 6,
    ua_r: -18, la_r: -65, hand_r: 0,
    ua_l: 22, la_l: 12, th_r: 22, sh_r: -8, th_l: 22, sh_l: -8
  });
  B.POSES.sneeze_inhale = Object.assign({}, B.POSES.idle, {
    crouch: 4, lean: -16, head: -22, headDY: -6,
    ua_r: 105, la_r: 138, ua_l: 105, la_l: 138, hand_r: 0, hand_l: 0
  });
  B.POSES.sneeze_burst = Object.assign({}, B.POSES.idle, {
    crouch: 18, lean: 24, head: 24, headDY: 8,
    ua_r: 124, la_r: 144, ua_l: 124, la_l: 144,
    th_r: 20, sh_r: -4, th_l: 20, sh_l: -4
  });
  B.POSES.cover_nose = Object.assign({}, B.POSES.idle, {
    crouch: 8, lean: -4, head: 4,
    ua_r: 44, la_r: -132, hand_r: 0,
    ua_l: 44, la_l: -132, hand_l: 0
  });
  B.POSES.sniff_pose = Object.assign({}, B.POSES.idle, {
    lean: 12, head: 12, ua_r: 68, la_r: 132, hand_r: 1, ua_l: 24, la_l: 10
  });
  B.POSES.reach_up = Object.assign({}, B.POSES.idle, {
    lean: -4, head: -14, ua_r: 162, la_r: 174, ua_l: 152, la_l: 166,
    th_r: 8, sh_r: 2, th_l: 12, sh_l: -2
  });

  const BACK_ACHE = 'back_ache';
  const SNEEZE_INHALE = 'sneeze_inhale';
  const SNEEZE_BURST = 'sneeze_burst';
  const COVER_NOSE = 'cover_nose';
  const SNIFF_POSE = 'sniff_pose';
  const REACH_UP = 'reach_up';

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

  // ----------------------------------------- HUD custom (Idade Biologica 30 -> 0)
  const AGE_MARKS = [
    { v: 30, txt: '30a' },
    { v: 20, txt: '20a' },
    { v: 10, txt: '10a' },
    { v: 5, txt: '5a' },
    { v: 0, txt: '0a' }
  ];
  function ageColor(age) {
    if (age <= 3) return '#FF2E3B';
    if (age <= 10) return '#FF7A29';
    if (age <= 17) return '#FFD400';
    return '#2ED573';
  }
  function fmtAge(a) {
    const n = Math.max(0, Math.round(a));
    if (n === 1) return '1 ANO';
    if (n === 0) return '0 ANOS!';
    return n + ' ANOS';
  }
  function ageHud(opts) {
    return function drawAgeHud(ctx, t) {
      const age = clamp(typeof opts.age === 'function' ? opts.age(t) : opts.age, 0, 30);
      const isAlert = !!opts.alert || age <= 6;
      const pulse = isAlert ? 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 2.6) : 0;

      // 1. PAINEL SUPERIOR (y=124, h=158, borda completa nos 4 lados)
      if (!opts.hideTop) {
        const y = 124, h = 158, padX = 24, gap = 22;
        const badgeTxt = opts.badge || 'ESPIRRO 1';
        const labTxt = opts.label || 'IDADE BIOLÓGICA';
        const valTxt = opts.value !== undefined
          ? (typeof opts.value === 'function' ? opts.value(t) : opts.value)
          : fmtAge(age);

        ctx.save();
        ctx.font = `54px ${HUD.FONT_DISPLAY}`;
        const bw = Math.max(ctx.measureText('ESPIRRO 30').width, ctx.measureText(badgeTxt).width) + 40;
        ctx.font = `30px ${HUD.FONT_DISPLAY}`;
        const lw = ctx.measureText(labTxt).width;
        ctx.font = `66px ${HUD.FONT_DISPLAY}`;
        const vw = Math.max(ctx.measureText(valTxt).width, 260);
        const rightW = Math.max(lw, vw, 300);
        const totalW = Math.min(960, padX + bw + gap + rightW + padX);
        const x = (W - totalW) / 2;

        rr(ctx, x, y, totalW, h, 28);
        ctx.fillStyle = 'rgba(11,15,25,0.85)'; ctx.fill();
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

        // coluna direita: rotulo + valor + barra de idade em 10 blocos
        const rx = bx + bw + gap;
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        ctx.font = `28px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? '#FF8A92' : '#A9BCE0';
        ctx.fillText(labTxt, rx, y + 40);

        ctx.font = `64px ${HUD.FONT_DISPLAY}`;
        ctx.fillStyle = isAlert ? (pulse > 0.5 ? '#FFFFFF' : '#FFD0D4') : '#FFFFFF';
        ctx.fillText(valTxt, rx, y + 105);

        const segs = 10, segGap = 6, barW = rightW - 6, segW = (barW - segGap * (segs - 1)) / segs;
        const barY = y + 122, barH = 18;
        const normAge = clamp(age / 30, 0, 1);
        const activeCount = age <= 0.05 ? 0 : Math.max(1, Math.round(normAge * segs));
        for (let i = 0; i < segs; i++) {
          const sx = rx + i * (segW + segGap);
          const col = i < 2 ? '#FF2E3B' : (i < 4 ? '#FF7A29' : (i < 6 ? '#FFD400' : '#2ED573'));
          rr(ctx, sx, barY, segW, barH, 4);
          ctx.fillStyle = i < activeCount ? col : 'rgba(255,255,255,0.14)';
          ctx.fill();
        }
        ctx.restore();
      }

      // 2. REGUA VERTICAL DE IDADE (30a no topo -> 0a na base, borda direita x=1012)
      if (!opts.hideGauge) {
        const x = 1012, y0 = 1080, y1 = 420;
        const yOf = v => y0 - (clamp(v, 0, 30) / 30) * (y0 - y1);
        const vib = (opts.vibrate && age <= 12) ? vnoise(t * 44) * clamp((14 - age) / 2.2, 1, 6) : 0;

        ctx.save();
        ctx.translate(vib, 0);
        rr(ctx, x - 14, y1 - 24, 28, y0 - y1 + 48, 14);
        ctx.fillStyle = 'rgba(11,15,25,0.78)'; ctx.fill();
        ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.82)'; ctx.stroke();

        const ym = yOf(age);
        const fillH = Math.max(0, y0 + 10 - ym);
        if (age > 0.05 && fillH > 2) {
          rr(ctx, x - 7, ym, 14, fillH, 7);
          ctx.fillStyle = ageColor(age); ctx.fill();
        }

        ctx.font = `24px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (const mk of AGE_MARKS) {
          const yy = yOf(mk.v);
          ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
          ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
          ctx.strokeText(mk.txt, x - 32, yy + 1);
          ctx.fillStyle = mk.v <= 5 ? '#FF6B6B' : 'rgba(255,255,255,0.96)';
          ctx.fillText(mk.txt, x - 32, yy + 1);
        }

        // losango indicador
        ctx.save(); ctx.translate(x, ym);
        ctx.beginPath(); ctx.moveTo(0, -18); ctx.lineTo(18, 0); ctx.lineTo(0, 18); ctx.lineTo(-18, 0); ctx.closePath();
        ctx.fillStyle = ageColor(age); ctx.fill();
        ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
        ctx.restore();
        ctx.restore();
      }
    };
  }

  // ------------------------------------------------ props e efeitos 2D tematicos
  /** Balao de impacto de espirro ou fala curta ("ATCHIM!!", "-1 ANO"). */
  function drawBurstBalloon(ctx, x, y, txt, scale, bgCol, txtCol, tailDir) {
    if (scale <= 0.02) return;
    ctx.save();
    ctx.translate(x, y); ctx.scale(scale, scale);
    ctx.font = `50px ${HUD.FONT_DISPLAY}`;
    const tw = ctx.measureText(txt).width;
    const bw = tw + 64, bh = 86;
    ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.lineCap = 'round';
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2 + 0.25;
      ctx.beginPath();
      ctx.moveTo(Math.cos(ang) * (bw * 0.56), Math.sin(ang) * (bh * 0.65));
      ctx.lineTo(Math.cos(ang) * (bw * 0.72), Math.sin(ang) * (bh * 0.98));
      ctx.stroke();
    }
    rr(ctx, -bw / 2, -bh / 2, bw, bh, 22);
    outlined(ctx, bgCol || '#FFFFFF', 7);
    if (tailDir) {
      const tx = tailDir === 'left' ? -bw * 0.26 : (tailDir === 'right' ? bw * 0.26 : 0);
      ctx.beginPath();
      ctx.moveTo(tx - 16, bh / 2 - 4);
      ctx.lineTo(tx + (tailDir === 'left' ? -26 : (tailDir === 'right' ? 26 : 0)), bh / 2 + 28);
      ctx.lineTo(tx + 18, bh / 2 - 4);
      ctx.closePath();
      outlined(ctx, bgCol || '#FFFFFF', 7);
      ctx.fillStyle = bgCol || '#FFFFFF';
      ctx.fillRect(tx - 15, bh / 2 - 8, 32, 10);
    }
    label(ctx, txt, 0, 3, 46, txtCol || INK);
    ctx.restore();
  }

  /** Estrelas brilhantes de rejuvenescimento ao redor do Beto. */
  function drawSparkles(ctx, cx, cy, t, count, radius, col) {
    ctx.save();
    for (let i = 0; i < count; i++) {
      const ang = (i / count) * Math.PI * 2 + t * 0.9;
      const r = radius * (0.65 + 0.35 * hash(i * 17));
      const sx = cx + Math.cos(ang) * r;
      const sy = cy + Math.sin(ang) * r * 0.75 - ((t * 45 + i * 23) % 70);
      const pulse = 0.5 + 0.5 * Math.sin(t * 7 + i * 1.9);
      const sz = (12 + hash(i * 31) * 14) * (0.6 + 0.5 * pulse);
      ctx.save();
      ctx.translate(sx, sy); ctx.rotate(t * 1.5 + i);
      ctx.beginPath();
      for (let p = 0; p < 8; p++) {
        const a = (p / 8) * Math.PI * 2;
        const rr2 = p % 2 === 0 ? sz : sz * 0.34;
        p === 0 ? ctx.moveTo(Math.cos(a) * rr2, Math.sin(a) * rr2) : ctx.lineTo(Math.cos(a) * rr2, Math.sin(a) * rr2);
      }
      ctx.closePath();
      outlined(ctx, col || '#FFD400', 4);
      ctx.restore();
    }
    ctx.restore();
  }

  /** Nuvem/rajada radial de espirro visivel no mudo. */
  function drawSneezeBlast(ctx, x, y, t, tStart, col) {
    const dt = t - tStart;
    if (dt < 0 || dt > 1.1) return;
    const k = clamp(dt / 0.85, 0, 1);
    const a = 1 - k;
    ctx.save();
    for (let i = 0; i < 3; i++) {
      const r = 36 + Math.max(0, dt - i * 0.08) * 680;
      if (r > 720) continue;
      ctx.globalAlpha = clamp(1 - r / 720, 0, 1) * 0.85;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.lineWidth = 14; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 8; ctx.strokeStyle = i % 2 === 0 ? (col || '#FFD400') : '#FFFFFF'; ctx.stroke();
    }
    // goticulas de espirro
    for (let j = 0; j < 10; j++) {
      const ang = -0.8 + (j / 9) * 1.6 + (hash(j * 7) - 0.5) * 0.3;
      const dist = 60 + k * (260 + hash(j * 13) * 180);
      const px = x + Math.cos(ang) * dist;
      const py = y + Math.sin(ang) * dist;
      ctx.globalAlpha = a;
      ctx.beginPath(); ctx.arc(px, py, 10 * (1 - k * 0.4), 0, Math.PI * 2);
      outlined(ctx, '#E0F7FA', 4);
    }
    ctx.restore();
  }

  /** Grao de polen estilizado com pontas (amarelo-ouro com contorno grosso). */
  function drawPollenGrain(ctx, x, y, r, rot, glowAlpha) {
    ctx.save();
    ctx.translate(x, y); ctx.rotate(rot || 0);
    if (glowAlpha) glow(ctx, 0, 0, r * 2.4, 'rgba(255,212,0,A)', glowAlpha);
    // pontas radiais
    const spikes = 10;
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(3, r * 0.24); ctx.lineCap = 'round';
    for (let i = 0; i < spikes; i++) {
      const a = (i / spikes) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r * 0.75, Math.sin(a) * r * 0.75);
      ctx.lineTo(Math.cos(a) * r * 1.38, Math.sin(a) * r * 1.38);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(Math.cos(a) * r * 1.4, Math.sin(a) * r * 1.4, Math.max(2.5, r * 0.16), 0, Math.PI * 2);
      outlined(ctx, '#FFE066', Math.max(2, r * 0.12));
    }
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2);
    outlined(ctx, '#FFD400', Math.max(3, r * 0.18));
    // brilho interno
    ctx.beginPath(); ctx.arc(-r * 0.28, -r * 0.28, r * 0.28, 0, Math.PI * 2);
    ctx.fillStyle = '#FFF7C2'; ctx.fill();
    ctx.restore();
  }

  /** Chuva de graos de polen flutuando pela tela. */
  function drawPollenStorm(ctx, t, count, speedX, speedY, rMin, rMax) {
    for (let i = 0; i < count; i++) {
      const px = ((hash(i * 19) * 1400 + t * (speedX || 180) * (0.7 + hash(i * 31) * 0.6)) % 1300) - 110;
      const py = ((hash(i * 43) * 1500 + Math.sin(t * 2.4 + i) * 55 + t * (speedY || 40)) % 1350) + 220;
      const r = lerp(rMin || 10, rMax || 22, hash(i * 53));
      drawPollenGrain(ctx, px, py, r, t * (1.2 + hash(i * 61)) * (i % 2 ? 1 : -1), 0.28);
    }
  }

  /** Pimenteiro gigante estilo desenho animado. */
  function drawPepperShaker(ctx, x, y, s, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    // corpo vermelho/preto
    rr(ctx, -46, -54, 92, 124, 22); outlined(ctx, '#262B38', 7);
    rr(ctx, -38, -22, 76, 62, 10); outlined(ctx, '#E8322A', 5);
    label(ctx, 'PIMENTA', 0, 10, 22, '#FFD400');
    // tampa metalica furada
    ctx.beginPath(); ctx.arc(0, -54, 42, Math.PI, 0); ctx.closePath();
    outlined(ctx, '#D1D5DB', 7);
    for (const dx of [-18, 0, 18]) {
      ctx.beginPath(); ctx.arc(dx, -72, 4, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
    }
    ctx.restore();
  }

  /** Pregador de roupa de madeira (icone da sobrevivencia!). */
  function drawClothespin(ctx, x, y, s, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0); ctx.scale(s, s);
    // duas hastes de madeira
    rr(ctx, -18, -74, 15, 148, 6); outlined(ctx, '#E3A857', 5);
    rr(ctx, 3, -74, 15, 148, 6); outlined(ctx, '#C98A3A', 5);
    // mola metalica no centro
    rr(ctx, -22, -14, 44, 24, 8); outlined(ctx, '#CBD5E1', 5);
    ctx.beginPath(); ctx.arc(0, -2, 8, 0, Math.PI * 2); outlined(ctx, '#64748B', 4);
    ctx.restore();
  }

  /** Chefe bravo de gravata no escritorio (manda Beto estudar!). */
  function drawBoss(ctx, x, y, s, pointDir) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    const dir = pointDir || 1;
    // pernas
    ctx.strokeStyle = INK; ctx.lineWidth = 18; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-22, 56); ctx.lineTo(-24, 134); ctx.moveTo(22, 56); ctx.lineTo(24, 134); ctx.stroke();
    // terno cinza escuro
    rr(ctx, -56, -54, 112, 118, 24); outlined(ctx, '#2C3A57', 7);
    // camisa branca + gravata vermelha
    ctx.beginPath(); ctx.moveTo(-22, -52); ctx.lineTo(22, -52); ctx.lineTo(0, 16); ctx.closePath();
    outlined(ctx, '#FFFFFF', 5);
    ctx.beginPath(); ctx.moveTo(-8, -46); ctx.lineTo(8, -46); ctx.lineTo(12, 22); ctx.lineTo(0, 36); ctx.lineTo(-12, 22); ctx.closePath();
    outlined(ctx, '#E8322A', 4);
    // braco apontando pro lado da escola
    ctx.strokeStyle = INK; ctx.lineWidth = 30;
    ctx.beginPath(); ctx.moveTo(dir * 52, -26); ctx.lineTo(dir * 136, -34); ctx.stroke();
    ctx.strokeStyle = '#2C3A57'; ctx.lineWidth = 18;
    ctx.beginPath(); ctx.moveTo(dir * 52, -26); ctx.lineTo(dir * 136, -34); ctx.stroke();
    ctx.beginPath(); ctx.arc(dir * 144, -34, 15, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 5);
    // cabeca careca/lateral + oculos + bigode bravo
    ctx.beginPath(); ctx.arc(0, -108, 52, 0, Math.PI * 2); outlined(ctx, '#F4B98C', 7);
    // cabelo lateral grisalho
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.arc(side * 50, -112, 14, 0, Math.PI * 2); outlined(ctx, '#64748B', 5);
    }
    // olhos e sobrancelhas bravas
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.arc(side * 18, -110, 13, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 5);
      ctx.beginPath(); ctx.arc(side * 18 + dir * 4, -109, 5, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
      ctx.strokeStyle = INK; ctx.lineWidth = 7;
      ctx.beginPath(); ctx.moveTo(side * 32, -132); ctx.lineTo(side * 6, -122); ctx.stroke();
    }
    // bigode + boca gritando
    rr(ctx, -28, -90, 56, 14, 7); outlined(ctx, '#475569', 4);
    ctx.beginPath(); ctx.ellipse(0, -72, 16, 11, 0, 0, Math.PI * 2); outlined(ctx, '#5E1117', 5);
    ctx.restore();
  }

  /** Moletom vermelho vazio e tenis caidos no chao (payoff final 0 ANOS!). */
  function drawEmptyHoodie(ctx, x, y, s) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    contactShadow(ctx, 0, 32, 135, 0.36);
    // tenis vazios ao lado
    ctx.beginPath(); ctx.ellipse(-74, 24, 28, 14, -0.25, 0, Math.PI * 2); outlined(ctx, '#F5F2EA', 6);
    ctx.beginPath(); ctx.ellipse(76, 20, 28, 14, 0.22, 0, Math.PI * 2); outlined(ctx, '#F5F2EA', 6);
    // calca dobrada
    rr(ctx, -64, 4, 128, 28, 12); outlined(ctx, '#2A3658', 6);
    // moletom vermelho murcho em pilha
    ctx.beginPath();
    ctx.moveTo(-98, 18);
    ctx.quadraticCurveTo(-76, -34, -28, -28);
    ctx.quadraticCurveTo(0, -44, 34, -26);
    ctx.quadraticCurveTo(86, -30, 102, 18);
    ctx.quadraticCurveTo(0, 36, -98, 18);
    ctx.closePath();
    outlined(ctx, '#E8322A', 7);
    // capuz vazio aberto
    ctx.beginPath(); ctx.ellipse(0, -24, 42, 18, 0, 0, Math.PI * 2); outlined(ctx, '#B01E19', 6);
    // cordoes brancos caidos
    ctx.strokeStyle = INK; ctx.lineWidth = 9; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-14, -14); ctx.quadraticCurveTo(-30, 6, -24, 24);
    ctx.moveTo(14, -14); ctx.quadraticCurveTo(28, 8, 20, 26); ctx.stroke();
    ctx.strokeStyle = '#F5F2EA'; ctx.lineWidth = 4.5;
    ctx.beginPath(); ctx.moveTo(-14, -14); ctx.quadraticCurveTo(-30, 6, -24, 24);
    ctx.moveTo(14, -14); ctx.quadraticCurveTo(28, 8, 20, 26); ctx.stroke();
    ctx.restore();
  }

  /** Nuvem de poof cartoon quando Beto some no Espirro 30. */
  function drawPoofCloud(ctx, x, y, k) {
    if (k <= 0 || k >= 1) return;
    const a = 1 - k;
    ctx.save(); ctx.translate(x, y); ctx.globalAlpha = a;
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2 + 0.3;
      const d = 24 + k * 140;
      const r = (54 - k * 24) * (0.8 + hash(i * 13) * 0.4);
      ctx.beginPath(); ctx.arc(Math.cos(ang) * d, Math.sin(ang) * d, Math.max(8, r), 0, Math.PI * 2);
      outlined(ctx, '#FFFFFF', 5);
    }
    ctx.restore();
  }

  // ============================================================== 12 CENAS
  const SC = {};

  // ----------------------------------------------------------------- 1. HOOK
  SC.hook = {
    keys(S) {
      return [
        { t: S.start('hook'), pose: 'flex', expr: 'amazed', dur: 0.16, ease: 'back' },
        { t: S.c('hook', 'rinite'), pose: SNEEZE_INHALE, expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('hook', 'atacar'), pose: SNEEZE_BURST, expr: 'scream', dur: 0.12, ease: 'back' },
        { t: S.c('hook', 'sumir'), pose: 'freefall_scream', expr: 'panic', dur: 0.14, ease: 'inout' }
      ];
    },
    ev(S) {
      return [S.c('hook', 'sonho'), S.c('hook', 'eterna'), S.c('hook', 'rinite'), S.c('hook', 'atacar'), S.c('hook', 'sumir')];
    },
    hud(S) {
      const s0 = S.start('hook'), tRin = S.c('hook', 'rinite'), tSum = S.c('hook', 'sumir');
      return {
        bar: null, ruler: null,
        alert: { t0: tRin, text: 'RINITE DETECTADA' },
        customHud: ageHud({
          badge: 'E SE...?', badgeT: s0,
          label: 'IDADE BIOLÓGICA',
          age: t => t < tRin ? 25 : HUD.roll(t, tRin, tSum + 0.35, 25, 0, 'lin'),
          alert: false, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('hook'), s1 = S.end('hook');
      const tRin = S.c('hook', 'rinite'), tAta = S.c('hook', 'atacar'), tSum = S.c('hook', 'sumir');
      const chaos = t >= tRin;
      const shake = hits(t, [
        { t: tRin, a: 22, d: 0.32 },
        { t: tAta, a: 36, d: 0.45 },
        { t: tSum, a: 34, d: 0.55 }
      ]);

      fillScreen(ctx, chaos
        ? vGrad(ctx, [[0, '#7A1C24'], [0.5, '#D97706'], [1, '#1C1018']])
        : vGrad(ctx, [[0, '#0F766E'], [0.55, '#10B981'], [1, '#064E3B']])
      );

      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tRin, 1.08], [tAta, 1.24, eBack], [s1, 1.12]]), shake }, t);

      if (!chaos) {
        speedLines(ctx, 520, 960, 26, 200, 960, '#A7F3D0', 0.35, t * 0.6);
        glow(ctx, 520, 920, 440, 'rgba(255,212,0,A)', 0.32);
        drawSparkles(ctx, 520, 900, t, 8, 250, '#FFD400');
        contactShadow(ctx, 520, 1220, 145, 0.32);
        drawBeto(ctx, st, { x: 520, y: pelvisFromFeet(1220, 1.15), scale: 1.15, t, rim: { color: '#FFD400', dir: [0.6, -0.8] } });
        pill(ctx, 520, 470, 480, 82, '#064E3B', '#FFD400', 'JUVENTUDE ETERNA!', '#FFD400', 42);
      } else {
        speedLines(ctx, 500, 960, 32, 160, 1100, '#FFE066', 0.45, -t * 1.6);
        drawPollenStorm(ctx, t, 18, 360, 80, 12, 28);
        const scBeto = kf(t, [[tRin, 1.08], [tAta, 0.72, eOut], [tSum, 0.25, eIn], [tSum + 0.35, 0.0, eIn]]);
        if (scBeto > 0.03) {
          contactShadow(ctx, 500, 1220, 130 * scBeto, 0.32);
          drawBeto(ctx, st, { x: 500, y: pelvisFromFeet(1220, scBeto), scale: scBeto, t, rim: { color: '#FFD400', dir: [-0.8, -0.5] } });
        } else {
          drawEmptyHoodie(ctx, 500, 1190, 0.95);
        }
        drawSneezeBlast(ctx, 520, 900, t, tAta, '#FFD400');
        drawPoofCloud(ctx, 500, 1120, clamp((t - tSum) / 0.65, 0, 1));
        if (t >= tAta && t < tSum + 0.2) {
          const pop = eBack(clamp((t - tAta) / 0.16, 0, 1));
          drawBurstBalloon(ctx, 490, 560, 'ATCHIM!!', pop * 1.15, '#FFD400', '#E8322A', 'center');
        }
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 2. PREMISSA
  SC.premissa = {
    keys(S) {
      return [
        { t: S.start('premissa'), pose: 'idle', expr: 'neutral', dur: 0.16, ease: 'inout' },
        { t: S.c('premissa', 'regra'), pose: 'point_hook', expr: 'curious', dur: 0.16, ease: 'back' },
        { t: S.c('premissa', 'espirro'), pose: SNEEZE_BURST, expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('premissa', 'jovem'), pose: 'jump_up', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('premissa', 'anos'), S.c('premissa', 'regra'), S.c('premissa', 'espirro'), S.c('premissa', 'jovem')]; },
    hud(S) {
      const s0 = S.start('premissa'), tEsp = S.c('premissa', 'espirro');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'REGRA', badgeT: s0, badgeCol: '#FFD400',
          label: 'IDADE INICIAL',
          age: t => t < tEsp ? 30 : HUD.roll(t, tEsp, tEsp + 0.35, 30, 29, 'lin')
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), s1 = S.end('premissa');
      const tReg = S.c('premissa', 'regra'), tEsp = S.c('premissa', 'espirro'), tJov = S.c('premissa', 'jovem');
      fillScreen(ctx, vGrad(ctx, [[0, '#1E293B'], [0.6, '#334155'], [1, '#0F172A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tReg, 1.06], [tEsp, 1.14, eBack], [s1, 1.04]]), shake: hits(t, [{ t: tReg, a: 14, d: 0.24 }, { t: tEsp, a: 22, d: 0.3 }]) }, t);

      // piso do estudio
      ctx.fillStyle = '#0F172A'; ctx.fillRect(-100, 1210, W + 200, 800);
      ctx.strokeStyle = 'rgba(255,255,255,0.2)'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(-100, 1210); ctx.lineTo(W + 100, 1210); ctx.stroke();

      // bolo de 30 anos na mesa a esquerda
      const cakeX = 240, cakeY = 1150;
      rr(ctx, cakeX - 96, cakeY + 24, 192, 46, 10); outlined(ctx, '#475569', 6);
      rr(ctx, cakeX - 74, cakeY - 46, 148, 72, 16); outlined(ctx, '#FDE68A', 6);
      rr(ctx, cakeX - 78, cakeY - 52, 156, 22, 10); outlined(ctx, '#F472B6', 5);
      label(ctx, '30', cakeX, cakeY - 10, 44, '#0B0F19');
      // velas acesas ate o espirro apagar
      const lit = t < tEsp;
      for (const dx of [-32, 0, 32]) {
        rr(ctx, cakeX + dx - 5, cakeY - 82, 10, 32, 3); outlined(ctx, '#60A5FA', 4);
        if (lit) {
          const fl = Math.sin(t * 24 + dx) * 3;
          ctx.beginPath(); ctx.ellipse(cakeX + dx + fl * 0.4, cakeY - 94, 8, 13, 0, 0, Math.PI * 2);
          outlined(ctx, '#FFD400', 3);
        }
      }

      // placa carimbada da regra no centro-alto
      if (t >= tReg) {
        const sc = eBack(clamp((t - tReg) / 0.24, 0, 1));
        ctx.save(); ctx.translate(500, 455); ctx.scale(sc, sc);
        pill(ctx, 0, 0, 560, 96, '#0B0F19', '#FFD400', '1 ESPIRRO = -1 ANO', '#FFD400', 46);
        ctx.restore();
      }

      // Beto no centro-direita
      const jumpY = t >= tJov ? -Math.abs(Math.sin((t - tJov) * 7)) * 45 : 0;
      contactShadow(ctx, 560, 1220, 132, 0.35);
      drawBeto(ctx, st, { x: 560, y: pelvisFromFeet(1220, 1.08) + jumpY, scale: 1.08, t, rim: { color: '#38BDF8', dir: [-0.7, -0.7] } });

      drawSneezeBlast(ctx, 510, 880, t, tEsp, '#2ED573');
      if (t >= tJov) drawSparkles(ctx, 560, 920, t, 7, 210, '#2ED573');
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 3. ESPIRRO 1 (29 ANOS)
  SC.espirro1 = {
    keys(S) {
      return [
        { t: S.start('espirro1'), pose: BACK_ACHE, expr: 'panic', dur: 0.16, ease: 'inout' },
        { t: S.c('espirro1', 'some'), pose: SNEEZE_BURST, expr: 'shock', dur: 0.12, ease: 'back' },
        { t: S.c('espirro1', 'vibra'), pose: 'jump_up', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro1', 'dor'), S.c('espirro1', 'costas'), S.c('espirro1', 'some'), S.c('espirro1', 'vibra')]; },
    hud(S) {
      const s0 = S.start('espirro1'), tSom = S.c('espirro1', 'some');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'ESPIRRO 1', badgeT: s0, badgeCol: '#2ED573',
          label: 'IDADE BIOLÓGICA',
          age: t => HUD.roll(t, s0, tSom, 30, 29, 'lin')
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro1'), s1 = S.end('espirro1');
      const tSom = S.c('espirro1', 'some'), tVib = S.c('espirro1', 'vibra');
      const cured = t >= tSom;

      fillScreen(ctx, cured
        ? vGrad(ctx, [[0, '#0D9488'], [0.6, '#34D399'], [1, '#065F46']])
        : vGrad(ctx, [[0, '#3B2F4A'], [0.6, '#5B4666'], [1, '#1F1A29']])
      );
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tSom, 1.16, eBack], [s1, 1.05]]), shake: hits(t, [{ t: tSom, a: 24, d: 0.35 }]) }, t);

      // piso da sala
      ctx.fillStyle = cured ? '#047857' : '#261D33';
      ctx.fillRect(-100, 1215, W + 200, 800);
      // janela clara no fundo
      rr(ctx, 130, 440, 240, 260, 14); outlined(ctx, cured ? '#FEF08A' : '#4C3B5E', 7);
      ctx.strokeStyle = INK; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(250, 440); ctx.lineTo(250, 700); ctx.moveTo(130, 570); ctx.lineTo(370, 570); ctx.stroke();

      // raios vermelhos de dor nas costas antes do espirro
      if (!cured) {
        const pulse = 0.65 + 0.35 * Math.sin(t * 22);
        ctx.save(); ctx.globalAlpha = pulse;
        ctx.strokeStyle = '#FF2E3B'; ctx.lineWidth = 10; ctx.lineCap = 'round';
        for (const dy of [-28, 8, 42]) {
          ctx.beginPath();
          ctx.moveTo(390, 960 + dy); ctx.lineTo(345, 945 + dy); ctx.lineTo(362, 975 + dy); ctx.lineTo(315, 960 + dy);
          ctx.stroke();
        }
        ctx.restore();
        pill(ctx, 510, 470, 380, 76, '#7F1D1D', '#FF8A92', 'DOR NAS COSTAS', '#FFFFFF', 36);
      } else {
        speedLines(ctx, 520, 950, 24, 190, 920, '#FFFFFF', 0.35, t * 0.9);
        drawSparkles(ctx, 520, 920, t, 9, 240, '#FFD400');
        pill(ctx, 510, 470, 380, 76, '#064E3B', '#FFD400', 'COLUNA NOVA!', '#FFD400', 40);
      }

      const hop = t >= tVib ? -Math.abs(Math.sin((t - tVib) * 8.5)) * 75 : 0;
      contactShadow(ctx, 520, 1225, 135 - Math.abs(hop) * 0.35, 0.34);
      drawBeto(ctx, st, { x: 520, y: pelvisFromFeet(1225, 1.12) + hop, scale: 1.12, t, rim: { color: cured ? '#FFD400' : '#FF8A92', dir: [-0.8, -0.5] } });

      drawSneezeBlast(ctx, 520, 880, t, tSom, '#2ED573');
      if (t >= tSom && t < tSom + 0.85) {
        drawBurstBalloon(ctx, 530, 620, 'ATCHIM!', eBack(clamp((t - tSom) / 0.16, 0, 1)), '#FFFFFF', '#0D9488', 'center');
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 4. ESPIRRO 5 (25 ANOS)
  SC.espirro5 = {
    keys(S) {
      return [
        { t: S.start('espirro5'), pose: SNIFF_POSE, expr: 'smug', dur: 0.16, ease: 'back' },
        { t: S.c('espirro5', 'pimenta'), pose: SNEEZE_BURST, expr: 'shock', dur: 0.12, ease: 'back' },
        { t: S.c('espirro5', 'beleza'), pose: 'flex', expr: 'amazed', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro5', 'cheira'), S.c('espirro5', 'pimenta'), S.c('espirro5', 'voltar'), S.c('espirro5', 'beleza')]; },
    hud(S) {
      const s0 = S.start('espirro5'), tPim = S.c('espirro5', 'pimenta');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'ESPIRRO 5', badgeT: s0, badgeCol: '#2ED573',
          label: 'IDADE BIOLÓGICA',
          age: t => HUD.roll(t, s0, tPim + 0.5, 29, 25, 'lin')
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro5'), s1 = S.end('espirro5');
      const tPim = S.c('espirro5', 'pimenta'), tBel = S.c('espirro5', 'beleza');
      const glam = t >= tBel;

      fillScreen(ctx, glam
        ? vGrad(ctx, [[0, '#D97706'], [0.5, '#F59E0B'], [1, '#78350F']])
        : vGrad(ctx, [[0, '#FDE68A'], [0.6, '#FCD34D'], [1, '#B45309']])
      );
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [tPim, 1.15, eBack], [tBel, 1.12], [s1, 1.18]]), shake: hits(t, [{ t: tPim, a: 24, d: 0.35 }, { t: tBel, a: 14, d: 0.25 }]) }, t);

      // bancada de cozinha clara
      rr(ctx, -40, 1170, W + 80, 420, 18); outlined(ctx, '#FFFBEB', 8);
      ctx.fillStyle = '#E2E8F0'; ctx.fillRect(-40, 1210, W + 80, 380);

      if (glam) {
        speedLines(ctx, 510, 900, 28, 170, 960, '#FFFFFF', 0.42, t * 1.1);
        glow(ctx, 510, 880, 420, 'rgba(255,255,255,A)', 0.45);
        drawSparkles(ctx, 510, 860, t, 10, 260, '#FFFFFF');
        pill(ctx, 500, 465, 420, 78, '#78350F', '#FFD400', 'AUGE DOS 25 ANOS!', '#FFD400', 40);
      }

      // pimenteiro gigante inclinando e soltando nuvem de pimenta preta
      const shakRot = t < tBel ? 0.65 + Math.sin(t * 26) * 0.22 : -0.15;
      drawPepperShaker(ctx, 250, 770 + Math.sin(t * 16) * 14, 1.25, shakRot);
      if (t < tBel) {
        for (let i = 0; i < 18; i++) {
          const k = ((t * 1.6 + hash(i * 17)) % 1);
          const px = 310 + k * 190 + Math.sin(t * 9 + i) * 18;
          const py = 740 + k * 110 + (hash(i * 23) - 0.5) * 60;
          ctx.beginPath(); ctx.arc(px, py, 5 + hash(i * 31) * 4, 0, Math.PI * 2);
          ctx.fillStyle = INK; ctx.fill();
        }
      }

      contactShadow(ctx, 550, 1185, 130, 0.28);
      drawBeto(ctx, st, { x: 550, y: pelvisFromFeet(1185, 1.08), scale: 1.08, t, rim: { color: '#FFFFFF', dir: [0.6, -0.8] } });
      drawSneezeBlast(ctx, 520, 860, t, tPim, '#FFD400');
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 5. ESPIRRO 12 (18 ANOS - VIRADA DA PRIMAVERA!)
  SC.espirro12 = {
    keys(S) {
      return [
        { t: S.start('espirro12'), pose: 'flex', expr: 'amazed', dur: 0.14, ease: 'back' },
        { t: S.c('espirro12', 'primavera'), pose: 'shock_closeup', expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('espirro12', 'ataca'), pose: SNEEZE_BURST, expr: 'panic', dur: 0.12, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro12', 'Pele'), S.c('espirro12', 'perfeita'), S.c('espirro12', 'primavera'), S.c('espirro12', 'rinite'), S.c('espirro12', 'ataca')]; },
    hud(S) {
      const s0 = S.start('espirro12'), tPri = S.c('espirro12', 'primavera'), tAta = S.c('espirro12', 'ataca');
      return {
        bar: null, ruler: null,
        alert: { t0: tPri, text: 'PRIMAVERA: ALERTA PÓLEN' },
        customHud: ageHud({
          badge: 'ESPIRRO 12', badgeT: s0,
          label: 'IDADE BIOLÓGICA',
          age: t => HUD.roll(t, s0, tAta + 0.5, 25, 18, 'lin'),
          alert: false, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro12'), s1 = S.end('espirro12');
      const tPri = S.c('espirro12', 'primavera'), tAta = S.c('espirro12', 'ataca');
      const storm = t >= tPri;

      fillScreen(ctx, storm
        ? vGrad(ctx, [[0, '#CA8A04'], [0.55, '#EAB308'], [1, '#713F12']])
        : vGrad(ctx, [[0, '#38BDF8'], [0.6, '#BAE6FD'], [1, '#15803D']])
      );
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tPri, 1.12], [tAta, 1.2, eBack], [s1, 1.08]]), shake: hits(t, [{ t: tPri, a: 16, d: 0.3 }, { t: tAta, a: 30, d: 0.45 }]) }, t);

      // gramado do parque + arvores floridas
      ctx.fillStyle = storm ? '#4D7C0F' : '#16A34A';
      ctx.fillRect(-100, 1180, W + 200, 800);
      for (const [tx, ty] of [[150, 830], [830, 850]]) {
        rr(ctx, tx - 26, ty + 70, 52, 290, 10); outlined(ctx, '#78350F', 6);
        for (const [ox, oy, rr2] of [[0, 0, 110], [-75, 45, 78], [75, 45, 78]]) {
          ctx.beginPath(); ctx.arc(tx + ox, ty + oy, rr2, 0, Math.PI * 2);
          outlined(ctx, storm ? '#FACC15' : '#F472B6', 6);
        }
      }

      if (!storm) {
        drawSparkles(ctx, 510, 900, t, 8, 220, '#FFFFFF');
      } else {
        drawPollenStorm(ctx, t, 22, 320, 60, 12, 26);
      }

      contactShadow(ctx, 510, 1210, 122, 0.32);
      drawBeto(ctx, st, { x: 510, y: pelvisFromFeet(1210, 1.0), scale: 1.0, t, wind: storm ? [45, 8] : [0, 0], rim: { color: storm ? '#FFD400' : '#FFFFFF', dir: [-0.8, -0.5] } });

      // nariz vermelho brilhando quando a rinite ataca
      if (storm) {
        const pulse = 0.7 + 0.3 * Math.sin(t * 20);
        glow(ctx, 510, 865, 36 * pulse, 'rgba(255,46,59,A)', 0.75);
      }
      drawSneezeBlast(ctx, 530, 880, t, tAta, '#FFD400');
      if (t >= tAta) {
        drawBurstBalloon(ctx, 490, 580, 'ATCHIM!! ATCHIM!!', eBack(clamp((t - tAta) / 0.16, 0, 1)), '#FFD400', '#E8322A', 'center');
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 6. ESPIRRO 18 (12 ANOS - ROUPA GIGANTE!)
  SC.espirro18 = {
    keys(S) {
      return [
        { t: S.start('espirro18'), pose: 'look_down', expr: 'shock', dur: 0.16, ease: 'back' },
        { t: S.c('espirro18', 'gigante'), pose: 'shrug_question', expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('espirro18', 'estudar'), pose: 'dodge_lean', expr: 'scream', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro18', 'roupa'), S.c('espirro18', 'gigante'), S.c('espirro18', 'chefe'), S.c('espirro18', 'estudar')]; },
    hud(S) {
      const s0 = S.start('espirro18'), tGig = S.c('espirro18', 'gigante');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'ESPIRRO 18', badgeT: s0, badgeCol: '#FFD400',
          label: 'IDADE BIOLÓGICA',
          age: t => HUD.roll(t, s0, tGig + 0.4, 18, 12, 'lin'),
          vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro18'), s1 = S.end('espirro18');
      const tChe = S.c('espirro18', 'chefe'), tEst = S.c('espirro18', 'estudar');

      fillScreen(ctx, vGrad(ctx, [[0, '#334155'], [0.6, '#475569'], [1, '#1E293B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.02], [tChe, 1.08], [tEst, 1.14, eBack], [s1, 1.06]]), shake: hits(t, [{ t: tChe, a: 14, d: 0.25 }, { t: tEst, a: 24, d: 0.35 }]) }, t);

      // piso do escritorio + janela panoramica com vista urbana atras
      rr(ctx, 80, 430, 820, 320, 12); outlined(ctx, '#7DD3FC', 7);
      ctx.save();
      rr(ctx, 84, 434, 812, 312, 10); ctx.clip();
      ctx.fillStyle = vGrad(ctx, [[0, '#38BDF8'], [1, '#BAE6FD']], 434, 746);
      ctx.fillRect(84, 434, 812, 312);
      // silhueta de predios no fundo da janela
      ctx.fillStyle = '#475569';
      for (const [px, pw, ph] of [[110, 95, 175], [220, 120, 215], [360, 85, 145], [470, 130, 230], [625, 110, 185], [755, 115, 200]]) {
        ctx.fillRect(px, 746 - ph, pw, ph);
      }
      // divisorias da janela
      ctx.strokeStyle = INK; ctx.lineWidth = 7;
      for (const mx of [350, 620]) {
        ctx.beginPath(); ctx.moveTo(mx, 430); ctx.lineTo(mx, 750); ctx.stroke();
      }
      ctx.restore();
      ctx.fillStyle = '#0F172A'; ctx.fillRect(-100, 1210, W + 200, 800);

      // placa ESCOLA -> no topo direito seguro
      if (t >= tEst) {
        const sc = eBack(clamp((t - tEst) / 0.2, 0, 1));
        ctx.save(); ctx.translate(650, 495); ctx.scale(sc, sc);
        pill(ctx, 0, 0, 360, 84, '#14532D', '#FFD400', 'VAI PRA ESCOLA!', '#FFD400', 38);
        ctx.restore();
      }

      // Chefe gigante a esquerda apontando pro Beto encolhido
      const bossX = kf(t, [[s0, 150], [tChe, 245, eBack], [s1, 260]]);
      contactShadow(ctx, bossX, 1215, 130, 0.32);
      drawBoss(ctx, bossX, 1020, 1.35, 1);

      // Beto visivelmente menor (12 anos, scale 0.72) com mochila escolar amarela
      const scB = kf(t, [[s0, 0.92], [tChe, 0.72, eOut], [s1, 0.7]]);
      const bx = 610;
      contactShadow(ctx, bx, 1215, 96, 0.32);
      // mochila amarela atras do Beto
      if (t >= tEst - 0.15) {
        const mSc = eBack(clamp((t - (tEst - 0.15)) / 0.2, 0, 1));
        ctx.save(); ctx.translate(bx + 42, 1045); ctx.scale(mSc, mSc);
        rr(ctx, -36, -48, 72, 92, 18); outlined(ctx, '#FACC15', 6);
        rr(ctx, -24, 4, 48, 28, 8); outlined(ctx, '#EAB308', 5);
        ctx.restore();
      }
      drawBeto(ctx, st, { x: bx, y: pelvisFromFeet(1215, scB), scale: scB, t, rim: { color: '#FFD400', dir: [-0.8, -0.5] } });
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 7. ESPIRRO 24 (6 ANOS - MESA GIGANTE!)
  SC.espirro24 = {
    keys(S) {
      return [
        { t: S.start('espirro24'), pose: REACH_UP, expr: 'curious', dur: 0.16, ease: 'back' },
        { t: S.c('espirro24', 'mesa'), pose: REACH_UP, expr: 'shock', dur: 0.14, ease: 'inout' },
        { t: S.c('espirro24', 'tapar'), pose: COVER_NOSE, expr: 'panic', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro24', 'alcança'), S.c('espirro24', 'mesa'), S.c('espirro24', 'tenta'), S.c('espirro24', 'tapar'), S.c('espirro24', 'nariz')]; },
    hud(S) {
      const s0 = S.start('espirro24'), tTap = S.c('espirro24', 'tapar');
      return {
        bar: null, ruler: null,
        alert: { t0: tTap, text: 'SEGURA ESSE ESPIRRO!' },
        customHud: ageHud({
          badge: 'ESPIRRO 24', badgeT: s0,
          label: 'IDADE BIOLÓGICA',
          age: t => HUD.roll(t, s0, tTap, 12, 6, 'lin'),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro24'), s1 = S.end('espirro24');
      const tTap = S.c('espirro24', 'tapar');

      fillScreen(ctx, vGrad(ctx, [[0, '#451A03'], [0.5, '#78350F'], [1, '#1C1917']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tTap, 1.15, eBack], [s1, 1.2]]), shake: hits(t, [{ t: tTap, a: 22, d: 0.35 }]) + (t >= tTap ? 5 : 0) }, t);

      // chao
      ctx.fillStyle = '#292524'; ctx.fillRect(-100, 1230, W + 200, 750);

      // MESA GIGANTE em primeiro plano/lateral para enfatizar a estatura de 6 anos
      rr(ctx, 60, 740, 420, 56, 12); outlined(ctx, '#92400E', 8);
      rr(ctx, 110, 796, 44, 434, 6); outlined(ctx, '#78350F', 7);
      rr(ctx, 405, 796, 44, 434, 6); outlined(ctx, '#78350F', 7);
      // caneca enorme em cima da mesa
      rr(ctx, 240, 620, 110, 120, 16); outlined(ctx, '#F8FAFC', 7);
      ctx.strokeStyle = INK; ctx.lineWidth = 14;
      ctx.beginPath(); ctx.arc(356, 680, 32, -Math.PI * 0.5, Math.PI * 0.5); ctx.stroke();

      // Beto mini (6 anos, scale 0.56) mal alcancando a quina da mesa!
      const bx = 585;
      const scB = 0.56;
      const bounce = t < tTap ? -Math.abs(Math.sin(t * 7.5)) * 22 : 0;
      contactShadow(ctx, bx, 1230, 76, 0.35);
      drawBeto(ctx, st, { x: bx, y: pelvisFromFeet(1230, scB) + bounce, scale: scB, t, rim: { color: '#FF7A29', dir: [-0.8, -0.5] } });

      // linhas de tremor ao tentar segurar o espirro
      if (t >= tTap) {
        glow(ctx, bx, 1020, 220, 'rgba(255,46,59,A)', 0.35);
        speedLines(ctx, bx, 1020, 18, 120, 420, '#FFD400', 0.55, t * 2.1);
        drawPollenStorm(ctx, t, 10, 240, 35, 10, 18);
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 8. ESPIRRO 28 (2 ANOS - CLIMAX NO BERCO!)
  SC.espirro28 = {
    keys(S) {
      return [
        { t: S.start('espirro28'), pose: 'shock_closeup', expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('espirro28', 'berço'), pose: COVER_NOSE, expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('espirro28', 'fim'), pose: 'freefall_scream', expr: 'scream', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('espirro28', 'Bebê'), S.c('espirro28', 'berço'), S.c('espirro28', 'dois'), S.c('espirro28', 'espirros'), S.c('espirro28', 'fim')]; },
    hud(S) {
      const s0 = S.start('espirro28'), tDois = S.c('espirro28', 'dois');
      return {
        bar: null, ruler: null,
        alert: { t0: s0, text: 'FALTAM SÓ 2 ESPIRROS!' },
        customHud: ageHud({
          badge: 'ESPIRRO 28', badgeT: s0,
          label: 'PERIGO CRÍTICO',
          age: t => HUD.roll(t, s0, tDois, 6, 2, 'lin'),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('espirro28'), s1 = S.end('espirro28');
      const tFim = S.c('espirro28', 'fim');
      const pulse = 0.5 + 0.5 * Math.sin(t * 14);

      fillScreen(ctx, vGrad(ctx, [[0, '#3B0A14'], [0.55, '#7F1D1D'], [1, '#1A060B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [tFim, 1.18, eBack], [s1, 1.22]]), shake: hits(t, [{ t: s0, a: 18, d: 0.3 }, { t: tFim, a: 28, d: 0.45 }]) + 6 }, t);

      // luz vermelha de emergencia piscando no quarto de bebe
      glow(ctx, 500, 760, 560, 'rgba(255,46,59,A)', 0.25 + 0.22 * pulse);

      // estrutura traseira do berco de madeira
      rr(ctx, 180, 680, 640, 560, 24); outlined(ctx, '#FEF3C7', 8);
      rr(ctx, 200, 1070, 600, 140, 18); outlined(ctx, '#93C5FD', 6); // colcha azul clara

      // Beto bebe (scale 0.50) no centro do berco entre as grades largas!
      const bx = 500, by = pelvisFromFeet(1155, 0.50);
      drawBeto(ctx, st, { x: bx, y: by, scale: 0.50, t, rim: { color: '#FF2E3B', dir: [0, -1] } });

      // chupeta azul vibrante presa perto da boca do Beto bebe
      ctx.save(); ctx.translate(bx, by - 64);
      ctx.beginPath(); ctx.ellipse(0, 0, 20, 12, 0, 0, Math.PI * 2); outlined(ctx, '#38BDF8', 4);
      ctx.beginPath(); ctx.arc(0, 9, 9, 0, Math.PI * 2); ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 4; ctx.stroke();
      ctx.restore();

      // grades frontais verticais do berco (espacadas para deixar o rosto 100% visivel!)
      rr(ctx, 170, 740, 660, 34, 12); outlined(ctx, '#D97706', 7);
      rr(ctx, 170, 1205, 660, 42, 12); outlined(ctx, '#B45309', 7);
      for (const gx of [220, 326, 426, 574, 674, 780]) {
        rr(ctx, gx - 9, 770, 18, 440, 6); outlined(ctx, '#F59E0B', 5);
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 9. BOLHA ESTERIL + PREGADOR
  SC.bolha = {
    keys(S) {
      return [
        { t: S.start('bolha'), pose: COVER_NOSE, expr: 'panic', dur: 0.14, ease: 'back' },
        { t: S.c('bolha', 'pregador'), pose: 'idle', expr: 'determined', dur: 0.16, ease: 'back' },
        { t: S.c('bolha', 'tranca'), pose: 'flex', expr: 'determined', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('bolha', 'pânico'), S.c('bolha', 'pregador'), S.c('bolha', 'nariz'), S.c('bolha', 'tranca'), S.c('bolha', 'bolha')]; },
    hud(S) {
      const s0 = S.start('bolha');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'MODO BOLHA', badgeT: s0, badgeCol: '#38BDF8',
          label: 'AMBIENTE ESTÉRIL', value: '2 ANOS / 0% PÓ',
          age: 2, alert: false, hideGauge: false
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('bolha'), s1 = S.end('bolha');
      const tPre = S.c('bolha', 'pregador'), tTra = S.c('bolha', 'tranca'), tBol = S.c('bolha', 'bolha');

      fillScreen(ctx, vGrad(ctx, [[0, '#082F49'], [0.55, '#0E7490'], [1, '#042F2E']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.08], [tPre, 1.14], [tTra, 1.02, eBack], [s1, 1.06]]), shake: hits(t, [{ t: tPre, a: 18, d: 0.25 }, { t: tTra, a: 20, d: 0.35 }]) }, t);

      // piso metalico de laboratorio + filtro HEPA girando no fundo
      ctx.fillStyle = '#0F172A'; ctx.fillRect(-100, 1210, W + 200, 760);
      // grade do filtro de ar no alto esquerdo
      rr(ctx, 110, 440, 210, 150, 14); outlined(ctx, '#334155', 7);
      for (let fy = 466; fy <= 566; fy += 24) {
        ctx.strokeStyle = '#94A3B8'; ctx.lineWidth = 7;
        ctx.beginPath(); ctx.moveTo(132, fy); ctx.lineTo(298, fy); ctx.stroke();
      }
      label(ctx, 'HEPA 99%', 215, 622, 28, '#7DD3FC');

      // base metalica da capsula
      rr(ctx, 210, 1165, 580, 68, 22); outlined(ctx, '#475569', 7);

      // Beto mini (2 anos, scale 0.56 para otima leitura na capsula)
      const bx = 500, by = pelvisFromFeet(1172, 0.56);
      drawBeto(ctx, st, { x: bx, y: by, scale: 0.56, t, rim: { color: '#38BDF8', dir: [0, -1] } });

      // pregador compacto preso no nariz mantendo os olhos 100% visiveis!
      if (t >= tPre) {
        const pSc = eBack(clamp((t - tPre) / 0.18, 0, 1));
        drawClothespin(ctx, bx + 4, by - 88, 0.34 * pSc, 0.38);
      }

      // cupula de vidro transparente descendo em "tranca" e travando em "bolha"
      if (t >= tTra - 0.15) {
        const dropK = eOut(clamp((t - (tTra - 0.15)) / 0.42, 0, 1));
        const domeY = lerp(520, 965, dropK);
        ctx.save();
        ctx.beginPath(); ctx.arc(500, domeY, 275, Math.PI, 0); ctx.lineTo(775, domeY + 205); ctx.lineTo(225, domeY + 205); ctx.closePath();
        ctx.fillStyle = 'rgba(125,211,252,0.18)'; ctx.fill();
        ctx.lineWidth = 9; ctx.strokeStyle = '#7DD3FC'; ctx.stroke();
        // reflexo de vidro
        ctx.strokeStyle = 'rgba(255,255,255,0.68)'; ctx.lineWidth = 10; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.arc(500, domeY, 238, Math.PI * 1.14, Math.PI * 1.38); ctx.stroke();
        ctx.restore();
      }
      if (t >= tBol) {
        pill(ctx, 500, 560, 340, 74, '#082F49', '#7DD3FC', 'BOLHA SELADA!', '#7DD3FC', 36);
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 10. TWIST A (O GRAO DE POLEN NO FILTRO!)
  SC.twist_a = {
    keys(S) {
      return [
        { t: S.start('twist_a'), pose: 'idle', expr: 'determined', dur: 0.16, ease: 'inout' },
        { t: S.c('twist_a', 'pólen'), pose: 'shock_closeup', expr: 'shock', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('twist_a', 'salvo'), S.c('twist_a', 'grão'), S.c('twist_a', 'pólen'), S.c('twist_a', 'passar'), S.c('twist_a', 'filtro')]; },
    hud(S) {
      const s0 = S.start('twist_a'), tPol = S.c('twist_a', 'pólen');
      return {
        bar: null, ruler: null,
        alert: { t0: tPol, text: 'INTRUSO NO FILTRO!' },
        customHud: ageHud({
          badge: 'ALERTA', badgeT: tPol,
          label: 'FILTRO HEPA',
          value: t => t < tPol ? '100% LIMPO' : '1 GRÃO!',
          age: 2, alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), s1 = S.end('twist_a');
      const tGrao = S.c('twist_a', 'grão'), tPol = S.c('twist_a', 'pólen'), tFil = S.c('twist_a', 'filtro');

      fillScreen(ctx, vGrad(ctx, [[0, '#020617'], [0.55, '#0F172A'], [1, '#1E1B4B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [tGrao, 1.12], [tFil, 1.34, eIn], [s1, 1.44]]), shake: t >= tPol ? 4 : 0 }, t);

      // macro da grade metalica do filtro no topo esquerdo
      rr(ctx, 70, 460, 420, 260, 16); outlined(ctx, '#1E293B', 8);
      for (let fy = 505; fy <= 685; fy += 42) {
        rr(ctx, 94, fy, 372, 16, 6); outlined(ctx, '#475569', 5);
      }

      // Beto ao fundo-direita olhando aterrorizado pro grao se aproximar!
      const bx = 680, by = pelvisFromFeet(1220, 0.65);
      drawBeto(ctx, st, { x: bx, y: by, scale: 0.65, look: -1, t, rim: { color: '#FFD400', dir: [-1, -0.4] } });
      drawClothespin(ctx, bx + 4, by - 102, 0.38, 0.38);

      // O UNICO GRAO DE POLEN atravessando o filtro em camera lenta dramatica!
      const moveK = clamp((t - tGrao) / Math.max(0.2, s1 - tGrao), 0, 1);
      const px = lerp(260, 585, eIO(moveK));
      const py = lerp(590, 955, eIO(moveK)) + Math.sin(t * 5) * 18;
      const pr = lerp(22, 48, moveK);
      // feixe de holofote dramatico no grao
      glow(ctx, px, py, 240, 'rgba(255,212,0,A)', 0.42 + 0.2 * Math.sin(t * 16));
      drawPollenGrain(ctx, px, py, pr, t * 2.2, 0.65);

      // mira de perigo ao redor do grao
      if (t >= tPol) {
        ctx.save(); ctx.translate(px, py); ctx.rotate(-t * 1.4);
        ctx.strokeStyle = '#FF2E3B'; ctx.lineWidth = 6; ctx.setLineDash([18, 12]);
        ctx.beginPath(); ctx.arc(0, 0, pr * 2.1, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 11. TWIST B (ESPIRRO 30: ZERO ANOS -> SUMIU!)
  SC.twist_b = {
    keys(S) {
      return [
        { t: S.start('twist_b'), pose: SNEEZE_INHALE, expr: 'shock', dur: 0.14, ease: 'back' },
        { t: S.c('twist_b', 'solta'), pose: SNEEZE_BURST, expr: 'scream', dur: 0.1, ease: 'back' },
        { t: S.c('twist_b', 'zero'), pose: 'freefall_scream', expr: 'panic', dur: 0.12, ease: 'inout' }
      ];
    },
    ev(S) { return [S.c('twist_b', 'puxa'), S.c('twist_b', 'solta'), S.c('twist_b', 'dois'), S.c('twist_b', 'zero'), S.c('twist_b', 'sumiu')]; },
    hud(S) {
      const s0 = S.start('twist_b'), tSol = S.c('twist_b', 'solta'), tZer = S.c('twist_b', 'zero');
      return {
        bar: null, ruler: null,
        alert: { t0: tZer, text: 'IDADE ZERO: DESAPARECEU!' },
        customHud: ageHud({
          badge: 'ESPIRRO 30', badgeT: tZer,
          label: 'IDADE BIOLÓGICA',
          age: t => t < tSol ? 2 : HUD.roll(t, tSol, tZer, 2, 0, 'lin'),
          alert: true, vibrate: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_b'), s1 = S.end('twist_b');
      const tSol = S.c('twist_b', 'solta'), tZer = S.c('twist_b', 'zero'), tSum = S.c('twist_b', 'sumiu');
      const blasted = t >= tSol;
      const vanished = t >= tZer + 0.15;

      const shake = hits(t, [
        { t: s0, a: 16, d: 0.25 },
        { t: tSol, a: 42, d: 0.5 },
        { t: tZer, a: 46, d: 0.6 },
        { t: tSum, a: 24, d: 0.45 }
      ]) + (blasted && !vanished ? 12 : 0);

      fillScreen(ctx, vanished
        ? vGrad(ctx, [[0, '#0F172A'], [0.6, '#1E293B'], [1, '#020617']])
        : (blasted
          ? vGrad(ctx, [[0, '#FF2E3B'], [0.5, '#F59E0B'], [1, '#450A0A']])
          : vGrad(ctx, [[0, '#082F49'], [0.6, '#1E3A8A'], [1, '#0B0F19']]))
      );

      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.18], [tSol, 1.32, eBack], [tZer, 1.06], [s1, 1.12]]), shake }, t);

      // piso da capsula
      ctx.fillStyle = vanished ? '#020617' : 'rgba(11,15,25,0.5)';
      ctx.fillRect(-100, 1210, W + 200, 760);

      if (blasted && !vanished) {
        speedLines(ctx, 500, 960, 36, 130, 1200, '#FFFFFF', 0.56, t * 1.8);
        glow(ctx, 500, 960, 520, 'rgba(255,255,255,A)', 0.5);
      }

      // pregador voando pro lado quando o espirro explode!
      if (t >= s0 + 0.15) {
        const pinK = clamp((t - (s0 + 0.15)) / 0.65, 0, 1);
        drawClothespin(ctx, 500 + pinK * 320, 880 - pinK * 280, 0.72, pinK * 7.5);
      }

      // Beto encolhe de 0.75 -> 0.0 e vira poof deixando o moletom vazio!
      const scB = kf(t, [[s0, 0.78], [tSol, 0.62, eOut], [tZer, 0.18, eIn], [tZer + 0.15, 0.0, eIn]]);
      if (scB > 0.03) {
        const sq = t < tSol ? 1 + 0.14 * Math.sin((t - s0) * 10) : 0.88;
        contactShadow(ctx, 500, 1215, 110 * scB, 0.34);
        drawBeto(ctx, st, { x: 500, y: pelvisFromFeet(1215, scB), scale: scB, squash: sq, t, rim: { color: '#FFFFFF', dir: [0, -1] } });
      } else {
        drawEmptyHoodie(ctx, 500, 1185, 1.12);
        drawSparkles(ctx, 500, 1080, t, 6, 180, '#FFD400');
      }

      // rajadas duplas de espirro + nuvem POOF
      drawSneezeBlast(ctx, 500, 960, t, tSol, '#FFD400');
      drawSneezeBlast(ctx, 500, 1020, t, tSol + 0.32, '#FF2E3B');
      drawPoofCloud(ctx, 500, 1120, clamp((t - tZer) / 0.75, 0, 1));

      if (t >= tSol && !vanished) {
        const scPop = eBack(clamp((t - tSol) / 0.15, 0, 1));
        drawBurstBalloon(ctx, 490, 565, 'ATCHIM!! ATCHIM!!', scPop * 1.12, '#FFD400', '#E8322A', 'center');
      } else if (vanished) {
        const scP = eBack(clamp((t - (tZer + 0.15)) / 0.22, 0, 1));
        ctx.save(); ctx.translate(500, 620); ctx.scale(scP, scP);
        pill(ctx, 0, 0, 410, 86, '#0B0F19', '#FF2E3B', 'POOF! SUMIU!', '#FFD400', 46);
        ctx.restore();
      }
      ctx.restore();
    }
  };

  // ------------------------------------------------------------- 12. LOOP (CTA FALADA!)
  SC.loop = {
    keys(S) {
      return [
        { t: S.start('loop'), pose: 'shrug_question', expr: 'curious', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'nariz'), pose: COVER_NOSE, expr: 'panic', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'Comenta'), pose: 'point_hook', expr: 'smug', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('loop', 'cheiraria'), S.c('loop', 'pimenta'), S.c('loop', 'rejuvenescer'), S.c('loop', 'nariz'), S.c('loop', 'Comenta')]; },
    hud(S) {
      const s0 = S.start('loop');
      return {
        bar: null, ruler: null, alert: null,
        customHud: ageHud({
          badge: 'SUA VEZ', badgeT: s0, badgeCol: '#FFD400',
          label: 'ESCOLHA AGORA', value: 'COMENTE AÍ',
          age: 25, alert: false, hideGauge: true
        })
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop');
      const tNar = S.c('loop', 'nariz'), tCom = S.c('loop', 'Comenta');

      // fundo dividido vibrante: ESQUERDA VERDE-OURO (PIMENTA 25 ANOS) vs DIREITA CARMIM (PREGADOR NO NARIZ)
      ctx.fillStyle = vGrad(ctx, [[0, '#059669'], [1, '#064E3B']]); ctx.fillRect(0, 0, W / 2, H);
      ctx.fillStyle = vGrad(ctx, [[0, '#C81E2B'], [1, '#5B0B14']]); ctx.fillRect(W / 2, 0, W / 2, H);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();

      const z = kf(t, [[s0, 1.32], [tNar, 1.48, eBack], [tCom, 1.62, eBack], [s1, 1.72, eIn]]);
      const shake = hits(t, [{ t: s0, a: 16, d: 0.3 }, { t: tNar, a: 22, d: 0.35 }, { t: tCom, a: 16, d: 0.3 }]) + 2;
      const bx = 540, by = 1170;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);

      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 150 / z, z, shake }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1.0, t, rim: { color: '#FFD400', dir: [0.8, -0.6] } });
      ctx.restore();

      // props nos flancos em espaco de tela (abaixo das placas de escolha e acima das legendas)
      drawPepperShaker(ctx, 185, 1020 + Math.sin(t * 7) * 22, 1.08, -0.3 + Math.sin(t * 5) * 0.18);
      drawClothespin(ctx, 895, 1020 + Math.cos(t * 7) * 22, 1.25, 0.32 - Math.sin(t * 5) * 0.18);

      // duas placas de escolha limpas no topo
      pill(ctx, 270, 360, 390, 80, '#064E3B', '#FFD400', 'PIMENTA: 25 ANOS', '#FFD400', 34);
      pill(ctx, 810, 360, 390, 80, '#2D070C', '#FFFFFF', 'TRAVAR O NARIZ', '#FFFFFF', 34);
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
