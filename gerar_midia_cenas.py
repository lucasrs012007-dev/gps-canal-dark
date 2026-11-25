"""Estacao 3A (Motor Cinematografico IA V8.0): gera midia unica por cena em 9:16 (1080x1920).

Uso (na raiz do repositorio):
    python3 gerar_midia_cenas.py
    python3 gerar_midia_cenas.py --max-cenas 2
    python3 gerar_midia_cenas.py --forcar

Estrategia de geracao (zero boneco Canvas, zero Pollinations/marca d'agua, zero tela preta):
1. Plug-and-play Video IA via `FAL_KEY` (opcional):
   - Se `FAL_KEY` estiver definida no ambiente, gera clipes reais `.mp4` por cena via
     `fal-ai/wan/v2.1/t2v-480p` (9:16). Em caso de erro em alguma cena, faz fallback automatico
     para a API de imagem do Gemini naquela cena.
2. Modo gratuito padrao via `GEMINI_API_KEY` (`google-genai`):
   - Tenta automaticamente os modelos nativos do Gemini:
     1) `gemini-2.5-flash-image` (`response_modalities=["IMAGE"]`)
     2) `gemini-2.0-flash-preview-image-generation` (`response_modalities=["IMAGE"]` / `["TEXT", "IMAGE"]`)
     3) `imagen-3.0-generate-002` (`aspect_ratio="9:16"`)
   - Faz cache do primeiro modelo que funcionar na conta para acelerar todas as cenas restantes.
   - Valida rigorosamente cada imagem (> 30KB, nao preta/vazia, crop inteligente 1080x1920 sem distorcao).
   - Se alguma cena falhar (ex.: filtro de seguranca em palavras como "morto/sangue"), reescreve
     o prompt de forma neutra e regera; em ultimo caso, reaproveita a cena valida anterior com
     enquadramento distinto (nunca gera tela preta vazia).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.config_canal import carregar_config_canal  # noqa: E402

ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
PASTA_SAIDA_PADRAO = RAIZ / "output" / "cenas"
MANIFESTO_NOME = "manifesto_midia.json"

LARGURA_ALVO = 1080
ALTURA_ALVO = 1920
TAMANHO_MIN_IMAGEM_BYTES = 30 * 1024
TAMANHO_MIN_VIDEO_BYTES = 50 * 1024

MODELOS_GEMINI_IMAGEM: tuple[str, ...] = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
    "imagen-3.0-generate-002",
)
FAL_ENDPOINT_T2V = "fal-ai/wan/v2.1/t2v-480p"
FAL_QUEUE_BASE = "https://queue.fal.run"

ESTILO_CINEMATOGRAFICO_PADRAO = (
    "hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, "
    "Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, "
    "no text, no letters, no watermark"
)

_SUBSTITUICOES_SEGURANCA: tuple[tuple[str, str], ...] = (
    (r"\b(?:bloody|blood|bleeding|sangue|ensanguentad[oa]s?)\b", "deep crimson shadow reflection"),
    (r"\b(?:corpse|dead\s+body|cadaver|cadáver|morto|morta|mortos|mortas)\b", "eerie motionless silhouette"),
    (r"\b(?:murder|murdered|kill|killed|killing|assassinat[oa]|matar|matou)\b", "mysterious dark disappearance"),
    (r"\b(?:gore|gory|wound|wounds|ferida|ferimento|mutilat\w*)\b", "dramatic weathered texture"),
    (r"\b(?:suicide|suicidio|suicídio|self[- ]harm)\b", "solitary suspenseful moment"),
    (r"\b(?:knife|blade|gun|pistol|rifle|weapon|shot|shooting|stab|faca|arma|tiro)\b", "metallic glinting object in shadow"),
    (r"\b(?:torture|terrorist|bomb|explosion|explosao|explosão)\b", "dramatic volumetric shockwave glow"),
    (r"\b(?:skull|skeleton|demon|devil|satanic|diabo)\b", "ancient stone sculpture in mist"),
)


def carregar_env(caminho_env: Path = ARQUIVO_ENV) -> bool:
    """Carrega variaveis de .env local apenas quando ausentes no ambiente."""
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


def _estilo_atual() -> str:
    try:
        cfg = carregar_config_canal()
        est = str(cfg.get("estilo_visual_prompt", "")).strip()
        if est:
            return est
    except Exception:
        pass
    return ESTILO_CINEMATOGRAFICO_PADRAO


def garantir_estilo_prompt(prompt: str) -> str:
    limpo = re.sub(r"\s+", " ", str(prompt or "")).strip(" ,.;:")
    estilo = _estilo_atual()
    if not limpo:
        return f"Moody cinematic dark atmospheric suspense scene, {estilo}"
    low = limpo.lower()
    if "no watermark" in low and "9:16" in low:
        return limpo
    return f"{limpo}, {estilo}"


def reescrever_prompt_neutro(prompt: str, fala_fallback: str = "") -> str:
    """Reescreve um prompt bloqueado por filtro de seguranca em linguagem atmosferica neutra."""
    texto = str(prompt or "").strip()
    if not texto and fala_fallback:
        texto = f"Dark cinematic atmospheric suspense scene inspired by a nocturnal mystery"
    for padrao, substituto in _SUBSTITUICOES_SEGURANCA:
        texto = re.sub(padrao, substituto, texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto).strip(" ,.;:")
    if len(texto) < 30:
        texto = (
            "Atmospheric nocturnal suspense environment with drifting fog, moody volumetric light beams "
            "and dramatic foreground silhouette"
        )
    return garantir_estilo_prompt(f"Safe artistic cinematic depiction, {texto}")


def validar_e_padronizar_imagem(
    raw_bytes: bytes,
    destino_jpg: Path,
    *,
    largura: int = LARGURA_ALVO,
    altura: int = ALTURA_ALVO,
    min_bytes: int = TAMANHO_MIN_IMAGEM_BYTES,
    centering: tuple[float, float] = (0.5, 0.5),
) -> dict[str, Any]:
    """Valida bytes de imagem, rejeita quadros pretos/vazios e salva JPEG 1080x1920 > 30KB."""
    if not raw_bytes or len(raw_bytes) < 2048:
        raise ValueError(f"Payload de imagem vazio ou pequeno demais ({len(raw_bytes)} bytes).")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img_raw:
            img_raw.load()
            if img_raw.width < 256 or img_raw.height < 256:
                raise ValueError(f"Resolucao insuficiente da imagem gerada: {img_raw.width}x{img_raw.height}.")
            rgb = img_raw.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Bytes nao representam uma imagem valida: {exc}") from exc

    # Rejeita telas pretas ou chapadas vazias
    stat = ImageStat.Stat(rgb)
    media_luma = sum(stat.mean) / 3.0
    max_std = max(stat.stddev)
    if media_luma < 6.0 or max_std < 5.0:
        raise ValueError(
            f"Imagem rejeitada por ser escura/vazia demais (media={media_luma:.1f}, stddev={max_std:.1f})."
        )

    ajustada = ImageOps.fit(
        rgb,
        (largura, altura),
        method=Image.Resampling.LANCZOS,
        centering=centering,
    )

    destino_jpg.parent.mkdir(parents=True, exist_ok=True)
    for qualidade in (94, 97, 99):
        ajustada.save(
            destino_jpg,
            format="JPEG",
            quality=qualidade,
            optimize=True,
            subsampling=0,
        )
        tam = destino_jpg.stat().st_size
        if tam > min_bytes:
            return {
                "arquivo": destino_jpg.name,
                "largura": largura,
                "altura": altura,
                "bytes": tam,
                "media_luma": round(media_luma, 1),
            }

    tam_final = destino_jpg.stat().st_size if destino_jpg.is_file() else 0
    destino_jpg.unlink(missing_ok=True)
    raise ValueError(
        f"Imagem salva ficou abaixo do minimo obrigatorio ({tam_final} bytes <= {min_bytes} bytes)."
    )


def reaproveitar_cena_anterior(
    origem_jpg: Path,
    destino_jpg: Path,
    indice_cena: int,
) -> dict[str, Any]:
    """Cria variacao de enquadramento (crop deslocado + zoom sutil) de uma cena valida anterior."""
    with Image.open(origem_jpg) as img_raw:
        img_raw.load()
        rgb = img_raw.convert("RGB")
        w, h = rgb.size
        # Zoom sutil de 14% com enquadramento deslocado para parecer nova tomada de camera
        nw, nh = int(w * 0.86), int(h * 0.86)
        deslocamentos = (
            (0, 0),
            (w - nw, 0),
            (int((w - nw) * 0.5), int((h - nh) * 0.2)),
            (0, h - nh),
            (w - nw, h - nh),
        )
        x0, y0 = deslocamentos[indice_cena % len(deslocamentos)]
        recorte = rgb.crop((x0, y0, x0 + nw, y0 + nh))
        buf = io.BytesIO()
        recorte.save(buf, format="PNG")
    info = validar_e_padronizar_imagem(buf.getvalue(), destino_jpg)
    info["reaproveitada"] = True
    return info


def _validar_video_mp4(caminho_mp4: Path) -> dict[str, Any]:
    """Valida que o clipe .mp4 baixado da fal.ai possui stream de video integro (> 50KB)."""
    if not caminho_mp4.is_file():
        raise ValueError(f"Arquivo de video ausente: {caminho_mp4}")
    tam = caminho_mp4.stat().st_size
    if tam <= TAMANHO_MIN_VIDEO_BYTES:
        raise ValueError(f"Video pequeno demais ({tam} bytes <= {TAMANHO_MIN_VIDEO_BYTES}).")
    res = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height:format=duration",
            "-of",
            "json",
            str(caminho_mp4),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    dados = json.loads(res.stdout)
    v_streams = [s for s in dados.get("streams", []) if s.get("codec_type") == "video"]
    if not v_streams:
        raise ValueError("Arquivo MP4 sem stream de video valido.")
    dur = float((dados.get("format") or {}).get("duration") or 0.0)
    if dur < 0.5:
        raise ValueError(f"Duracao de video invalida: {dur:.2f}s.")
    return {
        "arquivo": caminho_mp4.name,
        "largura": int(v_streams[0].get("width") or 0),
        "altura": int(v_streams[0].get("height") or 0),
        "duracao_s": round(dur, 3),
        "bytes": tam,
    }


def gerar_video_fal_ai(
    prompt: str,
    destino_mp4: Path,
    fal_key: str,
    *,
    modelo: str = FAL_ENDPOINT_T2V,
    timeout_total_s: float = 180.0,
    poll_s: float = 4.0,
) -> dict[str, Any]:
    """Gera clipe de video IA 9:16 via API REST da fal.ai (fal-ai/wan/v2.1/t2v-480p)."""
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "prompt": garantir_estilo_prompt(prompt),
        "aspect_ratio": "9:16",
        "resolution": "480p",
        "num_frames": 81,
        "frames_per_second": 16,
    }
    submit_url = f"{FAL_QUEUE_BASE}/{modelo}"
    req = urllib.request.Request(
        submit_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        sub = json.loads(resp.read().decode("utf-8"))

    status_url = str(sub.get("status_url") or "")
    response_url = str(sub.get("response_url") or "")
    request_id = str(sub.get("request_id") or "")
    if not status_url and request_id:
        status_url = f"{FAL_QUEUE_BASE}/{modelo}/requests/{request_id}/status"
    if not response_url and request_id:
        response_url = f"{FAL_QUEUE_BASE}/{modelo}/requests/{request_id}"

    # Caso a resposta ja traga video direto (sincrono)
    video_url = ""
    if isinstance(sub.get("video"), dict) and sub["video"].get("url"):
        video_url = str(sub["video"]["url"])
    else:
        if not status_url or not response_url:
            raise RuntimeError(f"Resposta fal.ai inesperada sem status_url/video: {list(sub.keys())}")
        deadline = time.monotonic() + timeout_total_s
        while time.monotonic() < deadline:
            req_st = urllib.request.Request(status_url, headers=headers, method="GET")
            with urllib.request.urlopen(req_st, timeout=30) as r_st:
                st = json.loads(r_st.read().decode("utf-8"))
            estado = str(st.get("status", "")).upper()
            if estado == "COMPLETED":
                break
            if estado in ("FAILED", "CANCELLED", "ERROR"):
                raise RuntimeError(f"fal.ai job falhou (status={estado}): {st.get('error') or st}")
            time.sleep(poll_s)
        else:
            raise TimeoutError(f"Timeout ({timeout_total_s:.0f}s) aguardando video na fal.ai ({request_id}).")

        req_res = urllib.request.Request(response_url, headers=headers, method="GET")
        with urllib.request.urlopen(req_res, timeout=45) as r_res:
            res_dados = json.loads(r_res.read().decode("utf-8"))
        vid_obj = res_dados.get("video") or (res_dados.get("data") or {}).get("video")
        if isinstance(vid_obj, dict) and vid_obj.get("url"):
            video_url = str(vid_obj["url"])

    if not video_url:
        raise RuntimeError("fal.ai concluiu sem retornar video.url.")

    destino_mp4.parent.mkdir(parents=True, exist_ok=True)
    req_dl = urllib.request.Request(video_url, method="GET")
    with urllib.request.urlopen(req_dl, timeout=90) as r_dl:
        destino_mp4.write_bytes(r_dl.read())

    info = _validar_video_mp4(destino_mp4)
    info["tipo"] = "video"
    info["modelo"] = modelo
    return info


def _extrair_bytes_imagem_genai_response(resp: Any) -> bytes | None:
    """Extrai bytes de imagem de uma resposta google-genai (generate_content ou generate_images)."""
    # 1. Resposta de generate_images (Imagen 3)
    gen_imgs = getattr(resp, "generated_images", None)
    if gen_imgs:
        for gi in gen_imgs:
            img_obj = getattr(gi, "image", None)
            raw = getattr(img_obj, "image_bytes", None)
            if isinstance(raw, (bytes, bytearray)) and raw:
                return bytes(raw)
            if isinstance(raw, str) and raw:
                return base64.b64decode(raw)

    # 2. Resposta de generate_content (Gemini native image generation)
    candidatos = getattr(resp, "candidates", None) or []
    for cand in candidatos:
        content = getattr(cand, "content", None)
        partes = getattr(content, "parts", None) or []
        for parte in partes:
            inline = getattr(parte, "inline_data", None)
            if inline is None:
                continue
            mime = str(getattr(inline, "mime_type", "") or "").lower()
            raw = getattr(inline, "data", None)
            if raw and (not mime or "image" in mime):
                if isinstance(raw, (bytes, bytearray)):
                    return bytes(raw)
                if isinstance(raw, str):
                    return base64.b64decode(raw)
    return None


def _chamar_modelo_gemini_imagem(client: Any, types_mod: Any, modelo: str, prompt: str) -> bytes:
    """Invoca um modelo especifico de imagem no SDK google-genai (Gemini Image ou Imagen 3)."""
    if modelo.startswith("imagen-"):
        cfg_cls = getattr(types_mod, "GenerateImagesConfig", None)
        if cfg_cls is not None:
            cfg = cfg_cls(number_of_images=1, aspect_ratio="9:16")
        else:
            cfg = {"number_of_images": 1, "aspect_ratio": "9:16"}
        resp = client.models.generate_images(model=modelo, prompt=prompt, config=cfg)
        raw = _extrair_bytes_imagem_genai_response(resp)
        if not raw:
            raise RuntimeError(f"Modelo {modelo} retornou resposta sem imagem.")
        return raw

    # Modelos nativos Gemini Image (gemini-2.5-flash-image / gemini-2.0-flash-preview-image-generation)
    tentativas_modalidades: list[list[str]] = (
        [["IMAGE"], ["TEXT", "IMAGE"]]
        if "2.5" in modelo
        else [["IMAGE", "TEXT"], ["IMAGE"]]
    )
    img_cfg_cls = getattr(types_mod, "ImageConfig", None)
    gen_cfg_cls = getattr(types_mod, "GenerateContentConfig", None)

    ultimo_erro: Exception | None = None
    for mods in tentativas_modalidades:
        for usar_img_cfg in (True, False):
            try:
                kwargs: dict[str, Any] = {"response_modalities": mods}
                if usar_img_cfg and img_cfg_cls is not None:
                    kwargs["image_config"] = img_cfg_cls(aspect_ratio="9:16")
                cfg = gen_cfg_cls(**kwargs) if gen_cfg_cls is not None else kwargs
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=cfg,
                )
                raw = _extrair_bytes_imagem_genai_response(resp)
                if raw:
                    return raw
                ultimo_erro = RuntimeError(f"Modelo {modelo} (modalidades={mods}) nao retornou inline_data de imagem.")
            except Exception as exc:
                ultimo_erro = exc
                msg_low = str(exc).lower()
                # Se rejeitou apenas image_config/aspect_ratio, tenta sem image_config na proxima iteracao
                if usar_img_cfg and ("image_config" in msg_low or "aspect_ratio" in msg_low or "unknown field" in msg_low):
                    continue
                # Se rejeitou modalidade apenas IMAGE, avanca para ["TEXT", "IMAGE"]
                if "modalit" in msg_low:
                    break
                raise
    assert ultimo_erro is not None
    raise ultimo_erro


def _eh_erro_temporario(exc: Exception) -> bool:
    txt = str(exc).lower()
    return any(tok in txt for tok in ("429", "resource_exhausted", "quota", "503", "500", "502", "504", "timeout", "temporar"))


def _eh_erro_modelo_indisponivel(exc: Exception) -> bool:
    txt = str(exc).lower()
    return any(tok in txt for tok in ("404", "not found", "not_found", "not supported", "is not found", "permission_denied"))


def gerar_imagem_gemini_com_cache(
    prompt: str,
    destino_jpg: Path,
    api_key: str,
    cache_modelo: dict[str, str],
    *,
    client: Any = None,
    types_mod: Any = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Gera imagem 1080x1920 via google-genai usando cache do primeiro modelo funcional na conta."""
    if client is None or types_mod is None:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]

        client = genai.Client(api_key=api_key)
        types_mod = types

    prompt_final = garantir_estilo_prompt(prompt)
    modelo_cache = cache_modelo.get("modelo", "")
    fila = [modelo_cache] + [m for m in MODELOS_GEMINI_IMAGEM if m != modelo_cache] if modelo_cache else list(MODELOS_GEMINI_IMAGEM)

    ultimo_erro: Exception | None = None
    for modelo in fila:
        for tentativa in range(max_retries + 1):
            try:
                raw = _chamar_modelo_gemini_imagem(client, types_mod, modelo, prompt_final)
                info = validar_e_padronizar_imagem(raw, destino_jpg)
                if cache_modelo.get("modelo") != modelo:
                    cache_modelo["modelo"] = modelo
                    print(f"Modelo Gemini Image em cache para esta rodada: {modelo}", flush=True)
                info["tipo"] = "imagem"
                info["modelo"] = modelo
                info["reaproveitada"] = False
                return info
            except Exception as exc:
                ultimo_erro = exc
                if _eh_erro_modelo_indisponivel(exc):
                    print(f"AVISO modelo '{modelo}' indisponivel ({exc}). Testando proximo modelo...", flush=True)
                    if cache_modelo.get("modelo") == modelo:
                        cache_modelo.pop("modelo", None)
                    break
                if _eh_erro_temporario(exc) and tentativa < max_retries:
                    espera = 4.0 * (tentativa + 1)
                    print(
                        f"AVISO Gemini Image [{modelo}] instabilidade ({exc}) tentativa {tentativa + 1}/{max_retries + 1}. "
                        f"Aguardando {espera:.1f}s...",
                        flush=True,
                    )
                    time.sleep(espera)
                    continue
                print(f"AVISO Gemini Image [{modelo}] falhou: {exc}", flush=True)
                break

    assert ultimo_erro is not None
    raise ultimo_erro


def _limpar_cenas_antigas_se_novo_video(saida_dir: Path, video_id: int, forcar: bool) -> None:
    manifesto_path = saida_dir / MANIFESTO_NOME
    deve_limpar = forcar
    if not deve_limpar and manifesto_path.is_file():
        try:
            ant = json.loads(manifesto_path.read_text(encoding="utf-8"))
            if int(ant.get("video_id", -1)) != int(video_id):
                deve_limpar = True
        except Exception:
            deve_limpar = True
    if deve_limpar and saida_dir.is_dir():
        for arq in list(saida_dir.glob("cena_*.jpg")) + list(saida_dir.glob("cena_*.mp4")):
            arq.unlink(missing_ok=True)
        manifesto_path.unlink(missing_ok=True)


def gerar_midias_todas_cenas(
    cenas_path: Path = ARQUIVO_CENAS_PADRAO,
    saida_dir: Path = PASTA_SAIDA_PADRAO,
    *,
    max_cenas: int | None = None,
    forcar: bool = False,
) -> dict[str, Any]:
    """Gera midia 9:16 (video fal.ai se FAL_KEY ativa, ou imagem 1080x1920 Gemini) para cada cena."""
    carregar_env()
    if not cenas_path.is_file():
        raise FileNotFoundError(f"cenas.json nao encontrado: {cenas_path}")

    cenas_dados = json.loads(cenas_path.read_text(encoding="utf-8"))
    lista_cenas = cenas_dados.get("cenas")
    if not isinstance(lista_cenas, list) or not lista_cenas:
        raise RuntimeError("cenas.json nao possui lista valida em 'cenas'.")

    if max_cenas is not None and max_cenas > 0:
        lista_cenas = lista_cenas[: int(max_cenas)]

    video_id = int(cenas_dados.get("video_id") or 0)
    titulo = str(cenas_dados.get("titulo") or "Episodio")
    saida_dir.mkdir(parents=True, exist_ok=True)
    _limpar_cenas_antigas_se_novo_video(saida_dir, video_id=video_id, forcar=forcar)

    fal_key = os.environ.get("FAL_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not fal_key and not gemini_key:
        raise RuntimeError(
            "Nenhuma credencial de midia encontrada (GEMINI_API_KEY e FAL_KEY ausentes). "
            "Configure GEMINI_API_KEY (gratuito) ou FAL_KEY nos Secrets."
        )

    client_genai = None
    types_mod = None
    if gemini_key:
        try:
            from google import genai  # type: ignore[import-not-found]
            from google.genai import types  # type: ignore[import-not-found]

            client_genai = genai.Client(api_key=gemini_key)
            types_mod = types
        except ImportError as exc:
            if not fal_key:
                raise RuntimeError("Biblioteca google-genai nao instalada. Rode: pip install google-genai") from exc
            print(f"AVISO google-genai ausente ({exc}); operando apenas com FAL_KEY.", flush=True)

    print(
        f"Estacao 3A (gerar_midia_cenas): Video {video_id:02d} '{titulo}' | "
        f"{len(lista_cenas)} cena(s) | FAL_KEY={'ATIVA (' + FAL_ENDPOINT_T2V + ')' if fal_key else 'desativada (Gemini Image gratuito)'}",
        flush=True,
    )

    cache_modelo: dict[str, str] = {}
    itens_manifesto: list[dict[str, Any]] = []
    ultima_imagem_valida: Path | None = None
    total_geradas_originais = 0

    for idx, cena in enumerate(lista_cenas, start=1):
        cena_id = str(cena.get("id") or f"cena_{idx:02d}")
        fala = str(cena.get("fala") or "").strip()
        prompt = garantir_estilo_prompt(str(cena.get("prompt_imagem") or fala))
        destino_mp4 = saida_dir / f"cena_{idx:02d}.mp4"
        destino_jpg = saida_dir / f"cena_{idx:02d}.jpg"

        # Reaproveita cache local da mesma rodada quando --forcar nao foi passado
        if not forcar and fal_key and destino_mp4.is_file() and destino_mp4.stat().st_size > TAMANHO_MIN_VIDEO_BYTES:
            try:
                info_v = _validar_video_mp4(destino_mp4)
                info_v.update({"indice": idx, "id": cena_id, "tipo": "video", "modelo": "cache_local", "reaproveitada": False})
                itens_manifesto.append(info_v)
                total_geradas_originais += 1
                print(f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_mp4.name} (cache video {info_v['bytes'] / 1024:.1f} KB)", flush=True)
                continue
            except Exception:
                destino_mp4.unlink(missing_ok=True)
        if not forcar and not fal_key and destino_jpg.is_file() and destino_jpg.stat().st_size > TAMANHO_MIN_IMAGEM_BYTES:
            try:
                info_i = validar_e_padronizar_imagem(destino_jpg.read_bytes(), destino_jpg)
                info_i.update({"indice": idx, "id": cena_id, "tipo": "imagem", "modelo": "cache_local", "reaproveitada": False})
                itens_manifesto.append(info_i)
                ultima_imagem_valida = destino_jpg
                total_geradas_originais += 1
                print(f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_jpg.name} (cache imagem {info_i['bytes'] / 1024:.1f} KB)", flush=True)
                continue
            except Exception:
                destino_jpg.unlink(missing_ok=True)

        # 1. Tenta Video IA via fal.ai se FAL_KEY estiver configurada
        if fal_key:
            try:
                info_v = gerar_video_fal_ai(prompt, destino_mp4, fal_key)
                destino_jpg.unlink(missing_ok=True)
                info_v.update({"indice": idx, "id": cena_id, "reaproveitada": False})
                itens_manifesto.append(info_v)
                total_geradas_originais += 1
                print(
                    f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_mp4.name} OK via fal.ai "
                    f"({info_v['largura']}x{info_v['altura']}, {info_v['duracao_s']:.2f}s, {info_v['bytes'] / 1024:.1f} KB)",
                    flush=True,
                )
                continue
            except Exception as exc:
                destino_mp4.unlink(missing_ok=True)
                print(
                    f"  AVISO [{idx:02d}/{len(lista_cenas):02d}] fal.ai falhou ({exc}); "
                    f"fazendo fallback automatico para Gemini Image API...",
                    flush=True,
                )

        # 2. Modo gratuito padrao (ou fallback da fal.ai): Gemini Image API com cache de modelo
        gerada = False
        if gemini_key and client_genai is not None:
            try:
                info_i = gerar_imagem_gemini_com_cache(
                    prompt=prompt,
                    destino_jpg=destino_jpg,
                    api_key=gemini_key,
                    cache_modelo=cache_modelo,
                    client=client_genai,
                    types_mod=types_mod,
                )
                destino_mp4.unlink(missing_ok=True)
                info_i.update({"indice": idx, "id": cena_id})
                itens_manifesto.append(info_i)
                ultima_imagem_valida = destino_jpg
                total_geradas_originais += 1
                gerada = True
                print(
                    f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_jpg.name} OK via {info_i['modelo']} "
                    f"({info_i['largura']}x{info_i['altura']}, {info_i['bytes'] / 1024:.1f} KB)",
                    flush=True,
                )
            except Exception as exc_orig:
                print(
                    f"  AVISO [{idx:02d}/{len(lista_cenas):02d}] prompt original falhou ({exc_orig}). "
                    f"Reescrevendo prompt de forma neutra para evitar filtro de seguranca...",
                    flush=True,
                )
                prompt_neutro = reescrever_prompt_neutro(prompt, fala_fallback=fala)
                try:
                    info_n = gerar_imagem_gemini_com_cache(
                        prompt=prompt_neutro,
                        destino_jpg=destino_jpg,
                        api_key=gemini_key,
                        cache_modelo=cache_modelo,
                        client=client_genai,
                        types_mod=types_mod,
                    )
                    destino_mp4.unlink(missing_ok=True)
                    info_n.update({"indice": idx, "id": cena_id, "prompt_neutro": True})
                    itens_manifesto.append(info_n)
                    ultima_imagem_valida = destino_jpg
                    total_geradas_originais += 1
                    gerada = True
                    print(
                        f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_jpg.name} OK apos reescrita neutra "
                        f"via {info_n['modelo']} ({info_n['bytes'] / 1024:.1f} KB)",
                        flush=True,
                    )
                except Exception as exc_neutro:
                    print(
                        f"  AVISO [{idx:02d}/{len(lista_cenas):02d}] reescrita neutra tambem falhou ({exc_neutro}).",
                        flush=True,
                    )

        # 3. Ultimo recurso isolado: reaproveita cena valida anterior com enquadramento diferente (nunca tela preta)
        if not gerada:
            if ultima_imagem_valida is not None and ultima_imagem_valida.is_file():
                info_r = reaproveitar_cena_anterior(ultima_imagem_valida, destino_jpg, indice_cena=idx)
                info_r.update(
                    {
                        "indice": idx,
                        "id": cena_id,
                        "tipo": "imagem",
                        "modelo": f"reaproveitada:{ultima_imagem_valida.name}",
                    }
                )
                itens_manifesto.append(info_r)
                print(
                    f"  [{idx:02d}/{len(lista_cenas):02d}] {destino_jpg.name} reaproveitada de {ultima_imagem_valida.name} "
                    f"com enquadramento distinto ({info_r['bytes'] / 1024:.1f} KB).",
                    flush=True,
                )
            else:
                raise RuntimeError(
                    f"Falha critica na cena {idx:02d}/{len(lista_cenas):02d}: nenhuma midia valida anterior "
                    f"disponivel para reaproveitamento. Verifique GEMINI_API_KEY / FAL_KEY."
                )

    if total_geradas_originais == 0:
        raise RuntimeError("Nenhuma midia original foi gerada com sucesso.")

    manifesto = {
        "video_id": video_id,
        "titulo": titulo,
        "total_cenas": len(itens_manifesto),
        "originais_geradas": total_geradas_originais,
        "fal_ativo": bool(fal_key),
        "modelo_imagem_cache": cache_modelo.get("modelo", ""),
        "itens": itens_manifesto,
    }
    (saida_dir / MANIFESTO_NOME).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Midias prontas em {saida_dir}: {len(itens_manifesto)} arquivo(s) validados "
        f"({total_geradas_originais} originais | modelo_cache={manifesto['modelo_imagem_cache'] or 'fal.ai'}).",
        flush=True,
    )
    return manifesto


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera midia 9:16 (Video IA via FAL_KEY ou Imagem 1080x1920 via Gemini Image API) para cada cena."
    )
    parser.add_argument("--cenas", type=Path, default=ARQUIVO_CENAS_PADRAO, help="Caminho de cenas.json.")
    parser.add_argument("--saida-dir", type=Path, default=PASTA_SAIDA_PADRAO, help="Pasta de saida (padrao: output/cenas).")
    parser.add_argument("--max-cenas", type=int, default=None, help="Limita quantidade de cenas (ex.: 2 no modo teste).")
    parser.add_argument("--forcar", action="store_true", help="Regera todas as cenas ignorando cache local.")
    args = parser.parse_args()

    cenas_p = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    saida_p = args.saida_dir if args.saida_dir.is_absolute() else (RAIZ / args.saida_dir)
    gerar_midias_todas_cenas(
        cenas_path=cenas_p,
        saida_dir=saida_p,
        max_cenas=args.max_cenas,
        forcar=args.forcar,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
