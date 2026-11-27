#!/usr/bin/env python3
"""Entrega direta de episodios da fabrica_v2 no Telegram via Bot API (stdlib apenas).

Regras de envio:
  - Le TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estritamente de variaveis de ambiente
    (com aliases de seguranca TG_BOT_TOKEN e TG_CHAT_ID).
  - Limite da Telegram Bot API e 50 MB: se <ep>/video_final.mp4 tiver <= 48 MB,
    envia video_final.mp4 em qualidade integral.
  - Se video_final.mp4 exceder 48 MB, usa <ep>/video_leve.mp4 (gerando via ffmpeg
    se ausente ou >= 18 MB para garantir entrega rapida abaixo de 18 MB).
  - Envia via sendVideo (supports_streaming=true, 1080x1920) e falha ruidosamente
    se a API retornar erro, sempre mascarando o token do bot.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

LIMITE_VIDEO_FINAL_BYTES = 48_000_000  # 48 MB decimal (margem segura abaixo do teto de 50 MB)
LIMITE_VIDEO_LEVE_BYTES = 18_000_000   # 18 MB decimal
LIMITE_API_TELEGRAM_BYTES = 50_000_000
LIMITE_CAPTION_CHARS = 1024


def _mascarar_token(texto: str, token: str) -> str:
    if not token:
        return texto
    return texto.replace(token, "***TOKEN***")


def obter_credenciais_env() -> tuple[str, str]:
    token = (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        or os.environ.get("TG_BOT_TOKEN", "").strip()
    )
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        or os.environ.get("TG_CHAT_ID", "").strip()
    )
    faltando: list[str] = []
    if not token:
        faltando.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        faltando.append("TELEGRAM_CHAT_ID")
    if faltando:
        raise SystemExit(
            f"ERRO Telegram: variaveis de ambiente ausentes: {', '.join(faltando)}. "
            "Configure os Secrets em GitHub Settings -> Secrets and variables -> Actions."
        )
    return token, chat_id


def sondar_video(caminho: Path) -> dict:
    """Extrai duracao, largura e altura do MP4 via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=codec_type,width,height",
        "-of",
        "json",
        str(caminho),
    ]
    bruto = subprocess.check_output(cmd, text=True)
    dados = json.loads(bruto)
    fmt = dados.get("format") or {}
    streams = dados.get("streams") or []
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration": float(fmt.get("duration") or 0.0),
        "size": int(fmt.get("size") or caminho.stat().st_size),
        "width": int(v_stream.get("width") or 1080),
        "height": int(v_stream.get("height") or 1920),
    }


def gerar_video_leve(video_final: Path, video_leve: Path) -> Path:
    """Gera copia mobile < 18 MB preservando 1080x1920, 30fps e AAC 128k."""
    meta = sondar_video(video_final)
    dur = max(1.0, meta["duration"])
    # Alvo ~16.2 MiB para margem folgada abaixo de 18 MB
    total_kbps = int((16.2 * 8192.0) / dur)
    v_kbps = max(600, min(1600, total_kbps - 136))
    maxrate = int(v_kbps * 1.12)
    bufsize = v_kbps * 2
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(video_final),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-b:v",
        f"{v_kbps}k",
        "-maxrate",
        f"{maxrate}k",
        "-bufsize",
        f"{bufsize}k",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(video_leve),
    ]
    print(
        f"Gerando {video_leve.name} ({v_kbps}k video + 128k audio) para fallback < 18 MB...",
        flush=True,
    )
    subprocess.run(cmd, check=True)
    if video_leve.stat().st_size >= LIMITE_VIDEO_LEVE_BYTES:
        raise SystemExit(
            f"ERRO: {video_leve.name} ficou com {video_leve.stat().st_size} bytes (>= 18 MB)."
        )
    return video_leve


def selecionar_video(ep_dir: Path, video_override: str) -> tuple[Path, str]:
    if video_override:
        alvo = Path(video_override).resolve()
        if not alvo.is_file():
            raise SystemExit(f"ERRO: arquivo --video nao encontrado: {alvo}")
        if alvo.stat().st_size > LIMITE_API_TELEGRAM_BYTES:
            raise SystemExit(
                f"ERRO: arquivo --video excede o limite de 50 MB do Telegram ({alvo.stat().st_size} bytes)."
            )
        return alvo, "override"

    video_final = ep_dir / "video_final.mp4"
    video_leve = ep_dir / "video_leve.mp4"
    if not video_final.is_file():
        raise SystemExit(f"ERRO: {video_final} nao encontrado. Rode render.py antes.")

    tam_final = video_final.stat().st_size
    if tam_final <= LIMITE_VIDEO_FINAL_BYTES:
        return video_final, "qualidade_total"

    print(
        f"video_final.mp4 tem {tam_final / (1024 * 1024):.2f} MB (> 48 MB). "
        "Usando fallback video_leve.mp4...",
        flush=True,
    )
    if not video_leve.is_file() or video_leve.stat().st_size >= LIMITE_VIDEO_LEVE_BYTES:
        gerar_video_leve(video_final, video_leve)
    return video_leve, "fallback_leve"


def montar_legenda(
    ep_dir: Path,
    arquivo: Path,
    meta: dict,
    modo: str,
    run_url: str,
    artifact_url: str,
) -> str:
    titulo = ""
    roteiro = ep_dir / "roteiro.json"
    if roteiro.is_file():
        try:
            titulo = str(json.loads(roteiro.read_text(encoding="utf-8")).get("titulo") or "").strip()
        except Exception:
            titulo = ""

    tam_mb = meta["size"] / (1024 * 1024)
    linhas = [f"Fabrica V2 | Episodio: {ep_dir.name}"]
    if titulo:
        linhas.append(f"Titulo: {titulo}")
    linhas.append(f"Duracao: {meta['duration']:.1f}s | Resolucao: {meta['width']}x{meta['height']}")
    linhas.append(f"Arquivo: {arquivo.name} ({tam_mb:.2f} MB | {modo})")
    if artifact_url:
        linhas.append(f"Artifact: {artifact_url}")
    elif run_url:
        linhas.append(f"Execucao: {run_url}")

    texto = "\n".join(linhas).strip()
    if len(texto) <= LIMITE_CAPTION_CHARS:
        return texto
    return texto[: LIMITE_CAPTION_CHARS - 3].rstrip() + "..."


def montar_multipart(campos: dict[str, str], campo_arquivo: str, caminho: Path) -> tuple[bytes, str]:
    boundary = f"----FabricaV2Telegram{uuid.uuid4().hex}"
    partes: list[bytes] = []
    for chave, valor in campos.items():
        partes.append(f"--{boundary}\r\n".encode("utf-8"))
        partes.append(f'Content-Disposition: form-data; name="{chave}"\r\n\r\n'.encode("utf-8"))
        partes.append(f"{valor}\r\n".encode("utf-8"))

    mime_type, _ = mimetypes.guess_type(caminho.name)
    mime_type = mime_type or "video/mp4"
    partes.append(f"--{boundary}\r\n".encode("utf-8"))
    partes.append(
        f'Content-Disposition: form-data; name="{campo_arquivo}"; filename="{caminho.name}"\r\n'.encode("utf-8")
    )
    partes.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    partes.append(caminho.read_bytes())
    partes.append(b"\r\n")
    partes.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={boundary}"


def enviar_video_telegram(
    token: str,
    chat_id: str,
    arquivo: Path,
    legenda: str,
    meta: dict,
    timeout: int = 180,
) -> dict:
    campos = {
        "chat_id": str(chat_id),
        "caption": legenda[:LIMITE_CAPTION_CHARS],
        "supports_streaming": "true",
        "width": str(meta["width"]),
        "height": str(meta["height"]),
        "duration": str(max(1, int(round(meta["duration"])))),
    }
    corpo, content_type = montar_multipart(campos, "video", arquivo)
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    req = urllib.request.Request(
        url,
        data=corpo,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            bruto = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detalhe = ""
        try:
            detalhe = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detalhe = ""
        raise SystemExit(
            _mascarar_token(f"ERRO Telegram sendVideo HTTP {exc.code}: {detalhe}", token)
        ) from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            _mascarar_token(f"ERRO de rede ao enviar para Telegram: {exc.reason}", token)
        ) from None
    except TimeoutError:
        raise SystemExit(f"ERRO: timeout ({timeout}s) no envio para Telegram sendVideo.") from None

    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        raise SystemExit(
            _mascarar_token(f"ERRO: resposta nao-JSON da API Telegram (HTTP {status}): {bruto[:300]}", token)
        ) from None

    if not dados.get("ok"):
        raise SystemExit(
            _mascarar_token(f"ERRO Telegram sendVideo rejeitado (HTTP {status}): {bruto[:500]}", token)
        )
    return dados


def main() -> int:
    ap = argparse.ArgumentParser(description="Envia video renderizado da fabrica_v2 para o Telegram.")
    ap.add_argument("--ep", required=True, help="diretorio do episodio (ex: fabrica_v2/episodios/ep02_encolher)")
    ap.add_argument("--video", default="", help="caminho opcional de MP4 especifico")
    ap.add_argument("--run-url", default="", help="URL opcional da execucao no GitHub Actions")
    ap.add_argument("--artifact-url", default="", help="URL opcional do Artifact no GitHub Actions")
    args = ap.parse_args()

    ep_dir = Path(args.ep).resolve()
    if not ep_dir.is_dir():
        raise SystemExit(f"ERRO: diretorio do episodio nao encontrado: {ep_dir}")

    token, chat_id = obter_credenciais_env()
    arquivo, modo = selecionar_video(ep_dir, args.video)
    meta = sondar_video(arquivo)
    legenda = montar_legenda(ep_dir, arquivo, meta, modo, args.run_url.strip(), args.artifact_url.strip())

    print(
        f"Enviando {arquivo.name} ({meta['size'] / (1024 * 1024):.2f} MB | {meta['duration']:.1f}s | {modo}) "
        "via Telegram sendVideo...",
        flush=True,
    )
    resp = enviar_video_telegram(token, chat_id, arquivo, legenda, meta)
    msg_id = (resp.get("result") or {}).get("message_id")
    print(f"OK Telegram: sendVideo concluido (message_id={msg_id}, arquivo={arquivo.name}).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
