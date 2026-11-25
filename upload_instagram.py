"""Estacao 5B (Motor V6): publicacao automatica de Reels no Instagram via Meta Graph API.

Usa exclusivamente a biblioteca padrao do Python (urllib) e credenciais lidas de variaveis
de ambiente (ou .env local em testes):
- IG_USER_ID (ID numerico da conta profissional Instagram conectada a Meta Graph API)
- IG_ACCESS_TOKEN (Token de acesso com permissao instagram_content_publish / instagram_business_content_publish)
- PUBLIC_VIDEO_URL (opcional localmente; no GitHub Actions e fornecida via asset temporario de GitHub Release)
- IG_API_VERSION (opcional; padrao: v21.0)
- IG_GRAPH_BASE_URL (opcional; padrao: https://graph.facebook.com)

Comportamento seguro na pipeline:
- Se IG_USER_ID, IG_ACCESS_TOKEN ou PUBLIC_VIDEO_URL estiverem vazios, imprime aviso claro no log
  e encerra com codigo 0, sem interromper YouTube, Artifacts nem Telegram.
- Executa o fluxo oficial da Meta Graph API para Reels:
  1. POST /{ig_user_id}/media com media_type=REELS, video_url, caption e share_to_feed=true.
  2. Polling em GET /{creation_id}?fields=status_code,status ate status_code == FINISHED.
  3. POST /{ig_user_id}/media_publish com creation_id.
  4. Consulta opcional de permalink em GET /{media_id}?fields=permalink e grava em output/instagram_url.txt.
- Mascara rigorosamente IG_ACCESS_TOKEN (forma bruta e URL-encoded) em logs e excecoes.

Uso (na raiz do repositorio):
    python3 upload_instagram.py
    python3 upload_instagram.py --dry-run
    python3 upload_instagram.py --video-url https://exemplo.com/short_10.mp4 --dry-run
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
ARQUIVO_URL_SAIDA = PASTA_OUTPUT / "instagram_url.txt"

IG_GRAPH_BASE_URL_PADRAO = "https://graph.facebook.com"
IG_API_VERSION_PADRAO = "v21.0"
LIMITE_LEGENDA_IG = 2200
HTTP_TIMEOUT_S = 60
MAX_RETRIES_HTTP = 3
STATUS_RETENTAVEIS = (429, 500, 502, 503, 504)
POLL_INTERVALO_INICIAL_S = 10.0
POLL_INTERVALO_MAX_S = 30.0
POLL_TIMEOUT_PADRAO_S = 300.0

RE_API_VERSION = re.compile(r"^v\d+\.\d+$")
RE_VIDEO_COMPLETO = re.compile(r"^short_(\d+)\.mp4$", re.IGNORECASE)
RE_LINHA_ROTEIRO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")
RE_TAGS_VOZ = re.compile(r"\[/?VOZ(?::[a-zA-Z0-9_]+)?\]", re.IGNORECASE)
RE_TAGS_CTRL = re.compile(r"\[/?(?:CTA_PAUSA|CORTE_PARTE_2|SFX:[^\]]+)\]", re.IGNORECASE)
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)


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
    """Oculta segredos em forma literal e URL-encoded para impedir vazamento em logs."""
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
    limpo = re.sub(r"(access_token=)[^&\s\"']+", r"\1***SECRET***", limpo, flags=re.IGNORECASE)
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


def _normalizar_api_version(valor: str | None) -> str:
    raw = str(valor or "").strip()
    if RE_API_VERSION.match(raw):
        return raw
    return IG_API_VERSION_PADRAO


def _normalizar_graph_base_url(valor: str | None) -> str:
    raw = str(valor or "").strip().rstrip("/")
    if raw.startswith("https://"):
        return raw
    return IG_GRAPH_BASE_URL_PADRAO


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
            return fala[:220].rstrip()
    return ""


def carregar_metadados_cenas(
    video_id: int | None = None,
    cenas_path: Path = ARQUIVO_CENAS,
    historico_path: Path = ARQUIVO_HISTORICO,
    raiz: Path = RAIZ,
) -> dict:
    """Le titulo, gancho, CTA e palavras-chave de cenas.json (com reforco opcional de historico_videos.json)."""
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
            gancho = _limpar_texto_social(
                str(lista_cenas[0].get("fala") or props0.get("celular_mensagem") or "")
            )

    cta_texto = ""
    if cenas_bate and isinstance(cenas.get("cta"), dict):
        cta_texto = _limpar_texto_social(str(cenas["cta"].get("texto", "") or ""))

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
        "cta": _restaurar_acentos_se_disponivel(cta_texto),
        "palavras_chave": palavras_chave,
    }


def montar_legenda_reels(meta: dict, config: dict | None = None) -> str:
    """Gera legenda curta com gancho, CTA e hashtags de config_canal.json para Reels."""
    cfg = config if isinstance(config, dict) else carregar_config_canal()
    fallback_titulo = _limpar_texto_social(cfg.get("nome_canal", "E Se Você?")) or "E Se Você?"
    titulo = _limpar_texto_social(meta.get("titulo", "")) or fallback_titulo
    gancho = _limpar_texto_social(meta.get("gancho", ""))
    tema = _limpar_texto_social(meta.get("tema", ""))
    cta_final = _limpar_texto_social(cfg.get("cta_final", "")) or _limpar_texto_social(meta.get("cta", ""))

    abertura = titulo if titulo.endswith((".", "!", "?")) else f"{titulo}."
    complemento = gancho or tema
    if complemento:
        if not complemento.endswith((".", "!", "?")):
            complemento += "."
        if complemento.lower() == abertura.lower():
            complemento = ""

    tags_base = obter_hashtags_plataforma("instagram", cfg)
    extras: list[str] = []
    for kw in meta.get("palavras_chave") or []:
        slug = _slug_hashtag(str(kw))
        if len(slug) >= 3 and slug not in tags_base and slug not in extras:
            extras.append(slug)
        if len(extras) >= 4:
            break
    hashtags = " ".join(f"#{t}" for t in (tags_base + extras))

    blocos = [abertura]
    if complemento:
        blocos.append(complemento)
    if cta_final:
        blocos.append(cta_final)
    blocos.append(hashtags)

    legenda = "\n\n".join(b for b in blocos if b).strip()
    return legenda[:LIMITE_LEGENDA_IG]


def _extrair_erro_graph(corpo: str) -> str:
    try:
        dados = json.loads(corpo)
        if isinstance(dados, dict) and isinstance(dados.get("error"), dict):
            err = dados["error"]
            msg = str(err.get("message", "") or "").strip()
            code = err.get("code")
            subcode = err.get("error_subcode")
            detalhes = f"code={code}" + (f", subcode={subcode}" if subcode is not None else "")
            return f"{msg} ({detalhes})" if msg else detalhes
    except json.JSONDecodeError:
        pass
    return corpo[:300].strip()


def _executar_requisicao_json(
    url: str,
    *,
    method: str = "GET",
    form_data: dict[str, str] | None = None,
    segredos: tuple[str, ...] = (),
    timeout: int = HTTP_TIMEOUT_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Executa requisicao HTTP para a Meta Graph API com retry em falhas transitorias e mascaramento."""
    data_bytes = None
    headers = {"Accept": "application/json", "User-Agent": "gps-canal-dark/6.0"}
    if form_data is not None:
        data_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    ultimo_erro = ""
    for tentativa in range(1, MAX_RETRIES_HTTP + 1):
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with urlopen_fn(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            dados = json.loads(raw) if raw.strip() else {}
            if not isinstance(dados, dict):
                raise RuntimeError(f"Resposta JSON inesperada da Meta Graph API: {type(dados).__name__}")
            if isinstance(dados.get("error"), dict):
                det = _mascarar_segredos(_extrair_erro_graph(raw), segredos)
                raise RuntimeError(f"Meta Graph API retornou erro: {det}")
            return dados
        except urllib.error.HTTPError as exc:
            corpo_erro = ""
            try:
                corpo_erro = exc.read().decode("utf-8", errors="replace")
            except Exception:
                corpo_erro = ""
            det_erro = _mascarar_segredos(_extrair_erro_graph(corpo_erro) or str(exc), segredos)
            ultimo_erro = f"HTTP {exc.code}: {det_erro}"
            if exc.code in STATUS_RETENTAVEIS and tentativa < MAX_RETRIES_HTTP:
                espera = float(2**tentativa)
                print(
                    f"AVISO Meta Graph API ({ultimo_erro}). Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
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
                    f"AVISO erro de rede na Meta Graph API ({ultimo_erro}). "
                    f"Tentativa {tentativa}/{MAX_RETRIES_HTTP} em {espera:.0f}s...",
                    flush=True,
                )
                sleep_fn(espera)
                continue
            raise RuntimeError(ultimo_erro) from None
        except json.JSONDecodeError as exc:
            msg = _mascarar_segredos(f"JSONDecodeError: {exc}", segredos)
            raise RuntimeError(f"Resposta invalida da Meta Graph API ({msg})") from None

    raise RuntimeError(ultimo_erro or "Falha desconhecida na Meta Graph API")


def criar_container_reels(
    ig_user_id: str,
    access_token: str,
    video_url: str,
    caption: str,
    *,
    api_version: str = IG_API_VERSION_PADRAO,
    graph_base_url: str = IG_GRAPH_BASE_URL_PADRAO,
    share_to_feed: bool = True,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Passo 1 da Meta Graph API: cria container de midia REELS e retorna creation_id."""
    versao = _normalizar_api_version(api_version)
    base = _normalizar_graph_base_url(graph_base_url)
    user_enc = urllib.parse.quote(ig_user_id.strip(), safe="")
    url = f"{base}/{versao}/{user_enc}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url.strip(),
        "caption": caption[:LIMITE_LEGENDA_IG],
        "share_to_feed": "true" if share_to_feed else "false",
        "access_token": access_token,
    }
    resp = _executar_requisicao_json(
        url,
        method="POST",
        form_data=payload,
        segredos=(access_token,),
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
    )
    creation_id = str(resp.get("id", "") or "").strip()
    if not creation_id:
        raise RuntimeError(f"Meta Graph API nao retornou creation_id ao criar container: {resp!r}")
    return creation_id


def aguardar_processamento_container(
    creation_id: str,
    access_token: str,
    *,
    api_version: str = IG_API_VERSION_PADRAO,
    graph_base_url: str = IG_GRAPH_BASE_URL_PADRAO,
    timeout_s: float = POLL_TIMEOUT_PADRAO_S,
    intervalo_inicial_s: float = POLL_INTERVALO_INICIAL_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> str:
    """Passo 2 da Meta Graph API: faz polling em status_code ate FINISHED (ou PUBLISHED)."""
    versao = _normalizar_api_version(api_version)
    base = _normalizar_graph_base_url(graph_base_url)
    cid_enc = urllib.parse.quote(creation_id.strip(), safe="")
    query = urllib.parse.urlencode({"fields": "status_code,status", "access_token": access_token})
    url = f"{base}/{versao}/{cid_enc}?{query}"

    inicio = monotonic_fn()
    espera = max(0.0, float(intervalo_inicial_s))
    tentativa = 0

    while True:
        tentativa += 1
        resp = _executar_requisicao_json(
            url,
            method="GET",
            segredos=(access_token,),
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        status_code = str(resp.get("status_code", "") or "").strip().upper()
        status_desc = str(resp.get("status", "") or "").strip()
        print(
            f"Instagram container {creation_id}: tentativa {tentativa} | status_code={status_code or 'INDEFINIDO'}",
            flush=True,
        )

        if status_code in ("FINISHED", "PUBLISHED"):
            return status_code
        if status_code in ("ERROR", "EXPIRED"):
            det = f" ({status_desc})" if status_desc else ""
            raise RuntimeError(f"Container Instagram falhou no processamento: status_code={status_code}{det}")

        decorrido = monotonic_fn() - inicio
        if decorrido >= timeout_s:
            raise RuntimeError(
                f"Timeout ({timeout_s:.0f}s) aguardando processamento do container Instagram "
                f"(ultimo status_code={status_code or 'INDEFINIDO'})."
            )

        sleep_fn(espera)
        espera = min(POLL_INTERVALO_MAX_S, max(1.0, espera * 1.4)) if espera > 0 else 0.0


def publicar_container_reels(
    ig_user_id: str,
    access_token: str,
    creation_id: str,
    *,
    api_version: str = IG_API_VERSION_PADRAO,
    graph_base_url: str = IG_GRAPH_BASE_URL_PADRAO,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Passo 3 da Meta Graph API: publica o container finalizado via /{ig_user_id}/media_publish."""
    versao = _normalizar_api_version(api_version)
    base = _normalizar_graph_base_url(graph_base_url)
    user_enc = urllib.parse.quote(ig_user_id.strip(), safe="")
    url = f"{base}/{versao}/{user_enc}/media_publish"
    payload = {
        "creation_id": creation_id.strip(),
        "access_token": access_token,
    }
    resp = _executar_requisicao_json(
        url,
        method="POST",
        form_data=payload,
        segredos=(access_token,),
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
    )
    media_id = str(resp.get("id", "") or "").strip()
    if not media_id:
        raise RuntimeError(f"Meta Graph API nao retornou media_id em media_publish: {resp!r}")
    return media_id


def obter_permalink_reels(
    media_id: str,
    access_token: str,
    *,
    api_version: str = IG_API_VERSION_PADRAO,
    graph_base_url: str = IG_GRAPH_BASE_URL_PADRAO,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Consulta opcionalmente o permalink publico do Reel recem-publicado."""
    versao = _normalizar_api_version(api_version)
    base = _normalizar_graph_base_url(graph_base_url)
    mid_enc = urllib.parse.quote(media_id.strip(), safe="")
    query = urllib.parse.urlencode({"fields": "permalink", "access_token": access_token})
    url = f"{base}/{versao}/{mid_enc}?{query}"
    try:
        resp = _executar_requisicao_json(
            url,
            method="GET",
            segredos=(access_token,),
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        return str(resp.get("permalink", "") or "").strip()
    except RuntimeError:
        return ""


def enviar_para_instagram(
    ig_user_id: str,
    access_token: str,
    video_url: str,
    caption: str,
    *,
    api_version: str = IG_API_VERSION_PADRAO,
    graph_base_url: str = IG_GRAPH_BASE_URL_PADRAO,
    timeout_s: float = POLL_TIMEOUT_PADRAO_S,
    intervalo_inicial_s: float = POLL_INTERVALO_INICIAL_S,
    urlopen_fn: Callable = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict:
    """Executa o ciclo completo da Meta Graph API (criar container -> polling -> media_publish)."""
    segredos = (access_token,)
    try:
        creation_id = criar_container_reels(
            ig_user_id=ig_user_id,
            access_token=access_token,
            video_url=video_url,
            caption=caption,
            api_version=api_version,
            graph_base_url=graph_base_url,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        print(f"Container Instagram Reels criado: creation_id={creation_id}", flush=True)

        status_final = aguardar_processamento_container(
            creation_id=creation_id,
            access_token=access_token,
            api_version=api_version,
            graph_base_url=graph_base_url,
            timeout_s=timeout_s,
            intervalo_inicial_s=intervalo_inicial_s,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )

        media_id = publicar_container_reels(
            ig_user_id=ig_user_id,
            access_token=access_token,
            creation_id=creation_id,
            api_version=api_version,
            graph_base_url=graph_base_url,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        permalink = obter_permalink_reels(
            media_id=media_id,
            access_token=access_token,
            api_version=api_version,
            graph_base_url=graph_base_url,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
        )
        return {
            "creation_id": creation_id,
            "status_container": status_final,
            "media_id": media_id,
            "permalink": permalink,
        }
    except Exception as exc:
        msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
        raise RuntimeError(f"Falha no upload para o Instagram Reels ({msg})") from None


def salvar_url_instagram(texto: str, destino: Path = ARQUIVO_URL_SAIDA) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto.strip() + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estacao 5B: publica automaticamente o Short como Instagram Reels via Meta Graph API."
    )
    parser.add_argument(
        "--video-url",
        type=str,
        default=None,
        help="URL HTTPS publica do MP4 completo (sobrescreve PUBLIC_VIDEO_URL).",
    )
    parser.add_argument(
        "--cenas",
        type=Path,
        default=ARQUIVO_CENAS,
        help="Caminho do cenas.json para gerar legenda e hashtags (padrao: cenas.json).",
    )
    parser.add_argument(
        "--saida-url",
        type=Path,
        default=ARQUIVO_URL_SAIDA,
        help="Arquivo onde o permalink/ID publicado sera salvo (padrao: output/instagram_url.txt).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra a legenda e configuracao montadas sem chamar a Meta Graph API.",
    )
    args = parser.parse_args(argv)

    carregar_env()

    ig_user_id = os.environ.get("IG_USER_ID", "").strip()
    ig_access_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    public_video_url = (args.video_url or os.environ.get("PUBLIC_VIDEO_URL", "")).strip()
    api_version = _normalizar_api_version(os.environ.get("IG_API_VERSION", IG_API_VERSION_PADRAO))
    graph_base_url = _normalizar_graph_base_url(os.environ.get("IG_GRAPH_BASE_URL", IG_GRAPH_BASE_URL_PADRAO))

    if not args.dry_run:
        faltantes = [
            nome
            for nome, val in (
                ("IG_USER_ID", ig_user_id),
                ("IG_ACCESS_TOKEN", ig_access_token),
            )
            if not val
        ]
        if faltantes:
            print(
                f"AVISO Estacao 5B (Instagram Reels) ignorada: secret(s) ausente(s): {', '.join(faltantes)}. "
                "Encerrando com codigo 0 sem interromper a pipeline.",
                flush=True,
            )
            return 0

        if not public_video_url:
            print(
                "AVISO Estacao 5B (Instagram Reels) ignorada: PUBLIC_VIDEO_URL vazia. "
                "Forneca uma URL publica HTTPS do MP4 (ex.: asset temporario de GitHub Release) para publicar. "
                "Encerrando com codigo 0 sem interromper a pipeline.",
                flush=True,
            )
            return 0

        if not public_video_url.startswith(("https://", "http://")):
            print(
                "ERRO Estacao 5B: PUBLIC_VIDEO_URL invalida (precisa iniciar com https:// ou http://).",
                file=sys.stderr,
                flush=True,
            )
            return 1

    cenas_path = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    video_local = descobrir_video_completo(PASTA_OUTPUT)
    video_id_num = extrair_numero_short(video_local) if video_local else None
    meta = carregar_metadados_cenas(video_id=video_id_num, cenas_path=cenas_path)
    legenda = montar_legenda_reels(meta)

    print(
        f"Estacao 5B (Instagram Reels): api={graph_base_url}/{api_version} | "
        f"ig_user_id={'configurado' if ig_user_id else 'ausente'} | "
        f"video_url={public_video_url or '(nao informada)'}",
        flush=True,
    )
    print(f"  Legenda ({len(legenda)}/{LIMITE_LEGENDA_IG} chars):\n{legenda}", flush=True)

    if args.dry_run:
        print("[DRY-RUN] Publicacao Instagram Reels simulada com sucesso (nenhuma chamada feita a Meta Graph API).", flush=True)
        return 0

    try:
        resultado = enviar_para_instagram(
            ig_user_id=ig_user_id,
            access_token=ig_access_token,
            video_url=public_video_url,
            caption=legenda,
            api_version=api_version,
            graph_base_url=graph_base_url,
        )
    except RuntimeError as exc:
        print(f"ERRO Estacao 5B: {exc}", file=sys.stderr, flush=True)
        return 1

    destino = args.saida_url if args.saida_url.is_absolute() else (RAIZ / args.saida_url)
    registro = resultado["permalink"] or f"instagram_media_id:{resultado['media_id']}"
    salvar_url_instagram(registro, destino=destino)

    print(
        f"Instagram Reels publicado com sucesso: media_id={resultado['media_id']}"
        + (f" | permalink={resultado['permalink']}" if resultado["permalink"] else ""),
        flush=True,
    )
    print(f"Registro salvo em: {destino}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
