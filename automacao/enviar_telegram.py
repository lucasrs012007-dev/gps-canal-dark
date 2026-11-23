"""Entrega automatica de Shorts renderizados e avisos de status no Telegram (stdlib apenas).

Usa TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID do ambiente (ou .env local).
- Envia mensagem de status com titulo/resumo do video.
- Envia cada MP4 via sendVideo (ate 49 MB), com fallback automatico para sendDocument.
- Se o arquivo ultrapassar 49 MB, envia aviso claro com link do Artifact no GitHub Actions.
- Suporta envio de alerta de falha (--erro) quando o workflow falhar.

Uso (na raiz do repositorio):
    python3 automacao/enviar_telegram.py --run-url "https://github.com/.../actions/runs/123"
    python3 automacao/enviar_telegram.py --arquivos output/short_07.mp4
    python3 automacao/enviar_telegram.py --erro "Falha na etapa de renderizacao" --run-url "..."
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.historico import (  # noqa: E402
    caminho_saida_atual,
    caminhos_partes_atual,
    obter_video_atual,
)

ARQUIVO_ENV = RAIZ / ".env"
LIMITE_BYTES_TELEGRAM = 49 * 1024 * 1024  # 49 MB (margem segura abaixo do teto de 50 MB da Bot API)


def carregar_env(caminho_env: Path = ARQUIVO_ENV) -> bool:
    """Carrega variaveis do .env local apenas quando ausentes no ambiente."""
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


def _mascarar_token(texto: str, token: str) -> str:
    if not token:
        return texto
    return texto.replace(token, "***TOKEN***")


def montar_multipart(
    campos: dict[str, str],
    arquivo_campo: str,
    arquivo_path: Path,
) -> tuple[bytes, str]:
    """Monta corpo multipart/form-data em memoria usando apenas stdlib."""
    boundary = f"----FabricaDarkBoundary{uuid.uuid4().hex}"
    partes: list[bytes] = []

    for chave, valor in campos.items():
        partes.append(f"--{boundary}\r\n".encode("utf-8"))
        partes.append(f'Content-Disposition: form-data; name="{chave}"\r\n\r\n'.encode("utf-8"))
        partes.append(f"{valor}\r\n".encode("utf-8"))

    mime_type, _ = mimetypes.guess_type(arquivo_path.name)
    mime_type = mime_type or "application/octet-stream"
    conteudo = arquivo_path.read_bytes()

    partes.append(f"--{boundary}\r\n".encode("utf-8"))
    partes.append(
        (
            f'Content-Disposition: form-data; name="{arquivo_campo}"; '
            f'filename="{arquivo_path.name}"\r\n'
        ).encode("utf-8")
    )
    partes.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    partes.append(conteudo)
    partes.append(b"\r\n")
    partes.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(partes), f"multipart/form-data; boundary={boundary}"


def _chamar_telegram_api(
    token: str,
    metodo: str,
    dados: bytes,
    content_type: str,
    timeout: int = 180,
    urlopen_fn: Callable | None = None,
) -> dict:
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    req = urllib.request.Request(
        url,
        data=dados,
        headers={"Content-Type": content_type},
        method="POST",
    )
    opener = urlopen_fn or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            corpo = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        det = ""
        try:
            det = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            det = ""
        raise RuntimeError(
            _mascarar_token(f"Telegram API {metodo} retornou HTTP {exc.code}: {det}", token)
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(
            _mascarar_token(f"Erro de rede no Telegram API ({metodo}): {exc.reason}", token)
        ) from None

    try:
        parsed = json.loads(corpo)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resposta nao-JSON da Telegram API ({metodo}): {exc}") from None

    if not parsed.get("ok"):
        desc = parsed.get("description", "erro desconhecido")
        raise RuntimeError(f"Telegram API ({metodo}) rejeitou a requisicao: {desc}")
    return parsed


def enviar_mensagem(
    token: str,
    chat_id: str,
    texto: str,
    urlopen_fn: Callable | None = None,
) -> dict:
    payload = json.dumps(
        {
            "chat_id": str(chat_id),
            "text": texto[:4000],
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    return _chamar_telegram_api(
        token=token,
        metodo="sendMessage",
        dados=payload,
        content_type="application/json",
        timeout=30,
        urlopen_fn=urlopen_fn,
    )


def enviar_arquivo_video(
    token: str,
    chat_id: str,
    caminho: Path,
    legenda: str,
    run_url: str | None = None,
    limite_bytes: int = LIMITE_BYTES_TELEGRAM,
    urlopen_fn: Callable | None = None,
) -> dict:
    """Envia MP4 via sendVideo, faz fallback para sendDocument, ou envia link do Artifact se > limite."""
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de video nao encontrado: {caminho}")

    tamanho = caminho.stat().st_size
    tamanho_mb = tamanho / (1024 * 1024)

    if tamanho > limite_bytes:
        link_txt = f"\nLink do Artifact no GitHub Actions: {run_url}" if run_url else ""
        aviso = (
            f"Video pronto, mas acima do limite de 49 MB do Telegram ({caminho.name}: {tamanho_mb:.1f} MB)."
            f"{link_txt}\nBaixe o MP4 diretamente nos Artifacts da execucao."
        )
        enviar_mensagem(token, chat_id, aviso, urlopen_fn=urlopen_fn)
        return {"modo": "aviso_tamanho", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}

    campos_video = {
        "chat_id": str(chat_id),
        "caption": legenda[:1000],
        "supports_streaming": "true",
        "width": "1080",
        "height": "1920",
    }
    try:
        corpo, ctype = montar_multipart(campos_video, "video", caminho)
        _chamar_telegram_api(token, "sendVideo", corpo, ctype, timeout=240, urlopen_fn=urlopen_fn)
        return {"modo": "sendVideo", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}
    except RuntimeError as exc_video:
        print(
            f"AVISO sendVideo falhou para {caminho.name} ({exc_video}). Tentando fallback via sendDocument...",
            flush=True,
        )
        campos_doc = {
            "chat_id": str(chat_id),
            "caption": legenda[:1000],
        }
        corpo_doc, ctype_doc = montar_multipart(campos_doc, "document", caminho)
        _chamar_telegram_api(token, "sendDocument", corpo_doc, ctype_doc, timeout=240, urlopen_fn=urlopen_fn)
        return {"modo": "sendDocument", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}


def descobrir_arquivos_video_atual() -> tuple[dict, list[Path]]:
    """Resolve automaticamente o MP4 completo e as partes 1/2 (quando existirem) do video ativo."""
    video_ativo = obter_video_atual(validar=False)
    candidatos: list[Path] = []
    saida_principal = caminho_saida_atual()
    if saida_principal.is_file():
        candidatos.append(saida_principal)

    if isinstance(video_ativo.get("saidas_partes"), list) and len(video_ativo["saidas_partes"]) >= 2:
        for p in caminhos_partes_atual():
            if p.is_file() and p not in candidatos:
                candidatos.append(p)
    else:
        for sufixo in ("_parte1", "_parte2"):
            p_cand = saida_principal.with_name(f"{saida_principal.stem}{sufixo}{saida_principal.suffix}")
            if p_cand.is_file() and p_cand not in candidatos:
                candidatos.append(p_cand)

    return video_ativo, candidatos


def main() -> None:
    parser = argparse.ArgumentParser(description="Envia videos renderizados e status da Fabrica V6 no Telegram.")
    parser.add_argument("--arquivos", nargs="*", type=Path, default=None, help="Lista manual de arquivos MP4 para enviar.")
    parser.add_argument("--titulo", type=str, default=None, help="Titulo do video para legenda e status.")
    parser.add_argument("--run-url", type=str, default=None, help="URL da execucao no GitHub Actions.")
    parser.add_argument("--erro", type=str, default=None, help="Mensagem de erro para notificar falha na nuvem.")
    parser.add_argument("--dry-run", action="store_true", help="Simula o envio sem chamar a API do Telegram.")
    args = parser.parse_args()

    carregar_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not args.dry_run and (not token or not chat_id):
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID precisam estar configurados nas variaveis de ambiente ou .env."
        )

    if args.erro:
        link = f"\nLogs da execucao: {args.run_url}" if args.run_url else ""
        msg_erro = f"Falha na Fabrica Dark V6 (GitHub Actions).\nMotivo: {args.erro}{link}"
        if args.dry_run:
            print(f"[DRY-RUN] Enviaria mensagem de erro:\n{msg_erro}")
            return
        enviar_mensagem(token, chat_id, msg_erro)
        print("Notificacao de falha enviada no Telegram.")
        return

    video_info: dict = {}
    if args.arquivos:
        arquivos = [p if p.is_absolute() else (RAIZ / p) for p in args.arquivos]
    else:
        video_info, arquivos = descobrir_arquivos_video_atual()

    arquivos_existentes = [p for p in arquivos if p.is_file()]
    if not arquivos_existentes:
        raise SystemExit("Nenhum arquivo MP4 encontrado para envio no Telegram.")

    titulo = args.titulo or str(video_info.get("titulo", "Short V6"))
    vid_num = video_info.get("id")
    prefixo = f"Video {int(vid_num):02d} ({titulo})" if vid_num is not None else titulo
    link_run = f"\nGitHub Actions: {args.run_url}" if args.run_url else ""

    status_msg = (
        f"Fabrica Dark V6 concluida: {prefixo}.\n"
        f"Arquivos prontos ({len(arquivos_existentes)}): "
        f"{', '.join(p.name for p in arquivos_existentes)}.{link_run}"
    )

    if args.dry_run:
        print(f"[DRY-RUN] Status:\n{status_msg}")
        for arq in arquivos_existentes:
            print(f"[DRY-RUN] Enviaria {arq} ({arq.stat().st_size / (1024 * 1024):.2f} MB)")
        return

    enviar_mensagem(token, chat_id, status_msg)
    for arq in arquivos_existentes:
        etiqueta = "Completo"
        if "_parte1" in arq.stem:
            etiqueta = "Parte 1"
        elif "_parte2" in arq.stem:
            etiqueta = "Parte 2"
        legenda = f"{prefixo} | {etiqueta} ({arq.name})"
        res = enviar_arquivo_video(token, chat_id, arq, legenda=legenda, run_url=args.run_url)
        print(f"Telegram OK [{res['modo']}]: {res['arquivo']} ({res['tamanho_mb']} MB)", flush=True)


if __name__ == "__main__":
    main()
