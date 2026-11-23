"""Entrega automatica de Shorts renderizados e avisos de status no Telegram (stdlib apenas).

Usa TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID do ambiente (ou .env local).
Estrategia padrao V5.2/V6 (`--estrategia partes`):
- Quando existirem `short_NN_parte1.mp4` (~21 MB) e `short_NN_parte2.mp4` (~20 MB), envia
  primeiro a Parte 1 (com legenda de gancho + link direto dos GitHub Artifacts) e logo em
  seguida a Parte 2 (com legenda de continuacao/desfecho), sem tentar subir o arquivo
  pesado inteiro (`short_NN.mp4` de 40+ MB, que permanece disponivel nos GitHub Artifacts).
- Em modo `--teste` (quando existe apenas `short_NN.mp4` curto de ~1 MB) ou em videos de
  parte unica abaixo de 45 MB, envia o MP4 disponivel com o mesmo formato.
- Cada arquivo respeita o teto seguro de 45 MB, com fallback automatico `sendVideo` ->
  `sendDocument` -> `sendMessage` (com link dos Artifacts e legenda pronta para postagem).

Uso (na raiz do repositorio):
    python3 automacao/enviar_telegram.py --run-url "https://github.com/.../actions/runs/123" \
        --artifact-url "https://github.com/.../actions/runs/123/artifacts/456"
    python3 automacao/enviar_telegram.py --dry-run --run-url "https://github.com/.../actions/runs/123"
    python3 automacao/enviar_telegram.py --erro "Falha na etapa de renderizacao" --run-url "..."
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import unicodedata
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
LIMITE_MB_PADRAO = 45.0
LIMITE_BYTES_TELEGRAM = int(LIMITE_MB_PADRAO * 1024 * 1024)  # Margem segura abaixo do teto de 50 MB
LIMITE_CAPTION_TELEGRAM = 1000  # Teto oficial da Bot API e 1024 caracteres
PAUSA_ENTRE_PARTES_S = 1.5

PADRAO_LINHA_ROTEIRO = re.compile(r"^\[\d+\s*-\s*\d+\]\s*\|")
PADRAO_TAGS_VOZ = re.compile(r"\[/?VOZ(?::[a-zA-Z0-9_]+)?\]", re.IGNORECASE)
PADRAO_TAGS_CTRL = re.compile(r"\[/?(?:CTA_PAUSA|CORTE_PARTE_2|SFX:[^\]]+)\]", re.IGNORECASE)


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


def _slug_hashtag(texto: str) -> str:
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(ch) != "Mn"
    )
    limpo = re.sub(r"[^a-zA-Z0-9]+", "", sem_acento).lower()
    return limpo


def extrair_gancho_roteiro(video_info: dict, raiz: Path = RAIZ) -> str:
    """Le a primeira frase falada do roteiro ativo para compor um gancho sem spoilers."""
    roteiro_rel = str(video_info.get("roteiro", "") or "").strip()
    if roteiro_rel:
        arq = Path(roteiro_rel)
        if not arq.is_absolute():
            arq = raiz / arq
        if arq.is_file():
            for linha in arq.read_text(encoding="utf-8", errors="ignore").splitlines():
                bruta = linha.strip()
                if not PADRAO_LINHA_ROTEIRO.match(bruta):
                    continue
                colunas = [c.strip() for c in bruta.split("|")]
                if len(colunas) < 2:
                    continue
                fala = PADRAO_TAGS_VOZ.sub("", colunas[1])
                fala = PADRAO_TAGS_CTRL.sub("", fala)
                fala = re.sub(r"\s+", " ", fala).strip()
                if fala:
                    return fala[:180].rstrip()
    tema = str(video_info.get("tema", "") or "").strip()
    if tema:
        return tema[:160].rstrip(".") + "."
    return "Uma historia de suspense que muda completamente nos segundos finais."


def montar_hashtags(video_info: dict, parte: str = "parte1", maximo: int = 6) -> str:
    """Gera hashtags limpas e relevantes a partir das palavras-chave do video ativo."""
    base = (
        ["shorts", "suspense", "terrorpsicologico", "parte2"]
        if parte == "parte2"
        else ["shorts", "suspense", "terrorpsicologico", "historiasdesuspense"]
    )
    extras: list[str] = []
    palavras = video_info.get("palavras_chave") or []
    if isinstance(palavras, list):
        for p in palavras:
            tag = _slug_hashtag(str(p))
            if len(tag) >= 3 and tag not in base and tag not in extras:
                extras.append(tag)
            if len(base) + len(extras) >= maximo:
                break
    todas = (base + extras)[:maximo]
    return " ".join(f"#{t}" for t in todas)


def montar_legenda_postagem(
    video_info: dict,
    parte: str | None = None,
    eh_parte1: bool = True,
    raiz: Path = RAIZ,
) -> str:
    """Monta legenda pronta para copiar e colar no Reels / YouTube Shorts / TikTok."""
    titulo = str(video_info.get("titulo", "Short Dark")).strip()
    modo = parte if parte in ("parte1", "parte2", "unico") else ("parte1" if eh_parte1 else "unico")

    if modo == "parte2":
        cta = (
            "Você esperava esse final? Comente o que faria no lugar dele. "
            "Quer aprender a criar vídeos assim no automático? Comente EU QUERO que eu te envio no Direct."
        )
        hashtags = montar_hashtags(video_info, parte="parte2")
        return (
            f"{titulo} (PARTE 2 - FINAL)\n"
            f"Continuação da Parte 1: assista ao desfecho completo de {titulo}.\n\n"
            f"{cta}\n\n"
            f"{hashtags}"
        )

    sufixo_parte = " (PARTE 1)" if modo == "parte1" else ""
    gancho = extrair_gancho_roteiro(video_info, raiz=raiz)
    cta = (
        "Quer aprender a criar vídeos assim no automático? "
        "Comente EU QUERO que eu te envio o passo a passo no Direct."
    )
    hashtags = montar_hashtags(video_info, parte="parte1")
    return f"{titulo}{sufixo_parte}\n{gancho}\n\n{cta}\n\n{hashtags}"


def montar_caption_telegram(
    video_info: dict,
    arquivo: Path,
    outros_arquivos: list[Path],
    artifact_url: str | None = None,
    run_url: str | None = None,
    raiz: Path = RAIZ,
) -> str:
    """Monta a legenda completa enviada junto ao video no Telegram (<= 1000 chars)."""
    titulo = str(video_info.get("titulo", "Short V6")).strip()
    vid_num = video_info.get("id")
    prefixo = f"Video {int(vid_num):02d}: {titulo}" if vid_num is not None else titulo

    stem_low = arquivo.stem.lower()
    if "_parte1" in stem_low:
        modo = "parte1"
        etiqueta = "Parte 1"
        cabecalho_legenda = "LEGENDA PRONTA PARA POSTAGEM (PARTE 1):"
    elif "_parte2" in stem_low:
        modo = "parte2"
        etiqueta = "Parte 2 (Final)"
        cabecalho_legenda = "LEGENDA PRONTA PARA POSTAGEM (PARTE 2):"
    else:
        modo = "unico"
        etiqueta = "Preview/Completo"
        cabecalho_legenda = "LEGENDA PRONTA PARA POSTAGEM:"

    tamanho_mb = (arquivo.stat().st_size / (1024 * 1024)) if arquivo.is_file() else 0.0
    link_artifacts = (artifact_url or "").strip()
    if not link_artifacts and run_url:
        link_artifacts = f"{run_url.rstrip('/')}#artifacts"

    linhas: list[str] = [
        f"{prefixo} | {etiqueta}",
        f"Arquivo enviado: {arquivo.name} ({tamanho_mb:.1f} MB)",
    ]
    if outros_arquivos and modo != "parte2":
        nomes_outros = ", ".join(p.name for p in outros_arquivos)
        linhas.append(f"Arquivo completo nos Artifacts: {nomes_outros}")
    if link_artifacts:
        linhas.append(f"GitHub Artifacts: {link_artifacts}")

    legenda_post = montar_legenda_postagem(video_info, parte=modo, raiz=raiz)
    linhas.append("")
    linhas.append(cabecalho_legenda)
    linhas.append(legenda_post)

    texto = "\n".join(linhas).strip()
    if len(texto) <= LIMITE_CAPTION_TELEGRAM:
        return texto
    return texto[: LIMITE_CAPTION_TELEGRAM - 3].rstrip() + "..."


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
    timeout: int = 120,
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
    except TimeoutError:
        raise RuntimeError(f"Timeout no Telegram API ({metodo}) apos {timeout}s.") from None

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
    artifact_url: str | None = None,
    limite_bytes: int = LIMITE_BYTES_TELEGRAM,
    urlopen_fn: Callable | None = None,
) -> dict:
    """Envia MP4 via sendVideo (ate limite_bytes), com fallback para sendDocument e sendMessage."""
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de video nao encontrado: {caminho}")

    tamanho = caminho.stat().st_size
    tamanho_mb = tamanho / (1024 * 1024)
    limite_mb = limite_bytes / (1024 * 1024)
    link_ref = (artifact_url or "").strip() or (f"{run_url.rstrip('/')}#artifacts" if run_url else "")

    if tamanho > limite_bytes:
        link_txt = f"\nLink do GitHub Artifact: {link_ref}" if link_ref else ""
        aviso = (
            f"Video pronto, mas acima do limite seguro de {limite_mb:.0f} MB para upload no bot "
            f"({caminho.name}: {tamanho_mb:.1f} MB).{link_txt}\n\n{legenda}"
        )
        enviar_mensagem(token, chat_id, aviso, urlopen_fn=urlopen_fn)
        return {"modo": "aviso_tamanho", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}

    campos_video = {
        "chat_id": str(chat_id),
        "caption": legenda[:LIMITE_CAPTION_TELEGRAM],
        "supports_streaming": "true",
        "width": "1080",
        "height": "1920",
    }
    try:
        corpo, ctype = montar_multipart(campos_video, "video", caminho)
        _chamar_telegram_api(token, "sendVideo", corpo, ctype, timeout=120, urlopen_fn=urlopen_fn)
        return {"modo": "sendVideo", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}
    except RuntimeError as exc_video:
        print(
            f"AVISO sendVideo falhou para {caminho.name} ({exc_video}). Tentando fallback via sendDocument...",
            flush=True,
        )
        try:
            campos_doc = {
                "chat_id": str(chat_id),
                "caption": legenda[:LIMITE_CAPTION_TELEGRAM],
            }
            corpo_doc, ctype_doc = montar_multipart(campos_doc, "document", caminho)
            _chamar_telegram_api(token, "sendDocument", corpo_doc, ctype_doc, timeout=120, urlopen_fn=urlopen_fn)
            return {"modo": "sendDocument", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}
        except RuntimeError as exc_doc:
            print(
                f"AVISO sendDocument tambem falhou ({exc_doc}). Enviando link dos Artifacts + legenda por texto.",
                flush=True,
            )
            link_txt = f"\nBaixe nos GitHub Artifacts: {link_ref}" if link_ref else ""
            msg_fallback = (
                f"Upload direto do MP4 ({caminho.name}, {tamanho_mb:.1f} MB) nao concluido pela API do Telegram."
                f"{link_txt}\n\n{legenda}"
            )
            enviar_mensagem(token, chat_id, msg_fallback, urlopen_fn=urlopen_fn)
            return {"modo": "fallback_texto", "arquivo": caminho.name, "tamanho_mb": round(tamanho_mb, 2)}


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


def selecionar_arquivos_entrega(
    candidatos: list[Path],
    estrategia: str = "partes",
) -> tuple[list[Path], list[Path]]:
    """Seleciona quais MP4s sobem no Telegram e quais ficam apenas nos GitHub Artifacts.

    - estrategia='partes' (padrao): envia primeiro `*_parte1.mp4` e logo em seguida `*_parte2.mp4`,
      deixando o arquivo pesado completo (`short_NN.mp4`) apenas nos Artifacts. Quando nao houver
      partes fatiadas (ex.: modo --teste de 2s ou video curto de parte unica), envia o arquivo disponivel.
    - estrategia='parte1': envia apenas `*_parte1.mp4` (quando existir).
    - estrategia='todas': envia todos os arquivos encontrados em sequencia.
    """
    existentes = [p for p in candidatos if p.is_file()]
    if not existentes:
        return [], []

    if estrategia == "todas":
        return existentes, []

    parte1 = next((p for p in existentes if "_parte1" in p.stem.lower()), None)
    parte2 = next((p for p in existentes if "_parte2" in p.stem.lower()), None)

    if estrategia == "parte1":
        if parte1 is not None:
            return [parte1], [p for p in existentes if p != parte1]
        escolhido = existentes[0]
        return [escolhido], [p for p in existentes if p != escolhido]

    # Estrategia padrao 'partes': Parte 1 seguida da Parte 2 (sem subir o arquivo completo pesado)
    partes_ordenadas = [p for p in (parte1, parte2) if p is not None]
    if partes_ordenadas:
        outros = [p for p in existentes if p not in partes_ordenadas]
        return partes_ordenadas, outros

    # Sem _parte1/_parte2 (ex.: --teste ou video curto): envia o primeiro arquivo disponivel
    escolhido = existentes[0]
    outros = [p for p in existentes if p != escolhido]
    return [escolhido], outros


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envia Parte 1 e Parte 2 (<= 45 MB cada), link dos Artifacts e legendas prontas no Telegram."
    )
    parser.add_argument("--arquivos", nargs="*", type=Path, default=None, help="Lista manual de arquivos MP4.")
    parser.add_argument("--titulo", type=str, default=None, help="Titulo do video para legenda e status.")
    parser.add_argument("--run-url", type=str, default=None, help="URL da execucao no GitHub Actions.")
    parser.add_argument("--artifact-url", type=str, default=None, help="URL direta do Artifact no GitHub Actions.")
    parser.add_argument(
        "--estrategia",
        choices=("partes", "parte1", "todas"),
        default="partes",
        help="Padrao 'partes': envia Parte 1 e Parte 2 em sequencia, mantendo o arquivo inteiro nos Artifacts.",
    )
    parser.add_argument(
        "--limite-mb",
        type=float,
        default=LIMITE_MB_PADRAO,
        help="Limite seguro em MB por upload na Bot API do Telegram (padrao: 45 MB).",
    )
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
        msg_erro = f"Falha na Fabrica Dark (GitHub Actions).\nMotivo: {args.erro}{link}"
        if args.dry_run:
            print(f"[DRY-RUN] Enviaria mensagem de erro:\n{msg_erro}")
            return
        enviar_mensagem(token, chat_id, msg_erro)
        print("Notificacao de falha enviada no Telegram.")
        return

    video_info: dict = {}
    if args.arquivos:
        candidatos = [p if p.is_absolute() else (RAIZ / p) for p in args.arquivos]
        try:
            video_info = obter_video_atual(validar=False)
        except Exception:
            video_info = {}
    else:
        video_info, candidatos = descobrir_arquivos_video_atual()

    if args.titulo:
        video_info = {**video_info, "titulo": args.titulo}

    para_enviar, apenas_artifact = selecionar_arquivos_entrega(candidatos, estrategia=args.estrategia)
    if not para_enviar:
        raise SystemExit("Nenhum arquivo MP4 encontrado para envio no Telegram.")

    limite_bytes = int(max(1.0, float(args.limite_mb)) * 1024 * 1024)

    for idx, arq in enumerate(para_enviar):
        caption = montar_caption_telegram(
            video_info=video_info,
            arquivo=arq,
            outros_arquivos=apenas_artifact,
            artifact_url=args.artifact_url,
            run_url=args.run_url,
        )
        if args.dry_run:
            tam_mb = arq.stat().st_size / (1024 * 1024)
            print(
                f"[DRY-RUN] ({idx + 1}/{len(para_enviar)}) Estrategia={args.estrategia} | "
                f"Enviaria: {arq.name} ({tam_mb:.2f} MB)"
            )
            if idx == 0 and apenas_artifact:
                print(f"[DRY-RUN] Mantidos apenas nos Artifacts: {[p.name for p in apenas_artifact]}")
            print(f"[DRY-RUN] Caption ({len(caption)} chars):\n{caption}\n")
            continue

        if idx > 0 and PAUSA_ENTRE_PARTES_S > 0:
            time.sleep(PAUSA_ENTRE_PARTES_S)

        res = enviar_arquivo_video(
            token=token,
            chat_id=chat_id,
            caminho=arq,
            legenda=caption,
            run_url=args.run_url,
            artifact_url=args.artifact_url,
            limite_bytes=limite_bytes,
        )
        print(
            f"Telegram OK ({idx + 1}/{len(para_enviar)}) [{res['modo']}]: "
            f"{res['arquivo']} ({res['tamanho_mb']} MB) | caption={len(caption)} chars",
            flush=True,
        )


if __name__ == "__main__":
    main()
