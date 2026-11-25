"""Testes unitarios do pool central Gemini (multi-chave, rotacao de modelos, fail-fast cota diaria e Groq).

Uso (na raiz do repositorio):
    python3 pipeline/testar_gemini_pool.py
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import random
import sys
import tempfile
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gerar_midia_cenas as gmc  # noqa: E402
from audio import gerar_narracao as gn  # noqa: E402
from pipeline import diretor_ia as dia  # noqa: E402
from pipeline import gemini_pool as gp  # noqa: E402


ERRO_COTA_20 = (
    '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED",'
    '"message":"You exceeded your current quota. Metric: '
    'generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20"}}'
).encode("utf-8")

ERRO_COTA_PERDAY = (
    '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED",'
    '"message":"Quota exceeded for quota metric GenerateRequestsPerDayPerProjectPerModel-FreeTier (PerDay)"}}'
).encode("utf-8")


class _RespFake:
    def __init__(self, dados_bytes: bytes):
        self._dados = dados_bytes

    def read(self) -> bytes:
        return self._dados

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _gerar_jpeg_rico_bytes() -> bytes:
    rng = random.Random(42)
    img = Image.new("RGB", (600, 1066), (14, 22, 42))
    draw = ImageDraw.Draw(img)
    for _ in range(140):
        x0 = rng.randint(0, 560)
        y0 = rng.randint(0, 1020)
        draw.rectangle(
            (x0, y0, x0 + rng.randint(20, 140), y0 + rng.randint(20, 160)),
            fill=(rng.randint(30, 210), rng.randint(40, 220), rng.randint(60, 240)),
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def testar_deteccao_cota_e_carregamento_chaves() -> None:
    assert gp.eh_erro_cota_diaria("429 generate_content_free_tier_requests limit: 20", status_code=429) is True
    assert gp.eh_erro_cota_diaria("Quota exceeded PerDay on free tier", status_code=429) is True
    assert gp.eh_erro_cota_diaria("RESOURCE_EXHAUSTED", status_code=429, ocorrencias_429_seguidas=2) is True
    assert gp.eh_erro_cota_diaria("Quota exceeded for TTS", status_code=429, ocorrencias_429_seguidas=1) is False

    backup = {k: os.environ.get(k) for k in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GROQ_API_KEY")}
    try:
        os.environ["GEMINI_API_KEY"] = "AIzaSyKeyOneValid000001"
        os.environ["GEMINI_API_KEY_2"] = "AIzaSyKeyTwoValid000002"
        os.environ["GEMINI_API_KEY_3"] = "AIzaSyKeyThreeValid0003"
        os.environ["GROQ_API_KEY"] = "gsk_valid_groq_key_123456"
        chaves = gp.carregar_chaves_gemini(ler_env_arquivo=False)
        assert [n for n, _ in chaves] == ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]
        assert gp.obter_groq_api_key(ler_env_arquivo=False) == "gsk_valid_groq_key_123456"
        sanit = gp.sanitizar_texto_sem_chaves("falha com AIzaSyKeyTwoValid000002", [v for _, v in chaves])
        assert "AIzaSyKeyTwoValid000002" not in sanit and "***API_KEY***" in sanit
    finally:
        for k, v in backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("[OK] pipeline/gemini_pool.py: carregamento de 3 chaves, mascaramento e deteccao fail-fast validados.")


def testar_estacao1_rotacao_imediata_sem_travar() -> None:
    """Simula 429 generate_content_free_tier_requests limit: 20 na Estacao 1 confirmando 0s sleep e troca imediata."""
    pool = gp.GeminiPool(
        chaves=[
            ("GEMINI_API_KEY", "AIzaSyKeyUmTeste000001"),
            ("GEMINI_API_KEY_2", "AIzaSyKeyDoisTeste0002"),
        ],
        modelos=["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
    )
    esperas: list[float] = []
    chamadas: list[tuple[str, str]] = []

    def _mock_urlopen(req, timeout=60):
        chave = req.headers.get("X-goog-api-key") or req.headers.get("x-goog-api-key") or ""
        url = req.full_url
        modelo = url.split("/models/")[1].split(":")[0]
        chamadas.append((chave, modelo))

        # Key 1 + gemini-2.5-flash bate limite diario 20 req/dia
        if chave == "AIzaSyKeyUmTeste000001" and modelo == "gemini-2.5-flash":
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {"Retry-After": "60"}, io.BytesIO(ERRO_COTA_20))
        # Key 2 + gemini-2.5-flash bate PerDay
        if chave == "AIzaSyKeyDoisTeste0002" and modelo == "gemini-2.5-flash":
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {"Retry-After": "60"}, io.BytesIO(ERRO_COTA_PERDAY))
        # Key 1 + gemini-2.5-flash-lite responde com sucesso
        resp_obj = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps({"titulo": "Teste Rotacao OK", "ok": True})}]
                    }
                }
            ]
        }
        return _RespFake(json.dumps(resp_obj).encode("utf-8"))

    ref: dict[str, str] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        res1 = dia._chamar_gemini_json(
            prompt="Gere JSON de teste.",
            urlopen_fn=_mock_urlopen,
            sleep_fn=lambda s: esperas.append(float(s)),
            modelo_ativo_ref=ref,
            pool=pool,
            groq_api_key="",
        )
        # Segunda chamada com o mesmo pool deve ir direto para a combinacao saudavel em cache
        res2 = dia._chamar_gemini_json(
            prompt="Gere segundo JSON de teste.",
            urlopen_fn=_mock_urlopen,
            sleep_fn=lambda s: esperas.append(float(s)),
            modelo_ativo_ref=ref,
            pool=pool,
            groq_api_key="",
        )

    assert res1["ok"] is True and res2["ok"] is True
    assert esperas == [], f"Nao deveria dormir em cota diaria (esperas={esperas})!"
    assert ref["modelo"] == "gemini-2.5-flash-lite" and ref["chave"] == "GEMINI_API_KEY"
    assert chamadas == [
        ("AIzaSyKeyUmTeste000001", "gemini-2.5-flash"),
        ("AIzaSyKeyDoisTeste0002", "gemini-2.5-flash"),
        ("AIzaSyKeyUmTeste000001", "gemini-2.5-flash-lite"),
        ("AIzaSyKeyUmTeste000001", "gemini-2.5-flash-lite"),
    ], f"Ordem de rotacao inesperada: {chamadas}"
    print("[OK] Estacao 1 (GeminiPool): fail-fast 0s sleep em 429 limit: 20 + rotacao de chave/modelo + cache OK.")


def testar_estacao1_groq_primario_e_16_cenas() -> None:
    """Confirma que Groq (llama-3.3-70b-versatile) roda PRIMEIRO na Estacao 1 com 0 chamadas ao Gemini e gera 16 cenas."""
    cenas_groq_16 = [
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Na madrugada de 2008, o farol da ilha apagou sem aviso.",
            "prompt_imagem": "Isolated stone lighthouse on jagged black cliffs as its beam dies in nocturnal fog, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "push_in",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O guarda subiu a escada em espiral segurando uma lanterna fraca.",
            "prompt_imagem": "Low angle inside a damp spiral lighthouse staircase illuminated by a single shaking flashlight beam, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_diag_tl",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "A porta de ferro da sala da lente estava trancada por dentro.",
            "prompt_imagem": "Close up of a rusted heavy iron door with bolted latch inside a dark maritime tower, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pull_out",
            "mood": "violet",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Mesmo assim, a lente gigante girava devagar no escuro completo.",
            "prompt_imagem": "Giant Fresnel glass lighthouse lens rotating silently in pitch darkness with faint moonlight reflection, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_right",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O radio da guarda costeira chiou com um pedido de socorro antigo.",
            "prompt_imagem": "Vintage naval shortwave radio console glowing amber in a shadowed control room with static sparks, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "push_in",
            "mood": "yellow",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "A voz na frequencia citava um cargueiro que afundou trinta anos antes.",
            "prompt_imagem": "Ghostly silhouette of a rusted cargo ship half-submerged in storm waves under dark clouds, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_left",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O guarda olhou pela janela molhada em direcao ao mar aberto.",
            "prompt_imagem": "Rain-streaked lighthouse window looking out over pitch-black turbulent ocean swell at night, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_diag_br",
            "mood": "violet",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Havia dezenas de lanternas acesas boiando perto das pedras.",
            "prompt_imagem": "Dozens of eerie pale glowing lanterns floating across black coastal waves near sharp basalt rocks, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "push_in",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Nenhum barco aparecia no radar verde da torre de vigia.",
            "prompt_imagem": "Green phosphor maritime radar screen sweeping smoothly over an completely empty dark sector, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pull_out",
            "mood": "cctv",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O gerador diesel no porao parou de vibrar no mesmo instante.",
            "prompt_imagem": "Dark industrial diesel generator room with cooling metal pipes and dim red emergency bulb, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_right",
            "mood": "dark",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Passos molhados comecaram a subir os degraus logo abaixo dele.",
            "prompt_imagem": "Wet dark footprints appearing one by one up a narrow metallic lighthouse staircase in dim mist, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "shake_impact",
            "mood": "red",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O cheiro de agua salgada tomou conta da sala fechada.",
            "prompt_imagem": "Cold ocean mist seeping beneath a bolted iron doorframe onto wet stone floor tiles, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "push_in",
            "mood": "navy",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "O diario de bordo aberto na mesa mostrou a data daquele dia.",
            "prompt_imagem": "Aged salt-stained maritime logbook lying open on a wooden desk under a single flickering desk lamp, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_left",
            "mood": "yellow",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "Alguem tinha assinado o turno da noite com a letra do proprio guarda.",
            "prompt_imagem": "Extreme close up of wet ink fountain pen resting beside a dripping ocean droplet on parchment, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pan_diag_tl",
            "mood": "violet",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "sussurro_twist",
            "texto": "Quando a luz voltou, o reflexo no vidro mostrava o farol vazio.",
            "prompt_imagem": "Dramatic cinematic reflection on dark lighthouse glass showing an empty room lit by cold blue moonlight, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "shake_impact",
            "mood": "red",
            "sfx_depois": None,
        },
        {
            "perfil_voz": "narrador_tenso",
            "texto": "E voce, desligaria o radio ou abriria a porta do farol?",
            "prompt_imagem": "Aerial vertical shot of the solitary lighthouse standing over storm-swept ocean cliffs at twilight, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark",
            "camera": "pull_out",
            "mood": "navy",
            "sfx_depois": None,
        },
    ]
    roteiro_16 = " ".join(c["texto"] for c in cenas_groq_16)

    chamadas_groq: list[dict] = []
    chamadas_gemini: list[str] = []

    def _mock_urlopen(req, timeout=60):
        url = req.full_url
        if "generativelanguage.googleapis.com" in url:
            chamadas_gemini.append(url)
            raise AssertionError("Gemini NAO deveria ser chamado quando GROQ_API_KEY esta ativa e saudavel!")
        assert url == gp.GROQ_API_URL, f"URL inesperada: {url}"
        assert req.headers.get("Authorization") == "Bearer gsk_groq_primary_key_999"
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "llama-3.3-70b-versatile"
        assert body["response_format"] == {"type": "json_object"}
        assert body["max_tokens"] >= 4096
        assert any(m["role"] == "system" for m in body["messages"])
        chamadas_groq.append(body)

        if len(chamadas_groq) == 1:
            conteudo_obj = {
                "titulo": "O Farol Que Acende Sozinho",
                "pilar": "misterios_reais",
                "tema": "Um farol isolado recebe sinais de um cargueiro desaparecido ha trinta anos.",
                "roteiro_bruto": roteiro_16,
            }
        else:
            # Simula resposta estrita com 16 cenas (inclusive testando alias 'cenas')
            conteudo_obj = {
                "titulo": "O Farol Que Acende Sozinho",
                "pilar": "misterios_reais",
                "tema": "Um farol isolado recebe sinais de um cargueiro desaparecido ha trinta anos.",
                "palavras_chave": ["farol", "cargueiro", "radar", "lanterna", "mar"],
                "horario": "02:44",
                "protagonista": {"nome": "Guarda", "jaqueta": "#0F766E", "pele": "#E0B292", "cabelo": "#141720"},
                "paleta": dict(dia.PALETA_PADRAO),
                "blocos": cenas_groq_16,
                "katana_hits": [
                    {"bloco_idx": 0, "palavra_gatilho": "farol", "linhas": ["FAROL"], "duracao": 0.42, "cor": "red"},
                    {"bloco_idx": 5, "palavra_gatilho": "cargueiro", "linhas": ["CARGUEIRO"], "duracao": 0.42, "cor": "red"},
                    {"bloco_idx": 10, "palavra_gatilho": "passos", "linhas": ["PASSOS"], "duracao": 0.42, "cor": "red"},
                    {"bloco_idx": 14, "palavra_gatilho": "vazio", "linhas": ["VAZIO"], "duracao": 0.46, "cor": "red"},
                ],
            }
        resp_envelope = {"choices": [{"message": {"content": json.dumps(conteudo_obj, ensure_ascii=False)}}]}
        return _RespFake(json.dumps(resp_envelope, ensure_ascii=False).encode("utf-8"))

    backup = {k: os.environ.get(k) for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3")}
    try:
        os.environ["GROQ_API_KEY"] = "gsk_groq_primary_key_999"
        os.environ["GEMINI_API_KEY"] = "AIzaSyGeminiBackupOnly001"
        os.environ.pop("GEMINI_API_KEY_2", None)
        os.environ.pop("GEMINI_API_KEY_3", None)

        with tempfile.TemporaryDirectory(prefix="teste_groq_prim_") as tmp:
            tmp_dir = Path(tmp)
            hist_path = tmp_dir / "historico_videos.json"
            hist_path.write_text(
                json.dumps(
                    {
                        "versao": 1,
                        "regra": "Sempre Video Novo",
                        "video_atual": 1,
                        "videos": [
                            {
                                "id": 1,
                                "slug": "video-inicial",
                                "titulo": "Video Inicial",
                                "tema": "Outro assunto completamente diferente no deserto.",
                                "palavras_chave": ["deserto", "areia", "sol", "camelo"],
                                "roteiro": "roteiro_01.txt",
                                "saida": "output/short_01.mp4",
                                "status": "publicado",
                                "pilar": "curiosidades_bizarras",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                res = dia.produzir_direcao_v6(
                    gerar_inedito=True,
                    exigir_gemini=True,
                    caminho_historico=hist_path,
                    dir_saida=tmp_dir,
                    atualizar_historico=True,
                    urlopen_fn=_mock_urlopen,
                    sleep_fn=lambda _: None,
                )

            assert len(chamadas_groq) == 2, f"Esperava 2 chamadas Groq (roteiro + direcao), obteve {len(chamadas_groq)}"
            assert chamadas_gemini == [], f"Gemini nao deveria ser chamado: {chamadas_gemini}"
            assert res["origem"].startswith("groq_inedito:groq:llama-3.3-70b-versatile"), f"Origem inesperada: {res['origem']}"
            assert res["titulo"] == "O Farol Que Acende Sozinho"
            assert res["pilar"] == "misterios_reais"
            cenas_geradas = res["cenas"]["cenas"]
            assert 14 <= len(cenas_geradas) <= 18, f"Esperava 14..18 cenas, obteve {len(cenas_geradas)}"
            assert dia.validar_cenas_json(res["cenas"]) == []
    finally:
        for k, v in backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print(f"[OK] Estacao 1 (Groq primario): 0 chamadas ao Gemini, titulo/pilar e {len(cenas_geradas)} cenas validas em JSON estrito.")


def testar_estacao1_groq_falha_fallback_gemini_pool() -> None:
    """Se Groq primario retornar HTTP 503, cai automaticamente no GeminiPool sem travar."""
    pool = gp.GeminiPool(
        chaves=[("GEMINI_API_KEY", "AIzaSyFallbackGemini0001")],
        modelos=["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    )
    ordem_provedores: list[str] = []

    def _mock_urlopen(req, timeout=60):
        url = req.full_url
        if url == gp.GROQ_API_URL:
            ordem_provedores.append("groq")
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(b'{"error":{"message":"Groq overloaded"}}'))
        if "generativelanguage.googleapis.com" in url:
            ordem_provedores.append("gemini")
            resp_obj = {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps({"titulo": "Fallback Gemini OK", "ok": True})}]
                        }
                    }
                ]
            }
            return _RespFake(json.dumps(resp_obj).encode("utf-8"))
        raise AssertionError(f"URL inesperada: {url}")

    ref: dict[str, str] = {}
    with contextlib.redirect_stdout(io.StringIO()):
        res = dia._chamar_gemini_json(
            prompt="Gere JSON de teste.",
            urlopen_fn=_mock_urlopen,
            sleep_fn=lambda _: None,
            modelo_ativo_ref=ref,
            pool=pool,
            groq_api_key="gsk_groq_overloaded_key_001",
        )

    assert res["ok"] is True and res["titulo"] == "Fallback Gemini OK"
    assert ordem_provedores[0] == "groq" and ordem_provedores[-1] == "gemini", f"Ordem inesperada: {ordem_provedores}"
    assert ref["provedor"] == "gemini" and ref["modelo"] == "gemini-2.5-flash"
    print("[OK] Estacao 1 (Fallback automatico): Groq 503 -> GeminiPool assumiu automaticamente com sucesso.")


def testar_estacao2_tts_rotacao_chaves_fail_fast() -> None:
    """Simula 429 limit: 20 na chave 1 do Gemini TTS e confirma troca instantanea para GEMINI_API_KEY_2 (0s sleep)."""
    pool = gp.GeminiPool(
        chaves=[
            ("GEMINI_API_KEY", "AIzaSyTTSKeyUm00000001"),
            ("GEMINI_API_KEY_2", "AIzaSyTTSKeyDois000002"),
        ],
        modelos=[gn.GEMINI_TTS_MODELO],
    )
    pcm_ok = b"\x00\x00" * 4800
    payload_ok = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/L16;codec=pcm;rate=24000",
                                    "data": base64.b64encode(pcm_ok).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        }
    ).encode("utf-8")

    esperas: list[float] = []
    chaves_chamadas: list[str] = []

    def _mock_urlopen(req, timeout=90):
        chave = req.headers.get("X-goog-api-key") or req.headers.get("x-goog-api-key") or ""
        chaves_chamadas.append(chave)
        if chave == "AIzaSyTTSKeyUm00000001":
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(ERRO_COTA_20))
        return _RespFake(payload_ok)

    with tempfile.TemporaryDirectory(prefix="teste_tts_pool_") as tmp:
        wav1 = Path(tmp) / "bloco1.wav"
        wav2 = Path(tmp) / "bloco2.wav"
        with contextlib.redirect_stdout(io.StringIO()):
            gn.sintetizar_gemini_tts(
                texto="Primeiro bloco de suspense.",
                destino_wav=wav1,
                perfil_voz="narrador_tenso",
                urlopen_fn=_mock_urlopen,
                sleep_fn=lambda s: esperas.append(float(s)),
                min_interval_s=0.0,
                gemini_pool=pool,
            )
            gn.sintetizar_gemini_tts(
                texto="Segundo bloco ja usando a chave 2 em cache.",
                destino_wav=wav2,
                perfil_voz="narrador_tenso",
                urlopen_fn=_mock_urlopen,
                sleep_fn=lambda s: esperas.append(float(s)),
                min_interval_s=0.0,
                gemini_pool=pool,
            )
        assert wav1.is_file() and wav1.stat().st_size > 1000
        assert wav2.is_file() and wav2.stat().st_size > 1000

    assert esperas == [], f"TTS nao deveria dormir em cota diaria (esperas={esperas})!"
    assert chaves_chamadas == [
        "AIzaSyTTSKeyUm00000001",
        "AIzaSyTTSKeyDois000002",
        "AIzaSyTTSKeyDois000002",
    ], f"Sequencia de chaves TTS inesperada: {chaves_chamadas}"
    print("[OK] Estacao 2 (Gemini TTS): troca instantanea para GEMINI_API_KEY_2 (0s sleep) e memoria entre blocos OK.")


def testar_estacao3_imagens_rotacao_chaves_fail_fast() -> None:
    """Simula 429 limit: 20 na chave 1 da Estacao 3 e confirma troca instantanea para GEMINI_API_KEY_2 (0s sleep)."""
    pool = gp.GeminiPool(
        chaves=[
            ("GEMINI_API_KEY", "AIzaSyImgKeyUm00000001"),
            ("GEMINI_API_KEY_2", "AIzaSyImgKeyDois000002"),
        ],
        modelos=list(gmc.MODELOS_GEMINI_IMAGEM),
    )
    raw_ok = _gerar_jpeg_rico_bytes()
    esperas: list[float] = []
    chamadas: list[tuple[str, str]] = []

    def _client_factory(chave: str):
        class _FakeModels:
            def generate_content(self, model, contents, config):
                chamadas.append((chave, model))
                if chave == "AIzaSyImgKeyUm00000001" and model == "gemini-2.5-flash-image":
                    raise RuntimeError(
                        "429 RESOURCE_EXHAUSTED: generate_content_free_tier_requests limit: 20"
                    )
                parte = SimpleNamespace(inline_data=SimpleNamespace(data=raw_ok))
                cand = SimpleNamespace(content=SimpleNamespace(parts=[parte]))
                return SimpleNamespace(candidates=[cand])

        return SimpleNamespace(models=_FakeModels())

    fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
    clientes_cache: dict = {}
    cache_modelo: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="teste_img_pool_") as tmp:
        p1 = Path(tmp) / "cena_01.jpg"
        p2 = Path(tmp) / "cena_02.jpg"
        with contextlib.redirect_stdout(io.StringIO()):
            r1 = gmc.gerar_imagem_gemini_com_cache(
                prompt="Dark foggy toll booth at night",
                destino_jpg=p1,
                cache_modelo=cache_modelo,
                types_mod=fake_types,
                pool=pool,
                client_factory=_client_factory,
                clientes_cache=clientes_cache,
                sleep_fn=lambda s: esperas.append(float(s)),
            )
            r2 = gmc.gerar_imagem_gemini_com_cache(
                prompt="Pale hand holding a muddy 20-real banknote",
                destino_jpg=p2,
                cache_modelo=cache_modelo,
                types_mod=fake_types,
                pool=pool,
                client_factory=_client_factory,
                clientes_cache=clientes_cache,
                sleep_fn=lambda s: esperas.append(float(s)),
            )
        assert p1.is_file() and p1.stat().st_size > 30 * 1024
        assert p2.is_file() and p2.stat().st_size > 30 * 1024

    assert esperas == [], f"Estacao 3 nao deveria dormir em cota diaria (esperas={esperas})!"
    assert r1["chave"] == "GEMINI_API_KEY_2" and r1["modelo"] == "gemini-2.5-flash-image"
    assert r2["chave"] == "GEMINI_API_KEY_2" and r2["modelo"] == "gemini-2.5-flash-image"
    assert chamadas == [
        ("AIzaSyImgKeyUm00000001", "gemini-2.5-flash-image"),
        ("AIzaSyImgKeyDois000002", "gemini-2.5-flash-image"),
        ("AIzaSyImgKeyDois000002", "gemini-2.5-flash-image"),
    ], f"Ordem de chamadas de imagem inesperada: {chamadas}"
    print("[OK] Estacao 3 (gerar_midia_cenas): troca instantanea para GEMINI_API_KEY_2 (0s sleep) e cache entre cenas OK.")


def main() -> int:
    testar_deteccao_cota_e_carregamento_chaves()
    testar_estacao1_groq_primario_e_16_cenas()
    testar_estacao1_groq_falha_fallback_gemini_pool()
    testar_estacao1_rotacao_imediata_sem_travar()
    testar_estacao2_tts_rotacao_chaves_fail_fast()
    testar_estacao3_imagens_rotacao_chaves_fail_fast()
    print("TODOS OS TESTES (GROQ PRIMARIO + GEMINI POOL FAIL-FAST) PASSARAM COM SUCESSO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
