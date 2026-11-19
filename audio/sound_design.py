"""Estacao 2 (v3): sintetiza cama sonora + SFX de suspense e masteriza audio/mix_final.mp3.

Uso (na raiz do repositorio, apos audio/gerar_narracao.py):
    python3 audio/sound_design.py

100% Python padrao (acelerado por numpy quando disponivel) + ffmpeg, sem downloads.
Antes de mixar, executa a trava blindada contra audio velho (pipeline/historico.py):
confere video_id, titulo, roteiro_sha256 e CTA final 'COMENTE EU QUERO'.
Suporta Video 03 ('O Pix de 1 Centavo'), Video 02 ('Rota recalculada') e Video 01 legado.
"""

from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.historico import validar_artefatos_audio  # noqa: E402

PASTA_AUDIO = RAIZ / "audio"
VOZ_LIMPA_MP3 = PASTA_AUDIO / "voz_limpa.mp3"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"
MIX_FINAL_MP3 = PASTA_AUDIO / "mix_final.mp3"
NARRACAO_MP3 = PASTA_AUDIO / "narracao.mp3"

SR = 44100


def medir_duracao_ffprobe(caminho: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(caminho),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def _criar_buffer_estereo(n: int):
    if np is not None:
        return np.zeros(n, dtype=np.float64), np.zeros(n, dtype=np.float64)
    return array("d", [0.0]) * n, array("d", [0.0]) * n


def _gravar_wav_estereo(caminho: Path, esq, dir_) -> None:
    if np is not None:
        l_clip = np.clip(esq, -0.98, 0.98)
        r_clip = np.clip(dir_, -0.98, 0.98)
        inter = np.empty(l_clip.size * 2, dtype=np.int16)
        inter[0::2] = (l_clip * 32767.0).astype(np.int16)
        inter[1::2] = (r_clip * 32767.0).astype(np.int16)
        dados = inter.tobytes()
    else:
        n = len(esq)
        buf = array("h", [0]) * (n * 2)
        for i in range(n):
            lv = max(-0.98, min(0.98, esq[i]))
            rv = max(-0.98, min(0.98, dir_[i]))
            buf[2 * i] = int(lv * 32767.0)
            buf[2 * i + 1] = int(rv * 32767.0)
        dados = buf.tobytes()

    with wave.open(str(caminho), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(dados)


def _misturar_trecho(esq, dir_, inicio_s: float, s_esq, s_dir, ganho: float = 1.0) -> None:
    ini = int(round(inicio_s * SR))
    n_tot = len(esq)
    n_seg = len(s_esq)
    if ini >= n_tot or ini + n_seg <= 0:
        return
    src_ini = max(0, -ini)
    dst_ini = max(0, ini)
    comp = min(n_seg - src_ini, n_tot - dst_ini)
    if comp <= 0:
        return
    if np is not None:
        esq[dst_ini : dst_ini + comp] += s_esq[src_ini : src_ini + comp] * ganho
        dir_[dst_ini : dst_ini + comp] += s_dir[src_ini : src_ini + comp] * ganho
    else:
        for k in range(comp):
            esq[dst_ini + k] += s_esq[src_ini + k] * ganho
            dir_[dst_ini + k] += s_dir[src_ini + k] * ganho


def _eh_video_03(ev: dict) -> bool:
    return ("pix_1" in ev) or ("guarda_roupa" in ev) or (int(ev.get("video_id", 1)) == 3)


def _eh_video_02(ev: dict) -> bool:
    return (not _eh_video_03(ev)) and (("gps_rota" in ev) or ("caminhao" in ev) or (int(ev.get("video_id", 1)) == 2))


def _envelope_drone_em_t(t: float, ev: dict) -> float:
    """Curva de tensao do drone com corte subito no plot_twist."""
    if _eh_video_03(ev):
        cong = float(ev.get("congela", 8.0))
        pix2 = float(ev.get("pix_2", 12.0))
        pix3 = float(ev.get("pix_3", 20.0))
        tj = float(ev.get("trava_janela", 26.0))
        tj_d = float(ev.get("trava_janela_duracao", 1.4))
        pix4 = float(ev.get("pix_4", 28.0))
        twist = float(ev.get("plot_twist", 33.0))
        gr = float(ev.get("guarda_roupa", 34.5))
        gr_d = float(ev.get("guarda_roupa_duracao", 1.6))
        cta = float(ev.get("cta", 40.0))

        # Corte subito no plot_twist e silencio gelado durante o rangido do guarda-roupa
        if twist + 0.045 <= t < gr + gr_d:
            return 0.0
        # Respiracao grave muito fina durante "No escuro do quarto..."
        if gr + gr_d <= t < cta:
            return 0.08
        # Cama limpa e discreta na CTA
        if t >= cta:
            return 0.11 * min(1.0, (t - cta) / 0.25)

        corte_twist = 1.0 if t < twist else max(0.0, 1.0 - (t - twist) / 0.045)
        if t < 0.35:
            base = 0.12 * (t / 0.35)
        elif t < cong:
            base = 0.13
        elif t < pix2:
            base = 0.22
        elif t < pix3:
            k = (t - pix2) / max(0.1, pix3 - pix2)
            base = 0.23 + 0.08 * k
        elif t < pix4:
            base = 0.33
        else:
            base = 0.38

        if tj - 0.1 <= t <= tj + tj_d + 0.1:
            base *= 0.32
        return base * corte_twist

    if _eh_video_02(ev):
        gps = float(ev.get("gps_rota", 7.0))
        rua = float(ev.get("rua_escura", 14.0))
        dest = float(ev.get("destino_acidente", 22.0))
        cam = float(ev.get("caminhao", 29.0))
        cam_d = float(ev.get("caminhao_duracao", 1.75))
        suss = float(ev.get("sussurro", 35.0))
        twist = float(ev.get("plot_twist", 37.0))
        cta = float(ev.get("cta", 41.0))

        if twist + 0.045 <= t < cta:
            return 0.0
        if t >= cta:
            rel = t - cta
            return 0.11 * min(1.0, rel / 0.25)

        corte_twist = 1.0 if t < twist else max(0.0, 1.0 - (t - twist) / 0.045)
        if t < 0.35:
            base = 0.15 * (t / 0.35)
        elif t < gps:
            base = 0.15 + 0.05 * (t / max(0.1, gps))
        elif t < rua:
            k = (t - gps) / max(0.1, rua - gps)
            base = 0.20 + 0.08 * k
        elif t < dest:
            k = (t - rua) / max(0.1, dest - rua)
            base = 0.28 + 0.08 * k
        elif t < cam:
            base = 0.37
        elif t < suss:
            base = 0.18
        else:
            base = 0.07

        if cam - 0.12 <= t <= cam + cam_d + 0.12:
            base *= 0.28
        return base * corte_twist

    # Curva legada Video 01
    h21 = float(ev.get("hora_21", 10.0))
    ap00 = float(ev.get("apagao_00", 19.0))
    h03 = float(ev.get("hora_03", 26.0))
    bat = float(ev.get("batidas_porta", 27.5))
    bat_d = float(ev.get("batidas_porta_duracao", 2.1))
    sil = float(ev.get("silencio", 34.0))
    foto = float(ev.get("foto_revela", 35.5))
    big = float(ev.get("big_face", 38.5))
    twist = float(ev.get("plot_twist", 40.5))

    if t >= twist + 0.045:
        return 0.0
    corte_twist = 1.0 if t < twist else max(0.0, 1.0 - (t - twist) / 0.045)
    if t < 0.4:
        base = 0.14 * (t / 0.4)
    elif t < h21:
        base = 0.14 + 0.04 * (t / max(0.1, h21))
    elif t < ap00:
        base = 0.18 + 0.07 * ((t - h21) / max(0.1, ap00 - h21))
    elif t < ap00 + 0.45:
        base = 0.08
    elif t < h03:
        base = 0.20 + 0.11 * ((t - (ap00 + 0.45)) / max(0.1, h03 - (ap00 + 0.45)))
    elif t < sil:
        base = 0.31
    elif t < foto:
        base = 0.05
    elif t < big:
        base = 0.16 + 0.24 * ((t - foto) / max(0.1, big - foto))
    else:
        base = 0.34
    if bat - 0.15 <= t <= bat + bat_d + 0.15:
        base *= 0.42
    return base * corte_twist


def sintetizar_cama_drone(duracao: float, ev: dict):
    """Sintetiza cama continua de suspense (sub-bass + batimento sombrio + ar grave filtrado)."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    passo = 128
    pontos = [
        _envelope_drone_em_t(min(duracao, (i * passo) / SR), ev)
        for i in range(n // passo + 2)
    ]

    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        idx_f = np.arange(n, dtype=np.float64) / passo
        idx_i = np.floor(idx_f).astype(np.int64)
        frac = idx_f - idx_i
        p_arr = np.array(pontos, dtype=np.float64)
        env = p_arr[idx_i] * (1.0 - frac) + p_arr[idx_i + 1] * frac

        lfo = 0.82 + 0.18 * np.sin(2.0 * np.pi * 0.25 * t)
        f0 = 44.0 if _eh_video_03(ev) else 49.0
        sub_l = 0.54 * np.sin(2.0 * np.pi * f0 * t) + 0.24 * np.sin(2.0 * np.pi * (f0 * 1.5) * t + 0.4)
        sub_r = 0.54 * np.sin(2.0 * np.pi * (f0 + 0.35) * t + 0.7) + 0.24 * np.sin(2.0 * np.pi * (f0 * 1.495) * t)
        harm = 0.10 * np.sin(2.0 * np.pi * 110.0 * t + 0.8 * np.sin(2.0 * np.pi * 0.19 * t))

        rng = np.random.default_rng(43)
        ruido = rng.uniform(-1.0, 1.0, n)
        k_lp = 95
        cs = np.cumsum(np.insert(ruido, 0, 0.0))
        ar = (cs[k_lp:] - cs[:-k_lp]) / k_lp
        ar = np.pad(ar, (0, n - len(ar))) * 1.4

        esq[:] = env * lfo * (sub_l + harm + 0.28 * ar)
        dir_[:] = env * lfo * (sub_r + harm * 0.92 - 0.24 * ar)
        return esq, dir_

    rng = random.Random(43)
    lp = 0.0
    alpha = 0.025
    two_pi = 2.0 * math.pi
    f0 = 44.0 if _eh_video_03(ev) else 49.0
    for i in range(n):
        t = i / SR
        bi = i // passo
        frac = (i - bi * passo) / passo
        env = pontos[bi] * (1.0 - frac) + pontos[bi + 1] * frac
        if env <= 1e-6:
            continue
        lfo = 0.82 + 0.18 * math.sin(two_pi * 0.25 * t)
        lp += alpha * (rng.uniform(-1.0, 1.0) - lp)
        harm = 0.10 * math.sin(two_pi * 110.0 * t + 0.8 * math.sin(two_pi * 0.19 * t))
        sub_l = 0.54 * math.sin(two_pi * f0 * t) + 0.24 * math.sin(two_pi * (f0 * 1.5) * t + 0.4)
        sub_r = 0.54 * math.sin(two_pi * (f0 + 0.35) * t + 0.7) + 0.24 * math.sin(two_pi * (f0 * 1.495) * t)
        esq[i] = env * lfo * (sub_l + harm + 0.8 * lp)
        dir_[i] = env * lfo * (sub_r + harm * 0.92 - 0.7 * lp)
    return esq, dir_


# ---------------- SFX VIDEO 03 ("O Pix de 1 Centavo") ----------------

def sfx_vibracao_celular(duracao: float = 0.46, intensidade: float = 1.0):
    """Vibracao realista de smartphone sobre cama/superficie (dois pulsos hapticos)."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    pulsos = [(0.0, 0.18), (0.24, 0.44)]
    for i in range(n):
        t = i / SR
        env = 0.0
        for p0, p1 in pulsos:
            if p0 <= t <= p1:
                env = min(1.0, (t - p0) / 0.012) * min(1.0, (p1 - t) / 0.018)
                break
        if env <= 0.0:
            continue
        buzz = (
            0.55 * math.sin(two_pi * 134.0 * t)
            + 0.32 * math.sin(two_pi * 268.0 * t)
            + 0.18 * math.sin(two_pi * 402.0 * t)
        )
        v = math.tanh(buzz * 1.5) * env * 0.52 * intensidade
        esq[i] = v * 0.95
        dir_[i] = v
    return esq, dir_


def sfx_pix_notificacao(nivel: int = 1):
    """Notificacao estilo app bancario brasileiro (limpa no Pix 1, cada vez mais sombria ate o Pix 4)."""
    dur = 0.42
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    pares = {
        1: (1046.5, 1318.5),  # Do6 -> Mi6 (alegre/limpo)
        2: (987.8, 1174.7),   # Si5 -> Re6 (estranho)
        3: (880.0, 830.6),    # La5 -> Sol#5 (tenso descendente)
        4: (784.0, 554.4),    # Sol5 -> Do#5 (tritono de terror)
    }
    f1, f2 = pares.get(nivel, (1046.5, 1318.5))
    for i in range(n):
        t = i / SR
        if t < 0.15:
            env = min(1.0, t / 0.005) * math.exp(-t * 14.0)
            f = f1
        elif t >= 0.16:
            tr = t - 0.16
            env = min(1.0, tr / 0.005) * math.exp(-tr * 10.5)
            f = f2
        else:
            env = 0.0
            f = f1
        tone = 0.70 * math.sin(two_pi * f * t) + 0.24 * math.sin(two_pi * (f * 2.0) * t)
        if nivel >= 3:
            tone += 0.22 * math.sin(two_pi * (f * 0.5) * t)
        val = tone * env * 0.55
        esq[i] = val
        dir_[i] = val * 0.97
    return esq, dir_


def sfx_tranca_porta():
    """Duplo clique metalico seco de chave/tranca girando na porta do quarto."""
    dur = 0.48
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(312)
    two_pi = 2.0 * math.pi
    cliques = [(0.04, 1.0, 1450.0), (0.22, 1.15, 1120.0)]
    lp = 0.0
    prev = 0.0
    for i in range(n):
        t = i / SR
        ruido = rng.uniform(-1.0, 1.0)
        lp += 0.32 * (ruido - lp)
        hp = lp - prev * 0.78
        prev = lp
        acc = 0.0
        for tc, gain, fm in cliques:
            dt = t - tc
            if 0.0 <= dt <= 0.16:
                env_m = math.exp(-dt * 42.0)
                env_b = math.exp(-dt * 18.0)
                metal = (math.sin(two_pi * fm * dt) + 0.55 * math.sin(two_pi * (fm * 1.63) * dt)) * env_m
                corpo = math.sin(two_pi * 165.0 * dt) * env_b * 0.7 + hp * env_m * 0.9
                acc += (metal * 0.5 + corpo * 0.65) * gain
        val = math.tanh(acc * 1.3) * 0.72
        esq[i] = val
        dir_[i] = val * 0.94
    return esq, dir_


def sfx_trava_janela(duracao: float = 1.40):
    """Janela batendo fechada + estalo metalico da trava + cortina pesada correndo no varao."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(313)
    two_pi = 2.0 * math.pi
    lp = 0.0
    lp2 = 0.0
    prev = 0.0

    for i in range(n):
        t = i / SR
        ruido = rng.uniform(-1.0, 1.0)
        lp += 0.28 * (ruido - lp)
        hp = lp - prev * 0.80
        prev = lp
        lp2 += 0.09 * (ruido - lp2)

        # 1. Folha da janela batendo fechada em t=0.12s
        batida = 0.0
        if 0.12 <= t <= 0.45:
            dt = t - 0.12
            f_b = 98.0 + 90.0 * math.exp(-dt * 18.0)
            batida = (math.sin(two_pi * f_b * dt) * 0.85 + hp * 0.75) * math.exp(-dt * 13.0) * 0.90

        # 2. Trava metalica clicando firme em t=0.50s
        trava = 0.0
        if 0.50 <= t <= 0.74:
            dt = t - 0.50
            trava = (
                0.55 * math.sin(two_pi * 1680.0 * dt)
                + 0.45 * math.sin(two_pi * 2410.0 * dt)
                + 0.60 * hp
            ) * math.exp(-dt * 34.0) * 0.82

        # 3. Cortina pesada correndo de 0.76s ate 1.34s (panning esquerda -> direita)
        cortina = 0.0
        pan_c = 0.5
        if 0.74 <= t <= 1.36:
            u = max(0.0, min(1.0, (t - 0.74) / 0.62))
            env_c = max(0.0, math.sin(math.pi * u)) ** 1.1
            anel = 0.16 * math.sin(two_pi * (760.0 + 140.0 * u) * t) * (0.5 + 0.5 * math.sin(two_pi * 24.0 * t))
            cortina = (lp2 * 1.15 + hp * 0.35 + anel) * env_c * 0.68
            pan_c = 0.20 + 0.60 * u

        base = math.tanh((batida + trava) * 1.2) * 0.85
        esq[i] = max(-0.96, min(0.96, base * 0.96 + cortina * (1.0 - pan_c * 0.5)))
        dir_[i] = max(-0.96, min(0.96, base + cortina * (0.5 + pan_c * 0.5)))
    return esq, dir_


def sfx_guarda_roupa(duracao: float = 1.60):
    """Rangido lento e arrepiante de porta de guarda-roupa abrindo no silencio do quarto."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(314)
    two_pi = 2.0 * math.pi
    fase1 = 0.0
    fase2 = 0.0
    fase_sub = 0.0
    lp = 0.0

    for i in range(n):
        t = i / SR
        p = t / duracao
        # Envelope cresce devagar, da dois solucos de dobradica enferrujada e morre no silencio
        env = min(1.0, t / 0.14) * min(1.0, (duracao - t) / 0.20)
        # Modulacao stick-slip (friccao irregular de dobradica de madeira/metal)
        stick_rate = 11.0 + 15.0 * (p ** 1.4) + 5.0 * math.sin(two_pi * 2.1 * t)
        stick = 0.38 + 0.62 * max(0.0, math.sin(two_pi * stick_rate * t))

        f_creak = 330.0 + 290.0 * math.sin(math.pi * (p ** 0.85)) + 42.0 * math.sin(two_pi * 6.5 * t)
        f_harm = f_creak * 2.04
        fase1 += two_pi * f_creak / SR
        fase2 += two_pi * f_harm / SR
        fase_sub += two_pi * (78.0 - 18.0 * p) / SR

        creak = (
            0.48 * math.sin(fase1)
            + 0.34 * math.sin(fase2)
            + 0.22 * math.tanh(2.4 * math.sin(fase1 * 1.5))
        ) * stick

        # Ressonancia de madeira oca + ar tenso no escuro
        lp += 0.06 * (rng.uniform(-1.0, 1.0) - lp)
        madeira = 0.28 * math.sin(fase_sub) + 0.42 * lp

        val = math.tanh((creak * 0.72 + madeira * 0.55) * 1.35) * env * 0.84
        # Levemente deslocado para a direita (onde esta o guarda-roupa na cena)
        esq[i] = val * 0.76
        dir_[i] = val * 1.04
    return esq, dir_


# ---------------- SFX COMPARTILHADOS & LEGADOS ----------------

def sfx_ping_gps(invertido: bool = False):
    dur = 0.38
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    f_a, f_b = (880.0, 587.33) if invertido else (783.99, 1046.50)
    for i in range(n):
        t = i / SR
        if t < 0.16:
            env = min(1.0, t / 0.006) * math.exp(-(t / 0.16) * 3.8)
            f = f_a
        elif t >= 0.17:
            tr = t - 0.17
            env = min(1.0, tr / 0.006) * math.exp(-(tr / 0.21) * 4.2)
            f = f_b
        else:
            env = 0.0
            f = f_a
        s = env * (0.68 * math.sin(two_pi * f * t) + 0.22 * math.sin(two_pi * (f * 2.0) * t)) * 0.58
        esq[i] = s
        dir_[i] = s * 0.96
    return esq, dir_


def sfx_alerta_emergencia():
    dur = 0.42
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    pulsos = [(0.0, 0.145), (0.215, 0.39)]
    two_pi = 2.0 * math.pi
    for i in range(n):
        t = i / SR
        env = 0.0
        for p0, p1 in pulsos:
            if p0 <= t <= p1:
                env = min(1.0, (t - p0) / 0.005) * min(1.0, (p1 - t) / 0.008)
                break
        if env <= 0.0:
            continue
        s = (
            0.46 * math.sin(two_pi * 853.0 * t)
            + 0.46 * math.sin(two_pi * 960.0 * t)
            + 0.14 * math.sin(two_pi * 1706.0 * t)
            + 0.12 * math.sin(two_pi * 145.0 * t)
        )
        s = math.tanh(s * 1.45) * 0.56 * env
        esq[i] = s
        dir_[i] = s * 0.96
    return esq, dir_


def sfx_whoosh_sombrio(duracao: float = 0.85):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(202)
    two_pi = 2.0 * math.pi
    lp = 0.0
    fase = 0.0
    for i in range(n):
        t = i / SR
        p = t / duracao
        env = math.sin(math.pi * p) ** 1.4
        lp += (0.04 + 0.18 * (1.0 - p)) * (rng.uniform(-1.0, 1.0) - lp)
        fase += two_pi * (135.0 * (1.0 - 0.65 * p)) / SR
        val = env * (0.45 * math.sin(fase) + 0.85 * lp) * 0.65
        esq[i] = val * (1.0 - 0.25 * p)
        dir_[i] = val * (0.75 + 0.25 * p)
    return esq, dir_


def sfx_apagao_farol(pitch_mult: float = 1.0):
    dur = 0.22
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    fase = 0.0
    for i in range(n):
        t = i / SR
        fase += two_pi * ((170.0 * pitch_mult) * math.exp(-t * 9.0) + 42.0) / SR
        v = math.sin(fase) * min(1.0, t / 0.006) * math.exp(-t * 14.0) * 0.52
        esq[i] = v
        dir_[i] = v * 0.95
    return esq, dir_


def sfx_freada(duracao: float = 1.15):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(505)
    two_pi = 2.0 * math.pi
    f1 = f2 = fa = lp = prev = 0.0
    for i in range(n):
        t = i / SR
        p = t / duracao
        env = min(1.0, t / 0.025) * min(1.0, (duracao - t) / 0.14)
        freq1 = 1920.0 - 760.0 * (p ** 0.75) + 45.0 * math.sin(two_pi * 17.0 * t)
        f1 += two_pi * freq1 / SR
        f2 += two_pi * (freq1 * 1.19 + 25.0 * math.sin(two_pi * 23.0 * t)) / SR
        chiado = (0.34 * math.sin(f1) + 0.24 * math.sin(f2)) * (0.75 + 0.25 * math.sin(two_pi * 13.0 * t))
        lp += 0.35 * (rng.uniform(-1.0, 1.0) - lp)
        hp = lp - prev * 0.72
        prev = lp
        fa += two_pi * (58.0 + 30.0 * math.exp(-t * 6.0)) / SR
        tranco = math.exp(-t * 9.0) * math.sin(fa) * 0.85
        val = math.tanh((chiado * 0.55 + hp * 0.42 + tranco) * 1.25) * env * 0.78
        esq[i] = val * 0.96
        dir_[i] = val
    return esq, dir_


def sfx_caminhao(duracao: float = 1.75):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(707)
    two_pi = 2.0 * math.pi
    fa = fb = fsub = lp = 0.0
    pico = duracao * 0.46
    for i in range(n):
        t = i / SR
        dt = (t - pico) / max(0.22, duracao * 0.24)
        doppler = 0.90 - 0.14 * math.tanh(dt * 1.45)
        fa += two_pi * (116.0 * doppler) / SR
        fb += two_pi * (146.5 * doppler) / SR
        fsub += two_pi * (58.0 * doppler) / SR
        env_b = min(1.0, t / 0.06) * math.exp(-((t - pico * 0.92) / (duracao * 0.42)) ** 2) * min(1.0, (duracao - t) / 0.16)
        buzina = math.tanh((0.52 * math.sin(fa) + 0.46 * math.sin(fb) + 0.26 * math.sin(fa * 2.0) + 0.34 * math.sin(fsub)) * 1.75) * env_b * 0.72
        env_ar = math.exp(-((t - pico * 1.04) / (duracao * 0.25)) ** 2)
        lp += (0.06 + 0.34 * env_ar) * (rng.uniform(-1.0, 1.0) - lp)
        mono = math.tanh((buzina + lp * env_ar * 1.05) * 1.15) * 0.92
        pan = max(0.0, min(1.0, 0.12 + 0.76 * (0.5 + 0.5 * math.tanh(dt * 1.3))))
        esq[i] = mono * math.cos(pan * math.pi * 0.5) * 1.25
        dir_[i] = mono * math.sin(pan * math.pi * 0.5) * 1.25
    return esq, dir_


def sfx_apagao():
    dur = 1.25
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(101)
    two_pi = 2.0 * math.pi
    f1 = f2 = lp = 0.0
    for i in range(n):
        t = i / SR
        estalo = 0.0
        if t < 0.04:
            lp += 0.25 * (rng.uniform(-1.0, 1.0) - lp)
            estalo = math.exp(-t / 0.009) * (0.75 * math.sin(two_pi * 115.0 * t) + 0.85 * lp)
        f1 += two_pi * (26.0 + 184.0 * math.exp(-t * 3.1)) / SR
        f2 += two_pi * (16.0 + 44.0 * math.exp(-t * 2.4)) / SR
        drop = min(1.0, t / 0.012) * math.exp(-t * 2.15) * (0.55 * math.sin(f1) + 0.40 * math.sin(f2))
        val = math.tanh((estalo + drop) * 1.15) * 0.78
        esq[i] = val
        dir_[i] = val * 0.98
    return esq, dir_


def sfx_batida_porta(intensidade: float = 1.0, desvio_pitch: float = 1.0, seed: int = 7):
    dur = 0.42
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(seed)
    two_pi = 2.0 * math.pi
    mono = [0.0] * n
    bp = prev = 0.0
    for i in range(n):
        t = i / SR
        bp += 0.22 * (rng.uniform(-1.0, 1.0) - bp)
        hp = bp - prev * 0.85
        prev = bp
        sweep = 1.0 + 0.22 * math.exp(-t / 0.012)
        v = (
            math.exp(-t / 0.007) * hp * 1.65
            + math.exp(-t / 0.095) * math.sin(two_pi * 118.0 * desvio_pitch * sweep * t) * 0.90
            + math.exp(-t / 0.055) * math.sin(two_pi * 252.0 * desvio_pitch * t + 0.3) * 0.55
        )
        mono[i] = math.tanh(v * 1.3) * min(1.0, t / 0.0025) * 0.88 * intensidade
    al, ar = int(0.034 * SR), int(0.068 * SR)
    for i in range(n):
        esq[i] = mono[i] + (mono[i - al] * 0.24 if i >= al else 0.0)
        dir_[i] = mono[i] * 0.94 + (mono[i - ar] * 0.14 if i >= ar else 0.0)
    return esq, dir_


def sfx_riser(duracao: float):
    dur = max(0.5, duracao)
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(303)
    two_pi = 2.0 * math.pi
    f1 = f2 = lp = 0.0
    for i in range(n):
        t = i / SR
        p = t / dur
        env = (p ** 2.1) * min(1.0, (dur - t) / 0.025)
        freq = 80.0 * (5.2 ** p)
        f1 += two_pi * freq / SR
        f2 += two_pi * (freq * 1.498) / SR
        lp += (0.03 + 0.32 * (p ** 2)) * (rng.uniform(-1.0, 1.0) - lp)
        s = env * (0.72 + 0.28 * math.sin(two_pi * (2.0 + 7.0 * p) * t)) * (0.42 * math.sin(f1) + 0.28 * math.sin(f2) + 0.55 * lp)
        esq[i] = s * 0.70
        dir_[i] = s * 0.74
    return esq, dir_


def sfx_sub_boom(duracao_max: float):
    dur = max(0.5, min(2.0, duracao_max))
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(909)
    two_pi = 2.0 * math.pi
    fase = lp = 0.0
    for i in range(n):
        t = i / SR
        fase += two_pi * (33.0 + 68.0 * math.exp(-t * 5.2)) / SR
        lp += 0.08 * (rng.uniform(-1.0, 1.0) - lp)
        val = math.tanh(
            (math.exp(-t * 1.65) * math.sin(fase) * 0.95 + math.exp(-t / 0.06) * math.sin(two_pi * 168.0 * t) * 0.45 + math.exp(-t * 2.6) * lp * 0.45) * 1.25
        ) * min(1.0, t / 0.006) * min(1.0, (dur - t) / 0.055) * 0.86
        esq[i] = val
        dir_[i] = val * 0.97
    return esq, dir_


def sfx_cta_pop():
    dur = 0.18
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    fase = 0.0
    for i in range(n):
        t = i / SR
        fase += two_pi * (340.0 + 520.0 * math.exp(-t * 22.0)) / SR
        s = math.sin(fase) * min(1.0, t / 0.004) * math.exp(-t * 24.0) * 0.45
        esq[i] = s
        dir_[i] = s
    return esq, dir_


def sintetizar_sfx(duracao: float, ev: dict):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    if _eh_video_03(ev):
        # 1. Celular vibrando na cama + Pix 1 (chime bancario limpo)
        if "vibra_cama" in ev:
            vl, vr = sfx_vibracao_celular(0.46, 0.90)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["vibra_cama"]) - 0.04), vl, vr, 0.82)
        if "pix_1" in ev:
            pl, pr = sfx_pix_notificacao(1)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pix_1"]) - 0.04), pl, pr, 0.82)

        # 2. Sub-hit seco ao ler "Nao acende a luz"
        if "nao_acende" in ev:
            bl, br = sfx_sub_boom(0.85)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["nao_acende"]) - 0.05), bl, br, 0.62)

        # 3. Pix 2 (vibracao + chime sombrio)
        if "pix_2" in ev:
            vl, vr = sfx_vibracao_celular(0.42, 0.95)
            pl, pr = sfx_pix_notificacao(2)
            t2 = max(0.0, float(ev["pix_2"]) - 0.05)
            _misturar_trecho(esq, dir_, t2, vl, vr, 0.72)
            _misturar_trecho(esq, dir_, t2 + 0.10, pl, pr, 0.82)

        # 4. Marina tranca a porta do quarto
        if "tranca_porta" in ev:
            tl, tr = sfx_tranca_porta()
            _misturar_trecho(esq, dir_, float(ev["tranca_porta"]) + 0.15, tl, tr, 0.86)

        # 5. Pix 3 (pulso vermelho: vibracao forte + chime tenso + sub hit)
        if "pix_3" in ev:
            vl, vr = sfx_vibracao_celular(0.44, 1.05)
            pl, pr = sfx_pix_notificacao(3)
            t3 = max(0.0, float(ev["pix_3"]) - 0.04)
            _misturar_trecho(esq, dir_, t3, vl, vr, 0.80)
            _misturar_trecho(esq, dir_, t3 + 0.08, pl, pr, 0.88)

        # 6. Bloco SFX puro: trava da janela + cortina fechando (1.4s)
        if "trava_janela" in ev:
            dur_j = float(ev.get("trava_janela_duracao", 1.4))
            jl, jr = sfx_trava_janela(dur_j)
            _misturar_trecho(esq, dir_, float(ev["trava_janela"]), jl, jr, 1.0)

        # 7. Pix 4 (ultima vibracao + alerta de tritono)
        if "hora_0314" in ev:
            vl, vr = sfx_vibracao_celular(0.50, 1.15)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["hora_0314"]) + 0.10), vl, vr, 0.88)
        if "pix_4" in ev:
            pl, pr = sfx_pix_notificacao(4)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pix_4"]) - 0.04), pl, pr, 0.90)

        # 8. Plot Twist ("Eu nao estava la fora") -> sub-bass boom + corte seco do drone
        if "plot_twist" in ev:
            t_tw = float(ev["plot_twist"])
            t_gr = float(ev.get("guarda_roupa", t_tw + 1.5))
            bm_l, bm_r = sfx_sub_boom(max(0.65, min(1.5, t_gr - t_tw + 0.05)))
            _misturar_trecho(esq, dir_, t_tw, bm_l, bm_r, 0.94)

        # 9. Bloco SFX puro: porta do guarda-roupa rangendo e abrindo devagar (1.6s)
        if "guarda_roupa" in ev:
            dur_g = float(ev.get("guarda_roupa_duracao", 1.6))
            gl, gr_ = sfx_guarda_roupa(dur_g)
            _misturar_trecho(esq, dir_, float(ev["guarda_roupa"]), gl, gr_, 1.0)

        # 10. Pop limpo na CTA "Comente EU QUERO"
        if "cta_acao" in ev:
            cl, cr = sfx_cta_pop()
            _misturar_trecho(esq, dir_, float(ev["cta_acao"]), cl, cr, 0.72)

        return esq, dir_

    if _eh_video_02(ev):
        ping_l, ping_r = sfx_ping_gps(invertido=False)
        if "gancho" in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev["gancho"]) + 0.15), ping_l, ping_r, 0.38)
        if "gps_rota" in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev["gps_rota"]) - 0.04), ping_l, ping_r, 0.85)
        if "rua_escura" in ev:
            wl, wr = sfx_whoosh_sombrio(0.90)
            _misturar_trecho(esq, dir_, float(ev["rua_escura"]), wl, wr, 0.72)
        if "retrovisor" in ev:
            t_ret = float(ev["retrovisor"])
            for idx_f, (off, pm) in enumerate([(0.30, 1.05), (1.05, 0.92), (1.80, 0.78)]):
                fl, fr = sfx_apagao_farol(pm)
                _misturar_trecho(esq, dir_, t_ret + off, fl, fr, 0.60 + idx_f * 0.08)
        if "destino_acidente" in ev:
            al, ar = sfx_alerta_emergencia()
            _misturar_trecho(esq, dir_, max(0.0, float(ev["destino_acidente"]) - 0.04), al, ar, 0.76)
        if "freio" in ev:
            t_fr = float(ev["freio"])
            t_cam = float(ev.get("caminhao", t_fr + 1.1))
            fr_l, fr_r = sfx_freada(max(0.65, min(1.25, (t_cam - t_fr) + 0.18)))
            _misturar_trecho(esq, dir_, max(0.0, t_fr - 0.05), fr_l, fr_r, 0.88)
        if "caminhao" in ev:
            cl, cr = sfx_caminhao(float(ev.get("caminhao_duracao", 1.75)))
            _misturar_trecho(esq, dir_, float(ev["caminhao"]), cl, cr, 1.0)
        if "sussurro" in ev and "plot_twist" in ev:
            dur_r = (float(ev["plot_twist"]) - 0.03) - float(ev["sussurro"])
            if dur_r >= 0.45:
                rl, rr = sfx_riser(dur_r)
                _misturar_trecho(esq, dir_, float(ev["sussurro"]), rl, rr, 0.65)
        if "plot_twist" in ev:
            t_tw = float(ev["plot_twist"])
            t_cta = float(ev.get("cta", t_tw + 2.2))
            bm_l, bm_r = sfx_sub_boom(max(0.6, min(1.8, (t_cta - t_tw) * 0.75)))
            _misturar_trecho(esq, dir_, t_tw, bm_l, bm_r, 0.90)
            pi_l, pi_r = sfx_ping_gps(invertido=True)
            _misturar_trecho(esq, dir_, t_tw + 0.06, pi_l, pi_r, 0.65)
        if "cta_acao" in ev:
            pl, pr = sfx_cta_pop()
            _misturar_trecho(esq, dir_, float(ev["cta_acao"]), pl, pr, 0.72)
        return esq, dir_

    # Legado Video 01
    alerta_l, alerta_r = sfx_alerta_emergencia()
    for chave in ("alerta_1", "alerta_2", "alerta_3"):
        if chave in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev[chave]) - 0.06), alerta_l, alerta_r, 0.78)
    if "apagao_00" in ev:
        ap_l, ap_r = sfx_apagao()
        _misturar_trecho(esq, dir_, float(ev["apagao_00"]), ap_l, ap_r, 0.85)
    if "batidas_porta" in ev:
        base_bat = float(ev["batidas_porta"])
        for offset, inten, pitch, seed in [(0.00, 0.90, 1.00, 11), (0.65, 0.96, 0.98, 22), (1.30, 1.06, 0.95, 33)]:
            bl, br = sfx_batida_porta(intensidade=inten, desvio_pitch=pitch, seed=seed)
            _misturar_trecho(esq, dir_, base_bat + offset, bl, br, 1.0)
    if "foto_revela" in ev and "big_face" in ev:
        t_foto, t_big = float(ev["foto_revela"]), float(ev["big_face"])
        t_twist = float(ev.get("plot_twist", t_big + 1.8))
        inicio_riser = max(t_foto, t_big - 2.4)
        dur_riser = (t_big - 0.03) - inicio_riser
        if dur_riser >= 0.4:
            rl, rr = sfx_riser(dur_riser)
            _misturar_trecho(esq, dir_, inicio_riser, rl, rr, 0.72)
        bm_l, bm_r = sfx_sub_boom(max(0.55, (t_twist + 0.04) - t_big))
        _misturar_trecho(esq, dir_, t_big, bm_l, bm_r, 0.92)
    return esq, dir_


def medir_loudnorm(wav_entrada: Path) -> dict:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(wav_entrada),
        "-af",
        "loudnorm=I=-14:TP=-1.5:LRA=7:print_format=json",
        "-f",
        "null",
        "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    m = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", res.stderr)
    if not m:
        raise RuntimeError(f"Nao foi possivel ler estatisticas loudnorm:\n{res.stderr[-600:]}")
    return json.loads(m.group(0))


def mixar_e_masterizar(
    voz_mp3: Path,
    drone_wav: Path,
    sfx_wav: Path,
    pre_mix_wav: Path,
    destino_mp3: Path,
) -> dict:
    """Mistura voz + drone (com ducking) + SFX e masteriza em 2 passagens a -14 LUFS."""
    filtro_mix = (
        "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        "highpass=f=75,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=10:release=120,"
        "asplit=3[v_main][v_sc_drone][v_sc_sfx];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        "volume=0.58[drone_in];"
        "[drone_in][v_sc_drone]sidechaincompress=threshold=0.02:ratio=4.5:attack=25:release=320:makeup=1[drone_duck];"
        "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        "volume=0.88[sfx_in];"
        "[sfx_in][v_sc_sfx]sidechaincompress=threshold=0.045:ratio=2.0:attack=12:release=160:makeup=1[sfx_duck];"
        "[v_main][drone_duck][sfx_duck]amix=inputs=3:duration=first:dropout_transition=0:normalize=0"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(voz_mp3),
            "-i",
            str(drone_wav),
            "-i",
            str(sfx_wav),
            "-filter_complex",
            filtro_mix,
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(pre_mix_wav),
        ],
        check=True,
    )

    stats = medir_loudnorm(pre_mix_wav)
    filtro_master = (
        "loudnorm=I=-14:TP=-1.5:LRA=7:linear=true:"
        f"measured_I={stats['input_i']}:"
        f"measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:"
        f"measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(pre_mix_wav),
            "-af",
            filtro_master,
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(destino_mp3),
        ],
        check=True,
    )
    return medir_loudnorm(destino_mp3)


def main() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")
    if not VOZ_LIMPA_MP3.is_file():
        raise SystemExit(f"Arquivo nao encontrado: {VOZ_LIMPA_MP3}. Rode audio/gerar_narracao.py primeiro.")

    # Trava blindada contra audio velho / cache de outro video / ausencia da CTA
    validacao = validar_artefatos_audio(PASTA_AUDIO)
    eventos = validacao["eventos"]
    carimbo = validacao["carimbo"]
    duracao = max(medir_duracao_ffprobe(VOZ_LIMPA_MP3), float(eventos.get("duracao_total", 0.0)))
    backend = "numpy" if np is not None else "stdlib"
    perfil = (
        "Video 03 (O Pix de 1 Centavo)"
        if _eh_video_03(eventos)
        else ("Video 02 (GPS / Rota recalculada)" if _eh_video_02(eventos) else "Video 01 (legado)")
    )
    print(
        f"Integridade OK (Video {carimbo['video_id']:02d}, sha256={carimbo['roteiro_sha256'][:12]}). "
        f"Sintetizando cama sonora e SFX [{perfil}] ({duracao:.3f}s, backend={backend})..."
    )

    with tempfile.TemporaryDirectory(prefix="sfx-v3-") as tmp:
        tmp_dir = Path(tmp)
        drone_wav = tmp_dir / "cama_drone.wav"
        sfx_wav = tmp_dir / "sfx_eventos.wav"
        pre_mix_wav = tmp_dir / "mix_pre.wav"

        d_l, d_r = sintetizar_cama_drone(duracao, eventos)
        _gravar_wav_estereo(drone_wav, d_l, d_r)

        s_l, s_r = sintetizar_sfx(duracao, eventos)
        _gravar_wav_estereo(sfx_wav, s_l, s_r)

        final_stats = mixar_e_masterizar(VOZ_LIMPA_MP3, drone_wav, sfx_wav, pre_mix_wav, MIX_FINAL_MP3)

    shutil.copy2(MIX_FINAL_MP3, NARRACAO_MP3)
    dur_final = medir_duracao_ffprobe(MIX_FINAL_MP3)
    print(
        f"Masterizado {MIX_FINAL_MP3.name} (e copiado para {NARRACAO_MP3.name}): "
        f"{dur_final:.3f}s | {final_stats['input_i']} LUFS | TP {final_stats['input_tp']} dBTP"
    )


if __name__ == "__main__":
    main()
