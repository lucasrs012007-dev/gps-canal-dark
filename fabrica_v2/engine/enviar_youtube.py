#!/usr/bin/env python3
"""Upload automatico de episodios da fabrica_v2 para o YouTube Shorts (Data API v3).

Regras de seguranca e operacao:
  - Le credenciais OAuth 2.0 estritamente de variaveis de ambiente:
      YOUTUBE_CLIENT_ID
      YOUTUBE_CLIENT_SECRET
      YOUTUBE_REFRESH_TOKEN
    Falha ruidosamente (codigo != 0) se qualquer uma estiver ausente, sem nunca
    imprimir segredos ou tokens.
  - Le metadados opcionais do bloco "youtube" em <ep>/roteiro.json
    (titulo, descricao, tags, categoria_id) com fallback automatico para Shorts
    quando ausente (compatibilidade com ep01/ep02).
  - Executa upload resumable de <ep>/video_final.mp4 (ou --video), imprime a URL
    https://youtube.com/shorts/<video_id>, grava <ep>/youtube_url.txt e registra
    youtube_url em GITHUB_OUTPUT quando disponivel.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

YOUTUBE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
CATEGORIA_PADRAO = "24"  # Entertainment
PRIVACIDADES_VALIDAS = ("public", "unlisted", "private")

LIMITE_TITULO_YT = 100
LIMITE_DESCRICAO_YT = 4500
LIMITE_CHARS_TAGS_YT = 450
CHUNK_SIZE_BYTES = 4 * 1024 * 1024
MAX_RETRIES_UPLOAD = 3
STATUS_RETENTAVEIS = (500, 502, 503, 504)

RE_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)


def _mascarar_segredos(texto: str, segredos: tuple[str, ...]) -> str:
    limpo = str(texto or "")
    for seg in segredos:
        if seg:
            limpo = limpo.replace(seg, "***SECRET***")
    return limpo


def _limpar_texto(texto: str) -> str:
    limpo = unicodedata.normalize("NFC", str(texto or ""))
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = limpo.replace("<", "").replace(">", "")
    limpo = re.sub(r"[ \t]+", " ", limpo)
    return limpo.strip()


def normalizar_privacidade(valor: str | None) -> str:
    raw = str(valor or os.environ.get("YOUTUBE_PRIVACY", "") or "public").strip().lower()
    if raw in PRIVACIDADES_VALIDAS:
        return raw
    raise SystemExit(
        f"ERRO: privacidade invalida '{raw}'. Use uma das opcoes: {', '.join(PRIVACIDADES_VALIDAS)}."
    )


def obter_credenciais_env() -> tuple[str, str, str]:
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    rtok = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    faltando: list[str] = []
    if not cid:
        faltando.append("YOUTUBE_CLIENT_ID")
    if not csec:
        faltando.append("YOUTUBE_CLIENT_SECRET")
    if not rtok:
        faltando.append("YOUTUBE_REFRESH_TOKEN")
    if faltando:
        raise SystemExit(
            f"ERRO YouTube: variaveis de ambiente ausentes: {', '.join(faltando)}. "
            "Configure os Secrets em GitHub Settings -> Secrets and variables -> Actions."
        )
    return cid, csec, rtok


def montar_titulo_shorts(titulo_base: str) -> str:
    base = _limpar_texto(titulo_base) or "E Se Voce?"
    sufixo = " #Shorts"
    if "#shorts" in base.lower():
        if len(base) <= LIMITE_TITULO_YT:
            return base
        base = re.sub(r"(?i)\s*#shorts\b", "", base).strip()
    max_base = LIMITE_TITULO_YT - len(sufixo)
    if len(base) > max_base:
        fatia = base[: max_base - 3]
        cortado = fatia.rsplit(" ", 1)[0].strip(" ,;:-") if " " in fatia else ""
        base = (cortado if len(cortado) >= 20 else fatia.strip(" ,;:-")) + "..."
    return f"{base}{sufixo}"


def montar_tags(tags_brutas: list[str]) -> list[str]:
    tags: list[str] = []
    vistas: set[str] = set()
    total_chars = 0
    for raw in tags_brutas:
        limpa = _limpar_texto(str(raw)).lstrip("#").strip(" ,;.")
        if len(limpa) < 2 or len(limpa) > 40:
            continue
        chave = limpa.lower()
        if chave in vistas:
            continue
        custo = len(limpa) + (2 if " " in limpa else 0) + 1
        if total_chars + custo > LIMITE_CHARS_TAGS_YT:
            break
        vistas.add(chave)
        tags.append(limpa)
        total_chars += custo
    return tags


def montar_body_youtube(ep_dir: Path, privacidade: str) -> dict:
    roteiro_path = ep_dir / "roteiro.json"
    cfg: dict = {}
    if roteiro_path.is_file():
        cfg = json.loads(roteiro_path.read_text(encoding="utf-8"))

    yt = cfg.get("youtube") if isinstance(cfg.get("youtube"), dict) else {}
    titulo_cfg = str(cfg.get("titulo") or ep_dir.name).strip()
    titulo = montar_titulo_shorts(str(yt.get("titulo") or titulo_cfg))

    segs = cfg.get("segmentos") if isinstance(cfg.get("segmentos"), list) else []
    gancho = ""
    if segs and isinstance(segs[0], dict):
        gancho = _limpar_texto(str(segs[0].get("fala") or ""))
    cta_loop = ""
    if segs and isinstance(segs[-1], dict):
        cta_loop = _limpar_texto(str(segs[-1].get("fala") or ""))

    desc_raw = str(yt.get("descricao") or "").strip()
    if desc_raw:
        linhas_desc = [_limpar_texto(ln) for ln in desc_raw.splitlines()]
        descricao = "\n".join(linhas_desc).strip()
        if "#shorts" not in descricao.lower():
            descricao = f"{descricao}\n\n#Shorts #curiosidades #ese".strip()
    else:
        partes = [p for p in (gancho or titulo_cfg, cta_loop, "#Shorts #curiosidades #ese") if p]
        descricao = "\n\n".join(partes)
    descricao = descricao[:LIMITE_DESCRICAO_YT]

    tags_raw = list(yt.get("tags") or []) if isinstance(yt.get("tags"), list) else []
    if not tags_raw:
        tags_raw = ["shorts", "curiosidades", "e se voce", "ciencia", "youtube shorts"]
    elif "shorts" not in [str(t).lower() for t in tags_raw]:
        tags_raw.append("shorts")
    tags = montar_tags(tags_raw)

    cat_id = str(yt.get("categoria_id") or CATEGORIA_PADRAO).strip() or CATEGORIA_PADRAO

    return {
        "snippet": {
            "title": titulo,
            "description": descricao,
            "tags": tags,
            "categoryId": cat_id,
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": normalizar_privacidade(privacidade),
            "selfDeclaredMadeForKids": False,
        },
    }


def criar_cliente_youtube(client_id: str, client_secret: str, refresh_token: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=YOUTUBE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def enviar_para_youtube(
    video_path: Path,
    body: dict,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    segredos = (client_id, client_secret, refresh_token)
    try:
        youtube = criar_cliente_youtube(client_id, client_secret, refresh_token)
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=CHUNK_SIZE_BYTES,
            resumable=True,
        )
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        tentativa = 0
        while response is None:
            try:
                status, response = request.next_chunk()
                if status is not None:
                    print(f"Upload YouTube em andamento: {int(status.progress() * 100)}%", flush=True)
            except HttpError as exc:
                cod = getattr(exc.resp, "status", None)
                if cod in STATUS_RETENTAVEIS and tentativa < MAX_RETRIES_UPLOAD:
                    tentativa += 1
                    espera = 2 ** tentativa
                    print(
                        f"AVISO HTTP {cod} no upload YouTube. Tentativa {tentativa}/{MAX_RETRIES_UPLOAD} "
                        f"em {espera}s...",
                        flush=True,
                    )
                    time.sleep(espera)
                    continue
                raise
            except (OSError, TimeoutError) as exc:
                if tentativa < MAX_RETRIES_UPLOAD:
                    tentativa += 1
                    espera = 2 ** tentativa
                    print(
                        f"AVISO rede ({type(exc).__name__}) no upload YouTube. "
                        f"Tentativa {tentativa}/{MAX_RETRIES_UPLOAD} em {espera}s...",
                        flush=True,
                    )
                    time.sleep(espera)
                    continue
                raise

        video_id = str((response or {}).get("id", "")).strip()
        if not video_id:
            raise RuntimeError(f"YouTube API retornou resposta sem 'id': {response!r}")
        return video_id
    except Exception as exc:
        msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
        raise SystemExit(f"ERRO no upload para o YouTube Shorts: {msg}") from None


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica episodio da fabrica_v2 no YouTube Shorts.")
    ap.add_argument("--ep", required=True, help="diretorio do episodio (ex: fabrica_v2/episodios/ep03_forca)")
    ap.add_argument("--video", default="", help="caminho opcional de MP4 (padrao: <ep>/video_final.mp4)")
    ap.add_argument(
        "--privacidade",
        default="",
        help="public, unlisted ou private (padrao: YOUTUBE_PRIVACY ou public)",
    )
    args = ap.parse_args()

    ep_dir = Path(args.ep).resolve()
    if not ep_dir.is_dir():
        raise SystemExit(f"ERRO: diretorio do episodio nao encontrado: {ep_dir}")

    video_path = Path(args.video).resolve() if args.video else (ep_dir / "video_final.mp4")
    if not video_path.is_file():
        raise SystemExit(f"ERRO: arquivo de video nao encontrado: {video_path}")

    privacidade = normalizar_privacidade(args.privacidade)
    client_id, client_secret, refresh_token = obter_credenciais_env()
    body = montar_body_youtube(ep_dir, privacidade)

    print(
        f"Iniciando upload YouTube Shorts: {video_path.name} ({video_path.stat().st_size / (1024 * 1024):.2f} MB) | "
        f"privacidade={body['status']['privacyStatus']} | titulo={body['snippet']['title']!r}",
        flush=True,
    )
    video_id = enviar_para_youtube(video_path, body, client_id, client_secret, refresh_token)
    url = f"https://youtube.com/shorts/{video_id}"
    (ep_dir / "youtube_url.txt").write_text(url + "\n", encoding="utf-8")

    gh_out = os.environ.get("GITHUB_OUTPUT", "").strip()
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"youtube_url={url}\n")

    print(f"OK YouTube Shorts publicado: {url}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
