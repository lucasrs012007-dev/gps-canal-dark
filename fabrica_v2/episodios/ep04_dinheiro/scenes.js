/*
 * ep04_dinheiro/scenes.js : Episodio 4 ("E se voce ganhasse 1 real hoje e dobrasse todo dia?")
 * 16 cenarios originais animados quadro a quadro em HTML5 Canvas 2D (1080x1920, 30fps).
 *
 * Reusa 100% do motor visual Opus (window.Beto e window.HUD) sem altera-los.
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
  const PUSH_CART = Object.assign({}, B.POSES.idle, {
    lean: 12, head: -4, ua_r: 78, la_r: 92, hand_r: 1,
    ua_l: -42, la_l: -64, hand_l: 1, th_r: 22, sh_r: -10, th_l: -12, sh_l: 16
  });
  const TOSS_COIN = Object.assign({}, B.POSES.idle, {
    lean: -4, head: -8, ua_r: 118, la_r: 148, hand_r: 0,
    ua_l: 28, la_l: -16, hand_l: 1, th_r: 10, sh_r: 2, th_l: 10, sh_l: 2
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

  // ------------------------------------------------ regua logaritmica de saldo
  const MONEY_MARKS = [
    { v: 1, txt: 'R$1' },
    { v: 1e3, txt: 'R$1k' },
    { v: 1e6, txt: 'R$1M' },
    { v: 1e9, txt: 'R$1B' },
    { v: 1e12, txt: 'R$1T' },
    { v: 1.7e13, txt: 'CAOS' }
  ];
  function fmtMoney(v) {
    if (v >= 1e12) return 'R$ ' + HUD.fmtNum(Math.round(v / 1e12), 0) + ' tri';
    if (v >= 1e9) return 'R$ ' + HUD.fmtNum(Math.round(v / 1e9), 0) + ' bi';
    if (v >= 1e6) return 'R$ ' + HUD.fmtNum(Math.round(v / 1e6), 0) + ' mi';
    if (v >= 1000) return 'R$ ' + HUD.fmtNum(Math.round(v / 1000), 0) + ' mil';
    return 'R$ ' + HUD.fmtNum(Math.round(v), 0);
  }
  /** Regua vertical logaritmica (R$1 embaixo -> CAOS no topo) na borda direita segura. */
  function moneyGauge(reais, opts) {
    opts = opts || {};
    return function drawMoneyGauge(ctx) {
      const x = 1012, y0 = 1080, y1 = 360;
      const lmin = 0, lmax = Math.log10(2e13);
      const yOf = v => y0 - (Math.log10(clamp(v, 1, 2e13)) - lmin) / (lmax - lmin) * (y0 - y1);
      ctx.save();
      rr(ctx, x - 14, y1 - 26, 28, y0 - y1 + 52, 14);
      ctx.fillStyle = 'rgba(11,15,25,0.74)'; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.78)'; ctx.stroke();
      const ym = yOf(reais);
      rr(ctx, x - 7, ym, 14, Math.max(0, y0 + 12 - ym), 7);
      ctx.fillStyle = opts.alert ? HUD.COLORS.alert : (opts.gold ? '#FFD400' : '#2ED573');
      ctx.fill();
      ctx.font = `22px ${HUD.FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const mk of MONEY_MARKS) {
        const yy = yOf(mk.v);
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
        ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.92)'; ctx.lineJoin = 'round';
        ctx.strokeText(mk.txt, x - 32, yy + 1);
        ctx.fillStyle = mk.v >= 1e13 ? '#FF6B6B' : 'rgba(255,255,255,0.95)';
        ctx.fillText(mk.txt, x - 32, yy + 1);
      }
      ctx.save(); ctx.translate(x, ym);
      ctx.beginPath(); ctx.moveTo(0, -19); ctx.lineTo(19, 0); ctx.lineTo(0, 19); ctx.lineTo(-19, 0); ctx.closePath();
      ctx.fillStyle = opts.alert ? '#E8322A' : '#FFD400'; ctx.fill();
      ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
      ctx.restore();
      ctx.restore();
    };
  }

  // --------------------------------------------------------- props de dinheiro
  /** Moeda brasileira bimetalica de 1 Real (aro dourado + miolo prata). */
  function drawRealCoin(ctx, x, y, r, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0);
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2);
    const og = ctx.createRadialGradient(-r * 0.3, -r * 0.3, r * 0.1, 0, 0, r);
    og.addColorStop(0, '#FFF3A0'); og.addColorStop(0.55, '#F5C428'); og.addColorStop(1, '#B88310');
    outlined(ctx, og, Math.max(5, r * 0.08));
    ctx.beginPath(); ctx.arc(0, 0, r * 0.68, 0, Math.PI * 2);
    const ig = ctx.createRadialGradient(-r * 0.2, -r * 0.2, r * 0.05, 0, 0, r * 0.7);
    ig.addColorStop(0, '#FFFFFF'); ig.addColorStop(0.65, '#DCE3EE'); ig.addColorStop(1, '#9BA6B8');
    outlined(ctx, ig, Math.max(4, r * 0.05));
    label(ctx, '1', 0, -r * 0.08, Math.round(r * 0.72), INK);
    label(ctx, 'REAL', 0, r * 0.34, Math.round(r * 0.24), INK);
    ctx.restore();
  }

  /** Cedula estilizada (azul R$100 ou verde esmeralda). */
  function drawBill(ctx, x, y, w, h, rot, col, txt) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0);
    rr(ctx, -w / 2, -h / 2, w, h, 10); outlined(ctx, col || '#49B86B', 5);
    ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 3;
    rr(ctx, -w / 2 + 8, -h / 2 + 8, w - 16, h - 16, 6); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, h * 0.3, 0, Math.PI * 2); outlined(ctx, '#FFF8D6', 4);
    label(ctx, txt || 'R$', 0, 2, Math.round(h * 0.42), INK);
    ctx.restore();
  }

  /** Maco grosso de dinheiro empilhado com cinta amarela. */
  function drawCashStack(ctx, x, y, w, h) {
    ctx.save(); ctx.translate(x, y);
    rr(ctx, -w / 2, -h / 2, w, h, 8); outlined(ctx, '#2E9E56', 5);
    rr(ctx, -w / 2, -h / 2 - 10, w, h * 0.48, 8); outlined(ctx, '#5BD984', 5);
    ctx.fillStyle = '#FFD400'; ctx.fillRect(-w * 0.16, -h / 2 - 10, w * 0.32, h + 10);
    ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(-w * 0.16, -h / 2 - 10, w * 0.32, h + 10);
    ctx.restore();
  }

  function drawSportsCar(ctx, x, y, s, color) {
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(-225, 42); ctx.lineTo(-225, -8); ctx.quadraticCurveTo(-180, -30, -110, -34);
    ctx.lineTo(-55, -96); ctx.lineTo(72, -96); ctx.lineTo(132, -32);
    ctx.quadraticCurveTo(205, -24, 232, 4); ctx.lineTo(232, 42); ctx.closePath();
    outlined(ctx, color, 8);
    // janelas
    ctx.beginPath(); ctx.moveTo(-90, -34); ctx.lineTo(-48, -80); ctx.lineTo(58, -80); ctx.lineTo(106, -34); ctx.closePath();
    outlined(ctx, '#9FE3FF', 5);
    ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(8, -80); ctx.lineTo(8, -34); ctx.stroke();
    // farois
    rr(ctx, 206, 2, 26, 20, 6); outlined(ctx, '#FFE86B', 4);
    rr(ctx, -228, 2, 20, 20, 6); outlined(ctx, '#FF4747', 4);
    // rodas esportivas
    for (const wx of [-138, 138]) {
      ctx.beginPath(); ctx.arc(wx, 48, 44, 0, Math.PI * 2); outlined(ctx, '#1A202E', 8);
      ctx.beginPath(); ctx.arc(wx, 48, 22, 0, Math.PI * 2); outlined(ctx, '#E5ECF5', 5);
    }
    ctx.restore();
  }

  // ==================================================================== CENAS
  const SC = {};

  // ------------------------------------------------------------------ 1. HOOK
  SC.hook = {
    times(S) {
      return {
        tMoe: S.c('hook', 'moeda'),
        tDia: S.c('hook', 'No') - 0.04,
        tBan: S.w('hook', 'Banco').t0,
        tPan: S.c('hook', 'pânico')
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: 0, pose: 'look_down', expr: 'curious', dur: 0.01 },
        { t: T.tMoe, expr: 'amazed' },
        { t: T.tDia, pose: 'shock_closeup', expr: 'shock', dur: 0.05 },
        { t: T.tPan, pose: 'shock_closeup', expr: 'scream', dur: 0.14, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tMoe, T.tDia, T.tBan, T.tPan]; },
    hud(S, t) {
      const T = this.times(S);
      if (t >= T.tDia) {
        return {
          bar: { day: 35, dayT: T.tDia, label: 'BANCO CENTRAL', value: 'PÂNICO TOTAL', alert: true },
          alert: { text: 'EMERGÊNCIA MONETÁRIA', t0: T.tBan }
        };
      }
      return { bar: null, ruler: null, alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S);
      if (t < T.tDia) {
        // Plano A (Estilo #1 - Choque de numero): moeda brilhante de R$ 1 girando e pousando na mesa!
        const dropK = eBack(clamp(t / 0.55, 0, 1));
        const z = kf(t, [[0, 1.06], [T.tDia, 1.18]]);
        fillScreen(ctx, vGrad(ctx, [[0, '#10253A'], [0.55, '#1D4466'], [1, '#2D1D14']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z, shake: hits(t, [{ t: 0.25, a: 14, d: 0.25 }]) }, t);
        // luz de holofote sobre a moeda
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        glow(ctx, 540, 820, 420, 'rgba(255,220,100,A)', 0.36);
        ctx.restore();
        // Beto espiando curioso atras da mesa
        drawBeto(ctx, st, { x: 315, y: 985, scale: 0.94, t, rim: { color: '#FFE88A', dir: [0.8, -0.5] } });
        // mesa de madeira em primeiro plano
        ctx.fillStyle = vGrad(ctx, [[0, '#A86B3E'], [1, '#633A1D']], 1040, H);
        ctx.fillRect(-200, 1040, W + 400, 960);
        ctx.strokeStyle = INK; ctx.lineWidth = 8; ctx.beginPath(); ctx.moveTo(-200, 1040); ctx.lineTo(W + 200, 1040); ctx.stroke();
        // moeda colossal de 1 REAL sobre a mesa!
        const cy = lerp(420, 885, dropK) + Math.sin(t * 6) * 6;
        contactShadow(ctx, 640, 1110, 175 * clamp(dropK, 0.4, 1), 0.45);
        drawRealCoin(ctx, 640, cy, 175, Math.sin(t * 4) * 0.08);
        pill(ctx, 640, 625, 225, 62, '#FFD400', null, 'DIA 1: R$ 1,00', INK, 34);
        ctx.restore();
        return;
      }
      // Plano B: corte seco para o BANCO CENTRAL em panico com sirene vermelha piscando!
      const lt = t - T.tDia;
      const flash = Math.sin(t * 18) > 0;
      const shake = hits(t, [{ t: T.tDia, a: 28, d: 0.4 }, { t: T.tPan, a: 36, d: 0.55 }]) + 5;
      fillScreen(ctx, vGrad(ctx, [[0, flash ? '#4A0810' : '#0A1026'], [0.5, '#1D1836'], [1, '#1A1C28']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[T.tDia, 1.02], [T.tPan, 1.14, eBack]]), shake }, t);
      // fachada neoclassica do BANCO CENTRAL (com sirene 100% visivel abaixo do banner de alerta!)
      ctx.beginPath(); ctx.moveTo(145, 650); ctx.lineTo(540, 515); ctx.lineTo(935, 650); ctx.closePath();
      outlined(ctx, '#D7DFEC', 8);
      rr(ctx, 165, 650, 750, 480, 6); outlined(ctx, '#B9C4D6', 8);
      // 4 colunas classicas
      for (const cx of [235, 405, 675, 845]) {
        rr(ctx, cx - 34, 675, 68, 445, 6); outlined(ctx, '#E8EEF7', 6);
      }
      // porta escura + placa BANCO CENTRAL
      rr(ctx, 465, 845, 150, 270, 12); outlined(ctx, '#1E2538', 7);
      pill(ctx, 540, 615, 360, 58, '#141B2E', '#FFD400', 'BANCO CENTRAL', '#FFD400', 34);
      // sirene giratoria vermelha piscando no topo do frontao (100% abaixo de EMERGENCIA MONETARIA!)
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 540, 495, flash ? 280 : 140, 'rgba(255,45,45,A)', flash ? 0.65 : 0.25);
      ctx.restore();
      ctx.beginPath(); ctx.arc(540, 495, 28, Math.PI, 0); ctx.closePath(); outlined(ctx, flash ? '#FF3B3B' : '#9E1A1A', 6);
      // chao + notas voando atras do Beto
      ctx.fillStyle = '#2B3142'; ctx.fillRect(-200, 1115, W + 400, 880);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1115); ctx.lineTo(W + 200, 1115); ctx.stroke();
      for (let i = 0; i < 6; i++) {
        drawBill(ctx, 130 + i * 165 + Math.sin(t * 5 + i) * 28, 720 + ((i * 95 + lt * 120) % 360), 86, 44, t * 2 + i, '#49B86B', 'R$');
      }
      // Beto em choque na frente do Banco Central!
      const feet = 1250, bs = 0.86;
      contactShadow(ctx, 540, feet, 95, 0.45);
      drawBeto(ctx, st, {
        x: 540, y: pelvisFromFeet(feet, bs), scale: bs, t,
        rim: { color: flash ? '#FF5C5C' : '#6FD8FF', dir: [0, -1] }
      });
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 2. PREMISSA
  const CASH_BARS = [
    { h: 0.12, lbl: 'R$1', d: 'D1' },
    { h: 0.22, lbl: 'R$16', d: 'D5' },
    { h: 0.34, lbl: 'R$512', d: 'D10' },
    { h: 0.50, lbl: 'R$8k', d: 'D14' },
    { h: 0.72, lbl: '131k', d: 'D18' },
    { h: 1.00, lbl: 'R$1M', d: 'D21' }
  ];
  SC.premissa = {
    keys(S) {
      const s0 = S.start('premissa');
      return [
        { t: s0, pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('premissa', 'dobra'), pose: 'flex', expr: 'amazed', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('premissa', 'meia-noite'), S.c('premissa', 'saldo'), S.c('premissa', 'dobra')]; },
    hud() { return { bar: null, ruler: null, alert: null }; },
    draw(ctx, t, S, st) {
      const s0 = S.start('premissa'), tD = S.w('premissa', 'dobra').t0;
      const shake = hits(t, [{ t: tD, a: 24, d: 0.45 }, { t: s0, a: 10, d: 0.25 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#071F1A'], [0.5, '#0D382E'], [1, '#081826']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.04], [tD, 1.0], [S.end('premissa'), 1.05]]), shake }, t);
      // grade bancaria esmeralda
      const off = (t * 34) % 54;
      ctx.lineWidth = 2;
      for (let x = -54 + off; x < W + 54; x += 54) {
        ctx.strokeStyle = 'rgba(72,240,150,0.14)';
        ctx.beginPath(); ctx.moveTo(x, -200); ctx.lineTo(x, H + 200); ctx.stroke();
      }
      for (let y = -54 + off; y < H + 54; y += 54) {
        ctx.strokeStyle = 'rgba(72,240,150,0.14)';
        ctx.beginPath(); ctx.moveTo(-200, y); ctx.lineTo(W + 200, y); ctx.stroke();
      }
      // relogio digital 00:00 no topo
      pill(ctx, 540, 260, 340, 74, '#0D1726', '#2ED573', '00:00 MEIA-NOITE', '#2ED573', 38);
      const ground = 1265, maxH = 680, pts = [];
      ctx.strokeStyle = '#2ED573'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(40, ground); ctx.lineTo(1040, ground); ctx.stroke();
      CASH_BARS.forEach((b, i) => {
        const x = 395 + i * 104, w = 72;
        const k = clamp((t - (s0 + 0.2 + i * 0.14)) / 0.28, 0, 1);
        const h = b.h * maxH * (k > 0 ? eBack(k) : 0);
        if (h > 1) {
          rr(ctx, x - w / 2, ground - h, w, h, 12);
          const g = ctx.createLinearGradient(0, ground - h, 0, ground);
          g.addColorStop(0, i === 5 ? '#FFE86B' : '#52F295'); g.addColorStop(1, '#198754');
          outlined(ctx, g, 6);
        }
        if (k > 0.6) label(ctx, b.lbl, x, ground - h - 52, 28, '#FFFFFF');
        label(ctx, b.d, x, ground + 40, 32, '#99F5C0');
        pts.push([x, ground - b.h * maxH, k]);
      });
      ctx.save(); ctx.setLineDash([16, 14]); ctx.lineDashOffset = -t * 60;
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 5; ctx.beginPath();
      let started = false;
      for (const p of pts) { if (p[2] <= 0.6) break; started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; }
      ctx.stroke(); ctx.restore();
      // carimbo X2 SALDO no quadrante superior esquerdo livre
      const ks = clamp((t - (tD - 0.05)) / 0.22, 0, 1);
      if (ks > 0) {
        ctx.save(); ctx.translate(390, 570); ctx.rotate(-0.1);
        const sc = 2.2 - 1.2 * eBack(ks); ctx.scale(sc, sc);
        ctx.globalAlpha = clamp(ks * 2, 0, 1);
        label(ctx, 'X2', 0, 0, 215, '#FFD400', 'center', HUD.FONT_CAPTION);
        label(ctx, 'SALDO / DIA', 0, 128, 58, '#52F295', 'center', HUD.FONT_CAPTION);
        ctx.restore();
      }
      const bs = 0.94;
      contactShadow(ctx, 185, ground, 92, 0.36);
      drawBeto(ctx, st, { x: 185, y: pelvisFromFeet(ground, bs), scale: bs, t, rim: { color: '#52F295', dir: [0.8, -0.5] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 3. DIA 1
  SC.dia1 = {
    times(S) { return { tPag: S.c('dia1', 'paga'), tBal: S.w('dia1', 'bala').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia1'), pose: 'look_down', expr: 'curious', dur: 0.01 },
        { t: T.tPag, pose: 'shrug_question', expr: 'shock', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPag, T.tBal]; },
    hud(S, t) {
      const s0 = S.start('dia1');
      return { bar: { day: 1, dayT: s0, label: 'SALDO', value: 'R$ 1' }, customHud: moneyGauge(1), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia1');
      fillScreen(ctx, vGrad(ctx, [[0, '#FFDFAA'], [0.55, '#F5C484'], [1, '#7A5434']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia1'), 1.08]]), shake: 1 }, t);
      // semaforo ao fundo esquerdo (no sinal!)
      rr(ctx, 115, 420, 88, 220, 20); outlined(ctx, '#222836', 7);
      ctx.fillStyle = '#333C4D'; ctx.fillRect(148, 640, 22, 490);
      for (const [cy, col] of [[470, '#FF3B3B'], [530, '#444'], [590, '#444']]) {
        ctx.beginPath(); ctx.arc(159, cy, 22, 0, Math.PI * 2); outlined(ctx, col, 4);
      }
      // balcao / barraca de balas na direita
      ctx.fillStyle = '#B87A48'; ctx.fillRect(-200, 1110, W + 400, 890);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1110); ctx.lineTo(W + 200, 1110); ctx.stroke();
      // pote de vidro cheio de balas coloridas
      const jx = 670, jy = 945;
      rr(ctx, jx - 115, jy - 145, 230, 290, 34); outlined(ctx, 'rgba(215,244,255,0.88)', 8);
      rr(ctx, jx - 86, jy - 185, 172, 46, 12); outlined(ctx, '#E8322A', 7);
      const candyCols = ['#FF5964', '#FFD400', '#35D07F', '#5CEEFF', '#B678FF', '#FF8E3C'];
      for (let i = 0; i < 12; i++) {
        const cx = jx - 68 + (i % 4) * 44, cy = jy - 75 + Math.floor(i / 4) * 62;
        ctx.beginPath(); ctx.ellipse(cx, cy, 24, 15, (i % 2 ? 0.3 : -0.3), 0, Math.PI * 2);
        outlined(ctx, candyCols[i % candyCols.length], 4);
      }
      pill(ctx, jx, jy - 245, 245, 62, '#FFD400', null, 'BALA: R$ 2,00', INK, 34);
      // Beto decepcionado segurando apenas 1 moedinha de R$ 1
      const feet = 1245, bs = 0.92;
      contactShadow(ctx, 355, feet, 92, 0.38);
      drawBeto(ctx, st, { x: 355, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFEBB8', dir: [0.6, -0.7] } });
      drawRealCoin(ctx, 480, 965 + Math.sin(t * 5) * 6, 46, 0);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 4. DIA 5
  SC.dia5 = {
    times(S) { return { tSal: S.c('dia5', 'salgado'), tSuc: S.w('dia5', 'suco').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia5'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tSal, pose: 'flex', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tSal, T.tSuc]; },
    hud(S, t) {
      const s0 = S.start('dia5');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia5', 'reais').t1, 1, 16);
      return { bar: { day: 5, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia5');
      fillScreen(ctx, vGrad(ctx, [[0, '#FFF1D0'], [0.55, '#F2C98A'], [1, '#7A4B2A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia5'), 1.08]]), shake: 1 }, t);
      // azulejos de padaria + letreiro PADARIA
      ctx.strokeStyle = 'rgba(180,120,70,0.22)'; ctx.lineWidth = 3;
      for (let x = -120; x < W + 120; x += 84) { ctx.beginPath(); ctx.moveTo(x, -100); ctx.lineTo(x, 1080); ctx.stroke(); }
      for (let y = -100; y < 1080; y += 84) { ctx.beginPath(); ctx.moveTo(-120, y); ctx.lineTo(W + 120, y); ctx.stroke(); }
      pill(ctx, 480, 440, 290, 68, '#B83227', '#FFD400', 'PADARIA', '#FFF5D6', 42);
      // Beto feliz atras do balcao da padaria
      drawBeto(ctx, st, { x: 315, y: 1005, scale: 0.94, t, rim: { color: '#FFE599', dir: [0.6, -0.7] } });
      // balcao de marmore
      ctx.fillStyle = '#E8DFD1'; ctx.fillRect(-200, 1060, W + 400, 80);
      ctx.fillStyle = '#9C5E34'; ctx.fillRect(-200, 1140, W + 400, 860);
      ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(-200, 1060); ctx.lineTo(W + 200, 1060); ctx.stroke();
      // COXINHA DOURADA GIGANTE num prato!
      ctx.beginPath(); ctx.ellipse(545, 1065, 115, 28, 0, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 6);
      ctx.beginPath();
      ctx.moveTo(545, 865);
      ctx.bezierCurveTo(615, 930, 645, 1040, 545, 1055);
      ctx.bezierCurveTo(445, 1040, 475, 930, 545, 865);
      ctx.closePath();
      outlined(ctx, '#E59B2E', 8);
      // COPO DE SUCO DE LARANJA GELADO com canudo!
      ctx.strokeStyle = INK; ctx.lineWidth = 16; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(755, 845); ctx.lineTo(795, 720); ctx.lineTo(845, 705); ctx.stroke();
      ctx.strokeStyle = '#FF5252'; ctx.lineWidth = 8; ctx.stroke();
      ctx.beginPath(); ctx.moveTo(692, 825); ctx.lineTo(808, 825); ctx.lineTo(790, 1058); ctx.lineTo(710, 1058); ctx.closePath();
      outlined(ctx, '#FFA928', 8);
      ctx.fillStyle = 'rgba(255,255,255,0.45)'; ctx.fillRect(714, 845, 18, 185);
      pill(ctx, 665, 650, 235, 58, '#2ED573', null, 'COMBO R$ 16', INK, 32);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 5. DIA 10
  SC.dia10 = {
    times(S) { return { tLim: S.c('dia10', 'limpa'), tPre: S.w('dia10', 'preço').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia10'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tLim, expr: 'amazed' },
        { t: T.tPre, expr: 'smug' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tLim, T.tPre]; },
    hud(S, t) {
      const s0 = S.start('dia10');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia10', 'reais').t1, 16, 512);
      return { bar: { day: 10, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia10');
      fillScreen(ctx, vGrad(ctx, [[0, '#EAF4FF'], [0.6, '#D0E2F5'], [1, '#A9B8CC']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia10'), 1.09]]), shake: 2 }, t);
      // prateleiras de supermercado passando ao fundo (suavizadas para destacar o carrinho!)
      ctx.save(); ctx.globalAlpha = 0.42;
      for (let row = 0; row < 3; row++) {
        const sy = 590 + row * 185;
        ctx.fillStyle = '#8FA0B8'; ctx.fillRect(-150, sy, W + 300, 16);
        for (let i = 0; i < 8; i++) {
          const px = ((i * 155 - (t - s0) * 190) % 1240 + 1240) % 1240 - 120;
          rr(ctx, px, sy - 80, 84, 80, 8); outlined(ctx, ['#FF6B6B', '#FFD400', '#35D07F', '#4FAFFF'][i % 4], 4);
        }
      }
      ctx.restore();
      // piso polido do mercado
      ctx.fillStyle = '#CFD8E6'; ctx.fillRect(-200, 1185, W + 400, 820);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1185); ctx.lineTo(W + 200, 1185); ctx.stroke();
      // Beto empurrando carrinho lotado ate o teto!
      const feet = 1248, bs = 0.86;
      contactShadow(ctx, 275, feet, 85, 0.35);
      drawBeto(ctx, st, {
        x: 275, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: PUSH_CART, rim: { color: '#FFFFFF', dir: [0, -1] }
      });
      // CARRINHO DE SUPERMERCADO TRANSBORDANDO DE COMPRAS!
      const cx = 615, cy = 1045;
      contactShadow(ctx, cx, feet, 210, 0.35);
      // montanha de caixas e comidas dentro do carrinho
      rr(ctx, cx - 140, cy - 260, 120, 160, 10); outlined(ctx, '#FF6B6B', 6);
      rr(ctx, cx - 15, cy - 305, 130, 195, 10); outlined(ctx, '#FFD400', 6);
      rr(ctx, cx + 65, cy - 220, 110, 135, 10); outlined(ctx, '#35D07F', 6);
      ctx.beginPath(); ctx.arc(cx - 55, cy - 290, 48, 0, Math.PI * 2); outlined(ctx, '#FF9F43', 6);
      // grade do carrinho
      ctx.beginPath();
      ctx.moveTo(cx - 195, cy - 115); ctx.lineTo(cx + 195, cy - 115);
      ctx.lineTo(cx + 150, cy + 85); ctx.lineTo(cx - 160, cy + 85); ctx.closePath();
      outlined(ctx, 'rgba(210,224,240,0.75)', 8);
      ctx.strokeStyle = INK; ctx.lineWidth = 5;
      for (let gx = cx - 125; gx <= cx + 125; gx += 50) { ctx.beginPath(); ctx.moveTo(gx, cy - 115); ctx.lineTo(gx - 10, cy + 85); ctx.stroke(); }
      ctx.beginPath(); ctx.moveTo(cx - 178, cy - 20); ctx.lineTo(cx + 174, cy - 20); ctx.stroke();
      // alca do carrinho ate a mao do Beto + rodinhas
      ctx.strokeStyle = INK; ctx.lineWidth = 14; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(cx - 245, cy - 135); ctx.lineTo(cx - 195, cy - 115); ctx.lineTo(cx - 155, cy + 145); ctx.lineTo(cx + 135, cy + 145); ctx.stroke();
      for (const wx of [cx - 130, cx + 115]) { ctx.beginPath(); ctx.arc(wx, cy + 170, 26, 0, Math.PI * 2); outlined(ctx, '#232836', 6); }
      pill(ctx, 510, 430, 265, 62, '#2ED573', null, 'SEM OLHAR PREÇO', INK, 32);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 6. DIA 14
  SC.dia14 = {
    times(S) { return { tGan: S.c('dia14', 'ganha'), tMes: S.w('dia14', 'meses').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia14'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tMes, pose: 'flex', expr: 'smug', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tGan, T.tMes]; },
    hud(S, t) {
      const s0 = S.start('dia14');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia14', 'reais').t1, 512, 8192);
      return { bar: { day: 14, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia14');
      fillScreen(ctx, vGrad(ctx, [[0, '#092B24'], [0.55, '#135748'], [1, '#08211C']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia14'), 1.1]]), shake: 2 }, t);
      // chuva abundante de cedulas de R$ 100 e R$ 200 (atras dos calendarios e do Beto!)
      for (let i = 0; i < 18; i++) {
        const bx = 90 + hash(i + 140) * 780;
        const by = 340 + ((hash(i + 141) * 960 + t * (210 + (i % 3) * 65)) % 960);
        drawBill(ctx, bx, by, 102, 52, Math.sin(t * 3 + i) * 0.6, i % 2 ? '#4FAFFF' : '#49B86B', i % 2 ? '100' : '200');
      }
      // folhas de calendario (JAN, FEV, MAR, ABR) legiveis no topo!
      const meses = ['JAN', 'FEV', 'MAR', 'ABR'];
      meses.forEach((m, i) => {
        const mx = 165 + i * 215, my = 565 + Math.sin(t * 3 + i) * 20;
        ctx.save(); ctx.translate(mx, my); ctx.rotate((i - 1.5) * 0.12);
        rr(ctx, -70, -78, 140, 156, 14); outlined(ctx, '#FFFFFF', 6);
        ctx.fillStyle = '#E8322A'; ctx.fillRect(-66, -74, 132, 42);
        label(ctx, m, 0, -52, 28, '#FFFFFF');
        label(ctx, '30d', 0, 24, 48, INK);
        ctx.restore();
      });
      // Beto no centro abrindo os bracos sob a chuva de dinheiro!
      const feet = 1248, bs = 0.96;
      contactShadow(ctx, 480, feet, 105, 0.4);
      drawBeto(ctx, st, { x: 480, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#52F295', dir: [0, -1] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 7. DIA 18
  SC.dia18 = {
    times(S) { return { tCar: S.c('dia18', 'carro'), tGar: S.w('dia18', 'garagem').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia18'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: T.tCar, pose: 'shock_closeup', expr: 'amazed', dur: 0.16, ease: 'back' },
        { t: T.tGar, pose: 'flex', expr: 'smug', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tCar, T.tGar]; },
    hud(S, t) {
      const s0 = S.start('dia18');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia18', 'reais').t1, 8192, 131072);
      return { bar: { day: 18, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia18');
      const dropK = eBack(clamp((t - (T.tCar - 0.15)) / 0.55, 0, 1));
      const shake = hits(t, [{ t: T.tGar, a: 22, d: 0.4 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#DCE4F0'], [0.6, '#BAC6D8'], [1, '#586274']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tGar, 1.08]]), shake }, t);
      // portao basculante aberto da garagem
      rr(ctx, 135, 420, 745, 740, 12); outlined(ctx, '#384152', 8);
      for (let y = 450; y < 580; y += 36) { ctx.fillStyle = '#9BA8BC'; ctx.fillRect(145, y, 725, 24); }
      // piso de concreto da garagem
      ctx.fillStyle = '#6D7688'; ctx.fillRect(-200, 1160, W + 400, 840);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1160); ctx.lineTo(W + 200, 1160); ctx.stroke();
      // CARRO ZERO QUILOMETRO VERMELHO caindo na garagem com laco de presente dourado!
      const cy = lerp(490, 1110, dropK);
      contactShadow(ctx, 590, 1215, 285 * clamp(dropK, 0.35, 1), 0.42);
      drawSportsCar(ctx, 590, cy, 1.18, '#E8322A');
      // laco de presente dourado no teto
      ctx.save(); ctx.translate(590, cy - 114);
      ctx.beginPath(); ctx.ellipse(-42, -16, 44, 24, -0.35, 0, Math.PI * 2); outlined(ctx, '#FFD400', 6);
      ctx.beginPath(); ctx.ellipse(42, -16, 44, 24, 0.35, 0, Math.PI * 2); outlined(ctx, '#FFD400', 6);
      ctx.beginPath(); ctx.arc(0, -10, 18, 0, Math.PI * 2); outlined(ctx, '#FFE975', 5);
      ctx.restore();
      pill(ctx, 590, cy - 205, 185, 56, '#FFD400', null, '0 KM NOVO', INK, 32);
      // Beto impressionado a esquerda
      const feet = 1245, bs = 0.86;
      contactShadow(ctx, 210, feet, 85, 0.38);
      drawBeto(ctx, st, { x: 210, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFE880', dir: [0.8, -0.5] } });
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 8. DIA 21
  SC.dia21 = {
    times(S) { return { tMil: S.c('dia21', 'milhão'), tCaf: S.w('dia21', 'café').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia21'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tMil, pose: 'flex', expr: 'smug', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tMil, T.tCaf]; },
    hud(S, t) {
      const s0 = S.start('dia21');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia21', 'reais').t1, 131072, 1048576);
      return { bar: { day: 21, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v, { gold: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia21');
      fillScreen(ctx, vGrad(ctx, [[0, '#FFCC70'], [0.48, '#FFF2CC'], [1, '#B37A48']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia21'), 1.09]]), shake: 1.5 }, t);
      // janela ensolarada da manha + caneca de cafe fumegante no criado-mudo
      rr(ctx, 95, 430, 290, 310, 14); outlined(ctx, '#8FD8FF', 8);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(240, 430); ctx.lineTo(240, 740); ctx.moveTo(95, 585); ctx.lineTo(385, 585); ctx.stroke();
      ctx.fillStyle = '#A86E42'; ctx.fillRect(-200, 1140, W + 400, 860);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1140); ctx.lineTo(W + 200, 1140); ctx.stroke();
      // criado-mudo + caneca de cafe na esquerda
      rr(ctx, 95, 965, 190, 210, 12); outlined(ctx, '#8A5229', 7);
      rr(ctx, 145, 895, 76, 72, 12); outlined(ctx, '#FFFFFF', 6);
      ctx.strokeStyle = INK; ctx.lineWidth = 8; ctx.beginPath(); ctx.arc(228, 932, 18, -1.2, 1.2); ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 5;
      for (const sx of [168, 194]) { ctx.beginPath(); ctx.moveTo(sx, 882); ctx.quadraticCurveTo(sx + Math.sin(t * 5) * 14, 845, sx, 815); ctx.stroke(); }
      // PIRAMIDE GIGANTE DE MACOS DE DINHEIRO!
      for (let row = 0; row < 4; row++) {
        const count = 4 - row;
        for (let k = 0; k < count; k++) {
          const sx = 545 + (k - (count - 1) / 2) * 124;
          const sy = 1175 - row * 56;
          drawCashStack(ctx, sx, sy, 116, 48);
        }
      }
      // Beto no topo da pilha de 1 milhao de reais!
      const feet = 975, bs = 0.84;
      contactShadow(ctx, 545, feet, 85, 0.35);
      drawBeto(ctx, st, { x: 545, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFE875', dir: [0, -1] } });
      pill(ctx, 545, 515, 290, 66, '#FFD400', null, '1 MILHÃO DE REAIS', INK, 34);
      ctx.restore();
    }
  };

  // ----------------------------------------------------------------- 9. DIA 25
  SC.dia25 = {
    times(S) { return { tMan: S.c('dia25', 'mansão'), tBol: S.w('dia25', 'bolso').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia25'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tBol, expr: 'amazed' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tMan, T.tBol]; },
    hud(S, t) {
      const s0 = S.start('dia25');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia25', 'milhões').t1, 1e6, 16e6);
      return { bar: { day: 25, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v, { gold: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('dia25');
      fillScreen(ctx, vGrad(ctx, [[0, '#FF7E5F'], [0.46, '#FEB47B'], [0.7, '#34A853'], [1, '#1E6B38']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [S.end('dia25'), 1.09]]), shake: 1.5 }, t);
      // palmeiras tropicais emoldurando a mansao
      for (const [px, lean] of [[118, -28], [858, 24]]) {
        ctx.strokeStyle = INK; ctx.lineWidth = 22; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(px, 1030); ctx.quadraticCurveTo(px + lean, 760, px + lean * 1.4, 540); ctx.stroke();
        ctx.strokeStyle = '#9C6234'; ctx.lineWidth = 10; ctx.stroke();
        const tx = px + lean * 1.4, ty = 540;
        for (const [dx, dy] of [[-85, -18], [-65, 36], [85, -14], [68, 38], [0, -58]]) {
          ctx.beginPath(); ctx.moveTo(tx, ty); ctx.quadraticCurveTo(tx + dx * 0.6, ty + dy - 26, tx + dx, ty + dy);
          ctx.quadraticCurveTo(tx + dx * 0.5, ty + dy + 12, tx, ty); ctx.closePath();
          outlined(ctx, '#28A745', 5);
        }
      }
      // gramado luxuoso
      ctx.fillStyle = '#2E9648'; ctx.fillRect(-200, 1020, W + 400, 980);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1020); ctx.lineTo(W + 200, 1020); ctx.stroke();
      // MANSAO MODERNA DE VIDRO, MADEIRA E CONCRETO BRANCO!
      rr(ctx, 170, 705, 675, 330, 10); outlined(ctx, '#F7F9FC', 8);
      rr(ctx, 275, 520, 485, 200, 10); outlined(ctx, '#FFFFFF', 8);
      // beiral escuro elegante + sacada
      rr(ctx, 250, 505, 535, 30, 8); outlined(ctx, '#2C344A', 6);
      rr(ctx, 150, 692, 715, 26, 8); outlined(ctx, '#2C344A', 6);
      // janeloes panoramicos + porta principal amadeirada
      rr(ctx, 325, 560, 385, 122, 8); outlined(ctx, '#6FD8FF', 6);
      rr(ctx, 215, 750, 215, 195, 8); outlined(ctx, '#6FD8FF', 6);
      rr(ctx, 460, 775, 105, 250, 8); outlined(ctx, '#8A5229', 6);
      rr(ctx, 595, 750, 215, 195, 8); outlined(ctx, '#6FD8FF', 6);
      // PISCINA TURQUESA GIGANTE NA FRENTE!
      ctx.beginPath(); ctx.moveTo(220, 1065); ctx.lineTo(830, 1065); ctx.lineTo(905, 1235); ctx.lineTo(145, 1235); ctx.closePath();
      outlined(ctx, '#38D9FF', 8);
      ctx.strokeStyle = 'rgba(255,255,255,0.75)'; ctx.lineWidth = 5;
      for (let i = 0; i < 3; i++) {
        const wy = 1110 + i * 42;
        ctx.beginPath(); ctx.moveTo(260 + Math.sin(t * 4 + i) * 18, wy); ctx.lineTo(440 + Math.sin(t * 4 + i) * 18, wy); ctx.stroke();
      }
      // Beto jogando moeda pra cima como troco de bolso!
      const feet = 1245, bs = 0.84;
      contactShadow(ctx, 235, feet, 85, 0.38);
      drawBeto(ctx, st, {
        x: 235, y: pelvisFromFeet(feet, bs), scale: bs, t,
        pose: TOSS_COIN, rim: { color: '#FFE880', dir: [0.6, -0.8] }
      });
      const coinArc = Math.abs(Math.sin(t * 5.2)) * 125;
      drawRealCoin(ctx, 325, 860 - coinArc, 38, t * 7);
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 10. DIA 28
  SC.dia28 = {
    times(S) { return { tJat: S.c('dia28', 'jatinho'), tVis: S.w('dia28', 'vista').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia28'), pose: 'idle', expr: 'smug', dur: 0.01 },
        { t: T.tVis, pose: 'flex', expr: 'amazed', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tJat, T.tVis]; },
    hud(S, t) {
      const s0 = S.start('dia28');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia28', 'milhões').t1, 16777216, 134217728);
      return { bar: { day: 28, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v, { gold: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia28');
      const slideIn = eOut(clamp((t - s0) / 0.85, 0, 1));
      fillScreen(ctx, vGrad(ctx, [[0, '#1D2B64'], [0.45, '#F89B54'], [0.72, '#4A5266'], [1, '#262B38']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tVis, 1.09]]), shake: 1.5 }, t);
      // pista de pouso executiva
      ctx.fillStyle = '#363C4D'; ctx.fillRect(-200, 1070, W + 400, 930);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1070); ctx.lineTo(W + 200, 1070); ctx.stroke();
      // tapete vermelho VIP
      ctx.beginPath(); ctx.moveTo(220, 1130); ctx.lineTo(445, 1130); ctx.lineTo(490, 1295); ctx.lineTo(155, 1295); ctx.closePath();
      outlined(ctx, '#D92B2B', 6);
      // JATINHO PARTICULAR BRANCO E DOURADO!
      const jx = lerp(910, 610, slideIn), jy = 860;
      contactShadow(ctx, jx, 1085, 290, 0.42);
      ctx.save(); ctx.translate(jx, jy); ctx.scale(0.9, 0.9);
      // cauda elegante em T
      ctx.beginPath(); ctx.moveTo(195, -24); ctx.lineTo(295, -215); ctx.lineTo(355, -215); ctx.lineTo(290, -18); ctx.closePath();
      outlined(ctx, '#FFD400', 8);
      // fuselagem aerodinamica
      ctx.beginPath();
      ctx.moveTo(-340, 10); ctx.quadraticCurveTo(-290, -56, -150, -56);
      ctx.lineTo(240, -56); ctx.quadraticCurveTo(325, -42, 325, 12);
      ctx.quadraticCurveTo(300, 52, 200, 52); ctx.lineTo(-220, 48);
      ctx.quadraticCurveTo(-340, 42, -340, 10); ctx.closePath();
      outlined(ctx, '#FFFFFF', 8);
      // faixa dourada + janelas redondas VIP + cockpit
      ctx.fillStyle = '#FFD400'; ctx.fillRect(-245, 4, 510, 16);
      ctx.beginPath(); ctx.moveTo(-285, -18); ctx.lineTo(-215, -36); ctx.lineTo(-215, -4); ctx.lineTo(-285, -4); ctx.closePath();
      outlined(ctx, '#5CEEFF', 5);
      for (let wx = -150; wx <= 155; wx += 48) { ctx.beginPath(); ctx.ellipse(wx, -20, 13, 18, 0, 0, Math.PI * 2); outlined(ctx, '#1C2A45', 4); }
      // asa + trem de pouso
      ctx.beginPath(); ctx.moveTo(-40, 26); ctx.lineTo(95, 26); ctx.lineTo(165, 105); ctx.lineTo(45, 105); ctx.closePath();
      outlined(ctx, '#DDE5F0', 7);
      for (const wx of [-175, 75]) { ctx.beginPath(); ctx.arc(wx, 92, 24, 0, Math.PI * 2); outlined(ctx, '#1A202E', 6); }
      ctx.restore();
      // Beto no tapete vermelho diante do jatinho!
      const feet = 1250, bs = 0.84;
      contactShadow(ctx, 285, feet, 85, 0.4);
      drawBeto(ctx, st, { x: 285, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFE875', dir: [0.8, -0.5] } });
      if (t >= T.tVis - 0.15) pill(ctx, 295, 570, 235, 66, '#FFD400', null, 'PAGO À VISTA', INK, 34);
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 11. DIA 31
  SC.dia31 = {
    times(S) { return { tTra: S.c('dia31', 'travam'), tHac: S.w('dia31', 'hackeou').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia31'), pose: 'shock_closeup', expr: 'shock', dur: 0.01 },
        { t: T.tTra, expr: 'panic' },
        { t: T.tHac, pose: 'shrug_question', expr: 'shock', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tTra, T.tHac]; },
    hud(S, t) {
      const T = this.times(S), s0 = S.start('dia31');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia31', 'reais').t1, 134217728, 1073741824);
      const alert = t >= T.tTra - 0.05;
      return {
        bar: { day: 31, dayT: s0, label: 'SALDO', value: fmtMoney(v), alert },
        customHud: moneyGauge(v, { alert }),
        alert: alert ? { text: 'SISTEMA TRAVADO', t0: T.tTra - 0.05 } : null
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia31');
      const flash = Math.sin(t * 16) > 0;
      const shake = hits(t, [{ t: T.tTra, a: 28, d: 0.5 }, { t: T.tHac, a: 22, d: 0.4 }]) + 3;
      fillScreen(ctx, vGrad(ctx, [[0, '#0C0818'], [0.5, flash ? '#2E0C1C' : '#131A34'], [1, '#0A0D1A']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tHac, 1.1]]), shake }, t);
      // 3 monitores gigantes de banco travados (abaixo do banner de alerta!)
      const screens = [
        [240, 610, 260, 175, 'ERRO 999', '#FF4A4A'],
        [635, 610, 310, 175, 'R$ 1 BILHÃO', '#FFD400'],
        [455, 825, 430, 155, 'CONTA BLOQUEADA?', '#FF5C5C']
      ];
      for (const [sx, sy, sw, sh, txt, col] of screens) {
        rr(ctx, sx - sw / 2, sy - sh / 2, sw, sh, 16); outlined(ctx, '#10182A', 8);
        rr(ctx, sx - sw / 2 + 12, sy - sh / 2 + 12, sw - 24, sh - 24, 10);
        ctx.fillStyle = flash ? 'rgba(255,55,55,0.22)' : 'rgba(55,180,255,0.14)'; ctx.fill();
        label(ctx, txt, sx, sy + 2, 38, col);
      }
      // faiscas eletricas saltando das bordas externas dos monitores!
      ctx.strokeStyle = '#FFE86B'; ctx.lineWidth = 6;
      for (const [sx, sy] of [[118, 575], [778, 565], [228, 865], [705, 860]]) {
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + 20, sy - 24); ctx.lineTo(sx + 6, sy - 40); ctx.lineTo(sx + 30, sy - 62); ctx.stroke();
      }
      // Beto na frente dos monitores dando de ombros inocente!
      const feet = 1255, bs = 0.84;
      contactShadow(ctx, 480, feet, 90, 0.45);
      drawBeto(ctx, st, {
        x: 480, y: pelvisFromFeet(feet, bs), scale: bs, t,
        rim: { color: flash ? '#FF5C5C' : '#5CEEFF', dir: [0, -1] }
      });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 12. DIA 35
  SC.dia35 = {
    times(S) { return { tPas: S.c('dia35', 'passa'), tBil: S.w('dia35', 'bilionários').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia35'), pose: 'soar_spread', expr: 'smug', dur: 0.01 },
        { t: T.tBil, pose: 'flex', expr: 'amazed', dur: 0.18, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tPas, T.tBil]; },
    hud(S, t) {
      const s0 = S.start('dia35');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia35', 'bilhões').t1, 1.07e9, 1.72e10);
      return { bar: { day: 35, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v, { gold: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia35');
      const riseK = eOut(clamp((t - (T.tPas - 0.15)) / 1.2, 0, 1));
      const shake = hits(t, [{ t: T.tBil, a: 20, d: 0.4 }]);
      fillScreen(ctx, vGrad(ctx, [[0, '#091026'], [0.5, '#172554'], [1, '#0B132B']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tBil, 1.08]]), shake }, t);
      pill(ctx, 470, 410, 440, 68, '#101B38', '#FFD400', 'RANKING BILIONÁRIOS', '#FFD400', 38);
      // 4 barras horizontais do ranking onde VOCE dispara pro topo!
      const rivals = [
        { y: 745, name: 'MAGNATA #2', val: 'R$ 15 BI', w: 460 },
        { y: 880, name: 'MAGNATA #3', val: 'R$ 12 BI', w: 390 },
        { y: 1015, name: 'MAGNATA #4', val: 'R$ 9 BI', w: 320 }
      ];
      for (const r of rivals) {
        rr(ctx, 115, r.y - 46, r.w, 92, 16); outlined(ctx, '#3B4B75', 6);
        label(ctx, r.name, 140, r.y - 12, 26, '#B9C8EA', 'left');
        label(ctx, r.val, 140, r.y + 20, 32, '#FFFFFF', 'left');
      }
      // BARRA DOURADA DO BETO SUBINDO FOGUETE PRO #1!
      const betoBarY = lerp(1145, 595, riseK);
      const betoBarW = lerp(310, 675, riseK);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 115 + betoBarW / 2, betoBarY, 220, 'rgba(255,212,0,A)', 0.32);
      ctx.restore();
      rr(ctx, 115, betoBarY - 56, betoBarW, 112, 18);
      const bg = ctx.createLinearGradient(115, 0, 115 + betoBarW, 0);
      bg.addColorStop(0, '#FFD400'); bg.addColorStop(1, '#FF8C00');
      outlined(ctx, bg, 8);
      label(ctx, '#1 VOCÊ', 145, betoBarY - 16, 30, INK, 'left');
      label(ctx, 'R$ 17 BILHÕES', 145, betoBarY + 22, 40, INK, 'left');
      // Beto comemorando a direita do ranking!
      const feet = 1255, bs = 0.78;
      contactShadow(ctx, 735, feet, 80, 0.4);
      drawBeto(ctx, st, { x: 735, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFD400', dir: [-0.8, -0.5] } });
      ctx.restore();
    }
  };

  // --------------------------------------------------------------- 13. DIA 40
  SC.dia40 = {
    times(S) { return { tSal: S.c('dia40', 'saldo'), tPai: S.w('dia40', 'países').t0 }; },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('dia40'), pose: 'soar_spread', expr: 'amazed', dur: 0.01 },
        { t: T.tPai, pose: 'flex', expr: 'shock', dur: 0.2, ease: 'back' }
      ];
    },
    ev(S) { const T = this.times(S); return [S.c('dia40', 'bilhões'), T.tSal, T.tPai]; },
    hud(S, t) {
      const s0 = S.start('dia40');
      const v = HUD.roll(t, s0 + 0.08, S.w('dia40', 'bilhões').t1, 1.72e10, 5.49e11);
      return { bar: { day: 40, dayT: s0, label: 'SALDO', value: fmtMoney(v) }, customHud: moneyGauge(v, { gold: true }), alert: null };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('dia40');
      const shake = hits(t, [{ t: T.tPai, a: 28, d: 0.55 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#09091A'], [0.5, '#1D183A'], [1, '#120F24']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[s0, 1.0], [T.tPai, 1.1]]), shake }, t);
      ctx.fillStyle = '#202236'; ctx.fillRect(-200, 1170, W + 400, 830);
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-200, 1170); ctx.lineTo(W + 200, 1170); ctx.stroke();
      // COFRE COLOSSAL DE OURO (SEU SALDO: R$ 549 BI) esmagando cofres de paises!
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 375, 810, 420, 'rgba(255,212,0,A)', 0.34);
      ctx.restore();
      rr(ctx, 130, 455, 480, 725, 28);
      const vg = ctx.createLinearGradient(130, 455, 610, 1180);
      vg.addColorStop(0, '#FFE875'); vg.addColorStop(0.5, '#E8A818'); vg.addColorStop(1, '#9E620A');
      outlined(ctx, vg, 9);
      // volante redondo do cofre colossal
      ctx.beginPath(); ctx.arc(370, 840, 135, 0, Math.PI * 2); outlined(ctx, '#2C344A', 8);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 14;
      for (let i = 0; i < 6; i++) {
        const a = i * Math.PI / 3 + t * 0.8;
        ctx.beginPath(); ctx.moveTo(370, 840); ctx.lineTo(370 + Math.cos(a) * 112, 840 + Math.sin(a) * 112); ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(370, 840, 38, 0, Math.PI * 2); outlined(ctx, '#FFD400', 6);
      pill(ctx, 370, 560, 345, 68, '#101628', '#FFD400', 'SEU CAIXA: 549 BI', '#FFD400', 34);
      // 3 cofrezinhos minusculos de paises inteiros a direita
      for (let i = 0; i < 3; i++) {
        const px = 670 + i * 75, py = 1175;
        rr(ctx, px - 30, py - 95 - i * 16, 60, 95 + i * 16, 8); outlined(ctx, '#687694', 6);
        label(ctx, 'P' + (i + 1), px, py - 45, 24, '#FFFFFF');
      }
      pill(ctx, 745, 995, 210, 54, '#2C344A', '#9FB8E8', 'PAÍSES INTEIROS', '#FFFFFF', 26);
      // Beto no topo/frente do cofre colossal!
      const feet = 1252, bs = 0.78;
      contactShadow(ctx, 215, feet, 80, 0.45);
      drawBeto(ctx, st, { x: 215, y: pelvisFromFeet(feet, bs), scale: bs, t, rim: { color: '#FFE875', dir: [0.8, -0.5] } });
      ctx.restore();
    }
  };

  // -------------------------------------------------------------- 14. TWIST A
  SC.twist_a = {
    keys(S) {
      return [
        { t: S.start('twist_a'), pose: 'idle', expr: 'curious', dur: 0.01 },
        { t: S.c('twist_a', 'armadilha'), expr: 'shock' },
        { t: S.c('twist_a', 'matemática'), pose: 'shock_closeup', expr: 'panic', dur: 0.25 }
      ];
    },
    ev(S) { return [S.c('twist_a', 'armadilha'), S.c('twist_a', 'matemática'), S.seg('twist_a').t1]; },
    hud() {
      return {
        bar: { day: 40, dayT: -9, label: 'SALDO', value: 'R$ 549 bi' },
        customHud: moneyGauge(5.49e11, { gold: true }),
        alert: null
      };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('twist_a'), tArm = S.c('twist_a', 'armadilha'), tEnd = S.seg('twist_a').t1;
      const z = kf(t, [[s0, 1.12], [tArm, 1.38], [tEnd, 1.24]]);
      fillScreen(ctx, vGrad(ctx, [[0, '#08040A'], [0.55, '#260E18'], [1, '#090612']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 920, z, shake: 2.5 }, t);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      glow(ctx, 540, 820, 480, 'rgba(255,70,70,A)', 0.26);
      ctx.restore();
      drawBeto(ctx, st, { x: 540, y: 960, scale: 1.06, t, rim: { color: '#FF7070', dir: [0, -1] } });
      ctx.restore();
      const hold = clamp((t - tArm) / 0.8, 0, 1);
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
        tExp: S.c('twist_b', 'explode'),
        tMil: S.c('twist_b', 'milhão') - 0.08,
        tPao: S.w('twist_b', 'pão').t0
      };
    },
    keys(S) {
      const T = this.times(S);
      return [
        { t: S.start('twist_b'), pose: 'freefall_scream', expr: 'scream', dur: 0.01 },
        { t: T.tMil, pose: 'shock_closeup', expr: 'panic', dur: 0.14 }
      ];
    },
    ev(S) { const T = this.times(S); return [T.tExp, T.tMil, T.tPao]; },
    hud(S, t) {
      const T = this.times(S), breadNow = t >= T.tMil;
      return {
        bar: { day: 45, dayT: -9, label: breadNow ? 'PREÇO DO PÃO' : 'INFLAÇÃO', value: breadNow ? 'R$ 1 MILHÃO' : 'EXPLOSÃO TOTAL', alert: true },
        customHud: moneyGauge(1.7e13, { alert: true }),
        alert: { text: breadNow ? 'DINHEIRO SEM VALOR' : 'HIPERINFLAÇÃO', t0: breadNow ? T.tMil : S.start('twist_b') }
      };
    },
    draw(ctx, t, S, st) {
      const T = this.times(S), s0 = S.start('twist_b');
      if (t < T.tMil) {
        // Beat 1: avalanche explosiva de papel-moeda + seta vermelha da inflacao subindo!
        const lt = t - s0;
        const shake = hits(t, [{ t: s0, a: 28, d: 0.45 }, { t: T.tExp, a: 42, d: 0.65 }]) + 6;
        fillScreen(ctx, vGrad(ctx, [[0, '#2B060A'], [0.5, '#591018'], [1, '#1A080E']]));
        ctx.save();
        camApply(ctx, { x: 540, y: 960, z: lerp(1.02, 1.16, clamp(lt / 2.2, 0, 1)), shake }, t);
        // grafico vermelho gigante de hiperinflacao disparando pro teto!
        ctx.strokeStyle = '#FF4242'; ctx.lineWidth = 24; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath(); ctx.moveTo(85, 1180); ctx.lineTo(310, 1130); ctx.lineTo(480, 960); ctx.lineTo(660, 565); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(660, 495); ctx.lineTo(595, 595); ctx.lineTo(725, 595); ctx.closePath(); outlined(ctx, '#FF4242', 6);
        // tempestade caotica de cedulas voando
        for (let i = 0; i < 26; i++) {
          const bx = 80 + ((hash(i + 1500) * 820 + t * (160 + (i % 4) * 50)) % 820);
          const by = 430 + ((hash(i + 1501) * 840 - t * (220 + (i % 3) * 70)) % 840 + 840) % 840;
          drawBill(ctx, bx, by, 98, 48, t * 4 + i, i % 3 ? '#49B86B' : '#4FAFFF', 'R$');
        }
        drawBeto(ctx, st, {
          x: 470, y: 990 + Math.sin(t * 7) * 14, scale: 0.92, t,
          rot: Math.sin(t * 5) * 0.14, rim: { color: '#FF7070', dir: [0, -1] }
        });
        ctx.restore();
        return;
      }
      // Beat 2: UM UNICO PAO FRANCES com etiqueta R$ 1.000.000 no balcao da padaria!
      const shake = hits(t, [{ t: T.tMil, a: 28, d: 0.45 }, { t: T.tPao, a: 24, d: 0.4 }]) + 2;
      fillScreen(ctx, vGrad(ctx, [[0, '#2B1810'], [0.55, '#593322'], [1, '#26140D']]));
      ctx.save();
      camApply(ctx, { x: 540, y: 960, z: kf(t, [[T.tMil, 1.04], [S.end('twist_b'), 1.14]]), shake }, t);
      // pilha inutil de macos de dinheiro empilhados a esquerda + Beto em choque atras do balcao
      for (let k = 0; k < 5; k++) { drawCashStack(ctx, 125 + (k % 2) * 20, 1080 - k * 42, 114, 44); }
      drawBeto(ctx, st, { x: 318, y: 975, scale: 0.88, t, rim: { color: '#FF8570', dir: [0.6, -0.8] } });
      // balcao
      ctx.fillStyle = '#E5DAC8'; ctx.fillRect(-200, 1100, W + 400, 75);
      ctx.fillStyle = '#734224'; ctx.fillRect(-200, 1175, W + 400, 830);
      ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(-200, 1100); ctx.lineTo(W + 200, 1100); ctx.stroke();
      // PRATO + UNICO PAO FRANCES MINUSCULO + PLACA GIGANTE R$ 1.000.000!
      ctx.beginPath(); ctx.ellipse(620, 1100, 145, 34, 0, 0, Math.PI * 2); outlined(ctx, '#FFFFFF', 7);
      // pao frances dourado com pestana
      ctx.beginPath(); ctx.ellipse(620, 1068, 92, 54, -0.05, 0, Math.PI * 2); outlined(ctx, '#E09F3E', 8);
      ctx.strokeStyle = '#9E5A14'; ctx.lineWidth = 7; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(575, 1044); ctx.quadraticCurveTo(620, 1030, 665, 1052); ctx.stroke();
      // haste + placa de preco gigantesca R$ 1.000.000!
      ctx.strokeStyle = INK; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(620, 1015); ctx.lineTo(620, 815); ctx.stroke();
      pill(ctx, 620, 765, 365, 115, '#FFD400', '#E8322A', 'R$ 1.000.000', INK, 54);
      label(ctx, '1 PÃO FRANCÊS', 620, 672, 34, '#FFE8B0');
      ctx.restore();
    }
  };

  // ---------------------------------------------------------------- 16. LOOP
  SC.loop = {
    keys(S) {
      return [
        { t: S.start('loop'), pose: 'shrug_question', expr: 'curious', dur: 0.18, ease: 'back' },
        { t: S.c('loop', 'parava'), pose: 'point_hook', expr: 'focus', dur: 0.16, ease: 'back' },
        { t: S.c('loop', 'Comenta'), pose: 'flex', expr: 'smug', dur: 0.16, ease: 'back' }
      ];
    },
    ev(S) { return [S.c('loop', 'parava'), S.c('loop', 'dobrar'), S.c('loop', 'Comenta')]; },
    hud(S) {
      const s0 = S.start('loop');
      return { bar: { day: 25, dayT: s0, label: 'SUA ESCOLHA', value: 'COMENTE' }, ruler: null, alert: null };
    },
    draw(ctx, t, S, st) {
      const s0 = S.start('loop'), s1 = S.end('loop'), tCom = S.c('loop', 'Comenta');
      // fundo dividido: ESQUERDA VERDE (PARAR R$ 16 MI) vs DIREITA CARMIM (DOBRAR X2)
      ctx.fillStyle = vGrad(ctx, [[0, '#0C5C36'], [1, '#062E1B']]); ctx.fillRect(0, 0, W / 2, H);
      ctx.fillStyle = vGrad(ctx, [[0, '#B0141F'], [1, '#54080E']]); ctx.fillRect(W / 2, 0, W / 2, H);
      ctx.strokeStyle = '#FFD400'; ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();
      // duas placas de escolha limpas nas laterais superiores (acima do cabelo do Beto!)
      pill(ctx, 270, 348, 360, 78, '#0A291A', '#2ED573', 'PARAR: 16 MI', '#52F295', 38);
      pill(ctx, 810, 348, 360, 78, '#2B090C', '#FFD400', 'DOBRAR: X2', '#FFD400', 38);
      const z = kf(t, [[s0, 1.55], [s0 + 0.2, 1.82, eBack], [tCom, 2.05, eBack], [s1, 2.25, eIn]]);
      const shake = hits(t, [{ t: s0, a: 24, d: 0.45 }, { t: tCom, a: 16, d: 0.3 }]) + 2;
      const bx = 540, by = 1180;
      const headY = by - (B.DIM.torso + B.DIM.neck + B.DIM.headR * 0.82);
      ctx.save();
      camApply(ctx, { x: bx, y: headY + (960 - 760) / z + 155 / z, z, shake }, t);
      drawBeto(ctx, st, { x: bx, y: by, scale: 1, t, rim: { color: '#FFD400', dir: [0.8, -0.6] } });
      ctx.restore();
    }
  };

  root.SCENES = SC;
})(typeof window !== 'undefined' ? window : globalThis);
