"""Estacao 2 (v4): biblioteca hibrida de SFX reais (assets/sfx/) + sintese acustica HD e master -14 LUFS.

Uso (na raiz do repositorio, apos audio/gerar_narracao.py):
    python3 audio/sound_design.py

Recursos V4 (skills biblioteca-sfx-reais + audio-sound-design-suspense + video-director):
- Trava blindada contra audio velho via pipeline/historico.py (video_id, titulo, roteiro_sha256, CTA).
- Carrega automaticamente SFX reais (.wav/.flac/.mp3/.ogg) de assets/sfx/ quando existirem,
  aplicando fade-in (5ms), fade-out (15ms) e ganho configurado em assets/sfx/catalogo.json.
- Fallback procedural acustico de alta fidelidade (filtros espectrais, impulsos stick-slip,
  formantes vocais e reflexoes precoces de sala) caso o arquivo real nao esteja presente.
- Suporta Video 04 ('A Baba Eletronica'), Video 03 ('O Pix de 1 Centavo'), Video 02 e Video 01.
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
PASTA_SFX = RAIZ / "assets" / "sfx"
CATALOGO_SFX_JSON = PASTA_SFX / "catalogo.json"
VOZ_LIMPA_MP3 = PASTA_AUDIO / "voz_limpa.mp3"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"
MIX_FINAL_MP3 = PASTA_AUDIO / "mix_final.mp3"
NARRACAO_MP3 = PASTA_AUDIO / "narracao.mp3"

SR = 44100
EXTENSOES_SFX = (".wav", ".flac", ".mp3", ".ogg")


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
        esq[dst_ini : dst_ini + comp] += np.asarray(s_esq[src_ini : src_ini + comp], dtype=np.float64) * ganho
        dir_[dst_ini : dst_ini + comp] += np.asarray(s_dir[src_ini : src_ini + comp], dtype=np.float64) * ganho
    else:
        for k in range(comp):
            esq[dst_ini + k] += s_esq[src_ini + k] * ganho
            dir_[dst_ini + k] += s_dir[src_ini + k] * ganho


# ============================================================
# CARREGADOR HIBRIDO DE SFX REAIS (assets/sfx/) + CATALOGO
# ============================================================

def _carregar_ganhos_catalogo() -> dict[str, float]:
    ganhos: dict[str, float] = {}
    if not CATALOGO_SFX_JSON.is_file():
        return ganhos
    try:
        dados = json.loads(CATALOGO_SFX_JSON.read_text(encoding="utf-8"))
        for item in dados.get("efeitos", []):
            nome = str(item.get("nome", "")).strip()
            if nome and item.get("ganho_db") is not None:
                ganhos[nome] = 10.0 ** (float(item["ganho_db"]) / 20.0)
    except Exception:
        pass
    return ganhos


def _localizar_sfx_real(nome: str) -> Path | None:
    if not PASTA_SFX.is_dir():
        return None
    for ext in EXTENSOES_SFX:
        cand = PASTA_SFX / f"{nome}{ext}"
        if cand.is_file() and cand.stat().st_size > 0:
            return cand
    return None


def _aplicar_fades_e_corte(esq, dir_, duracao_max: float | None = None, ganho_cat: float = 1.0):
    n = len(esq)
    if duracao_max is not None and duracao_max > 0.05:
        n_lim = min(n, int(round(duracao_max * SR)))
        esq = esq[:n_lim]
        dir_ = dir_[:n_lim]
        n = n_lim
    if n == 0:
        return esq, dir_

    fade_in = min(n // 4, int(round(0.005 * SR)))
    fade_out = min(n // 3, int(round(0.015 * SR)))
    if np is not None:
        esq = np.asarray(esq, dtype=np.float64).copy() * ganho_cat
        dir_ = np.asarray(dir_, dtype=np.float64).copy() * ganho_cat
        if fade_in > 1:
            rampa = np.linspace(0.0, 1.0, fade_in, dtype=np.float64)
            esq[:fade_in] *= rampa
            dir_[:fade_in] *= rampa
        if fade_out > 1:
            rampa = np.linspace(1.0, 0.0, fade_out, dtype=np.float64)
            esq[-fade_out:] *= rampa
            dir_[-fade_out:] *= rampa
        return np.clip(esq, -0.98, 0.98), np.clip(dir_, -0.98, 0.98)

    esq_out = array("d", (v * ganho_cat for v in esq))
    dir_out = array("d", (v * ganho_cat for v in dir_))
    for i in range(fade_in):
        f = i / max(1, fade_in - 1)
        esq_out[i] *= f
        dir_out[i] *= f
    for i in range(fade_out):
        f = 1.0 - (i / max(1, fade_out - 1))
        idx = n - fade_out + i
        esq_out[idx] *= f
        dir_out[idx] *= f
    return esq_out, dir_out


def carregar_sfx_real(nome: str, duracao_max: float | None = None, ganhos_cat: dict[str, float] | None = None):
    """Carrega um arquivo real (.wav/.flac/.mp3/.ogg) de assets/sfx/ em stereo 44.1kHz float64."""
    caminho = _localizar_sfx_real(nome)
    if caminho is None:
        return None, None

    bruto_pcm: bytes | None = None
    if caminho.suffix.lower() == ".wav":
        try:
            with wave.open(str(caminho), "rb") as wf:
                if wf.getframerate() == SR and wf.getnchannels() == 2 and wf.getsampwidth() == 2:
                    bruto_pcm = wf.readframes(wf.getnframes())
        except Exception:
            bruto_pcm = None

    if bruto_pcm is None:
        cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(caminho),
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-f",
            "s16le",
            "pipe:1",
        ]
        res = subprocess.run(cmd, capture_output=True, check=True)
        bruto_pcm = res.stdout

    if not bruto_pcm:
        return None, None

    if np is not None:
        inter = np.frombuffer(bruto_pcm, dtype=np.int16).astype(np.float64) / 32768.0
        n_frames = inter.size // 2
        esq = inter[0 : n_frames * 2 : 2]
        dir_ = inter[1 : n_frames * 2 : 2]
    else:
        amostras = array("h")
        amostras.frombytes(bruto_pcm)
        n_frames = len(amostras) // 2
        esq = array("d", (amostras[2 * i] / 32768.0 for i in range(n_frames)))
        dir_ = array("d", (amostras[2 * i + 1] / 32768.0 for i in range(n_frames)))

    ganho_cat = (ganhos_cat or {}).get(nome, 1.0)
    esq, dir_ = _aplicar_fades_e_corte(esq, dir_, duracao_max=duracao_max, ganho_cat=ganho_cat)
    return (esq, dir_), caminho.name


def obter_sfx(
    nome: str,
    gerador_fallback,
    duracao_max: float | None = None,
    ganhos_cat: dict[str, float] | None = None,
    relatorio: dict[str, str] | None = None,
):
    """Usa arquivo real em assets/sfx/ quando existir; senao executa o fallback acustico HD."""
    par, arq_nome = carregar_sfx_real(nome, duracao_max=duracao_max, ganhos_cat=ganhos_cat)
    if par is not None and arq_nome is not None:
        if relatorio is not None:
            relatorio[nome] = f"REAL ({arq_nome})"
        return par
    if relatorio is not None and nome not in relatorio:
        relatorio[nome] = "fallback procedural HD"
    return gerador_fallback()


# ============================================================
# NUCLEO DSP ORGANICO (FILTROS ESPECTRAIS, PINK NOISE, SALA)
# ============================================================

def _ruido_rosa_np(n: int, seed: int):
    rng = np.random.default_rng(seed)
    branco = rng.standard_normal(n)
    spec = np.fft.rfft(branco)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    escala = 1.0 / np.maximum(freqs, 25.0) ** 0.5
    escala[0] = 0.0
    rosa = np.fft.irfft(spec * escala, n=n)
    pico = float(np.max(np.abs(rosa))) or 1.0
    return rosa / pico


def _filtrar_banda_np(sinal, f_lo: float, f_hi: float, ordem: float = 2.0):
    n = len(sinal)
    spec = np.fft.rfft(sinal)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    resp = np.ones_like(freqs)
    if f_lo > 0.0:
        resp *= 1.0 / np.sqrt(1.0 + (f_lo / np.maximum(freqs, 1e-3)) ** (2.0 * ordem))
    if f_hi > 0.0:
        resp *= 1.0 / np.sqrt(1.0 + (freqs / f_hi) ** (2.0 * ordem))
    resp[0] = 0.0
    return np.fft.irfft(spec * resp, n=n)


def _ressonador_np(sinal, fc: float, q: float):
    """Filtro ressonador passa-banda espectral (simula cavidades de madeira, tubo vocal ou metal)."""
    n = len(sinal)
    spec = np.fft.rfft(sinal)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    bw = max(12.0, fc / max(0.5, q))
    delta = (freqs - fc) / (bw * 0.5)
    resp = 1.0 / np.sqrt(1.0 + delta * delta)
    resp[0] = 0.0
    return np.fft.irfft(spec * resp, n=n)


def _aplicar_sala_curta(mono, taps_ms_ganho: list[tuple[float, float, float]]):
    """Adiciona reflexoes precoces assimetricas em estereo (realismo de quarto/corredor)."""
    n = len(mono)
    esq, dir_ = _criar_buffer_estereo(n)
    if np is not None:
        m = np.asarray(mono, dtype=np.float64)
        esq[:] = m
        dir_[:] = m
        for atraso_ms, gl, gr in taps_ms_ganho:
            d = int(round((atraso_ms / 1000.0) * SR))
            if 0 < d < n:
                esq[d:] += m[:-d] * gl
                dir_[d:] += m[:-d] * gr
        return esq, dir_
    for i in range(n):
        esq[i] = mono[i]
        dir_[i] = mono[i]
    for atraso_ms, gl, gr in taps_ms_ganho:
        d = int(round((atraso_ms / 1000.0) * SR))
        for i in range(d, n):
            esq[i] += mono[i - d] * gl
            dir_[i] += mono[i - d] * gr
    return esq, dir_


def _normalizar_pico_estereo(esq, dir_, alvo: float = 0.88):
    if np is not None:
        pico = max(float(np.max(np.abs(esq))), float(np.max(np.abs(dir_))), 1e-6)
        escala = min(alvo / pico, 6.0)
        return np.clip(esq * escala, -0.96, 0.96), np.clip(dir_ * escala, -0.96, 0.96)
    pico = max(max((abs(v) for v in esq), default=1e-6), max((abs(v) for v in dir_), default=1e-6), 1e-6)
    escala = min(alvo / pico, 6.0)
    for i in range(len(esq)):
        esq[i] = max(-0.96, min(0.96, esq[i] * escala))
        dir_[i] = max(-0.96, min(0.96, dir_[i] * escala))
    return esq, dir_


# ============================================================
# DETECCAO DE VIDEO ATIVO E CURVA DE CAMA SONORA (DRONE)
# ============================================================

def _eh_video_05(ev: dict) -> bool:
    return ("interfone" in ev) or ("portaria_vazia" in ev) or (int(ev.get("video_id", 1)) == 5)


def _eh_video_04(ev: dict) -> bool:
    return (not _eh_video_05(ev)) and (("berco_vazio" in ev) or ("passos_corredor" in ev) or (int(ev.get("video_id", 1)) == 4))


def _eh_video_03(ev: dict) -> bool:
    return (not _eh_video_05(ev)) and (not _eh_video_04(ev)) and (("pix_1" in ev) or ("guarda_roupa" in ev) or (int(ev.get("video_id", 1)) == 3))


def _eh_video_02(ev: dict) -> bool:
    return (not _eh_video_05(ev)) and (not _eh_video_04(ev)) and (not _eh_video_03(ev)) and (
        ("gps_rota" in ev) or ("caminhao" in ev) or (int(ev.get("video_id", 1)) == 2)
    )


def _envelope_drone_em_t(t: float, ev: dict) -> float:
    """Curva de tensao do drone com corte subito no plot_twist."""
    if _eh_video_05(ev):
        cong = float(ev.get("congela", 4.0))
        interf = float(ev.get("interfone", 10.5))
        interf_d = float(ev.get("interfone_duracao", 1.2))
        porta = float(ev.get("porta_impacto", 14.5))
        porta_d = float(ev.get("porta_impacto_duracao", 1.1))
        vazia = float(ev.get("portaria_vazia", 17.5))
        abre = float(ev.get("abre_imagem", 22.0))
        imp = float(ev.get("impacto_twist", 23.5))
        imp_d = float(ev.get("impacto_twist_duracao", 1.4))
        twist = float(ev.get("plot_twist", 30.0))

        # Corte subito no impacto_twist e silencio gelado na revelacao final (sem cama de CTA no fim!)
        if imp + 0.04 <= t < imp + imp_d:
            return 0.0
        if imp + imp_d <= t < twist:
            return 0.06
        if t >= twist:
            return 0.0

        corte_imp = 1.0 if t < imp else max(0.0, 1.0 - (t - imp) / 0.04)
        if t < 0.35:
            base = 0.13 * (t / 0.35)
        elif t < cong:
            base = 0.14
        elif t < interf:
            base = 0.24
        elif t < vazia:
            base = 0.31
        elif t < abre:
            k = (t - vazia) / max(0.1, abre - vazia)
            base = 0.25 + 0.13 * k
        else:
            base = 0.40

        if interf - 0.08 <= t <= interf + interf_d + 0.08:
            base *= 0.24
        if porta - 0.08 <= t <= porta + porta_d + 0.08:
            base *= 0.30
        return base * corte_imp

    if _eh_video_04(ev):
        suss = float(ev.get("sussurro", 4.0))
        suss_d = float(ev.get("sussurro_duracao", 1.2))
        berco = float(ev.get("berco_vazio", 7.2))
        cor = float(ev.get("coracao_dispara", 9.0))
        passos = float(ev.get("passos_corredor", 13.0))
        passos_d = float(ev.get("passos_corredor_duracao", 1.3))
        bebe = float(ev.get("bebe_dormindo", 19.0))
        cam_v = float(ev.get("camera_vazio", 25.5))
        twist = float(ev.get("plot_twist", 28.8))
        imp = float(ev.get("impacto_twist", 31.2))
        imp_d = float(ev.get("impacto_twist_duracao", 1.4))
        cta = float(ev.get("cta", 36.0))

        # Corte seco no plot_twist ate o final do impacto (silencio gelado para o impacto brilhar)
        if twist + 0.04 <= t < imp + imp_d:
            return 0.0
        # Blecaute quase mudo ("A luz do quarto apaga sozinha.")
        if imp + imp_d <= t < cta:
            return 0.04
        # Cama limpa e controlada na CTA
        if t >= cta:
            return 0.11 * min(1.0, (t - cta) / 0.25)

        corte_twist = 1.0 if t < twist else max(0.0, 1.0 - (t - twist) / 0.04)
        if t < 0.35:
            base = 0.12 * (t / 0.35)
        elif t < berco:
            base = 0.14
        elif t < cor:
            base = 0.24
        elif t < bebe:
            base = 0.34
        elif t < cam_v:
            # Alivio temporario quando o bebe esta dormindo tranquilo no berco
            base = 0.06
        else:
            k = (t - cam_v) / max(0.1, twist - cam_v)
            base = 0.15 + 0.27 * (k ** 1.3)

        if suss - 0.08 <= t <= suss + suss_d + 0.08:
            base *= 0.22
        if passos - 0.08 <= t <= passos + passos_d + 0.08:
            base *= 0.28
        return base * corte_twist

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

        if twist + 0.045 <= t < gr + gr_d:
            return 0.0
        if gr + gr_d <= t < cta:
            return 0.08
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


def sintetizar_cama_drone(duracao: float, ev: dict, ganhos_cat: dict[str, float] | None = None, relatorio: dict[str, str] | None = None):
    """Cama continua de suspense: usa assets/sfx/drone_suspense.* em loop se existir, senao drone organico HD."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    passo = 128
    pontos = [
        _envelope_drone_em_t(min(duracao, (i * passo) / SR), ev)
        for i in range(n // passo + 2)
    ]

    par_real, arq_real = carregar_sfx_real("drone_suspense", ganhos_cat=ganhos_cat)
    if par_real is not None and arq_real is not None and len(par_real[0]) > SR // 2:
        if relatorio is not None:
            relatorio["drone_suspense"] = f"REAL ({arq_real})"
        src_l, src_r = par_real
        m = len(src_l)
        if np is not None:
            idx_f = np.arange(n, dtype=np.float64) / passo
            idx_i = np.floor(idx_f).astype(np.int64)
            frac = idx_f - idx_i
            p_arr = np.array(pontos, dtype=np.float64)
            env = p_arr[idx_i] * (1.0 - frac) + p_arr[idx_i + 1] * frac
            reps = (n // m) + 2
            esq[:] = np.tile(src_l, reps)[:n] * env
            dir_[:] = np.tile(src_r, reps)[:n] * env
            return esq, dir_
        for i in range(n):
            bi = i // passo
            frac = (i - bi * passo) / passo
            env = pontos[bi] * (1.0 - frac) + pontos[bi + 1] * frac
            esq[i] = src_l[i % m] * env
            dir_[i] = src_r[i % m] * env
        return esq, dir_

    if relatorio is not None:
        relatorio["drone_suspense"] = "fallback procedural HD"

    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        idx_f = np.arange(n, dtype=np.float64) / passo
        idx_i = np.floor(idx_f).astype(np.int64)
        frac = idx_f - idx_i
        p_arr = np.array(pontos, dtype=np.float64)
        env = p_arr[idx_i] * (1.0 - frac) + p_arr[idx_i + 1] * frac

        lfo = 0.84 + 0.16 * np.sin(2.0 * np.pi * 0.22 * t)
        f0 = 41.2 if _eh_video_04(ev) else (44.0 if _eh_video_03(ev) else 49.0)
        # Sub organico quente + ar grave filtrado por FFT (sem zumbido eletronico)
        sub_l = 0.56 * np.sin(2.0 * np.pi * f0 * t) + 0.20 * np.sin(2.0 * np.pi * (f0 * 1.498) * t + 0.4)
        sub_r = 0.56 * np.sin(2.0 * np.pi * (f0 + 0.31) * t + 0.7) + 0.20 * np.sin(2.0 * np.pi * (f0 * 1.494) * t)
        ar_l = _filtrar_banda_np(_ruido_rosa_np(n, 441), 35.0, 210.0, ordem=2.0) * 0.42
        ar_r = _filtrar_banda_np(_ruido_rosa_np(n, 442), 35.0, 210.0, ordem=2.0) * 0.42

        esq[:] = env * lfo * (sub_l + ar_l)
        dir_[:] = env * lfo * (sub_r + ar_r)
        return esq, dir_

    rng = random.Random(43)
    lp = 0.0
    two_pi = 2.0 * math.pi
    f0 = 41.2 if _eh_video_04(ev) else (44.0 if _eh_video_03(ev) else 49.0)
    for i in range(n):
        t = i / SR
        bi = i // passo
        frac = (i - bi * passo) / passo
        env = pontos[bi] * (1.0 - frac) + pontos[bi + 1] * frac
        if env <= 1e-6:
            continue
        lfo = 0.84 + 0.16 * math.sin(two_pi * 0.22 * t)
        lp += 0.018 * (rng.uniform(-1.0, 1.0) - lp)
        sub_l = 0.56 * math.sin(two_pi * f0 * t) + 0.20 * math.sin(two_pi * (f0 * 1.498) * t + 0.4)
        sub_r = 0.56 * math.sin(two_pi * (f0 + 0.31) * t + 0.7) + 0.20 * math.sin(two_pi * (f0 * 1.494) * t)
        esq[i] = env * lfo * (sub_l + 0.72 * lp)
        dir_[i] = env * lfo * (sub_r - 0.65 * lp)
    return esq, dir_


# ============================================================
# SFX PROCEDURAIS HD DE CINEMA (VIDEO 04 + FALLBACKS REFORMULADOS)
# ============================================================

def sfx_sussurro_hd(duracao: float = 1.20):
    """Sussurro humano soproso atraves de alto-falante de baba eletronica (formantes vocais sem pitch sintetico)."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        sopro = _ruido_rosa_np(n, 4041)

        # Tres silabas sussurradas irregulares ("shhh... tii... shhh...")
        sil1 = np.exp(-((t - 0.22) / 0.13) ** 2) * (0.75 + 0.25 * np.sin(2.0 * np.pi * 11.0 * t))
        sil2 = np.exp(-((t - 0.56) / 0.16) ** 2) * (0.70 + 0.30 * np.sin(2.0 * np.pi * 8.5 * t + 0.6))
        sil3 = np.exp(-((t - 0.94) / 0.15) ** 2) * (0.80 + 0.20 * np.sin(2.0 * np.pi * 13.0 * t + 1.1))
        env_fala = np.clip(sil1 * 0.95 + sil2 * 1.0 + sil3 * 0.85, 0.0, 1.15)

        # Formantes vocais de sussurro nao-vozeado (F1, F2, F3 + fricativa sibilante)
        f1 = _ressonador_np(sopro * env_fala, 640.0, 4.2) * 0.55
        f2 = _ressonador_np(sopro * env_fala, 1720.0, 5.5) * 0.92
        f3 = _ressonador_np(sopro * env_fala, 2860.0, 6.2) * 0.65
        sib = _filtrar_banda_np(sopro * (sil1 + sil3 * 0.8), 3400.0, 5800.0, ordem=2.0) * 0.36

        # Curva de alto-falante pequeno de baba eletronica + chiado leve de radio
        voz_radio = _filtrar_banda_np(f1 + f2 + f3 + sib, 380.0, 3900.0, ordem=2.0)
        estatica = _filtrar_banda_np(_ruido_rosa_np(n, 4042), 850.0, 4600.0, ordem=1.5) * 0.085
        # Micro-estalo de transmissao ao abrir/fechar squelch da baba eletronica
        squelch = (np.exp(-t / 0.012) + np.exp(-np.maximum(0.0, duracao - t) / 0.015)) * estatica * 2.4

        env_global = np.minimum(1.0, t / 0.018) * np.minimum(1.0, (duracao - t) / 0.045)
        mono = np.tanh((voz_radio * 2.2 + estatica + squelch) * 1.15) * env_global
        esq, dir_ = _aplicar_sala_curta(mono, [(19.0, 0.16, 0.22), (43.0, 0.09, 0.12)])
        # Levemente deslocado para o lado da mesa de cabeceira
        esq *= 0.88
        dir_ *= 1.02
        return _normalizar_pico_estereo(esq, dir_, alvo=0.84)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(4041)
    lp1 = lp2 = 0.0
    for i in range(n):
        t = i / SR
        r = rng.uniform(-1.0, 1.0)
        lp1 += 0.38 * (r - lp1)
        lp2 += 0.12 * (r - lp2)
        bp = lp1 - lp2
        e1 = math.exp(-((t - 0.22) / 0.13) ** 2)
        e2 = math.exp(-((t - 0.56) / 0.16) ** 2)
        e3 = math.exp(-((t - 0.94) / 0.15) ** 2)
        val = bp * (0.10 + 0.85 * (e1 + e2 + e3)) * min(1.0, t / 0.02) * min(1.0, (duracao - t) / 0.04)
        esq[i] = max(-0.9, min(0.9, val * 0.9))
        dir_[i] = max(-0.9, min(0.9, val))
    return esq, dir_


def sfx_passos_corredor_hd(duracao: float = 1.30):
    """4 passos lentos e pesados em corredor escuro de madeira com panorama esquerda -> direita."""
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    passos = [
        (0.06, 0.72, 0.20, 74.0, 910.0),
        (0.39, 0.84, 0.42, 68.0, 820.0),
        (0.73, 0.95, 0.66, 72.0, 980.0),
        (1.04, 1.02, 0.84, 64.0, 760.0),
    ]
    if np is not None:
        base_noise = _ruido_rosa_np(n, 4043)
        ruido_sola = _filtrar_banda_np(base_noise, 180.0, 950.0, ordem=2.0)
        ruido_tabua = _filtrar_banda_np(_ruido_rosa_np(n, 4044), 680.0, 1950.0, ordem=2.0)
        t_all = np.arange(n, dtype=np.float64) / SR
        for t0, gain, pan, f_thump, f_tab in passos:
            dt = t_all - t0
            mask = (dt >= 0.0) & (dt <= 0.24)
            if not np.any(mask):
                continue
            d = dt[mask]
            # Calcanhar grave abafado + impacto da sola + micro-rangido da tabua de madeira
            f_inst = f_thump * (1.0 + 0.55 * np.exp(-d / 0.014))
            thump = np.sin(2.0 * np.pi * f_inst * d) * np.exp(-d / 0.036) * 0.95
            sola = ruido_sola[mask] * np.exp(-d / 0.022) * 1.15
            # Micro-rangido organico na transferencia de peso (0.04s apos o impacto)
            d_creak = d - 0.045
            creak_env = np.where((d_creak >= 0.0) & (d_creak <= 0.09), np.sin(np.pi * np.clip(d_creak / 0.09, 0.0, 1.0)), 0.0)
            tabua = ruido_tabua[mask] * creak_env * (0.45 + 0.35 * np.sin(2.0 * np.pi * 42.0 * d)) * 0.55
            passo_s = np.tanh((thump + sola + tabua) * 1.25) * np.minimum(1.0, d / 0.004) * gain
            esq[mask] += passo_s * math.cos(pan * math.pi * 0.5)
            dir_[mask] += passo_s * math.sin(pan * math.pi * 0.5)

        # Reflexoes precoces de corredor estreito
        esq_r, dir_r = _aplicar_sala_curta(0.5 * (esq + dir_), [(26.0, 0.22, 0.14), (58.0, 0.11, 0.16), (92.0, 0.07, 0.07)])
        esq = esq * 0.78 + esq_r * 0.32
        dir_ = dir_ * 0.78 + dir_r * 0.32
        return _normalizar_pico_estereo(esq, dir_, alvo=0.88)

    rng = random.Random(4043)
    lp = 0.0
    for i in range(n):
        t = i / SR
        lp += 0.18 * (rng.uniform(-1.0, 1.0) - lp)
        for t0, gain, pan, f_thump, _ in passos:
            d = t - t0
            if 0.0 <= d <= 0.22:
                s = (math.sin(2.0 * math.pi * f_thump * d) * math.exp(-d / 0.036) + lp * math.exp(-d / 0.022)) * gain
                esq[i] += s * (1.0 - pan * 0.5)
                dir_[i] += s * (0.5 + pan * 0.5)
    return _normalizar_pico_estereo(esq, dir_, alvo=0.86)


def sfx_heartbeat_hd(duracao: float = 2.20):
    """Batimento cardiaco profundo e organico (lub-dub acelerando, filtrado abaixo de 115 Hz)."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        mono = np.zeros(n, dtype=np.float64)
        # 4 batimentos acelerando de 0.58s para 0.44s de intervalo
        ciclos = [(0.05, 0.78), (0.63, 0.88), (1.15, 0.96), (1.62, 1.05)]
        for t0, amp in ciclos:
            # Lub (primeiro pulso, 54 Hz -> 36 Hz)
            d1 = t - t0
            m1 = (d1 >= 0.0) & (d1 <= 0.18)
            if np.any(m1):
                dd = d1[m1]
                f = 36.0 + 24.0 * np.exp(-dd * 22.0)
                mono[m1] += np.sin(2.0 * np.pi * f * dd) * np.minimum(1.0, dd / 0.012) * np.exp(-dd / 0.048) * amp
            # Dub (segundo pulso 0.18s depois, 46 Hz -> 32 Hz)
            d2 = t - (t0 + 0.18)
            m2 = (d2 >= 0.0) & (d2 <= 0.16)
            if np.any(m2):
                dd = d2[m2]
                f = 32.0 + 18.0 * np.exp(-dd * 26.0)
                mono[m2] += np.sin(2.0 * np.pi * f * dd) * np.minimum(1.0, dd / 0.010) * np.exp(-dd / 0.042) * (amp * 0.78)
        mono = _filtrar_banda_np(mono, 24.0, 125.0, ordem=2.0)
        mono = np.tanh(mono * 1.4)
        env = np.minimum(1.0, t / 0.015) * np.minimum(1.0, (duracao - t) / 0.08)
        mono *= env
        return _normalizar_pico_estereo(mono.copy(), mono * 0.98, alvo=0.82)

    esq, dir_ = _criar_buffer_estereo(n)
    for i in range(n):
        t = i / SR
        v = 0.0
        for t0, amp in [(0.05, 0.78), (0.63, 0.88), (1.15, 0.96), (1.62, 1.05)]:
            for off, freq, sc in [(0.0, 48.0, 1.0), (0.18, 40.0, 0.78)]:
                d = t - (t0 + off)
                if 0.0 <= d <= 0.16:
                    v += math.sin(2.0 * math.pi * freq * d) * min(1.0, d / 0.012) * math.exp(-d / 0.045) * amp * sc
        esq[i] = math.tanh(v * 1.3) * 0.8
        dir_[i] = esq[i]
    return esq, dir_


def sfx_porta_impacto_hd(duracao: float = 0.90):
    """Macaneta girando + porta de madeira aberta com forca batendo no batente + clique de interruptor."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        rosa = _ruido_rosa_np(n, 4045)
        madeira_mid = _filtrar_banda_np(rosa, 180.0, 1150.0, ordem=2.0)
        estalo_hi = _filtrar_banda_np(_ruido_rosa_np(n, 4046), 1600.0, 6200.0, ordem=2.0)
        mono = np.zeros(n, dtype=np.float64)

        # 1. Macaneta metalica destravando (t=0.02s)
        d0 = t - 0.02
        m0 = (d0 >= 0.0) & (d0 <= 0.09)
        mono[m0] += estalo_hi[m0] * np.exp(-d0[m0] / 0.014) * 0.55

        # 2. Impacto pesado da porta aberta com forca (t=0.14s)
        d1 = t - 0.14
        m1 = (d1 >= 0.0) & (d1 <= 0.48)
        dd = d1[m1]
        sub_p = np.sin(2.0 * np.pi * (58.0 + 75.0 * np.exp(-dd / 0.018)) * dd) * np.exp(-dd / 0.085) * 0.95
        mad_p = madeira_mid[m1] * np.exp(-dd / 0.055) * 1.25
        mono[m1] += (sub_p + mad_p) * np.minimum(1.0, dd / 0.004)

        # 3. Clique seco de interruptor de luz acendendo (t=0.62s)
        d2 = t - 0.62
        m2 = (d2 >= 0.0) & (d2 <= 0.06)
        dc = d2[m2]
        clique = estalo_hi[m2] * (np.exp(-dc / 0.004) + 0.65 * np.exp(-np.maximum(0.0, dc - 0.012) / 0.005) * (dc >= 0.012))
        mono[m2] += clique * 0.95

        mono = np.tanh(mono * 1.25)
        esq, dir_ = _aplicar_sala_curta(mono, [(21.0, 0.22, 0.18), (48.0, 0.12, 0.15)])
        return _normalizar_pico_estereo(esq, dir_, alvo=0.90)

    return sfx_batida_porta(intensidade=1.05, desvio_pitch=0.92, seed=4045)


def sfx_glitch_tv_hd(duracao: float = 0.55):
    """Rajada realista de interferencia/chuvisco em baba eletronica de visao noturna."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        rng = np.random.default_rng(4047)
        branco = rng.standard_normal(n)
        estatica = _filtrar_banda_np(branco, 950.0, 6200.0, ordem=2.0)
        # Dropouts irregulares de sinal sem fio (blocos de 18ms)
        bloco = max(1, int(0.018 * SR))
        n_b = (n // bloco) + 1
        gate = np.repeat((rng.random(n_b) > 0.28).astype(np.float64), bloco)[:n]
        hum = 0.08 * np.sin(2.0 * np.pi * 60.0 * t) + 0.05 * np.sin(2.0 * np.pi * 120.0 * t)
        env = np.minimum(1.0, t / 0.012) * np.minimum(1.0, (duracao - t) / 0.045) * (0.45 + 0.55 * gate)
        mono = np.tanh((estatica * 0.85 + hum) * env * 1.3)
        return _normalizar_pico_estereo(mono * 0.94, mono * 1.0, alvo=0.68)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(4047)
    for i in range(n):
        t = i / SR
        env = min(1.0, t / 0.015) * min(1.0, (duracao - t) / 0.04)
        v = rng.uniform(-0.55, 0.55) * env
        esq[i] = v
        dir_[i] = v * 0.95
    return esq, dir_


def sfx_interruptor_apaga_hd():
    """Estalo seco de interruptor desligando + queda sub-grave de blecaute total."""
    dur = 0.42
    n = int(round(dur * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        hi = _filtrar_banda_np(_ruido_rosa_np(n, 4048), 1800.0, 6500.0, ordem=2.0)
        clique = hi * (np.exp(-t / 0.004) + 0.7 * np.exp(-np.maximum(0.0, t - 0.014) / 0.005) * (t >= 0.014)) * 1.4
        f_drop = 32.0 + 72.0 * np.exp(-t * 14.0)
        drop = np.sin(2.0 * np.pi * f_drop * t) * np.minimum(1.0, t / 0.006) * np.exp(-t / 0.14) * 0.88
        mono = np.tanh((clique + drop) * 1.25) * np.minimum(1.0, (dur - t) / 0.03)
        return _normalizar_pico_estereo(mono.copy(), mono * 0.96, alvo=0.88)
    return sfx_apagao_farol(0.8)


def sfx_impacto_twist_hd(duracao: float = 1.40):
    """Impacto cinematografico de terror: succao reversa curta + sub-bass boom + ressonancia sombria."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        t_hit = 0.085
        rosa = _ruido_rosa_np(n, 4049)

        # 1. Breve succao reversa de ar imediatamente antes do impacto (0..0.085s)
        ar_rev = _filtrar_banda_np(rosa, 220.0, 2600.0, ordem=2.0)
        env_rev = np.where(t < t_hit, (t / t_hit) ** 2.6, 0.0)
        rev = ar_rev * env_rev * 0.72

        # 2. Sub-bass boom profundo com queda de frequencia natural (t >= t_hit)
        dt = np.maximum(0.0, t - t_hit)
        ativo = (t >= t_hit).astype(np.float64)
        fase = np.cumsum(2.0 * np.pi * (31.0 + 66.0 * np.exp(-dt * 7.5)) / SR)
        sub = np.sin(fase) * np.minimum(1.0, dt / 0.005) * np.exp(-dt * 2.05) * ativo * 1.15

        # 3. Impacto de corpo grave + estalo metalico sombrio filtrado (zero senoide fina)
        corpo = _filtrar_banda_np(rosa, 90.0, 480.0, ordem=2.0) * np.exp(-dt / 0.095) * ativo * 1.35
        metal = _ressonador_np(rosa, 520.0, 8.0) * 0.45 + _ressonador_np(rosa, 745.0, 9.0) * 0.35
        metal *= np.exp(-dt * 2.8) * ativo * 0.52

        cauda = np.minimum(1.0, (duracao - t) / 0.09)
        mono = np.tanh((rev + sub + corpo + metal) * 1.25) * cauda
        esq, dir_ = _aplicar_sala_curta(mono, [(29.0, 0.24, 0.18), (67.0, 0.14, 0.19)])
        return _normalizar_pico_estereo(esq, dir_, alvo=0.92)

    return sfx_sub_boom(duracao)


def sfx_guarda_roupa(duracao: float = 1.60):
    """Rangido organico de madeira/dobradica (impulsos stick-slip + ressonadores de caixa de madeira, zero synth)."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        rng = np.random.default_rng(3141)

        # Gera trem de impulsos stick-slip irregulares (friccao fisica de dobradica/madeira seca)
        impulsos = np.zeros(n, dtype=np.float64)
        pos = int(0.06 * SR)
        fim = int((duracao - 0.10) * SR)
        while pos < fim:
            p = pos / float(n)
            # Cadencia acelera e desacelera como uma porta pesada cedendo aos solucos
            taxa_hz = 28.0 + 48.0 * (math.sin(math.pi * p) ** 1.3) + 14.0 * math.sin(2.0 * math.pi * 2.7 * (pos / SR))
            jitter = rng.uniform(0.72, 1.32)
            # Breve pausa natural de atrito no meio do movimento
            if 0.46 < p < 0.54:
                pos += int(0.045 * SR)
                continue
            amp = rng.uniform(0.45, 1.0) * (0.6 + 0.4 * math.sin(math.pi * p))
            impulsos[pos] += amp if rng.random() > 0.2 else -amp * 0.7
            passo_i = max(int(SR / 115.0), int((SR / max(18.0, taxa_hz)) * jitter))
            pos += passo_i

        # Ressonancias acusticas de caixa de madeira oca (3 formantes fisicos sem oscilador senoidal)
        r1 = _ressonador_np(impulsos, 245.0, 7.5) * 1.15
        r2 = _ressonador_np(impulsos, 585.0, 9.0) * 0.95
        r3 = _ressonador_np(impulsos, 1240.0, 8.0) * 0.55

        # Atrito seco de fibra de madeira/metal em alta frequencia
        atrito = _filtrar_banda_np(_ruido_rosa_np(n, 3142), 1800.0, 4200.0, ordem=2.0) * 0.24
        corpo_grav = _filtrar_banda_np(_ruido_rosa_np(n, 3143), 55.0, 165.0, ordem=2.0) * 0.34

        env = np.minimum(1.0, t / 0.14) * np.minimum(1.0, (duracao - t) / 0.20)
        mono = np.tanh((r1 + r2 + r3 + atrito + corpo_grav) * 1.8) * env
        esq, dir_ = _aplicar_sala_curta(mono, [(18.0, 0.14, 0.24), (44.0, 0.08, 0.14)])
        # Guarda-roupa levemente a direita da cena
        esq *= 0.78
        dir_ *= 1.04
        return _normalizar_pico_estereo(esq, dir_, alvo=0.86)

    # Fallback stdlib sem senoide limpa: ruido filtrado por pulsos irregulares
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(3141)
    lp1 = lp2 = 0.0
    for i in range(n):
        t = i / SR
        p = t / duracao
        env = min(1.0, t / 0.14) * min(1.0, (duracao - t) / 0.20)
        r = rng.uniform(-1.0, 1.0)
        lp1 += 0.22 * (r - lp1)
        lp2 += 0.04 * (r - lp2)
        pulso = 1.0 if ((i % max(220, int(680 - 300 * math.sin(math.pi * p)))) < 55) else 0.15
        val = (lp1 - lp2) * pulso * env * 1.4
        esq[i] = max(-0.9, min(0.9, val * 0.78))
        dir_[i] = max(-0.9, min(0.9, val * 1.02))
    return esq, dir_


# ---------------- SFX VIDEO 03 ("O Pix de 1 Centavo") ----------------

def sfx_vibracao_celular(duracao: float = 0.46, intensidade: float = 1.0):
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
    dur = 0.42
    n = int(round(dur * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    two_pi = 2.0 * math.pi
    pares = {
        1: (1046.5, 1318.5),
        2: (987.8, 1174.7),
        3: (880.0, 830.6),
        4: (784.0, 554.4),
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
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(313)
    two_pi = 2.0 * math.pi
    lp = lp2 = prev = 0.0

    for i in range(n):
        t = i / SR
        ruido = rng.uniform(-1.0, 1.0)
        lp += 0.28 * (ruido - lp)
        hp = lp - prev * 0.80
        prev = lp
        lp2 += 0.09 * (ruido - lp2)

        batida = 0.0
        if 0.12 <= t <= 0.45:
            dt = t - 0.12
            f_b = 98.0 + 90.0 * math.exp(-dt * 18.0)
            batida = (math.sin(two_pi * f_b * dt) * 0.85 + hp * 0.75) * math.exp(-dt * 13.0) * 0.90

        trava = 0.0
        if 0.50 <= t <= 0.74:
            dt = t - 0.50
            trava = (
                0.55 * math.sin(two_pi * 1680.0 * dt)
                + 0.45 * math.sin(two_pi * 2410.0 * dt)
                + 0.60 * hp
            ) * math.exp(-dt * 34.0) * 0.82

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
    """Whoosh cinematografico de ar grave filtrado (ruido rosa em varredura, sem tom sintetico)."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        p = t / duracao
        env = np.maximum(0.0, np.sin(np.pi * p)) ** 1.35
        rosa = _ruido_rosa_np(n, 2021)
        ar_grav = _filtrar_banda_np(rosa, 55.0, 320.0, ordem=2.0)
        ar_mid = _filtrar_banda_np(rosa, 260.0, 1400.0, ordem=2.0) * np.maximum(0.0, np.sin(np.pi * p)) ** 2.2
        sub = np.sin(np.cumsum(2.0 * np.pi * (95.0 - 52.0 * p) / SR)) * 0.35
        mono = np.tanh((ar_grav * 0.95 + ar_mid * 0.62 + sub) * env * 1.3)
        esq = mono * (1.0 - 0.35 * p)
        dir_ = mono * (0.65 + 0.35 * p)
        return _normalizar_pico_estereo(esq, dir_, alvo=0.80)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(202)
    lp = 0.0
    for i in range(n):
        t = i / SR
        p = t / duracao
        env = max(0.0, math.sin(math.pi * p)) ** 1.4
        lp += (0.04 + 0.18 * (1.0 - p)) * (rng.uniform(-1.0, 1.0) - lp)
        val = env * lp * 0.95
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
    """Riser de tensao organico com ruido filtrado crescente e pulso grave (sem sirene eletronica)."""
    dur = max(0.5, duracao)
    n = int(round(dur * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        p = t / dur
        env = (p ** 2.2) * np.minimum(1.0, (dur - t) / 0.025)
        rosa = _ruido_rosa_np(n, 3031)
        low_b = _filtrar_banda_np(rosa, 65.0, 320.0, ordem=2.0) * (1.0 - 0.3 * p)
        mid_b = _filtrar_banda_np(rosa, 320.0, 1600.0, ordem=2.0) * (p ** 1.1)
        hi_b = _filtrar_banda_np(rosa, 1500.0, 4800.0, ordem=2.0) * (p ** 2.4) * 0.72
        sub = np.sin(np.cumsum(2.0 * np.pi * (46.0 + 36.0 * (p ** 1.8)) / SR)) * 0.42
        pulso = 0.78 + 0.22 * np.sin(2.0 * np.pi * (2.2 + 5.5 * p) * t)
        mono = np.tanh((low_b + mid_b + hi_b + sub) * env * pulso * 1.45)
        return _normalizar_pico_estereo(mono * 0.96, mono * 1.0, alvo=0.76)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(303)
    two_pi = 2.0 * math.pi
    lp = 0.0
    f1 = 0.0
    for i in range(n):
        t = i / SR
        p = t / dur
        env = (p ** 2.1) * min(1.0, (dur - t) / 0.025)
        f1 += two_pi * (48.0 + 36.0 * p) / SR
        lp += (0.04 + 0.28 * (p ** 2)) * (rng.uniform(-1.0, 1.0) - lp)
        s = env * (0.40 * math.sin(f1) + 0.85 * lp)
        esq[i] = s * 0.74
        dir_[i] = s * 0.78
    return esq, dir_


def sfx_sub_boom(duracao_max: float):
    dur = max(0.5, min(2.0, duracao_max))
    n = int(round(dur * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        fase = np.cumsum(2.0 * np.pi * (32.0 + 68.0 * np.exp(-t * 5.8)) / SR)
        sub = np.exp(-t * 1.75) * np.sin(fase) * 0.98
        punch = _filtrar_banda_np(_ruido_rosa_np(n, 9091), 70.0, 340.0, ordem=2.0) * np.exp(-t / 0.065) * 0.92
        val = np.tanh((sub + punch) * 1.25) * np.minimum(1.0, t / 0.006) * np.minimum(1.0, (dur - t) / 0.055)
        return _normalizar_pico_estereo(val.copy(), val * 0.98, alvo=0.88)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(909)
    two_pi = 2.0 * math.pi
    fase = lp = 0.0
    for i in range(n):
        t = i / SR
        fase += two_pi * (33.0 + 68.0 * math.exp(-t * 5.2)) / SR
        lp += 0.08 * (rng.uniform(-1.0, 1.0) - lp)
        val = math.tanh(
            (math.exp(-t * 1.65) * math.sin(fase) * 0.95 + math.exp(-t * 2.6) * lp * 0.45) * 1.25
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


def sfx_interfone_hd(duracao: float = 1.20):
    """Interfone predial realista: clique analogico, zumbido eletromecanico abafado e chuva na portaria."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        rng = np.random.default_rng(5051)
        rosa = _ruido_rosa_np(n, 5052)

        # 1. Estalo mecanico de abertura do canal do interfone (t=0.02s)
        estalo = _filtrar_banda_np(rosa, 1100.0, 4400.0, ordem=2.0) * np.exp(-np.maximum(0.0, t - 0.02) / 0.011) * (t >= 0.02)

        # 2. Zumbido eletromecanico de interfone predial (bobina 60Hz+120Hz+180Hz em caixa plastica, dois toques)
        imp = np.zeros(n, dtype=np.float64)
        for p0, p1 in ((0.08, 0.44), (0.60, 0.94)):
            pos = int(p0 * SR)
            fim = int(p1 * SR)
            while pos < fim:
                amp = rng.uniform(0.65, 1.0)
                imp[pos] += amp
                # Oscilacao mecanica da lamina (~118 Hz com micro-jitter fisico)
                passo = max(280, int((SR / 118.0) * rng.uniform(0.95, 1.05)))
                pos += passo

        caixa_a = _ressonador_np(imp, 470.0, 5.5) * 0.95
        caixa_b = _ressonador_np(imp, 1290.0, 6.5) * 0.65
        caixa_c = _ressonador_np(imp, 2180.0, 7.0) * 0.35
        campainha = _filtrar_banda_np(caixa_a + caixa_b + caixa_c, 340.0, 3100.0, ordem=2.0)

        # 3. Chiado analogico de microfone + chuva noturna la fora na portaria
        chuva_est = _filtrar_banda_np(_ruido_rosa_np(n, 5053), 750.0, 3400.0, ordem=2.0) * 0.22
        env = np.minimum(1.0, t / 0.014) * np.minimum(1.0, (duracao - t) / 0.045)
        mono = np.tanh((estalo * 1.4 + campainha * 1.55 + chuva_est) * 1.2) * env
        esq, dir_ = _aplicar_sala_curta(mono, [(22.0, 0.18, 0.14), (52.0, 0.09, 0.12)])
        return _normalizar_pico_estereo(esq * 0.95, dir_, alvo=0.86)

    esq, dir_ = _criar_buffer_estereo(n)
    rng = random.Random(5051)
    lp1 = lp2 = 0.0
    for i in range(n):
        t = i / SR
        r = rng.uniform(-1.0, 1.0)
        lp1 += 0.34 * (r - lp1)
        lp2 += 0.09 * (r - lp2)
        bp = lp1 - lp2
        ativo = (0.08 <= t <= 0.44) or (0.60 <= t <= 0.94)
        pulso = 1.0 if (ativo and (i % 374) < 60) else 0.18
        env = min(1.0, t / 0.015) * min(1.0, (duracao - t) / 0.04)
        v = bp * pulso * env * 1.2
        esq[i] = max(-0.9, min(0.9, v))
        dir_[i] = max(-0.9, min(0.9, v * 0.96))
    return esq, dir_


def sfx_corrente_porta_hd(duracao: float = 1.10):
    """Porta da sala batendo fechada + corrente metalica deslizando no trilho e travando firme."""
    n = int(round(duracao * SR))
    if np is not None:
        t = np.arange(n, dtype=np.float64) / SR
        rng = np.random.default_rng(5055)
        rosa = _ruido_rosa_np(n, 5056)
        mad_mid = _filtrar_banda_np(rosa, 140.0, 980.0, ordem=2.0)
        mono = np.zeros(n, dtype=np.float64)

        # 1. Batida pesada da porta fechando (t=0.06s)
        d0 = t - 0.06
        m0 = (d0 >= 0.0) & (d0 <= 0.36)
        dd = d0[m0]
        sub_p = np.sin(2.0 * np.pi * (56.0 + 72.0 * np.exp(-dd / 0.016)) * dd) * np.exp(-dd / 0.075) * 0.95
        mono[m0] += (sub_p + mad_mid[m0] * np.exp(-dd / 0.048) * 1.20) * np.minimum(1.0, dd / 0.004)

        # 2. Corrente metalica deslizando no trilho (t=0.30..0.78s): impulsos metalicos irregulares
        imp_met = np.zeros(n, dtype=np.float64)
        for k in range(10):
            tk = 0.30 + k * 0.046 + rng.uniform(-0.009, 0.009)
            idx = int(tk * SR)
            if 0 <= idx < n:
                imp_met[idx] += rng.uniform(0.55, 1.05) * (0.7 + 0.3 * (k / 9.0))
        # 3. Trava firme no fim do trilho (t=0.80s)
        idx_trava = int(0.80 * SR)
        if idx_trava < n:
            imp_met[idx_trava] += 1.65

        aco = (
            _ressonador_np(imp_met, 2350.0, 12.0) * 0.90
            + _ressonador_np(imp_met, 3820.0, 14.0) * 0.72
            + _ressonador_np(imp_met, 5480.0, 13.0) * 0.45
        )
        # Corpo metalico seco no encaixe final
        d2 = t - 0.80
        m2 = (d2 >= 0.0) & (d2 <= 0.16)
        mono[m2] += mad_mid[m2] * np.exp(-d2[m2] / 0.024) * 0.85

        mono = np.tanh((mono + aco * 2.1) * 1.25) * np.minimum(1.0, (duracao - t) / 0.04)
        esq, dir_ = _aplicar_sala_curta(mono, [(19.0, 0.20, 0.15), (46.0, 0.11, 0.14)])
        return _normalizar_pico_estereo(esq, dir_, alvo=0.90)

    return sfx_porta_impacto_hd(duracao)


# ============================================================
# COMPOSICAO DE SFX SINCRONIZADA COM eventos.json
# ============================================================

def sintetizar_sfx(
    duracao: float,
    ev: dict,
    ganhos_cat: dict[str, float] | None = None,
    relatorio: dict[str, str] | None = None,
):
    n = int(round(duracao * SR))
    esq, dir_ = _criar_buffer_estereo(n)

    def pegar(nome: str, fn_fb, dur_max: float | None = None):
        return obter_sfx(nome, fn_fb, duracao_max=dur_max, ganhos_cat=ganhos_cat, relatorio=relatorio)

    if _eh_video_05(ev):
        # 1. Celular vibra as 02:15 + notificacao de app de entrega
        if "vibra_1" in ev:
            vl, vr = sfx_vibracao_celular(0.46, 0.92)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["vibra_1"]) - 0.04), vl, vr, 0.82)
        if "pedido_chegou" in ev:
            pl, pr = sfx_pix_notificacao(1)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pedido_chegou"]) - 0.04), pl, pr, 0.72)

        # 2. Katana Hit 1 ("NAO PEDIU"): sub_boom seco
        if "nao_pediu" in ev:
            bl, br = pegar("sub_boom", lambda: sfx_sub_boom(0.95), dur_max=1.05)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["nao_pediu"]) - 0.03), bl, br, 0.82)

        # 3. Tela do interfone: interferencia leve de CCTV
        if "tela_interfone" in ev:
            gl, gr = pegar("glitch_tv", lambda: sfx_glitch_tv_hd(0.40), dur_max=0.45)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["tela_interfone"]) - 0.02), gl, gr, 0.48)

        # 4. Bloco SFX puro [SFX:interfone:1.2]: interfone predial + chuva/estatica
        if "interfone" in ev:
            dur_i = float(ev.get("interfone_duracao", 1.2))
            il, ir = pegar("interfone", lambda: sfx_interfone_hd(dur_i), dur_max=dur_i + 0.06)
            _misturar_trecho(esq, dir_, float(ev["interfone"]), il, ir, 0.98)

        # 5. Bloco SFX puro [SFX:porta_impacto:1.1]: porta fechando + corrente metalica
        if "porta_impacto" in ev:
            dur_p = float(ev.get("porta_impacto_duracao", 1.1))
            pl, pr = pegar("porta_impacto", lambda: sfx_corrente_porta_hd(dur_p), dur_max=dur_p + 0.06)
            _misturar_trecho(esq, dir_, float(ev["porta_impacto"]), pl, pr, 1.0)

        # 6. Katana Hit 2 ("SUMIU") quando a portaria esta vazia: whoosh sombrio + glitch
        if "portaria_vazia" in ev:
            t_v = max(0.0, float(ev["portaria_vazia"]) - 0.04)
            wl, wr = pegar("whoosh", lambda: sfx_whoosh_sombrio(0.75), dur_max=0.85)
            _misturar_trecho(esq, dir_, t_v, wl, wr, 0.86)
            gl, gr = pegar("glitch_tv", lambda: sfx_glitch_tv_hd(0.32), dur_max=0.35)
            _misturar_trecho(esq, dir_, t_v, gl, gr, 0.42)

        # 7. CTA unica visual no meio (~48%-56%): pop limpo sutil na entrada
        if "cta_meio_inicio" in ev:
            cl, cr = pegar("cta_pop", sfx_cta_pop, dur_max=0.25)
            _misturar_trecho(esq, dir_, float(ev["cta_meio_inicio"]), cl, cr, 0.62)

        # 8. Segunda vibracao do celular ("Pedido entregue. Foto em anexo.")
        if "vibra_2" in ev:
            vl, vr = sfx_vibracao_celular(0.46, 1.05)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["vibra_2"]) - 0.04), vl, vr, 0.86)
        if "pedido_entregue" in ev:
            pl, pr = sfx_pix_notificacao(3)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pedido_entregue"]) - 0.04), pl, pr, 0.76)

        # 9. Riser tenso antes de abrir a foto
        if "foto_anexo" in ev and "impacto_twist" in ev:
            t_fa = float(ev["foto_anexo"])
            t_it = float(ev["impacto_twist"])
            dur_r = (t_it - 0.02) - t_fa
            if dur_r >= 0.45:
                rl, rr = pegar("riser", lambda: sfx_riser(dur_r), dur_max=dur_r)
                _misturar_trecho(esq, dir_, t_fa, rl, rr, 0.72)

        # 10. Bloco SFX puro [SFX:impacto_twist:1.4]: impacto cinematografico no silencio do drone
        if "impacto_twist" in ev:
            dur_it = float(ev.get("impacto_twist_duracao", 1.4))
            il, ir = pegar("impacto_twist", lambda: sfx_impacto_twist_hd(dur_it), dur_max=dur_it + 0.05)
            _misturar_trecho(esq, dir_, float(ev["impacto_twist"]), il, ir, 1.0)

        # 11. Katana Hit 3 ("ATRAS DELA"): golpe sub-grave seco encerrando para loop imediato
        if "plot_twist" in ev:
            t_tw = max(0.0, float(ev["plot_twist"]) - 0.02)
            rem = max(0.45, duracao - t_tw)
            bl, br = pegar("sub_boom", lambda: sfx_sub_boom(min(1.1, rem)), dur_max=rem)
            _misturar_trecho(esq, dir_, t_tw, bl, br, 0.94)

        return esq, dir_

    if _eh_video_04(ev):
        # 1. Interferencia sutil quando a baba eletronica chama atencao
        if "baba_som" in ev:
            gl, gr = pegar("glitch_tv", lambda: sfx_glitch_tv_hd(0.42), dur_max=0.48)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["baba_som"]) - 0.04), gl, gr, 0.54)

        # 2. Bloco SFX puro [SFX:sussurro:1.2]: sussurro vindo da baba eletronica
        if "sussurro" in ev:
            dur_s = float(ev.get("sussurro_duracao", 1.2))
            sl, sr = pegar("sussurro", lambda: sfx_sussurro_hd(dur_s), dur_max=dur_s + 0.06)
            _misturar_trecho(esq, dir_, float(ev["sussurro"]), sl, sr, 0.98)

        # 3. Katana Hit 1 ("VAZIO"): sub_boom seco + micro glitch na tela
        if "berco_vazio" in ev:
            t_v = max(0.0, float(ev["berco_vazio"]) - 0.03)
            bl, br = pegar("sub_boom", lambda: sfx_sub_boom(0.95), dur_max=1.05)
            _misturar_trecho(esq, dir_, t_v, bl, br, 0.82)
            gl, gr = pegar("glitch_tv", lambda: sfx_glitch_tv_hd(0.32), dur_max=0.35)
            _misturar_trecho(esq, dir_, t_v, gl, gr, 0.44)

        # 4. "O coracao dispara": heartbeat acelerando
        if "coracao_dispara" in ev:
            t_c = float(ev["coracao_dispara"])
            t_p = float(ev.get("passos_corredor", t_c + 2.4))
            dur_hb = max(1.1, min(2.4, t_p - t_c))
            hl, hr = pegar("heartbeat", lambda: sfx_heartbeat_hd(dur_hb), dur_max=dur_hb)
            _misturar_trecho(esq, dir_, t_c, hl, hr, 0.86)

        # 5. Katana Hit 2 ("SOMBRA"): whoosh sombrio na sombra cruzando o corredor
        if "sombra_corredor" in ev:
            wl, wr = pegar("whoosh", lambda: sfx_whoosh_sombrio(0.75), dur_max=0.85)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["sombra_corredor"]) - 0.05), wl, wr, 0.86)

        # 6. Bloco SFX puro [SFX:passos_corredor:1.3]: passos no corredor escuro + leve glitch
        if "passos_corredor" in ev:
            dur_p = float(ev.get("passos_corredor_duracao", 1.3))
            pl, pr = pegar("passos_corredor", lambda: sfx_passos_corredor_hd(dur_p), dur_max=dur_p + 0.05)
            _misturar_trecho(esq, dir_, float(ev["passos_corredor"]), pl, pr, 1.0)

        # 7. Abre a porta com forca e acende a luz
        if "abre_porta" in ev:
            pl, pr = pegar("porta_impacto", lambda: sfx_porta_impacto_hd(0.90), dur_max=0.95)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["abre_porta"]) - 0.04), pl, pr, 0.92)

        # 8. Retorno para a tela -> riser crescente ate "atras da porta" + glitch
        if "camera_vazio" in ev and "plot_twist" in ev:
            t_cv = float(ev["camera_vazio"])
            t_tw = float(ev["plot_twist"])
            dur_r = (t_tw - 0.02) - t_cv
            if dur_r >= 0.5:
                rl, rr = pegar("riser", lambda: sfx_riser(dur_r), dur_max=dur_r)
                _misturar_trecho(esq, dir_, t_cv, rl, rr, 0.72)
            gl, gr = pegar("glitch_tv", lambda: sfx_glitch_tv_hd(0.36), dur_max=0.40)
            _misturar_trecho(esq, dir_, t_cv, gl, gr, 0.50)

        # 9. Katana Hit 3 ("ATRAS DA PORTA"): impacto sub no instante da revelacao
        if "plot_twist" in ev:
            bl, br = pegar("sub_boom", lambda: sfx_sub_boom(1.15), dur_max=1.25)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["plot_twist"]) - 0.02), bl, br, 0.88)

        # 10. Bloco SFX puro [SFX:impacto_twist:1.4]: terror cinematografico no silencio do drone
        if "impacto_twist" in ev:
            dur_it = float(ev.get("impacto_twist_duracao", 1.4))
            il, ir = pegar("impacto_twist", lambda: sfx_impacto_twist_hd(dur_it), dur_max=dur_it + 0.05)
            _misturar_trecho(esq, dir_, float(ev["impacto_twist"]), il, ir, 1.0)

        # 11. Katana Hit 4 ("APAGA"): estalo seco do interruptor + queda de blecaute
        if "apaga_hit" in ev:
            al, ar = sfx_interruptor_apaga_hd()
            _misturar_trecho(esq, dir_, max(0.0, float(ev["apaga_hit"]) - 0.02), al, ar, 0.92)

        # 12. Pop limpo na CTA "Comente EU QUERO"
        if "cta_acao" in ev:
            cl, cr = pegar("cta_pop", sfx_cta_pop, dur_max=0.25)
            _misturar_trecho(esq, dir_, float(ev["cta_acao"]), cl, cr, 0.72)

        return esq, dir_

    if _eh_video_03(ev):
        if "vibra_cama" in ev:
            vl, vr = sfx_vibracao_celular(0.46, 0.90)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["vibra_cama"]) - 0.04), vl, vr, 0.82)
        if "pix_1" in ev:
            pl, pr = sfx_pix_notificacao(1)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pix_1"]) - 0.04), pl, pr, 0.82)
        if "nao_acende" in ev:
            bl, br = pegar("sub_boom", lambda: sfx_sub_boom(0.85), dur_max=0.95)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["nao_acende"]) - 0.05), bl, br, 0.62)
        if "pix_2" in ev:
            vl, vr = sfx_vibracao_celular(0.42, 0.95)
            pl, pr = sfx_pix_notificacao(2)
            t2 = max(0.0, float(ev["pix_2"]) - 0.05)
            _misturar_trecho(esq, dir_, t2, vl, vr, 0.72)
            _misturar_trecho(esq, dir_, t2 + 0.10, pl, pr, 0.82)
        if "tranca_porta" in ev:
            tl, tr = sfx_tranca_porta()
            _misturar_trecho(esq, dir_, float(ev["tranca_porta"]) + 0.15, tl, tr, 0.86)
        if "pix_3" in ev:
            vl, vr = sfx_vibracao_celular(0.44, 1.05)
            pl, pr = sfx_pix_notificacao(3)
            t3 = max(0.0, float(ev["pix_3"]) - 0.04)
            _misturar_trecho(esq, dir_, t3, vl, vr, 0.80)
            _misturar_trecho(esq, dir_, t3 + 0.08, pl, pr, 0.88)
        if "trava_janela" in ev:
            dur_j = float(ev.get("trava_janela_duracao", 1.4))
            jl, jr = sfx_trava_janela(dur_j)
            _misturar_trecho(esq, dir_, float(ev["trava_janela"]), jl, jr, 1.0)
        if "hora_0314" in ev:
            vl, vr = sfx_vibracao_celular(0.50, 1.15)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["hora_0314"]) + 0.10), vl, vr, 0.88)
        if "pix_4" in ev:
            pl, pr = sfx_pix_notificacao(4)
            _misturar_trecho(esq, dir_, max(0.0, float(ev["pix_4"]) - 0.04), pl, pr, 0.90)
        if "plot_twist" in ev:
            t_tw = float(ev["plot_twist"])
            t_gr = float(ev.get("guarda_roupa", t_tw + 1.5))
            bm_l, bm_r = pegar("sub_boom", lambda: sfx_sub_boom(max(0.65, min(1.5, t_gr - t_tw + 0.05))), dur_max=1.5)
            _misturar_trecho(esq, dir_, t_tw, bm_l, bm_r, 0.94)
        if "guarda_roupa" in ev:
            dur_g = float(ev.get("guarda_roupa_duracao", 1.6))
            gl, gr_ = pegar("guarda_roupa", lambda: sfx_guarda_roupa(dur_g), dur_max=dur_g + 0.06)
            _misturar_trecho(esq, dir_, float(ev["guarda_roupa"]), gl, gr_, 1.0)
        if "cta_acao" in ev:
            cl, cr = pegar("cta_pop", sfx_cta_pop, dur_max=0.25)
            _misturar_trecho(esq, dir_, float(ev["cta_acao"]), cl, cr, 0.72)
        return esq, dir_

    if _eh_video_02(ev):
        ping_l, ping_r = sfx_ping_gps(invertido=False)
        if "gancho" in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev["gancho"]) + 0.15), ping_l, ping_r, 0.38)
        if "gps_rota" in ev:
            _misturar_trecho(esq, dir_, max(0.0, float(ev["gps_rota"]) - 0.04), ping_l, ping_r, 0.85)
        if "rua_escura" in ev:
            wl, wr = pegar("whoosh", lambda: sfx_whoosh_sombrio(0.90), dur_max=0.95)
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
                rl, rr = pegar("riser", lambda: sfx_riser(dur_r), dur_max=dur_r)
                _misturar_trecho(esq, dir_, float(ev["sussurro"]), rl, rr, 0.65)
        if "plot_twist" in ev:
            t_tw = float(ev["plot_twist"])
            t_cta = float(ev.get("cta", t_tw + 2.2))
            bm_l, bm_r = pegar("sub_boom", lambda: sfx_sub_boom(max(0.6, min(1.8, (t_cta - t_tw) * 0.75))), dur_max=1.8)
            _misturar_trecho(esq, dir_, t_tw, bm_l, bm_r, 0.90)
            pi_l, pi_r = sfx_ping_gps(invertido=True)
            _misturar_trecho(esq, dir_, t_tw + 0.06, pi_l, pi_r, 0.65)
        if "cta_acao" in ev:
            pl, pr = pegar("cta_pop", sfx_cta_pop, dur_max=0.25)
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
            rl, rr = pegar("riser", lambda: sfx_riser(dur_riser), dur_max=dur_riser)
            _misturar_trecho(esq, dir_, inicio_riser, rl, rr, 0.72)
        bm_l, bm_r = pegar("sub_boom", lambda: sfx_sub_boom(max(0.55, (t_twist + 0.04) - t_big)), dur_max=1.8)
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

    validacao = validar_artefatos_audio(PASTA_AUDIO)
    eventos = validacao["eventos"]
    carimbo = validacao["carimbo"]
    duracao = max(medir_duracao_ffprobe(VOZ_LIMPA_MP3), float(eventos.get("duracao_total", 0.0)))
    backend = "numpy" if np is not None else "stdlib"
    perfil = (
        "Video 05 (O Pedido das 02h15)"
        if _eh_video_05(eventos)
        else (
            "Video 04 (A Baba Eletronica)"
            if _eh_video_04(eventos)
            else (
                "Video 03 (O Pix de 1 Centavo)"
                if _eh_video_03(eventos)
                else ("Video 02 (GPS / Rota recalculada)" if _eh_video_02(eventos) else "Video 01 (legado)")
            )
        )
    )
    print(
        f"Integridade OK (Video {carimbo['video_id']:02d}, sha256={carimbo['roteiro_sha256'][:12]}). "
        f"Montando cama sonora e SFX [{perfil}] ({duracao:.3f}s, backend={backend})..."
    )

    ganhos_cat = _carregar_ganhos_catalogo()
    relatorio_sfx: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="sfx-v4-") as tmp:
        tmp_dir = Path(tmp)
        drone_wav = tmp_dir / "cama_drone.wav"
        sfx_wav = tmp_dir / "sfx_eventos.wav"
        pre_mix_wav = tmp_dir / "mix_pre.wav"

        d_l, d_r = sintetizar_cama_drone(duracao, eventos, ganhos_cat=ganhos_cat, relatorio=relatorio_sfx)
        _gravar_wav_estereo(drone_wav, d_l, d_r)

        s_l, s_r = sintetizar_sfx(duracao, eventos, ganhos_cat=ganhos_cat, relatorio=relatorio_sfx)
        _gravar_wav_estereo(sfx_wav, s_l, s_r)

        final_stats = mixar_e_masterizar(VOZ_LIMPA_MP3, drone_wav, sfx_wav, pre_mix_wav, MIX_FINAL_MP3)

    shutil.copy2(MIX_FINAL_MP3, NARRACAO_MP3)
    dur_final = medir_duracao_ffprobe(MIX_FINAL_MP3)
    if relatorio_sfx:
        resumo_fontes = ", ".join(f"{k}={v}" for k, v in sorted(relatorio_sfx.items()))
        print(f"Fontes de SFX usadas: {resumo_fontes}")
    print(
        f"Masterizado {MIX_FINAL_MP3.name} (e copiado para {NARRACAO_MP3.name}): "
        f"{dur_final:.3f}s | {final_stats['input_i']} LUFS | TP {final_stats['input_tp']} dBTP"
    )


if __name__ == "__main__":
    main()
