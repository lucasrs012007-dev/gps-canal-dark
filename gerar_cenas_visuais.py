"""Estacao 3A (Motor Hibrido V7): gera 1 imagem vertical 1080x1920 unica por cena de cenas.json.

Fluxo 100% gratuito e resiliente com fallback automatico:
1. Tenta primeiro via API Gemini/Imagen usando GEMINI_API_KEY (quando o SDK `google-genai`
   estiver instalado e habilitado na conta).
2. Em caso de erro, cota ou indisponibilidade, faz fallback automatico para o endpoint gratuito
   `https://image.pollinations.ai/prompt/<prompt_encoded>?width=1080&height=1920&nologo=true&seed=<seed>`
   com retry, backoff exponencial e validacao estrita de imagem valida (> 20 KB + cabecalho real).
3. Normaliza cada imagem para JPEG Full HD vertical exato (1080x1920) em `output/cenas/cena_01.jpg`,
   `cena_02.jpg`, etc., gravando manifesto em `output/cenas/manifest.json`.

Uso (na raiz do repositorio):
    python3 gerar_cenas_visuais.py
    python3 gerar_cenas_visuais.py --max-cenas 2
    python3 gerar_cenas_visuais.py --mock
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
PASTA_CENAS_PADRAO = RAIZ / "output" / "cenas"

LARGURA = 1080
ALTURA = 1920
MIN_BYTES_IMAGEM = 20 * 1024  # Validacao estrita: > 20 KB
MAX_CHARS_PROMPT_URL = 620
TIMEOUT_POLLINATIONS_S = 90.0
MAX_RETRIES_POLLINATIONS = 4
USER_AGENT_PADRAO = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt/"
GEMINI_IMAGEN_MODELOS: tuple[str, ...] = (
    "imagen-3.0-generate-002",
    "imagen-4.0-fast-generate-001",
)
from pipeline.config_canal import carregar_config_canal  # noqa: E402

GEMINI_IMAGE_CONTENT_MODELOS: tuple[str, ...] = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-exp-image-generation",
)
ESTILO_VISUAL_PADRAO = str(carregar_config_canal()["estilo_visual_prompt"])


def obter_estilo_visual_ativo(caminho_config: Path | str | None = None) -> str:
    """Retorna o estilo visual configurado em config_canal.json (com fallback seguro)."""
    return str(carregar_config_canal(caminho_config)["estilo_visual_prompt"])

CORES_MOOD_FALLBACK: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    "navy": ((9, 15, 30), (18, 38, 68), (56, 217, 255)),
    "violet": ((19, 10, 38), (44, 18, 78), (168, 85, 247)),
    "red": ((38, 8, 12), (76, 14, 20), (255, 59, 48)),
    "yellow": ((30, 24, 10), (66, 50, 14), (255, 212, 0)),
    "cctv": ((14, 20, 18), (32, 42, 38), (160, 220, 180)),
    "dark": ((6, 8, 14), (18, 22, 34), (100, 130, 175)),
}


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


def detectar_formato_imagem(dados: bytes) -> str | None:
    """Identifica o formato real pelos magic bytes (rejeita HTML, JSON ou lixo)."""
    if len(dados) < 12:
        return None
    if dados[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


def validar_bytes_imagem(dados: bytes, min_bytes: int = MIN_BYTES_IMAGEM) -> tuple[bool, str]:
    """Confirma que o buffer baixado e uma imagem real com tamanho > 20 KB."""
    tam = len(dados)
    if tam <= min_bytes:
        return False, f"arquivo muito pequeno ({tam} bytes <= {min_bytes} bytes)"
    fmt = detectar_formato_imagem(dados)
    if fmt is None:
        amostra = dados[:64].decode("utf-8", errors="ignore").replace("\n", " ").strip()
        return False, f"cabecalho nao e imagem valida (inicio={amostra!r})"
    return True, fmt


def validar_arquivo_imagem(caminho: Path, min_bytes: int = MIN_BYTES_IMAGEM) -> tuple[bool, str]:
    """Valida arquivo em disco: existe, > 20 KB, magic bytes reais e decodificavel."""
    if not caminho.is_file():
        return False, "arquivo inexistente"
    try:
        dados = caminho.read_bytes()
    except OSError as exc:
        return False, f"erro ao ler arquivo ({exc})"
    ok, info = validar_bytes_imagem(dados, min_bytes=min_bytes)
    if not ok:
        return False, info

    try:
        from PIL import Image  # type: ignore[import-not-found]

        with Image.open(caminho) as im:
            im.verify()
        with Image.open(caminho) as im2:
            w, h = im2.size
        if w < 256 or h < 256:
            return False, f"resolucao baixa demais ({w}x{h})"
        return True, f"{info} {w}x{h} ({len(dados)} bytes)"
    except ImportError:
        pass
    except Exception as exc:
        return False, f"imagem corrompida na decodificacao ({exc})"

    if shutil.which("ffprobe"):
        try:
            res = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0:s=x",
                    str(caminho),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
            dims = res.stdout.strip()
            if "x" in dims:
                w_s, h_s = dims.split("x", 1)
                if int(w_s) < 256 or int(h_s) < 256:
                    return False, f"resolucao baixa demais ({dims})"
                return True, f"{info} {dims} ({len(dados)} bytes)"
        except Exception as exc:
            return False, f"ffprobe rejeitou a imagem ({exc})"

    return True, f"{info} ({len(dados)} bytes)"


def normalizar_para_jpeg_1080x1920(origem: Path, destino: Path) -> Path:
    """Converte e enquadra a imagem em JPEG vertical exato 1080x1920 com alta qualidade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = destino.with_suffix(".tmp.jpg")

    try:
        from PIL import Image, ImageOps  # type: ignore[import-not-found]

        with Image.open(origem) as im:
            im_rgb = im.convert("RGB")
            ajustada = ImageOps.fit(im_rgb, (LARGURA, ALTURA), method=Image.Resampling.LANCZOS)
            ajustada.save(tmp_out, format="JPEG", quality=92, optimize=True)
        tmp_out.replace(destino)
        return destino
    except ImportError:
        pass

    if not shutil.which("ffmpeg"):
        raise RuntimeError("Nem Pillow nem ffmpeg estao disponiveis para normalizar a imagem para 1080x1920.")

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(origem),
        "-vf",
        f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA}",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(tmp_out),
    ]
    subprocess.run(cmd, check=True, timeout=30)
    tmp_out.replace(destino)
    return destino


def calcular_seed_cena(video_id: int, slug: str, idx_1based: int, prompt: str) -> int:
    """Gera seed inteira deterministica por cena para consistencia e variacao controlada."""
    chave = f"{video_id}|{slug}|cena_{idx_1based:02d}|{prompt[:120]}"
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 899_999) + 100_000


def _encurtar_prompt_para_url(
    prompt: str,
    max_chars: int = MAX_CHARS_PROMPT_URL,
    estilo_visual: str | None = None,
) -> str:
    limpo = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if len(limpo) <= max_chars:
        return limpo
    estilo = (estilo_visual or "").strip() or obter_estilo_visual_ativo()
    estilo_low = estilo.lower()
    if estilo_low in limpo.lower():
        pos = limpo.lower().rfind(estilo_low)
        corpo = limpo[:pos].rstrip(" ,.;")
        cota = max(80, max_chars - len(estilo) - 2)
        if len(corpo) > cota:
            corpo = corpo[:cota].rsplit(" ", 1)[0].rstrip(" ,.;")
        return f"{corpo}, {estilo}"
    return limpo[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;")


def montar_url_pollinations(
    prompt: str,
    seed: int,
    largura: int = LARGURA,
    altura: int = ALTURA,
) -> str:
    """Monta URL gratuita do Pollinations em 1080x1920 sem marca d'agua."""
    prompt_seguro = _encurtar_prompt_para_url(prompt)
    prompt_encoded = urllib.parse.quote(prompt_seguro, safe="")
    return (
        f"{POLLINATIONS_BASE_URL}{prompt_encoded}"
        f"?width={int(largura)}&height={int(altura)}&nologo=true&seed={int(seed)}"
    )


def obter_prompt_cena(
    cena: dict,
    idx_0based: int,
    total_cenas: int,
    protagonista: dict | None = None,
    estilo_visual: str | None = None,
) -> str:
    """Retorna prompt_imagem da cena em cenas.json (com fallback usando estilo_visual_prompt de config_canal.json)."""
    estilo = (estilo_visual or "").strip() or obter_estilo_visual_ativo()
    bruto = str(cena.get("prompt_imagem", "") or "").strip()
    if len(bruto) >= 24:
        if estilo.lower() not in bruto.lower():
            return f"{bruto.rstrip(' ,.;')}, {estilo}"
        return bruto

    try:
        from pipeline.diretor_ia import gerar_prompt_imagem_cena

        props = cena.get("props") if isinstance(cena.get("props"), dict) else {}
        texto_pista = str(props.get("celular_mensagem", "") or cena.get("id", ""))
        gerado = gerar_prompt_imagem_cena(
            texto_bloco=texto_pista,
            modulo=str(cena.get("modulo", "corredor_escuro")),
            mood=str(cena.get("mood", "navy")),
            expressao=str(cena.get("expressao", "worry")),
            camera=str(cena.get("camera", "push_in")),
            props=props,
            protagonista=protagonista,
            idx=idx_0based,
            total=total_cenas,
        )
        if estilo.lower() not in gerado.lower():
            return f"{gerado.rstrip(' ,.;')}, {estilo}"
        return gerado
    except Exception:
        mood = str(cena.get("mood", "navy"))
        mod = str(cena.get("modulo", "corredor_escuro")).replace("_", " ")
        return (
            f"Dramatic vertical cinematic scene in a dark {mod} with {mood} atmospheric rim lighting, "
            f"scene beat {idx_0based + 1}, {estilo}"
        )


def gerar_imagem_gemini_imagen(
    prompt: str,
    destino_raw: Path,
    api_key: str,
) -> tuple[bool, str, bool]:
    """Tenta gerar imagem via SDK oficial google-genai (Imagen / Gemini Image).

    Retorna (sucesso, detalhe, erro_permanente). Quando erro_permanente=True,
    as proximas cenas pulam direto para o fallback Pollinations sem desperdicar tempo.
    """
    chave = str(api_key or "").strip()
    if not chave or len(chave) < 10:
        return False, "GEMINI_API_KEY ausente", True

    try:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]
    except Exception:
        return False, "SDK google-genai nao instalado", True

    segredos = (chave,)
    erros: list[str] = []
    todos_permanentes = True

    try:
        client = genai.Client(api_key=chave)
    except Exception as exc:
        return False, _mascarar_segredos(f"Falha ao criar cliente google-genai: {exc}", segredos), True

    modelo_env = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
    modelos_imagen = (modelo_env, *GEMINI_IMAGEN_MODELOS) if modelo_env else GEMINI_IMAGEN_MODELOS

    for modelo in modelos_imagen:
        if not modelo:
            continue
        try:
            resp = client.models.generate_images(
                model=modelo,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                    output_mime_type="image/jpeg",
                ),
            )
            imagens = getattr(resp, "generated_images", None) or []
            if imagens:
                img_obj = getattr(imagens[0], "image", None)
                raw_bytes = getattr(img_obj, "image_bytes", None)
                if isinstance(raw_bytes, (bytes, bytearray)):
                    ok, info = validar_bytes_imagem(bytes(raw_bytes))
                    if ok:
                        destino_raw.write_bytes(bytes(raw_bytes))
                        return True, f"gemini-imagen:{modelo} ({info})", False
                    erros.append(f"{modelo}: imagem invalida ({info})")
                    todos_permanentes = False
                    continue
            erros.append(f"{modelo}: resposta sem generated_images")
            todos_permanentes = False
        except Exception as exc:
            msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
            erros.append(f"{modelo}: {msg[:180]}")
            low = msg.lower()
            if not any(tok in low for tok in ("403", "404", "billing", "not found", "permission", "billed", "api_key")):
                todos_permanentes = False

    # Tentativa secundaria no mesmo SDK: geracao nativa de imagem via Gemini Flash Image
    for modelo in GEMINI_IMAGE_CONTENT_MODELOS:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            candidatos = getattr(resp, "candidates", None) or []
            for cand in candidatos:
                conteudo = getattr(cand, "content", None)
                partes = getattr(conteudo, "parts", None) or []
                for parte in partes:
                    inline = getattr(parte, "inline_data", None)
                    raw_bytes = getattr(inline, "data", None) if inline is not None else None
                    if isinstance(raw_bytes, (bytes, bytearray)):
                        ok, info = validar_bytes_imagem(bytes(raw_bytes))
                        if ok:
                            destino_raw.write_bytes(bytes(raw_bytes))
                            return True, f"gemini-image:{modelo} ({info})", False
            erros.append(f"{modelo}: resposta sem inline_data de imagem")
            todos_permanentes = False
        except Exception as exc:
            msg = _mascarar_segredos(f"{type(exc).__name__}: {exc}", segredos)
            erros.append(f"{modelo}: {msg[:180]}")
            low = msg.lower()
            if not any(tok in low for tok in ("403", "404", "billing", "not found", "permission", "quota", "429")):
                todos_permanentes = False

    resumo = " | ".join(erros[:3]) or "nenhum modelo de imagem Gemini disponivel"
    return False, resumo, todos_permanentes


def gerar_imagem_pollinations(
    prompt: str,
    seed: int,
    destino_raw: Path,
    *,
    max_tentativas: int = MAX_RETRIES_POLLINATIONS,
    timeout_s: float = TIMEOUT_POLLINATIONS_S,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    """Baixa imagem 1080x1920 do endpoint gratuito Pollinations com retry e validacao > 20 KB."""
    opener = urlopen_fn or urllib.request.urlopen
    tentativas = max(1, int(max_tentativas))
    ultimo_erro = "falha desconhecida no Pollinations"

    for tentativa in range(1, tentativas + 1):
        seed_atual = int(seed) + (tentativa - 1)
        url = montar_url_pollinations(prompt, seed=seed_atual, largura=LARGURA, altura=ALTURA)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT_PADRAO,
                "Accept": "image/jpeg,image/png,image/webp,image/*;q=0.8",
            },
            method="GET",
        )
        try:
            with opener(req, timeout=timeout_s) as resp:
                dados = resp.read()
            ok, info = validar_bytes_imagem(dados, min_bytes=MIN_BYTES_IMAGEM)
            if ok:
                destino_raw.write_bytes(dados)
                return True, f"pollinations (tentativa {tentativa}, seed={seed_atual}, {info}, {len(dados)} bytes)"
            ultimo_erro = f"tentativa {tentativa}/{tentativas}: resposta invalida ({info})"
        except urllib.error.HTTPError as exc:
            ultimo_erro = f"tentativa {tentativa}/{tentativas}: HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ultimo_erro = f"tentativa {tentativa}/{tentativas}: erro de rede ({type(exc).__name__}: {exc})"

        if tentativa < tentativas:
            espera = min(15.0, 3.0 * (2 ** (tentativa - 1)))
            print(
                f"  AVISO Pollinations ({ultimo_erro}). Nova tentativa em {espera:.0f}s...",
                flush=True,
            )
            sleep_fn(espera)

    return False, ultimo_erro


def gerar_imagem_fallback_procedural(
    destino_jpg: Path,
    mood: str = "navy",
    seed: int = 123456,
    indice: int = 1,
) -> Path:
    """Gera quadro atmosferico 1080x1920 (> 25 KB) para --mock ou emergencia sem rede."""
    destino_jpg.parent.mkdir(parents=True, exist_ok=True)
    c0, c1, ac = CORES_MOOD_FALLBACK.get(str(mood).lower(), CORES_MOOD_FALLBACK["navy"])

    try:
        import random
        from PIL import Image, ImageDraw, ImageFilter  # type: ignore[import-not-found]

        rng = random.Random(int(seed) + indice * 97)
        w_s, h_s = 270, 480
        base = Image.new("RGB", (w_s, h_s), c0)
        dr = ImageDraw.Draw(base)
        for y in range(h_s):
            t = y / max(1, h_s - 1)
            cor = (
                int(c0[0] * (1.0 - t) + c1[0] * t),
                int(c0[1] * (1.0 - t) + c1[1] * t),
                int(c0[2] * (1.0 - t) + c1[2] * t),
            )
            dr.line([(0, y), (w_s, y)], fill=cor)

        cx = int(w_s * (0.28 + ((indice * 0.21) % 0.44)))
        cy = int(h_s * (0.24 + ((indice * 0.15) % 0.30)))
        r_luz = 115
        luz = (
            min(255, int(c1[0] * 0.45 + ac[0] * 0.55)),
            min(255, int(c1[1] * 0.45 + ac[1] * 0.55)),
            min(255, int(c1[2] * 0.45 + ac[2] * 0.55)),
        )
        dr.ellipse((cx - r_luz, cy - r_luz, cx + r_luz, cy + r_luz), fill=luz)
        base = base.filter(ImageFilter.GaussianBlur(radius=34))

        im = base.resize((LARGURA, ALTURA), Image.Resampling.BICUBIC)
        dr_hd = ImageDraw.Draw(im)
        # Elementos arquitetonicos / silhuetas sutis para textura 2.5D e tamanho > 25 KB
        for k in range(18):
            x0 = rng.randint(-60, LARGURA - 60)
            y0 = rng.randint(int(ALTURA * 0.42), ALTURA - 40)
            bw = rng.randint(80, 260)
            bh = rng.randint(140, 560)
            fator = 0.25 + 0.35 * (k / 18.0)
            cor_b = (int(c0[0] * fator), int(c0[1] * fator), int(c0[2] * fator))
            dr_hd.rectangle((x0, y0, x0 + bw, y0 + bh), fill=cor_b)
        for _ in range(90):
            px = rng.randint(24, LARGURA - 24)
            py = rng.randint(40, int(ALTURA * 0.72))
            pr = rng.randint(2, 6)
            dr_hd.ellipse((px - pr, py - pr, px + pr, py + pr), fill=ac)

        im = im.filter(ImageFilter.GaussianBlur(radius=1.5))
        im.save(destino_jpg, format="JPEG", quality=92, optimize=True)
        return destino_jpg
    except ImportError:
        pass

    hex0 = f"0x{c0[0]:02x}{c0[1]:02x}{c0[2]:02x}"
    hex1 = f"0x{c1[0]:02x}{c1[1]:02x}{c1[2]:02x}"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"gradients=s={LARGURA}x{ALTURA}:c0={hex0}:c1={hex1}:nb_colors=2:speed=0.001,"
        f"vignette=PI/4.5,noise=alls=4:allf=t",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(destino_jpg),
    ]
    subprocess.run(cmd, check=True, timeout=30)
    return destino_jpg


def gerar_todas_cenas_visuais(
    cenas_path: Path = ARQUIVO_CENAS_PADRAO,
    saida_dir: Path = PASTA_CENAS_PADRAO,
    *,
    usar_mock: bool = False,
    apenas_pollinations: bool = False,
    exigir_ia: bool = False,
    max_cenas: int | None = None,
    limpar_antigas: bool = True,
    api_key: str | None = None,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Gera output/cenas/cena_01.jpg..cena_NN.jpg a partir de cenas.json com fallback automatico."""
    if not cenas_path.is_file():
        raise FileNotFoundError(f"Arquivo cenas.json nao encontrado: {cenas_path}")

    dados = json.loads(cenas_path.read_text(encoding="utf-8"))
    lista_cenas = dados.get("cenas")
    if not isinstance(lista_cenas, list) or not lista_cenas:
        raise ValueError(f"Campo 'cenas' ausente ou vazio em {cenas_path}.")

    if max_cenas is not None and max_cenas > 0:
        lista_cenas = lista_cenas[: int(max_cenas)]

    video_id = int(dados.get("video_id") or 1)
    slug = str(dados.get("slug") or f"video-{video_id:02d}")
    protagonista = dados.get("protagonista") if isinstance(dados.get("protagonista"), dict) else {}
    estilo_canal = str(dados.get("estilo_visual") or "").strip() or obter_estilo_visual_ativo()

    saida_dir.mkdir(parents=True, exist_ok=True)
    if limpar_antigas:
        for antigo in saida_dir.glob("cena_*.jpg"):
            antigo.unlink(missing_ok=True)

    chave_gemini = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
    gemini_disponivel = (not usar_mock) and (not apenas_pollinations) and bool(chave_gemini)

    resultados: list[dict] = []
    total = len(lista_cenas)

    print(
        f"Estacao 3A (Storyboard IA): gerando {total} cena(s) 1080x1920 para Video {video_id:02d} "
        f"-> {saida_dir}",
        flush=True,
    )

    with tempfile.TemporaryDirectory(prefix="cenas-ia-") as tmp:
        tmp_dir = Path(tmp)
        for idx, cena in enumerate(lista_cenas, start=1):
            cena_id = f"cena_{idx:02d}"
            destino_jpg = saida_dir / f"{cena_id}.jpg"
            prompt = obter_prompt_cena(
                cena,
                idx - 1,
                total,
                protagonista=protagonista,
                estilo_visual=estilo_canal,
            )
            seed = calcular_seed_cena(video_id, slug, idx, prompt)
            mood = str(cena.get("mood", "navy"))
            raw_tmp = tmp_dir / f"{cena_id}_raw.bin"
            origem = ""

            if usar_mock:
                gerar_imagem_fallback_procedural(destino_jpg, mood=mood, seed=seed, indice=idx)
                origem = "mock_procedural"
            else:
                gerou = False
                if gemini_disponivel:
                    ok_g, det_g, perm_g = gerar_imagem_gemini_imagen(prompt, raw_tmp, chave_gemini)
                    if ok_g:
                        normalizar_para_jpeg_1080x1920(raw_tmp, destino_jpg)
                        ok_val, info_val = validar_arquivo_imagem(destino_jpg, min_bytes=MIN_BYTES_IMAGEM)
                        if ok_val:
                            origem = det_g
                            gerou = True
                        else:
                            print(f"  AVISO {cena_id}: imagem Gemini rejeitada ({info_val}).", flush=True)
                    else:
                        print(
                            f"  INFO {cena_id}: Gemini/Imagen indisponivel ({det_g}); ativando fallback Pollinations.",
                            flush=True,
                        )
                        if perm_g:
                            gemini_disponivel = False

                if not gerou:
                    ok_p, det_p = gerar_imagem_pollinations(
                        prompt,
                        seed=seed,
                        destino_raw=raw_tmp,
                        urlopen_fn=urlopen_fn,
                        sleep_fn=sleep_fn,
                    )
                    if ok_p:
                        normalizar_para_jpeg_1080x1920(raw_tmp, destino_jpg)
                        ok_val, info_val = validar_arquivo_imagem(destino_jpg, min_bytes=MIN_BYTES_IMAGEM)
                        if ok_val:
                            origem = det_p
                            gerou = True
                        else:
                            print(f"  AVISO {cena_id}: JPEG Pollinations invalido ({info_val}).", flush=True)
                    else:
                        print(f"  AVISO {cena_id}: fallback Pollinations falhou ({det_p}).", flush=True)

                if not gerou:
                    if exigir_ia:
                        raise RuntimeError(f"Falha ao gerar imagem IA para {cena_id} em todos os provedores.")
                    print(
                        f"  AVISO {cena_id}: usando quadro atmosferico local de emergencia para manter a pipeline.",
                        flush=True,
                    )
                    gerar_imagem_fallback_procedural(destino_jpg, mood=mood, seed=seed, indice=idx)
                    origem = "fallback_procedural"

            ok_final, info_final = validar_arquivo_imagem(destino_jpg, min_bytes=MIN_BYTES_IMAGEM)
            if not ok_final:
                raise RuntimeError(f"Imagem final invalida em {destino_jpg}: {info_final}")

            tam_bytes = destino_jpg.stat().st_size
            print(
                f"  [{idx:02d}/{total:02d}] {destino_jpg.name}: {tam_bytes / 1024:.1f} KB | {origem}",
                flush=True,
            )
            resultados.append(
                {
                    "id": str(cena.get("id") or cena_id),
                    "arquivo": destino_jpg.name,
                    "caminho": str(destino_jpg),
                    "origem": origem,
                    "seed": seed,
                    "bytes": tam_bytes,
                    "prompt_imagem": prompt,
                }
            )

    manifesto = {
        "video_id": video_id,
        "slug": slug,
        "largura": LARGURA,
        "altura": ALTURA,
        "total_cenas": len(resultados),
        "cenas": resultados,
    }
    manifest_path = saida_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifesto


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estacao 3A: gera imagens 1080x1920 por cena a partir de cenas.json (Gemini/Imagen -> Pollinations)."
    )
    parser.add_argument("--cenas", type=Path, default=ARQUIVO_CENAS_PADRAO, help="Caminho do cenas.json.")
    parser.add_argument(
        "--saida-dir",
        type=Path,
        default=PASTA_CENAS_PADRAO,
        help="Pasta de destino das imagens (padrao: output/cenas).",
    )
    parser.add_argument("--max-cenas", type=int, default=None, help="Limita quantidade de cenas (ex.: modo teste).")
    parser.add_argument("--mock", action="store_true", help="Gera imagens atmosfericas locais sem chamadas de rede.")
    parser.add_argument(
        "--apenas-pollinations",
        action="store_true",
        help="Pula Gemini/Imagen e usa diretamente o endpoint gratuito Pollinations.",
    )
    parser.add_argument(
        "--exigir-ia",
        action="store_true",
        help="Falha explicitamente se Gemini/Imagen e Pollinations falharem em alguma cena.",
    )
    args = parser.parse_args()

    carregar_env()
    cenas_path = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    saida_dir = args.saida_dir if args.saida_dir.is_absolute() else (RAIZ / args.saida_dir)

    manifesto = gerar_todas_cenas_visuais(
        cenas_path=cenas_path,
        saida_dir=saida_dir,
        usar_mock=args.mock,
        apenas_pollinations=args.apenas_pollinations,
        exigir_ia=args.exigir_ia,
        max_cenas=args.max_cenas,
    )
    print(
        f"Estacao 3A concluida: {manifesto['total_cenas']} imagem(ns) 1080x1920 prontas em {saida_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
