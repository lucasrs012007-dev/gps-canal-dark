"""Estacao 5C (Motor V6): envio automatico do Short completo para o TikTok via Content Posting API v2.

Usa exclusivamente a biblioteca padrao do Python (urllib) e credenciais lidas de variaveis
de ambiente (ou .env local em testes):
- TIKTOK_ACCESS_TOKEN (Token OAuth 2.0 com escopo video.upload e/ou video.publish)
- TIKTOK_REFRESH_TOKEN (Refresh token OAuth 2.0; usado tambem em renovacao automatica se client_key/secret existirem)
- TIKTOK_MODE (padrao: inbox para Inbox/Rascunhos; aceita tambem direct para publicacao direta)
- TIKTOK_PRIVACY (usado em modo direct; padrao: PUBLIC_TO_EVERYONE; aceita tambem MUTUAL_FOLLOW_FRIENDS,
  FOLLOWER_OF_CREATOR e SELF_ONLY - apps ainda nao auditados devem usar SELF_ONLY)
- TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET (opcionais; habilitam refresh automatico em caso de HTTP 401)

Comportamento seguro na pipeline:
- Se TIKTOK_ACCESS_TOKEN ou TIKTOK_REFRESH_TOKEN estiverem vazios, imprime aviso claro no log e
  encerra com codigo 0 sem derrubar o workflow nem afetar YouTube ou Telegram.
- Identifica automaticamente o video completo mais recente (`output/short_NN.mp4`), ignorando
  sempre as versoes fatiadas `_parte1` e `_parte2`.
- Implementa o fluxo oficial `FILE_UPLOAD` da TikTok Content Posting API v2:
  1. Init em `/v2/post/publish/inbox/video/init/` (modo `inbox`, padrao) ou
     `/v2/post/publish/video/init/` (modo `direct`, enviando `post_info` com titulo + hashtags).
  2. Upload binario em chunks via `PUT` com `Content-Range` e `Content-Type: video/mp4` seguindo
     as regras oficiais de chunk do TikTok (1 chunk ate 64 MB; acima disso chunks de 10 MB com
     resto absorvido no ultimo chunk).
  3. Polling de status em `/v2/post/publish/status/fetch/` ate `SEND_TO_USER_INBOX` ou
     `PUBLISH_COMPLETE`, salvando o `publish_id` em `output/tiktok_publish_id.txt`.
- Mascara rigorosamente todos os tokens e segredos em logs e excecoes.

Uso (na raiz do repositorio):
    python3 upload_tiktok.py
    python3 upload_tiktok.py --dry-run
    python3 upload_tiktok.py --mode direct --video output/short_10.mp4 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.config_canal import (  # noqa: E402
    carregar_config_canal,
    obter_hashtags_plataforma,
)

ARQUIVO_ENV = RAIZ / ".env"
PASTA_OUTPUT = RAIZ / "output"
ARQUIVO_CENAS = RAIZ / "cenas.json"
ARQUIVO_HISTORICO = RAIZ / "historico_videos.json"
ARQUIVO_PUBLISH_SAIDA = PASTA_OUTPUT / "tiktok_publish_id.txt"

TIKTOK_API_BASE = "https://open.tiktokapis.com"
ENDPOINT_INIT_INBOX = f"{TIKTOK_API_BASE}/v2/post/publish/inbox/video/init/"
ENDPOINT_INIT_DIRECT = f"{TIKTOK_API_BASE}/v2/post/publish/video/init/"
ENDPOINT_STATUS_FETCH = f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/"
ENDPOINT_OAUTH_TOKEN = f"{TIKTOK_API_BASE}/v2/oauth/token/"

MODOS_VALIDOS: tuple[str, ...] = ("inbox", "direct")
PRIVACIDADES_TIKTOK: tuple[str, ...] = (
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
)

LIMITE_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024
CHUNK_PADRAO_GRANDE_BYTES = 10 * 1024 * 1024
MAX_CHUNKS_TIKTOK = 1000
LIMITE_TITULO_TIKTOK = 2200

HTTP_TIMEOUT_S = 120
MAX_RETRIES_HTTP = 3
STATUS_RETENTAVEIS = (429, 500, 502, 503, 504)
POLL_INTERVALO_INICIAL_S = 5.0
POLL_INTERVALO_MAX_S = 20.0
POLL_TIMEOUT_PADRAO_S = 300.0

RE_VIDEO_COMPLETO = re.compile(r"^short_(\d+)\.mp4$", re.IGNORECASE)
RE_LINHA_ROTEIRO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")
RE_TAGS_VOZ = re.compile(r"\[/?VOZ(?::[a-zA-Z0-9_]+)?\]", re.IGNORECASE)
RE_TAGS_CTRL = re.compile(r"\[/?(?:CTA_PAUSA|CORTE_PARTE_2|SFX:[^\]]+)\]", re.IGNORECASE)
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)


class _ErroAuthTikTok(RuntimeError):
    """Indica token de acesso expirado ou invalido (elegivel para refresh OAuth)."""


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


def _mascarar_segredos(texto: str, segredos: tuple[str, ...]) -> str:
    """Mascara tokens e credenciais em forma literal, URL-encoded e padroes Bearer/form."""
    limpo = str(texto or "")
    for seg in segredos:
        if not seg:
            continue
        variantes = {
            seg,
            urllib.parse.quote(seg, safe=""),
            urllib.parse.quote_plus(seg),
        }
        for v in variantes:
            if v:
                limpo = limpo.replace(v, "***SECRET***")
    limpo = re.sub(r"(Bearer\s+)[^\s\"']+", r"\1***SECRET***", limpo, flags=re.IGNORECASE)
    limpo = re.sub(
        r"((?:access_token|refresh_token|client_secret)=)[^&\s\"']+",
        r"\1***SECRET***",
        limpo,
        flags=re.IGNORECASE,
    )
    return limpo


def _limpar_texto_social(texto: str) -> str:
    """Normaliza UTF-8 preservando acentos PT-BR e remove emojis e travessoes."""
    limpo = unicodedata.normalize("NFC", str(texto or ""))
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = re.sub(r"[ \t]+", " ", limpo)
    return limpo.strip()


def _slug_hashtag(texto: str) -> str:
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"[^a-zA-Z0-9]+", "", sem_acento).lower()


def _restaurar_acentos_se_disponivel(texto: str) -> str:
    try:
        from pipeline.diretor_ia import restaurar_acentos_ptbr

        return restaurar_acentos_ptbr(texto)
    except Exception:
        return texto


def normalizar_modo_tiktok(valor: str | None) -> str:
    """Valida TIKTOK_MODE (padrao: inbox; aceita tambem direct)."""
    raw = str(valor or "").strip().lower()
    if raw in MODOS_VALIDOS:
        return raw
    if raw:
        print(
            f"AVISO TIKTOK_MODE='{raw}' invalido (aceitos: {', '.join(MODOS_VALIDOS)}). "
            "Usando padrao 'inbox'.",
            flush=True,
        )
    return "inbox"


def normalizar_privacidade_tiktok(valor: str | None) -> str:
    """Valida TIKTOK_PRIVACY para o modo direct."""
    raw = str(valor or "").strip().upper()
    if raw in PRIVACIDADES_TIKTOK:
        return raw
    if raw:
        print(
            f"AVISO TIKTOK_PRIVACY='{raw}' invalido (aceitos: {', '.join(PRIVACIDADES_TIKTOK)}). "
            "Usando padrao 'PUBLIC_TO_EVERYONE'.",
            flush=True,
        )
    return "PUBLIC_TO_EVERYONE"


def extrair_numero_short(caminho: Path) -> int | None:
    m = RE_VIDEO_COMPLETO.match(caminho.name)
    return int(m.group(1)) if m else None


def descobrir_video_completo(pasta_output: Path = PASTA_OUTPUT) -> Path | None:
    """Retorna o MP4 completo mais recente (`output/short_NN.mp4`), ignorando `_parte1` e `_parte2`."""
    if not pasta_output.is_dir():
        return None
    candidatos: list[tuple[float, int, Path]] = []
    for arq in pasta_output.iterdir():
        if not arq.is_file():
            continue
        stem_low = arq.stem.lower()
        if "_parte1" in stem_low or "_parte2" in stem_low:
            continue
        num = extrair_numero_short(arq)
        if num is None:
            continue
        try:
            st = arq.stat()
        except OSError:
            continue
        if st.st_size <= 0:
            continue
        candidatos.append((st.st_mtime, num, arq))
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidatos[0][2]


def _carregar_json_seguro(caminho: Path) -> dict:
    if not caminho.is_file():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _extrair_gancho_roteiro(roteiro_rel: str | None, raiz: Path = RAIZ) -> str:
    if not roteiro_rel:
        return ""
    arq = Path(roteiro_rel)
    if not arq.is_absolute():
        arq = raiz / arq
    if not arq.is_file():
        return ""
    try:
        linhas = arq.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    for linha in linhas:
        bruta = linha.strip()
        if not RE_LINHA_ROTEIRO.match(bruta):
            continue
        colunas = [c.strip() for c in bruta.split("|")]
        if len(colunas) < 2:
            continue
        fala = RE_TAGS_VOZ.sub("", colunas[1])
        fala = RE_TAGS_CTRL.sub("", fala)
        fala = _limpar_texto_social(fala)
        if fala:
            return fala[:200].rstrip()
    return ""


def carregar_metadados_tiktok(
    video_id: int | None = None,
    cenas_path: Path = ARQUIVO_CENAS,
    historico_path: Path = ARQUIVO_HISTORICO,
    raiz: Path = RAIZ,
) -> dict:
    """Combina titulo, gancho e palavras-chave de cenas.json e historico_videos.json."""
    cenas = _carregar_json_seguro(cenas_path)
    historico = _carregar_json_seguro(historico_path)
    videos = historico.get("videos") if isinstance(historico.get("videos"), list) else []

    alvo_id = video_id
    if alvo_id is None:
        cid = cenas.get("video_id")
        if isinstance(cid, int) and cid >= 1:
            alvo_id = cid
        elif isinstance(historico.get("video_atual"), int):
            alvo_id = int(historico["video_atual"])

    reg_hist: dict = {}
    if alvo_id is not None:
        for v in videos:
            if isinstance(v, dict) and int(v.get("id", -1)) == int(alvo_id):
                reg_hist = v
                break
    if not reg_hist and videos:
        vid_atual = historico.get("video_atual")
        for v in videos:
            if isinstance(v, dict) and vid_atual is not None and int(v.get("id", -1)) == int(vid_atual):
                reg_hist = v
                break
        if not reg_hist and isinstance(videos[-1], dict):
            reg_hist = videos[-1]

    cenas_bate = bool(cenas) and (
        alvo_id is None
        or not isinstance(cenas.get("video_id"), int)
        or int(cenas["video_id"]) == int(alvo_id)
    )

    cfg_canal = carregar_config_canal()
    nome_canal = _limpar_texto_social(cfg_canal.get("nome_canal", "E Se Você?")) or "E Se Você?"
    if cenas_bate and str(cenas.get("titulo", "")).strip():
        titulo = str(cenas["titulo"]).strip()
    elif str(reg_hist.get("titulo", "")).strip():
        titulo = str(reg_hist["titulo"]).strip()
    elif str(cenas.get("titulo", "")).strip():
        titulo = str(cenas["titulo"]).strip()
    else:
        titulo = f"{nome_canal} {alvo_id:02d}" if alvo_id else nome_canal

    tema = str(reg_hist.get("tema", "") or "").strip()
    gancho = _extrair_gancho_roteiro(str(reg_hist.get("roteiro", "") or ""), raiz=raiz)
    if not gancho and cenas_bate:
        lista_cenas = cenas.get("cenas") if isinstance(cenas.get("cenas"), list) else []
        if lista_cenas and isinstance(lista_cenas[0], dict):
            props0 = lista_cenas[0].get("props") if isinstance(lista_cenas[0].get("props"), dict) else {}
            gancho = _limpar_texto_social(str(props0.get("celular_mensagem", "") or ""))

    palavras_chave: list[str] = []
    vistas: set[str] = set()
    fontes_kw: list = []
    if cenas_bate and isinstance(cenas.get("palavras_vermelhas"), list):
        fontes_kw.extend(cenas["palavras_vermelhas"][:10])
    if isinstance(reg_hist.get("palavras_chave"), list):
        fontes_kw.extend(reg_hist["palavras_chave"])
    for item in fontes_kw:
        limpa = _limpar_texto_social(str(item))
        chave = _slug_hashtag(limpa)
        if len(chave) >= 3 and chave not in vistas:
            vistas.add(chave)
            palavras_chave.append(limpa)

    return {
        "video_id": alvo_id or reg_hist.get("id"),
        "titulo": _restaurar_acentos_se_disponivel(_limpar_texto_social(titulo)),
        "tema": _restaurar_acentos_se_disponivel(_limpar_texto_social(tema)),
        "gancho": _restaurar_acentos_se_disponivel(_limpar_texto_social(gancho)),
        "palavras_chave": palavras_chave,
    }


def montar_titulo_tiktok(meta: dict, config: dict | None = None) -> str:
    """Monta legenda/titulo conciso com hashtags de config_canal.json para o TikTok (<= 2200 chars)."""
    cfg = config if isinstance(config, dict) else carregar_config_canal()
    fallback_titulo = _limpar_texto_social(cfg.get("nome_canal", "E Se Você?")) or "E Se Você?"
    titulo = _limpar_texto_social(meta.get("titulo", "")) or fallback_titulo
    gancho = _limpar_texto_social(meta.get("gancho", ""))

    tags_base = obter_hashtags_plataforma("tiktok", cfg)
    extras: list[str] = []
    for kw in meta.get("palavras_chave") or []:
        slug = _slug_hashtag(str(kw))
        if len(slug) >= 3 and slug not in tags_base and slug not in extras:
            extras.append(slug)
        if len(extras) >= 4:
            break
    hashtags = " ".join(f"#{t}" for t in (tags_base + extras))

    partes = [titulo]
    if gancho and gancho.lower() != titulo.lower() and len(titulo) + len(gancho) <= 240:
        partes.append(gancho)
    partes.append(hashtags)

    texto = " ".join(p.strip() for p in partes if p.strip()).strip()
    return texto[:LIMITE_TITULO_TIKTOK]


def calcular_plano_chunks(video_size: int) -> dict:
    """Calcula chunk_size, total_chunk_count e intervalos de bytes conforme guia oficial TikTok.

    Regras oficiais da TikTok Content Posting API (FILE_UPLOAD):
    - Arquivos <= 64 MB podem ir em 1 unico chunk (chunk_size = video_size, total_chunk_count = 1).
    - Arquivos > 64 MB usam chunks de 5 MB a 64 MB, com total_chunk_count = video_size // chunk_size
      (arredondado para baixo) e o ultimo chunk absorvendo os bytes restantes (ate 128 MB).
    """
    if video_size <= 0:
        raise ValueError(f"Tamanho de video invalido para TikTok: {video_size}")

    if video_size <= LIMITE_SINGLE_CHUNK_BYTES:
        return {
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
            "ranges": [(0, video_size - 1)],
        }

    chunk_size = CHUNK_PADRAO_GRANDE_BYTES
    while (video_size // chunk_size) > MAX_CHUNKS_TIKTOK and chunk_size < LIMITE_SINGLE_CHUNK_BYTES:
        chunk_size = min(LIMITE_SINGLE_CHUNK_BYTES, chunk_size * 2)

    total_chunks = max(1, video_size // chunk_size)
    if total_chunks > MAX_CHUNKS_TIKTOK:
        raise ValueError(f"Arquivo excede o limite de {MAX_CHUNKS_TIKTOK} chunks do TikTok.")

    ranges: list[tuple[int, int]] = []
    for idx in range(total_chunks):
        start = idx * chunk_size
        end = (video_size - 1) if idx == (total_chunks - 1) else (start + chunk_size - 1)
        ranges.append((start, end))

    return {
        "video_size": video_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunks,
        "ranges": ranges,
    }


def _extrair_erro_tiktok(corpo: str) -> tuple[str, str]:
    """Retorna (codigo, descricao) do envelope padrao TikTok v2."""
    try:
        dados = json.loads(corpo)
        if isinstance(dados, dict) and isinstance(dados.get("error"), dict):
            err = dados["error"]
            code = str(err.get("code", "") or "").strip()
            msg = str(err.get("message", "") or "").strip()
            log_id = str(err.get("log_id", "") or "").strip()
            det = f"{code}: {msg}" if msg else code
            if log_id:
                det = f"{det} (log_id={log_id})"
            return code, det
    except json.JSONDecodeError:
        pass
    return "", corpo[:300].strip()


def _executar_post_json_tiktok(
    url: str,
    payload: dict,
    access_token: str,
    *,
    segredos: tuple[str, ...],
    timeout: int = HTTP_TIMEOUT_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Envia POST JSON autenticado a TikTok API v2 com retry em 429/5xx e mascaramento."""
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
        "User-Agent": "gps-canal-dark/6.0",
    }

    ultimo_erro = ""
    for tentativa in range(1, MAX_RETRIES_HTTP + 1):
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
        try:
            with urlopen_fn(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            dados = json.loads(raw) if raw.strip() else {}
            if not isinstance(dados, dict):
                raise RuntimeError(f"Resposta JSON inesperada da TikTok API: {type(dados).__name__}")
            err = dados.get("error")
            if isinstance(err, dict):
                code = str(err.get("code", "") or "").strip().lower()
                if code and code != "ok":
                    _, det = _extrair_erro_tiktok(raw)
                    det_seg = _mascarar_segredos(det, segredos)
                    if code in ("access_token_invalid", "invalid_token"):
                        raise _ErroAuthTikTok(f"TikTok auth erro: {det_seg}")
                    raise RuntimeError(f"TikTok API retornou erro: {det_seg}")
            return dados
        except urllib.error.HTTPError as exc:
            corpo = ""
            try:
                corpo = exc.read().decode("utf-8", errors="replace")
            except Exception:
                corpo = ""
            code_err, det = _extrair_erro_tiktok(corpo)
            det_seg = _mascarar_segredos(det or str(exc), segredos)
            ultimo_erro = f"HTTP {exc.code}: {det_seg}"
            if exc.code == 401 or code_err.lower() in ("access_token_invalid", "invalid_token"):
                raise _ErroAuthTikTok(ultimo_erro) from None
            if exc.code in STATUS_RETENTAVEIS and tentativa < MAX_RETRIES_HTTP:
                espera = float(2**tentativa)
                print(
                    f"AVISO TikTok API ({ultimo_erro}). Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
                    flush=True,
                )
                sleep_fn(espera)
                continue
            raise RuntimeError(ultimo_erro) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ultimo_erro = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
            if tentativa < MAX_RETRIES_HTTP:
                espera = float(2**tentativa)
                print(
                    f"AVISO erro de rede na TikTok API ({ultimo_erro}). "
                    f"Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
                    flush=True,
                )
                sleep_fn(espera)
                continue
            raise RuntimeError(ultimo_erro) from None
        except json.JSONDecodeError as exc:
            msg = _mascarar_segredos(f"JSONDecodeError: {exc}", segredos)
            raise RuntimeError(f"Resposta invalida da TikTok API ({msg})") from None

    raise RuntimeError(ultimo_erro or "Falha desconhecida na TikTok API")


def renovar_token_tiktok(
    refresh_token: str,
    client_key: str,
    client_secret: str,
    *,
    urlopen_fn: Callable = urllib.request.urlopen,
) -> str:
    """Troca TIKTOK_REFRESH_TOKEN por um novo access_token via OAuth v2 quando client_key/secret existem."""
    segredos = (refresh_token, client_key, client_secret)
    form_bytes = urllib.parse.urlencode(
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT_OAUTH_TOKEN,
        data=form_bytes,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
            "User-Agent": "gps-canal-dark/6.0",
        },
        method="POST",
    )
    try:
        with urlopen_fn(req, timeout=HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        dados = json.loads(raw)
        novo_token = str(dados.get("access_token", "") or "").strip()
        if not novo_token:
            raise RuntimeError("Resposta OAuth do TikTok sem 'access_token'.")
        return novo_token
    except Exception as exc:
        msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
        raise RuntimeError(f"Falha ao renovar TIKTOK_ACCESS_TOKEN ({msg})") from None


def montar_payload_init_tiktok(
    *,
    mode: str,
    plano_chunks: dict,
    titulo: str,
    privacy_level: str,
) -> tuple[str, dict]:
    """Retorna (endpoint, payload_json) oficial da TikTok Content Posting API v2."""
    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": int(plano_chunks["video_size"]),
        "chunk_size": int(plano_chunks["chunk_size"]),
        "total_chunk_count": int(plano_chunks["total_chunk_count"]),
    }
    if mode == "direct":
        payload = {
            "post_info": {
                "title": titulo[:LIMITE_TITULO_TIKTOK],
                "privacy_level": normalizar_privacidade_tiktok(privacy_level),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": source_info,
        }
        return ENDPOINT_INIT_DIRECT, payload
    return ENDPOINT_INIT_INBOX, {"source_info": source_info}


def inicializar_upload_tiktok(
    *,
    access_token: str,
    mode: str,
    plano_chunks: dict,
    titulo: str,
    privacy_level: str,
    segredos: tuple[str, ...],
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Passo 1 TikTok API: inicia sessao FILE_UPLOAD e retorna (publish_id, upload_url)."""
    endpoint, payload = montar_payload_init_tiktok(
        mode=mode,
        plano_chunks=plano_chunks,
        titulo=titulo,
        privacy_level=privacy_level,
    )
    resp = _executar_post_json_tiktok(
        endpoint,
        payload,
        access_token,
        segredos=segredos,
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
    )
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    publish_id = str(data.get("publish_id", "") or "").strip()
    upload_url = str(data.get("upload_url", "") or "").strip()
    if not publish_id or not upload_url:
        raise RuntimeError(f"TikTok init nao retornou publish_id/upload_url: {resp!r}")
    return publish_id, upload_url


def enviar_chunks_tiktok(
    video_path: Path,
    upload_url: str,
    plano_chunks: dict,
    *,
    segredos: tuple[str, ...],
    timeout: int = HTTP_TIMEOUT_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Passo 2 TikTok API: envia cada chunk binario via PUT com Content-Range."""
    video_size = int(plano_chunks["video_size"])
    ranges: list[tuple[int, int]] = plano_chunks["ranges"]
    total = len(ranges)

    with video_path.open("rb") as fh:
        for idx, (start, end) in enumerate(ranges, start=1):
            tamanho = end - start + 1
            fh.seek(start)
            bloco = fh.read(tamanho)
            if len(bloco) != tamanho:
                raise RuntimeError(
                    f"Leitura incompleta do chunk {idx}/{total} ({len(bloco)}/{tamanho} bytes)."
                )
            headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(tamanho),
                "Content-Range": f"bytes {start}-{end}/{video_size}",
                "User-Agent": "gps-canal-dark/6.0",
            }
            ultimo_erro = ""
            enviado = False
            for tentativa in range(1, MAX_RETRIES_HTTP + 1):
                req = urllib.request.Request(upload_url, data=bloco, headers=headers, method="PUT")
                try:
                    with urlopen_fn(req, timeout=timeout) as resp:
                        status = int(getattr(resp, "status", 200))
                        _ = resp.read()
                    if status not in (200, 201, 206):
                        raise RuntimeError(f"Status HTTP inesperado no upload de chunk TikTok: {status}")
                    pct = int(((end + 1) / video_size) * 100)
                    print(f"Upload TikTok chunk {idx}/{total} concluido ({pct}%, HTTP {status})", flush=True)
                    enviado = True
                    break
                except urllib.error.HTTPError as exc:
                    ultimo_erro = _mascarar_segredos(f"HTTP {exc.code}: {exc.reason}", segredos)
                    if exc.code in STATUS_RETENTAVEIS and tentativa < MAX_RETRIES_HTTP:
                        espera = float(2**tentativa)
                        print(
                            f"AVISO chunk {idx}/{total} TikTok ({ultimo_erro}). "
                            f"Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
                            flush=True,
                        )
                        sleep_fn(espera)
                        continue
                    raise RuntimeError(f"Falha no PUT do chunk {idx}/{total} ({ultimo_erro})") from None
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    ultimo_erro = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
                    if tentativa < MAX_RETRIES_HTTP:
                        espera = float(2**tentativa)
                        print(
                            f"AVISO rede no chunk {idx}/{total} TikTok ({ultimo_erro}). "
                            f"Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
                            flush=True,
                        )
                        sleep_fn(espera)
                        continue
                    raise RuntimeError(f"Falha de rede no chunk {idx}/{total} ({ultimo_erro})") from None
            if not enviado:
                raise RuntimeError(ultimo_erro or f"Falha ao enviar chunk {idx}/{total} ao TikTok.")


def aguardar_status_tiktok(
    publish_id: str,
    access_token: str,
    *,
    segredos: tuple[str, ...],
    timeout_s: float = POLL_TIMEOUT_PADRAO_S,
    intervalo_inicial_s: float = POLL_INTERVALO_INICIAL_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict:
    """Passo 3 TikTok API: consulta /v2/post/publish/status/fetch/ ate conclusao."""
    inicio = monotonic_fn()
    espera = max(0.0, float(intervalo_inicial_s))
    tentativa = 0

    while True:
        tentativa += 1
        resp = _executar_post_json_tiktok(
            ENDPOINT_STATUS_FETCH,
            {"publish_id": publish_id},
            access_token,
            segredos=segredos,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        status = str(data.get("status", "") or "").strip().upper()
        fail_reason = str(data.get("fail_reason", "") or "").strip()
        print(f"TikTok publish_id={publish_id}: tentativa {tentativa} | status={status or 'INDEFINIDO'}", flush=True)

        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return {"status": status, "data": data}
        if status == "FAILED":
            det = f" ({fail_reason})" if fail_reason else ""
            raise RuntimeError(f"Processamento no TikTok falhou: status=FAILED{det}")

        decorrido = monotonic_fn() - inicio
        if decorrido >= timeout_s:
            raise RuntimeError(
                f"Timeout ({timeout_s:.0f}s) aguardando status do TikTok (ultimo status={status or 'INDEFINIDO'})."
            )

        sleep_fn(espera)
        espera = min(POLL_INTERVALO_MAX_S, max(1.0, espera * 1.4)) if espera > 0 else 0.0


def enviar_para_tiktok(
    video_path: Path,
    *,
    titulo: str,
    access_token: str,
    refresh_token: str,
    mode: str = "inbox",
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    client_key: str = "",
    client_secret: str = "",
    timeout_s: float = POLL_TIMEOUT_PADRAO_S,
    intervalo_inicial_s: float = POLL_INTERVALO_INICIAL_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict:
    """Executa o fluxo completo FILE_UPLOAD (init -> chunk PUT -> status fetch) com refresh opcional."""
    modo_norm = normalizar_modo_tiktok(mode)
    priv_norm = normalizar_privacidade_tiktok(privacy_level)
    video_size = video_path.stat().st_size
    plano = calcular_plano_chunks(video_size)
    token_ativo = access_token
    segredos_lista = [s for s in (access_token, refresh_token, client_key, client_secret) if s]

    try:
        try:
            publish_id, upload_url = inicializar_upload_tiktok(
                access_token=token_ativo,
                mode=modo_norm,
                plano_chunks=plano,
                titulo=titulo,
                privacy_level=priv_norm,
                segredos=tuple(segredos_lista),
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
            )
        except _ErroAuthTikTok:
            if not (refresh_token and client_key and client_secret):
                raise
            print(
                "AVISO TIKTOK_ACCESS_TOKEN expirado; tentando renovar via TIKTOK_REFRESH_TOKEN...",
                flush=True,
            )
            token_ativo = renovar_token_tiktok(
                refresh_token=refresh_token,
                client_key=client_key,
                client_secret=client_secret,
                urlopen_fn=urlopen_fn,
            )
            segredos_lista.append(token_ativo)
            publish_id, upload_url = inicializar_upload_tiktok(
                access_token=token_ativo,
                mode=modo_norm,
                plano_chunks=plano,
                titulo=titulo,
                privacy_level=priv_norm,
                segredos=tuple(segredos_lista),
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
            )

        print(
            f"Sessao TikTok FILE_UPLOAD iniciada: mode={modo_norm} | publish_id={publish_id} | "
            f"chunks={plano['total_chunk_count']}",
            flush=True,
        )

        enviar_chunks_tiktok(
            video_path=video_path,
            upload_url=upload_url,
            plano_chunks=plano,
            segredos=tuple(segredos_lista),
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )

        status_res = aguardar_status_tiktok(
            publish_id=publish_id,
            access_token=token_ativo,
            segredos=tuple(segredos_lista),
            timeout_s=timeout_s,
            intervalo_inicial_s=intervalo_inicial_s,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        return {
            "publish_id": publish_id,
            "mode": modo_norm,
            "status": status_res["status"],
            "chunks": plano["total_chunk_count"],
        }
    except Exception as exc:
        msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", tuple(segredos_lista))
        raise RuntimeError(f"Falha no upload para o TikTok ({msg})") from None


def salvar_publish_id_tiktok(resultado: dict, destino: Path = ARQUIVO_PUBLISH_SAIDA) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    linha = f"{resultado['publish_id']} ({resultado['mode']}:{resultado['status']})"
    destino.write_text(linha + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estacao 5C: envia automaticamente o video completo (output/short_NN.mp4) ao TikTok."
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=None,
        help="Caminho manual do MP4 completo (padrao: output/short_NN.mp4 mais recente).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Sobrescreve TIKTOK_MODE (inbox para rascunhos/inbox ou direct para publicacao direta).",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        default=None,
        help="Sobrescreve TIKTOK_PRIVACY no modo direct (padrao: PUBLIC_TO_EVERYONE).",
    )
    parser.add_argument(
        "--cenas",
        type=Path,
        default=ARQUIVO_CENAS,
        help="Caminho do cenas.json para gerar titulo e hashtags (padrao: cenas.json).",
    )
    parser.add_argument(
        "--saida-id",
        type=Path,
        default=ARQUIVO_PUBLISH_SAIDA,
        help="Arquivo onde o publish_id sera salvo (padrao: output/tiktok_publish_id.txt).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o video selecionado, plano de chunks e payload sem enviar ao TikTok.",
    )
    args = parser.parse_args(argv)

    carregar_env()

    access_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    mode = normalizar_modo_tiktok(args.mode or os.environ.get("TIKTOK_MODE", "inbox"))
    privacy = normalizar_privacidade_tiktok(args.privacy or os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"))

    if not args.dry_run:
        faltantes = [
            nome
            for nome, val in (
                ("TIKTOK_ACCESS_TOKEN", access_token),
                ("TIKTOK_REFRESH_TOKEN", refresh_token),
            )
            if not val
        ]
        if faltantes:
            print(
                f"AVISO Estacao 5C (TikTok) ignorada: secret(s) ausente(s): {', '.join(faltantes)}. "
                "Encerrando com codigo 0 sem interromper a pipeline.",
                flush=True,
            )
            return 0

    if args.video is not None:
        video_path = args.video if args.video.is_absolute() else (RAIZ / args.video)
        if not video_path.is_file():
            raise SystemExit(f"Arquivo de video informado nao encontrado: {video_path}")
        if "_parte1" in video_path.stem.lower() or "_parte2" in video_path.stem.lower():
            raise SystemExit(
                f"Upload recusado para versao fatiada ({video_path.name}). Informe o video completo output/short_NN.mp4."
            )
    else:
        video_path = descobrir_video_completo(PASTA_OUTPUT)
        if video_path is None:
            print(
                "AVISO Estacao 5C (TikTok): nenhum video completo output/short_NN.mp4 encontrado em output/. "
                "Nada para enviar ao TikTok.",
                flush=True,
            )
            return 0

    cenas_path = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    video_id_num = extrair_numero_short(video_path)
    meta = carregar_metadados_tiktok(video_id=video_id_num, cenas_path=cenas_path)
    titulo_tiktok = montar_titulo_tiktok(meta)
    video_size = video_path.stat().st_size
    plano = calcular_plano_chunks(video_size)
    endpoint, payload_init = montar_payload_init_tiktok(
        mode=mode,
        plano_chunks=plano,
        titulo=titulo_tiktok,
        privacy_level=privacy,
    )

    tamanho_mb = video_size / (1024 * 1024)
    print(
        f"Estacao 5C (TikTok): arquivo={video_path.name} ({tamanho_mb:.2f} MB) | "
        f"mode={mode} | chunks={plano['total_chunk_count']} | endpoint={endpoint}",
        flush=True,
    )
    print(f"  Titulo/Legenda ({len(titulo_tiktok)}/{LIMITE_TITULO_TIKTOK}): {titulo_tiktok}", flush=True)

    if args.dry_run:
        print(f"  Payload init: {json.dumps(payload_init, ensure_ascii=False)}", flush=True)
        print("[DRY-RUN] Envio TikTok simulado com sucesso (nenhuma chamada feita a TikTok API).", flush=True)
        return 0

    try:
        resultado = enviar_para_tiktok(
            video_path=video_path,
            titulo=titulo_tiktok,
            access_token=access_token,
            refresh_token=refresh_token,
            mode=mode,
            privacy_level=privacy,
            client_key=client_key,
            client_secret=client_secret,
        )
    except RuntimeError as exc:
        print(f"ERRO Estacao 5C: {exc}", file=sys.stderr, flush=True)
        return 1

    destino = args.saida_id if args.saida_id.is_absolute() else (RAIZ / args.saida_id)
    salvar_publish_id_tiktok(resultado, destino=destino)
    print(
        f"TikTok concluido com sucesso: publish_id={resultado['publish_id']} | "
        f"mode={resultado['mode']} | status={resultado['status']}",
        flush=True,
    )
    print(f"Registro salvo em: {destino}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
