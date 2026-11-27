#!/usr/bin/env python3
"""Estacao de audio modular da fabrica_v2.

Fluxo (deterministico, reaproveitavel por episodio via --ep):
  1. Le <ep>/roteiro.json (fala por segmento, pronuncias_tts e deixas de SFX ancoradas em palavras).
  2. Sintetiza com Gemini 3.8 Flash TTS (voz Mako, --mode batch em 1 chamada ou segment) + alinhamento
     local via faster-whisper, ou fallback edge-tts (pt-BR-AntonioNeural). Cache em <ep>/build/tts_cache/.
  3. Remove silencio inicial com FFmpeg silenceremove (zero ar morto em 0.0s) deslocando carimbos.
  4. Sintetiza SFX procedurais filtrados com numpy nos tempos das palavras-ancora + cama com ducking.
  5. Normaliza a mixagem com FFmpeg loudnorm em duas passadas (-14 LUFS, TP -1.5 dBTP).

Saidas: <ep>/timestamps.json e <ep>/mix_final.wav (+ <ep>/build/voz.wav).
Uso: python3 fabrica_v2/engine/gerar_audio.py --ep fabrica_v2/episodios/ep01_velocidade --engine gemini --mode batch
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import mimetypes
import os
import re
import struct
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

ENGINE_DIR = Path(__file__).resolve().parent
EP_PADRAO = ENGINE_DIR.parent / "episodios" / "ep01_velocidade"
EP_DIR = EP_PADRAO
BUILD = EP_DIR / "build"
SR = 48000
FPS = 30
CAUDA_FINAL_PADRAO = 0.25


# ---------------------------------------------------------------------------
# Utilidades de E/S de audio (sempre via FFmpeg, float32)
# ---------------------------------------------------------------------------
def decodificar(caminho: Path, canais: int = 1) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(caminho), "-f", "f32le", "-ac", str(canais), "-ar", str(SR), "-"]
    bruto = subprocess.run(cmd, check=True, capture_output=True).stdout
    arr = np.frombuffer(bruto, dtype=np.float32).copy()
    return arr.reshape(-1, canais) if canais > 1 else arr


def gravar_wav(caminho: Path, dados: np.ndarray) -> None:
    canais = 1 if dados.ndim == 1 else dados.shape[1]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", str(canais), "-ar", str(SR), "-i", "-",
           "-c:a", "pcm_s16le", str(caminho)]
    subprocess.run(cmd, check=True, input=np.ascontiguousarray(dados, dtype=np.float32).tobytes())


def norm_txt(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    return s


# ---------------------------------------------------------------------------
# 1-2. TTS com WordBoundary
# ---------------------------------------------------------------------------
async def _tts(texto: str, voz: str, rate: str, pitch: str, mp3: Path) -> list[dict]:
    import edge_tts

    com = edge_tts.Communicate(texto, voz, rate=rate, pitch=pitch, boundary="WordBoundary")
    palavras: list[dict] = []
    with mp3.open("wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                t0 = ch["offset"] / 1e7
                palavras.append({"texto": ch["text"], "t0": t0, "t1": t0 + ch["duration"] / 1e7})
    return palavras


def coletar_pronuncias_cfg(cfg: dict) -> dict[str, str]:
    """Coleta substituicoes foneticas globais (pronuncias_tts) do roteiro.json."""
    out: dict[str, str] = {}
    for orig, fon in (cfg.get("pronuncias_tts") or {}).items():
        if orig and fon:
            out[str(orig)] = str(fon)
    return out


def construir_mapa_fonetico(cfg: dict) -> dict[str, str]:
    """Mapeia palavras foneticas para a forma canonica ascii (para alinhamento Whisper)."""
    mapa: dict[str, str] = {}
    pares: list[tuple[str, str]] = list(coletar_pronuncias_cfg(cfg).items())
    for seg in cfg.get("segmentos", []):
        for orig, fon in (seg.get("substituicoes_tts") or {}).items():
            pares.append((str(orig), str(fon)))
    for orig, fon in pares:
        ow = [_ascii_norm(re.sub(r"[^\w]", "", w)) for w in orig.split() if re.sub(r"[^\w]", "", w)]
        fw = [_ascii_norm(re.sub(r"[^\w]", "", w)) for w in fon.split() if re.sub(r"[^\w]", "", w)]
        if len(ow) == len(fw):
            for o_tok, f_tok in zip(ow, fw):
                if o_tok and f_tok and o_tok != f_tok and not o_tok.isdigit():
                    mapa[f_tok] = o_tok
    return mapa


def sintetizar_segmento(seg: dict, cfg: dict, usar_cache: bool) -> tuple[np.ndarray, list[dict]]:
    pasta = BUILD / "tts"
    pasta.mkdir(parents=True, exist_ok=True)
    subs: dict[str, str] = coletar_pronuncias_cfg(cfg)
    subs.update(seg.get("substituicoes_tts") or {})
    texto_tts = seg["fala"]
    for orig, fon in subs.items():
        texto_tts = texto_tts.replace(orig, fon)
    chave = hashlib.sha1(f"{texto_tts}|{cfg['voz']}|{cfg['rate']}|{cfg.get('pitch')}".encode()).hexdigest()[:12]
    mp3 = pasta / f"{seg['id']}_{chave}.mp3"
    meta = pasta / f"{seg['id']}_{chave}.json"
    if not (usar_cache and mp3.exists() and meta.exists()):
        ultimo = None
        for tentativa in range(1, 6):
            try:
                palavras = asyncio.run(_tts(texto_tts, cfg["voz"], cfg["rate"], cfg.get("pitch", "+0Hz"), mp3))
                if not palavras or mp3.stat().st_size < 2000:
                    raise RuntimeError("edge-tts sem audio ou sem WordBoundary")
                for p in palavras:
                    for orig, fon in subs.items():
                        if norm_txt(p["texto"]) == norm_txt(fon):
                            p["texto"] = orig
                        elif fon in p["texto"]:
                            p["texto"] = p["texto"].replace(fon, orig)
                meta.write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")
                break
            except Exception as exc:  # NoAudioReceived, rede instavel etc.
                ultimo = exc
                print(f"  aviso: edge-tts falhou no segmento {seg['id']} (tentativa {tentativa}/5): {exc}")
                time.sleep(1.5 * tentativa)
        else:
            raise SystemExit(f"edge-tts indisponivel para '{seg['id']}': {ultimo}. Sem voz real nao ha video.")
    palavras = json.loads(meta.read_text(encoding="utf-8"))
    return decodificar(mp3), palavras


def anexar_pontuacao(fala: str, palavras: list[dict]) -> None:
    """Recupera a pontuacao original (!, ?, ., :, ,) de cada palavra para quebrar legendas."""
    base = norm_txt(fala)
    cursor = 0
    for p in palavras:
        alvo = norm_txt(p["texto"])
        idx = base.find(alvo, cursor)
        if idx < 0:
            p["pont"] = ""
            continue
        fim = idx + len(alvo)
        m = re.match(r"[\.\,\!\?\:\;]+", fala[fim:])
        p["pont"] = m.group(0) if m else ""
        cursor = fim


# ---------------------------------------------------------------------------
# 2B. Gemini 3.8 Flash TTS (voz Mako) + alinhamento local via faster-whisper
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-3.8-flash-tts"
GEMINI_VOICE = "Mako"
GEMINI_STYLE = (
    "narrando um vídeo viral de curiosidade com energia, ritmo acelerado e tom de surpresa "
    "seja muito expressivo na sua voz sempre que apresentar algo fale com uma tom bem grande "
    "de surpresa como se isso fosse uma grande descoberta SEJA MUITO MUITO EMPOLGADO PRA FALAR "
    "AS COISAS TENHA UMA VOZ QUE AS PESSOAS FIQUE PASMA"
)
GEMINI_THROTTLE_S = 1.5
UNIDADES_COMPOSTAS = {"metros", "metro", "quilômetros", "quilômetro", "km/h", "km/s", "km", "m"}

_UNID_PT = [
    "zero", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove",
    "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove",
]
_DEZ_PT = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CENT_PT = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _int_pt(n: int) -> list[str]:
    """Expande inteiro nao-negativo em palavras PT-BR sem acento para alinhamento Whisper."""
    if n < 0:
        return ["menos"] + _int_pt(-n)
    if n < 20:
        return [_UNID_PT[n]]
    if n < 100:
        d, u = divmod(n, 10)
        return [_DEZ_PT[d]] if u == 0 else [_DEZ_PT[d], "e", _UNID_PT[u]]
    if n == 100:
        return ["cem"]
    if n < 1000:
        c, r = divmod(n, 100)
        return [_CENT_PT[c]] if r == 0 else [_CENT_PT[c], "e"] + _int_pt(r)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        pre = ["mil"] if m == 1 else _int_pt(m) + ["mil"]
        if r == 0:
            return pre
        if r < 100 or r % 100 == 0:
            return pre + ["e"] + _int_pt(r)
        return pre + _int_pt(r)
    mi, r = divmod(n, 1_000_000)
    pre = ["um", "milhao"] if mi == 1 else _int_pt(mi) + ["milhoes"]
    if r == 0:
        return pre
    return pre + ["e"] + _int_pt(r)


def _expandir_numero_pt(chave: str) -> list[str] | None:
    if re.fullmatch(r"\d+(?:\.\d{3})+", chave):
        return _int_pt(int(chave.replace(".", "")))
    if re.fullmatch(r"\d+", chave):
        return _int_pt(int(chave))
    m_dec = re.fullmatch(r"(\d+(?:\.\d{3})*),(\d+)", chave)
    if m_dec:
        inteiro = int(m_dec.group(1).replace(".", ""))
        dec = int(m_dec.group(2))
        return _int_pt(inteiro) + ["virgula"] + _int_pt(dec)
    return None


def carregar_gemini_api_key() -> str:
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave
    env_path = Path.home() / ".gemini_tts.env"
    if env_path.exists():
        for linha in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^\s*(?:export\s+)?GEMINI_API_KEY\s*=\s*["\']?([^"\'\n]+)["\']?\s*$', linha)
            if m:
                return m.group(1).strip()
    raise SystemExit("GEMINI_API_KEY nao encontrada no ambiente nem em ~/.gemini_tts.env.")


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    bits_per_sample = 16
    rate = 24000
    for param in mime_type.split(";"):
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except ValueError:
                pass
        elif param.lower().startswith("audio/l"):
            try:
                bits_per_sample = int(param.lower().split("audio/l", 1)[1].split(";", 1)[0])
            except ValueError:
                pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    params = parse_audio_mime_type(mime_type)
    bps = params["bits_per_sample"]
    sr = params["rate"]
    ch = 1
    data_size = len(audio_data)
    bytes_per_sample = bps // 8
    block_align = ch * bytes_per_sample
    byte_rate = sr * block_align
    chunk_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1, ch, sr, byte_rate, block_align, bps, b"data", data_size,
    )
    return header + audio_data


def aplicar_pronuncias_tts(seg: dict, extras: dict[str, str] | None = None) -> str:
    texto = seg["fala"]
    subs: dict[str, str] = {}
    if extras:
        subs.update(extras)
    subs.update(seg.get("substituicoes_tts") or {})
    for orig, fon in subs.items():
        texto = texto.replace(orig, fon)
    return texto


def aparar_silencio_bordas(
    audio: np.ndarray,
    limiar_db: float = -42.0,
    folga_ini: float = 0.04,
    folga_fim: float = 0.10,
) -> np.ndarray:
    """Remove silencio morto nas pontas preservando o ataque e a cauda natural da voz."""
    if len(audio) == 0:
        return audio
    pico = float(np.max(np.abs(audio)))
    if pico < 1e-6:
        return audio
    limiar = pico * (10.0 ** (limiar_db / 20.0))
    ativos = np.flatnonzero(np.abs(audio) >= limiar)
    if len(ativos) == 0:
        return audio
    s0 = max(0, int(ativos[0]) - int(folga_ini * SR))
    s1 = min(len(audio), int(ativos[-1]) + int(folga_fim * SR))
    trecho = audio[s0:s1].copy()
    fade = min(int(0.003 * SR), len(trecho) // 4)
    if fade > 1:
        rampa = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        trecho[:fade] *= rampa
        trecho[-fade:] *= rampa[::-1]
    return trecho


def tokenizar_canonico(fala: str) -> list[dict]:
    """Quebra a fala no formato canonico de timestamps.json (unindo numero + unidade)."""
    brutos: list[tuple[str, str]] = []
    for ped in fala.strip().split():
        m = re.match(r"^(.*?)([\.\,\!\?\:\;]+)$", ped)
        if m and m.group(1):
            brutos.append((m.group(1), m.group(2)))
        else:
            brutos.append((ped, ""))
    saida: list[dict] = []
    i = 0
    while i < len(brutos):
        txt, pont = brutos[i]
        if (
            not pont
            and i + 1 < len(brutos)
            and re.match(r"^\d[\d.,]*$", txt)
            and brutos[i + 1][0].lower() in UNIDADES_COMPOSTAS
        ):
            saida.append({"texto": f"{txt} {brutos[i + 1][0]}", "pont": brutos[i + 1][1]})
            i += 2
        else:
            saida.append({"texto": txt, "pont": pont})
            i += 1
    return saida


def _ascii_norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return sem_acento.lower().strip()


def _expandir_tokens_alinhamento(texto: str, fon_map: dict[str, str] | None = None) -> list[str]:
    out: list[str] = []
    fmap = fon_map or {}
    for parte in texto.split():
        limpo = re.sub(r"^[^\w/.,]+|[^\w/.,]+$", "", parte)
        chave = _ascii_norm(limpo)
        if not chave:
            continue
        if chave == "km/h":
            out.extend(["quilometros", "por", "hora"])
            continue
        if chave == "km/s":
            out.extend(["quilometros", "por", "segundo"])
            continue
        if chave == "km":
            out.append("quilometros")
            continue
        if chave == "f1":
            out.extend(["formula", "um"])
            continue
        if chave == "m":
            out.append("metros")
            continue
        exp_num = _expandir_numero_pt(chave)
        if exp_num is not None:
            out.extend(exp_num)
            continue
        chave_alnum = re.sub(r"[^a-z0-9]", "", chave)
        if not chave_alnum:
            continue
        out.append(fmap.get(chave_alnum, chave_alnum))
    return out or [_ascii_norm(texto) or "x"]


def transcrever_whisper(wav_48k: Path, prompt_inicial: str, estado: dict) -> tuple[str, list[dict]]:
    if estado.get("whisper") is None:
        from faster_whisper import WhisperModel

        estado["whisper"] = WhisperModel("small", device="cpu", compute_type="int8")
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(wav_48k), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        check=True,
        capture_output=True,
    ).stdout
    audio16 = np.frombuffer(raw, dtype=np.float32)
    segs, _ = estado["whisper"].transcribe(
        audio16,
        language="pt",
        word_timestamps=True,
        initial_prompt=prompt_inicial,
    )
    textos: list[str] = []
    palavras: list[dict] = []
    for s in segs:
        if s.text:
            textos.append(s.text.strip())
        for w in (s.words or []):
            tok = (w.word or "").strip()
            if tok:
                palavras.append({"word": tok, "start": float(w.start), "end": float(w.end)})
    return " ".join(textos).strip(), palavras


def alinhar_palavras_whisper(
    canonicos: list[dict],
    w_words: list[dict],
    dur_seg: float,
    fon_map: dict[str, str] | None = None,
) -> list[dict]:
    """Alinha monotonicamente as palavras do Whisper sobre os tokens canonicos do roteiro."""
    c_subs: list[tuple[int, str]] = []
    for ci, c in enumerate(canonicos):
        for st in _expandir_tokens_alinhamento(c["texto"], fon_map):
            c_subs.append((ci, st))

    w_subs: list[tuple[float, float, str]] = []
    for w in w_words:
        exps = _expandir_tokens_alinhamento(w["word"], fon_map)
        dt = max(0.01, (w["end"] - w["start"]) / len(exps))
        for k, st in enumerate(exps):
            w_subs.append((w["start"] + k * dt, min(w["end"], w["start"] + (k + 1) * dt), st))

    n_c, n_w = len(c_subs), len(w_subs)
    spans: dict[int, list[tuple[float, float]]] = {i: [] for i in range(len(canonicos))}

    if n_c > 0 and n_w > 0:
        gap = -0.35
        dp = np.zeros((n_c + 1, n_w + 1), dtype=np.float64)
        bt = np.zeros((n_c + 1, n_w + 1), dtype=np.int8)
        for i in range(1, n_c + 1):
            dp[i, 0] = i * gap
            bt[i, 0] = 1
        for j in range(1, n_w + 1):
            dp[0, j] = j * gap
            bt[0, j] = 2
        for i in range(1, n_c + 1):
            cs = c_subs[i - 1][1]
            for j in range(1, n_w + 1):
                ws_tok = w_subs[j - 1][2]
                sim = 1.0 if cs == ws_tok else difflib.SequenceMatcher(None, cs, ws_tok).ratio()
                score_match = (2.0 * sim - 0.85)
                diag = dp[i - 1, j - 1] + score_match
                up = dp[i - 1, j] + gap
                left = dp[i, j - 1] + gap
                if diag >= up and diag >= left:
                    dp[i, j] = diag
                    bt[i, j] = 0
                elif up >= left:
                    dp[i, j] = up
                    bt[i, j] = 1
                else:
                    dp[i, j] = left
                    bt[i, j] = 2

        i, j = n_c, n_w
        while i > 0 and j > 0:
            mv = bt[i, j]
            if mv == 0:
                ci, cs = c_subs[i - 1]
                s0, s1, ws_tok = w_subs[j - 1]
                sim = 1.0 if cs == ws_tok else difflib.SequenceMatcher(None, cs, ws_tok).ratio()
                if sim >= 0.42:
                    spans[ci].append((s0, s1))
                i -= 1
                j -= 1
            elif mv == 1:
                i -= 1
            else:
                j -= 1

    # Monta tempos brutos com interpolacao proporcional segura para lacunas
    tempos: list[list[float] | None] = []
    for ci in range(len(canonicos)):
        if spans[ci]:
            s0 = max(0.0, min(x[0] for x in spans[ci]))
            s1 = min(dur_seg, max(x[1] for x in spans[ci]))
            tempos.append([s0, max(s0 + 0.04, s1)])
        else:
            tempos.append(None)

    # Preenche grupos nao alinhados entre vizinhos ancorados
    idx = 0
    total = len(canonicos)
    while idx < total:
        if tempos[idx] is not None:
            idx += 1
            continue
        fim_g = idx
        while fim_g < total and tempos[fim_g] is None:
            fim_g += 1
        t_esq = tempos[idx - 1][1] if idx > 0 and tempos[idx - 1] is not None else 0.0
        t_dir = tempos[fim_g][0] if fim_g < total and tempos[fim_g] is not None else dur_seg
        if t_dir <= t_esq + 0.02:
            t_dir = min(dur_seg, t_esq + 0.08 * (fim_g - idx))
        pesos = [max(1, len(canonicos[k]["texto"])) for k in range(idx, fim_g)]
        soma = sum(pesos)
        cur = t_esq
        for off, peso in enumerate(pesos):
            fatia = (t_dir - t_esq) * (peso / soma)
            tempos[idx + off] = [cur, cur + max(0.03, fatia)]
            cur += fatia
        idx = fim_g

    # Garante monotonicidade estrita dentro de [0, dur_seg]
    resultado: list[dict] = []
    prev_t0 = 0.0
    for ci, c in enumerate(canonicos):
        t0, t1 = tempos[ci] or [prev_t0, min(dur_seg, prev_t0 + 0.08)]
        t0 = max(prev_t0, min(t0, max(0.0, dur_seg - 0.02)))
        t1 = max(t0 + 0.03, min(dur_seg, t1))
        if ci + 1 < total and tempos[ci + 1] is not None:
            prox_t0 = tempos[ci + 1][0]
            if t1 > prox_t0 and prox_t0 > t0 + 0.03:
                t1 = prox_t0
        resultado.append({
            "texto": c["texto"],
            "pont": c["pont"],
            "t0": round(t0, 4),
            "t1": round(t1, 4),
        })
        prev_t0 = t0
    return resultado


def sintetizar_segmento_gemini(
    seg: dict,
    cfg: dict,
    usar_cache: bool,
    estado: dict,
) -> tuple[np.ndarray, list[dict]]:
    pasta = BUILD / "tts_cache"
    pasta.mkdir(parents=True, exist_ok=True)
    pron_cfg = coletar_pronuncias_cfg(cfg)
    fon_map = construir_mapa_fonetico(cfg)
    texto_tts = aplicar_pronuncias_tts(seg, pron_cfg)
    canonicos = tokenizar_canonico(seg["fala"])
    chave_raw = f"{GEMINI_MODEL}|{GEMINI_VOICE}|{GEMINI_STYLE}|{texto_tts}"
    chave = hashlib.sha256(chave_raw.encode("utf-8")).hexdigest()[:16]
    wav_48k = pasta / f"{seg['id']}_{chave}.wav"
    meta_words = pasta / f"{seg['id']}_{chave}.words.json"

    do_cache = usar_cache and wav_48k.exists() and wav_48k.stat().st_size > 2000
    if not do_cache:
        if estado.get("client") is None:
            from google import genai
            from google.genai import types

            estado["client"] = genai.Client(
                api_key=carregar_gemini_api_key(),
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            estado["types"] = types

        client = estado["client"]
        types = estado["types"]
        prompt = f"## Style:\n{GEMINI_STYLE}\n\n## Transcript:\n{texto_tts}"
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        gcfg = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
                )
            ),
        )

        ultimo = None
        for tentativa in range(1, 5):
            decorrido = time.monotonic() - estado.get("ultima_chamada", 0.0)
            if estado.get("ultima_chamada", 0.0) > 0.0 and decorrido < GEMINI_THROTTLE_S:
                time.sleep(GEMINI_THROTTLE_S - decorrido)
            try:
                chunks: list[bytes] = []
                mime_type = ""
                for chunk in client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=gcfg,
                ):
                    cands = getattr(chunk, "candidates", None) or []
                    if not cands or not cands[0].content or not cands[0].content.parts:
                        continue
                    for part in cands[0].content.parts:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            chunks.append(part.inline_data.data)
                            if not mime_type and part.inline_data.mime_type:
                                mime_type = part.inline_data.mime_type
                estado["ultima_chamada"] = time.monotonic()
                bruto = b"".join(chunks)
                if len(bruto) < 1000:
                    raise RuntimeError("Gemini TTS retornou audio vazio ou curto demais.")
                ext = mimetypes.guess_extension(mime_type) if mime_type else None
                tmp_raw = pasta / f"{seg['id']}_{chave}_raw{ext or '.wav'}"
                if ext is None:
                    tmp_raw.write_bytes(convert_to_wav(bruto, mime_type or "audio/L16;rate=24000"))
                else:
                    tmp_raw.write_bytes(bruto)
                audio_48 = aparar_silencio_bordas(decodificar(tmp_raw, canais=1))
                gravar_wav(wav_48k, audio_48)
                try:
                    tmp_raw.unlink()
                except OSError:
                    pass
                break
            except Exception as exc:
                estado["ultima_chamada"] = time.monotonic()
                ultimo = exc
                atraso = 2.0 ** tentativa
                print(
                    f"  aviso: Gemini TTS falhou em '{seg['id']}' (tentativa {tentativa}/4): "
                    f"{type(exc).__name__}: {exc}. Aguardando {atraso:.0f}s...",
                    flush=True,
                )
                if tentativa < 4:
                    time.sleep(atraso)
        else:
            raise SystemExit(f"Gemini TTS indisponivel para '{seg['id']}': {type(ultimo).__name__}: {ultimo}")

    audio = decodificar(wav_48k, canais=1)
    dur_seg = len(audio) / SR

    if usar_cache and do_cache and meta_words.exists():
        meta = json.loads(meta_words.read_text(encoding="utf-8"))
        ws_cache = meta.get("palavras") or []
        if [w["texto"] for w in ws_cache] == [c["texto"] for c in canonicos]:
            print(f"  [gemini] {seg['id']} ({dur_seg:.2f}s | cache): whisper=\"{meta.get('whisper_text', '')}\"", flush=True)
            return audio, ws_cache

    whisper_txt, w_words = transcrever_whisper(wav_48k, seg["fala"], estado)
    palavras = alinhar_palavras_whisper(canonicos, w_words, dur_seg, fon_map=fon_map)
    meta_words.write_text(
        json.dumps({"whisper_text": whisper_txt, "palavras": palavras}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    origem = "cache+whisper" if do_cache else "api+whisper"
    print(f"  [gemini] {seg['id']} ({dur_seg:.2f}s | {origem}): whisper=\"{whisper_txt}\"", flush=True)
    return audio, palavras


_FRASES_ESTILO_PROIBIDAS = (
    "video viral",
    "curiosidade",
    "empolgado",
    "pasma",
    "ritmo acelerado",
    "tom de surpresa",
    "grande descoberta",
)


def _alinhar_com_stats(
    canonicos: list[dict],
    w_words: list[dict],
    dur_total: float,
    fon_map: dict[str, str] | None = None,
) -> tuple[list[dict], int, int, float]:
    """Alinha globalmente tokens canonicos (com campo 'seg' opcional) contra palavras do Whisper."""
    c_subs: list[tuple[int, str]] = []
    for ci, c in enumerate(canonicos):
        for st in _expandir_tokens_alinhamento(c["texto"], fon_map):
            c_subs.append((ci, st))

    w_subs: list[tuple[float, float, str]] = []
    for w in w_words:
        exps = _expandir_tokens_alinhamento(w["word"], fon_map)
        dt = max(0.01, (w["end"] - w["start"]) / len(exps))
        for k, st in enumerate(exps):
            w_subs.append((w["start"] + k * dt, min(w["end"], w["start"] + (k + 1) * dt), st))

    n_c, n_w = len(c_subs), len(w_subs)
    spans: dict[int, list[tuple[float, float]]] = {i: [] for i in range(len(canonicos))}

    if n_c > 0 and n_w > 0:
        gap = -0.35
        dp = np.zeros((n_c + 1, n_w + 1), dtype=np.float64)
        bt = np.zeros((n_c + 1, n_w + 1), dtype=np.int8)
        for i in range(1, n_c + 1):
            dp[i, 0] = i * gap
            bt[i, 0] = 1
        for j in range(1, n_w + 1):
            dp[0, j] = j * gap
            bt[0, j] = 2
        for i in range(1, n_c + 1):
            cs = c_subs[i - 1][1]
            for j in range(1, n_w + 1):
                ws_tok = w_subs[j - 1][2]
                sim = 1.0 if cs == ws_tok else difflib.SequenceMatcher(None, cs, ws_tok).ratio()
                score_match = 2.0 * sim - 0.85
                diag = dp[i - 1, j - 1] + score_match
                up = dp[i - 1, j] + gap
                left = dp[i, j - 1] + gap
                if diag >= up and diag >= left:
                    dp[i, j] = diag
                    bt[i, j] = 0
                elif up >= left:
                    dp[i, j] = up
                    bt[i, j] = 1
                else:
                    dp[i, j] = left
                    bt[i, j] = 2

        i, j = n_c, n_w
        while i > 0 and j > 0:
            mv = bt[i, j]
            if mv == 0:
                ci, cs = c_subs[i - 1]
                s0, s1, ws_tok = w_subs[j - 1]
                sim = 1.0 if cs == ws_tok else difflib.SequenceMatcher(None, cs, ws_tok).ratio()
                if sim >= 0.42:
                    spans[ci].append((s0, s1))
                i -= 1
                j -= 1
            elif mv == 1:
                i -= 1
            else:
                j -= 1

    matched = sum(1 for ci in range(len(canonicos)) if spans[ci])
    total = len(canonicos)
    ratio = matched / total if total else 0.0

    tempos: list[list[float] | None] = []
    for ci in range(total):
        if spans[ci]:
            s0 = max(0.0, min(x[0] for x in spans[ci]))
            s1 = min(dur_total, max(x[1] for x in spans[ci]))
            tempos.append([s0, max(s0 + 0.04, s1)])
        else:
            tempos.append(None)

    idx = 0
    while idx < total:
        if tempos[idx] is not None:
            idx += 1
            continue
        fim_g = idx
        while fim_g < total and tempos[fim_g] is None:
            fim_g += 1
        t_esq = tempos[idx - 1][1] if idx > 0 and tempos[idx - 1] is not None else 0.0
        t_dir = tempos[fim_g][0] if fim_g < total and tempos[fim_g] is not None else dur_total
        if t_dir <= t_esq + 0.02:
            t_dir = min(dur_total, t_esq + 0.08 * (fim_g - idx))
        pesos = [max(1, len(canonicos[k]["texto"])) for k in range(idx, fim_g)]
        soma = sum(pesos)
        cur = t_esq
        for off, peso in enumerate(pesos):
            fatia = (t_dir - t_esq) * (peso / soma)
            tempos[idx + off] = [cur, cur + max(0.03, fatia)]
            cur += fatia
        idx = fim_g

    resultado: list[dict] = []
    prev_t0 = 0.0
    for ci, c in enumerate(canonicos):
        t0, t1 = tempos[ci] or [prev_t0, min(dur_total, prev_t0 + 0.08)]
        t0 = max(prev_t0, min(t0, max(0.0, dur_total - 0.02)))
        t1 = max(t0 + 0.03, min(dur_total, t1))
        if ci + 1 < total and tempos[ci + 1] is not None:
            prox_t0 = tempos[ci + 1][0]
            if t1 > prox_t0 and prox_t0 > t0 + 0.03:
                t1 = prox_t0
        item = {
            "texto": c["texto"],
            "pont": c["pont"],
            "t0": round(t0, 4),
            "t1": round(t1, 4),
        }
        if "seg" in c:
            item["seg"] = c["seg"]
        resultado.append(item)
        prev_t0 = t0
    return resultado, matched, total, ratio


def _derivar_segmentos_contiguos(
    cfg_segs: list[dict],
    palavras: list[dict],
    dur_total: float,
) -> list[dict]:
    """Deriva limites contiguos [t0, t1] em [0.0, dur_total] usando pontos medios entre segmentos."""
    por_seg: dict[str, list[dict]] = {s["id"]: [] for s in cfg_segs}
    for p in palavras:
        por_seg[p["seg"]].append(p)

    n_segs = len(cfg_segs)
    bordas = [0.0] * (n_segs + 1)
    bordas[0] = 0.0
    bordas[-1] = round(dur_total, 4)

    for i in range(n_segs - 1):
        ws_a = por_seg[cfg_segs[i]["id"]]
        ws_b = por_seg[cfg_segs[i + 1]["id"]]
        fim_a = ws_a[-1]["t1"]
        ini_b = ws_b[0]["t0"]
        meio = round((fim_a + ini_b) / 2.0, 4)
        min_borda = round(max(bordas[i] + 0.05, ws_a[-1]["t0"] + 0.03), 4)
        max_borda = round(min(dur_total - 0.05, ws_b[0]["t1"] - 0.03), 4)
        meio = max(min_borda, min(meio, max_borda))
        bordas[i + 1] = meio
        if ws_a[-1]["t1"] > meio:
            ws_a[-1]["t1"] = meio
        if ws_b[0]["t0"] < meio:
            ws_b[0]["t0"] = meio

    segmentos: list[dict] = []
    for i, seg in enumerate(cfg_segs):
        t0, t1 = bordas[i], bordas[i + 1]
        for p in por_seg[seg["id"]]:
            p["t0"] = round(max(t0, min(p["t0"], t1 - 0.02)), 4)
            p["t1"] = round(max(p["t0"] + 0.02, min(p["t1"], t1)), 4)
        segmentos.append({"id": seg["id"], "fala": seg["fala"], "t0": t0, "t1": t1})
    return segmentos


def validar_lote_qualidade(
    cfg: dict,
    whisper_txt: str,
    palavras: list[dict],
    segmentos: list[dict],
    dur_total: float,
    matched: int,
    total: int,
    ratio: float,
) -> None:
    """Gate estrito antes de gravar outputs em --mode batch."""
    w_norm = _ascii_norm(whisper_txt)
    for frase in _FRASES_ESTILO_PROIBIDAS:
        if frase in w_norm:
            raise SystemExit(
                f"GATE LOTE FALHOU: possivel vazamento da instrucao de estilo na fala ('{frase}'): {whisper_txt!r}"
            )
    if ratio < 0.85:
        raise SystemExit(
            f"GATE LOTE FALHOU: taxa de alinhamento {matched}/{total} ({ratio * 100:.1f}%) abaixo de 85.0%."
        )
    todos_textos = " ".join(p["texto"] for p in palavras)
    fala_total = " ".join(seg["fala"] for seg in cfg["segmentos"])
    pares_pron: list[tuple[str, str]] = list(coletar_pronuncias_cfg(cfg).items())
    for seg in cfg["segmentos"]:
        for orig, fon in (seg.get("substituicoes_tts") or {}).items():
            pares_pron.append((str(orig), str(fon)))
    for orig, fon in pares_pron:
        if orig not in fala_total or orig == fon:
            continue
        if orig not in todos_textos:
            raise SystemExit(f"GATE LOTE FALHOU: grafia canonica ausente em palavras: '{orig}'.")
        if fon not in fala_total and fon in todos_textos:
            raise SystemExit(f"GATE LOTE FALHOU: grafia fonetica vazou para palavras: '{fon}'.")
        for f_tok in fon.split():
            if f_tok not in fala_total and f_tok in todos_textos:
                raise SystemExit(f"GATE LOTE FALHOU: termo fonetico vazou para palavras: '{f_tok}'.")
    if not segmentos or segmentos[0]["t0"] != 0.0 or abs(segmentos[-1]["t1"] - dur_total) > 1e-3:
        raise SystemExit("GATE LOTE FALHOU: limites externos dos segmentos nao cobrem [0.0, duracao].")
    seg_map = {s["id"]: s for s in segmentos}
    for i, s in enumerate(segmentos):
        if not (s["t1"] > s["t0"]):
            raise SystemExit(f"GATE LOTE FALHOU: segmento '{s['id']}' com tempo invalido ({s['t0']}..{s['t1']}).")
        if i + 1 < len(segmentos) and abs(s["t1"] - segmentos[i + 1]["t0"]) > 1e-4:
            raise SystemExit(f"GATE LOTE FALHOU: lacuna/sobreposicao entre '{s['id']}' e '{segmentos[i + 1]['id']}'.")
    prev_t0 = -1.0
    for p in palavras:
        s = seg_map[p["seg"]]
        if not (s["t0"] - 1e-4 <= p["t0"] < p["t1"] <= s["t1"] + 1e-4):
            raise SystemExit(f"GATE LOTE FALHOU: palavra fora do intervalo do segmento: {p} vs {s}")
        if p["t0"] < prev_t0 - 1e-4:
            raise SystemExit(f"GATE LOTE FALHOU: ordem nao monotonica em {p}")
        prev_t0 = p["t0"]
    for seg in cfg["segmentos"]:
        for d in seg.get("sfx", []):
            if "palavra" in d:
                achar_palavra(palavras, seg["id"], d["palavra"])


def sintetizar_lote_gemini(
    cfg: dict,
    usar_cache: bool,
    estado: dict,
) -> tuple[np.ndarray, list[dict], list[dict], float, float, dict]:
    """Sintetiza o roteiro inteiro em 1 unica chamada Gemini TTS + alinhamento global Whisper."""
    pasta = BUILD / "tts_cache"
    pasta.mkdir(parents=True, exist_ok=True)
    pron_cfg = coletar_pronuncias_cfg(cfg)
    fon_map = construir_mapa_fonetico(cfg)
    linhas_tts = [aplicar_pronuncias_tts(seg, pron_cfg) for seg in cfg["segmentos"]]
    texto_tts_completo = "\n".join(linhas_tts)
    texto_canonico_completo = " ".join(seg["fala"] for seg in cfg["segmentos"])

    chave_raw = f"batch|{GEMINI_MODEL}|{GEMINI_VOICE}|{GEMINI_STYLE}|{texto_tts_completo}"
    chave = hashlib.sha256(chave_raw.encode("utf-8")).hexdigest()[:16]
    wav_48k = pasta / f"batch_{chave}.wav"
    meta_whisper = pasta / f"batch_{chave}.whisper.json"

    do_cache = usar_cache and wav_48k.exists() and wav_48k.stat().st_size > 4000
    print(f"TTS [gemini/batch] 1 chamada para {len(cfg['segmentos'])} segmentos (cache={do_cache})", flush=True)

    if not do_cache:
        if estado.get("client") is None:
            from google import genai
            from google.genai import types

            estado["client"] = genai.Client(
                api_key=carregar_gemini_api_key(),
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            estado["types"] = types

        client = estado["client"]
        types = estado["types"]
        prompt = f"## Style:\n{GEMINI_STYLE}\n\n## Transcript:\n{texto_tts_completo}"
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        gcfg = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
                )
            ),
        )

        ultimo = None
        for tentativa in range(1, 5):
            try:
                chunks: list[bytes] = []
                mime_type = ""
                for chunk in client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=gcfg,
                ):
                    cands = getattr(chunk, "candidates", None) or []
                    if not cands or not cands[0].content or not cands[0].content.parts:
                        continue
                    for part in cands[0].content.parts:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            chunks.append(part.inline_data.data)
                            if not mime_type and part.inline_data.mime_type:
                                mime_type = part.inline_data.mime_type
                bruto = b"".join(chunks)
                if len(bruto) < 4000:
                    raise RuntimeError("Gemini TTS batch retornou audio vazio ou curto demais.")
                ext = mimetypes.guess_extension(mime_type) if mime_type else None
                tmp_raw = pasta / f"batch_{chave}_raw{ext or '.wav'}"
                if ext is None:
                    tmp_raw.write_bytes(convert_to_wav(bruto, mime_type or "audio/L16;rate=24000"))
                else:
                    tmp_raw.write_bytes(bruto)
                audio_48 = aparar_silencio_bordas(decodificar(tmp_raw, canais=1), limiar_db=-42.0, folga_ini=0.04, folga_fim=0.12)
                gravar_wav(wav_48k, audio_48)
                try:
                    tmp_raw.unlink()
                except OSError:
                    pass
                break
            except Exception as exc:
                ultimo = exc
                msg = str(exc)
                if "GenerateRequestsPerDay" in msg:
                    raise SystemExit(f"Gemini TTS batch atingiu cota diaria (429): {type(exc).__name__}: {exc}")
                atraso = 2.0 ** tentativa
                print(
                    f"  aviso: Gemini TTS batch falhou (tentativa {tentativa}/4): "
                    f"{type(exc).__name__}: {exc}. Aguardando {atraso:.0f}s...",
                    flush=True,
                )
                if tentativa < 4:
                    time.sleep(atraso)
        else:
            raise SystemExit(f"Gemini TTS batch indisponivel: {type(ultimo).__name__}: {ultimo}")

    voz_bruta = decodificar(wav_48k, canais=1)
    voz, removido = remover_silencio_inicial_ffmpeg(voz_bruta)
    wav_sr = BUILD / "voz_sr.wav"

    if usar_cache and do_cache and meta_whisper.exists():
        mw = json.loads(meta_whisper.read_text(encoding="utf-8"))
        whisper_txt = mw["whisper_text"]
        w_words = mw["w_words"]
        origem = "cache"
    else:
        whisper_txt, w_words = transcrever_whisper(wav_sr, texto_canonico_completo, estado)
        meta_whisper.write_text(
            json.dumps({"whisper_text": whisper_txt, "w_words": w_words}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        origem = "cache+whisper" if do_cache else "api+whisper"

    print(f"  [gemini/batch] ({len(voz) / SR:.2f}s | {origem}): whisper=\"{whisper_txt}\"", flush=True)

    canonicos_flat: list[dict] = []
    for seg in cfg["segmentos"]:
        for tok in tokenizar_canonico(seg["fala"]):
            canonicos_flat.append({"seg": seg["id"], "texto": tok["texto"], "pont": tok["pont"]})

    dur_fala = len(voz) / SR
    palavras, matched, total, ratio = _alinhar_com_stats(canonicos_flat, w_words, dur_fala, fon_map=fon_map)

    cauda = float(cfg.get("cauda_final", CAUDA_FINAL_PADRAO))
    fim_fala = palavras[-1]["t1"] if palavras else dur_fala
    dur = max(fim_fala + cauda, min(dur_fala, fim_fala + cauda + 0.08))
    dur = round(np.ceil(dur * FPS) / FPS, 4)
    segmentos = _derivar_segmentos_contiguos(cfg["segmentos"], palavras, dur)

    validar_lote_qualidade(cfg, whisper_txt, palavras, segmentos, dur, matched, total, ratio)
    info = {
        "matched": matched,
        "total": total,
        "ratio": ratio,
        "origem": origem,
        "whisper_text": whisper_txt,
    }
    return voz, palavras, segmentos, dur, removido, info


# ---------------------------------------------------------------------------
# 3. Compressao de pausas internas guiada pelos limites das palavras
# ---------------------------------------------------------------------------
def comprimir_pausas(audio: np.ndarray, palavras: list[dict], pausa_max: float) -> tuple[np.ndarray, list[dict]]:
    pos_fala, pre_fala = 0.09, 0.06  # mantem a cauda da palavra e o ataque da proxima
    faixas: list[list[float]] = []
    ini = max(0.0, palavras[0]["t0"] - 0.03)
    for a, b in zip(palavras, palavras[1:]):
        if b["t0"] - a["t1"] > pausa_max:
            faixas.append([ini, a["t1"] + pos_fala])
            ini = b["t0"] - pre_fala
    faixas.append([ini, min(len(audio) / SR, palavras[-1]["t1"] + 0.16)])

    pedacos, offsets, acum = [], [], 0.0
    fade = int(0.003 * SR)
    for a, b in faixas:
        s0, s1 = int(round(a * SR)), int(round(b * SR))
        trecho = audio[s0:s1].copy()
        if len(trecho) > 2 * fade:
            rampa = np.linspace(0, 1, fade, dtype=np.float32)
            trecho[:fade] *= rampa
            trecho[-fade:] *= rampa[::-1]
        pedacos.append(trecho)
        offsets.append((a, b, acum))
        acum += len(trecho) / SR

    def mapear(t: float) -> float:
        for a, b, off in offsets:
            if a - 1e-6 <= t <= b + 1e-6:
                return off + (t - a)
        # fora das faixas: prende ao limite mais proximo
        melhor = min(offsets, key=lambda o: min(abs(t - o[0]), abs(t - o[1])))
        return melhor[2] + (min(max(t, melhor[0]), melhor[1]) - melhor[0])

    novas = []
    for p in palavras:
        q = dict(p)
        q["t0"], q["t1"] = mapear(p["t0"]), mapear(p["t1"])
        novas.append(q)
    return np.concatenate(pedacos), novas


def remover_silencio_inicial_ffmpeg(voz: np.ndarray) -> tuple[np.ndarray, float]:
    """FFmpeg silenceremove no inicio: garante fala imediata em 0.0s e devolve o deslocamento medido."""
    ent, sai = BUILD / "voz_bruta.wav", BUILD / "voz_sr.wav"
    gravar_wav(ent, voz)
    filtro = "silenceremove=start_periods=1:start_duration=0:start_threshold=-42dB:detection=peak"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ent), "-af", filtro, "-ar", str(SR), str(sai)], check=True)
    nova = decodificar(sai)
    removido = (len(voz) - len(nova)) / SR
    return nova, max(0.0, removido)


# ---------------------------------------------------------------------------
# 5. Sintese de SFX (numpy puro, semente fixa)
# ---------------------------------------------------------------------------
RNG = np.random.default_rng(20261126)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _ruido(n: int) -> np.ndarray:
    return RNG.standard_normal(n).astype(np.float32)


def _passa_baixa(x: np.ndarray, corte) -> np.ndarray:
    """Passa-baixa de 1 polo com corte fixo ou variavel (array em Hz)."""
    corte = np.broadcast_to(np.asarray(corte, dtype=np.float64), x.shape)
    a = 1.0 - np.exp(-2 * np.pi * corte / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def _passa_alta(x: np.ndarray, corte: float) -> np.ndarray:
    return x - _passa_baixa(x, corte)


def _env(n: int, ataque: float, decaimento: float) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(ataque, 1e-4)) * np.exp(-np.maximum(0, t - ataque) / max(decaimento, 1e-4))
    return e.astype(np.float32)


def sfx_boom(dur=1.2, grave=1.0):
    t = _t(dur)
    f = 38 + 110 * np.exp(-t / 0.09)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.45 * grave))
    corpo = _passa_baixa(_ruido(len(t)), 900) * np.exp(-t / 0.12) * 2.5
    clique = _ruido(len(t)) * np.exp(-t / 0.006) * 0.6
    return (sub * 1.0 + corpo + clique).astype(np.float32)


def sfx_boom_leve():
    return sfx_boom(0.7, 0.5) * 0.7


def sfx_stamp():
    t = _t(0.35)
    golpe = _passa_baixa(_ruido(len(t)), 2500) * np.exp(-t / 0.03)
    tom = np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.1)
    return (golpe * 1.6 + tom).astype(np.float32)


def sfx_whoosh(dur=0.9, f0=240, f1=1700):
    t = _t(dur)
    fase = t / dur
    corte = f0 + (f1 - f0) * np.sin(np.pi * np.minimum(fase * 1.15, 1.0)) ** 2
    x = _passa_baixa(_passa_baixa(_ruido(len(t)), corte), 1500)
    x = _passa_alta(x, 110)
    env = np.sin(np.pi * fase) ** 1.6
    return (x * env * 1.8).astype(np.float32)


def sfx_whoosh_curto():
    return sfx_whoosh(0.45, 280, 1500) * 0.8


def sfx_pouso():
    t = _t(0.3)
    return (np.sin(2 * np.pi * 70 * t) * np.exp(-t / 0.06) + _passa_baixa(_ruido(len(t)), 500) * np.exp(-t / 0.04)).astype(np.float32)


def sfx_badge():
    t = _t(0.22)
    tom = np.sin(2 * np.pi * 1100 * t) * np.exp(-t / 0.05) + 0.4 * np.sin(2 * np.pi * 1650 * t) * np.exp(-t / 0.03)
    return (tom * 0.45).astype(np.float32)


def sfx_tique():
    t = _t(0.6)
    out = np.zeros(len(t), dtype=np.float32)
    for k in range(6):
        s = int(k * 0.08 * SR)
        n = int(0.03 * SR)
        tt = np.arange(n) / SR
        out[s:s + n] += (np.sin(2 * np.pi * (1200 + 90 * k) * tt) * np.exp(-tt / 0.008)).astype(np.float32)
    return out * 0.45


def sfx_ding():
    t = _t(2.0)
    parciais = [(1.0, 1.0, 1.4), (2.76, 0.35, 0.7), (5.4, 0.12, 0.3)]
    f = 784
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in parciais)
    return _passa_baixa((x * 0.4).astype(np.float32), 2400)


def sfx_flashes():
    out = np.zeros(int(1.4 * SR), dtype=np.float32)
    for k in range(9):
        s = int(RNG.uniform(0, 1.2) * SR)
        n = int(0.05 * SR)
        tt = np.arange(n) / SR
        burst = _passa_baixa(_passa_alta(_ruido(n), 800), 2000)
        out[s:s + n] += burst * np.exp(-tt / 0.006) * 0.45
    return out


def sfx_susto():
    t = _t(0.7)
    f = 420 + 260 * np.exp(-t / 0.2)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.14 * np.exp(-t / 0.25)
    return _passa_baixa(x.astype(np.float32), 1400)


def sfx_vento(dur=3.2):
    t = _t(dur)
    mod = 0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t) * np.sin(2 * np.pi * 0.23 * t + 1)
    corte = 260 + 420 * mod
    x = _passa_baixa(_passa_alta(_passa_baixa(_ruido(len(t)), corte), 120), 900)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (dur - t) / 0.6)
    return (x * mod * env * 1.4).astype(np.float32)


def sfx_passaros():
    out = np.zeros(int(1.6 * SR), dtype=np.float32)
    for k in range(14):
        s = int(RNG.uniform(0, 1.3) * SR)
        n = int(RNG.uniform(0.05, 0.12) * SR)
        tt = np.arange(n) / SR
        f0 = RNG.uniform(1500, 2300)
        f = f0 + 500 * np.sin(2 * np.pi * RNG.uniform(16, 26) * tt)
        out[s:s + n] += (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / tt[-1]) * 0.22).astype(np.float32)
    return _passa_baixa(out, 2400)


def sfx_jato_estereo(dur=2.6):
    """Jato com Doppler e pan esquerda->direita (filtrado para nao mascarar a voz). Retorna (n, 2)."""
    t = _t(dur)
    x_pos = (t / dur - 0.5) * 2  # -1 .. 1
    dist = np.sqrt(x_pos ** 2 + 0.12)
    v_rad = x_pos / dist  # componente de afastamento
    doppler = 1.0 / (1.0 + 0.35 * v_rad)
    turbina = np.sin(2 * np.pi * np.cumsum(640 * doppler) / SR) * 0.09
    turbina += np.sin(2 * np.pi * np.cumsum(1280 * doppler) / SR) * 0.03
    rugido = _passa_baixa(_ruido(len(t)), 420 + 680 * (1 - np.abs(x_pos)))
    rugido = _passa_baixa(_passa_alta(rugido, 65), 1200) * 1.4
    amp = (1.0 / dist) / (1.0 / np.sqrt(0.12))
    mono = _passa_baixa(((turbina + rugido) * amp).astype(np.float32), 1400)
    pan = (x_pos + 1) / 2
    return np.stack([mono * np.cos(pan * np.pi / 2), mono * np.sin(pan * np.pi / 2)], axis=1) * 0.95


def sfx_alarme(n_bips=6):
    out = []
    for k in range(n_bips):
        tt = _t(0.16)
        f = 620 if k % 2 == 0 else 480
        onda = np.sin(2 * np.pi * f * tt) + 0.12 * np.sin(4 * np.pi * f * tt)
        bip = onda * 0.15 * np.minimum(1, tt / 0.01) * np.minimum(1, (0.16 - tt) / 0.015)
        out.append(_passa_baixa(bip.astype(np.float32), 1300))
        out.append(np.zeros(int(0.08 * SR), dtype=np.float32))
    return np.concatenate(out)


def sfx_alarme_curto():
    return sfx_alarme(3)


def sfx_drone(dur=4.2):
    t = _t(dur)
    x = np.sin(2 * np.pi * 55 * t) + 0.6 * np.sin(2 * np.pi * 55.7 * t) + 0.3 * np.sin(2 * np.pi * 110.4 * t)
    env = np.minimum(1, t / 0.5) * np.minimum(1, (dur - t) / 0.8)
    return (x * env * 0.28).astype(np.float32)


def sfx_cristal():
    t = _t(1.0)
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, d in [(1046, 0.5), (1568, 0.35), (2093, 0.22)])
    return _passa_baixa((x * 0.12).astype(np.float32), 2000)


def sfx_riser(dur=1.2):
    t = _t(dur)
    fase = t / dur
    f = 160 * (2 ** (fase * 2.5))
    tom = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.2
    ru = _passa_baixa(_ruido(len(t)), 260 + 2200 * fase ** 2) * 0.85
    env = fase ** 1.8
    corte_fim = np.minimum(1, (dur - t) / 0.02)
    return _passa_baixa(((tom + ru) * env * corte_fim).astype(np.float32), 2000)


def sfx_drop():
    return sfx_boom(1.6, 1.6) * 1.15 + np.pad(sfx_stamp(), (0, int(1.6 * SR) - int(0.35 * SR)))


def sfx_fogo(dur=2.6):
    t = _t(dur)
    ru = _passa_baixa(_ruido(len(t)), 220) * 2.8
    estalos = (RNG.random(len(t)) > 0.9993).astype(np.float32) * _ruido(len(t)) * 0.7
    estalos = _passa_baixa(estalos, 1500)
    env = np.minimum(1, t / 0.05) * np.minimum(1, (dur - t) / 0.7)
    return ((ru + estalos) * env).astype(np.float32)


def sfx_sirene(dur=1.15):
    """Sirene policial estilizada (passa-baixa para nao disputar brilho com a voz)."""
    t = _t(dur)
    f = 690 + 180 * np.sin(2 * np.pi * 2.4 * t)
    onda = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.18 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    env = np.minimum(1, t / 0.08) * np.minimum(1, (dur - t) / 0.22)
    return _passa_baixa((onda * env * 0.26).astype(np.float32), 1400)


def sfx_motor_f1(dur=1.55):
    """Passagem Doppler de carro de Formula 1 em estereo (esquerda -> direita)."""
    t = _t(dur)
    x_pos = (t / dur - 0.48) * 2.0
    dist = np.sqrt(x_pos ** 2 + 0.14)
    v_rad = x_pos / dist
    doppler = 1.0 / (1.0 + 0.42 * v_rad)
    f_base = 340 * doppler
    motor = (
        0.55 * np.sin(2 * np.pi * np.cumsum(f_base) / SR)
        + 0.30 * np.sin(2 * np.pi * np.cumsum(2 * f_base) / SR)
        + 0.14 * np.sin(2 * np.pi * np.cumsum(3 * f_base) / SR)
    )
    ar = _passa_baixa(_passa_alta(_ruido(len(t)), 140), 1200) * 0.55
    amp = (1.0 / dist) / (1.0 / np.sqrt(0.14))
    env = np.minimum(1, t / 0.08) * np.minimum(1, (dur - t) / 0.25)
    mono = _passa_baixa(((motor * 0.38 + ar) * amp * env).astype(np.float32), 1650)
    pan = np.clip((x_pos + 1.0) / 2.0, 0.0, 1.0)
    return np.stack([mono * np.cos(pan * np.pi / 2), mono * np.sin(pan * np.pi / 2)], axis=1)


def sfx_sonic_boom(dur=1.25):
    """Estouro sonico duplo (onda N) + leve tilintar de vidro filtrado."""
    t = _t(dur)
    sub1 = np.sin(2 * np.pi * np.cumsum(36 + 130 * np.exp(-t / 0.06)) / SR) * np.exp(-t / 0.35)
    t2 = np.maximum(0.0, t - 0.085)
    sub2 = np.sin(2 * np.pi * np.cumsum(42 + 95 * np.exp(-t2 / 0.07)) / SR) * np.exp(-t2 / 0.32) * (t >= 0.085)
    onda = _passa_baixa(_ruido(len(t)), 850) * np.exp(-t / 0.11) * 2.2
    vidro = np.zeros(len(t), dtype=np.float32)
    for k in range(10):
        s = int((0.10 + RNG.uniform(0.0, 0.35)) * SR)
        n = int(0.045 * SR)
        if s + n <= len(t):
            tt = np.arange(n) / SR
            f = RNG.uniform(1300, 2200)
            vidro[s:s + n] += (np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.014) * 0.16).astype(np.float32)
    return _passa_baixa((sub1 * 0.95 + sub2 * 0.75 + onda + vidro).astype(np.float32), 2100)


def sfx_trovao(dur=1.5):
    """Estalo eletrico + trovao grave filtrado para raios congelados."""
    t = _t(dur)
    estalo = _passa_baixa(_passa_alta(_ruido(len(t)), 500), 1900) * np.exp(-t / 0.045) * 1.4
    ronco = _passa_baixa(_ruido(len(t)), 190) * np.exp(-t / 0.55) * 3.0
    sub = np.sin(2 * np.pi * 48 * t) * np.exp(-t / 0.45) * 0.6
    return (estalo + ronco + sub).astype(np.float32)


def sfx_explosao(dur=2.2):
    """Impacto nuclear grave com onda de choque profunda (passa-baixa limpa)."""
    t = _t(dur)
    f = 28 + 125 * np.exp(-t / 0.11)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.85) * 1.2
    choque = _passa_baixa(_ruido(len(t)), 620) * np.exp(-t / 0.22) * 2.6
    cauda = _passa_baixa(_ruido(len(t)), 160) * np.minimum(1, t / 0.08) * np.exp(-t / 0.9) * 2.2
    return _passa_baixa((sub + choque + cauda).astype(np.float32), 1250)


SFX = {
    "boom": sfx_boom, "boom_leve": sfx_boom_leve, "stamp": sfx_stamp, "whoosh": sfx_whoosh,
    "whoosh_curto": sfx_whoosh_curto, "pouso": sfx_pouso, "badge": sfx_badge, "tique": sfx_tique,
    "ding": sfx_ding, "flashes": sfx_flashes, "susto": sfx_susto, "vento": sfx_vento,
    "passaros": sfx_passaros, "jato": sfx_jato_estereo, "alarme": sfx_alarme,
    "alarme_curto": sfx_alarme_curto, "drone": sfx_drone, "cristal": sfx_cristal,
    "riser": sfx_riser, "drop": sfx_drop, "fogo": sfx_fogo,
    "sirene": sfx_sirene, "motor_f1": sfx_motor_f1, "sonic_boom": sfx_sonic_boom,
    "trovao": sfx_trovao, "explosao": sfx_explosao,
}


def somar(trilha: np.ndarray, som: np.ndarray, t: float, ganho: float) -> None:
    s0 = max(0, int(round(t * SR)))
    if som.ndim == 1:
        som = np.stack([som, som], axis=1)
    n = min(len(som), len(trilha) - s0)
    if n > 0:
        trilha[s0:s0 + n] += som[:n] * ganho


# ---------------------------------------------------------------------------
# Pulso energetico (cama) com ducking sob a voz
# ---------------------------------------------------------------------------
def gerar_cama(dur: float, voz: np.ndarray, zonas: dict) -> np.ndarray:
    n = int(round(dur * SR))
    cama = np.zeros(n, dtype=np.float32)
    bpm = 124
    passo = 60 / bpm
    kick_t = _t(0.25)
    kick = (np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-kick_t / 0.03)) / SR) * np.exp(-kick_t / 0.12)).astype(np.float32)
    hat_n = int(0.04 * SR)
    hat_base = _passa_alta(_ruido(hat_n), 6000) * np.exp(-np.arange(hat_n) / SR / 0.012)
    baixo_notas = [55.0, 55.0, 65.41, 49.0]  # A1 A1 C2 G1
    k = 0
    tb = 0.0
    while tb < dur:
        s = int(tb * SR)
        m = min(len(kick), n - s)
        if m > 0:
            cama[s:s + m] += kick[:m] * 0.9
        so = int((tb + passo / 2) * SR)
        m = min(hat_n, n - so)
        if m > 0:
            cama[so:so + m] += hat_base[:m] * 0.35
        nota = baixo_notas[(k // 4) % 4]
        bt = _t(passo * 0.9)
        baixo = np.sin(2 * np.pi * nota * bt) * np.exp(-bt / 0.25) * 0.35
        m = min(len(baixo), n - s)
        if m > 0:
            cama[s:s + m] += baixo[:m].astype(np.float32)
        tb += passo
        k += 1
    # ducking: envelope da voz suavizado
    env = np.abs(np.pad(voz, (0, max(0, n - len(voz))))[:n])
    janela = int(0.05 * SR)
    env = np.convolve(env, np.ones(janela) / janela, mode="same")
    env = env / (env.max() + 1e-9)
    duck = 1.0 - 0.55 * np.clip(env * 4, 0, 1)
    # zonas: silencio total antes do payoff, cama reduzida no espaco/climax
    ganho = np.ones(n, dtype=np.float32)
    tt = np.arange(n) / SR
    for a, b, g in zonas["ganhos"]:
        sel = (tt >= a) & (tt < b)
        ganho[sel] = g
    ganho = np.convolve(ganho, np.ones(int(0.04 * SR)) / int(0.04 * SR), mode="same")
    return (cama * duck * ganho).astype(np.float32)


# ---------------------------------------------------------------------------
# 6. Loudnorm em duas passadas
# ---------------------------------------------------------------------------
def loudnorm_2p(ent: Path, sai: Path, alvo=-14.0, tp=-1.5, lra=11.0) -> dict:
    base = f"loudnorm=I={alvo}:TP={tp}:LRA={lra}"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(ent), "-af", base + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    med = json.loads(m.group(0))
    filtro = (f"{base}:measured_I={med['input_i']}:measured_TP={med['input_tp']}:measured_LRA={med['input_lra']}"
              f":measured_thresh={med['input_thresh']}:offset={med['target_offset']}:linear=true:print_format=json")
    r2 = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(ent), "-af", filtro, "-ar", str(SR), "-c:a", "pcm_s16le", str(sai)],
                        capture_output=True, text=True, check=True)
    m2 = re.search(r"\{[^{}]*\"output_i\"[^{}]*\}", r2.stderr, re.S)
    return json.loads(m2.group(0)) if m2 else {}


# ---------------------------------------------------------------------------
def achar_palavra(palavras: list[dict], seg_id: str, alvo: str) -> dict:
    a = norm_txt(alvo)
    for p in palavras:
        if p["seg"] != seg_id:
            continue
        txt = norm_txt(p["texto"])
        if txt == a or txt.startswith(a + " "):
            return p
    raise SystemExit(f"Palavra-ancora '{alvo}' nao encontrada no segmento '{seg_id}'.")


def main() -> None:
    global EP_DIR, BUILD
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", default=str(EP_PADRAO), help="diretorio do episodio (padrao: fabrica_v2/episodios/ep01_velocidade)")
    ap.add_argument("--engine", choices=["gemini", "edge"], default="gemini", help="motor TTS (padrao: gemini)")
    ap.add_argument(
        "--mode",
        choices=["segment", "batch"],
        default=None,
        help="modo de sintese para Gemini TTS (padrao: batch quando --engine gemini; ignorado em --engine edge)",
    )
    ap.add_argument("--sem-cache", action="store_true", help="forca nova sintese TTS")
    args = ap.parse_args()

    EP_DIR = Path(args.ep).resolve()
    BUILD = EP_DIR / "build"
    BUILD.mkdir(parents=True, exist_ok=True)
    roteiro_path = EP_DIR / "roteiro.json"
    if not roteiro_path.exists():
        raise SystemExit(f"Roteiro nao encontrado: {roteiro_path}")
    cfg = json.loads(roteiro_path.read_text(encoding="utf-8"))
    pmax = float(cfg.get("pausa_max_interna", 0.15))
    modo = (args.mode or "batch") if args.engine == "gemini" else "segment"

    estado_gemini: dict = {"client": None, "whisper": None, "ultima_chamada": 0.0}
    info_lote: dict = {}

    if args.engine == "gemini" and modo == "batch":
        voz, palavras, segmentos, dur, removido, info_lote = sintetizar_lote_gemini(
            cfg,
            usar_cache=not args.sem_cache,
            estado=estado_gemini,
        )
    else:
        pedacos, palavras, segmentos, cursor = [], [], [], 0.0
        for seg in cfg["segmentos"]:
            print(f"TTS [{args.engine}/{modo}] {seg['id']}: {seg['fala']}", flush=True)
            if args.engine == "gemini":
                audio, ws = sintetizar_segmento_gemini(seg, cfg, usar_cache=not args.sem_cache, estado=estado_gemini)
            else:
                audio, ws = sintetizar_segmento(seg, cfg, usar_cache=not args.sem_cache)
                anexar_pontuacao(seg["fala"], ws)
            audio_c, ws_c = comprimir_pausas(audio, ws, pmax)
            for p in ws_c:
                palavras.append({"texto": p["texto"], "pont": p.get("pont", ""), "t0": cursor + p["t0"],
                                 "t1": cursor + p["t1"], "seg": seg["id"]})
            dur_seg = len(audio_c) / SR
            segmentos.append({"id": seg["id"], "fala": seg["fala"], "t0": cursor, "t1": cursor + dur_seg})
            pausa = float(seg.get("pausa_depois", cfg.get("pausa_entre_segmentos", 0.15)))
            pedacos.append(audio_c)
            pedacos.append(np.zeros(int(round(pausa * SR)), dtype=np.float32))
            cursor += dur_seg + len(pedacos[-1]) / SR

        voz = np.concatenate(pedacos)
        voz, removido = remover_silencio_inicial_ffmpeg(voz)
        for p in palavras:
            p["t0"] = round(max(0.0, p["t0"] - removido), 4)
            p["t1"] = round(max(0.0, p["t1"] - removido), 4)
        for s in segmentos:
            s["t0"] = round(max(0.0, s["t0"] - removido), 4)
            s["t1"] = round(max(0.0, s["t1"] - removido), 4)

        cauda = float(cfg.get("cauda_final", CAUDA_FINAL_PADRAO))
        fim_fala = palavras[-1]["t1"] if palavras else len(voz) / SR
        dur = max(fim_fala + cauda, min(len(voz) / SR, fim_fala + cauda + 0.08))
        dur = round(np.ceil(dur * FPS) / FPS, 4)  # duracao multipla exata de quadro
        if segmentos:
            segmentos[-1]["t1"] = dur

    n = int(round(dur * SR))
    voz = np.pad(voz, (0, max(0, n - len(voz))))[:n]
    pico = np.max(np.abs(voz)) + 1e-9
    voz = voz / pico * 0.89
    gravar_wav(BUILD / "voz.wav", voz)

    # SFX nas palavras-ancora
    seg_por_id = {s["id"]: s for s in segmentos}
    sfx_tl = []
    trilha = np.zeros((n, 2), dtype=np.float32)
    for seg in cfg["segmentos"]:
        for d in seg.get("sfx", []):
            s = seg_por_id[seg["id"]]
            if "palavra" in d:
                base_t = achar_palavra(palavras, seg["id"], d["palavra"])["t0"]
            elif d.get("ancora") == "fim":
                base_t = s["t1"]
            else:
                base_t = s["t0"]
            t = max(0.0, base_t + float(d.get("offset", 0.0)))
            fn = SFX[d["tipo"]]
            som = fn(max(0.2, s["t1"] - t)) if d.get("ate_fim") else fn()
            somar(trilha, som, t, float(d.get("ganho", 1.0)) * 0.12)
            sfx_tl.append({"tipo": d["tipo"], "t": round(t, 4), "seg": seg["id"]})

    # ducking leve no barramento de SFX durante fala ativa (voz sempre limpa em primeiro plano)
    env_voz = np.abs(voz)
    jan = int(0.05 * SR)
    env_voz = np.convolve(env_voz, np.ones(jan) / jan, mode="same")
    env_voz = env_voz / (env_voz.max() + 1e-9)
    duck_sfx = (1.0 - 0.35 * np.clip(env_voz * 4.0, 0.0, 1.0)).astype(np.float32)
    trilha *= duck_sfx[:, None]

    # cama: zonas dinamicas por episodio (climax reduzido + silencio dramatico antes do payoff)
    ganhos_zona: list[tuple[float, float, float]] = []
    climax_id = cfg.get("zona_climax_seg")
    seg_climax = seg_por_id.get(climax_id) if climax_id else (seg_por_id.get("dia28") or seg_por_id.get("dia19"))
    if seg_climax:
        ganhos_zona.append((seg_climax["t0"], seg_climax["t1"], 0.35))
    ta = seg_por_id.get("twist_a")
    tb = seg_por_id.get("twist_b")
    if ta and tb:
        ganhos_zona.append((ta["t0"], ta["t1"], 0.25))
        fim_ta = max((p["t1"] for p in palavras if p["seg"] == "twist_a"), default=ta["t1"])
        if tb["t0"] > fim_ta:
            ganhos_zona.append((fim_ta, tb["t0"], 0.0))
        ganhos_zona.append((tb["t0"], dur, 1.25))
    zonas = {"ganhos": ganhos_zona}
    cama = gerar_cama(dur, voz, zonas) * 0.16
    trilha[:, 0] += cama
    trilha[:, 1] += cama
    trilha[:, 0] += voz
    trilha[:, 1] += voz
    # fim suave para nao estalar sem abafar a ultima silaba
    fade = min(int(0.08 * SR), max(1, n // 4))
    trilha[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    trilha /= max(1.0, float(np.max(np.abs(trilha))) / 0.98)
    pre = BUILD / "mix_pre.wav"
    gravar_wav(pre, trilha)
    ln = loudnorm_2p(pre, EP_DIR / "mix_final.wav")

    voz_desc = f"{GEMINI_MODEL}/{GEMINI_VOICE}" if args.engine == "gemini" else cfg["voz"]
    dados = {
        "titulo": cfg["titulo"],
        "fps": FPS,
        "duracao": dur,
        "engine": args.engine,
        "mode": modo,
        "voz": voz_desc,
        "rate": cfg["rate"],
        "silencio_inicial_removido_s": round(removido, 4),
        "segmentos": segmentos,
        "palavras": palavras,
        "sfx": sfx_tl,
    }
    (EP_DIR / "timestamps.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    if info_lote:
        print(
            f"Alinhamento lote: {info_lote['matched']}/{info_lote['total']} "
            f"({info_lote['ratio'] * 100:.1f}%) | origem={info_lote['origem']}",
            flush=True,
        )
    print(f"Episodio: {EP_DIR.name} | Duracao: {dur:.3f}s | palavras: {len(palavras)} | silencio inicial removido: {removido:.3f}s")
    print(f"Primeira palavra em {palavras[0]['t0']:.3f}s | loudnorm saida: I={ln.get('output_i')} LUFS TP={ln.get('output_tp')}")


if __name__ == "__main__":
    sys.exit(main())
