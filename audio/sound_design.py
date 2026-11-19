"""Estacao 2 (v2): sintetiza cama sonora + SFX de suspense e masteriza audio/mix_final.mp3.

Uso (na raiz do repositorio, apos audio/gerar_narracao.py):
    python3 audio/sound_design.py

100% Python padrao (acelerado por numpy quando disponivel) + ffmpeg, sem downloads.
Le audio/voz_limpa.mp3 e audio/eventos.json, gera:
- cama continua (drone grave evolutivo com corte subito no plot_twist)
- SFX sincronizados (bipes EAS nos alertas, apagao eletrico, 3 batidas em madeira oca,
  riser crescente + sub-bass boom no big_face)
- mix final com ducking controlado pela voz e masterizacao em 2 passagens a -14 LUFS
  em audio/mix_final.mp3 (copiado tambem para audio/narracao.mp3).
"""

import json
import math
import random
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

RAIZ = Path(__file__).resolve().parent.parent
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


def _envelope_drone_em_t(t: float, ev: dict) -> float:
    """Curva de tensao do drone com queda no apagao, respiro nas batidas e corte subito no twist."""
    h21 = float(ev.get("hora_21", 10.0))
    ap00 = float(ev.get("apagao_00", 19.0))
    h03 = float(ev.get("hora_03", 26.0))
    bat = float(ev.get("batidas_porta", 27.5))
    bat_d = float(ev.get("batidas_porta_duracao", 2.1))
    sil = float(ev.get("silencio", 34.0))
    foto = float(ev.get("foto_revela", 35.5))
    big = float(ev.get("big_face", 38.5))
    twist = float(ev.get("plot_twist", 40.5))

    # Corte subito no momento exato do plot twist.
    if t >= twist + 0.045:
        return 0.0
    corte_twist = 1.0 if t < twist else max(0.0, 1.0 - (t - twist) / 0.045)

    if t < 0.4:
        base = 0.14 * (t / 0.4)
    elif t < h21:
        base = 0.14 + 0.04 * (t / max(0.1, h21))
    elif t < ap00:
        k = (t - h21) / max(0.1, ap00 - h21)
        base = 0.18 + 0.07 * k
    elif t < ap00 + 0.45:
        base = 0.08
    elif t < h03:
        k = (t - (ap00 + 0.45)) / max(0.1, h03 - (ap00 + 0.45))
        base = 0.20 + 0.11 * k
    elif t < sil:
        base = 0.31
    elif t < foto:
        base = 0.05
    elif t < big:
        k = (t - foto) / max(0.1, big - foto)
        base = 0.16 + 0.24 * k
    else:
        base = 0.34

    # Abaixa suavemente durante o bloco das 3 batidas para aumentar o desconforto.
    if bat - 0.15 <= t <= bat + bat_d + 0.15:
        base *= 0.42

    return base * corte_twist


def sintetizar_cama_drone(duracao: float, ev: dict):
    """Sintetiza cama continua de suspense (sub-bass + batimento sombrio + ar grave filtrado)."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    # Calcula envelope em blocos de 128 amostras e interpola para ficar rapido mesmo sem numpy.
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

        lfo = 0.82 + 0.18 * np.sin(2.0 * np.pi * 0.23 * t)
        sub_l = 0.55 * np.sin(2.0 * np.pi * 46.25 * t) + 0.24 * np.sin(2.0 * np.pi * 65.41 * t + 0.4)
        sub_r = 0.55 * np.sin(2.0 * np.pi * 46.60 * t + 0.7) + 0.24 * np.sin(2.0 * np.pi * 65.10 * t)
        harm = 0.11 * np.sin(2.0 * np.pi * 110.0 * t + 0.8 * np.sin(2.0 * np.pi * 0.17 * t))

        rng = np.random.default_rng(42)
        ruido = rng.uniform(-1.0, 1.0, n)
        # Media movel simples como passa-baixas sombrio (~200 Hz).
        k_lp = 95
        cs = np.cumsum(np.insert(ruido, 0, 0.0))
        ar = (cs[k_lp:] - cs[:-k_lp]) / k_lp
        ar = np.pad(ar, (0, n - len(ar))) * 1.4

        esq[:] = env * lfo * (sub_l + harm + 0.28 * ar)
        dir_[:] = env * lfo * (sub_r + harm * 0.92 - 0.24 * ar)
        return esq, dir_

    rng = random.Random(42)
    lp = 0.0
    alpha = 0.025
    two_pi = 2.0 * math.pi
    for i in range(n):
        t = i / SR
        bi = i // passo
        frac = (i - bi * passo) / passo
        env = pontos[bi] * (1.0 - frac) + pontos[bi + 1] * frac
        if env <= 1e-6:
            continue
        lfo = 0.82 + 0.18 * math.sin(two_pi * 0.23 * t)
        lp += alpha * (rng.uniform(-1.0, 1.0) - lp)
        harm = 0.11 * math.sin(two_pi * 110.0 * t + 0.8 * math.sin(two_pi * 0.17 * t))
        sub_l = 0.55 * math.sin(two_pi * 46.25 * t) + 0.24 * math.sin(two_pi * 65.41 * t + 0.4)
        sub_r = 0.55 * math.sin(two_pi * 46.60 * t + 0.7) + 0.24 * math.sin(two_pi * 65.10 * t)
        esq[i] = env * lfo * (sub_l + harm + 0.8 * lp)
        dir_[i] = env * lfo * (sub_r + harm * 0.92 - 0.7 * lp)
    return esq, dir_


def sfx_alerta_emergencia():
    """Bipe duplo agudo de alerta de emergencia de celular (estilo EAS / Defesa Civil)."""
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
                a = min(1.0, (t - p0) / 0.005)
                r = min(1.0, (p1 - t) / 0.008)
                env = a * r
                break
        if env <= 0.0:
            continue
        # Par classico WEA/EAS (853 Hz + 960 Hz) + brilho de alto-falante de celular + vibracao 145 Hz.
        s = (
            0.46 * math.sin(two_pi * 853.0 * t)
            + 0.46 * math.sin(two_pi * 960.0 * t)
            + 0.14 * math.sin(two_pi * 1706.0 * t)
            + 0.12 * math.sin(two_pi * 145.0 * t)
        )
        # Saturacao suave para timbre de alerta de celular.
        s = math.tanh(s * 1.45) * 0.58 * env
        esq[i] = s
        dir_[i] = s * 0.96
    return esq, dir_


def sfx_apagao():
    """Disjuntor desligando seguido de queda eletrica grave (pitch drop)."""
    dur = 1.25
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(101)
    two_pi = 2.0 * math.pi
    fase1 = 0.0
    fase2 = 0.0
    lp = 0.0

    for i in range(n):
        t = i / SR
        # Estalo mecanico do disjuntor nos primeiros 35ms.
        estalo = 0.0
        if t < 0.04:
            e = math.exp(-t / 0.009)
            lp += 0.25 * (rng.uniform(-1.0, 1.0) - lp)
            estalo = e * (0.75 * math.sin(two_pi * 115.0 * t) + 0.85 * lp)

        # Pitch drop eletrico (210 Hz -> 26 Hz e 60 Hz -> 16 Hz).
        f1 = 26.0 + 184.0 * math.exp(-t * 3.1)
        f2 = 16.0 + 44.0 * math.exp(-t * 2.4)
        fase1 += two_pi * f1 / SR
        fase2 += two_pi * f2 / SR
        env_drop = min(1.0, t / 0.012) * math.exp(-t * 2.15)
        drop = env_drop * (
            0.55 * math.sin(fase1)
            + 0.40 * math.sin(fase2)
            + 0.16 * math.tanh(2.5 * math.sin(fase1 * 2.0))
        )

        val = math.tanh((estalo + drop) * 1.15) * 0.78
        esq[i] = val
        dir_[i] = val * 0.98
    return esq, dir_


def sfx_batida_porta(intensidade: float = 1.0, desvio_pitch: float = 1.0, seed: int = 7):
    """Uma batida seca e grave em porta de madeira oca com reflexao curta de corredor."""
    dur = 0.42
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(seed)
    two_pi = 2.0 * math.pi

    f_corpo = 118.0 * desvio_pitch
    f_oca = 252.0 * desvio_pitch
    f_ataque = 490.0 * desvio_pitch
    mono = [0.0] * n
    bp = 0.0
    hp = 0.0
    prev = 0.0

    for i in range(n):
        t = i / SR
        ataque_env = min(1.0, t / 0.0025)
        ruido = rng.uniform(-1.0, 1.0)
        bp += 0.22 * (ruido - bp)
        hp = bp - prev * 0.85
        prev = bp
        transiente = math.exp(-t / 0.007) * hp * 1.65

        # Queda rapida de pitch no impacto inicial da madeira.
        sweep = 1.0 + 0.22 * math.exp(-t / 0.012)
        corpo = math.exp(-t / 0.095) * math.sin(two_pi * f_corpo * sweep * t) * 0.90
        cavidade = math.exp(-t / 0.055) * math.sin(two_pi * f_oca * t + 0.3) * 0.55
        toque = math.exp(-t / 0.024) * math.sin(two_pi * f_ataque * t) * 0.30

        mono[i] = math.tanh((transiente + corpo + cavidade + toque) * 1.3) * ataque_env * 0.88 * intensidade

    # Reflexoes curtas de corredor fechado (+34ms esquerda, +68ms direita).
    atraso_l = int(0.034 * SR)
    atraso_r = int(0.068 * SR)
    for i in range(n):
        eco_l = mono[i - atraso_l] * 0.24 if i >= atraso_l else 0.0
        eco_r = mono[i - atraso_r] * 0.14 if i >= atraso_r else 0.0
        esq[i] = mono[i] + eco_l
        dir_[i] = mono[i] * 0.94 + eco_r
    return esq, dir_


def sfx_riser(duracao: float):
    """Riser tenso crescente ate o instante anterior ao impacto do big_face."""
    dur = max(0.5, duracao)
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(303)
    two_pi = 2.0 * math.pi
    fase1 = 0.0
    fase2 = 0.0
    lp = 0.0

    for i in range(n):
        t = i / SR
        p = t / dur
        env = (p ** 2.1) * min(1.0, (dur - t) / 0.025)
        f1 = 80.0 * (5.2 ** p)
        f2 = f1 * 1.498  # quinta/tensao sombria
        fase1 += two_pi * f1 / SR
        fase2 += two_pi * f2 / SR

        lp_alpha = 0.03 + 0.32 * (p ** 2)
        lp += lp_alpha * (rng.uniform(-1.0, 1.0) - lp)
        pulso = 0.72 + 0.28 * math.sin(two_pi * (2.0 + 7.0 * p) * t)

        s = env * pulso * (0.42 * math.sin(fase1) + 0.28 * math.sin(fase2) + 0.55 * lp)
        esq[i] = s * 0.72
        dir_[i] = s * 0.76
    return esq, dir_


def sfx_sub_boom(duracao_max: float):
    """Impacto grave (sub-bass boom) no big_face, cortado limpo ao chegar no plot_twist."""
    dur = max(0.5, min(2.2, duracao_max))
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(909)
    two_pi = 2.0 * math.pi
    fase = 0.0
    lp = 0.0

    for i in range(n):
        t = i / SR
        f_sub = 33.0 + 68.0 * math.exp(-t * 5.2)
        fase += two_pi * f_sub / SR
        ataque = min(1.0, t / 0.006)
        corte_fim = min(1.0, (dur - t) / 0.055)
        sub = math.exp(-t * 1.65) * math.sin(fase) * 0.95
        punch = math.exp(-t / 0.06) * math.sin(two_pi * 168.0 * t) * 0.45
        lp += 0.08 * (rng.uniform(-1.0, 1.0) - lp)
        cauda = math.exp(-t * 2.6) * lp * 0.45

        val = math.tanh((sub + punch + cauda) * 1.25) * ataque * corte_fim * 0.88
        esq[i] = val
        dir_[i] = val * 0.97
    return esq, dir_


def sintetizar_sfx(duracao: float, ev: dict):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    # 1. Alertas de emergencia de celular (bipe duplo EAS)
    alerta_l, alerta_r = sfx_alerta_emergencia()
    for chave in ("alerta_1", "alerta_2", "alerta_3"):
        if chave in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev[chave]) - 0.06), alerta_l, alerta_r, 0.78)

    # 2. Queda de energia as 00:00
    if "apagao_00" in ev:
        ap_l, ap_r = sfx_apagao()
        _misturar_trecho(esq, dir_, float(ev["apagao_00"]), ap_l, ap_r, 0.85)

    # 3. Tres batidas secas em porta de madeira oca (0.0s, 0.65s, 1.30s)
    if "batidas_porta" in ev:
        base_bat = float(ev["batidas_porta"])
        specs = [(0.00, 0.90, 1.00, 11), (0.65, 0.96, 0.98, 22), (1.30, 1.06, 0.95, 33)]
        for offset, inten, pitch, seed in specs:
            bl, br = sfx_batida_porta(intensidade=inten, desvio_pitch=pitch, seed=seed)
            _misturar_trecho(esq, dir_, base_bat + offset, bl, br, 1.0)

    # 4. Riser tenso (foto_revela -> big_face) + sub-bass boom no big_face + corte no plot_twist
    if "foto_revela" in ev and "big_face" in ev:
        t_foto = float(ev["foto_revela"])
        t_big = float(ev["big_face"])
        t_twist = float(ev.get("plot_twist", t_big + 1.8))
        inicio_riser = max(t_foto, t_big - 2.4)
        dur_riser = (t_big - 0.03) - inicio_riser
        if dur_riser >= 0.4:
            rl, rr = sfx_riser(dur_riser)
            _misturar_trecho(esq, dir_, inicio_riser, rl, rr, 0.72)

        dur_boom = max(0.55, (t_twist + 0.04) - t_big)
        bm_l, bm_r = sfx_sub_boom(dur_boom)
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
    if not EVENTOS_JSON.is_file():
        raise SystemExit(f"Arquivo nao encontrado: {EVENTOS_JSON}. Rode audio/gerar_narracao.py primeiro.")

    eventos = json.loads(EVENTOS_JSON.read_text(encoding="utf-8"))
    duracao = max(medir_duracao_ffprobe(VOZ_LIMPA_MP3), float(eventos.get("duracao_total", 0.0)))
    backend = "numpy" if np is not None else "stdlib"
    print(f"Sintetizando cama sonora e SFX ({duracao:.3f}s, backend={backend})...")

    with tempfile.TemporaryDirectory(prefix="sfx-v2-") as tmp:
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
