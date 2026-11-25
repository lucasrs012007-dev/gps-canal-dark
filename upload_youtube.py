"""Estacao 5A (Motor V6): upload automatico do Short completo para o YouTube Shorts.

Usa YouTube Data API v3 via OAuth 2.0 (refresh token) com credenciais lidas exclusivamente
de variaveis de ambiente (ou .env local em testes):
- YOUTUBE_CLIENT_ID
- YOUTUBE_CLIENT_SECRET
- YOUTUBE_REFRESH_TOKEN
- YOUTUBE_PRIVACY (padrao: public; aceita tambem unlisted ou private)

Comportamento seguro na pipeline:
- Se qualquer um dos 3 secrets obrigatorios estiver vazio, registra aviso claro no log e
  encerra com codigo 0 sem derrubar o workflow nem impedir o envio ao Telegram.
- Identifica automaticamente o video completo mais recente da rodada (`output/short_NN.mp4`),
  ignorando sempre as versoes fatiadas `_parte1` e `_parte2`.
- Monta titulo otimizado (<= 100 chars com `#Shorts`), descricao curta com gancho e hashtags
  (`#shorts #curiosidades #ese`), tags de `palavras_chave`, categoria `24` (Entertainment) e
  `selfDeclaredMadeForKids: false`.
- Imprime a URL final (`https://youtube.com/shorts/<video_id>`) e grava em `output/youtube_url.txt`.

Uso (na raiz do repositorio):
    python3 upload_youtube.py
    python3 upload_youtube.py --dry-run
    python3 upload_youtube.py --video output/short_09.mp4 --privacidade unlisted
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

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ARQUIVO_ENV = RAIZ / ".env"
PASTA_OUTPUT = RAIZ / "output"
ARQUIVO_CENAS = RAIZ / "cenas.json"
ARQUIVO_HISTORICO = RAIZ / "historico_videos.json"
ARQUIVO_URL_SAIDA = PASTA_OUTPUT / "youtube_url.txt"

YOUTUBE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_CATEGORY_ENTERTAINMENT = "24"
PRIVACIDADES_VALIDAS: tuple[str, ...] = ("public", "unlisted", "private")

LIMITE_TITULO_YT = 100
LIMITE_DESCRICAO_YT = 4500
LIMITE_CHARS_TAGS_YT = 450
CHUNK_SIZE_BYTES = 4 * 1024 * 1024
MAX_RETRIES_UPLOAD = 3
STATUS_RETENTAVEIS = (500, 502, 503, 504)

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
    limpo = str(texto or "")
    for seg in segredos:
        if seg:
            limpo = limpo.replace(seg, "***SECRET***")
    return limpo


def _limpar_texto_youtube(texto: str) -> str:
    """Remove caracteres proibidos pela API do YouTube (<, >), emojis e travessoes."""
    limpo = unicodedata.normalize("NFC", str(texto or ""))
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = limpo.replace("<", "").replace(">", "")
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


def normalizar_privacidade(valor: str | None) -> str:
    """Valida YOUTUBE_PRIVACY (padrao: public; aceita public, unlisted ou private)."""
    raw = str(valor or "").strip().lower()
    if raw in PRIVACIDADES_VALIDAS:
        return raw
    if raw:
        print(
            f"AVISO YOUTUBE_PRIVACY='{raw}' invalido (aceitos: {', '.join(PRIVACIDADES_VALIDAS)}). "
            "Usando padrao 'public'.",
            flush=True,
        )
    return "public"


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
        fala = _limpar_texto_youtube(fala)
        if fala:
            return fala[:220].rstrip()
    return ""


def carregar_metadados_video(
    video_id: int | None = None,
    cenas_path: Path = ARQUIVO_CENAS,
    historico_path: Path = ARQUIVO_HISTORICO,
    raiz: Path = RAIZ,
) -> dict:
    """Combina titulo, tema, gancho e palavras_chave a partir de cenas.json e historico_videos.json."""
    cenas = _carregar_json_seguro(cenas_path)
    historico = _carregar_json_seguro(historico_path)
    videos = historico.get("videos") if isinstance(historico.get("videos"), list) else []

    reg_hist: dict = {}
    alvo_id = video_id
    if alvo_id is None:
        cid = cenas.get("video_id")
        if isinstance(cid, int) and cid >= 1:
            alvo_id = cid
        elif isinstance(historico.get("video_atual"), int):
            alvo_id = int(historico["video_atual"])

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

    titulo = ""
    if cenas_bate and str(cenas.get("titulo", "")).strip():
        titulo = str(cenas["titulo"]).strip()
    elif str(reg_hist.get("titulo", "")).strip():
        titulo = str(reg_hist["titulo"]).strip()
    elif str(cenas.get("titulo", "")).strip():
        titulo = str(cenas["titulo"]).strip()
    else:
        titulo = f"E Se Você Passasse Por Isso? {alvo_id:02d}" if alvo_id else "E Se Você Passasse Por Isso?"

    tema = str(reg_hist.get("tema", "") or "").strip()
    gancho = _extrair_gancho_roteiro(str(reg_hist.get("roteiro", "") or ""), raiz=raiz)
    if not gancho and cenas_bate:
        lista_cenas = cenas.get("cenas") if isinstance(cenas.get("cenas"), list) else []
        if lista_cenas and isinstance(lista_cenas[0], dict):
            props0 = lista_cenas[0].get("props") if isinstance(lista_cenas[0].get("props"), dict) else {}
            gancho = _limpar_texto_youtube(str(props0.get("celular_mensagem", "") or ""))

    palavras_chave: list[str] = []
    vistas: set[str] = set()
    fontes_kw = []
    if isinstance(reg_hist.get("palavras_chave"), list):
        fontes_kw.extend(reg_hist["palavras_chave"])
    if cenas_bate and isinstance(cenas.get("palavras_vermelhas"), list):
        fontes_kw.extend(cenas["palavras_vermelhas"][:10])
    for item in fontes_kw:
        limpa = _limpar_texto_youtube(str(item))
        chave = _slug_hashtag(limpa)
        if len(chave) >= 3 and chave not in vistas:
            vistas.add(chave)
            palavras_chave.append(limpa)

    return {
        "video_id": alvo_id or reg_hist.get("id"),
        "titulo": _restaurar_acentos_se_disponivel(_limpar_texto_youtube(titulo)),
        "tema": _restaurar_acentos_se_disponivel(_limpar_texto_youtube(tema)),
        "gancho": _restaurar_acentos_se_disponivel(_limpar_texto_youtube(gancho)),
        "palavras_chave": palavras_chave,
        "pilar": str(reg_hist.get("pilar", "") or "").strip().lower(),
    }


def montar_titulo_shorts(titulo_base: str) -> str:
    """Monta titulo otimizado para YouTube Shorts (<= 100 caracteres, incluindo #Shorts)."""
    base = _limpar_texto_youtube(titulo_base) or "E Se Você Passasse Por Isso?"
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


def montar_descricao_shorts(meta: dict) -> str:
    """Monta descricao curta em portugues com gancho, CTA e hashtags (#shorts #curiosidades #ese)."""
    titulo = _limpar_texto_youtube(meta.get("titulo", ""))
    gancho = _limpar_texto_youtube(meta.get("gancho", ""))
    tema = _limpar_texto_youtube(meta.get("tema", ""))

    abertura = gancho or tema or f"{titulo}: descubra o que aconteceria em cada segundo."
    if not abertura.endswith((".", "!", "?")):
        abertura += "."

    complemento = ""
    if tema and tema.lower() != abertura.lower() and tema.lower() not in abertura.lower():
        complemento = tema if tema.endswith((".", "!", "?")) else f"{tema}."

    tags_base = ["shorts", "curiosidades", "ese"]
    extras: list[str] = []
    for kw in meta.get("palavras_chave") or []:
        slug = _slug_hashtag(str(kw))
        if len(slug) >= 3 and slug not in tags_base and slug not in extras:
            extras.append(slug)
        if len(extras) >= 4:
            break
    hashtags = " ".join(f"#{t}" for t in (tags_base + extras))

    blocos: list[str] = [abertura]
    if complemento:
        blocos.append(complemento)
    blocos.append("O que você faria nessa situação? Comente aqui embaixo!")
    blocos.append("Quer aprender a criar vídeos assim no automático? Comente EU QUERO.")
    blocos.append(hashtags)

    descricao = "\n\n".join(b for b in blocos if b).strip()
    return descricao[:LIMITE_DESCRICAO_YT]


def montar_tags_youtube(palavras_chave: list[str] | None) -> list[str]:
    """Gera lista de tags validas para o YouTube respeitando o teto de caracteres."""
    iniciais = list(palavras_chave or []) + [
        "shorts",
        "youtube shorts",
        "curiosidades",
        "e se voce",
        "cenarios hipoteticos",
    ]
    tags: list[str] = []
    vistas: set[str] = set()
    total_chars = 0

    for raw in iniciais:
        limpa = _limpar_texto_youtube(str(raw)).lstrip("#").strip(" ,;.")
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


def montar_body_youtube(meta: dict, privacidade: str) -> dict:
    """Constroi o payload snippet + status oficial para youtube.videos().insert."""
    return {
        "snippet": {
            "title": montar_titulo_shorts(meta.get("titulo", "")),
            "description": montar_descricao_shorts(meta),
            "tags": montar_tags_youtube(meta.get("palavras_chave")),
            "categoryId": YOUTUBE_CATEGORY_ENTERTAINMENT,
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": normalizar_privacidade(privacidade),
            "selfDeclaredMadeForKids": False,
        },
    }


def criar_cliente_youtube(client_id: str, client_secret: str, refresh_token: str):
    """Cria cliente autenticado da YouTube Data API v3 a partir de refresh token OAuth 2.0."""
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
    """Executa upload resumable para YouTube Shorts com retry em falhas transitorias (5xx)."""
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
                    pct = int(status.progress() * 100)
                    print(f"Upload YouTube em andamento: {pct}%", flush=True)
            except HttpError as exc:
                cod = getattr(exc.resp, "status", None)
                if cod in STATUS_RETENTAVEIS and tentativa < MAX_RETRIES_UPLOAD:
                    tentativa += 1
                    espera = 2 ** tentativa
                    print(
                        f"AVISO HTTP {cod} durante upload YouTube. Tentativa {tentativa}/{MAX_RETRIES_UPLOAD} "
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
                        f"AVISO erro de rede ({type(exc).__name__}) no upload YouTube. "
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
        raise RuntimeError(f"Falha no upload para o YouTube Shorts ({msg})") from None


def salvar_url_youtube(url: str, destino: Path = ARQUIVO_URL_SAIDA) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(url.strip() + "\n", encoding="utf-8")
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estacao 5A: publica automaticamente o video completo (output/short_NN.mp4) no YouTube Shorts."
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=None,
        help="Caminho manual do MP4 completo (padrao: output/short_NN.mp4 mais recente).",
    )
    parser.add_argument(
        "--privacidade",
        type=str,
        default=None,
        help="Sobrescreve YOUTUBE_PRIVACY (public, unlisted ou private).",
    )
    parser.add_argument(
        "--saida-url",
        type=Path,
        default=ARQUIVO_URL_SAIDA,
        help="Arquivo onde a URL final sera salva (padrao: output/youtube_url.txt).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o video selecionado e os metadados montados sem enviar ao YouTube.",
    )
    args = parser.parse_args()

    carregar_env()

    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    privacidade = normalizar_privacidade(args.privacidade or os.environ.get("YOUTUBE_PRIVACY", "public"))

    if not args.dry_run:
        faltantes = [
            nome
            for nome, val in (
                ("YOUTUBE_CLIENT_ID", client_id),
                ("YOUTUBE_CLIENT_SECRET", client_secret),
                ("YOUTUBE_REFRESH_TOKEN", refresh_token),
            )
            if not val
        ]
        if faltantes:
            print(
                f"AVISO Estacao 5A (YouTube Shorts) ignorada: secret(s) ausente(s): {', '.join(faltantes)}. "
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
                "AVISO Estacao 5A: nenhum video completo output/short_NN.mp4 encontrado em output/. "
                "Nada para enviar ao YouTube.",
                flush=True,
            )
            return 0

    video_id_num = extrair_numero_short(video_path)
    meta = carregar_metadados_video(video_id=video_id_num)
    body = montar_body_youtube(meta, privacidade=privacidade)
    tamanho_mb = video_path.stat().st_size / (1024 * 1024)

    print(
        f"Estacao 5A (YouTube Shorts): arquivo={video_path.name} ({tamanho_mb:.2f} MB) | "
        f"privacidade={body['status']['privacyStatus']} | categoria={body['snippet']['categoryId']}",
        flush=True,
    )
    print(f"  Titulo ({len(body['snippet']['title'])}/100): {body['snippet']['title']}", flush=True)
    print(f"  Tags ({len(body['snippet']['tags'])}): {', '.join(body['snippet']['tags'])}", flush=True)

    if args.dry_run:
        print(f"  Descricao:\n{body['snippet']['description']}", flush=True)
        print("[DRY-RUN] Upload simulado com sucesso (nenhuma chamada feita a YouTube Data API).", flush=True)
        return 0

    try:
        yt_video_id = enviar_para_youtube(
            video_path=video_path,
            body=body,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
    except RuntimeError as exc:
        print(f"ERRO Estacao 5A: {exc}", file=sys.stderr, flush=True)
        return 1

    url_final = f"https://youtube.com/shorts/{yt_video_id}"
    saida_url = args.saida_url if args.saida_url.is_absolute() else (RAIZ / args.saida_url)
    salvar_url_youtube(url_final, destino=saida_url)

    print(f"YouTube Shorts publicado com sucesso: {url_final}", flush=True)
    print(f"URL salva em: {saida_url}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
