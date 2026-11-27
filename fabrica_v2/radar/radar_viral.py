#!/usr/bin/env python3
"""
Radar Viral YouTube (Fabrica V2)
Motor reutilizavel de varredura ao vivo de YouTube Shorts (EN/ES/PT) sem cache obsoleto.

Recursos:
- Busca ao vivo multi-idioma em YouTube Shorts via filtro nativo (sp=EgIQCQ== / EgQIBRAJ / EgQIBBAJ)
- Rotacao dinamica de queries quando --tema nao e informado (descoberta continua)
- Expansao automatica EN/ES/PT quando --tema "<assunto>" e informado
- Enriquecimento concorrente via yt-dlp (views, inscritos, likes, comentarios, data, duracao)
- Outlier Score (views_per_day, outlier_ratio, taxa de engajamento)
- Extracao de transcricao real dos primeiros 15s (gancho falado) para os top outliers
- Modo --analisar-url: metadados completos + transcricao 0-15s + 4 frames (0.5s, 1.5s, 3.0s, 5.0s)
- Deduplicacao automatica contra fabrica_v2/episodios/*/roteiro.json
- Saidas limpas em fabrica_v2/radar/output/: radar_dados.json, radar_resumo.md, relatorio_viral.html
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import glob
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:
    print(
        "ERRO: pacote 'yt-dlp' nao encontrado. Instale com: pip install -U yt-dlp",
        file=sys.stderr,
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[2]
EPISODIOS_DIR = REPO_ROOT / "fabrica_v2" / "episodios"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "fabrica_v2" / "radar" / "output"
FRAMES_DIR = Path("/tmp/radar_frames")

# Pool rotativo multi-idioma focado no formato do canal (What If / E Se / Stickman / Curiosidades)
ROTATING_QUERY_POOL: list[tuple[str, str]] = [
    # Ingles (EN)
    ("en", "what if you doubled every day"),
    ("en", "what if every day animation"),
    ("en", "what if stickman animation"),
    ("en", "what happens if you for 30 days"),
    ("en", "what if you never slept animation"),
    ("en", "what if gravity stopped animation"),
    ("en", "what if you had superpower every day"),
    ("en", "what if you survived 100 days animation"),
    ("en", "what if you ate only animation"),
    ("en", "what if human body animation"),
    ("en", "what if time froze animation"),
    ("en", "what if you became invisible"),
    ("en", "weird science facts animation"),
    ("en", "survival rules you didnt know animation"),
    # Portugues (PT)
    ("pt", "e se voce todo dia animacao"),
    ("pt", "e se voce acontecesse curiosidade"),
    ("pt", "e se o mundo parasse animacao"),
    ("pt", "o que aconteceria se voce 30 dias"),
    ("pt", "curiosidades bizarras corpo humano animacao"),
    ("pt", "e se voce ficasse preso animacao"),
    ("pt", "fatos psicologicos curiosos animacao"),
    ("pt", "stickman e se animacao"),
    # Espanhol (ES)
    ("es", "que pasaria si cada dia animacion"),
    ("es", "que pasaria si cuerpo humano"),
    ("es", "que pasaria si sobrevivieras animacion"),
    ("es", "curiosidades animacion stickman"),
    ("es", "que pasaria si el tiempo se detuviera"),
    ("es", "que pasaria si nunca durmieras"),
]

# Mapa leve PT -> (EN, ES) para expandir buscas quando --tema vem em portugues
TEMA_TRANSLATIONS: dict[str, tuple[str, str]] = {
    "dinheiro": ("money", "dinero"),
    "riqueza": ("money rich", "dinero riqueza"),
    "moeda": ("coin money", "moneda dinero"),
    "velocidade": ("speed", "velocidad"),
    "correr": ("running speed", "correr velocidad"),
    "forca": ("strength", "fuerza"),
    "forte": ("stronger", "mas fuerte"),
    "encolher": ("shrink", "encoger"),
    "gigante": ("giant grow", "gigante crecer"),
    "altura": ("height taller", "altura crecer"),
    "tempo": ("time", "tiempo"),
    "parar": ("stop freeze", "detener"),
    "gravidade": ("gravity", "gravedad"),
    "sono": ("sleep", "sueno dormir"),
    "dormir": ("sleep", "dormir"),
    "agua": ("water", "agua"),
    "oceano": ("ocean deep sea", "oceano"),
    "espaco": ("space", "espacio"),
    "invisivel": ("invisible", "invisible"),
    "mente": ("mind brain", "mente cerebro"),
    "cerebro": ("brain", "cerebro"),
    "memoria": ("memory", "memoria"),
    "dor": ("pain", "dolor"),
    "frio": ("cold freezing", "frio congelado"),
    "calor": ("heat", "calor"),
    "sol": ("sun", "sol"),
    "lua": ("moon", "luna"),
    "terra": ("earth", "tierra"),
    "sobrevivencia": ("survival", "supervivencia"),
    "sobrenatural": ("supernatural", "sobrenatural"),
    "sorte": ("luck", "suerte"),
    "idade": ("aging age", "envejecer edad"),
    "imortal": ("immortal", "inmortal"),
    "voar": ("flying", "volar"),
    "respirar": ("breathing oxygen", "respirar oxigeno"),
    "oxigenio": ("oxygen", "oxigeno"),
    "comida": ("food eating", "comida comer"),
    "cafe": ("coffee caffeine", "cafe"),
    "acucar": ("sugar", "azucar"),
    "celular": ("phone", "celular"),
    "internet": ("internet", "internet"),
    "energia": ("energy electricity", "energia electricidad"),
    "apagao": ("blackout power outage", "apagon"),
    "silencio": ("silence", "silencio"),
    "escuro": ("darkness", "oscuridad"),
    "sozinho": ("alone last person", "solo ultima persona"),
    "stickman": ("stickman", "stickman"),
}

# Conceitos semanticos para melhorar deteccao de temas ja produzidos mesmo em EN/ES
CONCEPT_SYNONYMS: dict[str, set[str]] = {
    "velocidade": {"velocidade", "speed", "faster", "fast", "velocidad", "rapido", "correr"},
    "encolher": {"encolher", "encolhesse", "shrink", "shrinking", "encoger", "encogieras", "metade", "half", "tiny"},
    "forca": {"forca", "strength", "strong", "stronger", "fuerza", "fuerte"},
    "dinheiro": {"dinheiro", "real", "reais", "money", "dollar", "penny", "cent", "dinero", "dolar", "centavo"},
}

STOPWORDS: set[str] = {
    "a", "as", "o", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "um", "uma", "por", "para", "com", "sem", "se", "que", "voce",
    "seu", "sua", "todo", "toda", "dia", "dias", "hoje", "pela", "pelo", "mais",
    "the", "and", "for", "you", "your", "what", "if", "every", "day", "days",
    "with", "without", "this", "that", "from", "into", "happens", "would",
    "shorts", "short", "viral", "animation", "animacao", "animacion", "video",
    "que", "pasaria", "si", "cada", "para", "como", "los", "las", "del", "una",
    "uno", "con", "por", "sobre", "toda", "todos", "part", "parte",
}

ACCEPT_LANG_BY_CODE = {
    "en": "en-US,en;q=0.9",
    "pt": "pt-BR,pt;q=0.9",
    "es": "es-ES,es;q=0.9",
}

# Filtros nativos de Shorts do YouTube Search (protobuf sp)
SP_SHORTS_RELEVANCE = "EgIQCQ%3D%3D"  # Tipo: Shorts
SP_SHORTS_YEAR = "EgQIBRAJ"          # Upload: Este ano + Tipo: Shorts
SP_SHORTS_MONTH = "EgQIBBAJ"         # Upload: Este mes + Tipo: Shorts


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    norm = normalize_text(text)
    return {w for w in norm.split() if len(w) >= 3 and w not in STOPWORDS}


def strip_emoji_and_dashes(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    cleaned = re.sub(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE0F\u200D]",
        "",
        text,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_short_views(text: str) -> int:
    """Converte strings como '233K views', '698 mil visualizacoes', '2,7 M' em inteiro aproximado."""
    if not text:
        return 0
    s = normalize_text(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(b|bi|bilhao|bilhoes|m|mi|milhao|milhoes|k|mil)?", s)
    if not m:
        return 0
    num_str = m.group(1)
    unit = m.group(2) or ""
    if "," in num_str and "." in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts[-1]) == 3 and not unit:
            num_str = num_str.replace(",", "")
        else:
            num_str = num_str.replace(",", ".")
    elif "." in num_str:
        parts = num_str.split(".")
        if len(parts[-1]) == 3 and not unit:
            num_str = num_str.replace(".", "")
    try:
        val = float(num_str)
    except ValueError:
        return 0
    if unit in {"b", "bi", "bilhao", "bilhoes"}:
        val *= 1_000_000_000
    elif unit in {"m", "mi", "milhao", "milhoes"}:
        val *= 1_000_000
    elif unit in {"k", "mil"}:
        val *= 1_000
    return int(val)


def load_existing_episodes() -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    if not EPISODIOS_DIR.is_dir():
        return episodes
    for path_str in sorted(glob.glob(str(EPISODIOS_DIR / "*" / "roteiro.json"))):
        path = Path(path_str)
        ep_slug = path.parent.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        titulo = data.get("titulo") or data.get("youtube", {}).get("titulo") or ep_slug
        hook = ""
        for seg in data.get("segmentos", []):
            if seg.get("id") == "hook":
                hook = seg.get("fala") or seg.get("texto") or ""
                break
        slug_part = re.sub(r"^ep\d+_", "", ep_slug.lower())
        tokens = tokenize(f"{slug_part} {titulo} {hook}")
        # Expande sinonimos EN/ES se o episodio bater com um conceito conhecido
        concept_hits: set[str] = set()
        for concept, syns in CONCEPT_SYNONYMS.items():
            if concept in slug_part or (tokens & syns):
                concept_hits.add(concept)
                tokens |= syns
        episodes.append(
            {
                "ep_id": ep_slug,
                "titulo": strip_emoji_and_dashes(titulo),
                "hook": strip_emoji_and_dashes(hook),
                "slug_core": slug_part,
                "tokens": tokens,
                "concepts": concept_hits,
            }
        )
    return episodes


def check_duplicate_episode(
    title: str, transcript: str, episodes: list[dict[str, Any]]
) -> tuple[bool, str | None, str]:
    """Detecta se o tema do video coincide com algum episodio ja produzido na fabrica_v2."""
    cand_tokens = tokenize(f"{title} {transcript}")
    if not cand_tokens:
        return False, None, ""
    double_markers = {"double", "doubled", "doubling", "dobra", "dobrasse", "duplica", "duplicara", "twice", "metade", "half"}
    has_double = bool(cand_tokens & double_markers)

    best_ep = None
    best_score = 0.0
    best_reason = ""
    for ep in episodes:
        overlap = cand_tokens & ep["tokens"]
        # Match forte por conceito + dinamica de escala ("dobrar/encolher todo dia")
        concept_match = False
        for c in ep["concepts"]:
            if cand_tokens & CONCEPT_SYNONYMS.get(c, set()):
                concept_match = True
                break
        score = len(overlap) / max(min(len(cand_tokens), len(ep["tokens"])), 1)
        if concept_match and (has_double or score >= 0.25 or ep["slug_core"] in cand_tokens):
            reason = f"conceito similar a {ep['ep_id']} ({ep['titulo']})"
            return True, ep["ep_id"], reason
        if len(overlap) >= 3 and score >= 0.35 and score > best_score:
            best_score = score
            best_ep = ep["ep_id"]
            best_reason = f"sobreposicao de tema com {ep['ep_id']} ({ep['titulo']})"
    if best_ep:
        return True, best_ep, best_reason
    return False, None, ""


def build_queries(tema: str | None, num_queries: int, seed: int | None) -> list[tuple[str, str]]:
    if tema and tema.strip():
        clean = tema.strip()
        words = normalize_text(clean).split()
        en_parts: list[str] = []
        es_parts: list[str] = []
        for w in words:
            if w in TEMA_TRANSLATIONS:
                en_parts.append(TEMA_TRANSLATIONS[w][0])
                es_parts.append(TEMA_TRANSLATIONS[w][1])
            elif w not in STOPWORDS:
                en_parts.append(w)
                es_parts.append(w)
        en_topic = " ".join(en_parts).strip() or clean
        es_topic = " ".join(es_parts).strip() or clean
        queries = [
            ("en", f"what if {en_topic}"),
            ("en", f"{en_topic} animation"),
            ("en", f"what happens if {en_topic}"),
            ("pt", f"e se {clean}"),
            ("pt", f"{clean} curiosidade animacao"),
            ("es", f"que pasaria si {es_topic}"),
        ]
        # Deduplica mantendo ordem
        dedup: list[tuple[str, str]] = []
        seen: set[str] = set()
        for lang, q in queries:
            key = f"{lang}:{normalize_text(q)}"
            if key not in seen:
                seen.add(key)
                dedup.append((lang, q))
        return dedup[: max(num_queries, 3)]

    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    en_pool = [q for q in ROTATING_QUERY_POOL if q[0] == "en"]
    pt_pool = [q for q in ROTATING_QUERY_POOL if q[0] == "pt"]
    es_pool = [q for q in ROTATING_QUERY_POOL if q[0] == "es"]
    rng.shuffle(en_pool)
    rng.shuffle(pt_pool)
    rng.shuffle(es_pool)

    # Mix equilibrado EN + PT + ES para descobrir novos outliers a cada execucao
    n_en = max(2, math.ceil(num_queries * 0.5))
    n_pt = max(1, math.floor(num_queries * 0.34))
    n_es = max(1, num_queries - n_en - n_pt)
    picked = en_pool[:n_en] + pt_pool[:n_pt] + es_pool[:n_es]
    return picked[:num_queries]


def choose_sp_filter(dias: int, index: int) -> str:
    if dias <= 31:
        return SP_SHORTS_MONTH
    if dias <= 365:
        # Alterna entre Shorts deste ano e relevancia geral de Shorts para equilibrar frescor e volume
        return SP_SHORTS_YEAR if index % 2 == 0 else SP_SHORTS_RELEVANCE
    return SP_SHORTS_RELEVANCE


def search_youtube_shorts_live(
    lang: str, query: str, sp: str, max_results: int
) -> list[dict[str, Any]]:
    """Busca ao vivo no YouTube Search com filtro nativo de Shorts e extrai candidatos com views."""
    url = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote(query)
        + "&sp="
        + sp
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": ACCEPT_LANG_BY_CODE.get(lang, "en-US,en;q=0.9"),
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        html_body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return []

    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html_body)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []

    found: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "shortsLockupViewModel" in node:
                s = node["shortsLockupViewModel"]
                vid = (
                    s.get("onTap", {})
                    .get("innertubeCommand", {})
                    .get("reelWatchEndpoint", {})
                    .get("videoId")
                )
                title = (
                    s.get("overlayMetadata", {})
                    .get("primaryText", {})
                    .get("content", "")
                )
                views_txt = (
                    s.get("overlayMetadata", {})
                    .get("secondaryText", {})
                    .get("content", "")
                )
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    found.append(
                        {
                            "id": vid,
                            "title_preview": title,
                            "views_preview": parse_short_views(views_txt),
                            "lang_query": lang,
                            "query": query,
                        }
                    )
            elif "videoRenderer" in node:
                v = node["videoRenderer"]
                vid = v.get("videoId")
                title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs", []))
                views_txt = (
                    v.get("viewCountText", {}).get("simpleText", "")
                    or v.get("shortViewCountText", {}).get("simpleText", "")
                )
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    found.append(
                        {
                            "id": vid,
                            "title_preview": title,
                            "views_preview": parse_short_views(views_txt),
                            "lang_query": lang,
                            "query": query,
                        }
                    )
            for val in node.values():
                walk(val)
        elif isinstance(node, list):
            for val in node:
                walk(val)

    walk(data)
    # Prioriza os videos com mais views dentro da pagina de resultados de Shorts
    found.sort(key=lambda x: x["views_preview"], reverse=True)
    return found[:max_results]


def fetch_video_metadata(video_id: str) -> dict[str, Any] | None:
    url = f"https://www.youtube.com/shorts/{video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
    except Exception:
        return None


def pick_best_caption_track(info: dict[str, Any]) -> tuple[str, str] | None:
    """Retorna (modo, idioma) onde modo e 'manual' ou 'auto', escolhendo apenas 1 trilha original."""
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    preferred = ["pt-BR", "pt", "pt-orig", "en", "en-US", "en-orig", "es", "es-419", "es-orig"]
    for lang in preferred:
        if lang in subs:
            return ("manual", lang)
    for lang in preferred:
        if lang in auto and lang.endswith("-orig"):
            return ("auto", lang)
    for lang in auto:
        if lang.endswith("-orig"):
            return ("auto", lang)
    for lang in ["pt", "en", "es"]:
        if lang in auto:
            return ("auto", lang)
    return None


def parse_vtt_opening(vtt_text: str, max_seconds: float = 15.0) -> str:
    lines = vtt_text.splitlines()
    chunks: list[str] = []
    include = False
    ts_re = re.compile(r"(\d+):(\d+):(\d+(?:\.\d+)?)\s*-->")
    for line in lines:
        m = ts_re.search(line)
        if m:
            sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            include = sec <= max_seconds
            continue
        if include:
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and not clean.startswith("WEBVTT") and not clean.isdigit():
                if not chunks or chunks[-1] != clean:
                    chunks.append(clean)
    return strip_emoji_and_dashes(" ".join(chunks))


def extract_opening_transcript(
    video_id: str, info: dict[str, Any], max_seconds: float = 15.0
) -> tuple[str, str]:
    """Baixa apenas 1 trilha de legenda via yt-dlp e extrai os primeiros max_seconds segundos."""
    picked = pick_best_caption_track(info)
    if not picked:
        return "", ""
    mode, lang = picked
    url = f"https://www.youtube.com/shorts/{video_id}"
    with tempfile.TemporaryDirectory(prefix="radar_sub_") as tmpdir:
        out_tmpl = os.path.join(tmpdir, "sub")
        cmd = [
            "yt-dlp",
            "-q",
            "--no-warnings",
            "--skip-download",
            "--sub-langs",
            lang,
            "--sub-format",
            "json3/vtt/best",
            "-o",
            out_tmpl,
            url,
        ]
        if mode == "manual":
            cmd.insert(4, "--write-sub")
        else:
            cmd.insert(4, "--write-auto-sub")
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except Exception:
            return "", lang

        json3_files = glob.glob(os.path.join(tmpdir, "*.json3"))
        if json3_files:
            try:
                data = json.loads(Path(json3_files[0]).read_text(encoding="utf-8", errors="ignore"))
                segs: list[str] = []
                limit_ms = int(max_seconds * 1000)
                for ev in data.get("events", []):
                    if (ev.get("tStartMs") or 0) <= limit_ms:
                        txt = "".join((s.get("utf8") or "") for s in ev.get("segs", []))
                        txt = txt.replace("\n", " ").strip()
                        if txt:
                            segs.append(txt)
                text = strip_emoji_and_dashes(" ".join(segs))
                if text:
                    return text, lang
            except Exception:
                pass

        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if vtt_files:
            try:
                raw = Path(vtt_files[0]).read_text(encoding="utf-8", errors="ignore")
                text = parse_vtt_opening(raw, max_seconds=max_seconds)
                if text:
                    return text, lang
            except Exception:
                pass
    return "", lang


def compute_metrics(info: dict[str, Any], today: dt.date) -> dict[str, Any]:
    views = int(info.get("view_count") or 0)
    likes = int(info.get("like_count") or 0)
    comments = int(info.get("comment_count") or 0)
    subs = int(info.get("channel_follower_count") or 0)
    duration = int(info.get("duration") or 0)

    upload_raw = str(info.get("upload_date") or "")
    upload_iso = ""
    days_since = 30
    if len(upload_raw) == 8 and upload_raw.isdigit():
        try:
            pub_date = dt.date(int(upload_raw[:4]), int(upload_raw[4:6]), int(upload_raw[6:8]))
            upload_iso = pub_date.isoformat()
            days_since = max((today - pub_date).days, 1)
        except ValueError:
            pass

    views_per_day = round(views / max(days_since, 1), 1)
    outlier_ratio = round(views / max(subs, 1000), 2)
    engagement_points = likes + comments * 5
    engagement_rate = round(engagement_points / max(views, 1), 5)

    # Score composto balanceando velocidade (views/dia), poder de outlier e engajamento
    velocity_term = math.log10(views_per_day + 10.0) * 20.0
    outlier_term = math.log10(outlier_ratio + 1.0) * 35.0
    engagement_term = min(engagement_rate * 400.0, 25.0)
    volume_bonus = math.log10(views + 10.0) * 5.0
    viral_score = round(velocity_term + outlier_term + engagement_term + volume_bonus, 2)

    vid = info.get("id") or ""
    shorts_url = f"https://www.youtube.com/shorts/{vid}" if vid else (info.get("webpage_url") or "")
    thumb = info.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "")

    return {
        "id": vid,
        "titulo": strip_emoji_and_dashes(info.get("title") or ""),
        "canal": strip_emoji_and_dashes(info.get("channel") or info.get("uploader") or ""),
        "url": shorts_url,
        "thumbnail": thumb,
        "duracao_s": duration,
        "upload_date": upload_iso,
        "dias_no_ar": days_since,
        "views": views,
        "inscritos": subs,
        "likes": likes,
        "comentarios": comments,
        "views_por_dia": views_per_day,
        "outlier_ratio": outlier_ratio,
        "engajamento_pontos": engagement_points,
        "engajamento_taxa": engagement_rate,
        "viral_score": viral_score,
    }


def extract_frames_for_url(
    url: str, info: dict[str, Any], out_dir: Path, timestamps: list[float]
) -> dict[str, Any]:
    """
    Extrai 4 frames-chave (0.5s, 1.5s, 3.0s, 5.0s) em /tmp/radar_frames/.
    Tenta primeiro download direto via yt-dlp + ffmpeg; se bloqueado (403 em datacenter),
    recorta automaticamente os quadros equivalentes do storyboard oficial (i.ytimg.com)
    e baixa a thumbnail HD.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):
        old.unlink(missing_ok=True)
    for old in out_dir.glob("thumbnail_*.jpg"):
        old.unlink(missing_ok=True)
    for old in out_dir.glob("storyboard_*.jpg"):
        old.unlink(missing_ok=True)

    duration = float(info.get("duration") or 10.0)
    safe_ts = [min(t, max(duration - 0.2, 0.1)) for t in timestamps]
    extracted: list[str] = []
    source_mode = "yt-dlp+ffmpeg"

    # Sempre salva a thumbnail HD como referencia complementar
    thumb_url = info.get("thumbnail") or f"https://i.ytimg.com/vi/{info.get('id', '')}/hqdefault.jpg"
    thumb_path = out_dir / "thumbnail_hd.jpg"
    try:
        urllib.request.urlretrieve(thumb_url, str(thumb_path))
    except Exception:
        thumb_path = None

    with tempfile.TemporaryDirectory(prefix="radar_vid_") as tmpdir:
        vid_path = os.path.join(tmpdir, "short.mp4")
        dl_cmd = [
            "yt-dlp",
            "-q",
            "--no-warnings",
            "-f",
            "bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
            "-o",
            vid_path,
            "--force-overwrites",
            url,
        ]
        dl_ok = False
        try:
            r = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=35)
            dl_ok = r.returncode == 0 and os.path.exists(vid_path) and os.path.getsize(vid_path) > 10_000
        except Exception:
            dl_ok = False

        if dl_ok:
            for orig_t, t in zip(timestamps, safe_ts):
                frame_file = out_dir / f"frame_{orig_t:.1f}s.jpg"
                r_ff = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "error",
                        "-ss",
                        f"{t:.2f}",
                        "-i",
                        vid_path,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        str(frame_file),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r_ff.returncode == 0 and frame_file.exists():
                    extracted.append(str(frame_file))

    if len(extracted) == len(timestamps):
        return {
            "modo": source_mode,
            "frames": extracted,
            "thumbnail_hd": str(thumb_path) if thumb_path and thumb_path.exists() else "",
        }

    # Fallback automatico via storyboard oficial do YouTube (i.ytimg.com) + ffmpeg crop
    source_mode = "storyboard_fallback+ffmpeg"
    extracted = []
    sbs = [
        f
        for f in (info.get("formats") or [])
        if f.get("ext") == "mhtml" and f.get("fragments")
    ]
    sbs.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), reverse=True)
    if sbs:
        best = sbs[0]
        cell_w = int(best.get("width") or 50)
        cell_h = int(best.get("height") or 90)
        cols = int(best.get("columns") or 5)
        rows = int(best.get("rows") or 5)
        frag0 = best["fragments"][0]
        frag_dur = float(frag0.get("duration") or max(duration, 10.0))
        cells_per_sheet = max(cols * rows, 1)
        sec_per_cell = frag_dur / cells_per_sheet
        sb_path = out_dir / "storyboard_grid.jpg"
        try:
            urllib.request.urlretrieve(frag0["url"], str(sb_path))
            for orig_t, t in zip(timestamps, safe_ts):
                idx = min(int(round(t / max(sec_per_cell, 0.1))), cells_per_sheet - 1)
                row = idx // cols
                col = idx % cols
                x = col * cell_w
                y = row * cell_h
                frame_file = out_dir / f"frame_{orig_t:.1f}s.jpg"
                vf = f"crop={cell_w}:{cell_h}:{x}:{y},scale={cell_w * 4}:{cell_h * 4}:flags=lanczos"
                r_ff = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "error",
                        "-i",
                        str(sb_path),
                        "-vf",
                        vf,
                        "-q:v",
                        "2",
                        str(frame_file),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r_ff.returncode == 0 and frame_file.exists():
                    extracted.append(str(frame_file))
        except Exception:
            pass

    return {
        "modo": source_mode,
        "frames": extracted,
        "thumbnail_hd": str(thumb_path) if thumb_path and thumb_path.exists() else "",
    }


def fmt_int(n: int | float) -> str:
    val = int(round(n))
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(val)


def write_markdown_report(payload: dict[str, Any], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Radar Viral YouTube: Varredura ao Vivo")
    lines.append("")
    lines.append(f"- Gerado em: `{payload['gerado_em']}`")
    lines.append(f"- Tema: `{payload['tema'] or 'Rotacao multi-idioma (What If / E Se / Stickman / Curiosidades)'}`")
    lines.append(f"- Janela alvo: ultimos `{payload['dias']}` dias")
    lines.append(f"- Queries executadas ({len(payload['queries'])}): " + ", ".join(f"`[{l}] {q}`" for l, q in payload["queries"]))
    lines.append(f"- Candidatos avaliados: `{payload['total_candidatos_avaliados']}` | Outliers ranqueados: `{len(payload['outliers'])}`")
    lines.append("")

    if payload["episodios_existentes"]:
        lines.append("## Episodios ja produzidos na Fabrica V2 (anti-repeticao)")
        for ep in payload["episodios_existentes"]:
            lines.append(f"- `{ep['ep_id']}`: {ep['titulo']} (Gancho: \"{ep['hook']}\")")
        lines.append("")

    lines.append("## Ranking de Outliers Ao Vivo")
    lines.append("")
    lines.append("| # | Idioma | Titulo | Canal | Views | Views/Dia | Outlier | Engajamento | Status | Link |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---|---|")
    for idx, item in enumerate(payload["outliers"], 1):
        status = f"JA PRODUZIDO ({item['episodio_similar']})" if item["ja_produzido"] else "INEDITO"
        title_cell = item["titulo"].replace("|", "/")
        canal_cell = item["canal"].replace("|", "/")
        eng_pct = f"{item['engajamento_taxa'] * 100:.2f}%"
        lines.append(
            f"| {idx} | {item['idioma_busca'].upper()} | {title_cell} | {canal_cell} "
            f"| {fmt_int(item['views'])} | {fmt_int(item['views_por_dia'])}/d "
            f"| {item['outlier_ratio']:.2f}x | {eng_pct} | {status} | [Abrir]({item['url']}) |"
        )

    lines.append("")
    lines.append("## Ganchos Reais Capturados (Primeiros 15s)")
    lines.append("")
    any_hook = False
    for idx, item in enumerate(payload["outliers"], 1):
        if item.get("gancho_transcricao"):
            any_hook = True
            lines.append(
                f"{idx}. **{item['titulo']}** (`{item['canal']}`, `{fmt_int(item['views'])}` views, `{item['outlier_ratio']:.2f}x`):"
            )
            lines.append(f"   - Legenda (`{item.get('legenda_idioma', 'auto')}`): \"{item['gancho_transcricao']}\"")
            lines.append(f"   - URL: {item['url']}")
    if not any_hook:
        lines.append("Nenhuma legenda disponivel para os videos retornados nesta rodada.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html_report(payload: dict[str, Any], out_path: Path) -> None:
    cards_html: list[str] = []
    for idx, item in enumerate(payload["outliers"], 1):
        is_dup = item["ja_produzido"]
        status_cls = "badge-dup" if is_dup else "badge-new"
        status_txt = f"JA PRODUZIDO: {item['episodio_similar']}" if is_dup else "INEDITO"
        lang_code = item["idioma_busca"].lower()
        hook_txt = item.get("gancho_transcricao") or "Sem legenda automatica capturada para os primeiros 15s."
        dup_note = (
            f"<p class=\"dup-reason\">Alerta anti-repeticao: {html.escape(item['motivo_similaridade'])}</p>"
            if is_dup and item.get("motivo_similaridade")
            else ""
        )
        cards_html.append(
            f"""
      <article class="card" data-status="{'dup' if is_dup else 'new'}" data-lang="{html.escape(lang_code)}">
        <a class="thumb-link" href="{html.escape(item['url'])}" target="_blank" rel="noopener noreferrer">
          <img src="{html.escape(item['thumbnail'])}" alt="{html.escape(item['titulo'])}" loading="lazy" />
          <span class="rank-pill">#{idx}</span>
          <span class="dur-pill">{item['duracao_s']}s</span>
        </a>
        <div class="card-body">
          <div class="badges">
            <span class="badge {status_cls}">{html.escape(status_txt)}</span>
            <span class="badge badge-lang">{html.escape(lang_code.upper())}</span>
            <span class="badge badge-score">Score {item['viral_score']:.1f}</span>
          </div>
          <h3><a href="{html.escape(item['url'])}" target="_blank" rel="noopener noreferrer">{html.escape(item['titulo'])}</a></h3>
          <p class="meta">{html.escape(item['canal'])} ({fmt_int(item['inscritos'])} inscritos) | {html.escape(item['upload_date'] or 'data indisponivel')} ({item['dias_no_ar']}d)</p>
          <div class="metrics">
            <div class="metric"><span class="m-label">Views</span><strong class="m-val">{fmt_int(item['views'])}</strong></div>
            <div class="metric"><span class="m-label">Views/Dia</span><strong class="m-val">{fmt_int(item['views_por_dia'])}</strong></div>
            <div class="metric"><span class="m-label">Outlier</span><strong class="m-val accent">{item['outlier_ratio']:.2f}x</strong></div>
            <div class="metric"><span class="m-label">Engajamento</span><strong class="m-val">{item['engajamento_taxa'] * 100:.2f}%</strong></div>
          </div>
          <div class="hook-box">
            <span class="hook-label">Gancho 0-15s ({html.escape(item.get('legenda_idioma') or 'n/a')})</span>
            <p>{html.escape(hook_txt)}</p>
          </div>
          {dup_note}
        </div>
      </article>"""
        )

    tema_label = payload["tema"] or "Rotacao multi-idioma (What If / E Se / Stickman)"
    total_new = sum(1 for x in payload["outliers"] if not x["ja_produzido"])
    top_vpd = max((x["views_por_dia"] for x in payload["outliers"]), default=0)
    top_out = max((x["outlier_ratio"] for x in payload["outliers"]), default=0.0)

    doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Radar Viral YouTube | Fabrica V2</title>
  <style>
    :root {{
      --bg: #0c0e13;
      --surface: #141821;
      --surface-2: #1b2130;
      --border: #283044;
      --text: #f1f3f8;
      --muted: #9aa6be;
      --accent: #f5b72b;
      --ok: #34d399;
      --warn: #fb7185;
      --radius: 12px;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 20px 16px 56px;
    }}
    .wrap {{ max-width: 1240px; margin: 0 auto; }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--accent);
      font-weight: 700;
    }}
    h1 {{
      margin: 6px 0 8px;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1.1;
      letter-spacing: -0.02em;
    }}
    .subtitle {{ margin: 0; color: var(--muted); font-size: 15px; }}
    .summary-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin: 20px 0 24px;
    }}
    .stat-tile {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
    }}
    .stat-tile span {{ display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; }}
    .stat-tile strong {{ display: block; font-size: 24px; margin-top: 4px; color: var(--text); }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 20px;
    }}
    .pill-btn {{
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      min-height: 38px;
    }}
    .pill-btn:hover {{ border-color: var(--accent); }}
    .pill-btn:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .pill-btn[aria-pressed="true"] {{
      background: var(--accent);
      color: #0c0e13;
      border-color: var(--accent);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }}
    @media (min-width: 720px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (min-width: 1080px) {{ .grid {{ grid-template-columns: repeat(3, 1fr); }} }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .thumb-link {{
      position: relative;
      display: block;
      aspect-ratio: 16 / 9;
      background: #080a0f;
      overflow: hidden;
    }}
    .thumb-link img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .rank-pill, .dur-pill {{
      position: absolute;
      top: 10px;
      padding: 4px 9px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      background: rgba(12, 14, 19, 0.88);
      border: 1px solid var(--border);
      color: var(--text);
    }}
    .rank-pill {{ left: 10px; color: var(--accent); }}
    .dur-pill {{ right: 10px; }}
    .card-body {{ padding: 16px; display: flex; flex-direction: column; gap: 10px; flex: 1; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .badge {{
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      border: 1px solid var(--border);
      letter-spacing: 0.03em;
    }}
    .badge-new {{ color: var(--ok); background: rgba(52, 211, 153, 0.12); border-color: rgba(52, 211, 153, 0.35); }}
    .badge-dup {{ color: var(--warn); background: rgba(251, 113, 133, 0.12); border-color: rgba(251, 113, 133, 0.35); }}
    .badge-lang {{ color: var(--text); background: var(--surface-2); }}
    .badge-score {{ color: var(--accent); background: rgba(245, 183, 43, 0.10); border-color: rgba(245, 183, 43, 0.35); }}
    h3 {{ margin: 0; font-size: 16px; line-height: 1.3; }}
    h3 a {{ color: var(--text); text-decoration: none; }}
    h3 a:hover {{ color: var(--accent); text-decoration: underline; }}
    .meta {{ margin: 0; font-size: 13px; color: var(--muted); }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
    }}
    .m-label {{ display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; }}
    .m-val {{ font-size: 15px; color: var(--text); }}
    .m-val.accent {{ color: var(--accent); }}
    .hook-box {{
      background: #10141d;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: auto;
    }}
    .hook-label {{
      display: block;
      font-size: 11px;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .hook-box p {{ margin: 0; font-size: 13px; color: #dce2ee; }}
    .dup-reason {{ margin: 0; font-size: 12px; color: var(--warn); font-weight: 600; }}
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="eyebrow">Fabrica V2 | Radar Viral YouTube Ao Vivo</div>
      <h1>{html.escape(tema_label)}</h1>
      <p class="subtitle">Varredura em tempo real executada em {html.escape(payload['gerado_em'])} | Janela: {payload['dias']} dias | {len(payload['outliers'])} outliers ranqueados</p>
    </header>

    <section class="summary-bar" aria-label="Resumo da varredura">
      <div class="stat-tile"><span>Outliers Ranqueados</span><strong>{len(payload['outliers'])}</strong></div>
      <div class="stat-tile"><span>Temas Ineditos</span><strong>{total_new}</strong></div>
      <div class="stat-tile"><span>Pico Views/Dia</span><strong>{fmt_int(top_vpd)}/d</strong></div>
      <div class="stat-tile"><span>Maior Outlier Ratio</span><strong>{top_out:.2f}x</strong></div>
    </section>

    <nav class="controls" aria-label="Filtros">
      <button type="button" class="pill-btn" data-filter="all" aria-pressed="true">Todos ({len(payload['outliers'])})</button>
      <button type="button" class="pill-btn" data-filter="new" aria-pressed="false">Somente Ineditos ({total_new})</button>
      <button type="button" class="pill-btn" data-filter="en" aria-pressed="false">EN</button>
      <button type="button" class="pill-btn" data-filter="pt" aria-pressed="false">PT</button>
      <button type="button" class="pill-btn" data-filter="es" aria-pressed="false">ES</button>
    </nav>

    <main class="grid" id="cards">
      {"".join(cards_html)}
    </main>
  </div>
  <script>
    const buttons = document.querySelectorAll(".pill-btn");
    const cards = document.querySelectorAll(".card");
    buttons.forEach((btn) => {{
      btn.addEventListener("click", () => {{
        buttons.forEach((b) => b.setAttribute("aria-pressed", "false"));
        btn.setAttribute("aria-pressed", "true");
        const f = btn.dataset.filter;
        cards.forEach((c) => {{
          const show =
            f === "all" ||
            (f === "new" && c.dataset.status === "new") ||
            c.dataset.lang === f;
          c.classList.toggle("hidden", !show);
        }});
      }});
    }});
  </script>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")


def run_single_url_analysis(url: str, output_dir: Path) -> int:
    print(f"[RADAR] Analise profunda de URL: {url}")
    today = dt.date.today()
    episodes = load_existing_episodes()

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        print(f"ERRO ao extrair metadados da URL: {exc}", file=sys.stderr)
        return 1

    metrics = compute_metrics(info, today)
    transcript, sub_lang = extract_opening_transcript(metrics["id"], info, max_seconds=15.0)
    is_dup, ep_match, dup_reason = check_duplicate_episode(metrics["titulo"], transcript, episodes)

    timestamps = [0.5, 1.5, 3.0, 5.0]
    frames_info = extract_frames_for_url(url, info, FRAMES_DIR, timestamps)

    result = {
        "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "modo": "analisar_url",
        **metrics,
        "descricao_resumo": strip_emoji_and_dashes((info.get("description") or "")[:400]),
        "gancho_transcricao": transcript,
        "legenda_idioma": sub_lang,
        "ja_produzido": is_dup,
        "episodio_similar": ep_match,
        "motivo_similaridade": dup_reason,
        "frames_extracao": frames_info,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "analise_url.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "analise_url.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Titulo: {result['titulo']}")
    print(f"Canal: {result['canal']} ({fmt_int(result['inscritos'])} inscritos)")
    print(
        f"Metricas: {fmt_int(result['views'])} views | {fmt_int(result['views_por_dia'])}/dia | "
        f"Outlier {result['outlier_ratio']:.2f}x | Engajamento {result['engajamento_taxa']*100:.2f}% | "
        f"Duracao {result['duracao_s']}s | Upload {result['upload_date']}"
    )
    print(f"Status canal: {'JA PRODUZIDO (' + str(ep_match) + ')' if is_dup else 'INEDITO'}")
    print(f"Gancho 0-15s ({sub_lang or 'n/a'}): {transcript or '(sem legenda disponivel)'}")
    print(f"Frames ({frames_info['modo']}): {frames_info['frames']}")
    if frames_info.get("thumbnail_hd"):
        print(f"Thumbnail HD: {frames_info['thumbnail_hd']}")
    return 0


def run_live_scan(args: argparse.Namespace) -> int:
    t0 = time.time()
    today = dt.date.today()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    episodes = load_existing_episodes()
    queries = build_queries(args.tema, num_queries=args.queries, seed=args.seed)
    print(
        f"[RADAR] Varredura ao vivo iniciada | queries={len(queries)} | "
        f"max_per_query={args.max_per_query} | limite={args.limite} | dias={args.dias}"
    )

    # 1. Busca paralela de candidatos Shorts no YouTube
    candidates_by_id: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries), 6)) as pool:
        future_map = {}
        for idx, (lang, q) in enumerate(queries):
            sp = choose_sp_filter(args.dias, idx)
            fut = pool.submit(search_youtube_shorts_live, lang, q, sp, args.max_per_query)
            future_map[fut] = (lang, q)
        for fut in concurrent.futures.as_completed(future_map):
            lang, q = future_map[fut]
            rows = fut.result() or []
            print(f"  -> [{lang.upper()}] '{q}': {len(rows)} shorts candidatos")
            for r in rows:
                vid = r["id"]
                if vid not in candidates_by_id or r["views_preview"] > candidates_by_id[vid]["views_preview"]:
                    candidates_by_id[vid] = r

    # Ordena candidatos pela previa de views e limita enriquecimento para manter velocidade
    cand_list = sorted(candidates_by_id.values(), key=lambda x: x["views_preview"], reverse=True)
    enrich_cap = max(args.limite * 2, len(queries) * args.max_per_query)
    enrich_cap = min(enrich_cap, 45)
    cand_list = cand_list[:enrich_cap]
    print(f"[RADAR] Enriquecendo {len(cand_list)} candidatos unicos via yt-dlp...")

    # 2. Enriquecimento concorrente via yt-dlp
    enriched: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fut_to_cand = {pool.submit(fetch_video_metadata, c["id"]): c for c in cand_list}
        for fut in concurrent.futures.as_completed(fut_to_cand):
            cand = fut_to_cand[fut]
            info = fut.result()
            if not info:
                continue
            dur = int(info.get("duration") or 0)
            if dur <= 0 or dur > args.max_duracao:
                continue
            metrics = compute_metrics(info, today)
            if metrics["views"] < args.min_views:
                continue
            enriched.append((cand, info, metrics))

    # 3. Aplica janela de dias (com fallback suave caso tema especifico tenha poucos recentes)
    in_window = [item for item in enriched if item[2]["dias_no_ar"] <= args.dias]
    used_fallback_window = False
    if len(in_window) >= min(args.limite, 5):
        selected_pool = in_window
    else:
        selected_pool = enriched
        used_fallback_window = len(enriched) > len(in_window)

    # Ordena por viral_score decrescente
    selected_pool.sort(key=lambda x: x[2]["viral_score"], reverse=True)
    top_items = selected_pool[: args.limite]

    # 4. Extracao de legenda de abertura (0-15s) para os top outliers (com cadencia segura anti-429)
    cap_limit = min(len(top_items), args.legendas_top)
    print(f"[RADAR] Extraindo gancho real (0-15s) dos top {cap_limit} outliers...")
    final_outliers: list[dict[str, Any]] = []
    for idx, (cand, info, metrics) in enumerate(top_items):
        transcript = ""
        sub_lang = ""
        if idx < cap_limit:
            transcript, sub_lang = extract_opening_transcript(metrics["id"], info, max_seconds=15.0)
            if idx + 1 < cap_limit:
                time.sleep(0.45)

        is_dup, ep_match, dup_reason = check_duplicate_episode(
            metrics["titulo"], transcript, episodes
        )
        final_outliers.append(
            {
                **metrics,
                "idioma_busca": cand["lang_query"],
                "query_origem": cand["query"],
                "fora_janela_dias": metrics["dias_no_ar"] > args.dias,
                "gancho_transcricao": transcript,
                "legenda_idioma": sub_lang,
                "ja_produzido": is_dup,
                "episodio_similar": ep_match,
                "motivo_similaridade": dup_reason,
            }
        )

    payload = {
        "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "tema": args.tema or "",
        "dias": args.dias,
        "usou_fallback_janela": used_fallback_window,
        "max_per_query": args.max_per_query,
        "limite": args.limite,
        "queries": [[l, q] for l, q in queries],
        "total_candidatos_avaliados": len(cand_list),
        "episodios_existentes": [
            {"ep_id": e["ep_id"], "titulo": e["titulo"], "hook": e["hook"]} for e in episodes
        ],
        "outliers": final_outliers,
    }

    json_path = output_dir / "radar_dados.json"
    md_path = output_dir / "radar_resumo.md"
    html_path = output_dir / "relatorio_viral.html"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(payload, md_path)
    write_html_report(payload, html_path)

    elapsed = time.time() - t0
    print(
        f"[RADAR] Concluido em {elapsed:.1f}s | outliers={len(final_outliers)} "
        f"| ineditos={sum(1 for x in final_outliers if not x['ja_produzido'])}"
    )
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"  HTML: {html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Radar Viral YouTube ao vivo para Fabrica V2 (Shorts EN/ES/PT)"
    )
    p.add_argument(
        "--tema",
        type=str,
        default=None,
        help="Tema especifico para gerar buscas multi-idioma (EN/ES/PT). Sem este flag, usa pool rotativo.",
    )
    p.add_argument(
        "--dias",
        type=int,
        default=180,
        help="Janela maxima em dias para priorizar uploads recentes (padrao: 180).",
    )
    p.add_argument(
        "--max-per-query",
        type=int,
        default=8,
        help="Maximo de candidatos Shorts coletados por query (padrao: 8).",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=15,
        help="Quantidade de outliers ranqueados na saida final (padrao: 15).",
    )
    p.add_argument(
        "--queries",
        type=int,
        default=6,
        help="Numero de queries multi-idioma por varredura (padrao: 6).",
    )
    p.add_argument(
        "--legendas-top",
        type=int,
        default=8,
        help="Quantidade de outliers no topo com extracao de transcricao 0-15s (padrao: 8).",
    )
    p.add_argument(
        "--max-duracao",
        type=int,
        default=120,
        help="Duracao maxima em segundos para considerar o video como Short (padrao: 120).",
    )
    p.add_argument(
        "--min-views",
        type=int,
        default=1000,
        help="Minimo de visualizacoes para entrar no ranking (padrao: 1000).",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente opcional apenas para testes reproduziveis (padrao: aleatoria em toda execucao).",
    )
    p.add_argument(
        "--analisar-url",
        type=str,
        default=None,
        help="URL de um unico video do YouTube para analise profunda + transcricao 0-15s + 4 frames.",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Diretorio de saida para radar_dados.json, radar_resumo.md e relatorio_viral.html.",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.analisar_url:
        return run_single_url_analysis(args.analisar_url, Path(args.output_dir))
    return run_live_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
