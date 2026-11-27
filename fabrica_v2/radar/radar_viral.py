#!/usr/bin/env python3
"""
Radar Viral Multiplataforma (Fabrica V2 - Modo 2 Gratuito)
Varredura ao vivo sem cache obsoleto em YouTube Shorts + TikTok + Instagram Reels.

Recursos:
- --plataformas (padrao: youtube,tiktok,instagram): YouTube Shorts (yt-dlp + filtro nativo sp),
  TikTok e Instagram Reels (descoberta publica gratuita via busca web + enriquecimento leve yt-dlp)
- --tema "<assunto>": gera buscas multi-idioma (EN/ES/PT); sem tema, usa pool rotativo
- --dias, --max-per-query, --limite: controle fino sem teto fixo
- --apenas-novos + vistos.json: memoria de frescor que prioriza ou filtra itens ineditos
- --analisar-url "<url>": analise universal (YouTube, TikTok e tentativa segura em Reels)
  com metadados, 4 frames (0.5s, 1.5s, 3.0s, 5.0s) em /tmp/radar_frames/ e transcricao 0-15s
  com fallback automatico para Whisper local (faster-whisper / whisper via ffmpeg 16kHz mono)
- Deduplicacao automatica contra fabrica_v2/episodios/*/roteiro.json
- Saidas em fabrica_v2/radar/output/: vistos.json, radar_dados.json, radar_resumo.md, relatorio_viral.html
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import glob
import html
import json
import math
import os
import random
import re
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

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
}

ROTATING_QUERY_POOL: list[tuple[str, str]] = [
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
    ("pt", "e se voce todo dia animacao"),
    ("pt", "e se voce acontecesse curiosidade"),
    ("pt", "e se o mundo parasse animacao"),
    ("pt", "curiosidades bizarras corpo humano animacao"),
    ("pt", "e se voce ficasse preso animacao"),
    ("pt", "fatos psicologicos curiosos animacao"),
    ("pt", "stickman e se animacao"),
    ("es", "que pasaria si cada dia animacion"),
    ("es", "que pasaria si cuerpo humano"),
    ("es", "que pasaria si sobrevivieras animacion"),
    ("es", "curiosidades animacion stickman"),
    ("es", "que pasaria si el tiempo se detuviera"),
    ("es", "que pasaria si nunca durmieras"),
]

TEMA_TRANSLATIONS: dict[str, tuple[str, str]] = {
    "dinheiro": ("money", "dinero"),
    "riqueza": ("money rich", "dinero riqueza"),
    "velocidade": ("speed", "velocidad"),
    "forca": ("strength", "fuerza"),
    "encolher": ("shrink", "encoger"),
    "gigante": ("giant grow", "gigante crecer"),
    "tempo": ("time", "tiempo"),
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
    "sobrevivencia": ("survival", "supervivencia"),
    "idade": ("aging age", "envejecer edad"),
    "espirro": ("sneeze", "estornudo"),
    "cura": ("healing", "curacion"),
    "som": ("sound loud", "sonido fuerte"),
    "grito": ("scream loud", "grito fuerte"),
    "silencio": ("silence", "silencio"),
    "sozinho": ("alone last person", "solo ultima persona"),
    "stickman": ("stickman", "stickman"),
}

CONCEPT_SYNONYMS: dict[str, set[str]] = {
    "velocidade": {"velocidade", "speed", "velocidad", "correr", "corrida"},
    "encolher": {"encolher", "encolhesse", "shrink", "shrinking", "encoger", "encogieras", "metade"},
    "forca": {"forca", "strength", "strong", "stronger", "fuerza", "fuerte"},
    "dinheiro": {"dinheiro", "real", "reais", "money", "dollar", "penny", "cent", "dinero", "dolar"},
    "ja_to_indo": {"decibeis", "decibels", "decibelios", "grito", "gritos", "volume"},
}

STOPWORDS: set[str] = {
    "a", "as", "o", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "um", "uma", "por", "para", "com", "sem", "se", "que", "voce",
    "seu", "sua", "todo", "toda", "dia", "dias", "hoje", "pela", "pelo", "mais",
    "the", "and", "for", "you", "your", "what", "if", "every", "day", "days",
    "with", "without", "this", "that", "from", "into", "happens", "would",
    "shorts", "short", "viral", "animation", "animacao", "animacion", "video",
    "que", "pasaria", "si", "cada", "como", "los", "las", "del", "una", "uno",
    "con", "sobre", "todos", "part", "parte", "tiktok", "instagram", "reel", "reels",
}

ACCEPT_LANG_BY_CODE = {
    "en": "en-US,en;q=0.9",
    "pt": "pt-BR,pt;q=0.9",
    "es": "es-ES,es;q=0.9",
}

SP_SHORTS_RELEVANCE = "EgIQCQ%3D%3D"
SP_SHORTS_YEAR = "EgQIBRAJ"
SP_SHORTS_MONTH = "EgQIBBAJ"

_WHISPER_MODEL: Any = None


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    return {w for w in normalize_text(text).split() if len(w) >= 3 and w not in STOPWORDS}


def strip_emoji_and_dashes(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE0F\u200D]", "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def detect_platform(url: str) -> str:
    low = (url or "").lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "youtube"
    if "tiktok.com" in low:
        return "tiktok"
    if "instagram.com" in low or "instagr.am" in low:
        return "instagram"
    return "web"


def canonical_item_key(platform: str, item_id: str, url: str) -> str:
    if platform == "youtube" and item_id:
        return f"yt:{item_id}"
    if platform == "tiktok":
        m = re.search(r"/video/(\d+)", url or "")
        tid = m.group(1) if m else item_id
        if tid:
            return f"tt:{tid}"
    if platform == "instagram":
        m = re.search(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)", url or "")
        code = m.group(1) if m else item_id
        if code:
            return f"ig:{code}"
    clean = (url or "").split("?")[0].rstrip("/").lower()
    return f"{platform}:{clean or item_id}"


def load_seen_memory(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "vistos.json"
    if not path.is_file():
        return {"atualizado_em": "", "itens": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("itens"), dict):
            return data
    except Exception:
        pass
    return {"atualizado_em": "", "itens": {}}


def save_seen_memory(output_dir: Path, seen_data: dict[str, Any], surfaced: list[dict[str, Any]]) -> Path:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    itens = seen_data.setdefault("itens", {})
    for item in surfaced:
        key = canonical_item_key(item.get("plataforma", "web"), item.get("id", ""), item.get("url", ""))
        prev = itens.get(key)
        if prev:
            prev["ultima_vez"] = now
            prev["vezes"] = int(prev.get("vezes", 1)) + 1
        else:
            itens[key] = {
                "url": item.get("url", ""),
                "plataforma": item.get("plataforma", "web"),
                "titulo": strip_emoji_and_dashes(item.get("titulo", ""))[:120],
                "primeira_vez": now,
                "ultima_vez": now,
                "vezes": 1,
            }
    seen_data["atualizado_em"] = now
    path = output_dir / "vistos.json"
    path.write_text(json.dumps(seen_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_short_views(text: str) -> int:
    if not text:
        return 0
    s = normalize_text(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(b|bi|bilhao|bilhoes|m|mi|milhao|milhoes|k|mil)?", s)
    if not m:
        return 0
    num_str, unit = m.group(1), m.group(2) or ""
    if "," in num_str and "." in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        num_str = num_str.replace(",", "") if (len(num_str.split(",")[-1]) == 3 and not unit) else num_str.replace(",", ".")
    elif "." in num_str and len(num_str.split(".")[-1]) == 3 and not unit:
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
    cand_tokens = tokenize(f"{title} {transcript}")
    if not cand_tokens:
        return False, None, ""
    double_markers = {"double", "doubled", "doubling", "dobra", "dobrasse", "duplica", "twice", "metade", "half"}
    has_double = bool(cand_tokens & double_markers)

    best_ep, best_score, best_reason = None, 0.0, ""
    for ep in episodes:
        overlap = cand_tokens & ep["tokens"]
        concept_match = any(bool(cand_tokens & CONCEPT_SYNONYMS.get(c, set())) for c in ep["concepts"])
        score = len(overlap) / max(min(len(cand_tokens), len(ep["tokens"])), 1)
        if concept_match and (has_double or score >= 0.25 or ep["slug_core"] in cand_tokens):
            return True, ep["ep_id"], f"conceito similar a {ep['ep_id']} ({ep['titulo']})"
        if len(overlap) >= 3 and score >= 0.35 and score > best_score:
            best_score, best_ep = score, ep["ep_id"]
            best_reason = f"sobreposicao de tema com {ep['ep_id']} ({ep['titulo']})"
    return (True, best_ep, best_reason) if best_ep else (False, None, "")


def build_queries(tema: str | None, num_queries: int, seed: int | None) -> list[tuple[str, str]]:
    if tema and tema.strip():
        clean = tema.strip()
        words = normalize_text(clean).split()
        en_parts, es_parts = [], []
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
        dedup, seen = [], set()
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

    n_en = max(2, math.ceil(num_queries * 0.5))
    n_pt = max(1, math.floor(num_queries * 0.34))
    n_es = max(1, num_queries - n_en - n_pt)
    return (en_pool[:n_en] + pt_pool[:n_pt] + es_pool[:n_es])[:num_queries]


# --------------------------------------------------------- YouTube Shorts live
def choose_sp_filter(dias: int, index: int) -> str:
    if dias <= 31:
        return SP_SHORTS_MONTH
    if dias <= 365:
        return SP_SHORTS_YEAR if index % 2 == 0 else SP_SHORTS_RELEVANCE
    return SP_SHORTS_RELEVANCE


def search_youtube_shorts_live(lang: str, query: str, sp: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=" + sp
    headers = {**BROWSER_HEADERS, "Accept-Language": ACCEPT_LANG_BY_CODE.get(lang, "en-US,en;q=0.9")}
    try:
        html_body = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return []
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html_body)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []

    found, seen_ids = [], set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "shortsLockupViewModel" in node:
                s = node["shortsLockupViewModel"]
                vid = s.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}).get("videoId")
                title = s.get("overlayMetadata", {}).get("primaryText", {}).get("content", "")
                views_txt = s.get("overlayMetadata", {}).get("secondaryText", {}).get("content", "")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    found.append({"id": vid, "title_preview": title, "views_preview": parse_short_views(views_txt), "lang_query": lang, "query": query})
            elif "videoRenderer" in node:
                v = node["videoRenderer"]
                vid = v.get("videoId")
                title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs", []))
                views_txt = v.get("viewCountText", {}).get("simpleText", "") or v.get("shortViewCountText", {}).get("simpleText", "")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    found.append({"id": vid, "title_preview": title, "views_preview": parse_short_views(views_txt), "lang_query": lang, "query": query})
            for val in node.values():
                walk(val)
        elif isinstance(node, list):
            for val in node:
                walk(val)

    walk(data)
    found.sort(key=lambda x: x["views_preview"], reverse=True)
    return found[:max_results]


def fetch_video_metadata(video_id: str) -> dict[str, Any] | None:
    url = f"https://www.youtube.com/shorts/{video_id}"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 15}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def pick_best_caption_track(info: dict[str, Any]) -> tuple[str, str] | None:
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
    chunks, include = [], False
    ts_re = re.compile(r"(\d+):(\d+):(\d+(?:\.\d+)?)\s*-->")
    for line in vtt_text.splitlines():
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


def extract_opening_transcript(video_id: str, info: dict[str, Any], max_seconds: float = 15.0) -> tuple[str, str]:
    picked = pick_best_caption_track(info)
    if not picked:
        return "", ""
    mode, lang = picked
    url = info.get("webpage_url") or f"https://www.youtube.com/shorts/{video_id}"
    with tempfile.TemporaryDirectory(prefix="radar_sub_") as tmpdir:
        out_tmpl = os.path.join(tmpdir, "sub")
        cmd = [
            "yt-dlp", "-q", "--no-warnings", "--skip-download",
            "--write-sub" if mode == "manual" else "--write-auto-sub",
            "--sub-langs", lang, "--sub-format", "json3/vtt/best",
            "-o", out_tmpl, url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except Exception:
            return "", lang

        json3_files = glob.glob(os.path.join(tmpdir, "*.json3"))
        if json3_files:
            try:
                data = json.loads(Path(json3_files[0]).read_text(encoding="utf-8", errors="ignore"))
                segs, limit_ms = [], int(max_seconds * 1000)
                for ev in data.get("events", []):
                    if (ev.get("tStartMs") or 0) <= limit_ms:
                        txt = "".join((s.get("utf8") or "") for s in ev.get("segs", [])).replace("\n", " ").strip()
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
                text = parse_vtt_opening(Path(vtt_files[0]).read_text(encoding="utf-8", errors="ignore"), max_seconds=max_seconds)
                if text:
                    return text, lang
            except Exception:
                pass
    return "", lang


# -------------------------------------------- Modo 2: TikTok & Instagram Reels
def _http_get_text(url: str, timeout: int = 10) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except Exception:
        return 0, ""


def _parse_ddg_html(body: str) -> list[tuple[str, str]]:
    """Extrai pares (url, titulo) da pagina HTML publica do DuckDuckGo."""
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        raw_href = html.unescape(m.group(1))
        title = strip_emoji_and_dashes(html.unescape(re.sub(r"<[^>]+>", "", m.group(2))))
        uddg = re.search(r"[?&]uddg=([^&]+)", raw_href)
        url = urllib.parse.unquote(uddg.group(1)) if uddg else raw_href
        if url.startswith("http"):
            results.append((url, title))
    return results


def _parse_bing_web_html(body: str) -> list[tuple[str, str]]:
    """Extrai pares (url, titulo) de resultados publicos do Bing Web (HTTP 200)."""
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'<li class="b_algo"[^>]*>(.*?)</li>', body, re.S):
        blk = m.group(1)
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", blk, re.S)
        title = strip_emoji_and_dashes(html.unescape(re.sub(r"<[^>]+>", "", h2.group(1)))) if h2 else ""
        href_m = re.search(r'href="([^"]+)"', h2.group(1) if h2 else blk)
        link = html.unescape(href_m.group(1)) if href_m else ""
        if "bing.com/ck/a" in link:
            u_m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", link)
            if u_m:
                b64 = u_m.group(1) + "=" * (-len(u_m.group(1)) % 4)
                try:
                    link = base64.urlsafe_b64decode(b64).decode("utf-8", "ignore")
                except Exception:
                    pass
        if link.startswith("http"):
            results.append((link, title))
    return results


def _extract_bing_video_tiktok_leads(body: str, query: str, lang: str) -> list[dict[str, Any]]:
    """Extrai URLs reais tiktok.com/@user/video/ID do Bing Videos publico."""
    unq = urllib.parse.unquote(body)
    urls = list(dict.fromkeys(re.findall(r"https?://(?:www\.|m\.)?tiktok\.com/@[A-Za-z0-9_.-]+/video/\d+", unq)))
    leads: list[dict[str, Any]] = []
    for u in urls:
        clean_u = u.replace("m.tiktok.com", "www.tiktok.com").split("?")[0]
        user_m = re.search(r"tiktok\.com/(@[A-Za-z0-9_.-]+)/video/(\d+)", clean_u)
        canal = user_m.group(1) if user_m else "tiktok"
        vid = user_m.group(2) if user_m else ""
        leads.append({
            "id": vid,
            "url": clean_u,
            "titulo": f"TikTok {canal} ({query})",
            "canal": canal,
            "idioma_busca": lang,
            "query_origem": query,
            "fonte_descoberta": "bing_videos",
        })
    return leads


def _enrich_social_url_ytdlp(lead: dict[str, Any], platform: str, today: dt.date, timeout_s: int = 12) -> dict[str, Any]:
    """Enriquecimento leve via yt-dlp --dump-json com fallback seguro (nunca quebra a varredura)."""
    url = lead["url"]
    info: dict[str, Any] | None = None
    try:
        r = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", "--skip-download", url],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if r.returncode == 0 and r.stdout.strip():
            info = json.loads(r.stdout.splitlines()[0])
    except Exception:
        info = None

    if info:
        m = compute_metrics(info, today, platform=platform)
        m["url"] = url
        if not m["titulo"]:
            m["titulo"] = lead["titulo"]
        m["enriquecido"] = True
        m["idioma_busca"] = lead["idioma_busca"]
        m["query_origem"] = lead["query_origem"]
        m["fonte_descoberta"] = lead.get("fonte_descoberta", "web")
        return m

    return {
        "id": lead.get("id", ""),
        "plataforma": platform,
        "titulo": strip_emoji_and_dashes(lead.get("titulo", "")) or url,
        "canal": strip_emoji_and_dashes(lead.get("canal", "")) or platform,
        "url": url,
        "thumbnail": "",
        "duracao_s": 0,
        "upload_date": "",
        "dias_no_ar": 0,
        "views": 0,
        "inscritos": 0,
        "likes": 0,
        "comentarios": 0,
        "views_por_dia": 0.0,
        "outlier_ratio": 0.0,
        "engajamento_pontos": 0,
        "engajamento_taxa": 0.0,
        "viral_score": 0.0,
        "enriquecido": False,
        "idioma_busca": lead.get("idioma_busca", "en"),
        "query_origem": lead.get("query_origem", ""),
        "fonte_descoberta": lead.get("fonte_descoberta", "web"),
    }


def discover_tiktok_leads(
    queries: list[tuple[str, str]],
    today: dt.date,
    episodes: list[dict[str, Any]],
    seen_keys: set[str],
    apenas_novos: bool,
    max_items: int = 6,
) -> tuple[list[dict[str, Any]], str]:
    raw_leads: dict[str, dict[str, Any]] = {}
    search_queries = queries[:3]
    ddg_blocked = False

    for lang, q in search_queries:
        if len(raw_leads) >= max_items * 2:
            break
        # 1. Tenta DuckDuckGo HTML publico primeiro
        ddg_q = f'site:tiktok.com "/video/" {q}'
        status, body = _http_get_text("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(ddg_q), timeout=10)
        if status == 200 and body:
            for link, title in _parse_ddg_html(body):
                m = re.search(r"(https?://(?:www\.|m\.)?tiktok\.com/@[A-Za-z0-9_.-]+/video/(\d+))", link)
                if m:
                    clean_u = m.group(1).replace("m.tiktok.com", "www.tiktok.com")
                    vid = m.group(2)
                    if vid not in raw_leads:
                        um = re.search(r"tiktok\.com/(@[A-Za-z0-9_.-]+)/video/", clean_u)
                        raw_leads[vid] = {
                            "id": vid, "url": clean_u,
                            "titulo": title or f"TikTok ({q})",
                            "canal": um.group(1) if um else "tiktok",
                            "idioma_busca": lang, "query_origem": q, "fonte_descoberta": "ddg_html",
                        }
        else:
            ddg_blocked = True

        # 2. Fallback publico via Bing Videos (HTTP 200) se DDG nao retornou resultados
        if len(raw_leads) < max_items:
            bv_url = "https://www.bing.com/videos/search?q=" + urllib.parse.quote(f"{q} site:tiktok.com")
            b_status, b_body = _http_get_text(bv_url, timeout=10)
            if b_status == 200 and b_body:
                for lead in _extract_bing_video_tiktok_leads(b_body, q, lang):
                    if lead["id"] and lead["id"] not in raw_leads:
                        raw_leads[lead["id"]] = lead

    # Prioriza itens ainda nao vistos em vistos.json
    candidates = list(raw_leads.values())
    if apenas_novos:
        candidates = [c for c in candidates if canonical_item_key("tiktok", c["id"], c["url"]) not in seen_keys]
    else:
        candidates.sort(key=lambda c: canonical_item_key("tiktok", c["id"], c["url"]) in seen_keys)
    candidates = candidates[:max_items]

    if not candidates:
        note = "sem URLs publicas retornadas (DDG status!=200)" if ddg_blocked else "sem resultados novos"
        return [], note

    enriched: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(_enrich_social_url_ytdlp, c, "tiktok", today, 14) for c in candidates]
        for fut in concurrent.futures.as_completed(futs):
            item = fut.result()
            key = canonical_item_key("tiktok", item["id"], item["url"])
            is_dup, ep_match, dup_reason = check_duplicate_episode(item["titulo"], "", episodes)
            item["ja_visto"] = key in seen_keys
            item["ja_produzido"] = is_dup
            item["episodio_similar"] = ep_match
            item["motivo_similaridade"] = dup_reason
            item["gancho_transcricao"] = ""
            item["legenda_idioma"] = ""
            enriched.append(item)

    enriched.sort(key=lambda x: (x["ja_visto"], -x["viral_score"], -x["views"]))
    ok_meta = sum(1 for x in enriched if x.get("enriquecido"))
    return enriched, f"{len(enriched)} leads ({ok_meta} enriquecidos via yt-dlp)"


def discover_instagram_leads(
    queries: list[tuple[str, str]],
    today: dt.date,
    episodes: list[dict[str, Any]],
    seen_keys: set[str],
    apenas_novos: bool,
    max_items: int = 6,
) -> tuple[list[dict[str, Any]], str]:
    raw_leads: dict[str, dict[str, Any]] = {}
    search_queries = queries[:3]
    ddg_restricted = False

    for lang, q in search_queries:
        if len(raw_leads) >= max_items * 2:
            break
        ddg_q = f"site:instagram.com/reel/ {q}"
        status, body = _http_get_text("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(ddg_q), timeout=10)
        if status == 200 and body:
            for link, title in _parse_ddg_html(body):
                m = re.search(r"(https?://(?:www\.)?instagram\.com/reel/([A-Za-z0-9_-]+)/?)", link)
                if m and m.group(2) not in raw_leads:
                    raw_leads[m.group(2)] = {
                        "id": m.group(2), "url": m.group(1).rstrip("/") + "/",
                        "titulo": title or f"Instagram Reel ({q})",
                        "canal": "instagram", "idioma_busca": lang, "query_origem": q,
                        "fonte_descoberta": "ddg_html",
                    }
        else:
            ddg_restricted = True

        # Fallback publico via Bing Web (extrai apenas URLs reais instagram.com/reel/<id>)
        if len(raw_leads) < max_items:
            b_status, b_body = _http_get_text(
                "https://www.bing.com/search?q=" + urllib.parse.quote(f"site:instagram.com/reel/ {q}"),
                timeout=10,
            )
            if b_status == 200 and b_body:
                for link, title in _parse_bing_web_html(b_body):
                    m = re.search(r"(https?://(?:www\.)?instagram\.com/reel/([A-Za-z0-9_-]+)/?)", link)
                    if m and m.group(2) not in raw_leads:
                        raw_leads[m.group(2)] = {
                            "id": m.group(2), "url": m.group(1).rstrip("/") + "/",
                            "titulo": title or f"Instagram Reel ({q})",
                            "canal": "instagram", "idioma_busca": lang, "query_origem": q,
                            "fonte_descoberta": "bing_web",
                        }

    candidates = list(raw_leads.values())
    if apenas_novos:
        candidates = [c for c in candidates if canonical_item_key("instagram", c["id"], c["url"]) not in seen_keys]
    else:
        candidates.sort(key=lambda c: canonical_item_key("instagram", c["id"], c["url"]) in seen_keys)
    candidates = candidates[:max_items]

    if not candidates:
        reason = (
            "0 leads nesta rede (busca publica DDG/Bing sem URLs de Reels neste IP; modo gratuito sem login)"
            if ddg_restricted
            else "0 leads novos retornados"
        )
        return [], reason

    enriched: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_enrich_social_url_ytdlp, c, "instagram", today, 8) for c in candidates]
        for fut in concurrent.futures.as_completed(futs):
            item = fut.result()
            key = canonical_item_key("instagram", item["id"], item["url"])
            is_dup, ep_match, dup_reason = check_duplicate_episode(item["titulo"], "", episodes)
            item["ja_visto"] = key in seen_keys
            item["ja_produzido"] = is_dup
            item["episodio_similar"] = ep_match
            item["motivo_similaridade"] = dup_reason
            item["gancho_transcricao"] = ""
            item["legenda_idioma"] = ""
            enriched.append(item)

    enriched.sort(key=lambda x: (x["ja_visto"], -x["viral_score"], -x["views"]))
    ok_meta = sum(1 for x in enriched if x.get("enriquecido"))
    return enriched, f"{len(enriched)} leads ({ok_meta} enriquecidos; fallback de snippet quando exige login)"


# -------------------------------------------- Metricas, Whisper local e Frames
def compute_metrics(info: dict[str, Any], today: dt.date, platform: str = "youtube") -> dict[str, Any]:
    views = int(info.get("view_count") or 0)
    likes = int(info.get("like_count") or 0)
    comments = int(info.get("comment_count") or 0)
    subs = int(info.get("channel_follower_count") or info.get("uploader_follower_count") or 0)
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

    views_per_day = round(views / max(days_since, 1), 1) if views else 0.0
    outlier_ratio = round(views / max(subs, 1000), 2) if views else 0.0
    engagement_points = likes + comments * 5
    engagement_rate = round(engagement_points / max(views, 1), 5) if views else 0.0

    viral_score = 0.0
    if views > 0:
        viral_score = round(
            math.log10(views_per_day + 10.0) * 20.0
            + math.log10(outlier_ratio + 1.0) * 35.0
            + min(engagement_rate * 400.0, 25.0)
            + math.log10(views + 10.0) * 5.0,
            2,
        )

    vid = str(info.get("id") or "")
    if platform == "youtube" and vid:
        item_url = f"https://www.youtube.com/shorts/{vid}"
    else:
        item_url = info.get("webpage_url") or info.get("original_url") or ""
    thumb = info.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if (platform == "youtube" and vid) else "")

    return {
        "id": vid,
        "plataforma": platform,
        "titulo": strip_emoji_and_dashes(info.get("title") or info.get("description") or ""),
        "canal": strip_emoji_and_dashes(info.get("channel") or info.get("uploader") or info.get("creator") or ""),
        "url": item_url,
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


def transcribe_clip_with_local_whisper(video_path: Path, max_seconds: float = 15.0) -> tuple[str, str]:
    """
    Fallback local de transcricao (0-15s) para TikTok/Reels/videos sem legenda nativa:
    1) Extrai audio 16kHz mono via ffmpeg
    2) Transcreve com faster-whisper (passando float32 PCM direto, evitando bug do av.open)
       ou openai-whisper como segundo fallback.
    """
    global _WHISPER_MODEL
    if not video_path.is_file() or video_path.stat().st_size < 1000:
        return "", ""

    with tempfile.TemporaryDirectory(prefix="radar_wh_") as tmpdir:
        wav_path = Path(tmpdir) / "clip_15s.wav"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(video_path), "-t", str(int(max_seconds)),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav_path),
                ],
                check=True, capture_output=True, timeout=20,
            )
        except Exception:
            return "", ""

        if not wav_path.is_file() or wav_path.stat().st_size < 1000:
            return "", ""

        # Caminho 1: faster_whisper (ja instalado e em cache no ambiente)
        try:
            import numpy as np
            from faster_whisper import WhisperModel

            if _WHISPER_MODEL is None:
                _WHISPER_MODEL = WhisperModel("small", device="cpu", compute_type="int8")
            raw_f32 = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(wav_path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                check=True, capture_output=True, timeout=15,
            ).stdout
            audio16 = np.frombuffer(raw_f32, dtype=np.float32)
            segs, info = _WHISPER_MODEL.transcribe(audio16, beam_size=1)
            txt = strip_emoji_and_dashes(" ".join(s.text.strip() for s in segs))
            if txt:
                return txt, getattr(info, "language", "auto") or "auto"
        except Exception:
            pass

        # Caminho 2: openai-whisper (caso exista em outra maquina)
        try:
            import whisper

            model = whisper.load_model("small")
            res = model.transcribe(str(wav_path))
            txt = strip_emoji_and_dashes(res.get("text") or "")
            if txt:
                return txt, res.get("language") or "auto"
        except Exception:
            pass

    return "", ""


def extract_frames_and_optional_whisper(
    url: str,
    info: dict[str, Any],
    platform: str,
    out_dir: Path,
    timestamps: list[float],
    need_whisper: bool,
) -> tuple[dict[str, Any], str, str]:
    """
    Extrai 4 frames (0.5s, 1.5s, 3.0s, 5.0s) em /tmp/radar_frames/ via yt-dlp + ffmpeg.
    Se need_whisper=True e o clipe for baixado com sucesso, transcreve 0-15s com Whisper local.
    No YouTube, usa fallback automatico do storyboard oficial se o download direto retornar 403.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for pat in ("frame_*.jpg", "thumbnail_*.jpg", "storyboard_*.jpg"):
        for old in out_dir.glob(pat):
            old.unlink(missing_ok=True)

    duration = float(info.get("duration") or 10.0)
    safe_ts = [min(t, max(duration - 0.2, 0.1)) for t in timestamps]
    extracted: list[str] = []
    source_mode = "yt-dlp+ffmpeg"
    whisper_txt, whisper_lang = "", ""

    thumb_url = info.get("thumbnail") or (f"https://i.ytimg.com/vi/{info.get('id', '')}/hqdefault.jpg" if platform == "youtube" else "")
    thumb_path = out_dir / "thumbnail_hd.jpg"
    if thumb_url:
        try:
            urllib.request.urlretrieve(thumb_url, str(thumb_path))
        except Exception:
            thumb_path = None
    else:
        thumb_path = None

    with tempfile.TemporaryDirectory(prefix="radar_vid_") as tmpdir:
        vid_path = Path(tmpdir) / "clip.mp4"
        fmt_sel = (
            "best[ext=mp4]/best"
            if platform in {"tiktok", "instagram"}
            else "bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]/best[ext=mp4]/best"
        )
        dl_ok = False
        try:
            r = subprocess.run(
                ["yt-dlp", "-q", "--no-warnings", "-f", fmt_sel, "-o", str(vid_path), "--force-overwrites", url],
                capture_output=True, text=True, timeout=40,
            )
            dl_ok = r.returncode == 0 and vid_path.is_file() and vid_path.stat().st_size > 10_000
        except Exception:
            dl_ok = False

        if dl_ok:
            for orig_t, t in zip(timestamps, safe_ts):
                frame_file = out_dir / f"frame_{orig_t:.1f}s.jpg"
                r_ff = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(vid_path), "-frames:v", "1", "-q:v", "2", str(frame_file)],
                    capture_output=True, text=True, timeout=15,
                )
                if r_ff.returncode == 0 and frame_file.exists():
                    extracted.append(str(frame_file))
            if need_whisper:
                whisper_txt, whisper_lang = transcribe_clip_with_local_whisper(vid_path, max_seconds=15.0)

    if len(extracted) == len(timestamps):
        return (
            {
                "modo": source_mode,
                "frames": extracted,
                "thumbnail_hd": str(thumb_path) if thumb_path and thumb_path.exists() else "",
            },
            whisper_txt,
            whisper_lang,
        )

    # Fallback de storyboard oficial do YouTube quando googlevideo bloqueia download em datacenter
    if platform == "youtube":
        source_mode = "storyboard_fallback+ffmpeg"
        extracted = []
        sbs = [f for f in (info.get("formats") or []) if f.get("ext") == "mhtml" and f.get("fragments")]
        sbs.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), reverse=True)
        if sbs:
            best = sbs[0]
            cell_w, cell_h = int(best.get("width") or 50), int(best.get("height") or 90)
            cols, rows = int(best.get("columns") or 5), int(best.get("rows") or 5)
            frag0 = best["fragments"][0]
            sec_per_cell = float(frag0.get("duration") or max(duration, 10.0)) / max(cols * rows, 1)
            sb_path = out_dir / "storyboard_grid.jpg"
            try:
                urllib.request.urlretrieve(frag0["url"], str(sb_path))
                for orig_t, t in zip(timestamps, safe_ts):
                    idx = min(int(round(t / max(sec_per_cell, 0.1))), max(cols * rows - 1, 0))
                    x, y = (idx % cols) * cell_w, (idx // cols) * cell_h
                    frame_file = out_dir / f"frame_{orig_t:.1f}s.jpg"
                    vf = f"crop={cell_w}:{cell_h}:{x}:{y},scale={cell_w * 4}:{cell_h * 4}:flags=lanczos"
                    r_ff = subprocess.run(
                        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(sb_path), "-vf", vf, "-q:v", "2", str(frame_file)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if r_ff.returncode == 0 and frame_file.exists():
                        extracted.append(str(frame_file))
            except Exception:
                pass

    return (
        {
            "modo": source_mode if extracted else "indisponivel",
            "frames": extracted,
            "thumbnail_hd": str(thumb_path) if thumb_path and thumb_path.exists() else "",
        },
        whisper_txt,
        whisper_lang,
    )


def fmt_int(n: int | float) -> str:
    val = int(round(n))
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(val)


# -------------------------------------------- Relatorios (Markdown + HTML Dark)
def write_markdown_report(payload: dict[str, Any], out_path: Path) -> None:
    lines: list[str] = [
        "# Radar Viral Multiplataforma: Varredura ao Vivo",
        "",
        f"- Gerado em: `{payload['gerado_em']}`",
        f"- Plataformas: `{', '.join(payload['plataformas'])}` | Apenas novos: `{payload['apenas_novos']}`",
        f"- Tema: `{payload['tema'] or 'Rotacao multi-idioma (What If / E Se / Stickman / Curiosidades)'}`",
        f"- Janela alvo: ultimos `{payload['dias']}` dias",
        f"- Contagem por plataforma: YouTube=`{payload['contagem_plataformas'].get('youtube', 0)}` | TikTok=`{payload['contagem_plataformas'].get('tiktok', 0)}` | Instagram=`{payload['contagem_plataformas'].get('instagram', 0)}`",
        "",
    ]
    if payload.get("status_plataformas"):
        lines.append("## Status das Plataformas (Modo 2 Gratuito)")
        for plat, msg in payload["status_plataformas"].items():
            lines.append(f"- `{plat}`: {msg}")
        lines.append("")

    if payload["episodios_existentes"]:
        lines.append("## Episodios ja produzidos na Fabrica V2 (anti-repeticao)")
        for ep in payload["episodios_existentes"]:
            lines.append(f"- `{ep['ep_id']}`: {ep['titulo']} (Gancho: \"{ep['hook']}\")")
        lines.append("")

    lines.append("## YouTube Shorts: Outliers Ranqueados")
    lines.append("")
    if payload["outliers"]:
        lines.append("| # | Frescor | Idioma | Titulo | Canal | Views | Views/Dia | Outlier | Engajamento | Status | Link |")
        lines.append("|---|---|---|---|---|---:|---:|---:|---:|---|---|")
        for idx, item in enumerate(payload["outliers"], 1):
            fresh = "VISTO" if item.get("ja_visto") else "NOVO"
            status = f"JA PRODUZIDO ({item['episodio_similar']})" if item["ja_produzido"] else "INEDITO"
            lines.append(
                f"| {idx} | {fresh} | {item['idioma_busca'].upper()} | {item['titulo'].replace('|', '/')} "
                f"| {item['canal'].replace('|', '/')} | {fmt_int(item['views'])} | {fmt_int(item['views_por_dia'])}/d "
                f"| {item['outlier_ratio']:.2f}x | {item['engajamento_taxa']*100:.2f}% | {status} | [Abrir]({item['url']}) |"
            )
    else:
        lines.append("Nenhum outlier do YouTube retornado nesta rodada.")

    lines.append("")
    lines.append("## TikTok e Instagram Reels: Leads Virais (Modo 2 Gratuito)")
    lines.append("")
    if payload["leads_sociais"]:
        lines.append("| # | Plataforma | Frescor | Titulo | Perfil | Views | Engajamento | Metadados | Link |")
        lines.append("|---|---|---|---|---|---:|---:|---|---|")
        for idx, item in enumerate(payload["leads_sociais"], 1):
            fresh = "VISTO" if item.get("ja_visto") else "NOVO"
            meta_txt = "yt-dlp OK" if item.get("enriquecido") else "snippet web"
            views_txt = fmt_int(item["views"]) if item["views"] > 0 else "n/a"
            eng_txt = f"{item['engajamento_taxa']*100:.2f}%" if item["views"] > 0 else "n/a"
            lines.append(
                f"| {idx} | {item['plataforma'].upper()} | {fresh} | {item['titulo'].replace('|', '/')[:90]} "
                f"| {item['canal'].replace('|', '/')} | {views_txt} | {eng_txt} | {meta_txt} | [Abrir]({item['url']}) |"
            )
    else:
        lines.append("Nenhum lead de TikTok ou Instagram Reels disponivel nesta execucao.")

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
    all_items = payload.get("itens", [])
    cards_html: list[str] = []
    for idx, item in enumerate(all_items, 1):
        plat = item.get("plataforma", "youtube")
        is_dup = bool(item.get("ja_produzido"))
        is_seen = bool(item.get("ja_visto"))
        status_cls = "badge-dup" if is_dup else "badge-new"
        status_txt = f"JA PRODUZIDO: {item['episodio_similar']}" if is_dup else "INEDITO"
        fresh_cls = "badge-seen" if is_seen else "badge-fresh"
        fresh_txt = "JA VISTO" if is_seen else "NOVO"
        plat_cls = f"badge-plat-{plat}"
        hook_txt = item.get("gancho_transcricao") or (
            "Use --analisar-url neste link para baixar 4 frames + transcricao Whisper local (0-15s)."
            if plat in {"tiktok", "instagram"}
            else "Sem legenda automatica capturada para os primeiros 15s."
        )
        thumb_html = (
            f'<img src="{html.escape(item["thumbnail"])}" alt="{html.escape(item["titulo"])}" loading="lazy" />'
            if item.get("thumbnail")
            else f'<div class="thumb-placeholder">{html.escape(plat.upper())} LEAD</div>'
        )
        views_txt = fmt_int(item["views"]) if item.get("views", 0) > 0 else "n/a"
        vpd_txt = fmt_int(item["views_por_dia"]) if item.get("views", 0) > 0 else "n/a"
        out_txt = f"{item['outlier_ratio']:.2f}x" if item.get("views", 0) > 0 else "lead"
        eng_txt = f"{item['engajamento_taxa']*100:.2f}%" if item.get("views", 0) > 0 else "n/a"

        cards_html.append(
            f"""
      <article class="card" data-plat="{html.escape(plat)}" data-status="{'dup' if is_dup else 'new'}" data-fresh="{'seen' if is_seen else 'fresh'}">
        <a class="thumb-link" href="{html.escape(item['url'])}" target="_blank" rel="noopener noreferrer">
          {thumb_html}
          <span class="rank-pill">#{idx}</span>
          <span class="dur-pill">{item['duracao_s']}s</span>
        </a>
        <div class="card-body">
          <div class="badges">
            <span class="badge {plat_cls}">{html.escape(plat.upper())}</span>
            <span class="badge {fresh_cls}">{fresh_txt}</span>
            <span class="badge {status_cls}">{html.escape(status_txt)}</span>
          </div>
          <h3><a href="{html.escape(item['url'])}" target="_blank" rel="noopener noreferrer">{html.escape(item['titulo'])}</a></h3>
          <p class="meta">{html.escape(item['canal'])} | {html.escape(item['upload_date'] or 'data n/a')}</p>
          <div class="metrics">
            <div class="metric"><span class="m-label">Views</span><strong class="m-val">{views_txt}</strong></div>
            <div class="metric"><span class="m-label">Views/Dia</span><strong class="m-val">{vpd_txt}</strong></div>
            <div class="metric"><span class="m-label">Outlier</span><strong class="m-val accent">{out_txt}</strong></div>
            <div class="metric"><span class="m-label">Engajamento</span><strong class="m-val">{eng_txt}</strong></div>
          </div>
          <div class="hook-box">
            <span class="hook-label">Gancho 0-15s ({html.escape(item.get('legenda_idioma') or plat)})</span>
            <p>{html.escape(hook_txt)}</p>
          </div>
        </div>
      </article>"""
        )

    tema_label = payload["tema"] or "Rotacao multi-idioma (What If / E Se / Stickman)"
    cnt = payload["contagem_plataformas"]
    total_fresh = sum(1 for x in all_items if not x.get("ja_visto"))

    doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Radar Viral Multiplataforma | Fabrica V2</title>
  <style>
    :root {{
      --bg: #0c0e13; --surface: #141821; --surface-2: #1b2130; --border: #283044;
      --text: #f1f3f8; --muted: #9aa6be; --accent: #f5b72b; --ok: #34d399;
      --warn: #fb7185; --yt: #ff4d4f; --tt: #22d3ee; --ig: #f472b6;
      --radius: 12px; --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: var(--font); background: var(--bg); color: var(--text); line-height: 1.5; padding: 20px 16px 56px; }}
    .wrap {{ max-width: 1260px; margin: 0 auto; }}
    header {{ border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 22px; }}
    .eyebrow {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent); font-weight: 700; }}
    h1 {{ margin: 6px 0 8px; font-size: clamp(28px, 4vw, 40px); line-height: 1.1; }}
    .subtitle {{ margin: 0; color: var(--muted); font-size: 14px; }}
    .summary-bar {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 18px 0 22px; }}
    .stat-tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; }}
    .stat-tile span {{ display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; }}
    .stat-tile strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }}
    .pill-btn {{ background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 999px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; min-height: 38px; }}
    .pill-btn:hover {{ border-color: var(--accent); }}
    .pill-btn:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .pill-btn[aria-pressed="true"] {{ background: var(--accent); color: #0c0e13; border-color: var(--accent); }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
    @media (min-width: 720px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (min-width: 1080px) {{ .grid {{ grid-template-columns: repeat(3, 1fr); }} }}
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: flex; flex-direction: column; }}
    .thumb-link {{ position: relative; display: block; aspect-ratio: 16 / 9; background: #080a0f; overflow: hidden; text-decoration: none; }}
    .thumb-link img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .thumb-placeholder {{ width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-weight: 800; letter-spacing: 0.08em; color: var(--muted); background: #101520; }}
    .rank-pill, .dur-pill {{ position: absolute; top: 10px; padding: 4px 9px; border-radius: 6px; font-size: 12px; font-weight: 700; background: rgba(12,14,19,0.88); border: 1px solid var(--border); color: var(--text); }}
    .rank-pill {{ left: 10px; color: var(--accent); }}
    .dur-pill {{ right: 10px; }}
    .card-body {{ padding: 16px; display: flex; flex-direction: column; gap: 10px; flex: 1; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .badge {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; border: 1px solid var(--border); letter-spacing: 0.03em; }}
    .badge-plat-youtube {{ color: var(--yt); background: rgba(255,77,79,0.12); border-color: rgba(255,77,79,0.4); }}
    .badge-plat-tiktok {{ color: var(--tt); background: rgba(34,211,238,0.12); border-color: rgba(34,211,238,0.4); }}
    .badge-plat-instagram {{ color: var(--ig); background: rgba(244,114,182,0.12); border-color: rgba(244,114,182,0.4); }}
    .badge-fresh {{ color: var(--accent); background: rgba(245,183,43,0.12); border-color: rgba(245,183,43,0.35); }}
    .badge-seen {{ color: var(--muted); background: var(--surface-2); }}
    .badge-new {{ color: var(--ok); background: rgba(52,211,153,0.12); border-color: rgba(52,211,153,0.35); }}
    .badge-dup {{ color: var(--warn); background: rgba(251,113,133,0.12); border-color: rgba(251,113,133,0.35); }}
    h3 {{ margin: 0; font-size: 16px; line-height: 1.3; }}
    h3 a {{ color: var(--text); text-decoration: none; }}
    h3 a:hover {{ color: var(--accent); text-decoration: underline; }}
    .meta {{ margin: 0; font-size: 13px; color: var(--muted); }}
    .metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }}
    .m-label {{ display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; }}
    .m-val {{ font-size: 15px; }}
    .m-val.accent {{ color: var(--accent); }}
    .hook-box {{ background: #10141d; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-top: auto; }}
    .hook-label {{ display: block; font-size: 11px; font-weight: 700; color: var(--accent); text-transform: uppercase; margin-bottom: 4px; }}
    .hook-box p {{ margin: 0; font-size: 13px; color: #dce2ee; }}
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="eyebrow">Fabrica V2 | Radar Viral Multiplataforma (Modo 2 Gratuito)</div>
      <h1>{html.escape(tema_label)}</h1>
      <p class="subtitle">Varredura ao vivo em {html.escape(payload['gerado_em'])} | YouTube: {cnt.get('youtube', 0)} | TikTok: {cnt.get('tiktok', 0)} | Instagram: {cnt.get('instagram', 0)}</p>
    </header>
    <section class="summary-bar" aria-label="Resumo multiplataforma">
      <div class="stat-tile"><span>Total Itens</span><strong>{len(all_items)}</strong></div>
      <div class="stat-tile"><span>YouTube Shorts</span><strong>{cnt.get('youtube', 0)}</strong></div>
      <div class="stat-tile"><span>TikTok Leads</span><strong>{cnt.get('tiktok', 0)}</strong></div>
      <div class="stat-tile"><span>Instagram Reels</span><strong>{cnt.get('instagram', 0)}</strong></div>
      <div class="stat-tile"><span>Novos (vistos.json)</span><strong>{total_fresh}</strong></div>
    </section>
    <nav class="controls" aria-label="Filtros por plataforma e frescor">
      <button type="button" class="pill-btn" data-filter="all" aria-pressed="true">Todos ({len(all_items)})</button>
      <button type="button" class="pill-btn" data-filter="youtube" aria-pressed="false">YouTube ({cnt.get('youtube', 0)})</button>
      <button type="button" class="pill-btn" data-filter="tiktok" aria-pressed="false">TikTok ({cnt.get('tiktok', 0)})</button>
      <button type="button" class="pill-btn" data-filter="instagram" aria-pressed="false">Instagram ({cnt.get('instagram', 0)})</button>
      <button type="button" class="pill-btn" data-filter="fresh" aria-pressed="false">Somente Novos ({total_fresh})</button>
      <button type="button" class="pill-btn" data-filter="new" aria-pressed="false">Somente Ineditos</button>
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
            (f === "fresh" && c.dataset.fresh === "fresh") ||
            (f === "new" && c.dataset.status === "new") ||
            c.dataset.plat === f;
          c.classList.toggle("hidden", !show);
        }});
      }});
    }});
  </script>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")


# ------------------------------------------------ Analise Universal de URL
def run_single_url_analysis(url: str, output_dir: Path) -> int:
    platform = detect_platform(url)
    print(f"[RADAR] Analise profunda universal | plataforma={platform} | url={url}")
    today = dt.date.today()
    episodes = load_existing_episodes()

    info: dict[str, Any] = {}
    meta_err = ""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as exc:
        meta_err = str(exc)
        if platform != "instagram":
            print(f"ERRO ao extrair metadados da URL: {exc}", file=sys.stderr)
            return 1
        print(f"[RADAR] Aviso Instagram sem login: metadados restritos ({meta_err[:120]})")

    metrics = compute_metrics(info, today, platform=platform) if info else {
        "id": "", "plataforma": platform, "titulo": url, "canal": platform, "url": url,
        "thumbnail": "", "duracao_s": 0, "upload_date": "", "dias_no_ar": 0,
        "views": 0, "inscritos": 0, "likes": 0, "comentarios": 0,
        "views_por_dia": 0.0, "outlier_ratio": 0.0, "engajamento_pontos": 0,
        "engajamento_taxa": 0.0, "viral_score": 0.0,
    }

    # 1. Tenta legenda nativa primeiro (YouTube)
    transcript, sub_lang, sub_origin = "", "", "indisponivel"
    if info and platform == "youtube":
        transcript, sub_lang = extract_opening_transcript(metrics["id"], info, max_seconds=15.0)
        if transcript:
            sub_origin = "legenda_nativa"

    # 2. Baixa clipe para 4 frames (0.5s, 1.5s, 3.0s, 5.0s) + fallback Whisper local se sem legenda
    timestamps = [0.5, 1.5, 3.0, 5.0]
    frames_info, wh_txt, wh_lang = extract_frames_and_optional_whisper(
        url, info, platform, FRAMES_DIR, timestamps, need_whisper=(not bool(transcript))
    )
    if not transcript and wh_txt:
        transcript = wh_txt
        sub_lang = wh_lang or "whisper"
        sub_origin = "whisper_local"
    elif not transcript:
        transcript = "Transcricao indisponivel"

    is_dup, ep_match, dup_reason = check_duplicate_episode(metrics["titulo"], transcript, episodes)
    result = {
        "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "modo": "analisar_url",
        **metrics,
        "descricao_resumo": strip_emoji_and_dashes((info.get("description") or "")[:400]),
        "gancho_transcricao": transcript,
        "legenda_idioma": sub_lang,
        "legenda_origem": sub_origin,
        "aviso_restricao": meta_err[:200] if meta_err else "",
        "ja_produzido": is_dup,
        "episodio_similar": ep_match,
        "motivo_similaridade": dup_reason,
        "frames_extracao": frames_info,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "analise_url.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "analise_url.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Plataforma: {platform.upper()} | Titulo: {result['titulo']}")
    print(f"Canal: {result['canal']} ({fmt_int(result['inscritos'])} inscritos)")
    print(
        f"Metricas: {fmt_int(result['views'])} views | {fmt_int(result['views_por_dia'])}/dia | "
        f"Outlier {result['outlier_ratio']:.2f}x | Engajamento {result['engajamento_taxa']*100:.2f}% | "
        f"Duracao {result['duracao_s']}s | Upload {result['upload_date']}"
    )
    print(f"Status canal: {'JA PRODUZIDO (' + str(ep_match) + ')' if is_dup else 'INEDITO'}")
    print(f"Gancho 0-15s [{sub_origin}/{sub_lang or 'n/a'}]: {transcript}")
    print(f"Frames ({frames_info['modo']}): {frames_info['frames']}")
    if frames_info.get("thumbnail_hd"):
        print(f"Thumbnail HD: {frames_info['thumbnail_hd']}")
    return 0


# ----------------------------------------------------- Varredura Multiplataforma
def run_live_scan(args: argparse.Namespace) -> int:
    t0 = time.time()
    today = dt.date.today()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    platforms = [p.strip().lower() for p in args.plataformas.split(",") if p.strip()]
    valid_plats = [p for p in platforms if p in {"youtube", "tiktok", "instagram"}] or ["youtube"]

    episodes = load_existing_episodes()
    seen_data = load_seen_memory(output_dir)
    seen_keys = set(seen_data.get("itens", {}).keys())
    queries = build_queries(args.tema, num_queries=args.queries, seed=args.seed)

    print(
        f"[RADAR] Varredura multiplataforma ao vivo | plataformas={','.join(valid_plats)} "
        f"| queries={len(queries)} | max_per_query={args.max_per_query} | limite={args.limite} "
        f"| dias={args.dias} | apenas_novos={args.apenas_novos} | vistos_previos={len(seen_keys)}"
    )

    yt_outliers: list[dict[str, Any]] = []
    social_leads: list[dict[str, Any]] = []
    status_plataformas: dict[str, str] = {}
    total_yt_cands = 0

    # --- 1. YouTube Shorts (motor original 100% intacto + vistos.json) ---
    if "youtube" in valid_plats:
        candidates_by_id: dict[str, dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries), 6)) as pool:
            future_map = {
                pool.submit(search_youtube_shorts_live, lang, q, choose_sp_filter(args.dias, idx), args.max_per_query): (lang, q)
                for idx, (lang, q) in enumerate(queries)
            }
            for fut in concurrent.futures.as_completed(future_map):
                lang, q = future_map[fut]
                rows = fut.result() or []
                print(f"  -> [YT/{lang.upper()}] '{q}': {len(rows)} shorts candidatos")
                for r in rows:
                    vid = r["id"]
                    if vid not in candidates_by_id or r["views_preview"] > candidates_by_id[vid]["views_preview"]:
                        candidates_by_id[vid] = r

        cand_list = sorted(candidates_by_id.values(), key=lambda x: x["views_preview"], reverse=True)
        enrich_cap = min(max(args.limite * 2, len(queries) * args.max_per_query), 45)
        cand_list = cand_list[:enrich_cap]
        total_yt_cands = len(cand_list)
        print(f"[RADAR] Enriquecendo {len(cand_list)} candidatos YouTube via yt-dlp...")

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
                metrics = compute_metrics(info, today, platform="youtube")
                if metrics["views"] < args.min_views:
                    continue
                enriched.append((cand, info, metrics))

        in_window = [item for item in enriched if item[2]["dias_no_ar"] <= args.dias]
        selected_pool = in_window if len(in_window) >= min(args.limite, 5) else enriched

        # Aplica memoria vistos.json (prioriza nao vistos ou filtra completamente com --apenas-novos)
        if args.apenas_novos:
            selected_pool = [
                it for it in selected_pool
                if canonical_item_key("youtube", it[2]["id"], it[2]["url"]) not in seen_keys
            ]
        selected_pool.sort(
            key=lambda it: (
                canonical_item_key("youtube", it[2]["id"], it[2]["url"]) in seen_keys,
                -it[2]["viral_score"],
            )
        )
        top_items = selected_pool[: args.limite]

        cap_limit = min(len(top_items), args.legendas_top)
        print(f"[RADAR] Extraindo gancho real YouTube (0-15s) dos top {cap_limit} outliers...")
        for idx, (cand, info, metrics) in enumerate(top_items):
            transcript, sub_lang = "", ""
            if idx < cap_limit:
                transcript, sub_lang = extract_opening_transcript(metrics["id"], info, max_seconds=15.0)
                if idx + 1 < cap_limit:
                    time.sleep(0.45)
            is_dup, ep_match, dup_reason = check_duplicate_episode(metrics["titulo"], transcript, episodes)
            key = canonical_item_key("youtube", metrics["id"], metrics["url"])
            yt_outliers.append({
                **metrics,
                "enriquecido": True,
                "ja_visto": key in seen_keys,
                "idioma_busca": cand["lang_query"],
                "query_origem": cand["query"],
                "fora_janela_dias": metrics["dias_no_ar"] > args.dias,
                "gancho_transcricao": transcript,
                "legenda_idioma": sub_lang,
                "ja_produzido": is_dup,
                "episodio_similar": ep_match,
                "motivo_similaridade": dup_reason,
            })
        status_plataformas["youtube"] = f"{len(yt_outliers)} outliers ranqueados ({total_yt_cands} candidatos)"

    # --- 2. TikTok (Modo 2 gratuito) ---
    if "tiktok" in valid_plats:
        print("[RADAR] Buscando leads publicos no TikTok (Modo 2 gratuito)...")
        tt_leads, tt_status = discover_tiktok_leads(queries, today, episodes, seen_keys, args.apenas_novos, max_items=6)
        social_leads.extend(tt_leads)
        status_plataformas["tiktok"] = tt_status
        print(f"  -> [TIKTOK] {tt_status}")

    # --- 3. Instagram Reels (Modo 2 gratuito) ---
    if "instagram" in valid_plats:
        print("[RADAR] Buscando leads publicos no Instagram Reels (Modo 2 gratuito)...")
        ig_leads, ig_status = discover_instagram_leads(queries, today, episodes, seen_keys, args.apenas_novos, max_items=6)
        social_leads.extend(ig_leads)
        status_plataformas["instagram"] = ig_status
        print(f"  -> [INSTAGRAM] {ig_status}")

    all_items = yt_outliers + social_leads
    contagem = {
        "youtube": len(yt_outliers),
        "tiktok": sum(1 for x in social_leads if x["plataforma"] == "tiktok"),
        "instagram": sum(1 for x in social_leads if x["plataforma"] == "instagram"),
    }

    payload = {
        "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "plataformas": valid_plats,
        "apenas_novos": bool(args.apenas_novos),
        "tema": args.tema or "",
        "dias": args.dias,
        "max_per_query": args.max_per_query,
        "limite": args.limite,
        "queries": [[l, q] for l, q in queries],
        "total_candidatos_avaliados": total_yt_cands + len(social_leads),
        "contagem_plataformas": contagem,
        "status_plataformas": status_plataformas,
        "episodios_existentes": [{"ep_id": e["ep_id"], "titulo": e["titulo"], "hook": e["hook"]} for e in episodes],
        "outliers": yt_outliers,
        "leads_sociais": social_leads,
        "itens": all_items,
    }

    vistos_path = save_seen_memory(output_dir, seen_data, all_items)
    json_path = output_dir / "radar_dados.json"
    md_path = output_dir / "radar_resumo.md"
    html_path = output_dir / "relatorio_viral.html"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(payload, md_path)
    write_html_report(payload, html_path)

    elapsed = time.time() - t0
    print(
        f"[RADAR] Concluido em {elapsed:.1f}s | YT={contagem['youtube']} | TikTok={contagem['tiktok']} "
        f"| Instagram={contagem['instagram']} | vistos_total={len(seen_data.get('itens', {}))}"
    )
    print(f"  VISTOS: {vistos_path}")
    print(f"  JSON:   {json_path}")
    print(f"  MD:     {md_path}")
    print(f"  HTML:   {html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Radar Viral Multiplataforma ao vivo para Fabrica V2 (YouTube Shorts, TikTok, Instagram Reels)"
    )
    p.add_argument("--plataformas", type=str, default="youtube,tiktok,instagram", help="Plataformas separadas por virgula (padrao: youtube,tiktok,instagram).")
    p.add_argument("--apenas-novos", action="store_true", help="Filtra completamente itens ja registrados em vistos.json.")
    p.add_argument("--tema", type=str, default=None, help="Tema especifico para buscas multi-idioma (EN/ES/PT).")
    p.add_argument("--dias", type=int, default=180, help="Janela maxima em dias para uploads recentes (padrao: 180).")
    p.add_argument("--max-per-query", type=int, default=8, help="Maximo de candidatos YouTube por query (padrao: 8).")
    p.add_argument("--limite", type=int, default=15, help="Quantidade de outliers YouTube na saida final (padrao: 15).")
    p.add_argument("--queries", type=int, default=6, help="Numero de queries multi-idioma por varredura (padrao: 6).")
    p.add_argument("--legendas-top", type=int, default=8, help="Top outliers YouTube com legenda 0-15s (padrao: 8).")
    p.add_argument("--max-duracao", type=int, default=120, help="Duracao maxima em segundos para Shorts (padrao: 120).")
    p.add_argument("--min-views", type=int, default=1000, help="Minimo de views para YouTube Shorts (padrao: 1000).")
    p.add_argument("--seed", type=int, default=None, help="Semente opcional para testes reproduziveis.")
    p.add_argument("--analisar-url", type=str, default=None, help="URL universal (YouTube, TikTok ou Reel) para metadados + 4 frames + legenda/Whisper 0-15s.")
    p.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Diretorio de saida (padrao: fabrica_v2/radar/output).")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.analisar_url:
        return run_single_url_analysis(args.analisar_url, Path(args.output_dir))
    return run_live_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
