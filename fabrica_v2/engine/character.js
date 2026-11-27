/*
 * character.js : "Beto", personagem 2D rigado para Shorts em Canvas (1080x1920).
 *
 * Rig de 10 articulacoes: pelve, pescoco, ombro E/D, cotovelo E/D, quadril E/D, joelho E/D.
 * Estilo: contorno preto grosso, cabeca grande e expressiva, corpo simples,
 * UM acessorio iconico (moletom vermelho com capuz e cordoes brancos), luz de recorte (rim light),
 * respiracao ociosa continua, piscadas deterministicas, squash and stretch.
 *
 * Contrato: tudo e funcao pura do tempo t (nada de Date.now, nada de estado acumulado).
 *
 * API publica (window.Beto):
 *   Beto.draw(ctx, opts)            desenha o corpo inteiro. Origem = pelve.
 *   Beto.track(keys, t)             resolve pose/expressao/mao num instante a partir de keyframes.
 *   Beto.POSES / Beto.EXPR          bibliotecas reutilizaveis de poses e expressoes.
 *   Beto.drawPointingHand(ctx,...)  mao gigante apontando para a camera (escorco), para ganchos.
 *   Beto.STAND_PELVIS               distancia pelve -> sola do pe na pose em pe (unidades de rig).
 *
 * Angulos das poses em graus. Membros: 0 = para baixo, 90 = para fora (lado do membro),
 * 180 = para cima, negativo = cruza para dentro. Lado direito = lado direito da TELA.
 */
(function (root) {
  'use strict';

  const INK = '#0B0F19';
  const PAL = {
    skin: '#F4B98C', skinShade: '#DE9A6E', blush: '#F07F7F',
    hoodie: '#E8322A', hoodieDark: '#B01E19', hoodieLight: '#FF6A55',
    pants: '#2A3658', pantsDark: '#1C2440',
    shoe: '#F5F2EA', shoeSole: '#C9C2B4', shoeAccent: '#E8322A',
    hair: '#3A2416', eye: '#FFFFFF', mouth: '#4A0F12', tongue: '#E5646A', teeth: '#FFFFFF',
    cord: '#F5F2EA', sweat: '#8FD3FF', frost: '#BFE8FF'
  };
  const D = {
    torso: 104, neck: 8, headR: 70, upperArm: 52, foreArm: 48, thigh: 58, shin: 56,
    hipW: 22, shoulderW: 44, armW: 25, legW: 30, ol: 7
  };
  const STAND_PELVIS = D.thigh + D.shin + 32; // quadril (6) + coxa + canela + sapato (12 + 15)
  const HEIGHT_UNITS = STAND_PELVIS + D.torso + D.neck + D.headR * 0.82 + D.headR + 34; // sola ate a ponta do cabelo
  const RAD = Math.PI / 180;

  // ------------------------------------------------------------------ poses
  const base = {
    lean: 0, head: 0, headDY: 0, crouch: 0,
    ua_r: 14, la_r: 6, ua_l: 14, la_l: 6,
    th_r: 6, sh_r: 2, th_l: 6, sh_l: 2,
    hand_r: 0, hand_l: 0 // 0 aberta, 1 punho, 2 apontando
  };
  function P(o) { return Object.assign({}, base, o); }
  const POSES = {
    idle: P({}),
    point_hook: P({ ua_r: 100, la_r: 112, hand_r: 2, ua_l: 18, la_l: 4, lean: -3, head: 4 }),
    shock_closeup: P({ ua_r: 118, la_r: 148, ua_l: 118, la_l: 148, head: 0, headDY: 4 }),
    flex: P({ ua_r: 95, la_r: 170, ua_l: 95, la_l: 170, hand_r: 1, hand_l: 1, lean: 0 }),
    crouch_charge: P({ crouch: 22, lean: 8, ua_r: -25, la_r: -10, ua_l: -25, la_l: -10, th_r: 48, sh_r: -8, th_l: 48, sh_l: -8, hand_r: 1, hand_l: 1 }),
    jump_up: P({ ua_r: 128, la_r: 150, ua_l: 128, la_l: 150, th_r: 4, sh_r: 12, th_l: 14, sh_l: -6, head: -4 }),
    super_launch: P({ ua_r: 130, la_r: 148, ua_l: 130, la_l: 148, th_r: 2, sh_r: 2, th_l: 2, sh_l: 2, hand_r: 1, hand_l: 1, headDY: -4 }),
    high_jump_arch: P({ lean: -8, ua_r: 120, la_r: 150, ua_l: 110, la_l: 140, th_r: 40, sh_r: -60, th_l: 30, sh_l: -70, head: -18 }),
    soar_spread: P({ ua_r: 92, la_r: 96, ua_l: 92, la_l: 96, th_r: 18, sh_r: 10, th_l: 22, sh_l: 6, head: -6 }),
    dodge_lean: P({ lean: -22, ua_r: 126, la_r: 144, ua_l: 60, la_l: 20, th_r: 30, sh_r: -10, th_l: 10, sh_l: 40, head: -14 }),
    space_float_panic: P({ ua_r: 120, la_r: 146, ua_l: 135, la_l: 95, th_r: 30, sh_r: -20, th_l: 20, sh_l: 35, head: 8, hand_r: 0, hand_l: 0 }),
    freezing_hug: P({ crouch: 6, ua_r: -30, la_r: -120, ua_l: -30, la_l: -120, th_r: 4, sh_r: -2, th_l: 4, sh_l: -2, head: 4, headDY: 6 }),
    freefall_scream: P({ ua_r: 124, la_r: 146, ua_l: 124, la_l: 146, th_r: 30, sh_r: 60, th_l: 20, sh_l: 70, head: 0 }),
    look_down: P({ head: 16, headDY: 6, ua_r: 30, la_r: 10, ua_l: 30, la_l: 10, lean: 6 }),
    shrug_question: P({ ua_r: 60, la_r: 140, ua_l: 60, la_l: 140, head: -8 }),
    land: P({ crouch: 12, lean: 4, ua_r: 70, la_r: 50, ua_l: 70, la_l: 50, th_r: 36, sh_r: -6, th_l: 36, sh_l: -6 })
  };

  // ------------------------------------------------------------ expressoes
  const E0 = {
    browL: 0, browR: 0, browY: 0, lid: 0, eyeOpen: 1, pupil: 1, px: 0, py: 0,
    mouthW: 34, mouthOpen: 0, mouthCurve: 0.3, mouthSkew: 0, teeth: 0, tongue: 0,
    blush: 0, sweat: 0, frost: 0, shiver: 0, sparkle: 0
  };
  function X(o) { return Object.assign({}, E0, o); }
  const EXPR = {
    neutral: X({}),
    shock: X({ browL: 18, browR: 18, browY: -18, eyeOpen: 1.32, pupil: 0.48, mouthW: 30, mouthOpen: 0.75, mouthCurve: -0.2, teeth: 0, tongue: 0.6 }),
    scream: X({ browL: 26, browR: 26, browY: -22, eyeOpen: 1.42, pupil: 0.36, mouthW: 46, mouthOpen: 1.25, mouthCurve: -0.35, teeth: 1, tongue: 1, sweat: 0.6 }),
    smug: X({ browL: -6, browR: 14, browY: -4, lid: 0.42, pupil: 0.95, px: 3, mouthW: 38, mouthCurve: 0.75, mouthSkew: 0.6 }),
    focus: X({ browL: -20, browR: -20, browY: 6, lid: 0.28, pupil: 0.9, mouthW: 26, mouthCurve: -0.1 }),
    amazed: X({ browL: 10, browR: 10, browY: -16, eyeOpen: 1.22, pupil: 1.12, sparkle: 1, mouthW: 40, mouthOpen: 0.7, mouthCurve: 0.85, teeth: 1, tongue: 0.4, blush: 0.6 }),
    panic: X({ browL: 28, browR: 28, browY: -12, eyeOpen: 1.3, pupil: 0.5, px: -2, mouthW: 40, mouthOpen: 0.55, mouthCurve: -0.8, teeth: 1, sweat: 1 }),
    freezing: X({ browL: 22, browR: 22, browY: -6, eyeOpen: 0.95, pupil: 0.62, mouthW: 40, mouthOpen: 0.32, mouthCurve: -0.5, teeth: 1, frost: 1, shiver: 1 }),
    curious: X({ browL: -4, browR: 20, browY: -8, eyeOpen: 1.08, pupil: 0.9, px: 5, py: 3, mouthW: 18, mouthOpen: 0.28, mouthCurve: 0 }),
    determined: X({ browL: -16, browR: -16, browY: 4, lid: 0.18, pupil: 0.95, mouthW: 40, mouthCurve: 0.55, mouthSkew: 0.25, teeth: 1, mouthOpen: 0.18 })
  };

  // --------------------------------------------------------------- helpers
  function lerp(a, b, k) { return a + (b - a) * k; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function easeInOut(k) { return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; }
  function easeOutBack(k) { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); }
  function mixObj(a, b, k) {
    const o = {};
    for (const key in a) o[key] = (typeof a[key] === 'number') ? lerp(a[key], b[key], k) : (k < 0.5 ? a[key] : b[key]);
    return o;
  }
  function hash(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }

  /** Piscada deterministica: devolve 0..1 (1 = olho fechado). */
  function blinkAmount(t, seed) {
    seed = seed || 1;
    let acc = 0.6 + hash(seed) * 1.2, i = 0;
    while (acc < t + 0.2 && i < 400) {
      const d = Math.abs(t - acc);
      if (d < 0.075) return 1 - d / 0.075;
      acc += 2.4 + hash(seed + i * 7.3) * 1.9; i++;
    }
    return 0;
  }

  /**
   * Resolve um rastro de keyframes: keys = [{t, pose, expr, dur, ease:'back'|'inout', exprDur}]
   * ordenados por t. Pose e expressao sao herdadas do key anterior quando ausentes.
   * Devolve {pose, expr, blinkBoost} ja misturados. Uma troca de expressao gera uma piscada curta
   * centrada na troca (transicao natural).
   */
  function track(keys, t) {
    let poseA = POSES.idle, poseB = POSES.idle, pk = 1, pDur = 0.2, pEase = 'inout';
    let exA = EXPR.neutral, exB = EXPR.neutral, ek = 1, blinkBoost = 0;
    let curPose = 'idle', curExpr = 'neutral';
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (k.t > t) break;
      if (k.pose && k.pose !== curPose) {
        poseA = mixObj(poseA, poseB, pEase === 'back' ? easeOutBack(pk) : easeInOut(pk));
        poseB = POSES[k.pose]; curPose = k.pose; pDur = k.dur || 0.2; pEase = k.ease || 'inout';
        pk = clamp((t - k.t) / pDur, 0, 1);
      } else if (curPose === (k.pose || curPose)) {
        // sem troca de pose: progresso continua do ultimo inicio
      }
      if (k.expr && k.expr !== curExpr) {
        exA = mixObj(exA, exB, ek);
        exB = EXPR[k.expr]; curExpr = k.expr;
        ek = clamp((t - k.t) / (k.exprDur || 0.1), 0, 1);
        const d = Math.abs(t - (k.t + 0.03));
        if (d < 0.08) blinkBoost = Math.max(blinkBoost, 1 - d / 0.08);
      }
    }
    // progresso da pose ativa e recalculado pelo ultimo key com pose valida
    for (let i = keys.length - 1; i >= 0; i--) {
      const k = keys[i];
      if (k.t <= t && k.pose === curPose) { pk = clamp((t - k.t) / (k.dur || 0.2), 0, 1); pEase = k.ease || 'inout'; break; }
    }
    for (let i = keys.length - 1; i >= 0; i--) {
      const k = keys[i];
      if (k.t <= t && k.expr === curExpr) { ek = clamp((t - k.t) / (k.exprDur || 0.1), 0, 1); break; }
    }
    const kp = pEase === 'back' ? easeOutBack(pk) : easeInOut(pk);
    return { pose: mixObj(poseA, poseB, kp), expr: mixObj(exA, exB, easeInOut(ek)), blinkBoost, poseName: curPose, exprName: curExpr };
  }

  // ------------------------------------------------------------ primitivas
  function limbVec(angDeg, side) { const a = angDeg * RAD; return [side * Math.sin(a), Math.cos(a)]; }

  function strokeLimb(ctx, pts, w, fill, rim, rimDir) {
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.strokeStyle = INK; ctx.lineWidth = w + D.ol * 2; ctx.stroke();
    if (rim) {
      ctx.strokeStyle = rim; ctx.lineWidth = w; ctx.stroke();
      ctx.save(); ctx.translate(-rimDir[0] * 4, -rimDir[1] * 4);
      ctx.strokeStyle = fill; ctx.lineWidth = w - 8; ctx.stroke();
      ctx.restore();
    } else {
      ctx.strokeStyle = fill; ctx.lineWidth = w; ctx.stroke();
    }
  }

  function fillShapeWithRim(ctx, pathFn, fill, rim, rimDir, k) {
    pathFn(); ctx.fillStyle = INK; ctx.lineWidth = D.ol * 2; ctx.strokeStyle = INK; ctx.stroke();
    if (rim) {
      pathFn(); ctx.fillStyle = rim; ctx.fill();
      ctx.save(); pathFn(); ctx.clip();
      ctx.translate(-rimDir[0] * (k || 9), -rimDir[1] * (k || 9));
      pathFn(); ctx.fillStyle = fill; ctx.fill();
      ctx.restore();
    } else { pathFn(); ctx.fillStyle = fill; ctx.fill(); }
  }

  function drawHand(ctx, x, y, dir, kind, r) {
    r = r || 15;
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(dir[1], dir[0]) - Math.PI / 2);
    ctx.lineCap = 'round';
    if (kind > 1.5) { // apontando
      ctx.beginPath(); ctx.moveTo(0, 4); ctx.lineTo(0, r + 22);
      ctx.strokeStyle = INK; ctx.lineWidth = 11 + D.ol * 2; ctx.stroke();
      ctx.strokeStyle = PAL.skin; ctx.lineWidth = 11; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(0, 4, r, 0, Math.PI * 2);
    ctx.fillStyle = PAL.skin; ctx.strokeStyle = INK; ctx.lineWidth = D.ol; ctx.fill(); ctx.stroke();
    if (kind < 0.5) { // polegar da mao aberta
      ctx.beginPath(); ctx.arc(r * 0.85, -2, r * 0.42, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.moveTo(-r * 0.5, 4); ctx.lineTo(r * 0.5, 4);
      ctx.lineWidth = 3; ctx.stroke();
    }
    ctx.restore();
  }

  function drawShoe(ctx, x, y, dir, side) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(dir[1], dir[0]) - Math.PI / 2);
    ctx.beginPath();
    ctx.ellipse(side * 10, 12, 27, 15, 0, 0, Math.PI * 2);
    ctx.fillStyle = PAL.shoe; ctx.strokeStyle = INK; ctx.lineWidth = D.ol; ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(side * 10 - 22, 20); ctx.lineTo(side * 10 + 22, 20);
    ctx.strokeStyle = PAL.shoeAccent; ctx.lineWidth = 5; ctx.stroke();
    ctx.restore();
  }

  // ------------------------------------------------------------------ face
  function drawFace(ctx, ex, t, blink, opts) {
    const R = D.headR;
    const shiver = ex.shiver * Math.sin(t * 90) * 1.6;
    ctx.save(); ctx.translate(shiver, 0);
    const eyeY = -6 + ex.browY * 0.1, eyeDX = 26;
    // blush e frio
    if (ex.blush > 0.01) {
      ctx.globalAlpha = 0.45 * ex.blush; ctx.fillStyle = PAL.blush;
      ctx.beginPath(); ctx.ellipse(-42, 24, 14, 8, 0, 0, Math.PI * 2); ctx.ellipse(42, 24, 14, 8, 0, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
    }
    for (const side of [-1, 1]) {
      const cx = side * eyeDX + (opts.look || 0) * 4, cy = eyeY;
      const rx = 17, ry = 20 * ex.eyeOpen;
      const lid = clamp(Math.max(ex.lid, blink), 0, 1);
      ctx.save();
      ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = PAL.eye; ctx.fill();
      ctx.clip();
      const pr = 9.5 * ex.pupil;
      const ppx = cx + ex.px + (opts.look || 0) * 6, ppy = cy + ex.py;
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(ppx, ppy, pr, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(ppx - pr * 0.35, ppy - pr * 0.4, Math.max(2, pr * 0.32), 0, Math.PI * 2); ctx.fill();
      if (ex.sparkle > 0.3) { ctx.beginPath(); ctx.arc(ppx + pr * 0.4, ppy + pr * 0.35, 2.2, 0, Math.PI * 2); ctx.fill(); }
      if (lid > 0.01) { // palpebra cobre de cima para baixo
        const ly = cy - ry + 2 * ry * lid;
        ctx.fillStyle = PAL.skin; ctx.fillRect(cx - rx - 2, cy - ry - 4, rx * 2 + 4, ly - (cy - ry) + 4);
        ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(cx - rx, ly); ctx.lineTo(cx + rx, ly); ctx.stroke();
      }
      ctx.restore();
      ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.stroke();
      // sobrancelha
      const bAng = (side < 0 ? ex.browL : ex.browR) * RAD;
      const by = cy - ry - 12 + ex.browY * 0.6;
      ctx.save(); ctx.translate(cx, by); ctx.rotate(-side * bAng);
      ctx.strokeStyle = INK; ctx.lineWidth = 9; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(-14, 0); ctx.lineTo(14, 0); ctx.stroke();
      ctx.restore();
    }
    // nariz
    ctx.strokeStyle = INK; ctx.lineWidth = 4.5; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-2, 14); ctx.quadraticCurveTo(7, 20, 0, 24); ctx.stroke();
    // boca
    const mw = ex.mouthW, mo = ex.mouthOpen, my = 40, c = ex.mouthCurve * 10, sk = ex.mouthSkew * 8;
    const chatter = ex.frost > 0.5 ? Math.abs(Math.sin(t * 38)) * 0.25 : 0;
    const open = Math.max(0, mo - chatter);
    if (open > 0.12) {
      const h = 30 * open;
      const pathM = () => {
        ctx.beginPath();
        ctx.moveTo(-mw / 2, my - c + sk);
        ctx.quadraticCurveTo(0, my - c * 0.2 - h * 0.2, mw / 2, my - c - sk);
        ctx.quadraticCurveTo(mw * 0.42, my + h, 0, my + h * 1.05);
        ctx.quadraticCurveTo(-mw * 0.42, my + h, -mw / 2, my - c + sk);
        ctx.closePath();
      };
      pathM(); ctx.fillStyle = PAL.mouth; ctx.fill();
      ctx.save(); pathM(); ctx.clip();
      if (ex.tongue > 0.05) { ctx.fillStyle = PAL.tongue; ctx.beginPath(); ctx.ellipse(0, my + h * 1.0, mw * 0.32, h * 0.42 * ex.tongue + 2, 0, 0, Math.PI * 2); ctx.fill(); }
      if (ex.teeth > 0.05) { ctx.fillStyle = PAL.teeth; ctx.fillRect(-mw / 2, my - c - 12, mw, 12 + Math.min(9, h * 0.22)); }
      ctx.restore();
      pathM(); ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.stroke();
    } else {
      ctx.beginPath();
      if (ex.frost > 0.5) { // boca tremida de frio
        for (let i = 0; i <= 8; i++) { const x = -mw / 2 + mw * i / 8; const y = my + (i % 2 ? 4 : -4); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
      } else {
        ctx.moveTo(-mw / 2, my - c + sk); ctx.quadraticCurveTo(0, my + c * 1.4, mw / 2, my - c - sk);
      }
      ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.stroke();
    }
    // suor
    if (ex.sweat > 0.05) {
      const k = (t * 1.3) % 1;
      ctx.globalAlpha = ex.sweat * (1 - k * 0.6);
      for (const [sx, sy0] of [[R * 0.78, -R * 0.35], [-R * 0.82, -R * 0.15]]) {
        const sy = sy0 + k * 26;
        ctx.beginPath(); ctx.moveTo(sx, sy - 13); ctx.quadraticCurveTo(sx + 9, sy + 2, sx, sy + 7); ctx.quadraticCurveTo(sx - 9, sy + 2, sx, sy - 13);
        ctx.fillStyle = PAL.sweat; ctx.fill(); ctx.strokeStyle = INK; ctx.lineWidth = 3.5; ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  }

  function drawHead(ctx, ex, t, blink, opts, rim, rimDir) {
    const R = D.headR;
    const wind = opts.wind || [0, 0];
    // orelhas
    for (const s of [-1, 1]) {
      ctx.beginPath(); ctx.ellipse(s * (R - 2), 6, 13, 17, 0, 0, Math.PI * 2);
      ctx.fillStyle = PAL.skin; ctx.strokeStyle = INK; ctx.lineWidth = D.ol; ctx.fill(); ctx.stroke();
    }
    const headPath = () => {
      ctx.beginPath();
      ctx.moveTo(0, -R);
      ctx.bezierCurveTo(R * 0.78, -R, R, -R * 0.55, R, -R * 0.05);
      ctx.bezierCurveTo(R, R * 0.6, R * 0.6, R * 0.95, 0, R * 0.95);
      ctx.bezierCurveTo(-R * 0.6, R * 0.95, -R, R * 0.6, -R, -R * 0.05);
      ctx.bezierCurveTo(-R, -R * 0.55, -R * 0.78, -R, 0, -R);
      ctx.closePath();
    };
    fillShapeWithRim(ctx, headPath, PAL.skin, rim, rimDir, 10);
    // gelo no rosto
    const ex2 = ex;
    if (ex2.frost > 0.05) {
      ctx.save(); headPath(); ctx.clip();
      ctx.globalAlpha = 0.35 * ex2.frost; ctx.fillStyle = PAL.frost; ctx.fillRect(-R, -R, R * 2, R * 2);
      ctx.globalAlpha = 0.9 * ex2.frost; ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 2.5;
      for (let i = 0; i < 7; i++) {
        const a = hash(i + 3) * Math.PI * 2, rr = R * (0.55 + hash(i + 9) * 0.4);
        const x = Math.cos(a) * rr, y = Math.sin(a) * rr;
        ctx.beginPath(); for (let j = 0; j < 3; j++) { const b = j * Math.PI / 3; ctx.moveTo(x - Math.cos(b) * 7, y - Math.sin(b) * 7); ctx.lineTo(x + Math.cos(b) * 7, y + Math.sin(b) * 7); } ctx.stroke();
      }
      ctx.restore(); ctx.globalAlpha = 1;
    }
    // cabelo espetado (vento inclina e abre as pontas sem achatar contra a testa)
    ctx.beginPath();
    const spikes = 7;
    const wMag = Math.hypot(wind[0], wind[1]);
    const wxPush = clamp(wind[0], -50, 50) * 0.32;
    const wDown = clamp(wind[1], 0, 90);
    const wUp = clamp(wind[1], -90, 0);
    ctx.moveTo(-R * 0.92, -R * 0.35);
    for (let i = 0; i <= spikes; i++) {
      const k = i / spikes;
      const ang = Math.PI + k * Math.PI;
      const bx = Math.cos(ang) * R * 0.95, by = Math.sin(ang) * R * 0.95;
      const tipLen = 26 + hash(i) * 12;
      const flutter = wMag > 5 ? Math.sin(t * 22 + i * 2.1) * Math.min(6, wMag * 0.08) : 0;
      const sweepX = wxPush + Math.cos(ang) * wDown * 0.28 + flutter;
      const sweepY = wDown * 0.10 + wUp * 0.28;
      let tx = Math.cos(ang) * (R + tipLen) + sweepX;
      let ty = Math.sin(ang) * (R + tipLen) + sweepY - 6;
      const dist = Math.hypot(tx, ty) || 1;
      const minR = R + tipLen * 0.84;
      if (dist < minR) { tx = tx / dist * minR; ty = ty / dist * minR; }
      if (i < spikes) {
        const nx = Math.cos(ang + Math.PI / spikes) * R * 0.95, ny = Math.sin(ang + Math.PI / spikes) * R * 0.95;
        ctx.lineTo(bx, by); ctx.lineTo(tx, ty); ctx.lineTo(nx * 0.98, ny * 0.98);
      }
    }
    ctx.lineTo(R * 0.92, -R * 0.35);
    ctx.quadraticCurveTo(R * 0.5, -R * 0.58, 0, -R * 0.52);
    ctx.quadraticCurveTo(-R * 0.5, -R * 0.58, -R * 0.92, -R * 0.35);
    ctx.closePath();
    ctx.fillStyle = PAL.hair; ctx.strokeStyle = INK; ctx.lineWidth = D.ol; ctx.lineJoin = 'round';
    ctx.fill(); ctx.stroke();
    drawFace(ctx, ex, t, blink, opts);
  }

  // ------------------------------------------------------------------ draw
  /**
   * opts: {x, y, scale, pose, expr, t, rot (rad), squash (1 = neutro, >1 estica), blink,
   *        wind [dx,dy] em unidades de rig, rim {color, dir:[dx,dy]}, look -1..1, seed}
   * pose/expr aceitam nome (string) ou objeto ja misturado (saida de Beto.track).
   */
  function draw(ctx, o) {
    const pose = typeof o.pose === 'string' ? POSES[o.pose] : (o.pose || POSES.idle);
    const ex = typeof o.expr === 'string' ? EXPR[o.expr] : (o.expr || EXPR.neutral);
    const t = o.t || 0, s = o.scale || 1, sq = o.squash || 1;
    const wind = o.wind || [0, 0];
    const rim = o.rim ? o.rim.color : null;
    const rd = o.rim ? o.rim.dir : [1, -0.4];
    const rl = Math.hypot(rd[0], rd[1]) || 1; const rimDir = [rd[0] / rl, rd[1] / rl];
    const blink = Math.max(o.blink || 0, blinkAmount(t, o.seed || 3));
    const breath = Math.sin(t * Math.PI * 2 / 2.6);

    ctx.save();
    ctx.translate(o.x, o.y); ctx.rotate(o.rot || 0); ctx.scale(s / Math.sqrt(sq), s * sq);
    const crouch = pose.crouch;
    ctx.translate(0, crouch);

    // pernas (origem: pelve)
    const hipR = [D.hipW, 6], hipL = [-D.hipW, 6];
    const legs = [];
    for (const side of [-1, 1]) {
      const hip = side > 0 ? hipR : hipL;
      const th = side > 0 ? pose.th_r : pose.th_l, sh = side > 0 ? pose.sh_r : pose.sh_l;
      const v1 = limbVec(th, side), v2 = limbVec(sh, side);
      const shinLen = D.shin + 0; // canela; a agachada vem do angulo
      const knee = [hip[0] + v1[0] * D.thigh, hip[1] + v1[1] * D.thigh - crouch * 0];
      const foot = [knee[0] + v2[0] * shinLen, knee[1] + v2[1] * shinLen];
      legs.push({ side, hip, knee, foot, v2 });
    }
    for (const L of legs) {
      strokeLimb(ctx, [L.hip, L.knee, L.foot], D.legW, PAL.pants, '#5A6A99', rimDir);
      drawShoe(ctx, L.foot[0], L.foot[1], L.v2, L.side);
    }

    // tronco (inclinacao) + respiracao
    ctx.save();
    ctx.rotate(pose.lean * RAD);
    const tl = D.torso * (1 + breath * 0.012);
    const sw = D.shoulderW * (1 + breath * 0.01);
    // capuz atras da cabeca
    ctx.beginPath(); ctx.ellipse(0, -tl - 8, 52, 30, 0, 0, Math.PI * 2);
    ctx.fillStyle = PAL.hoodieDark; ctx.strokeStyle = INK; ctx.lineWidth = D.ol; ctx.fill(); ctx.stroke();
    const torsoPath = () => {
      ctx.beginPath();
      ctx.moveTo(-D.hipW - 12, 14);
      ctx.quadraticCurveTo(-sw - 10, -tl * 0.45, -sw, -tl + 12);
      ctx.quadraticCurveTo(-sw + 6, -tl - 6, -18, -tl - 4);
      ctx.lineTo(18, -tl - 4);
      ctx.quadraticCurveTo(sw - 6, -tl - 6, sw, -tl + 12);
      ctx.quadraticCurveTo(sw + 10, -tl * 0.45, D.hipW + 12, 14);
      ctx.quadraticCurveTo(0, 22, -D.hipW - 12, 14);
      ctx.closePath();
    };
    ctx.lineJoin = 'round';
    fillShapeWithRim(ctx, torsoPath, PAL.hoodie, rim || PAL.hoodieLight, rimDir, 10);
    // bolso canguru e barra
    ctx.strokeStyle = INK; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(-30, -6); ctx.lineTo(-22, -36); ctx.lineTo(22, -36); ctx.lineTo(30, -6); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-D.hipW - 10, 6); ctx.quadraticCurveTo(0, 14, D.hipW + 10, 6); ctx.stroke();
    // cordoes do capuz (vento)
    for (const s2 of [-1, 1]) {
      const x0 = s2 * 12, y0 = -tl + 2;
      const x1 = x0 + wind[0] * 0.6 + Math.sin(t * 7 + s2) * (Math.abs(wind[0]) + Math.abs(wind[1])) * 0.08;
      const y1 = y0 + 38 + wind[1] * 0.6;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.quadraticCurveTo(x0 + wind[0] * 0.2, y0 + 20, x1, y1);
      ctx.strokeStyle = INK; ctx.lineWidth = 9; ctx.stroke();
      ctx.strokeStyle = PAL.cord; ctx.lineWidth = 4.5; ctx.stroke();
      ctx.beginPath(); ctx.arc(x1, y1, 5, 0, Math.PI * 2); ctx.fillStyle = PAL.cord; ctx.fill(); ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.stroke();
    }

    // cabeca
    ctx.save();
    ctx.translate(0, -tl - D.neck - D.headR * 0.82 + pose.headDY + breath * 1.5);
    ctx.rotate(pose.head * RAD);
    drawHead(ctx, ex, t, blink, o, rim, rimDir);
    ctx.restore();

    // bracos por cima do tronco
    for (const side of [-1, 1]) {
      const sh = [side * (sw - 6), -tl + 16];
      const ua = side > 0 ? pose.ua_r : pose.ua_l, la = side > 0 ? pose.la_r : pose.la_l;
      const flutter = Math.sin(t * 13 + side) * (Math.abs(wind[0]) + Math.abs(wind[1])) * 0.03;
      const v1 = limbVec(ua + flutter, side), v2 = limbVec(la + flutter * 1.6, side);
      const el = [sh[0] + v1[0] * D.upperArm, sh[1] + v1[1] * D.upperArm];
      const hd = [el[0] + v2[0] * D.foreArm, el[1] + v2[1] * D.foreArm];
      strokeLimb(ctx, [sh, el, hd], D.armW, PAL.hoodie, rim || PAL.hoodieLight, rimDir);
      drawHand(ctx, hd[0], hd[1], v2, side > 0 ? pose.hand_r : pose.hand_l);
    }
    ctx.restore(); // tronco
    ctx.restore();
  }

  /** Mao gigante apontando para a camera (escorco): circulo da mao + ponta do dedo em primeiro plano. */
  function drawPointingHand(ctx, x, y, r, rot) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0);
    // manga
    ctx.beginPath(); ctx.ellipse(0, r * 1.25, r * 0.95, r * 0.7, 0, 0, Math.PI * 2);
    ctx.fillStyle = PAL.hoodie; ctx.strokeStyle = INK; ctx.lineWidth = D.ol * 2; ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(0, r * 0.95, r * 0.8, r * 0.38, 0, 0, Math.PI * 2);
    ctx.fillStyle = PAL.hoodieDark; ctx.fill(); ctx.stroke();
    // punho
    ctx.beginPath(); ctx.ellipse(0, r * 0.15, r * 0.82, r * 0.78, 0, 0, Math.PI * 2);
    ctx.fillStyle = PAL.skin; ctx.fill(); ctx.stroke();
    // dedos dobrados
    ctx.lineWidth = D.ol;
    for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(-r * 0.36 + i * r * 0.36, r * 0.55, r * 0.2, Math.PI * 1.05, Math.PI * 1.95); ctx.stroke(); }
    // indicador em escorco, apontando para a lente
    ctx.beginPath(); ctx.arc(r * 0.05, -r * 0.35, r * 0.42, 0, Math.PI * 2);
    ctx.fillStyle = PAL.skin; ctx.lineWidth = D.ol * 2; ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(r * 0.05, -r * 0.42, r * 0.2, r * 0.14, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#F7D2B6'; ctx.lineWidth = D.ol * 0.8; ctx.fill(); ctx.stroke();
    ctx.restore();
  }

  root.Beto = { draw, track, POSES, EXPR, PAL, INK, DIM: D, STAND_PELVIS, HEIGHT_UNITS, blinkAmount, drawPointingHand, mixObj };
})(typeof window !== 'undefined' ? window : globalThis);
