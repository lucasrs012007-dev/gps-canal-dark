"""Gerenciador da biblioteca de SFX reais em assets/sfx/ (skill biblioteca-sfx-reais).

Uso (na raiz do repositorio):
    python3 audio/baixar_sfx.py --verificar
    python3 audio/baixar_sfx.py --importar <nome> <arquivo.wav|mp3>
    python3 audio/baixar_sfx.py --elevenlabs [--efeitos sussurro passos_corredor]
    python3 audio/baixar_sfx.py --baixar [--efeitos sub_boom whoosh]

Funcoes:
- Audita assets/sfx/ com ffprobe + analise de pico dBFS e atraso de ataque.
- Padroniza qualquer arquivo real via ffmpeg (44100 Hz, 16-bit PCM, estereo,
  silenceremove no inicio e loudnorm I=-18 TP=-3 LRA=9).
- Suporta geracao sob demanda via ElevenLabs Sound Effects lendo ELEVENLABS_API_KEY
  exclusivamente do ambiente ou do .env local (nunca grava chaves em arquivos).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SFX = RAIZ / "assets" / "sfx"
CATALOGO_JSON = PASTA_SFX / "catalogo.json"
ARQUIVO_ENV = RAIZ / ".env"

SR_PADRAO = 44100
CANAIS_PADRAO = 2
EXTENSOES_SUPORTADAS = (".wav", ".flac", ".mp3", ".ogg")

# Lista curada de fontes CC0/livres e prompts ElevenLabs para os efeitos canonicos da fabrica
CATALOGO_CURADO: list[dict] = [
    {
        "nome": "sub_boom",
        "arquivo": "sub_boom.wav",
        "categoria": "impacto",
        "duracao_alvo_s": 1.6,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=cinematic+sub+boom&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Deep cinematic sub bass boom impact with short dark tail, suspense thriller trailer, dry studio quality, no music",
    },
    {
        "nome": "whoosh",
        "arquivo": "whoosh.wav",
        "categoria": "transicao",
        "duracao_alvo_s": 0.85,
        "ganho_db": -1.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=dark+whoosh+cinematic&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Dark cinematic low air whoosh transition sweeping left to right, horror suspense film, clean studio recording, no music",
    },
    {
        "nome": "riser",
        "arquivo": "riser.wav",
        "categoria": "tensao",
        "duracao_alvo_s": 2.4,
        "ganho_db": -2.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=horror+tension+riser&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Suspense horror tension riser building with dark metallic scrape and breathy air swell ending abruptly, no music",
    },
    {
        "nome": "heartbeat",
        "arquivo": "heartbeat.wav",
        "categoria": "suspense",
        "duracao_alvo_s": 2.2,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=heartbeat+fast+scary&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Fast tense human heartbeat pounding deep low thump lub dub accelerating in suspense thriller, dry close mic, no music",
    },
    {
        "nome": "sussurro",
        "arquivo": "sussurro.wav",
        "categoria": "terror",
        "duracao_alvo_s": 1.2,
        "ganho_db": 1.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=creepy+whisper+radio&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Creepy eerie human breathy whisper through cheap baby monitor speaker with subtle radio static at night, horror foley, no music",
    },
    {
        "nome": "passos_corredor",
        "arquivo": "passos_corredor.wav",
        "categoria": "foley",
        "duracao_alvo_s": 1.3,
        "ganho_db": 0.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=wooden+hallway+footsteps&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Four slow heavy footsteps walking across dark wooden hallway floorboards with faint creak and room reverb at night, no music",
    },
    {
        "nome": "porta_impacto",
        "arquivo": "porta_impacto.wav",
        "categoria": "foley",
        "duracao_alvo_s": 0.9,
        "ganho_db": 0.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=door+slam+open+bedroom&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Wooden bedroom door flung open forcefully hitting wall followed by crisp light switch click indoors, realistic foley, no music",
    },
    {
        "nome": "glitch_tv",
        "arquivo": "glitch_tv.wav",
        "categoria": "eletronico",
        "duracao_alvo_s": 0.55,
        "ganho_db": -2.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=tv+static+glitch+short&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Short analog baby monitor video static glitch burst with wireless signal interference crackle, clean foley, no music",
    },
    {
        "nome": "impacto_twist",
        "arquivo": "impacto_twist.wav",
        "categoria": "climax",
        "duracao_alvo_s": 1.4,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=horror+sting+boom+impact&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Terrifying horror plot twist slam with massive deep sub bass hit, sharp metallic sting and sudden silence, trailer quality, no music",
    },
    {
        "nome": "guarda_roupa",
        "arquivo": "guarda_roupa.wav",
        "categoria": "foley",
        "duracao_alvo_s": 1.6,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=wooden+door+creak+slow&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Old wooden wardrobe closet door creaking open slowly in quiet dark bedroom, realistic dry wood friction and hinge foley, no music",
    },
    {
        "nome": "interfone",
        "arquivo": "interfone.wav",
        "categoria": "eletronico",
        "duracao_alvo_s": 1.2,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=apartment+intercom+buzzer+static&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Brazilian apartment building intercom buzzer buzz with analog speaker static crackle and light midnight rain outside, realistic foley, no music",
    },
    {
        "nome": "porta_elevador",
        "arquivo": "porta_elevador.wav",
        "categoria": "foley",
        "duracao_alvo_s": 1.1,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=elevator+door+close+metal&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Heavy stainless steel apartment elevator doors sliding shut slowly with electric track hum and firm mechanical latch thud indoors, realistic foley, no music",
    },
    {
        "nome": "tranco_elevador",
        "arquivo": "tranco_elevador.wav",
        "categoria": "impacto",
        "duracao_alvo_s": 1.2,
        "ganho_db": 0.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=elevator+stop+jolt+metal+bang&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Old apartment elevator suddenly jolting and braking hard to a halt with heavy metallic cable shudder, electrical relay snap and dark power drop, cinematic foley, no music",
    },
    {
        "nome": "alarme_interfone",
        "arquivo": "alarme_interfone.wav",
        "categoria": "eletronico",
        "duracao_alvo_s": 1.1,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=elevator+alarm+bell+button&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Desperate repeated presses on plastic elevator emergency button followed by muffled metallic elevator alarm bell buzz inside steel cabin, realistic foley, no music",
    },
    {
        "nome": "glitch_cta",
        "arquivo": "glitch_cta.wav",
        "categoria": "transicao",
        "duracao_alvo_s": 0.38,
        "ganho_db": -1.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=tape+stop+glitch+transition&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Short crisp cinematic tape stop brake with subtle analog glitch crackle and clean punch cut transition, studio quality, no music",
    },
    {
        "nome": "cta_pop",
        "arquivo": "cta_pop.wav",
        "categoria": "ui",
        "duracao_alvo_s": 0.22,
        "ganho_db": -2.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=ui+pop+click+clean&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Crisp clean subtle modern interface pop click notification sound, dry studio quality, no music",
    },
    {
        "nome": "motor_acelerando",
        "arquivo": "motor_acelerando.wav",
        "categoria": "veiculo",
        "duracao_alvo_s": 1.15,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=car+engine+accelerating+interior&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Sedan car engine accelerating aggressively from inside dark cabin at night on wet city avenue, deep low exhaust roar and cabin rumble rising fast, realistic foley, no music",
    },
    {
        "nome": "trava_porta_carro",
        "arquivo": "trava_porta_carro.wav",
        "categoria": "foley",
        "duracao_alvo_s": 1.1,
        "ganho_db": 0.5,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=car+door+handle+locked&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Desperate repeated pulls on locked interior car door handle with crisp metallic child lock clack and hollow plastic rattle inside sedan cabin, realistic foley, no music",
    },
    {
        "nome": "celular_tocando",
        "arquivo": "celular_tocando.wav",
        "categoria": "eletronico",
        "duracao_alvo_s": 1.2,
        "ganho_db": 0.0,
        "licenca": "CC0 / ElevenLabs SFX",
        "fonte_cc0": "https://freesound.org/search/?q=smartphones+vibrating+ringing+car&f=license:%22Creative+Commons+0%22",
        "url_download_cc0": "",
        "prompt_elevenlabs": "Multiple smartphones vibrating simultaneously on car passenger seat leather with overlapping urgent incoming call chimes inside dark quiet car cabin, realistic foley, no music",
    },
]


def carregar_env(caminho_env: Path = ARQUIVO_ENV) -> bool:
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


def carregar_catalogo() -> dict:
    if CATALOGO_JSON.is_file():
        return json.loads(CATALOGO_JSON.read_text(encoding="utf-8"))
    return {
        "versao": 1,
        "padrao_tecnico": {
            "sample_rate_hz": SR_PADRAO,
            "channels": CANAIS_PADRAO,
            "codec": "pcm_s16le",
            "loudness_alvo_lufs": -18.0,
            "true_peak_max_dbtp": -3.0,
            "ataque_max_s": 0.015,
        },
        "efeitos": [
            {**item, "origem": "fallback_procedural_hd", "presente": False, "duracao_s": None, "pico_dbfs": None}
            for item in CATALOGO_CURADO
        ],
    }


def salvar_catalogo(dados: dict) -> None:
    PASTA_SFX.mkdir(parents=True, exist_ok=True)
    CATALOGO_JSON.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def localizar_arquivo_sfx(nome: str) -> Path | None:
    for ext in EXTENSOES_SUPORTADAS:
        cand = PASTA_SFX / f"{nome}{ext}"
        if cand.is_file() and cand.stat().st_size > 0:
            return cand
    return None


def padronizar_para_wav(origem: Path, destino_wav: Path, duracao_max: float | None = None) -> None:
    """Padroniza qualquer audio para 44100 Hz, estereo, PCM 16-bit, sem silencio morto no ataque."""
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg precisa estar instalado e no PATH.")
    destino_wav.parent.mkdir(parents=True, exist_ok=True)
    filtro = (
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB:detection=peak,"
        "loudnorm=I=-18:TP=-3:LRA=9"
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
    ]
    if duracao_max is not None and duracao_max > 0.1:
        cmd.extend(["-t", f"{duracao_max:.3f}"])
    cmd.extend([
        "-ar",
        str(SR_PADRAO),
        "-ac",
        str(CANAIS_PADRAO),
        "-c:a",
        "pcm_s16le",
        str(destino_wav),
    ])
    subprocess.run(cmd, check=True)


def inspecionar_audio(caminho: Path) -> dict:
    """Inspeciona taxa, canais, codec, duracao, pico dBFS e atraso do transiente inicial."""
    info = {
        "arquivo": caminho.name,
        "tamanho_kb": round(caminho.stat().st_size / 1024.0, 1),
        "sample_rate": None,
        "channels": None,
        "codec": None,
        "duracao_s": None,
        "pico_dbfs": None,
        "ataque_s": None,
        "padrao_ok": False,
        "avisos": [],
    }
    if shutil.which("ffprobe"):
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels:format=duration",
                "-of",
                "json",
                str(caminho),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        dados = json.loads(res.stdout)
        stream = (dados.get("streams") or [{}])[0]
        fmt = dados.get("format") or {}
        info["codec"] = stream.get("codec_name")
        info["sample_rate"] = int(stream["sample_rate"]) if stream.get("sample_rate") else None
        info["channels"] = int(stream["channels"]) if stream.get("channels") else None
        info["duracao_s"] = round(float(fmt["duration"]), 3) if fmt.get("duration") else None

    if caminho.suffix.lower() == ".wav":
        try:
            with wave.open(str(caminho), "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                bruto = wf.readframes(wf.getnframes())
            if sw == 2 and bruto:
                from array import array

                amostras = array("h")
                amostras.frombytes(bruto)
                pico = max((abs(v) for v in amostras), default=0)
                info["pico_dbfs"] = round(20.0 * math.log10(max(pico, 1) / 32768.0), 2)
                limiar = int(32768 * (10 ** (-42.0 / 20.0)))
                ataque_frame = None
                for idx in range(0, len(amostras), ch):
                    if any(abs(amostras[idx + c]) >= limiar for c in range(ch)):
                        ataque_frame = idx // ch
                        break
                if ataque_frame is not None:
                    info["ataque_s"] = round(ataque_frame / float(sr), 4)
        except Exception as exc:
            info["avisos"].append(f"leitura wav: {exc}")

    if info["sample_rate"] != SR_PADRAO:
        info["avisos"].append(f"sample_rate={info['sample_rate']} (padrao {SR_PADRAO})")
    if info["channels"] != CANAIS_PADRAO:
        info["avisos"].append(f"channels={info['channels']} (padrao {CANAIS_PADRAO})")
    if caminho.suffix.lower() == ".wav" and info["codec"] != "pcm_s16le":
        info["avisos"].append(f"codec={info['codec']} (padrao pcm_s16le)")
    if info["ataque_s"] is not None and info["ataque_s"] > 0.020:
        info["avisos"].append(f"ataque atrasado ({info['ataque_s']}s > 0.015s)")
    if info["pico_dbfs"] is not None and info["pico_dbfs"] > -0.3:
        info["avisos"].append(f"pico alto ({info['pico_dbfs']} dBFS)")

    info["padrao_ok"] = len(info["avisos"]) == 0
    return info


def auditar_biblioteca(atualizar_json: bool = False) -> int:
    PASTA_SFX.mkdir(parents=True, exist_ok=True)
    cat = carregar_catalogo()
    efeitos = cat.get("efeitos", [])
    nomes_catalogados = {e["nome"] for e in efeitos}

    reais = 0
    fallbacks = 0
    fora_padrao = 0

    print(f"Auditoria da biblioteca de SFX reais: {PASTA_SFX.relative_to(RAIZ).as_posix()}/")
    print(f"{'EFEITO':<18} {'STATUS':<14} {'ARQUIVO':<22} {'DUR(s)':<8} {'PICO(dBFS)':<11} {'DETALHE'}")
    print("-" * 92)

    for item in efeitos:
        nome = item["nome"]
        arq = localizar_arquivo_sfx(nome)
        if arq is not None:
            reais += 1
            meta = inspecionar_audio(arq)
            status = "REAL OK" if meta["padrao_ok"] else "REAL AVISO"
            if not meta["padrao_ok"]:
                fora_padrao += 1
            dur_s = f"{meta['duracao_s']:.3f}" if meta["duracao_s"] is not None else "-"
            pico_s = f"{meta['pico_dbfs']:.2f}" if meta["pico_dbfs"] is not None else "-"
            detalhe = "; ".join(meta["avisos"]) if meta["avisos"] else "44100Hz 2ch PCM ok"
            print(f"{nome:<18} {status:<14} {arq.name:<22} {dur_s:<8} {pico_s:<11} {detalhe}")
            if atualizar_json:
                item["presente"] = True
                item["arquivo"] = arq.name
                item["duracao_s"] = meta["duracao_s"]
                item["pico_dbfs"] = meta["pico_dbfs"]
                if item.get("origem") == "fallback_procedural_hd":
                    item["origem"] = "arquivo_real_local"
        else:
            fallbacks += 1
            print(
                f"{nome:<18} {'FALLBACK HD':<14} {'(ausente)':<22} "
                f"{item.get('duracao_alvo_s', 0):<8.2f} {'-':<11} sintese acustica procedural"
            )
            if atualizar_json:
                item["presente"] = False
                item["duracao_s"] = None
                item["pico_dbfs"] = None
                item["origem"] = "fallback_procedural_hd"

    extras = sorted(
        p.name
        for p in PASTA_SFX.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES_SUPORTADAS and p.stem not in nomes_catalogados
    )
    if extras:
        print(f"\nArquivos extras encontrados (nao listados em catalogo.json): {', '.join(extras)}")

    print("-" * 92)
    print(
        f"Resumo: {reais} SFX real(is) encontrado(s) | {fallbacks} em fallback procedural HD | "
        f"{fora_padrao} aviso(s) de padronizacao."
    )
    if atualizar_json:
        salvar_catalogo(cat)
        print(f"Catalogo atualizado em {CATALOGO_JSON.relative_to(RAIZ).as_posix()}.")
    return 0


def gerar_via_elevenlabs(efeitos_filtro: set[str] | None, sobrescrever: bool) -> int:
    carregar_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "ELEVENLABS_API_KEY nao encontrada no ambiente nem no .env local. "
            "Configure a chave ou use --importar para adicionar arquivos CC0 locais."
        )

    cat = carregar_catalogo()
    gerados = 0
    for item in cat.get("efeitos", []):
        nome = item["nome"]
        if efeitos_filtro and nome not in efeitos_filtro:
            continue
        destino = PASTA_SFX / f"{nome}.wav"
        if destino.is_file() and not sobrescrever:
            print(f"[SKIP] {destino.name} ja existe (use --sobrescrever para regenerar).")
            continue

        dur = max(0.5, min(5.0, float(item.get("duracao_alvo_s", 1.5))))
        payload = json.dumps(
            {
                "text": item["prompt_elevenlabs"],
                "duration_seconds": dur,
                "prompt_influence": 0.45,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/sound-generation",
            data=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        print(f"[GEN] {nome} ({dur:.2f}s) via ElevenLabs Sound Effects...", flush=True)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                dados_mp3 = resp.read()
        except urllib.error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", errors="replace")[:240]
            print(f"[ERRO] HTTP {exc.code} ao gerar {nome}: {corpo}")
            continue
        except Exception as exc:
            print(f"[ERRO] Falha de rede ao gerar {nome}: {exc}")
            continue

        with tempfile.TemporaryDirectory(prefix="sfx-el-") as tmp:
            bruto = Path(tmp) / f"{nome}.mp3"
            bruto.write_bytes(dados_mp3)
            padronizar_para_wav(bruto, destino, duracao_max=dur + 0.15)
        item["origem"] = "elevenlabs_sound_effects"
        item["licenca"] = "ElevenLabs Generated"
        gerados += 1
        print(f"[OK] Salvo e padronizado: {destino.relative_to(RAIZ).as_posix()}")

    salvar_catalogo(cat)
    auditar_biblioteca(atualizar_json=True)
    print(f"Total gerado nesta execucao: {gerados}")
    return 0


def baixar_fontes_cc0(efeitos_filtro: set[str] | None, sobrescrever: bool) -> int:
    cat = carregar_catalogo()
    baixados = 0
    for item in cat.get("efeitos", []):
        nome = item["nome"]
        if efeitos_filtro and nome not in efeitos_filtro:
            continue
        destino = PASTA_SFX / f"{nome}.wav"
        if destino.is_file() and not sobrescrever:
            print(f"[SKIP] {destino.name} ja existe.")
            continue
        url = str(item.get("url_download_cc0", "")).strip()
        if not url:
            print(
                f"[MANUAL] {nome}: sem URL direta configurada. Busca CC0: {item.get('fonte_cc0', '-')} "
                f"(depois rode: python3 audio/baixar_sfx.py --importar {nome} <arquivo>)"
            )
            continue
        print(f"[DOWN] Baixando {nome} de {url}...", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gps-canal-dark-sfx/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                dados = resp.read()
        except Exception as exc:
            print(f"[AVISO] Nao foi possivel baixar {nome}: {exc}")
            continue
        with tempfile.TemporaryDirectory(prefix="sfx-cc0-") as tmp:
            bruto = Path(tmp) / f"{nome}.bin"
            bruto.write_bytes(dados)
            padronizar_para_wav(bruto, destino, duracao_max=float(item.get("duracao_alvo_s", 2.0)) + 0.3)
        item["origem"] = "cc0_download"
        item["licenca"] = "CC0"
        baixados += 1
        print(f"[OK] Baixado e padronizado: {destino.relative_to(RAIZ).as_posix()}")

    salvar_catalogo(cat)
    auditar_biblioteca(atualizar_json=True)
    print(f"Total baixado nesta execucao: {baixados}")
    return 0


def importar_arquivo_local(nome: str, origem: Path, licenca: str) -> int:
    if not origem.is_file():
        raise SystemExit(f"Arquivo de origem nao encontrado: {origem}")
    cat = carregar_catalogo()
    destino = PASTA_SFX / f"{nome}.wav"
    padronizar_para_wav(origem, destino)

    encontrado = None
    for item in cat.get("efeitos", []):
        if item["nome"] == nome:
            encontrado = item
            break
    if encontrado is None:
        encontrado = {
            "nome": nome,
            "arquivo": destino.name,
            "categoria": "custom",
            "duracao_alvo_s": 1.5,
            "ganho_db": 0.0,
            "origem": f"importado_local ({origem.name})",
            "licenca": licenca,
            "prompt_elevenlabs": "",
            "fonte_cc0": "",
            "url_download_cc0": "",
            "presente": True,
            "duracao_s": None,
            "pico_dbfs": None,
        }
        cat.setdefault("efeitos", []).append(encontrado)
    else:
        encontrado["origem"] = f"importado_local ({origem.name})"
        encontrado["licenca"] = licenca
        encontrado["arquivo"] = destino.name

    salvar_catalogo(cat)
    print(f"Importado e padronizado para 44100Hz 16-bit estereo: {destino.relative_to(RAIZ).as_posix()}")
    return auditar_biblioteca(atualizar_json=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audita, importa ou baixa/gera SFX reais padronizados para assets/sfx/."
    )
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Audita assets/sfx/ e lista quais efeitos sao reais e quais usam fallback procedural HD.",
    )
    parser.add_argument(
        "--atualizar-catalogo",
        action="store_true",
        help="Usado com --verificar para sincronizar assets/sfx/catalogo.json.",
    )
    parser.add_argument(
        "--baixar",
        action="store_true",
        help="Baixa efeitos com url_download_cc0 definida e lista buscas CC0 para os demais.",
    )
    parser.add_argument(
        "--elevenlabs",
        action="store_true",
        help="Gera SFX reais via ElevenLabs Sound Effects usando ELEVENLABS_API_KEY do ambiente/.env.",
    )
    parser.add_argument(
        "--importar",
        nargs=2,
        metavar=("NOME", "ARQUIVO"),
        help="Importa e padroniza um arquivo .wav/.mp3 local como assets/sfx/<NOME>.wav.",
    )
    parser.add_argument(
        "--licenca",
        default="CC0",
        help="Licenca registrada no catalogo ao usar --importar (padrao: CC0).",
    )
    parser.add_argument(
        "--efeitos",
        nargs="*",
        default=None,
        help="Filtra nomes especificos ao usar --baixar ou --elevenlabs.",
    )
    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Regenera/sobrescreve arquivos que ja existem em assets/sfx/.",
    )
    args = parser.parse_args()

    filtro = set(args.efeitos) if args.efeitos else None
    if args.importar:
        sys.exit(importar_arquivo_local(args.importar[0].strip(), Path(args.importar[1]), args.licenca))
    if args.elevenlabs:
        sys.exit(gerar_via_elevenlabs(filtro, args.sobrescrever))
    if args.baixar:
        sys.exit(baixar_fontes_cc0(filtro, args.sobrescrever))
    sys.exit(auditar_biblioteca(atualizar_json=args.atualizar_catalogo))


if __name__ == "__main__":
    main()
