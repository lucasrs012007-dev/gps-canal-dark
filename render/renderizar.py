"""Estacao 3 (Motor Cinematografico IA V8.0): Cortes rapidos 1080x1920 @ 30fps via FFmpeg.

Uso (na raiz do repositorio):
    python3 render/renderizar.py --legendas          # render completo (output/short_NN.mp4 + parte1 + parte2)
    python3 render/renderizar.py --legendas --teste  # render rapido de 3s (90 quadros @ 30fps) para validacao
    python3 render/renderizar.py --legendas --dry-run-ffmpeg

Recursos V8.0 (zero boneco Canvas, zero player_universal.html, zero badge PARTE 1, zero caixa HUD):
- Combina midias unicas por cena geradas em `output/cenas/`:
  * Clipes de video IA `.mp4` (quando `FAL_KEY` foi usada na Estacao 3A), ou
  * Imagens cinematograficas 9:16 `.jpg` da Gemini Image API com movimento de camera 30fps perceptivel
    (zoom-in rapido, zoom-out, pans diagonais, pans horizontais e camera-shake sutil em tensao/climax).
- Aplica transicoes rapidas (`xfade` de 0.15s), vinheta cinematografica e camada atmosferica viva
  (grao de filme animado `noise=alls=4:allf=t+u` para nenhum quadro parecer estatico).
- Queima legendas ASS limpas palavra por palavra centralizadas na area segura Shorts/Reels/TikTok
  (branco nitido, palavra ativa em amarelo `#FFD400`, gatilhos de alerta em vermelho `#FF3B30`,
  contorno preto grosso e acentuacao UTF-8 intacta).
- Mixa audio profissional via `audio/trilha_mix.py` (trilha aleatoria em loop ou atmosfera dark sutil,
  ducking automatico `sidechaincompress` e normalizacao social `-14 LUFS`).
- Exporta MP4 Full HD vertical 1080x1920 (`libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30`),
  mantendo compatibilidade total com `upload_youtube.py`, `upload_instagram.py`, `upload_tiktok.py`,
  `automacao/enviar_telegram.py` e corte automatico Parte 1 / Parte 2.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from audio.trilha_mix import (  # noqa: E402
    PASTA_TRILHAS,
    montar_filtro_mixagem_audio,
    selecionar_trilha_aleatoria,
)
from pipeline.historico import (  # noqa: E402
    caminho_saida_atual,
    caminhos_partes_atual,
    obter_video_atual,
    validar_artefatos_audio,
)

MOTOR_EXCLUSIVO = "cinematografico_ia_30fps"
PASTA_AUDIO = RAIZ / "audio"
PASTA_CENAS_PADRAO = RAIZ / "output" / "cenas"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
AUDIO_MIX = PASTA_AUDIO / "mix_final.mp3"
AUDIO_MP3 = PASTA_AUDIO / "narracao.mp3"
AUDIO_VOZ_LIMPA = PASTA_AUDIO / "voz_limpa.mp3"
TIMESTAMPS_JSON = PASTA_AUDIO / "timestamps.json"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"

LARGURA = 1080
ALTURA = 1920
OVERSAMPLE_LARGURA = 1296
OVERSAMPLE_ALTURA = 2304
FPS_PADRAO = 30
DURACAO_PREVIA = 45.0
DURACAO_TESTE_S = 3.0
FOLGA_AUDIO = 0.25
TRANSICAO_XFADE_PADRAO_S = 0.15

TAMANHO_MIN_IMAGEM_BYTES = 20 * 1024
TAMANHO_MIN_VIDEO_BYTES = 40 * 1024

MOVIMENTOS_CAMERA: tuple[str, ...] = (
    "push_in",
    "pan_diag_tl",
    "pull_out",
    "pan_diag_br",
    "pan_right",
    "pan_left",
)

MAPA_CAMERA_MOVIMENTO: dict[str, str] = {
    "push_in": "push_in",
    "zoom_in": "push_in",
    "pull_out": "pull_out",
    "zoom_out": "pull_out",
    "pan_diag_tl": "pan_diag_tl",
    "pan_diag_br": "pan_diag_br",
    "pan_left": "pan_left",
    "pan_rl": "pan_left",
    "pan_right": "pan_right",
    "pan_lr": "pan_right",
    "pan_ud": "pan_diag_tl",
    "pan_du": "pan_diag_br",
    "shake_impact": "shake_impact",
    "shake": "shake_impact",
    "static": "push_in",
    "hold": "pull_out",
}

TRANSICOES_RAPIDAS: tuple[str, ...] = (
    "fade",
    "dissolve",
    "smoothleft",
    "smoothright",
)


def duracao_audio_ffprobe(caminho: Path) -> float:
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


def _ler_json_opcional(caminho: Path) -> dict | None:
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None


def _normalizar_chave_palavra(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    limpo = "".join(ch for ch in sem_acento if not unicodedata.combining(ch))
    return "".join(ch for ch in limpo.lower() if ch.isalnum())


def _escapar_texto_ass(texto: str) -> str:
    return (
        str(texto or "")
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _formatar_tempo_ass(segundos: float) -> str:
    seg = max(0.0, float(segundos))
    cent_total = int(round(seg * 100.0))
    cent = cent_total % 100
    s_total = cent_total // 100
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h}:{m:02d}:{s:02d}.{cent:02d}"


def _escapar_caminho_filtro_ffmpeg(caminho: Path) -> str:
    txt = str(caminho.resolve()).replace("\\", "/")
    return txt.replace(":", r"\:").replace("'", r"\'")


def gerar_legenda_ass(
    timestamps_dados: dict | None,
    cenas_dados: dict | None,
    destino_ass: Path,
    duracao_max: float | None = None,
    fonte: str = "DejaVu Sans",
) -> Path | None:
    """Gera legendas ASS limpas palavra por palavra centralizadas (zero HUD, zero badge PARTE 1)."""
    if not isinstance(timestamps_dados, dict):
        return None
    grupos = timestamps_dados.get("grupos")
    if not isinstance(grupos, list) or not grupos:
        return None

    destaques_vermelhos: set[str] = set()
    if isinstance(cenas_dados, dict):
        for p in cenas_dados.get("palavras_vermelhas") or []:
            chave = _normalizar_chave_palavra(str(p))
            if chave:
                destaques_vermelhos.add(chave)

    cabecalho = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {LARGURA}",
        f"PlayResY: {ALTURA}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Branco limpo, palavra ativa em amarelo (#FFD400 = &H0000D4FF BGR), contorno preto grosso (6px),
        # centralizada na area segura de YouTube Shorts / Reels / TikTok (sem HUD superior nem badges).
        f"Style: Shorts,{fonte},76,&H00FFFFFF,&H0000D4FF,&H00000000,&H88000000,-1,0,0,0,100,100,1,0,1,6,3,2,96,96,470,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    eventos_ass: list[str] = []
    for grp in grupos:
        if not isinstance(grp, dict):
            continue
        palavras = grp.get("palavras")
        if not isinstance(palavras, list) or not palavras:
            g_ini = float(grp.get("inicio", 0.0))
            g_fim = float(grp.get("fim", g_ini + 0.4))
            if duracao_max is not None:
                if g_ini >= duracao_max:
                    continue
                g_fim = min(g_fim, duracao_max)
            if g_fim - g_ini < 0.04:
                continue
            texto_grp = _escapar_texto_ass(str(grp.get("texto", "")).upper())
            if texto_grp:
                eventos_ass.append(
                    f"Dialogue: 0,{_formatar_tempo_ass(g_ini)},{_formatar_tempo_ass(g_fim)},Shorts,,0,0,0,,{texto_grp}"
                )
            continue

        for idx_p, pal in enumerate(palavras):
            t_ini = float(pal.get("inicio", grp.get("inicio", 0.0)))
            if idx_p + 1 < len(palavras):
                t_fim = float(palavras[idx_p + 1].get("inicio", pal.get("fim", t_ini + 0.15)))
            else:
                t_fim = float(pal.get("fim", grp.get("fim", t_ini + 0.18)))
            if duracao_max is not None:
                if t_ini >= duracao_max:
                    continue
                t_fim = min(t_fim, duracao_max)
            if t_fim <= t_ini + 0.02:
                t_fim = min(duracao_max if duracao_max is not None else t_ini + 0.08, t_ini + 0.08)
            if t_fim <= t_ini + 0.01:
                continue

            partes_txt: list[str] = []
            for j, item_w in enumerate(palavras):
                palavra_up = _escapar_texto_ass(str(item_w.get("palavra", "")).upper())
                if not palavra_up:
                    continue
                chave_w = _normalizar_chave_palavra(palavra_up)
                if j == idx_p:
                    if chave_w in destaques_vermelhos:
                        partes_txt.append(
                            r"{\c&H00303BFF&\fscx109\fscy109}" + palavra_up + r"{\c&H00FFFFFF&\fscx100\fscy100}"
                        )
                    else:
                        partes_txt.append(
                            r"{\c&H0000D4FF&\fscx107\fscy107}" + palavra_up + r"{\c&H00FFFFFF&\fscx100\fscy100}"
                        )
                else:
                    partes_txt.append(palavra_up)
            linha_txt = " ".join(partes_txt).strip()
            if linha_txt:
                eventos_ass.append(
                    f"Dialogue: 0,{_formatar_tempo_ass(t_ini)},{_formatar_tempo_ass(t_fim)},Shorts,,0,0,0,,{linha_txt}"
                )

    if not eventos_ass:
        return None

    destino_ass.parent.mkdir(parents=True, exist_ok=True)
    destino_ass.write_text("\n".join(cabecalho + eventos_ass) + "\n", encoding="utf-8")
    return destino_ass


def escolher_movimento_cena(
    camera_hint: str | None,
    idx: int,
    anterior: str | None,
    *,
    tensao: bool = False,
    mood: str = "navy",
) -> str:
    """Alterna zoom-in rapido, zoom-out, pans diagonais/horizontais e shake de tensao sem repetir."""
    hint = MAPA_CAMERA_MOVIMENTO.get(str(camera_hint or "").strip().lower())
    if (tensao or str(mood).lower() == "red" or hint == "shake_impact") and anterior != "shake_impact":
        return "shake_impact"
    if hint and hint != anterior:
        return hint
    for desloc in range(len(MOVIMENTOS_CAMERA)):
        cand = MOVIMENTOS_CAMERA[(idx + desloc) % len(MOVIMENTOS_CAMERA)]
        if cand != anterior:
            return cand
    return "push_in"


def expressao_zoompan_cena(movimento: str, total_frames: int, fps: int) -> str:
    """Constroi filtro zoompan 30fps perceptivel com oversampling 1296x2304 -> 1080x1920."""
    n_frames = max(2, int(total_frames))
    denom = max(1, n_frames - 1)
    prog = f"min(1,on/{denom})"

    if movimento == "pull_out":
        expr = f"z='1.17-0.17*{prog}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif movimento == "pan_diag_tl":
        expr = f"z='1.18':x='(iw-iw/zoom)*{prog}':y='(ih-ih/zoom)*{prog}'"
    elif movimento == "pan_diag_br":
        expr = f"z='1.18':x='(iw-iw/zoom)*(1-{prog})':y='(ih-ih/zoom)*(1-{prog})'"
    elif movimento == "pan_right":
        expr = f"z='1.16':x='(iw-iw/zoom)*{prog}':y='ih/2-(ih/zoom/2)'"
    elif movimento == "pan_left":
        expr = f"z='1.16':x='(iw-iw/zoom)*(1-{prog})':y='ih/2-(ih/zoom/2)'"
    elif movimento == "shake_impact":
        # Push-in tenso + vibracao organica sutil contida dentro da margem oversampled
        expr = (
            f"z='1.14+0.04*{prog}':"
            "x='clip(iw/2-(iw/zoom/2)+10*sin(on*1.75)+5*cos(on*3.1),0,iw-iw/zoom)':"
            "y='clip(ih/2-(ih/zoom/2)+8*cos(on*2.15)+4*sin(on*2.9),0,ih-ih/zoom)'"
        )
    else:
        # push_in rapido e fluido
        expr = f"z='1+0.17*{prog}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    return (
        f"scale={OVERSAMPLE_LARGURA}:{OVERSAMPLE_ALTURA}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OVERSAMPLE_LARGURA}:{OVERSAMPLE_ALTURA},"
        f"zoompan={expr}:d={n_frames}:s={LARGURA}x{ALTURA}:fps={int(fps)}"
    )


def expressao_clip_video_cena(movimento: str, fps: int, dur_clip: float) -> str:
    """Padroniza clipe de video IA (.mp4 da fal.ai) em 1080x1920 @ 30fps com shake sutil em tensao."""
    if movimento == "shake_impact":
        # Oversample leve para camera-shake organico tambem nos clipes .mp4 de tensao
        return (
            "scale=1160:2062:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop=1160:2062,"
            f"fps={int(fps)},"
            f"crop={LARGURA}:{ALTURA}:x='40+10*sin(n*1.75)':y='71+8*cos(n*2.15)',"
            f"format=yuv420p,setsar=1,settb=AVTB,trim=duration={dur_clip:.4f},setpts=PTS-STARTPTS"
        )
    return (
        f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={LARGURA}:{ALTURA},"
        f"fps={int(fps)},"
        f"format=yuv420p,setsar=1,settb=AVTB,trim=duration={dur_clip:.4f},setpts=PTS-STARTPTS"
    )


def listar_midias_disponiveis(pasta_cenas: Path) -> list[tuple[Path, str]]:
    """Lista midias validas (`cena_*.mp4`, `cena_*.jpg`, `cena_*.png`) em `pasta_cenas`."""
    if not pasta_cenas.is_dir():
        return []
    encontradas: list[tuple[Path, str]] = []
    for p in sorted(pasta_cenas.glob("cena_*.*")):
        ext = p.suffix.lower()
        if not p.is_file():
            continue
        tam = p.stat().st_size
        if ext == ".mp4" and tam > TAMANHO_MIN_VIDEO_BYTES:
            encontradas.append((p, "video"))
        elif ext in (".jpg", ".jpeg", ".png") and tam > TAMANHO_MIN_IMAGEM_BYTES:
            encontradas.append((p, "imagem"))
    return encontradas


def resolver_midia_cena(
    pasta_cenas: Path,
    indice_1based: int,
    fallback_lista: list[tuple[Path, str]],
) -> tuple[Path, str]:
    """Resolve `cena_NN.mp4` (prioridade Video IA) ou `cena_NN.jpg`/`.png` para a cena."""
    mp4 = pasta_cenas / f"cena_{indice_1based:02d}.mp4"
    if mp4.is_file() and mp4.stat().st_size > TAMANHO_MIN_VIDEO_BYTES:
        return mp4, "video"
    for ext in (".jpg", ".jpeg", ".png"):
        img = pasta_cenas / f"cena_{indice_1based:02d}{ext}"
        if img.is_file() and img.stat().st_size > TAMANHO_MIN_IMAGEM_BYTES:
            return img, "imagem"
    if fallback_lista:
        return fallback_lista[(indice_1based - 1) % len(fallback_lista)]
    raise FileNotFoundError(
        f"Nenhuma midia valida (cena_NN.mp4 ou cena_NN.jpg) encontrada em {pasta_cenas}. "
        "Rode `python3 gerar_midia_cenas.py` antes de renderizar."
    )


def construir_timeline_cenas(
    cenas_dados: dict,
    eventos_dados: dict | None,
    duracao_total: float,
    pasta_cenas: Path = PASTA_CENAS_PADRAO,
) -> list[dict[str, Any]]:
    """Sincroniza cada cena visual (video .mp4 ou imagem .jpg) com a duracao exata da fala no audio."""
    lista = cenas_dados.get("cenas") if isinstance(cenas_dados, dict) else None
    if not isinstance(lista, list) or not lista:
        raise RuntimeError("cenas.json nao possui lista valida em 'cenas'.")

    ev = eventos_dados if isinstance(eventos_dados, dict) else {}
    dur = max(0.5, float(duracao_total))
    n = len(lista)

    dur_estimadas = [max(1.5, float(c.get("duracao_estimada_s") or 3.2)) for c in lista]
    soma_est = sum(dur_estimadas) or float(n * 3.2)

    inicios: list[float] = []
    acum_est = 0.0
    for idx, c in enumerate(lista):
        chave = str(c.get("evento_inicio") or c.get("id") or f"cena_{idx + 1:02d}")
        val = ev.get(chave)
        if isinstance(val, (int, float)) and val >= 0.0:
            inicios.append(float(val))
        else:
            dur_ref = max(dur, float(ev.get("duracao_total") or dur))
            inicios.append((acum_est / soma_est) * dur_ref)
        acum_est += dur_estimadas[idx]

    inicios[0] = 0.0
    for i in range(1, n):
        if inicios[i] <= inicios[i - 1] + 0.25:
            inicios[i] = inicios[i - 1] + 0.45

    midias_disponiveis = listar_midias_disponiveis(pasta_cenas)
    if not midias_disponiveis:
        raise FileNotFoundError(
            f"Nenhuma midia valida (cena_*.mp4 ou cena_*.jpg) encontrada em {pasta_cenas}. "
            "Rode `python3 gerar_midia_cenas.py` primeiro."
        )

    timeline: list[dict[str, Any]] = []
    mov_anterior: str | None = None

    for idx, c in enumerate(lista):
        t_ini = inicios[idx]
        if t_ini >= dur - 0.15:
            break
        t_fim = inicios[idx + 1] if idx + 1 < n else dur
        t_fim = min(dur, max(t_ini + 0.15, t_fim))
        dur_cena = round(t_fim - t_ini, 4)
        if dur_cena < 0.10:
            continue

        midia_path, tipo_midia = resolver_midia_cena(pasta_cenas, idx + 1, midias_disponiveis)
        mood = str(c.get("mood", "navy")).strip().lower()
        tensao = bool(c.get("tensao", False)) or mood == "red" or str(c.get("camera", "")).strip().lower() == "shake_impact"
        mov = escolher_movimento_cena(
            c.get("camera"),
            idx,
            mov_anterior,
            tensao=tensao,
            mood=mood,
        )
        mov_anterior = mov
        timeline.append(
            {
                "indice": idx + 1,
                "id": str(c.get("id") or f"cena_{idx + 1:02d}"),
                "midia": midia_path,
                "imagem": midia_path,
                "tipo_midia": tipo_midia,
                "inicio": round(t_ini, 4),
                "fim": round(t_fim, 4),
                "duracao": dur_cena,
                "movimento": mov,
                "mood": mood,
                "tensao": tensao,
            }
        )

    if not timeline:
        raise RuntimeError("Timeline de cenas vazia apos sincronizacao com a duracao do audio.")

    timeline[-1]["fim"] = round(dur, 4)
    timeline[-1]["duracao"] = round(max(0.15, dur - timeline[-1]["inicio"]), 4)
    return timeline


def _escolher_transicao_xfade(indice_destino: int, item_destino: dict[str, Any], total: int) -> str:
    """Escolhe transicao rapida (0.15s) adequada ao ritmo da cena."""
    if item_destino.get("tensao") or item_destino.get("mood") == "red":
        return "fadeblack" if (indice_destino == total - 1 or indice_destino % 2 == 1) else "dissolve"
    return TRANSICOES_RAPIDAS[(indice_destino - 1) % len(TRANSICOES_RAPIDAS)]


def montar_comando_ffmpeg_cinematografico(
    timeline: list[dict[str, Any]],
    saida: Path,
    fps: int,
    audio_alvo: Path | None,
    duracao: float,
    *,
    arquivo_ass: Path | None = None,
    transicao_s: float = TRANSICAO_XFADE_PADRAO_S,
    trilha_audio: Path | None = None,
    usar_mix_profissional: bool = True,
) -> list[str]:
    """Monta comando FFmpeg 1080x1920 @ 30fps: cortes rapidos + zoompan/video + xfade 0.15s + atmosfera + ASS + -14 LUFS."""
    if not timeline:
        raise ValueError("Timeline de cenas vazia.")

    fps_int = max(24, int(fps))
    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for item in timeline:
        midia = Path(item["midia"])
        if item.get("tipo_midia") == "video":
            cmd.extend(["-stream_loop", "-1", "-i", str(midia)])
        else:
            cmd.extend(["-i", str(midia)])

    audio_input_idx = len(timeline)
    inputs_audio_extras: list[str] = []
    fc_audio_mix: str | None = None
    audio_map_spec = f"{audio_input_idx}:a:0"

    if audio_alvo is not None:
        cmd.extend(["-i", str(audio_alvo)])
        if usar_mix_profissional:
            inputs_audio_extras, fc_audio_mix, audio_out_lbl, _origem = montar_filtro_mixagem_audio(
                voice_input_idx=audio_input_idx,
                duracao=duracao,
                trilha_path=trilha_audio,
                trilha_input_idx=audio_input_idx + 1,
                label_saida="aout",
            )
            cmd.extend(inputs_audio_extras)
            audio_map_spec = f"[{audio_out_lbl}]"
    else:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]
        )

    n = len(timeline)
    transicoes: list[float] = []
    for i in range(n - 1):
        d_atual = float(timeline[i]["duracao"])
        d_prox = float(timeline[i + 1]["duracao"])
        if transicao_s > 0.0 and min(d_atual, d_prox) >= max(0.45, transicao_s * 2.5):
            transicoes.append(round(float(transicao_s), 3))
        else:
            transicoes.append(0.0)

    partes_fc: list[str] = []
    folga_frame = round(1.0 / fps_int, 4)
    for i, item in enumerate(timeline):
        sobreposicao = transicoes[i] if i < n - 1 else 0.0
        # Margem de 1 quadro somente quando ha sobreposicao xfade para imunidade a arredondamento de PTS
        dur_clip = float(item["duracao"]) + sobreposicao + (folga_frame if sobreposicao > 0.0 else 0.0)
        if item.get("tipo_midia") == "video":
            filtro_cena = expressao_clip_video_cena(item["movimento"], fps=fps_int, dur_clip=dur_clip)
            partes_fc.append(f"[{i}:v]{filtro_cena}[v{i}]")
        else:
            total_frames = max(2, int(round(dur_clip * fps_int)) + 2)
            zp = expressao_zoompan_cena(item["movimento"], total_frames=total_frames, fps=fps_int)
            partes_fc.append(
                f"[{i}:v]{zp},format=yuv420p,setsar=1,settb=AVTB,"
                f"trim=duration={dur_clip:.4f},setpts=PTS-STARTPTS[v{i}]"
            )

    label_atual = "v0"
    tempo_acum = float(timeline[0]["duracao"])
    for i in range(1, n):
        t_xf = transicoes[i - 1]
        prox_label = f"xf{i}"
        if t_xf > 0.0:
            tipo_xf = _escolher_transicao_xfade(i, timeline[i], n)
            partes_fc.append(
                f"[{label_atual}][v{i}]xfade=transition={tipo_xf}:duration={t_xf:.3f}:offset={tempo_acum:.4f}[{prox_label}]"
            )
        else:
            partes_fc.append(f"[{label_atual}][v{i}]concat=n=2:v=1:a=0[{prox_label}]")
        label_atual = prox_label
        tempo_acum += float(timeline[i]["duracao"])

    # Camada atmosferica viva em 30fps: micro-contraste + vinheta + grao temporal sutil + legendas ASS limpas
    pos_filtros = [
        "eq=contrast=1.03:saturation=1.06",
        "vignette=PI/4.5",
        "noise=alls=4:allf=t+u",
    ]
    if arquivo_ass is not None and arquivo_ass.is_file():
        ass_esc = _escapar_caminho_filtro_ffmpeg(arquivo_ass)
        pos_filtros.append(f"ass=filename='{ass_esc}'")
    partes_fc.append(f"[{label_atual}]{','.join(pos_filtros)},format=yuv420p[vout]")

    if fc_audio_mix is not None:
        partes_fc.append(fc_audio_mix)

    filter_complex = ";".join(partes_fc)
    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", audio_map_spec])
    if audio_alvo is not None and fc_audio_mix is None:
        cmd.extend(["-af", "apad"])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps_int),
            "-c:a",
            "aac",
            "-b:a",
            "192k" if audio_alvo is not None else "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            *([] if fc_audio_mix is not None else ["-shortest"]),
            "-t",
            f"{duracao:.3f}",
            "-movflags",
            "+faststart",
            str(saida),
        ]
    )
    return cmd


def selecionar_audio() -> Path | None:
    """Prioriza audio/mix_final.mp3, com fallback para audio/narracao.mp3 e audio/voz_limpa.mp3."""
    for candidato in (AUDIO_MIX, AUDIO_MP3, AUDIO_VOZ_LIMPA):
        if candidato.is_file() and candidato.stat().st_size > 0:
            return candidato
    return None


def fatiar_partes_ffmpeg(
    saida_completa: Path,
    corte_parte_2: float,
    saidas_partes: list[Path] | None = None,
) -> tuple[Path, Path]:
    """Fatia o MP4 completo em Parte 1 (0..corte) e Parte 2 (corte..fim) com precisao de quadro."""
    if not saida_completa.is_file():
        raise RuntimeError(f"Arquivo de entrada ausente para fatiamento: {saida_completa}")

    dur_total = duracao_audio_ffprobe(saida_completa)
    if corte_parte_2 <= 0.2 or corte_parte_2 >= dur_total - 0.2:
        raise RuntimeError(
            f"corte_parte_2={corte_parte_2:.3f}s invalido para duracao total {dur_total:.3f}s."
        )

    if saidas_partes and len(saidas_partes) >= 2:
        p1, p2 = Path(saidas_partes[0]), Path(saidas_partes[1])
    else:
        p1 = saida_completa.with_name(f"{saida_completa.stem}_parte1{saida_completa.suffix}")
        p2 = saida_completa.with_name(f"{saida_completa.stem}_parte2{saida_completa.suffix}")

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    cortes = [
        (p1, ["-ss", "0.000", "-t", f"{corte_parte_2:.3f}"]),
        (p2, ["-ss", f"{corte_parte_2:.3f}"]),
    ]
    for destino, args_tempo in cortes:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(saida_completa),
            *args_tempo,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(destino),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou ao gerar {destino.name}: {res.stderr.strip()}")
    return p1, p2


def resolver_saida(explicit: str | None) -> Path:
    if explicit:
        caminho = Path(explicit)
        return caminho if caminho.is_absolute() else (RAIZ / caminho)
    return caminho_saida_atual()


def _garantir_midias_cenas(cenas_path: Path, pasta_cenas: Path, modo_teste: bool) -> None:
    """Se output/cenas/ estiver vazio, aciona gerar_midia_cenas.py automaticamente."""
    if listar_midias_disponiveis(pasta_cenas):
        return
    print(
        f"Pasta {pasta_cenas} sem midias prontas; acionando gerar_midia_cenas.py automaticamente...",
        flush=True,
    )
    from gerar_midia_cenas import gerar_midias_todas_cenas

    gerar_midias_todas_cenas(
        cenas_path=cenas_path,
        saida_dir=pasta_cenas,
        max_cenas=2 if modo_teste else None,
        forcar=False,
    )


def renderizar_video_cinematografico(
    *,
    cenas_path: Path = ARQUIVO_CENAS_PADRAO,
    pasta_cenas: Path = PASTA_CENAS_PADRAO,
    saida: Path,
    audio_alvo: Path | None = None,
    timestamps_path: Path = TIMESTAMPS_JSON,
    eventos_path: Path = EVENTOS_JSON,
    fps: int = FPS_PADRAO,
    duracao: float | None = None,
    modo_teste: bool = False,
    legendas: bool = True,
    transicao_s: float = TRANSICAO_XFADE_PADRAO_S,
    trilha_audio: Path | None = None,
    pasta_trilhas: Path = PASTA_TRILHAS,
    usar_mix_profissional: bool = True,
    dry_run_ffmpeg: bool = False,
) -> dict[str, Any]:
    """Executa a renderizacao 1080x1920 @ 30fps do Motor Cinematografico IA."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    cenas_dados = _ler_json_opcional(cenas_path)
    if not cenas_dados or not cenas_dados.get("cenas"):
        raise RuntimeError(f"Arquivo de cenas invalido ou ausente: {cenas_path}")

    eventos_dados = _ler_json_opcional(eventos_path)
    timestamps_dados = _ler_json_opcional(timestamps_path)

    if duracao is None:
        if audio_alvo is not None and audio_alvo.is_file():
            duracao = duracao_audio_ffprobe(audio_alvo) + FOLGA_AUDIO
        elif isinstance(eventos_dados, dict) and isinstance(eventos_dados.get("duracao_total"), (int, float)):
            duracao = float(eventos_dados["duracao_total"]) + FOLGA_AUDIO
        else:
            duracao = DURACAO_PREVIA

    if modo_teste:
        duracao = min(float(duracao), DURACAO_TESTE_S)
    duracao = max(0.5, float(duracao))

    _garantir_midias_cenas(cenas_path, pasta_cenas, modo_teste=modo_teste)
    timeline = construir_timeline_cenas(
        cenas_dados=cenas_dados,
        eventos_dados=eventos_dados,
        duracao_total=duracao,
        pasta_cenas=pasta_cenas,
    )

    trilha_resolvida = trilha_audio
    if usar_mix_profissional and trilha_resolvida is None and audio_alvo is not None:
        trilha_resolvida = selecionar_trilha_aleatoria(pasta_trilhas)

    saida.parent.mkdir(parents=True, exist_ok=True)
    qtd_video = sum(1 for it in timeline if it.get("tipo_midia") == "video")
    qtd_img = sum(1 for it in timeline if it.get("tipo_midia") != "video")

    with tempfile.TemporaryDirectory(prefix="render_v8_") as tmp_dir:
        arquivo_ass: Path | None = None
        if legendas and timestamps_dados is not None:
            ass_cand = Path(tmp_dir) / "legendas.ass"
            arquivo_ass = gerar_legenda_ass(
                timestamps_dados=timestamps_dados,
                cenas_dados=cenas_dados,
                destino_ass=ass_cand,
                duracao_max=duracao,
            )

        cmd = montar_comando_ffmpeg_cinematografico(
            timeline=timeline,
            saida=saida,
            fps=fps,
            audio_alvo=audio_alvo,
            duracao=duracao,
            arquivo_ass=arquivo_ass,
            transicao_s=transicao_s,
            trilha_audio=trilha_resolvida,
            usar_mix_profissional=usar_mix_profissional,
        )

        origem_trilha = (
            "desativada"
            if (not usar_mix_profissional or audio_alvo is None)
            else (f"trilha_loop:{trilha_resolvida.name}" if trilha_resolvida is not None else "sintese_dark_ffmpeg")
        )

        if dry_run_ffmpeg:
            print("DRY-RUN FFmpeg (Motor Cinematografico IA 30fps):", flush=True)
            print(" ".join(cmd), flush=True)
            return {
                "saida": str(saida),
                "duracao": round(duracao, 3),
                "fps": int(fps),
                "cenas": len(timeline),
                "qtd_video": qtd_video,
                "qtd_imagem": qtd_img,
                "legendas_ass": arquivo_ass is not None,
                "origem_trilha": origem_trilha,
                "cmd": cmd,
                "dry_run": True,
            }

        print(
            f"Renderizando Motor Cinematografico IA V8.0: {len(timeline)} cena(s) "
            f"({qtd_video} video IA, {qtd_img} imagem IA) | {LARGURA}x{ALTURA} @ {fps}fps | "
            f"duracao={duracao:.2f}s | transicao={transicao_s:.2f}s | trilha={origem_trilha} | "
            f"legendas={'ASS' if arquivo_ass else 'off'}",
            flush=True,
        )
        t0 = time.monotonic()
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"FFmpeg falhou na renderizacao cinematografica (codigo {res.returncode}): {res.stderr.strip()}"
            )
        elapsed = time.monotonic() - t0
        tam_mb = saida.stat().st_size / (1024 * 1024)
        print(
            f"Video pronto: {saida} ({tam_mb:.2f} MB) em {elapsed:.1f}s.",
            flush=True,
        )
        return {
            "saida": str(saida),
            "duracao": round(duracao, 3),
            "fps": int(fps),
            "cenas": len(timeline),
            "qtd_video": qtd_video,
            "qtd_imagem": qtd_img,
            "legendas_ass": arquivo_ass is not None,
            "origem_trilha": origem_trilha,
            "bytes": saida.stat().st_size,
            "tempo_render_s": round(elapsed, 2),
            "dry_run": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estacao 3 (Motor Cinematografico IA V8.0): renderiza 1080x1920 @ 30fps via FFmpeg."
    )
    parser.add_argument("--saida", "-o", type=str, default=None, help="Caminho do MP4 final.")
    parser.add_argument("--cenas", type=Path, default=ARQUIVO_CENAS_PADRAO, help="Caminho de cenas.json.")
    parser.add_argument(
        "--pasta-cenas",
        type=Path,
        default=PASTA_CENAS_PADRAO,
        help="Pasta com cena_01.mp4 / cena_01.jpg (padrao: output/cenas).",
    )
    parser.add_argument("--fps", type=int, default=FPS_PADRAO, help="Taxa de quadros (padrao: 30).")
    parser.add_argument("--duracao", type=float, default=None, help="Duracao manual em segundos.")
    parser.add_argument(
        "--transicao",
        type=float,
        default=TRANSICAO_XFADE_PADRAO_S,
        help="Duracao da transicao xfade entre cenas em segundos (padrao: 0.15).",
    )
    parser.add_argument(
        "--legendas",
        action="store_true",
        help="Ativa legendas ASS limpas palavra por palavra (amarelo/vermelho, UTF-8).",
    )
    parser.add_argument(
        "--sem-legendas",
        action="store_true",
        help="Desativa explicitamente as legendas ASS.",
    )
    parser.add_argument(
        "--teste",
        action="store_true",
        help="Renderiza teste rapido de 3.0 segundos (90 quadros @ 30fps).",
    )
    parser.add_argument(
        "--trilha",
        type=Path,
        default=None,
        help="Arquivo de trilha musical manual (.mp3/.wav).",
    )
    parser.add_argument(
        "--pasta-trilhas",
        type=Path,
        default=PASTA_TRILHAS,
        help="Pasta com trilhas aleatorias (padrao: assets/trilhas).",
    )
    parser.add_argument(
        "--sem-trilha",
        action="store_true",
        help="Desativa mixagem de trilha ambiente e mantem audio bruto.",
    )
    parser.add_argument(
        "--dry-run-ffmpeg",
        action="store_true",
        help="Monta e imprime o comando FFmpeg completo sem executar a codificacao.",
    )
    parser.add_argument(
        "--motor",
        type=str,
        default=MOTOR_EXCLUSIVO,
        help=f"Motor travado exclusivamente em '{MOTOR_EXCLUSIVO}' (Canvas boneco removido).",
    )
    args = parser.parse_args()

    if str(args.motor or "").strip().lower() != MOTOR_EXCLUSIVO:
        raise SystemExit(
            f"Motor '{args.motor}' nao e suportado. O motor de boneco Canvas foi removido definitivamente; "
            f"use apenas '{MOTOR_EXCLUSIVO}'."
        )

    cenas_path = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    pasta_cenas = args.pasta_cenas if args.pasta_cenas.is_absolute() else (RAIZ / args.pasta_cenas)
    pasta_trilhas = args.pasta_trilhas if args.pasta_trilhas.is_absolute() else (RAIZ / args.pasta_trilhas)
    trilha_manual = None
    if args.trilha is not None:
        trilha_manual = args.trilha if args.trilha.is_absolute() else (RAIZ / args.trilha)

    saida = resolver_saida(args.saida)
    audio_alvo = selecionar_audio()
    if audio_alvo is not None and not args.dry_run_ffmpeg:
        try:
            validar_artefatos_audio()
        except Exception as exc:
            print(f"AVISO validacao de audio: {exc}", flush=True)

    usar_legendas = not args.sem_legendas if (args.legendas or not args.sem_legendas) else False
    if not args.legendas and not args.sem_legendas:
        usar_legendas = True

    renderizar_video_cinematografico(
        cenas_path=cenas_path,
        pasta_cenas=pasta_cenas,
        saida=saida,
        audio_alvo=audio_alvo,
        timestamps_path=TIMESTAMPS_JSON,
        eventos_path=EVENTOS_JSON,
        fps=args.fps,
        duracao=args.duracao,
        modo_teste=args.teste,
        legendas=usar_legendas,
        transicao_s=args.transicao,
        trilha_audio=trilha_manual,
        pasta_trilhas=pasta_trilhas,
        usar_mix_profissional=not args.sem_trilha,
        dry_run_ffmpeg=args.dry_run_ffmpeg,
    )

    # Corte automatico Parte 1 / Parte 2 (apenas quando houver corte_parte_2 no audio e nao for --teste)
    if not args.teste and not args.dry_run_ffmpeg:
        ev = _ler_json_opcional(EVENTOS_JSON) or {}
        corte_p2 = ev.get("corte_parte_2")
        if isinstance(corte_p2, (int, float)) and corte_p2 > 1.0:
            try:
                vid = obter_video_atual()
                saidas_partes = caminhos_partes_atual() if vid else None
            except Exception:
                saidas_partes = None
            p1, p2 = fatiar_partes_ffmpeg(saida, float(corte_p2), saidas_partes=saidas_partes)
            print(
                f"Corte automatico concluido em {float(corte_p2):.2f}s: "
                f"Parte 1 = {p1.name} ({p1.stat().st_size / (1024 * 1024):.2f} MB) | "
                f"Parte 2 = {p2.name} ({p2.stat().st_size / (1024 * 1024):.2f} MB).",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
