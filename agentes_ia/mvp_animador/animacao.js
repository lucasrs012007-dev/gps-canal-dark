/*
 * animacao.js : Motor HTML5 Canvas 9:16 (540x960) do StudioStick IA.
 *
 * Zero dependencias externas, 100% offline (compativel com file:// em celular e PC).
 * Exporta window.StudioStickCanvas com { PRESETS, createPlayer }.
 *
 * Inspirado na estetica de boneco articulado expressivo (contorno grosso #0B0F19,
 * moletom vermelho #E8322A com cordoes brancos, rim light, piscadas deterministicas,
 * squash and stretch) e HUD de videogame com borda completa nos 4 lados.
 */
(function (root) {
  'use strict';

  var W = 540;
  var H = 960;
  var DURATION = 10;
  var DEFAULT_TEMA = 'E se voce ganhasse 1 real dobrando todo dia?';
  var DEFAULT_PRESET = 'escala_viral';

  var PRESETS = [
    {
      id: 'escala_viral',
      nome: 'Escala Viral 2D',
      tag: 'Gratis',
      pro: false,
      descricao: 'Boneco expressivo, medidor exponencial e explosao visual em 10s'
    },
    {
      id: 'caos_sonoro',
      nome: 'Onda de Choque',
      tag: 'Pro',
      pro: true,
      descricao: 'Camera shake forte, aneis sonoros e cortes rapidos de panico'
    },
    {
      id: 'suspense_noir',
      nome: 'Suspense Noir',
      tag: 'Pro',
      pro: true,
      descricao: 'Spotlight dramatico, cronometro regressivo e clima de tensao'
    }
  ];

  var COLORS = {
    ink: '#0B0F19',
    panel: 'rgba(11, 15, 25, 0.84)',
    panelStrong: 'rgba(11, 15, 25, 0.92)',
    border: 'rgba(255, 255, 255, 0.86)',
    borderSoft: 'rgba(255, 255, 255, 0.45)',
    accent: '#FFD400',
    alert: '#FF2E3B',
    alertSoft: '#FF8A92',
    label: '#A9BCE0',
    white: '#FFFFFF'
  };

  var FONT_DISPLAY = '"Anton", "Impact", "Arial Narrow", "Roboto Condensed", "DejaVu Sans", sans-serif';
  var FONT_CAPTION = '"Luckiest Guy", "Anton", "Impact", "Arial Black", "DejaVu Sans", sans-serif';
  var FONT_UI = '"Inter", "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif';

  var RAD = Math.PI / 180;

  // --------------------------------------------------------------- utilitarios
  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  function lerp(a, b, k) {
    return a + (b - a) * k;
  }

  function invLerp(a, b, v) {
    if (b === a) return 0;
    return clamp((v - a) / (b - a), 0, 1);
  }

  function easeOutCubic(k) {
    var u = 1 - clamp(k, 0, 1);
    return 1 - u * u * u;
  }

  function easeInOutCubic(k) {
    var x = clamp(k, 0, 1);
    return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  }

  function easeOutBack(k) {
    var x = clamp(k, 0, 1);
    var c1 = 1.70158;
    var c3 = c1 + 1;
    return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
  }

  function mixObj(a, b, k) {
    var o = {};
    for (var key in a) {
      if (Object.prototype.hasOwnProperty.call(a, key)) {
        o[key] = typeof a[key] === 'number' ? lerp(a[key], b[key], k) : (k < 0.5 ? a[key] : b[key]);
      }
    }
    return o;
  }

  function hash(n) {
    var s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return s - Math.floor(s);
  }

  function roundRect(ctx, x, y, w, h, r) {
    var rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.arcTo(x + w, y, x + w, y + rr, rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
    ctx.lineTo(x + rr, y + h);
    ctx.arcTo(x, y + h, x, y + h - rr, rr);
    ctx.lineTo(x, y + rr);
    ctx.arcTo(x, y, x + rr, y, rr);
    ctx.closePath();
  }

  function stripAccents(str) {
    var text = String(str || '');
    if (typeof text.normalize === 'function') {
      return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }
    return text.toLowerCase();
  }

  function fmtNum(v, dec) {
    var s = v.toFixed(dec);
    var parts = s.split('.');
    var intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    var decPart = parts[1] ? parts[1].replace(/0+$/, '') : '';
    return decPart ? intPart + ',' + decPart : intPart;
  }

  function expScale(minVal, maxVal, p) {
    var k = clamp(p, 0, 1);
    return Math.exp(Math.log(minVal) + (Math.log(maxVal) - Math.log(minVal)) * k);
  }

  function sanitizeText(str) {
    return String(str || '')
      .replace(/[\u2014\u2013]/g, ' - ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function resolvePresetId(id) {
    for (var i = 0; i < PRESETS.length; i++) {
      if (PRESETS[i].id === id) return id;
    }
    return DEFAULT_PRESET;
  }

  // ------------------------------------------------------ deteccao de tema
  function detectTheme(tema) {
    var norm = stripAccents(tema);

    if (/\b(dinheiro|real|reais|pix|rico|rica|milhao|milhoes|bilhao|bilhoes|dolar|moeda|ouro|conta|banco|salario|fortuna|dobrar|dobro|centavo|grana|lucro|milionario|bilionario)\b/.test(norm)) {
      return {
        id: 'dinheiro',
        propsType: 'money',
        palette: {
          bgTop: '#071B16',
          bgMid: '#0E3B2F',
          bgBottom: '#185A44',
          floorTop: '#0A261E',
          floorBottom: '#051410',
          accent: '#FFD400',
          secondary: '#3CE896',
          rim: '#FFE373',
          rays: 'rgba(255, 212, 0, 0.20)'
        },
        hud: {
          badgePrefix: 'DIA ',
          badgeStart: 1,
          badgeEnd: 24,
          label: 'SALDO TOTAL',
          marks: ['R$ 1', 'R$ 1K', 'R$ 50K', 'R$ 1M', '16 MI'],
          formatValue: function (p) {
            var v = expScale(1, 16000000, p);
            if (v < 1000) return 'R$ ' + fmtNum(Math.round(v), 0);
            if (v < 1000000) return 'R$ ' + fmtNum(Math.round(v / 1000), 0) + ' MIL';
            var mi = v / 1000000;
            return 'R$ ' + (mi >= 10 ? fmtNum(Math.round(mi), 0) : fmtNum(mi, 1)) + ' MI';
          }
        },
        act2Phrases: ['CADA DIA MULTIPLICA', 'O SALDO DISPARA'],
        act3Phrases: ['A CONTA EXPLODIU!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(velocidade|correr|corrida|rapido|rapida|veloz|mach|luz|turbo|acelerar|carro|aviao|foguete|voar|pular|salto|vento|km|quilometro)\b/.test(norm)) {
      return {
        id: 'velocidade',
        propsType: 'speed',
        palette: {
          bgTop: '#06142B',
          bgMid: '#0E2E61',
          bgBottom: '#1B5599',
          floorTop: '#091E40',
          floorBottom: '#040E21',
          accent: '#38D9FF',
          secondary: '#FFD400',
          rim: '#75E8FF',
          rays: 'rgba(56, 217, 255, 0.22)'
        },
        hud: {
          badgePrefix: 'FASE ',
          badgeStart: 1,
          badgeEnd: 10,
          label: 'VELOCIDADE',
          marks: ['10', '100', '600', 'M 1', 'MACH 5'],
          formatValue: function (p) {
            var kmh = expScale(10, 6174, p);
            if (kmh < 1235) return fmtNum(Math.round(kmh), 0) + ' km/h';
            var mach = kmh / 1234.8;
            return 'MACH ' + (mach >= 4.9 ? '5' : fmtNum(mach, 1));
          }
        },
        act2Phrases: ['ACELERACAO SEM FREIO', 'O AR COMECA A QUEIMAR'],
        act3Phrases: ['BARREIRA DO SOM ROMPIDA!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(forca|forte|peso|musculo|soco|levantar|tonelada|quebrar|esmagar|gravidade|pesado|academia|treino|impacto|poder)\b/.test(norm)) {
      return {
        id: 'forca',
        propsType: 'strength',
        palette: {
          bgTop: '#1E0A10',
          bgMid: '#4A141E',
          bgBottom: '#78251C',
          floorTop: '#260E14',
          floorBottom: '#12060A',
          accent: '#FF8524',
          secondary: '#FFD400',
          rim: '#FFB673',
          rays: 'rgba(255, 133, 36, 0.22)'
        },
        hud: {
          badgePrefix: 'NIVEL ',
          badgeStart: 1,
          badgeEnd: 10,
          label: 'FORCA BRUTA',
          marks: ['50kg', '500kg', '5T', '50T', '500T'],
          formatValue: function (p) {
            var kg = expScale(50, 500000, p);
            if (kg < 1000) return fmtNum(Math.round(kg), 0) + ' kg';
            var ton = kg / 1000;
            return (ton >= 10 ? fmtNum(Math.round(ton), 0) : fmtNum(ton, 1)) + ' TON';
          }
        },
        act2Phrases: ['O CHAO COMECA A RACHAR', 'PRESSAO FORA DO NORMAL'],
        act3Phrases: ['IMPACTO COLOSSAL!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(encolher|altura|tamanho|gigante|pequeno|pequena|crescer|formiga|atomo|micro|metro|grande|diminuir|mini|colossal|enorme)\b/.test(norm)) {
      var isShrink = /\b(encolher|pequeno|pequena|formiga|atomo|micro|diminuir|mini)\b/.test(norm);
      return {
        id: 'encolher',
        propsType: 'scale',
        shrink: isShrink,
        palette: {
          bgTop: '#120C2B',
          bgMid: '#261A59',
          bgBottom: '#3E2D87',
          floorTop: '#160E36',
          floorBottom: '#0A061A',
          accent: '#54F2C8',
          secondary: '#FFD400',
          rim: '#8FFAE0',
          rays: 'rgba(84, 242, 200, 0.22)'
        },
        hud: {
          badgePrefix: 'ESCALA ',
          badgeStart: 1,
          badgeEnd: 10,
          label: isShrink ? 'TAMANHO ATUAL' : 'ALTURA ATUAL',
          marks: isShrink ? ['1,7m', '30cm', '5cm', '5mm', '0,1mm'] : ['1,7m', '15m', '150m', '800m', '1,7km'],
          formatValue: function (p) {
            if (isShrink) {
              var mm = expScale(1700, 0.1, p);
              if (mm >= 1000) return fmtNum(mm / 1000, 2) + ' m';
              if (mm >= 10) return fmtNum(mm / 10, 1) + ' cm';
              return fmtNum(mm, 1) + ' mm';
            }
            var m = expScale(1.7, 1700, p);
            if (m < 10) return fmtNum(m, 2) + ' m';
            if (m < 1000) return fmtNum(Math.round(m), 0) + ' m';
            return fmtNum(m / 1000, 1) + ' km';
          }
        },
        act2Phrases: ['A ESCALA MUDA TUDO', 'O MUNDO FICA IRRECONHECIVEL'],
        act3Phrases: ['FISICA NO EXTREMO!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(som|grito|gritar|alto|decibeis|decibel|barulho|audio|voz|musica|eco|estrondo|silencio|falar|sussurro|explosao|onda)\b/.test(norm)) {
      return {
        id: 'som',
        propsType: 'sound',
        palette: {
          bgTop: '#170724',
          bgMid: '#371052',
          bgBottom: '#61196E',
          floorTop: '#1E092E',
          floorBottom: '#0E0417',
          accent: '#FF4794',
          secondary: '#FFD400',
          rim: '#FF8CC0',
          rays: 'rgba(255, 71, 148, 0.22)'
        },
        hud: {
          badgePrefix: 'ONDA ',
          badgeStart: 1,
          badgeEnd: 10,
          label: 'PRESSAO SONORA',
          marks: ['60dB', '95dB', '130dB', '160dB', '194dB'],
          formatValue: function (p) {
            var db = lerp(60, 194, Math.pow(clamp(p, 0, 1), 0.92));
            return fmtNum(Math.round(db), 0) + ' dB';
          }
        },
        act2Phrases: ['O AR VIBRA SEM PARAR', 'VIDROS COMECAM A TREMER'],
        act3Phrases: ['ONDA DE CHOQUE TOTAL!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(tempo|relogio|parar|congelar|segundo|minuto|hora|futuro|passado|eterno|idade|envelhecer|cronometro|ano|seculo)\b/.test(norm)) {
      return {
        id: 'tempo',
        propsType: 'time',
        palette: {
          bgTop: '#081020',
          bgMid: '#132445',
          bgBottom: '#1F3B66',
          floorTop: '#0B162B',
          floorBottom: '#050A14',
          accent: '#F5B83D',
          secondary: '#5CD6FF',
          rim: '#FFE18C',
          rays: 'rgba(245, 184, 61, 0.20)'
        },
        hud: {
          badgePrefix: 'HORA ',
          badgeStart: 1,
          badgeEnd: 24,
          label: 'FLUXO TEMPORAL',
          marks: ['1x', '10x', '100x', '1K x', '10K x'],
          formatValue: function (p) {
            var v = expScale(1, 10000, p);
            if (v < 10) return fmtNum(v, 1) + 'x';
            return fmtNum(Math.round(v), 0) + 'x';
          }
        },
        act2Phrases: ['OS PONTEIROS DISPARAM', 'CADA SEGUNDO VALE HORAS'],
        act3Phrases: ['COLAPSO DO TEMPO!', 'LIMITE ATINGIDO!']
      };
    }

    if (/\b(corpo|coracao|espirro|espirrar|cerebro|dormir|sono|piscar|respirar|pulmao|sangue|pele|osso|olho|comer|agua|fome|febre|suor|adrenalina)\b/.test(norm)) {
      return {
        id: 'corpo',
        propsType: 'body',
        palette: {
          bgTop: '#160A18',
          bgMid: '#381229',
          bgBottom: '#5C1B37',
          floorTop: '#1E0D21',
          floorBottom: '#0E0610',
          accent: '#29E3B5',
          secondary: '#FFD400',
          rim: '#7AF7D8',
          rays: 'rgba(41, 227, 181, 0.20)'
        },
        hud: {
          badgePrefix: 'PULSO ',
          badgeStart: 1,
          badgeEnd: 10,
          label: 'RITMO CARDIACO',
          marks: ['72', '110', '150', '195', '240'],
          formatValue: function (p) {
            var bpm = lerp(72, 240, Math.pow(clamp(p, 0, 1), 1.15));
            return fmtNum(Math.round(bpm), 0) + ' BPM';
          }
        },
        act2Phrases: ['SEU CORPO ENTRA EM ALERTA', 'ADRENALINA NO TALO'],
        act3Phrases: ['SOBRECARGA BIOLOGICA!', 'LIMITE ATINGIDO!']
      };
    }

    return {
      id: 'generico',
      propsType: 'energy',
      palette: {
        bgTop: '#0B1229',
        bgMid: '#192957',
        bgBottom: '#294082',
        floorTop: '#0F1836',
        floorBottom: '#070B1A',
        accent: '#FFD400',
        secondary: '#45D9FF',
        rim: '#82D9FF',
        rays: 'rgba(255, 212, 0, 0.20)'
      },
      hud: {
        badgePrefix: 'NIVEL ',
        badgeStart: 1,
        badgeEnd: 10,
        label: 'ESCALA VIRAL',
        marks: ['1x', '10x', '50x', '250x', '1.000x'],
        formatValue: function (p) {
          var v = expScale(1, 1000, p);
          if (v < 10) return fmtNum(v, 1) + 'x';
          return fmtNum(Math.round(v), 0) + 'x';
        }
      },
      act2Phrases: ['A ESCALA FOGE DO CONTROLE', 'TUDO ACELERA RAPIDO'],
      act3Phrases: ['IMPACTO FORA DA CURVA!', 'LIMITE ATINGIDO!']
    };
  }

  // ------------------------------------------------ legendas cineticas
  function splitHookChunks(text) {
    var clean = sanitizeText(text);
    if (!clean) clean = DEFAULT_TEMA;
    var words = clean.split(' ').slice(0, 14);
    if (words.length <= 5 || clean.length <= 28) {
      return [words];
    }
    var mid = Math.ceil(words.length * 0.56);
    if (mid < 3) mid = 3;
    if (mid >= words.length) return [words];
    return [words.slice(0, mid), words.slice(mid)];
  }

  function timeChunks(wordGroups, tStart, tEnd) {
    var totalWords = 0;
    for (var i = 0; i < wordGroups.length; i++) totalWords += wordGroups[i].length;
    if (totalWords === 0) return [];

    var span = Math.max(0.2, tEnd - tStart);
    var wordDur = span / totalWords;
    var cursor = tStart;
    var out = [];

    for (var g = 0; g < wordGroups.length; g++) {
      var group = wordGroups[g];
      var timedWords = [];
      var cStart = cursor;
      for (var j = 0; j < group.length; j++) {
        timedWords.push({
          texto: group[j],
          t0: cursor,
          t1: cursor + wordDur
        });
        cursor += wordDur;
      }
      out.push({
        words: timedWords,
        t0: cStart,
        t1: cursor
      });
    }
    return out;
  }

  function buildTimelineCaptions(tema, theme) {
    var hookGroups = splitHookChunks(tema);
    var act1 = timeChunks(hookGroups, 0.0, 2.55);

    var act2Groups = [];
    for (var i = 0; i < theme.act2Phrases.length; i++) {
      act2Groups.push(theme.act2Phrases[i].split(' '));
    }
    var act2 = timeChunks(act2Groups, 2.65, 5.50);

    var act3Groups = [];
    for (var k = 0; k < theme.act3Phrases.length; k++) {
      act3Groups.push(theme.act3Phrases[k].split(' '));
    }
    var act3 = timeChunks(act3Groups, 5.62, 8.10);

    return act1.concat(act2).concat(act3);
  }

  // ------------------------------------------------ boneco articulado (rig)
  var CHAR_PAL = {
    skin: '#F4B98C',
    blush: '#F07F7F',
    hoodie: '#E8322A',
    hoodieDark: '#B01E19',
    hoodieLight: '#FF6A55',
    pants: '#2A3658',
    pantsRim: '#5A6A99',
    shoe: '#F5F2EA',
    shoeAccent: '#E8322A',
    hair: '#3A2416',
    eye: '#FFFFFF',
    mouth: '#4A0F12',
    tongue: '#E5646A',
    teeth: '#FFFFFF',
    cord: '#F5F2EA',
    sweat: '#8FD3FF'
  };

  var RIG = {
    torso: 104,
    neck: 8,
    headR: 70,
    upperArm: 52,
    foreArm: 48,
    thigh: 58,
    shin: 56,
    hipW: 22,
    shoulderW: 44,
    armW: 25,
    legW: 30,
    ol: 7
  };

  var BASE_POSE = {
    lean: 0, head: 0, headDY: 0, crouch: 0,
    ua_r: 14, la_r: 6, ua_l: 14, la_l: 6,
    th_r: 6, sh_r: 2, th_l: 6, sh_l: 2,
    hand_r: 0, hand_l: 0
  };

  function makePose(o) {
    return Object.assign({}, BASE_POSE, o);
  }

  var POSES = {
    idle: makePose({}),
    point_hook: makePose({ ua_r: 102, la_r: 114, hand_r: 2, ua_l: 22, la_l: 8, lean: -4, head: 5 }),
    shrug_question: makePose({ ua_r: 66, la_r: 138, ua_l: 66, la_l: 138, head: -6, lean: 2 }),
    flex: makePose({ ua_r: 96, la_r: 168, ua_l: 96, la_l: 168, hand_r: 1, hand_l: 1, lean: -2 }),
    jump_up: makePose({ ua_r: 128, la_r: 152, ua_l: 128, la_l: 152, th_r: 8, sh_r: 14, th_l: 16, sh_l: -6, head: -4 }),
    dodge_lean: makePose({ lean: -18, ua_r: 124, la_r: 144, ua_l: 68, la_l: 28, th_r: 28, sh_r: -10, th_l: 12, sh_l: 34, head: -10 }),
    shock_closeup: makePose({ ua_r: 116, la_r: 146, ua_l: 116, la_l: 146, head: 0, headDY: 4 }),
    space_float_panic: makePose({ ua_r: 124, la_r: 148, ua_l: 134, la_l: 100, th_r: 28, sh_r: -18, th_l: 20, sh_l: 32, head: 8 }),
    freefall_scream: makePose({ ua_r: 130, la_r: 154, ua_l: 130, la_l: 154, th_r: 26, sh_r: 52, th_l: 22, sh_l: 58, head: -3, headDY: -2 })
  };

  var BASE_EXPR = {
    browL: 0, browR: 0, browY: 0, lid: 0, eyeOpen: 1, pupil: 1, px: 0, py: 0,
    mouthW: 34, mouthOpen: 0, mouthCurve: 0.3, mouthSkew: 0, teeth: 0, tongue: 0,
    blush: 0, sweat: 0, sparkle: 0, shiver: 0
  };

  function makeExpr(o) {
    return Object.assign({}, BASE_EXPR, o);
  }

  var EXPR = {
    neutral: makeExpr({}),
    curious: makeExpr({ browL: -4, browR: 20, browY: -8, eyeOpen: 1.1, pupil: 0.92, px: 4, py: 2, mouthW: 22, mouthOpen: 0.25, mouthCurve: 0.1 }),
    amazed: makeExpr({ browL: 12, browR: 12, browY: -16, eyeOpen: 1.24, pupil: 1.12, sparkle: 1, mouthW: 40, mouthOpen: 0.72, mouthCurve: 0.85, teeth: 1, tongue: 0.4, blush: 0.6 }),
    determined: makeExpr({ browL: -16, browR: -16, browY: 4, lid: 0.16, pupil: 0.95, mouthW: 40, mouthCurve: 0.55, mouthSkew: 0.25, teeth: 1, mouthOpen: 0.22 }),
    shock: makeExpr({ browL: 20, browR: 20, browY: -18, eyeOpen: 1.34, pupil: 0.46, mouthW: 32, mouthOpen: 0.82, mouthCurve: -0.22, tongue: 0.6, sweat: 0.35 }),
    panic: makeExpr({ browL: 28, browR: 28, browY: -14, eyeOpen: 1.34, pupil: 0.44, px: -2, mouthW: 42, mouthOpen: 0.65, mouthCurve: -0.78, teeth: 1, sweat: 0.95, shiver: 0.6 }),
    scream: makeExpr({ browL: 28, browR: 28, browY: -22, eyeOpen: 1.44, pupil: 0.36, mouthW: 48, mouthOpen: 1.25, mouthCurve: -0.35, teeth: 1, tongue: 1, sweat: 1.0, shiver: 0.9 })
  };

  function blinkAmount(t, seed) {
    var sd = seed || 3;
    var acc = 0.75 + hash(sd) * 1.1;
    var i = 0;
    while (acc < t + 0.2 && i < 120) {
      var d = Math.abs(t - acc);
      if (d < 0.07) return 1 - d / 0.07;
      acc += 2.3 + hash(sd + i * 7.3) * 1.6;
      i++;
    }
    return 0;
  }

  function trackRig(keys, t) {
    var poseA = POSES.point_hook;
    var poseB = POSES.point_hook;
    var pk = 1;
    var pDur = 0.22;
    var pEase = 'inout';
    var exA = EXPR.amazed;
    var exB = EXPR.amazed;
    var ek = 1;
    var blinkBoost = 0;
    var curPose = 'point_hook';
    var curExpr = 'amazed';

    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (k.t > t) break;
      if (k.pose && k.pose !== curPose) {
        poseA = mixObj(poseA, poseB, pEase === 'back' ? easeOutBack(pk) : easeInOutCubic(pk));
        poseB = POSES[k.pose];
        curPose = k.pose;
        pDur = k.dur || 0.22;
        pEase = k.ease || 'inout';
        pk = clamp((t - k.t) / pDur, 0, 1);
      }
      if (k.expr && k.expr !== curExpr) {
        exA = mixObj(exA, exB, easeInOutCubic(ek));
        exB = EXPR[k.expr];
        curExpr = k.expr;
        ek = clamp((t - k.t) / (k.exprDur || 0.12), 0, 1);
        if (k.t > 0.1) {
          var d = Math.abs(t - (k.t + 0.03));
          if (d < 0.07) blinkBoost = Math.max(blinkBoost, 1 - d / 0.07);
        }
      }
    }

    for (var p = keys.length - 1; p >= 0; p--) {
      if (keys[p].t <= t && keys[p].pose === curPose) {
        pk = clamp((t - keys[p].t) / (keys[p].dur || 0.22), 0, 1);
        pEase = keys[p].ease || 'inout';
        break;
      }
    }
    for (var e = keys.length - 1; e >= 0; e--) {
      if (keys[e].t <= t && keys[e].expr === curExpr) {
        ek = clamp((t - keys[e].t) / (keys[e].exprDur || 0.12), 0, 1);
        break;
      }
    }

    var kp = pEase === 'back' ? easeOutBack(pk) : easeInOutCubic(pk);
    return {
      pose: mixObj(poseA, poseB, kp),
      expr: mixObj(exA, exB, easeInOutCubic(ek)),
      blinkBoost: blinkBoost
    };
  }

  function limbVec(angDeg, side) {
    var a = angDeg * RAD;
    return [side * Math.sin(a), Math.cos(a)];
  }

  function strokeLimb(ctx, pts, w, fill, rim, rimDir) {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = w + RIG.ol * 2;
    ctx.stroke();

    if (rim) {
      ctx.strokeStyle = rim;
      ctx.lineWidth = w;
      ctx.stroke();
      ctx.save();
      ctx.translate(-rimDir[0] * 4, -rimDir[1] * 4);
      ctx.strokeStyle = fill;
      ctx.lineWidth = w - 8;
      ctx.stroke();
      ctx.restore();
    } else {
      ctx.strokeStyle = fill;
      ctx.lineWidth = w;
      ctx.stroke();
    }
  }

  function fillShapeWithRim(ctx, pathFn, fill, rim, rimDir, offset) {
    pathFn();
    ctx.fillStyle = COLORS.ink;
    ctx.lineWidth = RIG.ol * 2;
    ctx.strokeStyle = COLORS.ink;
    ctx.stroke();
    if (rim) {
      pathFn();
      ctx.fillStyle = rim;
      ctx.fill();
      ctx.save();
      pathFn();
      ctx.clip();
      ctx.translate(-rimDir[0] * (offset || 9), -rimDir[1] * (offset || 9));
      pathFn();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.restore();
    } else {
      pathFn();
      ctx.fillStyle = fill;
      ctx.fill();
    }
  }

  function drawHand(ctx, x, y, dir, kind) {
    var r = 15;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(dir[1], dir[0]) - Math.PI / 2);
    ctx.lineCap = 'round';
    if (kind > 1.5) {
      ctx.beginPath();
      ctx.moveTo(0, 4);
      ctx.lineTo(0, r + 22);
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 11 + RIG.ol * 2;
      ctx.stroke();
      ctx.strokeStyle = CHAR_PAL.skin;
      ctx.lineWidth = 11;
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(0, 4, r, 0, Math.PI * 2);
    ctx.fillStyle = CHAR_PAL.skin;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = RIG.ol;
    ctx.fill();
    ctx.stroke();
    if (kind < 0.5) {
      ctx.beginPath();
      ctx.arc(r * 0.85, -2, r * 0.42, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(-r * 0.5, 4);
      ctx.lineTo(r * 0.5, 4);
      ctx.lineWidth = 3;
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawShoe(ctx, x, y, dir, side) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(dir[1], dir[0]) - Math.PI / 2);
    ctx.beginPath();
    ctx.ellipse(side * 10, 12, 27, 15, 0, 0, Math.PI * 2);
    ctx.fillStyle = CHAR_PAL.shoe;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = RIG.ol;
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(side * 10 - 22, 20);
    ctx.lineTo(side * 10 + 22, 20);
    ctx.strokeStyle = CHAR_PAL.shoeAccent;
    ctx.lineWidth = 5;
    ctx.stroke();
    ctx.restore();
  }

  function drawFace(ctx, ex, t, blink, opts) {
    var R = RIG.headR;
    var shiverAmp = opts.reducedMotion ? 0.2 : 1.4;
    var shiver = ex.shiver * Math.sin(t * 78) * shiverAmp;
    ctx.save();
    ctx.translate(shiver, 0);

    var eyeY = -6 + ex.browY * 0.1;
    var eyeDX = 26;

    if (ex.blush > 0.01) {
      ctx.globalAlpha = 0.45 * ex.blush;
      ctx.fillStyle = CHAR_PAL.blush;
      ctx.beginPath();
      ctx.ellipse(-42, 24, 14, 8, 0, 0, Math.PI * 2);
      ctx.ellipse(42, 24, 14, 8, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    var sides = [-1, 1];
    for (var s = 0; s < 2; s++) {
      var side = sides[s];
      var cx = side * eyeDX + (opts.look || 0) * 4;
      var cy = eyeY;
      var rx = 17;
      var ry = 20 * ex.eyeOpen;
      var lid = clamp(Math.max(ex.lid, blink), 0, 1);

      ctx.save();
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = CHAR_PAL.eye;
      ctx.fill();
      ctx.clip();

      var pr = 9.5 * ex.pupil;
      var ppx = cx + ex.px + (opts.look || 0) * 6;
      var ppy = cy + ex.py;
      ctx.fillStyle = COLORS.ink;
      ctx.beginPath();
      ctx.arc(ppx, ppy, pr, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.arc(ppx - pr * 0.35, ppy - pr * 0.4, Math.max(2, pr * 0.32), 0, Math.PI * 2);
      ctx.fill();
      if (ex.sparkle > 0.3) {
        ctx.beginPath();
        ctx.arc(ppx + pr * 0.4, ppy + pr * 0.35, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }

      if (lid > 0.01) {
        var ly = cy - ry + 2 * ry * lid;
        ctx.fillStyle = CHAR_PAL.skin;
        ctx.fillRect(cx - rx - 2, cy - ry - 4, rx * 2 + 4, ly - (cy - ry) + 4);
        ctx.strokeStyle = COLORS.ink;
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.moveTo(cx - rx, ly);
        ctx.lineTo(cx + rx, ly);
        ctx.stroke();
      }
      ctx.restore();

      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 5;
      ctx.stroke();

      // sobrancelha
      var bAng = (side < 0 ? ex.browL : ex.browR) * RAD;
      var by = cy - ry - 12 + ex.browY * 0.6;
      ctx.save();
      ctx.translate(cx, by);
      ctx.rotate(-side * bAng);
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 9;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(-14, 0);
      ctx.lineTo(14, 0);
      ctx.stroke();
      ctx.restore();
    }

    // nariz
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 4.5;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(-2, 14);
    ctx.quadraticCurveTo(7, 20, 0, 24);
    ctx.stroke();

    // boca
    var mw = ex.mouthW;
    var open = Math.max(0, ex.mouthOpen);
    var my = 40;
    var c = ex.mouthCurve * 10;
    var sk = ex.mouthSkew * 8;
    if (open > 0.12) {
      var h = 30 * open;
      var pathM = function () {
        ctx.beginPath();
        ctx.moveTo(-mw / 2, my - c + sk);
        ctx.quadraticCurveTo(0, my - c * 0.2 - h * 0.2, mw / 2, my - c - sk);
        ctx.quadraticCurveTo(mw * 0.42, my + h, 0, my + h * 1.05);
        ctx.quadraticCurveTo(-mw * 0.42, my + h, -mw / 2, my - c + sk);
        ctx.closePath();
      };
      pathM();
      ctx.fillStyle = CHAR_PAL.mouth;
      ctx.fill();
      ctx.save();
      pathM();
      ctx.clip();
      if (ex.tongue > 0.05) {
        ctx.fillStyle = CHAR_PAL.tongue;
        ctx.beginPath();
        ctx.ellipse(0, my + h * 1.0, mw * 0.32, h * 0.42 * ex.tongue + 2, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      if (ex.teeth > 0.05) {
        ctx.fillStyle = CHAR_PAL.teeth;
        ctx.fillRect(-mw / 2, my - c - 12, mw, 12 + Math.min(9, h * 0.22));
      }
      ctx.restore();
      pathM();
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 5;
      ctx.lineJoin = 'round';
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(-mw / 2, my - c + sk);
      ctx.quadraticCurveTo(0, my + c * 1.4, mw / 2, my - c - sk);
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 6;
      ctx.stroke();
    }

    // gotas de suor expressivas
    if (ex.sweat > 0.05) {
      var k = (t * 1.4) % 1;
      ctx.globalAlpha = ex.sweat * (1 - k * 0.55);
      var drops = [[R * 0.78, -R * 0.34], [-R * 0.82, -R * 0.14]];
      for (var d = 0; d < drops.length; d++) {
        var sx = drops[d][0];
        var sy = drops[d][1] + k * 28;
        ctx.beginPath();
        ctx.moveTo(sx, sy - 13);
        ctx.quadraticCurveTo(sx + 9, sy + 2, sx, sy + 7);
        ctx.quadraticCurveTo(sx - 9, sy + 2, sx, sy - 13);
        ctx.fillStyle = CHAR_PAL.sweat;
        ctx.fill();
        ctx.strokeStyle = COLORS.ink;
        ctx.lineWidth = 3.5;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    ctx.restore();
  }

  function drawHead(ctx, ex, t, blink, opts, rim, rimDir) {
    var R = RIG.headR;
    var wind = opts.wind || [0, 0];

    // orelhas
    var sides = [-1, 1];
    for (var s = 0; s < 2; s++) {
      ctx.beginPath();
      ctx.ellipse(sides[s] * (R - 2), 6, 13, 17, 0, 0, Math.PI * 2);
      ctx.fillStyle = CHAR_PAL.skin;
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = RIG.ol;
      ctx.fill();
      ctx.stroke();
    }

    var headPath = function () {
      ctx.beginPath();
      ctx.moveTo(0, -R);
      ctx.bezierCurveTo(R * 0.78, -R, R, -R * 0.55, R, -R * 0.05);
      ctx.bezierCurveTo(R, R * 0.6, R * 0.6, R * 0.95, 0, R * 0.95);
      ctx.bezierCurveTo(-R * 0.6, R * 0.95, -R, R * 0.6, -R, -R * 0.05);
      ctx.bezierCurveTo(-R, -R * 0.55, -R * 0.78, -R, 0, -R);
      ctx.closePath();
    };
    fillShapeWithRim(ctx, headPath, CHAR_PAL.skin, rim, rimDir, 10);

    // cabelo espetado reativo ao vento
    ctx.beginPath();
    var spikes = 7;
    var wMag = Math.hypot(wind[0], wind[1]);
    var wxPush = clamp(wind[0], -50, 50) * 0.32;
    var wDown = clamp(wind[1], 0, 90);
    var wUp = clamp(wind[1], -90, 0);
    ctx.moveTo(-R * 0.92, -R * 0.35);
    for (var i = 0; i <= spikes; i++) {
      var kk = i / spikes;
      var ang = Math.PI + kk * Math.PI;
      var bx = Math.cos(ang) * R * 0.95;
      var by = Math.sin(ang) * R * 0.95;
      var tipLen = 26 + hash(i) * 12;
      var flutter = wMag > 5 ? Math.sin(t * 20 + i * 2.1) * Math.min(6, wMag * 0.08) : 0;
      var sweepX = wxPush + Math.cos(ang) * wDown * 0.28 + flutter;
      var sweepY = wDown * 0.10 + wUp * 0.28;
      var tx = Math.cos(ang) * (R + tipLen) + sweepX;
      var ty = Math.sin(ang) * (R + tipLen) + sweepY - 6;
      var dist = Math.hypot(tx, ty) || 1;
      var minR = R + tipLen * 0.84;
      if (dist < minR) {
        tx = tx / dist * minR;
        ty = ty / dist * minR;
      }
      if (i < spikes) {
        var nx = Math.cos(ang + Math.PI / spikes) * R * 0.95;
        var ny = Math.sin(ang + Math.PI / spikes) * R * 0.95;
        ctx.lineTo(bx, by);
        ctx.lineTo(tx, ty);
        ctx.lineTo(nx * 0.98, ny * 0.98);
      }
    }
    ctx.lineTo(R * 0.92, -R * 0.35);
    ctx.quadraticCurveTo(R * 0.5, -R * 0.58, 0, -R * 0.52);
    ctx.quadraticCurveTo(-R * 0.5, -R * 0.58, -R * 0.92, -R * 0.35);
    ctx.closePath();
    ctx.fillStyle = CHAR_PAL.hair;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = RIG.ol;
    ctx.lineJoin = 'round';
    ctx.fill();
    ctx.stroke();

    drawFace(ctx, ex, t, blink, opts);
  }

  function drawCharacter(ctx, o) {
    var pose = typeof o.pose === 'string' ? POSES[o.pose] : (o.pose || POSES.idle);
    var ex = typeof o.expr === 'string' ? EXPR[o.expr] : (o.expr || EXPR.neutral);
    var t = o.t || 0;
    var s = o.scale || 0.72;
    var sq = o.squash || 1;
    var wind = o.wind || [0, 0];
    var rim = o.rim ? o.rim.color : CHAR_PAL.hoodieLight;
    var rd = o.rim ? o.rim.dir : [1, -0.4];
    var rl = Math.hypot(rd[0], rd[1]) || 1;
    var rimDir = [rd[0] / rl, rd[1] / rl];
    var blink = Math.max(o.blink || 0, blinkAmount(t, o.seed || 3));
    var breath = Math.sin(t * Math.PI * 2 / 2.4);

    ctx.save();
    ctx.translate(o.x, o.y);
    ctx.rotate(o.rot || 0);
    ctx.scale(s / Math.sqrt(sq), s * sq);
    ctx.translate(0, pose.crouch);

    // pernas
    var sides = [-1, 1];
    for (var i = 0; i < 2; i++) {
      var side = sides[i];
      var hip = [side * RIG.hipW, 6];
      var th = side > 0 ? pose.th_r : pose.th_l;
      var sh = side > 0 ? pose.sh_r : pose.sh_l;
      var v1 = limbVec(th, side);
      var v2 = limbVec(sh, side);
      var knee = [hip[0] + v1[0] * RIG.thigh, hip[1] + v1[1] * RIG.thigh];
      var foot = [knee[0] + v2[0] * RIG.shin, knee[1] + v2[1] * RIG.shin];
      strokeLimb(ctx, [hip, knee, foot], RIG.legW, CHAR_PAL.pants, CHAR_PAL.pantsRim, rimDir);
      drawShoe(ctx, foot[0], foot[1], v2, side);
    }

    // tronco + moletom vermelho com capuz
    ctx.save();
    ctx.rotate(pose.lean * RAD);
    var tl = RIG.torso * (1 + breath * 0.014);
    var sw = RIG.shoulderW * (1 + breath * 0.012);

    ctx.beginPath();
    ctx.ellipse(0, -tl - 8, 52, 30, 0, 0, Math.PI * 2);
    ctx.fillStyle = CHAR_PAL.hoodieDark;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = RIG.ol;
    ctx.fill();
    ctx.stroke();

    var torsoPath = function () {
      ctx.beginPath();
      ctx.moveTo(-RIG.hipW - 12, 14);
      ctx.quadraticCurveTo(-sw - 10, -tl * 0.45, -sw, -tl + 12);
      ctx.quadraticCurveTo(-sw + 6, -tl - 6, -18, -tl - 4);
      ctx.lineTo(18, -tl - 4);
      ctx.quadraticCurveTo(sw - 6, -tl - 6, sw, -tl + 12);
      ctx.quadraticCurveTo(sw + 10, -tl * 0.45, RIG.hipW + 12, 14);
      ctx.quadraticCurveTo(0, 22, -RIG.hipW - 12, 14);
      ctx.closePath();
    };
    ctx.lineJoin = 'round';
    fillShapeWithRim(ctx, torsoPath, CHAR_PAL.hoodie, rim || CHAR_PAL.hoodieLight, rimDir, 10);

    // bolso canguru e barra
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(-30, -6);
    ctx.lineTo(-22, -36);
    ctx.lineTo(22, -36);
    ctx.lineTo(30, -6);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(-RIG.hipW - 10, 6);
    ctx.quadraticCurveTo(0, 14, RIG.hipW + 10, 6);
    ctx.stroke();

    // cordoes brancos do capuz
    for (var c = 0; c < 2; c++) {
      var s2 = sides[c];
      var x0 = s2 * 12;
      var y0 = -tl + 2;
      var sway = Math.sin(t * 7 + s2) * (Math.abs(wind[0]) + Math.abs(wind[1]) + 10) * 0.08;
      var x1 = x0 + wind[0] * 0.55 + sway;
      var y1 = y0 + 38 + wind[1] * 0.55;
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.quadraticCurveTo(x0 + wind[0] * 0.2, y0 + 20, x1, y1);
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 9;
      ctx.stroke();
      ctx.strokeStyle = CHAR_PAL.cord;
      ctx.lineWidth = 4.5;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x1, y1, 5, 0, Math.PI * 2);
      ctx.fillStyle = CHAR_PAL.cord;
      ctx.fill();
      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 3;
      ctx.stroke();
    }

    // cabeca
    ctx.save();
    ctx.translate(0, -tl - RIG.neck - RIG.headR * 0.82 + pose.headDY + breath * 1.5);
    ctx.rotate(pose.head * RAD);
    drawHead(ctx, ex, t, blink, o, rim, rimDir);
    ctx.restore();

    // bracos por cima do tronco
    for (var a = 0; a < 2; a++) {
      var aside = sides[a];
      var shPos = [aside * (sw - 6), -tl + 16];
      var ua = aside > 0 ? pose.ua_r : pose.ua_l;
      var la = aside > 0 ? pose.la_r : pose.la_l;
      var flutter = Math.sin(t * 13 + aside) * (Math.abs(wind[0]) + Math.abs(wind[1])) * 0.03;
      var av1 = limbVec(ua + flutter, aside);
      var av2 = limbVec(la + flutter * 1.6, aside);
      var el = [shPos[0] + av1[0] * RIG.upperArm, shPos[1] + av1[1] * RIG.upperArm];
      var hd = [el[0] + av2[0] * RIG.foreArm, el[1] + av2[1] * RIG.foreArm];
      strokeLimb(ctx, [shPos, el, hd], RIG.armW, CHAR_PAL.hoodie, rim || CHAR_PAL.hoodieLight, rimDir);
      drawHand(ctx, hd[0], hd[1], av2, aside > 0 ? pose.hand_r : pose.hand_l);
    }

    ctx.restore();
    ctx.restore();
  }

  // ------------------------------------------------ fundo e marca dagua
  function drawBackground(ctx, theme, presetId, t, climaxK, reducedMotion) {
    var pal = theme.palette;
    var g = ctx.createLinearGradient(0, 0, 0, H);

    if (presetId === 'suspense_noir') {
      g.addColorStop(0, '#05070D');
      g.addColorStop(0.55, '#0F1524');
      g.addColorStop(1, '#1A2030');
    } else if (presetId === 'caos_sonoro') {
      g.addColorStop(0, '#0D061A');
      g.addColorStop(0.5, pal.bgMid);
      g.addColorStop(1, '#260B29');
    } else {
      g.addColorStop(0, pal.bgTop);
      g.addColorStop(0.58, pal.bgMid);
      g.addColorStop(1, pal.bgBottom);
    }
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // brilho radial central atras do boneco
    var glowR = lerp(240, 360, climaxK);
    var rg = ctx.createRadialGradient(W * 0.48, H * 0.46, 20, W * 0.48, H * 0.46, glowR);
    if (presetId === 'suspense_noir') {
      rg.addColorStop(0, 'rgba(180, 205, 255, 0.16)');
      rg.addColorStop(1, 'rgba(0, 0, 0, 0)');
    } else {
      rg.addColorStop(0, climaxK > 0.25 ? 'rgba(255, 64, 80, 0.34)' : 'rgba(255, 255, 255, 0.14)');
      rg.addColorStop(1, 'rgba(0, 0, 0, 0)');
    }
    ctx.fillStyle = rg;
    ctx.fillRect(0, 0, W, H);

    // plano de chao com grade sutil em perspectiva
    var horizonY = 620;
    var fg = ctx.createLinearGradient(0, horizonY, 0, H);
    fg.addColorStop(0, presetId === 'suspense_noir' ? '#0C101C' : pal.floorTop);
    fg.addColorStop(1, presetId === 'suspense_noir' ? '#04060A' : pal.floorBottom);
    ctx.fillStyle = fg;
    ctx.fillRect(0, horizonY, W, H - horizonY);

    ctx.save();
    ctx.strokeStyle = presetId === 'suspense_noir' ? 'rgba(169, 188, 224, 0.12)' : 'rgba(255, 255, 255, 0.10)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, horizonY);
    ctx.lineTo(W, horizonY);
    ctx.stroke();

    for (var i = -4; i <= 4; i++) {
      ctx.beginPath();
      ctx.moveTo(W * 0.5 + i * 52, horizonY);
      ctx.lineTo(W * 0.5 + i * 165, H);
      ctx.stroke();
    }
    ctx.restore();

    // linhas de acao radiais (crescem na escalada e explodem no climax)
    var rayAlpha = presetId === 'suspense_noir' ? climaxK * 0.35 : (0.14 + climaxK * 0.72);
    if (rayAlpha > 0.02) {
      ctx.save();
      ctx.translate(W * 0.46, H * 0.46);
      var spin = reducedMotion ? 0.12 : 0.65;
      ctx.rotate(t * spin * (0.3 + climaxK));
      var rays = presetId === 'caos_sonoro' ? 28 : 20;
      ctx.fillStyle = climaxK > 0.4 ? 'rgba(255, 58, 72, 0.17)' : pal.rays;
      ctx.globalAlpha = rayAlpha;
      for (var r = 0; r < rays; r++) {
        var a0 = (r / rays) * Math.PI * 2;
        var spread = (Math.PI / rays) * (0.32 + hash(r + 11) * 0.25);
        ctx.beginPath();
        ctx.moveTo(Math.cos(a0) * 110, Math.sin(a0) * 110);
        ctx.lineTo(Math.cos(a0 - spread) * 680, Math.sin(a0 - spread) * 680);
        ctx.lineTo(Math.cos(a0 + spread) * 680, Math.sin(a0 + spread) * 680);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    }

    // marca dagua diagonal translucida obrigatoria no fundo
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.rotate(-26 * RAD);
    ctx.font = '800 34px ' + FONT_UI;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.065)';
    for (var row = -3; row <= 3; row++) {
      var offsetX = (row % 2) * 140;
      for (var col = -1; col <= 1; col++) {
        ctx.fillText('STUDIOSTICK IA', col * 340 + offsetX, row * 150);
      }
    }
    ctx.restore();
  }

  // ------------------------------------------------ props animados por tema
  function drawMoneyProps(ctx, t, intensity, layer) {
    var count = layer === 'back' ? 12 : 6;
    var speed = lerp(65, 210, intensity);
    ctx.save();
    for (var i = 0; i < count; i++) {
      var seed = (layer === 'back' ? 10 : 70) + i * 3.7;
      var x = hash(seed) * (W - 70) + 35;
      var y = ((hash(seed + 1) * (H + 140) + t * speed * (0.65 + hash(seed + 2) * 0.75)) % (H + 140)) - 70;
      var rot = t * (1.8 + hash(seed + 3) * 2.5) * (i % 2 ? 1 : -1) + seed;
      var isBill = i % 3 === 0;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(rot);
      ctx.globalAlpha = layer === 'back' ? lerp(0.42, 0.85, intensity) : lerp(0.55, 0.92, intensity);
      if (isBill) {
        roundRect(ctx, -24, -12, 48, 24, 4);
        ctx.fillStyle = '#2BB673';
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = COLORS.ink;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(0, 0, 6, 0, Math.PI * 2);
        ctx.fillStyle = '#9BF5C4';
        ctx.fill();
      } else {
        var r = layer === 'back' ? 13 : 16;
        var flip = Math.max(0.32, Math.abs(Math.cos(t * 4.5 + seed)));
        ctx.scale(flip, 1);
        ctx.beginPath();
        ctx.arc(0, 0, r, 0, Math.PI * 2);
        ctx.fillStyle = '#FFD400';
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = COLORS.ink;
        ctx.stroke();
        ctx.fillStyle = COLORS.ink;
        ctx.font = '900 13px ' + FONT_UI;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('$', 0, 1);
      }
      ctx.restore();
    }
    ctx.restore();
  }

  function drawSpeedProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // radar concentric arcs atras do boneco
      ctx.save();
      ctx.translate(W * 0.46, H * 0.48);
      ctx.strokeStyle = 'rgba(56, 217, 255, ' + lerp(0.16, 0.42, intensity) + ')';
      ctx.lineWidth = 2.5;
      for (var r = 1; r <= 4; r++) {
        ctx.beginPath();
        ctx.arc(0, 0, r * 62, 0, Math.PI * 2);
        ctx.stroke();
      }
      var sweep = t * lerp(2.2, 7.5, intensity);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(sweep) * 250, Math.sin(sweep) * 250);
      ctx.strokeStyle = '#38D9FF';
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
    }

    // linhas de velocidade rasgando o quadro
    var lines = layer === 'back' ? 14 : 8;
    var speed = lerp(240, 820, intensity);
    for (var i = 0; i < lines; i++) {
      var seed = (layer === 'back' ? 100 : 160) + i * 5.3;
      var y = hash(seed) * (H - 180) + 90;
      var len = 55 + hash(seed + 1) * 110 * (0.5 + intensity);
      var x = W + 80 - ((hash(seed + 2) * (W + 240) + t * speed * (0.7 + hash(seed + 3) * 0.8)) % (W + 240));
      ctx.strokeStyle = i % 3 === 0 ? '#FFD400' : '#7AEBFF';
      ctx.globalAlpha = layer === 'back' ? 0.48 : 0.72;
      ctx.lineWidth = layer === 'back' ? 3 : 4;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + len, y - len * 0.14);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawStrengthProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // rachaduras no chao expandindo conforme intensidade sobe
      ctx.strokeStyle = '#FF8524';
      ctx.lineWidth = 3.5;
      ctx.globalAlpha = lerp(0.25, 0.9, intensity);
      var cx = W * 0.46;
      var cy = 648;
      for (var c = 0; c < 6; c++) {
        var dir = -Math.PI * 0.12 - (c / 5) * Math.PI * 0.76;
        var reach = lerp(45, 220, intensity) * (0.7 + hash(c + 3) * 0.45);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(dir) * reach * 0.5, cy + Math.sin(dir) * reach * 0.16 + 18);
        ctx.lineTo(cx + Math.cos(dir) * reach, cy + Math.sin(dir) * reach * 0.25 + 48);
        ctx.stroke();
      }
    }

    // estilhacos de energia e pedras levitando
    var chunks = layer === 'back' ? 10 : 6;
    for (var i = 0; i < chunks; i++) {
      var seed = (layer === 'back' ? 210 : 270) + i * 4.1;
      var x = hash(seed) * (W - 80) + 40;
      var rise = ((hash(seed + 1) * 520 + t * lerp(40, 175, intensity)) % 520);
      var y = 760 - rise;
      var sz = (layer === 'back' ? 9 : 13) + hash(seed + 2) * 8;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(t * 2.4 + seed);
      ctx.globalAlpha = lerp(0.35, 0.88, intensity) * (1 - rise / 560);
      ctx.beginPath();
      ctx.moveTo(0, -sz);
      ctx.lineTo(sz * 0.85, -sz * 0.2);
      ctx.lineTo(sz * 0.55, sz * 0.9);
      ctx.lineTo(-sz * 0.75, sz * 0.5);
      ctx.closePath();
      ctx.fillStyle = i % 2 ? '#FF8524' : '#4E3B46';
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = COLORS.ink;
      ctx.stroke();
      ctx.restore();
    }
    ctx.restore();
  }

  function drawScaleProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // grade de medicao geometrica e aneis de escala
      ctx.strokeStyle = 'rgba(84, 242, 200, ' + lerp(0.18, 0.45, intensity) + ')';
      ctx.lineWidth = 2;
      var step = lerp(48, 28, intensity);
      var drift = (t * 24) % step;
      for (var y = 140; y < 670; y += step) {
        ctx.beginPath();
        ctx.moveTo(26, y + drift);
        ctx.lineTo(W - 26, y + drift);
        ctx.stroke();
      }
      ctx.save();
      ctx.translate(W * 0.46, H * 0.47);
      for (var k = 0; k < 3; k++) {
        var phase = (t * 0.55 + k / 3) % 1;
        var rad = lerp(50, 260, phase);
        ctx.globalAlpha = (1 - phase) * lerp(0.35, 0.8, intensity);
        ctx.strokeStyle = k % 2 ? '#54F2C8' : '#FFD400';
        ctx.lineWidth = 3;
        ctx.setLineDash([12, 8]);
        ctx.beginPath();
        ctx.arc(0, 0, rad, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.restore();
    } else {
      // setas de escala flutuantes
      for (var i = 0; i < 5; i++) {
        var s = 310 + i * 3.1;
        var ax = hash(s) * (W - 110) + 55;
        var ay = 240 + hash(s + 1) * 380 + Math.sin(t * 4 + i) * 14;
        ctx.save();
        ctx.translate(ax, ay);
        ctx.strokeStyle = '#54F2C8';
        ctx.lineWidth = 3;
        ctx.globalAlpha = lerp(0.35, 0.78, intensity);
        ctx.beginPath();
        ctx.moveTo(0, -14);
        ctx.lineTo(0, 14);
        ctx.moveTo(-7, -7);
        ctx.lineTo(0, -14);
        ctx.lineTo(7, -7);
        ctx.moveTo(-7, 7);
        ctx.lineTo(0, 14);
        ctx.lineTo(7, 7);
        ctx.stroke();
        ctx.restore();
      }
    }
    ctx.restore();
  }

  function drawSoundProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // barras de equalizador atras
      var bars = 16;
      var bw = 18;
      var gap = 10;
      var totalW = bars * bw + (bars - 1) * gap;
      var startX = (W - totalW) / 2;
      for (var b = 0; b < bars; b++) {
        var amp = (0.25 + 0.75 * Math.abs(Math.sin(t * (5 + b * 0.4) + b))) * lerp(45, 190, intensity);
        roundRect(ctx, startX + b * (bw + gap), 620 - amp, bw, amp, 5);
        ctx.fillStyle = b % 2 ? 'rgba(255, 71, 148, 0.34)' : 'rgba(255, 212, 0, 0.28)';
        ctx.fill();
      }
    }

    // ondas concentricas de choque
    var rings = layer === 'back' ? 4 : 3;
    ctx.translate(W * 0.46, H * 0.44);
    for (var i = 0; i < rings; i++) {
      var phase = (t * lerp(0.85, 2.2, intensity) + i / rings + (layer === 'front' ? 0.15 : 0)) % 1;
      var r = lerp(45, 310, phase);
      ctx.globalAlpha = (1 - phase) * lerp(0.32, 0.85, intensity);
      ctx.strokeStyle = i % 2 ? '#FF4794' : '#FFD400';
      ctx.lineWidth = lerp(3, 7, intensity) * (1 - phase * 0.5);
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawTimeProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // relogio gigante translucido girando atras
      ctx.save();
      ctx.translate(W * 0.46, H * 0.46);
      ctx.globalAlpha = lerp(0.24, 0.55, intensity);
      ctx.strokeStyle = '#F5B83D';
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.arc(0, 0, 178, 0, Math.PI * 2);
      ctx.stroke();
      for (var h = 0; h < 12; h++) {
        var ang = (h / 12) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(Math.cos(ang) * 154, Math.sin(ang) * 154);
        ctx.lineTo(Math.cos(ang) * 172, Math.sin(ang) * 172);
        ctx.stroke();
      }
      var fastAng = t * lerp(1.6, 14.0, intensity);
      var slowAng = fastAng * 0.12;
      ctx.lineCap = 'round';
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(slowAng - Math.PI / 2) * 95, Math.sin(slowAng - Math.PI / 2) * 95);
      ctx.stroke();
      ctx.strokeStyle = '#5CD6FF';
      ctx.lineWidth = 4.5;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(fastAng - Math.PI / 2) * 142, Math.sin(fastAng - Math.PI / 2) * 142);
      ctx.stroke();
      ctx.restore();
    } else {
      // raios temporais energeticos
      var bolts = 4;
      for (var b = 0; b < bolts; b++) {
        var seed = 410 + b * 9.1;
        var pulse = Math.sin(t * 10 + b * 2.1);
        if (pulse < 0.25 - intensity * 0.35) continue;
        var x0 = hash(seed) * (W - 120) + 60;
        var y0 = 210 + hash(seed + 1) * 280;
        ctx.strokeStyle = b % 2 ? '#5CD6FF' : '#FFD400';
        ctx.lineWidth = 3.5;
        ctx.globalAlpha = lerp(0.45, 0.9, intensity);
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x0 + 18, y0 + 26);
        ctx.lineTo(x0 - 8, y0 + 44);
        ctx.lineTo(x0 + 16, y0 + 74);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawBodyProps(ctx, t, intensity, layer) {
    ctx.save();
    if (layer === 'back') {
      // linha ECG de batimento cardiaco animada
      ctx.strokeStyle = intensity > 0.65 ? '#FF2E3B' : '#29E3B5';
      ctx.lineWidth = 4;
      ctx.globalAlpha = lerp(0.45, 0.9, intensity);
      ctx.beginPath();
      var baseY = 560;
      var freq = lerp(1.5, 4.2, intensity);
      for (var x = 0; x <= W; x += 6) {
        var phase = ((x / 150) + t * freq) % 1;
        var dy = 0;
        if (phase > 0.35 && phase < 0.42) dy = -22 * Math.sin(((phase - 0.35) / 0.07) * Math.PI);
        else if (phase >= 0.45 && phase < 0.50) dy = 18;
        else if (phase >= 0.50 && phase < 0.57) dy = -lerp(55, 115, intensity) * Math.sin(((phase - 0.50) / 0.07) * Math.PI);
        else if (phase >= 0.57 && phase < 0.63) dy = 34 * Math.sin(((phase - 0.57) / 0.06) * Math.PI);
        if (x === 0) ctx.moveTo(x, baseY + dy);
        else ctx.lineTo(x, baseY + dy);
      }
      ctx.stroke();
    } else {
      // particulas de adrenalina pulsantes
      for (var i = 0; i < 8; i++) {
        var s = 510 + i * 6.7;
        var px = hash(s) * (W - 80) + 40;
        var py = 720 - ((hash(s + 1) * 520 + t * lerp(55, 180, intensity)) % 520);
        var rad = 4 + hash(s + 2) * 6;
        ctx.globalAlpha = lerp(0.35, 0.85, intensity);
        ctx.fillStyle = i % 2 ? '#29E3B5' : '#FF5C7C';
        ctx.beginPath();
        ctx.arc(px, py, rad, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawEnergyProps(ctx, t, intensity, layer) {
    ctx.save();
    var count = layer === 'back' ? 14 : 7;
    for (var i = 0; i < count; i++) {
      var seed = (layer === 'back' ? 610 : 680) + i * 5.1;
      var x = hash(seed) * (W - 70) + 35 + Math.sin(t * 2.5 + i) * 14;
      var travel = ((hash(seed + 1) * (H + 80) + t * lerp(55, 220, intensity) * (0.6 + hash(seed + 2) * 0.7)) % (H + 80));
      var y = H + 20 - travel;
      var sz = (layer === 'back' ? 6 : 9) + hash(seed + 3) * 6;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(t * 2 + seed);
      ctx.globalAlpha = lerp(0.32, 0.85, intensity);
      ctx.fillStyle = i % 2 ? '#FFD400' : '#45D9FF';
      ctx.beginPath();
      ctx.moveTo(0, -sz);
      ctx.lineTo(sz * 0.72, 0);
      ctx.lineTo(0, sz);
      ctx.lineTo(-sz * 0.72, 0);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();
  }

  function drawThemeProps(ctx, theme, t, intensity, layer) {
    switch (theme.propsType) {
      case 'money': drawMoneyProps(ctx, t, intensity, layer); break;
      case 'speed': drawSpeedProps(ctx, t, intensity, layer); break;
      case 'strength': drawStrengthProps(ctx, t, intensity, layer); break;
      case 'scale': drawScaleProps(ctx, t, intensity, layer); break;
      case 'sound': drawSoundProps(ctx, t, intensity, layer); break;
      case 'time': drawTimeProps(ctx, t, intensity, layer); break;
      case 'body': drawBodyProps(ctx, t, intensity, layer); break;
      default: drawEnergyProps(ctx, t, intensity, layer); break;
    }
  }

  // ------------------------------------------------ atmosferas por preset
  function drawPresetAtmosphere(ctx, presetId, t, climaxK, reducedMotion) {
    if (presetId === 'suspense_noir') {
      // cone de luz dramatico vindo do topo
      ctx.save();
      var sway = reducedMotion ? 0 : Math.sin(t * 1.4) * 18;
      var cone = ctx.createLinearGradient(W * 0.48, 0, W * 0.48 + sway, H * 0.85);
      cone.addColorStop(0, 'rgba(215, 232, 255, 0.28)');
      cone.addColorStop(0.65, 'rgba(180, 210, 255, 0.08)');
      cone.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = cone;
      ctx.beginPath();
      ctx.moveTo(W * 0.34, 0);
      ctx.lineTo(W * 0.62, 0);
      ctx.lineTo(W * 0.92 + sway, H * 0.9);
      ctx.lineTo(W * 0.04 + sway, H * 0.9);
      ctx.closePath();
      ctx.fill();

      // vinheta noir escura nas bordas
      var vig = ctx.createRadialGradient(W * 0.48, H * 0.46, 120, W * 0.48, H * 0.46, 540);
      vig.addColorStop(0, 'rgba(0, 0, 0, 0)');
      vig.addColorStop(1, climaxK > 0.35 ? 'rgba(65, 5, 12, 0.72)' : 'rgba(2, 4, 10, 0.68)');
      ctx.fillStyle = vig;
      ctx.fillRect(0, 0, W, H);
      ctx.restore();
      return;
    }

    if (presetId === 'caos_sonoro') {
      // aneis sonoros de choque com deslocamento cromatico ciano/magenta
      ctx.save();
      ctx.translate(W * 0.46, H * 0.45);
      var ringCount = 3;
      var rate = reducedMotion ? 0.6 : 1.75;
      for (var i = 0; i < ringCount; i++) {
        var ph = (t * rate + i / ringCount) % 1;
        var rad = lerp(55, 360, ph);
        var alpha = (1 - ph) * lerp(0.28, 0.78, climaxK);
        ctx.lineWidth = lerp(2.5, 6, climaxK);
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = '#00F0FF';
        ctx.beginPath();
        ctx.arc(-4, 0, rad, 0, Math.PI * 2);
        ctx.stroke();
        ctx.strokeStyle = '#FF2E63';
        ctx.beginPath();
        ctx.arc(4, 0, rad, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();
    }

    // vinheta vermelha pulsante no climax
    if (climaxK > 0.05) {
      var pulse = reducedMotion ? 0.6 : (0.5 + 0.5 * Math.sin(t * 14));
      var rv = ctx.createRadialGradient(W * 0.5, H * 0.48, 150, W * 0.5, H * 0.48, 520);
      rv.addColorStop(0, 'rgba(255, 46, 59, 0)');
      rv.addColorStop(1, 'rgba(255, 30, 46, ' + (climaxK * (0.28 + 0.22 * pulse)).toFixed(3) + ')');
      ctx.fillStyle = rv;
      ctx.fillRect(0, 0, W, H);
    }
  }

  // ------------------------------------------------ elementos de HUD (4 lados)
  function drawWatermarkBadge(ctx, presetId, t) {
    ctx.save();
    var bx = 16;
    var by = 14;
    var bh = 28;
    ctx.font = '800 12px ' + FONT_UI;
    var label = 'PREVIA GRATIS';
    var tw = ctx.measureText(label).width;
    var bw = tw + 30;

    roundRect(ctx, bx, by, bw, bh, 14);
    ctx.fillStyle = 'rgba(11, 15, 25, 0.80)';
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(255, 212, 0, 0.82)';
    ctx.stroke();

    // ponto indicador vetorial (nunca emoji)
    ctx.beginPath();
    ctx.arc(bx + 13, by + bh / 2, 4, 0, Math.PI * 2);
    ctx.fillStyle = COLORS.accent;
    ctx.fill();

    ctx.fillStyle = COLORS.white;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, bx + 22, by + bh / 2 + 0.5);

    // cronometro discreto extra no preset Suspense Noir
    if (presetId === 'suspense_noir') {
      var rem = Math.max(0, DURATION - t).toFixed(1);
      var rtxt = 'T-' + rem + 's';
      var rw = ctx.measureText(rtxt).width + 28;
      var rx = W - 16 - rw;
      roundRect(ctx, rx, by, rw, bh, 14);
      ctx.fillStyle = 'rgba(11, 15, 25, 0.82)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(255, 46, 59, 0.82)';
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(rx + 12, by + bh / 2, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = COLORS.alert;
      ctx.fill();
      ctx.fillStyle = COLORS.white;
      ctx.fillText(rtxt, rx + 21, by + bh / 2 + 0.5);
    }

    ctx.restore();
  }

  function drawTopHud(ctx, o) {
    if (o.alpha <= 0.01) return;
    ctx.save();
    ctx.globalAlpha = o.alpha;

    var y = 54;
    var h = 76;
    var padX = 14;
    var gap = 14;

    ctx.font = '900 28px ' + FONT_DISPLAY;
    var badgeW = Math.max(ctx.measureText('NIVEL 10').width, ctx.measureText(o.badgeText).width) + 24;
    ctx.font = '800 15px ' + FONT_UI;
    var labW = ctx.measureText(o.label).width;
    ctx.font = '900 34px ' + FONT_DISPLAY;
    var valW = Math.max(ctx.measureText(o.value).width, ctx.measureText('1.000x').width);

    var rightW = Math.max(labW, valW);
    var totalW = Math.min(W - 32, padX + badgeW + gap + rightW + padX);
    var x = (W - totalW) / 2;
    var pulse = o.alert ? (o.reducedMotion ? 0.7 : 0.5 + 0.5 * Math.sin(o.t * 14)) : 0;

    // caixa principal com borda completa nos 4 lados
    roundRect(ctx, x, y, totalW, h, 16);
    ctx.fillStyle = COLORS.panel;
    ctx.fill();
    ctx.lineWidth = o.alert ? 3 : 2;
    ctx.strokeStyle = o.alert ? 'rgba(255, 46, 59, ' + (0.65 + 0.35 * pulse).toFixed(2) + ')' : COLORS.border;
    ctx.stroke();

    // selo amarelo com pop deterministico quando o numero muda
    var popK = clamp(o.badgeStepK, 0, 1);
    var popS = popK < 1 ? 0.80 + 0.20 * easeOutBack(popK) : 1;
    var bx = x + padX;
    var by = y + 11;
    var bh = h - 22;

    ctx.save();
    ctx.translate(bx + badgeW / 2, by + bh / 2);
    ctx.scale(popS, popS);
    roundRect(ctx, -badgeW / 2, -bh / 2, badgeW, bh, 11);
    ctx.fillStyle = COLORS.accent;
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = COLORS.ink;
    ctx.stroke();
    ctx.fillStyle = COLORS.ink;
    ctx.font = '900 26px ' + FONT_DISPLAY;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(o.badgeText, 0, 2);
    ctx.restore();

    // rotulo em cima, valor grande embaixo (sem colisao)
    var rx = bx + badgeW + gap;
    var maxRight = x + totalW - padX - rx;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.font = '800 13px ' + FONT_UI;
    ctx.fillStyle = o.alert ? COLORS.alertSoft : COLORS.label;
    ctx.fillText(o.label, rx, y + 27, maxRight);

    ctx.font = '900 34px ' + FONT_DISPLAY;
    ctx.fillStyle = o.alert ? (pulse > 0.5 ? '#FFFFFF' : '#FFC4C8') : COLORS.white;
    ctx.fillText(o.value, rx, y + 64, maxRight);

    ctx.restore();
  }

  function drawWarnIcon(ctx, x, y, s) {
    ctx.save();
    ctx.translate(x, y);
    ctx.beginPath();
    ctx.moveTo(0, -s * 0.52);
    ctx.lineTo(s * 0.54, s * 0.44);
    ctx.lineTo(-s * 0.54, s * 0.44);
    ctx.closePath();
    ctx.fillStyle = COLORS.accent;
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = COLORS.ink;
    ctx.stroke();
    ctx.fillStyle = COLORS.ink;
    ctx.fillRect(-s * 0.06, -s * 0.2, s * 0.12, s * 0.34);
    ctx.beginPath();
    ctx.arc(0, s * 0.27, s * 0.075, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawAlertBanner(ctx, o) {
    if (o.alpha <= 0.01) return;
    var enter = clamp((o.t - o.t0) / 0.22, 0, 1);
    if (enter <= 0) return;
    var pulse = o.reducedMotion ? 0.55 : (0.5 + 0.5 * Math.sin((o.t - o.t0) * 18));

    ctx.save();
    ctx.globalAlpha = o.alpha;
    var y = 140;
    var h = 44;
    ctx.font = '900 24px ' + FONT_DISPLAY;
    var text = o.text || 'LIMITE ATINGIDO';
    var tw = ctx.measureText(text).width;
    var w = Math.min(W - 44, tw + 70);
    var x = (W - w) / 2;
    var sc = 0.78 + 0.22 * easeOutBack(enter);

    ctx.translate(W / 2, y + h / 2);
    ctx.scale(sc, sc);
    ctx.translate(-W / 2, -(y + h / 2));

    roundRect(ctx, x, y, w, h, 12);
    ctx.fillStyle = 'rgba(' + ((160 + 95 * pulse) | 0) + ', 20, 32, 0.94)';
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = COLORS.white;
    ctx.stroke();

    drawWarnIcon(ctx, x + 28, y + h / 2, 26);

    ctx.fillStyle = COLORS.white;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, x + 48, y + h / 2 + 1.5);
    ctx.restore();
  }

  function drawVerticalMeter(ctx, o) {
    if (o.alpha <= 0.01) return;
    ctx.save();
    ctx.globalAlpha = o.alpha;

    var x = 502;
    var yTop = 225;
    var yBot = 605;
    var trackH = yBot - yTop;
    var level = clamp(o.progress, 0, 1);
    var fillY = lerp(yBot, yTop, level);

    // trilho com borda completa nos 4 lados
    roundRect(ctx, x - 9, yTop - 12, 18, trackH + 24, 9);
    ctx.fillStyle = 'rgba(11, 15, 25, 0.74)';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.78)';
    ctx.stroke();

    // preenchimento da barra
    var fillH = Math.max(8, yBot + 6 - fillY);
    roundRect(ctx, x - 5, fillY, 10, fillH, 5);
    ctx.fillStyle = o.alert ? COLORS.alert : COLORS.accent;
    ctx.fill();

    // marcas de escala com contorno para leitura nitida
    var marks = o.marks || ['1x', '10x', '50x', '250x', '1.000x'];
    ctx.font = '800 13px ' + FONT_UI;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    for (var i = 0; i < marks.length; i++) {
      var frac = marks.length > 1 ? i / (marks.length - 1) : 0;
      var yy = lerp(yBot, yTop, frac);
      ctx.strokeStyle = COLORS.white;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - 10, yy);
      ctx.lineTo(x - 17, yy);
      ctx.stroke();

      ctx.strokeStyle = COLORS.ink;
      ctx.lineWidth = 4;
      ctx.strokeText(marks[i], x - 21, yy + 0.5);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
      ctx.fillText(marks[i], x - 21, yy + 0.5);
    }

    // losango marcador no nivel atual
    var jitter = (o.alert && !o.reducedMotion) ? Math.sin(o.t * 36) * 2.2 : 0;
    ctx.save();
    ctx.translate(x, fillY + jitter);
    ctx.beginPath();
    ctx.moveTo(0, -11);
    ctx.lineTo(11, 0);
    ctx.lineTo(0, 11);
    ctx.lineTo(-11, 0);
    ctx.closePath();
    ctx.fillStyle = CHAR_PAL.hoodie;
    ctx.fill();
    ctx.lineWidth = 2.8;
    ctx.strokeStyle = COLORS.white;
    ctx.stroke();
    ctx.restore();

    ctx.restore();
  }

  function drawKineticCaptions(ctx, chunks, t, alpha) {
    if (alpha <= 0.01 || !chunks || !chunks.length) return;
    var activeChunk = null;
    for (var i = 0; i < chunks.length; i++) {
      if (t >= chunks[i].t0 && t < chunks[i].t1) {
        activeChunk = chunks[i];
        break;
      }
    }
    if (!activeChunk) return;

    var size = activeChunk.words.length > 3 ? 38 : 42;
    var maxW = 472;
    var centerY = 766;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.font = '900 ' + size + 'px ' + FONT_CAPTION;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    ctx.miterLimit = 2;

    var toks = [];
    for (var w = 0; w < activeChunk.words.length; w++) {
      var item = activeChunk.words[w];
      var txt = typeof item.texto.toLocaleUpperCase === 'function'
        ? item.texto.toLocaleUpperCase('pt-BR')
        : item.texto.toUpperCase();
      var m = ctx.measureText(txt);
      var inked = (m.actualBoundingBoxLeft || 0) + (m.actualBoundingBoxRight || 0);
      toks.push({ w: item, txt: txt, width: Math.max(m.width, inked) });
    }

    var space = Math.max(ctx.measureText(' ').width * 1.35, size * 0.34);
    var lines = [];
    var line = [];
    var lw = 0;

    for (var tkIdx = 0; tkIdx < toks.length; tkIdx++) {
      var tk = toks[tkIdx];
      var add = (line.length ? space : 0) + tk.width;
      if (line.length && lw + add > maxW) {
        lines.push({ toks: line, w: lw });
        line = [];
        lw = 0;
      }
      lw += (line.length ? space : 0) + tk.width;
      line.push(tk);
    }
    if (line.length) lines.push({ toks: line, w: lw });

    var widest = 0;
    for (var l = 0; l < lines.length; l++) {
      if (lines[l].w > widest) widest = lines[l].w;
    }
    var fit = widest > maxW ? maxW / widest : 1;
    var enter = clamp((t - activeChunk.t0) / 0.11, 0, 1);
    var es = (0.85 + 0.15 * easeOutBack(enter)) * fit;
    var lh = size * 1.18;

    ctx.translate(W / 2, centerY);
    ctx.scale(es, es);

    for (var li = 0; li < lines.length; li++) {
      var ln = lines[li];
      var x = -ln.w / 2;
      var yy = (li - (lines.length - 1) / 2) * lh;
      for (var ti = 0; ti < ln.toks.length; ti++) {
        var tok = ln.toks[ti];
        var isActive = t >= tok.w.t0 - 0.02 && t < tok.w.t1 + 0.02;
        var pop = isActive ? 1 + 0.08 * Math.max(0, 1 - (t - tok.w.t0) / 0.14) : 1;
        ctx.save();
        ctx.translate(x + tok.width / 2, yy);
        ctx.scale(pop, pop);
        ctx.textAlign = 'center';
        ctx.lineWidth = 10;
        ctx.strokeStyle = COLORS.ink;
        ctx.strokeText(tok.txt, 0, 0);
        ctx.fillStyle = isActive ? COLORS.accent : COLORS.white;
        ctx.fillText(tok.txt, 0, 0);
        ctx.restore();
        x += tok.width + space;
      }
    }

    ctx.restore();
  }

  function drawLockIcon(ctx, x, y, s) {
    ctx.save();
    ctx.translate(x, y);
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.arc(0, -s * 0.22, s * 0.24, Math.PI, 0);
    ctx.stroke();
    roundRect(ctx, -s * 0.34, -s * 0.2, s * 0.68, s * 0.56, 3);
    ctx.fillStyle = COLORS.ink;
    ctx.fill();
    ctx.fillStyle = COLORS.accent;
    ctx.beginPath();
    ctx.arc(0, s * 0.06, s * 0.09, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawAct4Overlay(ctx, act4K) {
    if (act4K <= 0.01) return;
    var fade = easeOutCubic(clamp(act4K / 0.28, 0, 1));
    var slideY = (1 - fade) * 26;

    ctx.save();
    // gradiente discreto na base para legibilidade sem tampar o rosto do boneco
    var scrim = ctx.createLinearGradient(0, 590, 0, H);
    scrim.addColorStop(0, 'rgba(7, 10, 18, 0)');
    scrim.addColorStop(0.55, 'rgba(7, 10, 18, ' + (0.68 * fade).toFixed(3) + ')');
    scrim.addColorStop(1, 'rgba(7, 10, 18, ' + (0.94 * fade).toFixed(3) + ')');
    ctx.fillStyle = scrim;
    ctx.fillRect(0, 590, W, H - 590);

    // cartao discreto na base com borda completa nos 4 lados
    ctx.globalAlpha = fade;
    var cw = W - 44;
    var ch = 152;
    var cx = 22;
    var cy = H - ch - 26 + slideY;

    roundRect(ctx, cx, cy, cw, ch, 18);
    ctx.fillStyle = COLORS.panelStrong;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255, 212, 0, 0.85)';
    ctx.stroke();

    // selo superior do cartao
    var pillW = 148;
    var pillH = 26;
    var px = cx + (cw - pillW) / 2;
    var py = cy + 16;
    roundRect(ctx, px, py, pillW, pillH, 13);
    ctx.fillStyle = COLORS.accent;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = COLORS.ink;
    ctx.stroke();
    drawLockIcon(ctx, px + 18, py + pillH / 2 + 1, 16);
    ctx.fillStyle = COLORS.ink;
    ctx.font = '800 12px ' + FONT_UI;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText('MODO PRO 65S', px + 32, py + pillH / 2 + 0.5);

    // texto principal do gancho de venda da previa
    ctx.textAlign = 'center';
    ctx.fillStyle = COLORS.white;
    ctx.font = '800 20px ' + FONT_UI;
    ctx.fillText('Previa de 10s encerrada:', W / 2, cy + 72);

    ctx.fillStyle = COLORS.accent;
    ctx.font = '800 19px ' + FONT_UI;
    ctx.fillText('desbloqueie 65s Full HD no Pro', W / 2, cy + 100);

    // barra de encerramento discreta
    var barW = cw - 56;
    var barX = cx + 28;
    var barY = cy + 124;
    roundRect(ctx, barX, barY, barW, 8, 4);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.14)';
    ctx.fill();
    roundRect(ctx, barX, barY, barW * clamp(0.45 + act4K * 0.55, 0, 1), 8, 4);
    ctx.fillStyle = COLORS.accent;
    ctx.fill();

    ctx.restore();
  }

  // ------------------------------------------------ cronograma dos 4 atos
  var RIG_KEYS = [
    { t: 0.0, pose: 'point_hook', expr: 'amazed', dur: 0.25, ease: 'back' },
    { t: 1.35, pose: 'shrug_question', expr: 'shock', dur: 0.28, ease: 'inout' },
    { t: 2.6, pose: 'flex', expr: 'determined', dur: 0.26, ease: 'back' },
    { t: 3.7, pose: 'jump_up', expr: 'amazed', dur: 0.28, ease: 'back' },
    { t: 4.75, pose: 'dodge_lean', expr: 'shock', dur: 0.24, ease: 'inout' },
    { t: 5.6, pose: 'space_float_panic', expr: 'panic', dur: 0.20, ease: 'back' },
    { t: 6.85, pose: 'freefall_scream', expr: 'scream', dur: 0.18, ease: 'back' },
    { t: 8.2, pose: 'shock_closeup', expr: 'panic', dur: 0.30, ease: 'inout' }
  ];

  function renderFrame(ctx, compiled, tRaw, reducedMotion) {
    var t = clamp(tRaw, 0, DURATION);
    var theme = compiled.theme;
    var presetId = compiled.presetId;

    // desaceleracao dramatica no Ato 4 (8.2s - 10.0s) mantendo vida sutil
    var animT = t <= 8.2 ? t : 8.2 + (t - 8.2) * 0.24;

    // fases normalizadas dos 4 atos
    var act1K = invLerp(0.0, 2.6, t);
    var act2K = invLerp(2.6, 5.6, t);
    var act3K = invLerp(5.6, 8.2, t);
    var act4K = invLerp(8.2, 10.0, t);

    // progresso da metrica (0..1)
    var metricP = 0;
    if (t < 2.6) {
      metricP = lerp(0.0, 0.08, easeOutCubic(act1K));
    } else if (t < 5.6) {
      metricP = lerp(0.08, 0.72, easeInOutCubic(act2K));
    } else if (t < 8.2) {
      metricP = lerp(0.72, 1.0, easeOutCubic(act3K));
    } else {
      metricP = 1.0;
    }

    // intensidade visual geral (0..1)
    var intensity = t < 2.6
      ? lerp(0.18, 0.35, act1K)
      : (t < 5.6 ? lerp(0.35, 0.78, act2K) : (t < 8.2 ? lerp(0.78, 1.0, act3K) : lerp(1.0, 0.45, clamp(act4K * 2, 0, 1))));

    // fator de climax (ativo em 5.6 - 8.2, suavizando no Ato 4)
    var climaxK = t < 5.6
      ? 0
      : (t < 8.2 ? easeOutCubic(invLerp(5.6, 6.1, t)) : lerp(1, 0.35, easeOutCubic(invLerp(8.2, 8.8, t))));

    // camera zoom e enquadramento
    var zoom = 1.0;
    if (t < 2.6) {
      // zoom punch-in rapido no gancho (estavel e impactante em t=0.4s)
      var punch = easeOutBack(clamp(t / 0.38, 0, 1));
      zoom = lerp(1.04, 1.15, punch) + act1K * 0.03;
    } else if (t < 5.6) {
      zoom = lerp(1.18, 0.98, easeOutCubic(invLerp(2.6, 3.1, t))) + act2K * 0.06;
    } else if (t < 8.2) {
      zoom = lerp(1.04, 1.16, easeOutCubic(act3K));
    } else {
      zoom = lerp(1.16, 1.04, easeOutCubic(invLerp(8.2, 8.85, t)));
    }

    // cortes rapidos de zoom no preset Onda de Choque
    if (presetId === 'caos_sonoro' && t < 8.2 && !reducedMotion) {
      var beat = (t * 1.8) % 1;
      zoom += (1 - easeOutCubic(clamp(beat / 0.22, 0, 1))) * (0.04 + climaxK * 0.05);
    }

    // camera shake (respeita prefers-reduced-motion)
    var shakeAmp = 0;
    if (t >= 5.6 && t < 8.2) {
      shakeAmp = lerp(5.5, 11.5, act3K);
    } else if (t >= 2.6 && t < 5.6) {
      shakeAmp = lerp(0.6, 2.8, act2K);
    }
    if (presetId === 'caos_sonoro') shakeAmp *= 1.55;
    if (presetId === 'suspense_noir') shakeAmp *= 0.65;
    if (reducedMotion) shakeAmp *= 0.08;

    var sx = shakeAmp > 0.05 ? Math.sin(t * 67) * shakeAmp + Math.cos(t * 43) * shakeAmp * 0.4 : 0;
    var sy = shakeAmp > 0.05 ? Math.cos(t * 59) * shakeAmp + Math.sin(t * 37) * shakeAmp * 0.4 : 0;

    ctx.clearRect(0, 0, W, H);

    // mundo com transformacao de camera
    ctx.save();
    ctx.translate(W / 2 + sx, H * 0.48 + sy);
    ctx.scale(zoom, zoom);
    ctx.translate(-W / 2, -H * 0.48);

    drawBackground(ctx, theme, presetId, animT, climaxK, reducedMotion);
    drawThemeProps(ctx, theme, animT, intensity, 'back');

    // sombra no chao sob o boneco
    var meterVisible = invLerp(2.3, 2.8, t);
    var charX = lerp(270, 232, easeInOutCubic(meterVisible));
    var jumpArc = (t >= 3.6 && t < 4.75) ? Math.sin(invLerp(3.6, 4.75, t) * Math.PI) * 44 : 0;
    var floatBob = (t >= 5.6 && t < 8.2) ? Math.sin(animT * 10) * (reducedMotion ? 3 : 11) : Math.sin(animT * 2.5) * 4;
    var charPelvisY = 532 - jumpArc + floatBob;

    ctx.save();
    ctx.fillStyle = 'rgba(5, 8, 16, 0.46)';
    var shScale = clamp(1 - jumpArc / 160, 0.58, 1);
    ctx.beginPath();
    ctx.ellipse(charX, 642, 72 * shScale, 15 * shScale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // personagem articulado
    var tracked = trackRig(RIG_KEYS, t);
    var windForce = t >= 5.6 ? [lerp(-22, -42, climaxK), -18] : [lerp(4, -14, act2K), -4];
    if (theme.id === 'velocidade') windForce[0] -= 26 * intensity;

    var charScale = 0.74;
    if (theme.id === 'encolher' && t >= 2.6) {
      charScale = theme.shrink
        ? lerp(0.74, 0.56, easeInOutCubic(clamp((t - 2.6) / 5.4, 0, 1)))
        : lerp(0.74, 0.86, easeInOutCubic(clamp((t - 2.6) / 5.4, 0, 1)));
    }
    var squash = 1 + Math.sin(animT * 6.5) * (t >= 5.6 && t < 8.2 ? 0.035 : 0.014);
    if (jumpArc > 4) squash = 1.07;

    drawCharacter(ctx, {
      x: charX,
      y: charPelvisY,
      scale: charScale,
      pose: tracked.pose,
      expr: tracked.expr,
      t: animT,
      rot: (t >= 5.6 && t < 8.2 && !reducedMotion) ? Math.sin(animT * 14) * 0.04 : 0,
      squash: squash,
      blink: tracked.blinkBoost,
      wind: windForce,
      rim: {
        color: presetId === 'suspense_noir' ? '#C7DCFF' : theme.palette.rim,
        dir: [1, -0.45]
      },
      look: t < 2.6 ? 0.25 : (t < 5.6 ? 0.45 : -0.15),
      seed: 5,
      reducedMotion: reducedMotion
    });

    drawThemeProps(ctx, theme, animT, intensity, 'front');
    ctx.restore(); // fim camera

    // atmosfera do preset (spotlight noir, aneis cromaticos, vinheta climax)
    drawPresetAtmosphere(ctx, presetId, animT, climaxK, reducedMotion);

    // HUD de 4 lados
    var hudAlpha = easeOutCubic(invLerp(0.05, 0.32, t));
    var badgeSpan = theme.hud.badgeEnd - theme.hud.badgeStart;
    var badgeFloat = theme.hud.badgeStart + badgeSpan * metricP;
    var badgeNum = clamp(Math.floor(badgeFloat + 0.0001), theme.hud.badgeStart, theme.hud.badgeEnd);
    var badgeText = theme.hud.badgePrefix + badgeNum;
    var badgeStepK = t < 2.6 ? clamp(t / 0.3, 0, 1) : (badgeNum >= theme.hud.badgeEnd ? 1 : clamp((badgeFloat - Math.floor(badgeFloat)) / 0.35, 0, 1));

    var alertActive = t >= 5.6;
    drawTopHud(ctx, {
      t: t,
      alpha: hudAlpha,
      badgeText: badgeText,
      badgeStepK: badgeStepK,
      label: theme.hud.label,
      value: theme.hud.formatValue(metricP),
      alert: alertActive && t < 8.5,
      reducedMotion: reducedMotion
    });

    // medidor vertical a direita (Ato 2 e Ato 3, suaviza no Ato 4)
    var rulerAlpha = t < 8.2
      ? easeOutCubic(invLerp(2.35, 2.85, t))
      : lerp(1, 0.38, easeOutCubic(invLerp(8.2, 8.7, t)));
    drawVerticalMeter(ctx, {
      t: t,
      alpha: rulerAlpha,
      progress: metricP,
      marks: theme.hud.marks,
      alert: alertActive,
      reducedMotion: reducedMotion
    });

    // faixa de alerta pulsante no Ato 3
    if (t >= 5.6) {
      var alertAlpha = t < 8.2 ? 1 : lerp(1, 0, easeOutCubic(invLerp(8.2, 8.55, t)));
      drawAlertBanner(ctx, {
        t: t,
        t0: 5.6,
        alpha: alertAlpha,
        text: 'LIMITE ATINGIDO',
        reducedMotion: reducedMotion
      });
    }

    // legendas cineticas no terco inferior (desaparecem antes do cartao do Ato 4)
    var captionAlpha = t < 8.0 ? 1 : lerp(1, 0, invLerp(8.0, 8.2, t));
    drawKineticCaptions(ctx, compiled.captions, t, captionAlpha);

    // gancho de venda da previa (8.2s - 10.0s)
    if (t >= 8.2) {
      drawAct4Overlay(ctx, act4K);
    }

    // selo obrigatorio PREVIA GRATIS sempre legivel no topo
    drawWatermarkBadge(ctx, presetId, t);
  }

  // ------------------------------------------------ fabrica do player
  function createPlayer(canvasElement, callbacks) {
    var cb = callbacks || {};
    var ctx = null;

    if (canvasElement && typeof canvasElement.getContext === 'function') {
      if (canvasElement.width !== W) canvasElement.width = W;
      if (canvasElement.height !== H) canvasElement.height = H;
      ctx = canvasElement.getContext('2d');
      if (ctx) {
        ctx.imageSmoothingEnabled = true;
      }
    }

    var state = {
      tema: DEFAULT_TEMA,
      presetId: DEFAULT_PRESET,
      currentTime: 0.4,
      duration: DURATION,
      playing: false,
      finished: false,
      destroyed: false
    };

    var compiled = null;
    var rafId = null;
    var lastTs = null;

    // deteccao de prefers-reduced-motion
    var reducedMotion = false;
    var mq = null;
    var onMqChange = null;
    if (typeof root.matchMedia === 'function') {
      try {
        mq = root.matchMedia('(prefers-reduced-motion: reduce)');
        reducedMotion = Boolean(mq.matches);
        onMqChange = function (ev) {
          reducedMotion = Boolean(ev.matches);
          if (!state.playing && !state.destroyed) drawNow();
        };
        if (typeof mq.addEventListener === 'function') {
          mq.addEventListener('change', onMqChange);
        } else if (typeof mq.addListener === 'function') {
          mq.addListener(onMqChange);
        }
      } catch (err) {
        reducedMotion = false;
      }
    }

    function compile(temaInput, presetInput) {
      var cleanTema = sanitizeText(temaInput);
      state.tema = cleanTema || DEFAULT_TEMA;
      state.presetId = resolvePresetId(presetInput || state.presetId);
      var theme = detectTheme(state.tema);
      compiled = {
        theme: theme,
        presetId: state.presetId,
        captions: buildTimelineCaptions(state.tema, theme)
      };
    }

    function notifyTime() {
      if (typeof cb.onTimeUpdate === 'function') {
        cb.onTimeUpdate(state.currentTime, DURATION);
      }
    }

    function notifyState() {
      if (typeof cb.onStateChange === 'function') {
        cb.onStateChange(state.playing);
      }
    }

    function notifyFinish() {
      if (typeof cb.onFinish === 'function') {
        cb.onFinish();
      }
    }

    function cancelLoop() {
      if (rafId !== null) {
        if (typeof cancelAnimationFrame === 'function') {
          cancelAnimationFrame(rafId);
        } else {
          clearTimeout(rafId);
        }
        rafId = null;
      }
      lastTs = null;
    }

    function scheduleFrame(fn) {
      if (typeof requestAnimationFrame === 'function') {
        return requestAnimationFrame(fn);
      }
      return setTimeout(function () {
        fn(Date.now());
      }, 16);
    }

    function drawNow() {
      if (!ctx || state.destroyed) return;
      if (!compiled) compile(state.tema, state.presetId);
      renderFrame(ctx, compiled, state.currentTime, reducedMotion);
    }

    function tick(ts) {
      if (!state.playing || state.destroyed) return;
      if (lastTs === null) {
        lastTs = ts;
      }
      var dt = (ts - lastTs) / 1000;
      lastTs = ts;
      if (dt < 0) dt = 0;
      if (dt > 0.08) dt = 0.08;

      state.currentTime = Math.min(DURATION, state.currentTime + dt);
      drawNow();
      notifyTime();

      if (state.currentTime >= DURATION) {
        cancelLoop();
        state.currentTime = DURATION;
        state.playing = false;
        state.finished = true;
        notifyState();
        notifyFinish();
        return;
      }

      rafId = scheduleFrame(tick);
    }

    function start(opts) {
      if (state.destroyed) return;
      var o = opts || {};
      cancelLoop();
      compile(
        o.tema !== undefined ? o.tema : state.tema,
        o.presetId !== undefined ? o.presetId : state.presetId
      );
      state.currentTime = 0;
      state.finished = false;
      state.playing = true;
      lastTs = null;
      drawNow();
      notifyState();
      notifyTime();
      rafId = scheduleFrame(tick);
    }

    function togglePlay() {
      if (state.destroyed) return;
      if (state.playing) {
        cancelLoop();
        state.playing = false;
        notifyState();
        return;
      }
      if (state.finished || state.currentTime >= DURATION - 0.001) {
        state.currentTime = 0;
        state.finished = false;
      }
      if (!compiled) compile(state.tema, state.presetId);
      state.playing = true;
      lastTs = null;
      drawNow();
      notifyState();
      notifyTime();
      rafId = scheduleFrame(tick);
    }

    function replay() {
      if (state.destroyed) return;
      start({ tema: state.tema, presetId: state.presetId });
    }

    function setPreviewStatic(opts) {
      if (state.destroyed) return;
      var o = opts || {};
      var wasPlaying = state.playing;
      cancelLoop();
      compile(
        o.tema !== undefined ? o.tema : state.tema,
        o.presetId !== undefined ? o.presetId : state.presetId
      );
      state.playing = false;
      state.finished = false;
      state.currentTime = 0.4;
      drawNow();
      if (wasPlaying) {
        notifyState();
      }
    }

    function getState() {
      return {
        tema: state.tema,
        presetId: state.presetId,
        currentTime: state.currentTime,
        duration: DURATION,
        playing: state.playing
      };
    }

    function destroy() {
      cancelLoop();
      state.playing = false;
      state.destroyed = true;
      if (mq && onMqChange) {
        if (typeof mq.removeEventListener === 'function') {
          mq.removeEventListener('change', onMqChange);
        } else if (typeof mq.removeListener === 'function') {
          mq.removeListener(onMqChange);
        }
      }
    }

    // compilacao inicial pronta para uso imediato
    compile(DEFAULT_TEMA, DEFAULT_PRESET);

    return {
      start: start,
      togglePlay: togglePlay,
      replay: replay,
      setPreviewStatic: setPreviewStatic,
      getState: getState,
      destroy: destroy
    };
  }

  root.StudioStickCanvas = {
    PRESETS: PRESETS,
    createPlayer: createPlayer
  };
})(typeof window !== 'undefined' ? window : globalThis);
