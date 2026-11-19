"""Estacao 2 (v3): gera audio/voz_limpa.mp3, audio/timestamps.json e audio/eventos.json.

Uso (na raiz do repositorio):
    python3 audio/gerar_narracao.py          # ElevenLabs (via ambiente/.env) com fallback automatico edge-tts
    python3 audio/gerar_narracao.py --mock   # teste automatizado local sem rede

Regras aplicadas (skill audio-sound-design-suspense):
- Consulta historico_videos.json via pipeline/historico.py para usar o roteiro do video ativo
  e validar a regra permanente 'Sempre Video Novo'.
- Carrega automaticamente o arquivo .env local (ignorado pelo Git) quando ELEVENLABS_API_KEY
  nao estiver definida no ambiente. Nunca imprime nem grava chaves em disco.
- Se ElevenLabs retornar HTTP 401/403 (ex.: detected_unusual_activity em IP de nuvem do Colab),
  captura o erro, imprime o motivo exato e cai automaticamente para edge-tts sem derrubar o fluxo.
- Grava carimbo de integridade (video_id, titulo, roteiro_sha256) em timestamps.json e eventos.json
  e valida a presenca da CTA obrigatoria ("COMENTE EU QUERO").
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.historico import (  # noqa: E402
    calcular_sha256_arquivo,
    caminho_roteiro_atual,
    obter_video_atual,
    validar_artefatos_audio,
)

PASTA_AUDIO = RAIZ / "audio"
VOZ_LIMPA_MP3 = PASTA_AUDIO / "voz_limpa.mp3"
TIMESTAMPS_JSON = PASTA_AUDIO / "timestamps.json"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"
TEXTO_TXT = PASTA_AUDIO / "narracao.txt"
ARQUIVO_ENV = RAIZ / ".env"

# Configuracoes de voz
EDGE_VOZ = "pt-BR-AntonioNeural"
EDGE_PITCH = "-6Hz"
EDGE_RATE = "+6%"

ELEVENLABS_MODELO = "eleven_multilingual_v2"
ELEVENLABS_VOZ_PADRAO = "pNInz6obpgDQGcFmaJgB"  # Adam (masculina grave/narrativa)

# Ritmo cinematografico (segundos)
PAUSA_PADRAO = 0.16
PAUSA_DRAMATICA = 0.42
DURACAO_BATIDAS_PORTA = 2.10
CAUDA_FINAL = 0.45

TAXA_AMOSTRAGEM = 44100
CANAIS = 2
TICKS_POR_SEGUNDO = 10_000_000

LINHA_BLOCO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")
PADRAO_SFX = re.compile(
    r"^\[\s*SFX\s*:\s*([a-zA-Z0-9_]+)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*\]$",
    re.IGNORECASE,
)
PADRAO_BATIDAS = re.compile(
    r"(?:^|\s)(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?(?=\s|$)",
    re.IGNORECASE,
)
SEPARADOR_FRASES = re.compile(r"(?<!\.\.)(?<=[\.\!\?])\s+")


def carregar_env(caminho_env: Path = ARQUIVO_ENV) -> bool:
    """Carrega variaveis do .env local apenas quando ausentes ou vazias no ambiente."""
    if not caminho_env.is_file():
        return False
    carregou = False
    for linha in caminho_env.read_text(encoding="utf-8").splitlines():
        bruta = linha.strip()
        if not bruta or bruta.startswith("#"):
            continue
        if bruta.startswith("export "):
            bruta = bruta[7:].strip()
        if "=" not in bruta:
            continue
        chave, valor = bruta.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
            valor = valor[1:-1]
        if chave and not os.environ.get(chave, "").strip():
            os.environ[chave] = valor
            carregou = True
    return carregou


def normalizar_chave(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def suavizar_prosodia_legado(trecho: str) -> str:
    """Ajuste legado para roteiro_01.txt."""
    ajustes = [
        (
            "Sete da noite. Todo celular do Brasil apita ao mesmo tempo.",
            "Sete da noite, todo celular do Brasil apita ao mesmo tempo.",
        ),
        (
            "Caio ri. Acha que é teste do governo.",
            "Caio ri, achando que é teste do governo.",
        ),
        (
            "Nove da noite. Caio chega em casa.",
            "Nove da noite, Caio chega em casa.",
        ),
        (
            "Meia-noite. A luz cai no bairro inteiro.",
            "Meia-noite, a luz cai no bairro inteiro.",
        ),
    ]
    out = trecho
    for orig, fluido in ajustes:
        out = out.replace(orig, fluido)
    return out


def _interpretar_coluna_eventos(espec: str) -> tuple[list[str], list[tuple[str, str]], float | None]:
    eventos_inicio: list[str] = []
    eventos_palavra: list[tuple[str, str]] = []
    pausa_explicita: float | None = None

    for parte in espec.split(","):
        tok = parte.strip()
        if not tok:
            continue
        if tok.lower().startswith("pausa="):
            pausa_explicita = float(tok.split("=", 1)[1].strip())
        elif "@" in tok:
            ev_nome, alvo = tok.split("@", 1)
            ev_nome = ev_nome.strip()
            alvo = normalizar_chave(alvo.strip())
            if ev_nome and alvo:
                eventos_palavra.append((ev_nome, alvo))
        else:
            eventos_inicio.append(tok)
    return eventos_inicio, eventos_palavra, pausa_explicita


def extrair_itens_roteiro(caminho: Path) -> tuple[list[dict], bool]:
    """Extrai falas e blocos silenciosos de SFX na ordem do roteiro."""
    linhas_bloco: list[list[str]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if LINHA_BLOCO.match(linha):
            colunas = [c.strip() for c in linha.split("|")]
            if len(colunas) >= 2:
                linhas_bloco.append(colunas)
    if not linhas_bloco:
        raise SystemExit(f"Nenhum bloco de narracao encontrado em {caminho}.")

    usa_eventos_explicitos = any(len(cols) >= 4 and cols[3] for cols in linhas_bloco)
    marcador = " __BATIDAS_PORTA__ "
    itens: list[dict] = []

    for bloco_idx, colunas in enumerate(linhas_bloco):
        narracao = colunas[1]
        espec_eventos = colunas[3] if len(colunas) >= 4 else ""
        ev_inicio, ev_palavra, pausa_explicita = _interpretar_coluna_eventos(espec_eventos)

        m_sfx = PADRAO_SFX.match(narracao)
        if m_sfx:
            nome_ev = ev_inicio[0] if ev_inicio else m_sfx.group(1)
            dur_sfx = float(m_sfx.group(2))
            itens.append(
                {
                    "tipo": "silencio",
                    "bloco": bloco_idx,
                    "evento": nome_ev,
                    "duracao": dur_sfx,
                    "pausa_antes": pausa_explicita,
                }
            )
            continue

        if not usa_eventos_explicitos:
            narracao = suavizar_prosodia_legado(narracao)

        substituido = PADRAO_BATIDAS.sub(marcador, narracao)
        partes = substituido.split("__BATIDAS_PORTA__")
        primeira_fala_do_bloco = True
        for p_idx, parte in enumerate(partes):
            trecho = parte.strip()
            if trecho:
                frases = [f.strip() for f in SEPARADOR_FRASES.split(trecho) if f.strip()]
                for frase in frases:
                    itens.append(
                        {
                            "tipo": "fala",
                            "bloco": bloco_idx,
                            "texto": frase,
                            "eventos_inicio": ev_inicio if primeira_fala_do_bloco else [],
                            "eventos_palavra": ev_palavra,
                            "pausa_antes": pausa_explicita if primeira_fala_do_bloco else None,
                        }
                    )
                    primeira_fala_do_bloco = False
            if p_idx < len(partes) - 1:
                itens.append(
                    {
                        "tipo": "silencio",
                        "bloco": bloco_idx,
                        "evento": "batidas_porta",
                        "duracao": DURACAO_BATIDAS_PORTA,
                        "pausa_antes": None,
                    }
                )
    return itens, usa_eventos_explicitos


def pausa_antes_do_item(itens: list[dict], idx: int) -> float:
    """Define a pausa exata antes de cada item."""
    if idx == 0:
        return 0.0
    anterior = itens[idx - 1]
    atual = itens[idx]
    if atual.get("pausa_antes") is not None:
        return float(atual["pausa_antes"])
    if anterior["tipo"] == "silencio":
        return 0.0
    if atual["tipo"] == "silencio":
        return 0.08
    if atual["tipo"] == "fala":
        chave = normalizar_chave(atual["texto"])
        if chave.startswith("silencio") or chave.startswith("e o rosto dele"):
            return PAUSA_DRAMATICA
    return PAUSA_PADRAO


def mapear_evento_legado(texto: str) -> str | None:
    chave = normalizar_chave(texto)
    mapa = [
        ("alerta de emergencia", "alerta_1"),
        ("caio ri", "caio_ri"),
        ("nove da noite", "hora_21"),
        ("segundo alerta", "alerta_2"),
        ("a mae para de responder", "chat_mae"),
        ("meia-noite", "hora_00"),
        ("meia noite", "hora_00"),
        ("a luz cai", "apagao_00"),
        ("so as telas", "janelas_telas"),
        ("terceiro alerta", "alerta_3"),
        ("tres da manha", "hora_03"),
        ("do outro lado da porta", "respiracao"),
        ("uma voz sussurra", "sussurro"),
        ("silencio", "silencio"),
        ("caio finalmente abre a foto", "foto_revela"),
        ("e o rosto dele", "big_face"),
        ("caio nunca esteve", "plot_twist"),
    ]
    for prefixo, evento in mapa:
        if chave.startswith(prefixo):
            return evento
    return None


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


def gerar_wav_silencio(caminho: Path, duracao: float) -> float:
    n_frames = max(0, int(round(duracao * TAXA_AMOSTRAGEM)))
    with wave.open(str(caminho), "wb") as wf:
        wf.setnchannels(CANAIS)
        wf.setsampwidth(2)
        wf.setframerate(TAXA_AMOSTRAGEM)
        if n_frames:
            wf.writeframes(b"\x00\x00" * CANAIS * n_frames)
    return n_frames / TAXA_AMOSTRAGEM


def sintetizar_mock(texto: str, destino_wav: Path, indice: int) -> list[dict]:
    """Gera sinal vocal simulado com silencios nas pontas para validar o pipeline sem rede."""
    palavras = texto.split()
    peso_chars = sum(max(2, len(p)) for p in palavras)
    dur_ativa = max(0.55, min(3.4, 0.24 + peso_chars * 0.046))
    pad_ini = 0.14
    pad_fim = 0.18
    dur_total = pad_ini + dur_ativa + pad_fim
    n_total = int(round(dur_total * TAXA_AMOSTRAGEM))
    freq_base = 124.0 + (indice % 5) * 9.0

    amostras = bytearray()
    for i in range(n_total):
        t = i / TAXA_AMOSTRAGEM
        if t < pad_ini or t > pad_ini + dur_ativa:
            s = 0.0
        else:
            tr = t - pad_ini
            env = min(1.0, tr / 0.025) * min(1.0, (dur_ativa - tr) / 0.03)
            cadencia = 0.65 + 0.35 * math.sin(2.0 * math.pi * 4.2 * tr)
            f = freq_base * (1.0 - 0.08 * (tr / dur_ativa))
            s = 0.22 * env * cadencia * (
                0.75 * math.sin(2.0 * math.pi * f * tr)
                + 0.25 * math.sin(2.0 * math.pi * (f * 2.0) * tr)
            )
        val = max(-32767, min(32767, int(s * 32767)))
        amostras.extend(struct.pack("<hh", val, val))

    with wave.open(str(destino_wav), "wb") as wf:
        wf.setnchannels(CANAIS)
        wf.setsampwidth(2)
        wf.setframerate(TAXA_AMOSTRAGEM)
        wf.writeframes(bytes(amostras))
    return []


def alinhamento_elevenlabs_para_palavras(texto: str, alignment: dict | None) -> list[dict]:
    if not alignment:
        return []
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (chars and len(chars) == len(starts) == len(ends)):
        return []

    palavras_raw = []
    buf = []
    ini = None
    fim = None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf and ini is not None and fim is not None:
                palavras_raw.append(
                    {"palavra": "".join(buf), "inicio": float(ini), "duracao": max(0.02, float(fim - ini))}
                )
                buf = []
                ini = None
                fim = None
        else:
            if ini is None:
                ini = s
            fim = e
            buf.append(ch)
    if buf and ini is not None and fim is not None:
        palavras_raw.append(
            {"palavra": "".join(buf), "inicio": float(ini), "duracao": max(0.02, float(fim - ini))}
        )
    return palavras_raw if len(palavras_raw) == len(texto.split()) else []


def _extrair_motivo_http_error(exc: urllib.error.HTTPError) -> str:
    """Extrai o motivo detalhado devolvido pela API ElevenLabs sem expor segredos."""
    try:
        corpo = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        corpo = ""
    if not corpo:
        return str(exc.reason or f"HTTP {exc.code}")
    try:
        dados = json.loads(corpo)
        detail = dados.get("detail")
        if isinstance(detail, dict):
            status = detail.get("status", "")
            msg = detail.get("message", "")
            if status and msg:
                return f"{status}: {msg}"
            return str(status or msg or detail)
        if detail:
            return str(detail)
    except Exception:
        pass
    return corpo[:260]


def sintetizar_elevenlabs(texto: str, destino_mp3: Path, api_key: str, voice_id: str) -> list[dict]:
    payload = json.dumps(
        {
            "text": texto,
            "model_id": ELEVENLABS_MODELO,
            "voice_settings": {
                "stability": 0.42,
                "similarity_boost": 0.80,
                "style": 0.35,
                "use_speaker_boost": True,
            },
        }
    ).encode("utf-8")

    headers_json = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url_ts = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    req_ts = urllib.request.Request(url_ts, data=payload, headers=headers_json, method="POST")
    try:
        with urllib.request.urlopen(req_ts, timeout=60) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        destino_mp3.write_bytes(base64.b64decode(dados["audio_base64"]))
        return alinhamento_elevenlabs_para_palavras(texto, dados.get("alignment"))
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404, 422):
            raise

    headers_mp3 = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    req = urllib.request.Request(url, data=payload, headers=headers_mp3, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        destino_mp3.write_bytes(resp.read())
    return []


async def _sintetizar_edge_async(texto: str, destino_mp3: Path) -> list[dict]:
    import edge_tts

    comunicar = edge_tts.Communicate(
        texto,
        EDGE_VOZ,
        rate=EDGE_RATE,
        pitch=EDGE_PITCH,
        boundary="WordBoundary",
    )
    palavras = []
    with destino_mp3.open("wb") as arq:
        async for pedaco in comunicar.stream():
            if pedaco["type"] == "audio":
                arq.write(pedaco["data"])
            elif pedaco["type"] == "WordBoundary":
                palavras.append(
                    {
                        "palavra": pedaco["text"],
                        "inicio": pedaco["offset"] / TICKS_POR_SEGUNDO,
                        "duracao": pedaco["duration"] / TICKS_POR_SEGUNDO,
                    }
                )
    return palavras


def sintetizar_edge(texto: str, destino_mp3: Path) -> list[dict]:
    return asyncio.run(_sintetizar_edge_async(texto, destino_mp3))


def limpar_silencio_frase(origem: Path, destino_wav: Path) -> float:
    """Corta silencios mortos nas pontas via silenceremove e normaliza em PCM 44.1kHz estereo."""
    filtro = (
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-42dB:detection=peak,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-42dB:detection=peak,"
        "areverse,"
        "afade=t=in:st=0:d=0.008"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(origem),
        "-af",
        filtro,
        "-ar",
        str(TAXA_AMOSTRAGEM),
        "-ac",
        str(CANAIS),
        "-c:a",
        "pcm_s16le",
        str(destino_wav),
    ]
    subprocess.run(cmd, check=True)
    dur = medir_duracao_ffprobe(destino_wav)
    if dur < 0.08:
        cmd_raw = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(origem),
            "-ar",
            str(TAXA_AMOSTRAGEM),
            "-ac",
            str(CANAIS),
            "-c:a",
            "pcm_s16le",
            str(destino_wav),
        ]
        subprocess.run(cmd_raw, check=True)
        dur = medir_duracao_ffprobe(destino_wav)
    return dur


def alinhar_palavras_na_frase(
    texto: str,
    t_inicio: float,
    dur_frase: float,
    raw_words: list[dict],
) -> list[dict]:
    """Trava os tempos de cada palavra dentro de [t_inicio, t_inicio + dur_frase]."""
    tokens = texto.split()
    if not tokens:
        return []

    if raw_words and len(raw_words) == len(tokens):
        base = raw_words[0]["inicio"]
        fim_raw = max(w["inicio"] + w["duracao"] for w in raw_words)
        span = max(0.05, fim_raw - base)
        escala = dur_frase / span
        saida = []
        for tok, rw in zip(tokens, raw_words):
            rel_ini = max(0.0, (rw["inicio"] - base) * escala)
            rel_dur = max(0.03, rw["duracao"] * escala)
            if rel_ini + rel_dur > dur_frase:
                rel_dur = max(0.02, dur_frase - rel_ini)
            ini_abs = round(t_inicio + rel_ini, 3)
            fim_abs = round(min(t_inicio + dur_frase, t_inicio + rel_ini + rel_dur), 3)
            saida.append(
                {
                    "palavra": tok,
                    "inicio": ini_abs,
                    "duracao": round(max(0.02, fim_abs - ini_abs), 3),
                    "fim": fim_abs,
                }
            )
        return saida

    pesos = []
    for tok in tokens:
        limpa = re.sub(r"[^\wÀ-ÿ]", "", tok)
        peso = max(2.0, float(len(limpa))) + 1.2
        if tok.endswith((":", ",", ";", "...")):
            peso += 1.5
        pesos.append(peso)
    soma = sum(pesos)
    cursor = t_inicio
    saida = []
    for idx, (tok, peso) in enumerate(zip(tokens, pesos)):
        dur_w = dur_frase * (peso / soma)
        fim_w = t_inicio + dur_frase if idx == len(tokens) - 1 else cursor + dur_w
        ini_r = round(cursor, 3)
        fim_r = round(fim_w, 3)
        saida.append(
            {
                "palavra": tok,
                "inicio": ini_r,
                "duracao": round(max(0.02, fim_r - ini_r), 3),
                "fim": fim_r,
            }
        )
        cursor = fim_w
    return saida


def quebrar_em_grupos_legenda(palavras_frase: list[dict]) -> list[list[dict]]:
    """Agrupa palavras de UMA unica frase em blocos de no maximo 3 palavras."""
    if not palavras_frase:
        return []

    clausulas: list[list[dict]] = []
    atual: list[dict] = []
    for idx, p in enumerate(palavras_frase):
        atual.append(p)
        restantes = len(palavras_frase) - idx - 1
        if p["palavra"].endswith((":", ",")) and (len(atual) >= 2 or "-" in p["palavra"]) and restantes >= 2:
            clausulas.append(atual)
            atual = []
    if atual:
        clausulas.append(atual)

    grupos: list[list[dict]] = []
    for clausula in clausulas:
        i = 0
        n = len(clausula)
        while i < n:
            falta = n - i
            if falta <= 3:
                tam = falta
            elif falta == 4:
                tam = 2
            else:
                tam = 3
            grupos.append(clausula[i : i + tam])
            i += tam
    return grupos


def concatenar_wavs_para_mp3(lista_wavs: list[Path], wav_mestre: Path, destino_mp3: Path) -> float:
    with wave.open(str(wav_mestre), "wb") as out:
        out.setnchannels(CANAIS)
        out.setsampwidth(2)
        out.setframerate(TAXA_AMOSTRAGEM)
        for caminho in lista_wavs:
            with wave.open(str(caminho), "rb") as inp:
                if (
                    inp.getnchannels() != CANAIS
                    or inp.getsampwidth() != 2
                    or inp.getframerate() != TAXA_AMOSTRAGEM
                ):
                    raise RuntimeError(f"Formato WAV inconsistente em {caminho}")
                out.writeframes(inp.readframes(inp.getnframes()))

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(wav_mestre),
        "-ar",
        str(TAXA_AMOSTRAGEM),
        "-ac",
        str(CANAIS),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(destino_mp3),
    ]
    subprocess.run(cmd, check=True)
    return medir_duracao_ffprobe(destino_mp3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera voz_limpa.mp3, timestamps.json e eventos.json sincronizados com o roteiro ativo."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa tons sinteticos locais no lugar do TTS (apenas para teste automatizado).",
    )
    parser.add_argument(
        "--roteiro",
        type=Path,
        default=None,
        help="Caminho manual do roteiro (padrao: video ativo em historico_videos.json).",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    env_carregado = carregar_env()
    video_ativo = obter_video_atual(validar=True)
    roteiro_path = args.roteiro if args.roteiro else caminho_roteiro_atual()
    if not roteiro_path.is_absolute():
        roteiro_path = RAIZ / roteiro_path
    if not roteiro_path.is_file():
        raise SystemExit(f"Roteiro nao encontrado: {roteiro_path}")

    roteiro_sha256 = calcular_sha256_arquivo(roteiro_path)
    PASTA_AUDIO.mkdir(exist_ok=True)
    itens, usa_eventos_explicitos = extrair_itens_roteiro(roteiro_path)

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or ELEVENLABS_VOZ_PADRAO

    if args.mock:
        motor = "mock"
        voz_usada = "mock-tone-pt-BR"
    elif api_key:
        motor = "elevenlabs"
        voz_usada = f"{ELEVENLABS_MODELO}:{voice_id}"
    else:
        motor = "edge-tts"
        voz_usada = f"{EDGE_VOZ} (pitch={EDGE_PITCH}, rate={EDGE_RATE})"

    origem_chave = " (.env local)" if (motor == "elevenlabs" and env_carregado) else ""
    print(
        f"Video {int(video_ativo['id']):02d}: {video_ativo['titulo']} | "
        f"Roteiro: {roteiro_path.name} (sha256={roteiro_sha256[:12]})"
    )
    print(f"Motor de voz inicial: {motor} ({voz_usada}){origem_chave}")

    texto_falado = " ".join(it["texto"] for it in itens if it["tipo"] == "fala")
    TEXTO_TXT.write_text(texto_falado + "\n", encoding="utf-8")

    palavras_todas: list[dict] = []
    grupos_todos: list[dict] = []
    frases_log: list[dict] = []
    eventos: dict[str, float | int | str | list[float]] = {
        "video_id": int(video_ativo["id"]),
        "slug": str(video_ativo["slug"]),
        "titulo": str(video_ativo["titulo"]),
        "parte_label": str(video_ativo.get("parte_label", "PARTE 1")),
        "roteiro": roteiro_path.name,
        "roteiro_sha256": roteiro_sha256,
    }

    with tempfile.TemporaryDirectory(prefix="voz-v3-") as tmp:
        tmp_dir = Path(tmp)
        wavs_concat: list[Path] = []
        cursor = 0.0
        frase_idx = 0

        for idx, item in enumerate(itens):
            pausa = pausa_antes_do_item(itens, idx)
            if pausa > 0:
                p_wav = tmp_dir / f"pausa_{idx:02d}.wav"
                dur_p = gerar_wav_silencio(p_wav, pausa)
                wavs_concat.append(p_wav)
                cursor += dur_p

            if item["tipo"] == "silencio":
                s_wav = tmp_dir / f"silencio_{idx:02d}.wav"
                t_ini = round(cursor, 3)
                dur_s = gerar_wav_silencio(s_wav, item["duracao"])
                wavs_concat.append(s_wav)
                ev_nome = item["evento"]
                eventos[ev_nome] = t_ini
                eventos[f"{ev_nome}_duracao"] = round(dur_s, 3)
                if ev_nome == "batidas_porta":
                    eventos["batidas_tempos"] = [
                        round(t_ini + 0.0, 3),
                        round(t_ini + 0.65, 3),
                        round(t_ini + 1.30, 3),
                    ]
                frases_log.append(
                    {
                        "tipo": "silencio",
                        "evento": ev_nome,
                        "inicio": t_ini,
                        "fim": round(cursor + dur_s, 3),
                        "duracao": round(dur_s, 3),
                    }
                )
                cursor += dur_s
                continue

            texto = item["texto"]
            raw_arq = tmp_dir / f"frase_{idx:02d}_raw.{'wav' if motor == 'mock' else 'mp3'}"
            limpa_wav = tmp_dir / f"frase_{idx:02d}_limpa.wav"

            if motor == "mock":
                raw_words = sintetizar_mock(texto, raw_arq, idx)
            elif motor == "elevenlabs":
                try:
                    raw_words = sintetizar_elevenlabs(texto, raw_arq, api_key, voice_id)
                except urllib.error.HTTPError as exc:
                    if exc.code in (401, 403, 429):
                        motivo = _extrair_motivo_http_error(exc)
                        print(
                            f"AVISO ElevenLabs HTTP {exc.code} ({motivo}). "
                            f"Alternando automaticamente para fallback edge-tts ({EDGE_VOZ})...",
                            flush=True,
                        )
                        motor = "edge-tts"
                        voz_usada = f"{EDGE_VOZ} (pitch={EDGE_PITCH}, rate={EDGE_RATE}) [fallback HTTP {exc.code}]"
                        raw_words = sintetizar_edge(texto, raw_arq)
                    else:
                        raise
            else:
                raw_words = sintetizar_edge(texto, raw_arq)

            dur_frase = limpar_silencio_frase(raw_arq, limpa_wav)
            wavs_concat.append(limpa_wav)

            t_ini = cursor
            palavras_frase = alinhar_palavras_na_frase(texto, t_ini, dur_frase, raw_words)

            evento_principal = None
            if usa_eventos_explicitos:
                for ev_nome in item.get("eventos_inicio", []):
                    if ev_nome not in eventos:
                        eventos[ev_nome] = round(t_ini, 3)
                    if evento_principal is None:
                        evento_principal = ev_nome
                for ev_nome, alvo in item.get("eventos_palavra", []):
                    if ev_nome in eventos:
                        continue
                    for p in palavras_frase:
                        limpa_p = re.sub(r"[^a-z0-9]", "", normalizar_chave(p["palavra"]))
                        if limpa_p.startswith(alvo):
                            eventos[ev_nome] = p["inicio"]
                            if evento_principal is None:
                                evento_principal = ev_nome
                            break
            else:
                evento_principal = mapear_evento_legado(texto)
                if evento_principal and evento_principal not in eventos:
                    eventos[evento_principal] = round(t_ini, 3)
                chave_f = normalizar_chave(texto)
                if "apita" in chave_f and "mapa_apito" not in eventos:
                    for p in palavras_frase:
                        if normalizar_chave(p["palavra"]).startswith("apita"):
                            eventos["mapa_apito"] = p["inicio"]
                            break
                if "a luz cai" in chave_f and "apagao_00" not in eventos:
                    for idx_p, p in enumerate(palavras_frase):
                        if normalizar_chave(p["palavra"]).startswith("luz"):
                            t_ap = palavras_frase[idx_p - 1]["inicio"] if idx_p > 0 else p["inicio"]
                            eventos["apagao_00"] = t_ap
                            break

            grupos_frase = quebrar_em_grupos_legenda(palavras_frase)

            for grp in grupos_frase:
                g_idx = len(grupos_todos)
                palavras_grp = []
                for p in grp:
                    p_idx = len(palavras_todas)
                    registro = {
                        "indice": p_idx,
                        "frase_indice": frase_idx,
                        "grupo_indice": g_idx,
                        "palavra": p["palavra"],
                        "inicio": p["inicio"],
                        "duracao": p["duracao"],
                        "fim": p["fim"],
                    }
                    palavras_todas.append(registro)
                    palavras_grp.append(
                        {
                            "indice": p_idx,
                            "palavra": p["palavra"],
                            "inicio": p["inicio"],
                            "duracao": p["duracao"],
                            "fim": p["fim"],
                        }
                    )
                g_ini = palavras_grp[0]["inicio"]
                g_fim = palavras_grp[-1]["fim"]
                grupos_todos.append(
                    {
                        "indice": g_idx,
                        "frase_indice": frase_idx,
                        "texto": " ".join(p["palavra"] for p in palavras_grp),
                        "inicio": g_ini,
                        "fim": g_fim,
                        "duracao": round(max(0.02, g_fim - g_ini), 3),
                        "palavras": palavras_grp,
                    }
                )

            frases_log.append(
                {
                    "tipo": "fala",
                    "frase_indice": frase_idx,
                    "texto": texto,
                    "evento": evento_principal,
                    "inicio": round(t_ini, 3),
                    "fim": round(t_ini + dur_frase, 3),
                    "duracao": round(dur_frase, 3),
                }
            )
            cursor += dur_frase
            frase_idx += 1

        if CAUDA_FINAL > 0:
            cauda_wav = tmp_dir / "cauda_final.wav"
            cursor += gerar_wav_silencio(cauda_wav, CAUDA_FINAL)
            wavs_concat.append(cauda_wav)

        wav_mestre = tmp_dir / "voz_limpa_mestre.wav"
        dur_mp3 = concatenar_wavs_para_mp3(wavs_concat, wav_mestre, VOZ_LIMPA_MP3)

    duracao_total = round(dur_mp3, 3)
    eventos["duracao_total"] = duracao_total
    eventos["frases"] = frases_log

    obrigatorios_por_roteiro = {
        "roteiro_02.txt": [
            "gancho", "hora_02", "gps_rota", "sem_destino", "rua_escura",
            "retrovisor", "destino_acidente", "hora_0206", "freio", "caminhao",
            "quase", "sussurro", "plot_twist", "proximo_acidente", "cta", "cta_acao",
            "duracao_total",
        ],
        "roteiro_03.txt": [
            "gancho", "vibra_cama", "pix_1", "marina_ri", "congela", "nao_acende",
            "hora_0313", "pix_2", "desc_2", "tranca_porta", "corredor_breu",
            "pix_3", "fecha_janela", "trava_janela", "hora_0314", "pix_4",
            "msg_final", "plot_twist", "guarda_roupa", "abre_devagar",
            "cta", "cta_acao", "duracao_total",
        ],
        "roteiro_04.txt": [
            "gancho", "acorda_sussurro", "baba_som", "sussurro",
            "olha_tela", "berco_vazio", "coracao_dispara", "sombra_corredor",
            "passos_corredor", "corre_quarto", "abre_porta", "acende_luz",
            "bebe_dormindo", "alivio", "olha_volta", "camera_vazio",
            "alguem_parado", "atras_porta", "olha_lente", "plot_twist",
            "impacto_twist", "luz_apaga", "apaga_hit",
            "cta", "cta_acao", "duracao_total",
        ],
    }
    if roteiro_path.name in obrigatorios_por_roteiro:
        faltando = [k for k in obrigatorios_por_roteiro[roteiro_path.name] if k not in eventos]
        if faltando:
            raise RuntimeError(f"Eventos obrigatorios ausentes para {roteiro_path.name}: {faltando}")

    dados_timestamps = {
        "video_id": int(video_ativo["id"]),
        "slug": str(video_ativo["slug"]),
        "titulo": str(video_ativo["titulo"]),
        "roteiro": roteiro_path.name,
        "roteiro_sha256": roteiro_sha256,
        "audio": VOZ_LIMPA_MP3.name,
        "motor": motor,
        "voz": voz_usada,
        "duracao_total": duracao_total,
        "texto": texto_falado,
        "max_palavras_por_grupo": 3,
        "total_palavras": len(palavras_todas),
        "total_grupos": len(grupos_todos),
        "grupos": grupos_todos,
        "palavras": palavras_todas,
    }

    TIMESTAMPS_JSON.write_text(
        json.dumps(dados_timestamps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    EVENTOS_JSON.write_text(
        json.dumps(eventos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Valida imediatamente os artefatos recem-gerados se estiver usando o roteiro ativo
    if args.roteiro is None:
        validar_artefatos_audio(PASTA_AUDIO)

    print(
        f"Gerado {VOZ_LIMPA_MP3.name}: {duracao_total:.3f}s | motor final={motor} | "
        f"{len(palavras_todas)} palavras em {len(grupos_todos)} grupos de legenda"
    )
    if "cta" in eventos:
        cta_dur = duracao_total - float(eventos["cta"])
        print(f"Plot twist em {eventos.get('plot_twist')}s | CTA em {eventos['cta']}s (ultimos {cta_dur:.2f}s)")


if __name__ == "__main__":
    main()
