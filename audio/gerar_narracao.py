"""Estacao 2 (v2): gera audio/voz_limpa.mp3, audio/timestamps.json e audio/eventos.json.

Uso (na raiz do repositorio):
    python3 audio/gerar_narracao.py          # ElevenLabs (se ELEVENLABS_API_KEY) ou edge-tts
    python3 audio/gerar_narracao.py --mock   # teste automatizado local sem rede

Regras aplicadas (skill audio-sound-design-suspense):
- Remove onomatopeias de acao ("Toc. Toc. Toc." / "Toque. Toque. Toque.") da fala
  e substitui por bloco de silencio exato de 2.1s (evento batidas_porta).
- Sintetiza frase por frase, corta silencios mortos nas pontas via ffmpeg silenceremove,
  meca a duracao real via ffprobe e concatena em PCM WAV antes de codificar voz_limpa.mp3
  para evitar deriva acumulada de quadros MP3.
- Gera timestamps.json (grupos de no maximo 3 palavras, sem misturar frases) e
  eventos.json com os segundos exatos de cada marco da historia.
"""

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
import tempfile
import unicodedata
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ROTEIRO = RAIZ / "roteiro_01.txt"
PASTA_AUDIO = RAIZ / "audio"
VOZ_LIMPA_MP3 = PASTA_AUDIO / "voz_limpa.mp3"
TIMESTAMPS_JSON = PASTA_AUDIO / "timestamps.json"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"
TEXTO_TXT = PASTA_AUDIO / "narracao.txt"

# Configuracoes de voz
EDGE_VOZ = "pt-BR-AntonioNeural"
EDGE_PITCH = "-6Hz"
EDGE_RATE = "+6%"

ELEVENLABS_MODELO = "eleven_multilingual_v2"
ELEVENLABS_VOZ_PADRAO = "pNInz6obpgDQGcFmaJgB"  # Adam (masculina grave/narrativa)

# Ritmo cinematografico (segundos)
PAUSA_PADRAO = 0.18
PAUSA_DRAMATICA = 0.45
DURACAO_BATIDAS_PORTA = 2.10
CAUDA_FINAL = 1.40

TAXA_AMOSTRAGEM = 44100
CANAIS = 2
TICKS_POR_SEGUNDO = 10_000_000

LINHA_BLOCO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")
PADRAO_BATIDAS = re.compile(
    r"(?:^|\s)(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?(?=\s|$)",
    re.IGNORECASE,
)


def normalizar_chave(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def suavizar_prosodia(trecho: str) -> str:
    """Une micro-frases picotadas demais para leitura conversacional fluida sem alterar a historia."""
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


def extrair_itens_roteiro(caminho: Path) -> list[dict]:
    """Extrai frases fluidas na ordem do roteiro, trocando batidas por silencio de 2.1s."""
    blocos = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if LINHA_BLOCO.match(linha):
            colunas = [c.strip() for c in linha.split("|")]
            blocos.append(suavizar_prosodia(colunas[1]))
    if not blocos:
        raise SystemExit(f"Nenhum bloco de narracao encontrado em {caminho}.")

    marcador = " __BATIDAS_PORTA__ "
    itens: list[dict] = []
    for bloco_idx, bloco in enumerate(blocos):
        substituido = PADRAO_BATIDAS.sub(marcador, bloco)
        partes = substituido.split("__BATIDAS_PORTA__")
        for p_idx, parte in enumerate(partes):
            trecho = parte.strip()
            if trecho:
                frases = [f.strip() for f in re.split(r"(?<=[\.\!\?])\s+", trecho) if f.strip()]
                for frase in frases:
                    itens.append({"tipo": "fala", "bloco": bloco_idx, "texto": frase})
            if p_idx < len(partes) - 1:
                itens.append(
                    {
                        "tipo": "silencio",
                        "bloco": bloco_idx,
                        "evento": "batidas_porta",
                        "duracao": DURACAO_BATIDAS_PORTA,
                    }
                )
    return itens


def pausa_antes_do_item(itens: list[dict], idx: int) -> float:
    """Define a pausa exata antes de cada item."""
    if idx == 0:
        return 0.0
    anterior = itens[idx - 1]
    atual = itens[idx]
    # Depois do bloco silencioso de 2.1s das batidas, a fala entra direto (ja ha respiro apos a 3a batida).
    if anterior["tipo"] == "silencio":
        return 0.0
    if atual["tipo"] == "fala":
        chave = normalizar_chave(atual["texto"])
        if chave.startswith("silencio") or chave.startswith("e o rosto dele"):
            return PAUSA_DRAMATICA
    return PAUSA_PADRAO


def mapear_evento_da_frase(texto: str) -> str | None:
    chave = normalizar_chave(texto)
    if chave.startswith("alerta de emergencia"):
        return "alerta_1"
    if chave.startswith("caio ri"):
        return "caio_ri"
    if chave.startswith("nove da noite"):
        return "hora_21"
    if chave.startswith("segundo alerta"):
        return "alerta_2"
    if chave.startswith("a mae para de responder"):
        return "chat_mae"
    if chave.startswith("meia-noite") or chave.startswith("meia noite"):
        return "hora_00"
    if chave.startswith("a luz cai"):
        return "apagao_00"
    if chave.startswith("so as telas"):
        return "janelas_telas"
    if chave.startswith("terceiro alerta"):
        return "alerta_3"
    if chave.startswith("tres da manha"):
        return "hora_03"
    if chave.startswith("do outro lado da porta"):
        return "respiracao"
    if chave.startswith("uma voz sussurra"):
        return "sussurro"
    if chave.startswith("silencio"):
        return "silencio"
    if chave.startswith("caio finalmente abre a foto"):
        return "foto_revela"
    if chave.startswith("e o rosto dele"):
        return "big_face"
    if chave.startswith("caio nunca esteve"):
        return "plot_twist"
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
    """Gera um sinal vocal simulado com silencios nas pontas para validar todo o pipeline localmente."""
    palavras = texto.split()
    peso_chars = sum(max(2, len(p)) for p in palavras)
    dur_ativa = max(0.55, min(3.4, 0.24 + peso_chars * 0.048))
    pad_ini = 0.14
    pad_fim = 0.18
    dur_total = pad_ini + dur_ativa + pad_fim
    n_total = int(round(dur_total * TAXA_AMOSTRAGEM))
    freq_base = 128.0 + (indice % 5) * 9.0

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
        frame = struct.pack("<hh", val, val)
        amostras.extend(frame)

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
        # Protecao caso uma frase muito curta/baixa tenha sido removida pelo limiar.
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

    # Distribuicao proporcional ao tamanho da palavra e micro-pausas de pontuacao interna.
    pesos = []
    for tok in tokens:
        limpa = re.sub(r"[^\wÀ-ÿ]", "", tok)
        peso = max(2.0, float(len(limpa))) + 1.2
        if tok.endswith((":", ",", ";")):
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
    """Agrupa palavras de UMA unica frase em blocos de no maximo 3 palavras, sem orfaos desnecessarios."""
    if not palavras_frase:
        return []

    # Primeiro respeita quebras naturais em ":" ou "," desde que nao gere bloco de 1 palavra.
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
        description="Gera voz_limpa.mp3, timestamps.json e eventos.json sincronizados com roteiro_01.txt."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa tons sinteticos locais no lugar do TTS (apenas para teste automatizado).",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    PASTA_AUDIO.mkdir(exist_ok=True)
    itens = extrair_itens_roteiro(ROTEIRO)

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

    print(f"Motor de voz: {motor} ({voz_usada})")

    texto_falado = " ".join(it["texto"] for it in itens if it["tipo"] == "fala")
    TEXTO_TXT.write_text(texto_falado + "\n", encoding="utf-8")

    palavras_todas: list[dict] = []
    grupos_todos: list[dict] = []
    frases_log: list[dict] = []
    eventos: dict[str, float | list[float]] = {}

    with tempfile.TemporaryDirectory(prefix="voz-v2-") as tmp:
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
                eventos[item["evento"]] = t_ini
                eventos["batidas_porta_duracao"] = round(dur_s, 3)
                eventos["batidas_tempos"] = [
                    round(t_ini + 0.0, 3),
                    round(t_ini + 0.65, 3),
                    round(t_ini + 1.30, 3),
                ]
                frases_log.append(
                    {
                        "tipo": "silencio",
                        "evento": item["evento"],
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
                raw_words = sintetizar_elevenlabs(texto, raw_arq, api_key, voice_id)
            else:
                raw_words = sintetizar_edge(texto, raw_arq)

            dur_frase = limpar_silencio_frase(raw_arq, limpa_wav)
            wavs_concat.append(limpa_wav)

            t_ini = cursor
            evento_nome = mapear_evento_da_frase(texto)
            if evento_nome and evento_nome not in eventos:
                eventos[evento_nome] = round(t_ini, 3)

            palavras_frase = alinhar_palavras_na_frase(texto, t_ini, dur_frase, raw_words)

            # Marcos intra-frase precisos (quando duas micro-frases foram unidas pela prosodia).
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
                    "evento": evento_nome,
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

    obrigatorios = [
        "alerta_1",
        "hora_21",
        "alerta_2",
        "apagao_00",
        "alerta_3",
        "hora_03",
        "batidas_porta",
        "sussurro",
        "silencio",
        "foto_revela",
        "big_face",
        "plot_twist",
        "duracao_total",
    ]
    faltando = [k for k in obrigatorios if k not in eventos]
    if faltando:
        raise RuntimeError(f"Eventos obrigatorios ausentes: {faltando}")

    eventos_ordenados = {k: eventos[k] for k in obrigatorios}
    for extra in (
        "mapa_apito",
        "caio_ri",
        "chat_mae",
        "hora_00",
        "janelas_telas",
        "respiracao",
        "batidas_porta_duracao",
        "batidas_tempos",
    ):
        if extra in eventos:
            eventos_ordenados[extra] = eventos[extra]
    eventos_ordenados["frases"] = frases_log

    dados_timestamps = {
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
        json.dumps(eventos_ordenados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"Gerado {VOZ_LIMPA_MP3.name}: {duracao_total:.3f}s | "
        f"{len(palavras_todas)} palavras em {len(grupos_todos)} grupos de legenda"
    )
    print(f"Eventos gravados em {EVENTOS_JSON.name} (batidas_porta={eventos['batidas_porta']}s)")


if __name__ == "__main__":
    main()
