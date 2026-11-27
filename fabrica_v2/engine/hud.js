/*
 * hud.js : HUD de videogame + legendas palavra por palavra para Shorts 1080x1920.
 *
 * Regras de layout (verificaveis):
 *  - Toda caixa tem borda completa nos 4 lados (nunca barra colorida em um lado so).
 *  - Rotulo e valor sao medidos com ctx.measureText e empilhados (rotulo pequeno em cima,
 *    valor grande embaixo), entao nunca colidem, qualquer que seja o tamanho do numero.
 *  - Legendas: blocos de ate 3 palavras / 16 caracteres, quebra em pontuacao e troca de segmento,
 *    branco com contorno preto grosso (18px) e palavra ativa em amarelo #FFD400.
 *  - Contador animado e grafico; o valor final sempre para no numero exato do roteiro.
 *
 * API (window.HUD): drawTopBar, drawAlert, drawRuler, drawCaptions, buildChunks,
 *                   fmtAlt, fmtNum, roll, FONT_DISPLAY, FONT_CAPTION, COLORS.
 */
(function (root) {
  'use strict';

  const COLORS = {
    ink: '#0B0F19', panel: 'rgba(11,15,25,0.80)', border: 'rgba(255,255,255,0.88)',
    accent: '#FFD400', alert: '#FF2E3B', label: '#A9BCE0', white: '#FFFFFF'
  };
  const FONT_DISPLAY = '"Anton", "Liberation Sans Narrow", "DejaVu Sans", sans-serif';
  const FONT_CAPTION = '"Luckiest Guy", "Anton", "DejaVu Sans", sans-serif';
  const W = 1080;

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function easeOutCubic(k) { return 1 - Math.pow(1 - k, 3); }
  function easeOutBack(k) { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r); ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h); ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r); ctx.arcTo(x, y, x + r, y, r); ctx.closePath();
  }

  /** Formata numero no padrao pt-BR (virgula decimal, ponto de milhar). */
  function fmtNum(v, dec) {
    const s = v.toFixed(dec);
    let [i, d] = s.split('.');
    i = i.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    if (d) { d = d.replace(/0+$/, ''); }
    return d ? i + ',' + d : i;
  }
  /** Altura em metros -> "0,5 m", "2,45 m", "256 m", "2 km", "131 km". */
  function fmtAlt(m) {
    if (m < 10) return fmtNum(m, 2) + ' m';
    if (m < 1000) return fmtNum(Math.round(m), 0) + ' m';
    const km = m / 1000;
    if (km < 10) return fmtNum(km, 1) + ' km';
    return fmtNum(Math.round(km), 0) + ' km';
  }
  /** Contador com easing, em escala log quando os valores sao positivos (crescimento exponencial). */
  function roll(t, t0, t1, v0, v1, mode) {
    const k = easeOutCubic(clamp((t - t0) / Math.max(1e-3, t1 - t0), 0, 1));
    if (mode === 'lin' || v0 <= 0 || v1 <= 0) return v0 + (v1 - v0) * k;
    return Math.exp(Math.log(v0) + (Math.log(v1) - Math.log(v0)) * k);
  }

  // --------------------------------------------------------------- top bar
  /**
   * o: {t, day, dayT, label, value, alert, alpha, y}
   * Painel centralizado: [selo DIA N] | [ROTULO em cima / VALOR embaixo]. Borda completa.
   */
  function drawTopBar(ctx, o) {
    const a = o.alpha === undefined ? 1 : o.alpha;
    if (a <= 0.01) return;
    const y = o.y || 132;
    ctx.save(); ctx.globalAlpha = a;
    const padX = 26, gap = 24, h = 150;
    ctx.font = `64px ${FONT_DISPLAY}`;
    const dayTxt = 'DIA ' + o.day;
    const dayW = Math.max(ctx.measureText('DIA 00').width, ctx.measureText(dayTxt).width) + 44;
    ctx.font = `34px ${FONT_DISPLAY}`;
    const labW = ctx.measureText(o.label).width;
    ctx.font = `76px ${FONT_DISPLAY}`;
    const valW = Math.max(ctx.measureText(o.value).width, ctx.measureText('000 km').width);
    const rightW = Math.max(labW, valW);
    const totalW = padX + dayW + gap + rightW + padX;
    const x = (W - totalW) / 2;
    const pulse = o.alert ? 0.5 + 0.5 * Math.sin(o.t * Math.PI * 2 * 2.2) : 0;
    // painel
    roundRect(ctx, x, y, totalW, h, 30);
    ctx.fillStyle = COLORS.panel; ctx.fill();
    ctx.lineWidth = o.alert ? 6 : 4;
    ctx.strokeStyle = o.alert ? `rgba(255,46,59,${0.6 + 0.4 * pulse})` : COLORS.border;
    ctx.stroke();
    // selo do dia com pop quando o dia muda
    const pk = clamp((o.t - (o.dayT || -9)) / 0.28, 0, 1);
    const ps = pk < 1 ? 0.6 + 0.4 * easeOutBack(pk) : 1;
    const bx = x + padX, by = y + 22, bh = h - 44;
    ctx.save(); ctx.translate(bx + dayW / 2, by + bh / 2); ctx.scale(ps, ps);
    roundRect(ctx, -dayW / 2, -bh / 2, dayW, bh, 20);
    ctx.fillStyle = COLORS.accent; ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = COLORS.ink; ctx.stroke();
    ctx.fillStyle = COLORS.ink; ctx.font = `64px ${FONT_DISPLAY}`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(dayTxt, 0, 3);
    ctx.restore();
    // rotulo (linha pequena) e valor (linha grande): pilha sem colisao
    const rx = bx + dayW + gap;
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.font = `34px ${FONT_DISPLAY}`;
    ctx.fillStyle = o.alert ? '#FF8A92' : COLORS.label;
    ctx.fillText(o.label, rx, y + 52);
    ctx.font = `76px ${FONT_DISPLAY}`;
    ctx.fillStyle = o.alert ? (pulse > 0.5 ? '#FFFFFF' : '#FFC2C6') : COLORS.white;
    ctx.fillText(o.value, rx, y + 130);
    ctx.restore();
  }

  /** Icone de alerta (triangulo) desenhado em vetor, nunca emoji. */
  function warnIcon(ctx, x, y, s, color) {
    ctx.save(); ctx.translate(x, y);
    ctx.beginPath(); ctx.moveTo(0, -s * 0.55); ctx.lineTo(s * 0.55, s * 0.45); ctx.lineTo(-s * 0.55, s * 0.45); ctx.closePath();
    ctx.fillStyle = color; ctx.fill(); ctx.lineWidth = 4; ctx.strokeStyle = COLORS.ink; ctx.stroke();
    ctx.fillStyle = COLORS.ink; ctx.fillRect(-s * 0.06, -s * 0.22, s * 0.12, s * 0.36);
    ctx.beginPath(); ctx.arc(0, s * 0.28, s * 0.07, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  /** Faixa de alerta pulsante com borda completa. o: {t, t0, text, y, alpha} */
  function drawAlert(ctx, o) {
    const k = clamp((o.t - o.t0) / 0.22, 0, 1);
    if (k <= 0) return;
    const a = (o.alpha === undefined ? 1 : o.alpha);
    const y = o.y || 312;
    const pulse = 0.5 + 0.5 * Math.sin((o.t - o.t0) * Math.PI * 2 * 3);
    ctx.save(); ctx.globalAlpha = a;
    ctx.font = `52px ${FONT_DISPLAY}`;
    const tw = ctx.measureText(o.text).width;
    const w = tw + 130, h = 88, x = (W - w) / 2;
    ctx.translate(W / 2, y + h / 2); ctx.scale(0.7 + 0.3 * easeOutBack(k), 0.7 + 0.3 * easeOutBack(k)); ctx.translate(-W / 2, -(y + h / 2));
    roundRect(ctx, x, y, w, h, 22);
    ctx.fillStyle = `rgba(${150 + 105 * pulse | 0},20,32,0.92)`; ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
    warnIcon(ctx, x + 50, y + h / 2, 52, COLORS.accent);
    ctx.fillStyle = '#FFFFFF'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(o.text, x + 92, y + h / 2 + 3);
    ctx.restore();
  }

  // ---------------------------------------------------------------- regua
  const RULER_MARKS = [
    { m: 1, txt: '1 m' }, { m: 10, txt: '10 m' }, { m: 100, txt: '100 m' },
    { m: 1000, txt: '1 km' }, { m: 10000, txt: '10 km' }, { m: 100000, txt: '100 km' }
  ];
  /** Regua vertical logaritmica (0,3 m .. 200 km) na borda direita: a grandeza constante do video. */
  function drawRuler(ctx, o) {
    const a = o.alpha === undefined ? 1 : o.alpha;
    if (a <= 0.01) return;
    const x = 1012, y0 = 1080, y1 = 360;
    const lmin = Math.log10(0.3), lmax = Math.log10(200000);
    const yOf = m => y0 - (Math.log10(Math.max(0.3, m)) - lmin) / (lmax - lmin) * (y0 - y1);
    ctx.save(); ctx.globalAlpha = a;
    roundRect(ctx, x - 14, y1 - 26, 28, y0 - y1 + 52, 14);
    ctx.fillStyle = 'rgba(11,15,25,0.62)'; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.75)'; ctx.stroke();
    // preenchimento ate a altura atual
    const ym = yOf(o.meters);
    roundRect(ctx, x - 7, ym, 14, Math.max(0, y0 + 12 - ym), 7);
    ctx.fillStyle = o.alert ? COLORS.alert : COLORS.accent; ctx.fill();
    ctx.font = `30px ${FONT_DISPLAY}`; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const mk of RULER_MARKS) {
      const yy = yOf(mk.m);
      ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x - 14, yy); ctx.lineTo(x - 26, yy); ctx.stroke();
      ctx.lineWidth = 6; ctx.strokeStyle = 'rgba(11,15,25,0.9)'; ctx.lineJoin = 'round';
      ctx.strokeText(mk.txt, x - 32, yy + 1);
      ctx.fillStyle = 'rgba(255,255,255,0.92)'; ctx.fillText(mk.txt, x - 32, yy + 1);
    }
    // marcador do Beto: losango com contorno
    ctx.save(); ctx.translate(x, ym);
    ctx.beginPath(); ctx.moveTo(0, -20); ctx.lineTo(20, 0); ctx.lineTo(0, 20); ctx.lineTo(-20, 0); ctx.closePath();
    ctx.fillStyle = '#E8322A'; ctx.fill(); ctx.lineWidth = 5; ctx.strokeStyle = '#FFFFFF'; ctx.stroke();
    ctx.restore();
    ctx.restore();
  }

  // -------------------------------------------------------------- legendas
  /** Agrupa palavras em blocos de leitura. words: [{texto, pont, t0, t1, seg}] */
  function buildChunks(words, maxWords, maxChars) {
    maxWords = maxWords || 3; maxChars = maxChars || 16;
    const chunks = []; let cur = [];
    const flush = () => { if (cur.length) { chunks.push(cur); cur = []; } };
    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      if (cur.length && cur[0].seg !== w.seg) flush();
      const len = cur.reduce((s, x) => s + x.texto.length + 1, 0) + w.texto.length;
      if (cur.length && (cur.length >= maxWords || len > maxChars)) flush();
      cur.push(w);
      if (/[\.\!\?\:]/.test(w.pont || '') || (/,/.test(w.pont || '') && cur.length >= 2)) flush();
    }
    flush();
    return chunks.map((ws, i) => ({
      words: ws,
      t0: ws[0].t0 - 0.04,
      t1: (i + 1 < chunks.length + 1) ? null : null
    })).map((c, i, arr) => {
      const next = arr[i + 1];
      const last = c.words[c.words.length - 1];
      c.t1 = next ? Math.min(next.t0, last.t1 + 0.55) : last.t1 + 1.2;
      return c;
    });
  }

  /** o: {y, size, maxW, hidden} */
  function drawCaptions(ctx, chunks, t, o) {
    o = o || {};
    let c = null;
    for (const ch of chunks) { if (t >= ch.t0 && t < ch.t1) { c = ch; break; } }
    if (!c && chunks.length && t < chunks[0].t0 && t >= 0) c = chunks[0].t0 < 0.2 ? chunks[0] : null;
    if (!c) return;
    const size = o.size || 92, y = o.y || 1390, maxW = o.maxW || 900;
    ctx.save();
    ctx.font = `${size}px ${FONT_CAPTION}`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'; ctx.miterLimit = 2;
    const toks = c.words.map((w, i) => {
      const txt = (w.texto + (/[!?]/.test(w.pont || '') ? w.pont.replace(/[^!?]/g, '') : '')).toLocaleUpperCase('pt-BR');
      const m = ctx.measureText(txt);
      const inked = (m.actualBoundingBoxLeft || 0) + (m.actualBoundingBoxRight || 0);
      return { w, txt, width: Math.max(m.width, inked) };
    });
    const space = Math.max(ctx.measureText(' ').width * 2.0, size * 0.44);
    // quebra em linhas se passar da largura maxima
    const lines = []; let line = [], lw = 0;
    for (const tk of toks) {
      const add = (line.length ? space : 0) + tk.width;
      if (line.length && lw + add > maxW) { lines.push({ toks: line, w: lw }); line = []; lw = 0; }
      lw += (line.length ? space : 0) + tk.width; line.push(tk);
    }
    if (line.length) lines.push({ toks: line, w: lw });
    // escala de seguranca se uma unica palavra exceder a largura
    const widest = Math.max(...lines.map(l => l.w));
    const fit = widest > maxW ? maxW / widest : 1;
    const enter = clamp((t - c.t0) / 0.09, 0, 1);
    const es = (0.86 + 0.14 * easeOutBack(enter)) * fit;
    const lh = size * 1.12;
    ctx.translate(W / 2, y); ctx.scale(es, es);
    lines.forEach((ln, li) => {
      let x = -ln.w / 2;
      const yy = (li - (lines.length - 1) / 2) * lh;
      for (const tk of ln.toks) {
        const active = t >= tk.w.t0 - 0.02 && (t < tk.w.t1 + 0.12 || tk === ln.toks[ln.toks.length - 1] && li === lines.length - 1);
        const nextIdx = c.words.indexOf(tk.w) + 1;
        const nextStart = nextIdx < c.words.length ? c.words[nextIdx].t0 - 0.02 : Infinity;
        const isActive = t >= tk.w.t0 - 0.02 && t < nextStart;
        const pop = isActive ? 1 + 0.06 * Math.max(0, 1 - (t - tk.w.t0) / 0.14) : 1;
        ctx.save();
        ctx.translate(x + tk.width / 2, yy); ctx.scale(pop, pop);
        ctx.textAlign = 'center';
        ctx.lineWidth = 18; ctx.strokeStyle = COLORS.ink; ctx.strokeText(tk.txt, 0, 0);
        ctx.fillStyle = isActive ? COLORS.accent : COLORS.white;
        ctx.fillText(tk.txt, 0, 0);
        ctx.restore();
        x += tk.width + space;
        void active;
      }
    });
    ctx.restore();
  }

  root.HUD = { drawTopBar, drawAlert, drawRuler, drawCaptions, buildChunks, fmtAlt, fmtNum, roll, roundRect, warnIcon, COLORS, FONT_DISPLAY, FONT_CAPTION };
})(typeof window !== 'undefined' ? window : globalThis);
