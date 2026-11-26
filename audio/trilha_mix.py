"""Tratamento profissional de audio FFmpeg para a Estacao 3 (trilha ambiente + ducking + -14 LUFS).

Recursos:
1. Trilha musical automatica:
   - Se existir qualquer `.mp3` ou `.wav` em `assets/trilhas/`, sorteia uma trilha aleatoria em loop
     (`-stream_loop -1`) ajustada a duracao exata do video.
   - Se `assets/trilhas/` estiver vazia, sintetiza automaticamente uma trilha ambiente dark/suspense
     sutil via FFmpeg (`anoisesrc` pink + `sine` sub-grave 55Hz/82.41Hz filtrados em grave baixo)
     para nunca faltar fundo musical.
2. Ducking automatico (`sidechaincompress`):
   - A trilha e calibrada para permanecer bem baixinha (-22 dB a -26 dB) enquanto o narrador fala
     e subir levemente nas pausas naturais.
3. Normalizacao social (`loudnorm`):
   - A voz principal e normalizada para o padrao de redes sociais (-14 LUFS, TP -1.5 dBTP)
     para soar firme e nitida no celular.

Uso CLI (teste/mixagem avulsa):
    python3 audio/trilha_mix.py --voz audio/voz_limpa.mp3 --saida /tmp/mix_teste.mp3
    python3 audio/trilha_mix.py --voz audio/voz_limpa.mp3 --saida /tmp/mix_teste.mp3 --trilha assets/trilhas/dark.mp3
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

PASTA_TRILHAS = RAIZ / "assets" / "trilhas"
EXTENSOES_TRILHA: tuple[str, ...] = (".mp3", ".wav")
TAXA_AMOSTRAGEM = 44100

# Calibracao medida em FFmpeg 6.x:
# - Voz principal: loudnorm I=-14 LUFS, TP=-1.5 dBTP, LRA=11
# - Trilha base: atmosfera limpa e sutil sem zumbido (pausa ~ -21 dB, ducking durante fala ~ -25 dB)
LOUDNORM_VOZ = "loudnorm=I=-14:TP=-1.5:LRA=11"
LOUDNORM_TRILHA_BASE = "loudnorm=I=-21:TP=-3.0:LRA=7"
SILENCEREMOVE_INICIO = "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB"
SIDECHAIN_DUCKING = "sidechaincompress=threshold=0.045:ratio=3.0:attack=15:release=260:knee=4:makeup=1"
LIMITER_FINAL = "alimiter=limit=0.89:attack=5:release=50"


def listar_trilhas_disponiveis(pasta_trilhas: Path = PASTA_TRILHAS) -> list[Path]:
    """Lista todos os arquivos .mp3 e .wav validos (> 0 bytes) em assets/trilhas/."""
    if not pasta_trilhas.is_dir():
        return []
    return sorted(
        p
        for p in pasta_trilhas.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES_TRILHA and p.stat().st_size > 0
    )


def selecionar_trilha_aleatoria(
    pasta_trilhas: Path = PASTA_TRILHAS,
    rng: random.Random | None = None,
) -> Path | None:
    """Seleciona aleatoriamente um .mp3/.wav de assets/trilhas/, ou None quando a pasta esta vazia."""
    candidatos = listar_trilhas_disponiveis(pasta_trilhas)
    if not candidatos:
        return None
    gerador = rng if rng is not None else random
    return gerador.choice(candidatos)


def medir_duracao_audio(caminho: Path) -> float:
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


def medir_loudness_lufs(caminho: Path) -> dict[str, float]:
    """Mede loudness integrado (LUFS) e true peak (dBTP) via filtro loudnorm do FFmpeg."""
    res = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(caminho),
            "-vn",
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"\{[\s\S]*\}", res.stderr)
    if not m:
        raise RuntimeError(f"Nao foi possivel extrair metricas loudnorm para {caminho}.")
    dados = json.loads(m.group(0))
    return {
        "input_i": float(dados["input_i"]),
        "input_tp": float(dados["input_tp"]),
        "input_lra": float(dados["input_lra"]),
    }


def montar_filtro_trilha_sintetizada(
    duracao: float,
    *,
    duracao_processamento: float | None = None,
    label_saida: str = "bgm_base",
    sample_rate: int = TAXA_AMOSTRAGEM,
) -> str:
    """Sintetiza atmosfera dark/suspense limpa e sutil (grave suave, sem zumbido incomodo)."""
    dur = max(0.5, float(duracao))
    dur_proc = max(3.5, dur) if duracao_processamento is None else max(dur, float(duracao_processamento))
    fade_in = min(0.45, dur * 0.20)
    fade_out = min(0.65, dur * 0.25)
    fade_out_ini = max(0.0, dur - fade_out)
    return (
        f"anoisesrc=color=pink:sample_rate={sample_rate}:amplitude=0.28:duration={dur_proc:.3f},"
        "highpass=f=75,lowpass=f=420[bgm_noise];"
        f"sine=frequency=55:sample_rate={sample_rate}:duration={dur_proc:.3f},volume=0.045,lowpass=f=100[bgm_sub];"
        f"sine=frequency=82.41:sample_rate={sample_rate}:duration={dur_proc:.3f},volume=0.025,lowpass=f=140[bgm_fifth];"
        "[bgm_noise][bgm_sub][bgm_fifth]amix=inputs=3:duration=first:normalize=0,"
        f"aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
        f"{LOUDNORM_TRILHA_BASE},"
        f"afade=t=in:st=0:d={fade_in:.3f},afade=t=out:st={fade_out_ini:.3f}:d={fade_out:.3f}[{label_saida}]"
    )


def montar_filtro_mixagem_audio(
    voice_input_idx: int,
    duracao: float,
    *,
    trilha_path: Path | None = None,
    trilha_input_idx: int | None = None,
    label_saida: str = "aout",
    sample_rate: int = TAXA_AMOSTRAGEM,
) -> tuple[list[str], str, str, str]:
    """Constroi inputs extras e filter_complex de voz (-14 LUFS) + trilha (loop ou sintese) + ducking.

    Usa janela minima de 3.5s antes do loudnorm (exigencia interna EBU R128 de 3s) e corta
    exatamente para `duracao` na saida final, garantindo funcionamento impecavel inclusive em --teste (2s).
    """
    dur = max(0.5, float(duracao))
    dur_proc = max(3.5, dur)
    fade_in = min(0.45, dur * 0.20)
    fade_out = min(0.65, dur * 0.25)
    fade_out_ini = max(0.0, dur - fade_out)

    inputs_extras: list[str] = []
    partes: list[str] = [
        f"[{voice_input_idx}:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
        f"{SILENCEREMOVE_INICIO},"
        f"apad,atrim=0:{dur_proc:.3f},asetpts=PTS-STARTPTS,"
        f"{LOUDNORM_VOZ},asplit=2[v_main][v_sc]"
    ]

    if trilha_path is not None and trilha_path.is_file() and trilha_path.stat().st_size > 0:
        idx_t = (voice_input_idx + 1) if trilha_input_idx is None else int(trilha_input_idx)
        inputs_extras = ["-stream_loop", "-1", "-i", str(trilha_path)]
        partes.append(
            f"[{idx_t}:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
            f"atrim=0:{dur_proc:.3f},asetpts=PTS-STARTPTS,"
            f"highpass=f=35,lowpass=f=4500,{LOUDNORM_TRILHA_BASE},"
            f"afade=t=in:st=0:d={fade_in:.3f},afade=t=out:st={fade_out_ini:.3f}:d={fade_out:.3f}[bgm_base]"
        )
        origem_desc = f"trilha_loop:{trilha_path.name}"
    else:
        partes.append(
            montar_filtro_trilha_sintetizada(
                dur,
                duracao_processamento=dur_proc,
                label_saida="bgm_base",
                sample_rate=sample_rate,
            )
        )
        origem_desc = "sintese_dark_ffmpeg"

    partes.append(f"[bgm_base][v_sc]{SIDECHAIN_DUCKING}[bgm_duck]")
    partes.append(
        f"[v_main][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"{LIMITER_FINAL},atrim=0:{dur:.3f},asetpts=PTS-STARTPTS[{label_saida}]"
    )
    return inputs_extras, ";".join(partes), label_saida, origem_desc


def montar_comando_mix_audio_avulso(
    voz_entrada: Path,
    destino_saida: Path,
    duracao: float,
    *,
    trilha_path: Path | None = None,
) -> tuple[list[str], str]:
    """Monta comando FFmpeg completo para mixar voz + trilha/sintese + ducking + -14 LUFS em arquivo de audio."""
    inputs_extras, fc, out_lbl, origem_desc = montar_filtro_mixagem_audio(
        voice_input_idx=0,
        duracao=duracao,
        trilha_path=trilha_path,
        trilha_input_idx=1,
        label_saida="aout",
    )
    ext = destino_saida.suffix.lower()
    if ext == ".wav":
        codec_args = ["-c:a", "pcm_s16le"]
    elif ext in (".m4a", ".aac"):
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
    else:
        codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(voz_entrada),
        *inputs_extras,
        "-filter_complex",
        fc,
        "-map",
        f"[{out_lbl}]",
        "-ar",
        str(TAXA_AMOSTRAGEM),
        "-ac",
        "2",
        *codec_args,
        "-t",
        f"{duracao:.3f}",
        str(destino_saida),
    ]
    return cmd, origem_desc


def mixar_audio_profissional(
    voz_entrada: Path,
    destino_saida: Path,
    *,
    duracao: float | None = None,
    trilha_forcada: Path | None = None,
    pasta_trilhas: Path = PASTA_TRILHAS,
    rng: random.Random | None = None,
) -> dict:
    """Executa mixagem profissional avulsa e retorna origem, comando e metricas de loudness."""
    if not voz_entrada.is_file():
        raise FileNotFoundError(f"Arquivo de voz nao encontrado: {voz_entrada}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    dur_real = float(duracao) if duracao is not None else medir_duracao_audio(voz_entrada)
    trilha = trilha_forcada if trilha_forcada is not None else selecionar_trilha_aleatoria(pasta_trilhas, rng=rng)
    destino_saida.parent.mkdir(parents=True, exist_ok=True)

    cmd, origem_desc = montar_comando_mix_audio_avulso(
        voz_entrada=voz_entrada,
        destino_saida=destino_saida,
        duracao=dur_real,
        trilha_path=trilha,
    )
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou na mixagem de audio (codigo {res.returncode}): {res.stderr.strip()}")

    stats = medir_loudness_lufs(destino_saida)
    return {
        "origem_trilha": origem_desc,
        "trilha_arquivo": str(trilha) if trilha is not None else None,
        "duracao": round(medir_duracao_audio(destino_saida), 3),
        "lufs": stats["input_i"],
        "true_peak_dbtp": stats["input_tp"],
        "cmd": cmd,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mixador profissional FFmpeg: trilha em loop ou sintese dark + sidechaincompress + loudnorm -14 LUFS."
    )
    parser.add_argument("--voz", type=Path, required=True, help="Arquivo de voz principal (.mp3 ou .wav).")
    parser.add_argument("--saida", "-o", type=Path, required=True, help="Arquivo de audio de saida.")
    parser.add_argument("--trilha", type=Path, default=None, help="Trilha manual opcional (.mp3/.wav).")
    parser.add_argument(
        "--pasta-trilhas",
        type=Path,
        default=PASTA_TRILHAS,
        help="Pasta de trilhas aleatorias (padrao: assets/trilhas).",
    )
    parser.add_argument("--duracao", type=float, default=None, help="Duracao alvo em segundos (padrao: duracao da voz).")
    args = parser.parse_args()

    voz = args.voz if args.voz.is_absolute() else (RAIZ / args.voz)
    saida = args.saida if args.saida.is_absolute() else (RAIZ / args.saida)
    trilha = None
    if args.trilha is not None:
        trilha = args.trilha if args.trilha.is_absolute() else (RAIZ / args.trilha)
    pasta_trilhas = args.pasta_trilhas if args.pasta_trilhas.is_absolute() else (RAIZ / args.pasta_trilhas)

    info = mixar_audio_profissional(
        voz_entrada=voz,
        destino_saida=saida,
        duracao=args.duracao,
        trilha_forcada=trilha,
        pasta_trilhas=pasta_trilhas,
    )
    print(
        f"Audio profissional pronto: {saida} ({info['duracao']:.2f}s) | "
        f"trilha={info['origem_trilha']} | loudness={info['lufs']:.2f} LUFS (TP={info['true_peak_dbtp']:.2f} dBTP)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
