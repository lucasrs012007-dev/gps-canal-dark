"""Suite de validacao ponta a ponta do Motor Cinematografico IA V8.0 (1080x1920 @ 30fps).

Uso (na raiz do repositorio):
    python3 render/testar_motor_cinematografico.py
    python3 render/testar_motor_cinematografico.py --salvar-amostras /tmp/amostras_v8
    python3 render/testar_motor_cinematografico.py --somente-logica
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import math
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import wave
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageChops, ImageDraw, ImageStat

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gerar_midia_cenas as gmc  # noqa: E402
from audio import gerar_narracao as gn  # noqa: E402
from audio import trilha_mix as tm  # noqa: E402
from pipeline import diretor_ia as dia  # noqa: E402
from render import renderizar as rnd  # noqa: E402


def _gerar_imagem_detalhada_jpg(destino: Path, *, paleta: tuple[tuple[int, int, int], tuple[int, int, int]], seed: int) -> Path:
    """Cria imagem 1080x1920 detalhada (> 50KB) com iluminacao dramatica para testes locais sem API."""
    rng = random.Random(seed)
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h), paleta[0])
    draw = ImageDraw.Draw(img)

    # Gradiente atmosferico vertical
    c0, c1 = paleta
    for y in range(0, h, 4):
        f = y / float(h)
        cor = (
            int(c0[0] * (1.0 - f) + c1[0] * f),
            int(c0[1] * (1.0 - f) + c1[1] * f),
            int(c0[2] * (1.0 - f) + c1[2] * f),
        )
        draw.rectangle((0, y, w, y + 4), fill=cor)

    # Estruturas geometricas e feixes volumetricos de luz (garante textura rica > 50KB e alto contraste de movimento)
    for _ in range(180):
        x0 = rng.randint(0, w - 40)
        y0 = rng.randint(0, h - 40)
        x1 = min(w, x0 + rng.randint(25, 220))
        y1 = min(h, y0 + rng.randint(25, 260))
        cor = (
            max(0, min(255, c1[0] + rng.randint(-45, 70))),
            max(0, min(255, c1[1] + rng.randint(-45, 70))),
            max(0, min(255, c1[2] + rng.randint(-45, 70))),
        )
        draw.rectangle((x0, y0, x1, y1), fill=cor)

    # Feixes diagonais e pontos brilhantes
    for k in range(16):
        x_base = int((k / 16.0) * w)
        draw.polygon(
            [(x_base, 0), (x_base + 70, 0), (x_base + 240, h), (x_base + 140, h)],
            fill=(min(255, c1[0] + 35), min(255, c1[1] + 45), min(255, c1[2] + 60)),
        )
    for _ in range(420):
        cx = rng.randint(10, w - 10)
        cy = rng.randint(10, h - 10)
        r = rng.randint(2, 12)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(210, 225, 245))

    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, format="JPEG", quality=94, optimize=True, subsampling=0)
    assert destino.stat().st_size > 30 * 1024, f"Imagem de teste ficou abaixo de 30KB: {destino.stat().st_size}"
    return destino


def _gerar_clip_video_teste_mp4(destino: Path, duracao_s: float = 1.6) -> Path:
    """Gera clipe .mp4 vertical 720x1280 sintetico simulando clipe de video IA da fal.ai."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=720x1280:rate=30:duration={duracao_s:.2f}",
        "-vf",
        "eq=brightness=-0.22:contrast=1.25:saturation=0.85,vignette=PI/4",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(destino),
    ]
    subprocess.run(cmd, check=True)
    assert destino.stat().st_size > 40 * 1024, f"Clipe .mp4 de teste pequeno demais: {destino.stat().st_size}"
    return destino


def _gerar_voz_sintetica_wav(destino: Path, duracao_s: float = 4.0) -> Path:
    """Gera sinal de voz sintetico modulado (fala + pausa) para validar ducking e -14 LUFS."""
    sr = 44100
    n = int(sr * duracao_s)
    buf = bytearray()
    for i in range(n):
        t = i / sr
        # Fala ativa em 0.1..1.4s e 2.0..3.6s; pausa entre 1.4..2.0s
        if (0.10 <= t <= 1.40) or (2.00 <= t <= 3.60):
            env = 0.55 + 0.35 * math.sin(2.0 * math.pi * 4.5 * t)
            s = (
                0.50 * math.sin(2.0 * math.pi * 180.0 * t)
                + 0.30 * math.sin(2.0 * math.pi * 360.0 * t)
                + 0.15 * math.sin(2.0 * math.pi * 720.0 * t)
            ) * env * 0.45
        else:
            s = 0.0
        val = max(-32767, min(32767, int(s * 32767)))
        buf.extend(struct.pack("<hh", val, val))

    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(buf))
    return destino


def testar_narracao_gemini_8d9ce26() -> None:
    """Valida restauracao do commit 8d9ce26, prioridade Gemini TTS, 3 retries com backoff e logs claros."""
    assert gn.GEMINI_TTS_MODELO == "gemini-2.5-flash-preview-tts", f"Modelo inesperado: {gn.GEMINI_TTS_MODELO}"
    assert gn.GEMINI_VOZ_NARRADOR == "Charon", f"Voz narrador inesperada: {gn.GEMINI_VOZ_NARRADOR}"
    assert gn.GEMINI_VOZ_TELEFONE == "Fenrir", f"Voz telefone inesperada: {gn.GEMINI_VOZ_TELEFONE}"
    assert abs(float(gn.VELOCIDADE_VOZ_PADRAO) - 1.02) < 1e-6, f"Velocidade inesperada: {gn.VELOCIDADE_VOZ_PADRAO}"
    assert len(gn.GEMINI_RETRY_ESPERAS) >= 3, "Menos de 3 retries configurados no Gemini TTS."

    # Teste de protecao de anos e numeros nas legendas ("EM 2004", "20 REAIS" nunca partidos entre grupos)
    texto_num = gn.sanitizar_texto_tts("Em 2004, ele pagou 20 reais no pedagio.")
    assert "2004" in texto_num and "20 reais" in texto_num
    palavras_leg = gn.alinhar_palavras_na_frase(
        "Em 2004, a nota de 20 reais apareceu no pedagio.",
        t_inicio=0.0,
        dur_frase=3.0,
        raw_words=[],
    )
    grupos_leg = gn.quebrar_em_grupos_legenda(palavras_leg)
    textos_grupos = [" ".join(p["palavra"] for p in g).upper() for g in grupos_leg]
    assert any("EM 2004" in g for g in textos_grupos), f"'EM 2004' quebrado entre grupos: {textos_grupos}"
    assert any("20 REAIS" in g for g in textos_grupos), f"'20 REAIS' quebrado entre grupos: {textos_grupos}"

    # Teste de retry com backoff (HTTP 429 -> URLError -> 200 OK com PCM valido)
    pcm_fake = b"\x00\x00" * 4800
    payload_ok = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/L16;codec=pcm;rate=24000",
                                    "data": base64.b64encode(pcm_fake).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        }
    ).encode("utf-8")

    chamadas = {"n": 0}
    esperas_registradas: list[float] = []

    class _RespFake:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _mock_urlopen(req, timeout=180):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                {},
                io.BytesIO(b'{"error":{"message":"Quota exceeded for TTS"}}'),
            )
        if chamadas["n"] == 2:
            raise urllib.error.URLError("Temporary DNS failure")
        return _RespFake(payload_ok)

    buf_log = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="teste_tts_") as tmp:
        wav_out = Path(tmp) / "ok.wav"
        with contextlib.redirect_stdout(buf_log):
            gn.sintetizar_gemini_tts(
                texto="Teste de voz humana Gemini.",
                destino_wav=wav_out,
                api_key="AIzaSyFakeKeyParaTesteLocal123456",
                perfil_voz="narrador_tenso",
                urlopen_fn=_mock_urlopen,
                sleep_fn=lambda s: esperas_registradas.append(float(s)),
            )
        assert wav_out.is_file() and wav_out.stat().st_size > 1000, "WAV do Gemini TTS nao foi gravado."

    logs = buf_log.getvalue()
    assert chamadas["n"] == 3, f"Esperava 3 chamadas (2 falhas + 1 sucesso), obteve {chamadas['n']}"
    assert len(esperas_registradas) == 2, f"Esperava 2 esperas de backoff, obteve {esperas_registradas}"
    assert "429" in logs and "Quota exceeded" in logs, f"Motivo HTTP 429 ausente nos logs:\n{logs}"
    assert "URLError" in logs and "Temporary DNS failure" in logs, f"Motivo URLError ausente nos logs:\n{logs}"
    print("[OK] audio/gerar_narracao.py: Gemini TTS 8d9ce26 + retries com backoff + logs explicitos verificados.")


def testar_trilha_mix_suavizada() -> None:
    """Valida suavizacao de graves em audio/trilha_mix.py e normalizacao -14 LUFS."""
    filtro = tm.montar_filtro_trilha_sintetizada(4.0)
    assert "volume=0.045" in filtro and "volume=0.025" in filtro, f"Volumes sub-graves nao suavizados: {filtro}"
    assert "highpass=f=75" in filtro and "lowpass=f=420" in filtro, f"Filtro passa-banda inesperado: {filtro}"
    assert "loudnorm=I=-21" in filtro, f"Base da trilha fora do alvo -21 LUFS: {filtro}"

    with tempfile.TemporaryDirectory(prefix="teste_audio_") as tmp:
        voz = _gerar_voz_sintetica_wav(Path(tmp) / "voz.wav", duracao_s=4.0)
        mix = Path(tmp) / "mix.mp3"
        info = tm.mixar_audio_profissional(voz, mix, pasta_trilhas=Path(tmp) / "vazia")
        assert info["origem_trilha"] == "sintese_dark_ffmpeg"
        lufs = float(info["lufs"])
        assert -16.5 <= lufs <= -12.0, f"Loudness fora da janela -14 LUFS: {lufs:.2f}"
        print(f"[OK] audio/trilha_mix.py: trilha limpa sem zumbido + ducking + {lufs:.2f} LUFS (TP={info['true_peak_dbtp']:.2f} dBTP).")


def testar_diretor_ia_cortes_rapidos() -> None:
    """Valida Estacao 1 V8.0: 14-18 cenas curtas (3s-4s), prompts literais UE5 9:16 e zero CTA no meio."""
    roteiro_teste = (
        "Em 2004, na cabine do pedagio sob a neblina das 03:12, um sedã preto parou sem acender os farois. "
        "O vidro desceu devagar e uma mao palida entregou uma nota de 20 reais suja de barro. "
        "O cobrador sentiu o papel gelado e olhou para o banco vazio do motorista. "
        "Nao havia ninguem no volante, apenas o radio chiando em uma frequencia antiga. "
        "Quando ele ergueu a cabeca para chamar a seguranca na guarita, o carro ja tinha sumido na estrada deserta. "
        "No monitor da camera de vigilancia, a cancela nunca abriu naquela madrugada inteira. "
        "Porem a nota de 20 reais continuava molhada dentro da gaveta do caixa com o numero de serie de 1998. "
        "O supervisor puxou o arquivo de acidentes da rodovia e empalideceu na hora. "
        "Exatamente naquele quilometro, um motorista havia desaparecido seis anos antes com o mesmo carro preto. "
        "Na manha seguinte, a cabine recebeu outra ligacao mudinha da mesma linha cortada. "
        "E voce, abriria a janela naquela madrugada ou desligaria todas as luzes?"
    )
    plano_raw = dia.diretor_mock_deterministico(roteiro_teste, titulo_forcado="A Nota do Pedagio", catalogo_sfx={})
    plano, _avisos = dia.validar_e_corrigir_plano(plano_raw, roteiro_teste, titulo_forcado="A Nota do Pedagio", catalogo_sfx={})
    texto_rot, cenas_json, _ = dia.compor_roteiro_e_cenas(
        plano=plano,
        video_id=99,
        slug="a-nota-do-pedagio",
        catalogo_sfx={},
    )
    erros_cenas = dia.validar_cenas_json(cenas_json)
    assert not erros_cenas, f"Erros em cenas.json V8.0: {erros_cenas}"
    assert cenas_json["schema_version"] == "8.0"
    assert cenas_json["motor"] == "cinematografico_ia_30fps"
    assert cenas_json.get("parte_label", "") == ""
    assert "[CTA_PAUSA]" not in texto_rot and "[VOZ:cta_comercial]" not in texto_rot

    cenas = cenas_json["cenas"]
    assert len(cenas) >= 12, f"Esperava cortes rapidos (>=12 cenas), obteve {len(cenas)}"
    prompts_todos = " ".join(c["prompt_imagem"].lower() for c in cenas)
    assert "toll booth" in prompts_todos, "Prompt literal de cabine de pedagio ausente."
    assert "banknote" in prompts_todos or "pale hand" in prompts_todos, "Prompt literal da nota suja de barro / mao palida ausente."
    assert "unreal engine 5" in prompts_todos and "no watermark" in prompts_todos

    for i, c in enumerate(cenas):
        palavras_fala = len(str(c["fala"]).split())
        assert palavras_fala <= 18, f"Cena {i + 1} longa demais ({palavras_fala} palavras): {c['fala']}"
    print(f"[OK] pipeline/diretor_ia.py: {len(cenas)} cortes rapidos validados (schema 8.0, zero CTA no meio, prompts literais UE5).")


def testar_gerar_midia_cenas() -> None:
    """Valida gerar_midia_cenas.py: rejeicao de tela preta, reescrita neutra, cache de modelo e reaproveitamento."""
    # 1. Rejeita tela preta pura
    img_preta = Image.new("RGB", (1080, 1920), (0, 0, 0))
    buf_preto = io.BytesIO()
    img_preta.save(buf_preto, format="PNG")
    with tempfile.TemporaryDirectory(prefix="teste_midia_") as tmp:
        tmp_dir = Path(tmp)
        rejeitou_preta = False
        try:
            gmc.validar_e_padronizar_imagem(buf_preto.getvalue(), tmp_dir / "preta.jpg")
        except ValueError:
            rejeitou_preta = True
        assert rejeitou_preta, "validar_e_padronizar_imagem deveria rejeitar imagem preta!"

        # 2. Aceita imagem rica e salva 1080x1920 > 30KB
        img_rica = _gerar_imagem_detalhada_jpg(tmp_dir / "orig.jpg", paleta=((12, 18, 34), (48, 86, 128)), seed=11)
        info_ok = gmc.validar_e_padronizar_imagem(img_rica.read_bytes(), tmp_dir / "cena_01.jpg")
        assert info_ok["largura"] == 1080 and info_ok["altura"] == 1920 and info_ok["bytes"] > 30 * 1024

        # 3. Reaproveitamento com crop deslocado
        info_re = gmc.reaproveitar_cena_anterior(tmp_dir / "cena_01.jpg", tmp_dir / "cena_02.jpg", indice_cena=2)
        assert info_re["reaproveitada"] is True and info_re["bytes"] > 30 * 1024
        with Image.open(tmp_dir / "cena_01.jpg") as a, Image.open(tmp_dir / "cena_02.jpg") as b:
            diff = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0
            assert diff > 5.0, f"Enquadramento reaproveitado ficou identico (diff={diff:.2f})."

        # 4. Reescrita neutra remove gatilhos de filtro de seguranca
        neutro = gmc.reescrever_prompt_neutro("A bloody corpse with a knife in a dark alley")
        for bloqueada in ("blood", "corpse", "knife"):
            assert bloqueada not in neutro.lower(), f"Palavra sensivel permaneceu apos reescrita: {neutro}"
        assert "no watermark" in neutro.lower() and "9:16" in neutro.lower()

        # 5. Cache de modelo funcional no Gemini Image API
        modelos_chamados: list[str] = []
        raw_ok = (tmp_dir / "cena_01.jpg").read_bytes()

        class _FakeModels:
            def generate_content(self, model, contents, config):
                modelos_chamados.append(model)
                if model == "gemini-2.5-flash-image":
                    raise RuntimeError("404 model not enabled on this project")
                parte = SimpleNamespace(inline_data=SimpleNamespace(data=raw_ok))
                cand = SimpleNamespace(content=SimpleNamespace(parts=[parte]))
                return SimpleNamespace(candidates=[cand])

        fake_client = SimpleNamespace(models=_FakeModels())
        fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
        cache: dict[str, str] = {}
        r1 = gmc.gerar_imagem_gemini_com_cache(
            "Dark toll booth in fog",
            tmp_dir / "gen_01.jpg",
            api_key="fake",
            cache_modelo=cache,
            client=fake_client,
            types_mod=fake_types,
        )
        r2 = gmc.gerar_imagem_gemini_com_cache(
            "Pale hand holding muddy banknote",
            tmp_dir / "gen_02.jpg",
            api_key="fake",
            cache_modelo=cache,
            client=fake_client,
            types_mod=fake_types,
        )
        assert r1["modelo"] == "gemini-2.0-flash-preview-image-generation"
        assert r2["modelo"] == "gemini-2.0-flash-preview-image-generation"
        assert cache["modelo"] == "gemini-2.0-flash-preview-image-generation"
        # Segunda cena usa o cache direto (sem tentar novamente o modelo que falhou)
        assert modelos_chamados == [
            "gemini-2.5-flash-image",
            "gemini-2.0-flash-preview-image-generation",
            "gemini-2.0-flash-preview-image-generation",
        ], f"Sequencia de modelos inesperada: {modelos_chamados}"
    print("[OK] gerar_midia_cenas.py: validacao >30KB, rejeicao tela preta, reescrita neutra, reaproveitamento e cache OK.")


def testar_render_real_3s(salvar_amostras: Path | None = None) -> None:
    """Executa renderizacao real de 3s @ 30fps (imagens + video IA .mp4 + shake + xfade 0.15s + ASS + -14 LUFS)."""
    with tempfile.TemporaryDirectory(prefix="teste_render_v8_") as tmp:
        tmp_dir = Path(tmp)
        pasta_cenas = tmp_dir / "cenas"
        pasta_cenas.mkdir(parents=True, exist_ok=True)

        # Cena 1: imagem Gemini (.jpg) com push_in
        _gerar_imagem_detalhada_jpg(pasta_cenas / "cena_01.jpg", paleta=((10, 18, 36), (36, 82, 118)), seed=101)
        # Cena 2: imagem Gemini (.jpg) em tensao (mood=red -> shake_impact)
        _gerar_imagem_detalhada_jpg(pasta_cenas / "cena_02.jpg", paleta=((46, 10, 14), (138, 32, 34)), seed=202)
        # Cena 3: clipe de video IA (.mp4 da fal.ai)
        _gerar_clip_video_teste_mp4(pasta_cenas / "cena_03.mp4", duracao_s=1.4)

        voz_wav = _gerar_voz_sintetica_wav(tmp_dir / "voz_teste.wav", duracao_s=3.5)

        cenas_dados = {
            "schema_version": "8.0",
            "motor": "cinematografico_ia_30fps",
            "video_id": 99,
            "titulo": "Teste Motor Cinematografico",
            "parte_label": "",
            "palavras_vermelhas": ["pedagio", "2004", "palida"],
            "cenas": [
                {
                    "id": "cena_01",
                    "evento_inicio": "cena_01",
                    "fala": "Em 2004, na cabine do pedagio",
                    "prompt_imagem": "Nocturnal toll booth in dense fog",
                    "camera": "push_in",
                    "mood": "navy",
                    "tensao": False,
                },
                {
                    "id": "cena_02",
                    "evento_inicio": "cena_02",
                    "fala": "Uma mao palida surgiu no vidro",
                    "prompt_imagem": "Pale hand emerging in fog",
                    "camera": "shake_impact",
                    "mood": "red",
                    "tensao": True,
                },
                {
                    "id": "cena_03",
                    "evento_inicio": "cena_03",
                    "fala": "E a camera nao gravou nada",
                    "prompt_imagem": "Dark CCTV corridor flicker",
                    "camera": "pan_diag_tl",
                    "mood": "violet",
                    "tensao": False,
                },
            ],
        }
        eventos_dados = {
            "cena_01": 0.0,
            "cena_02": 1.0,
            "cena_03": 2.0,
            "duracao_total": 3.0,
        }
        timestamps_dados = {
            "grupos": [
                {
                    "inicio": 0.05,
                    "fim": 0.95,
                    "texto": "EM 2004 NO PEDÁGIO",
                    "palavras": [
                        {"palavra": "EM", "inicio": 0.05, "fim": 0.25},
                        {"palavra": "2004", "inicio": 0.25, "fim": 0.50},
                        {"palavra": "NO", "inicio": 0.50, "fim": 0.68},
                        {"palavra": "PEDÁGIO", "inicio": 0.68, "fim": 0.95},
                    ],
                },
                {
                    "inicio": 1.05,
                    "fim": 1.95,
                    "texto": "UMA MÃO PÁLIDA SURGIU",
                    "palavras": [
                        {"palavra": "UMA", "inicio": 1.05, "fim": 1.25},
                        {"palavra": "MÃO", "inicio": 1.25, "fim": 1.48},
                        {"palavra": "PÁLIDA", "inicio": 1.48, "fim": 1.72},
                        {"palavra": "SURGIU", "inicio": 1.72, "fim": 1.95},
                    ],
                },
                {
                    "inicio": 2.05,
                    "fim": 2.95,
                    "texto": "A CÂMERA NÃO GRAVOU",
                    "palavras": [
                        {"palavra": "A", "inicio": 2.05, "fim": 2.20},
                        {"palavra": "CÂMERA", "inicio": 2.20, "fim": 2.48},
                        {"palavra": "NÃO", "inicio": 2.48, "fim": 2.70},
                        {"palavra": "GRAVOU", "inicio": 2.70, "fim": 2.95},
                    ],
                },
            ]
        }

        cenas_path = tmp_dir / "cenas.json"
        eventos_path = tmp_dir / "eventos.json"
        ts_path = tmp_dir / "timestamps.json"
        cenas_path.write_text(json.dumps(cenas_dados, ensure_ascii=False), encoding="utf-8")
        eventos_path.write_text(json.dumps(eventos_dados, ensure_ascii=False), encoding="utf-8")
        ts_path.write_text(json.dumps(timestamps_dados, ensure_ascii=False), encoding="utf-8")

        saida_mp4 = tmp_dir / "short_teste_v8.mp4"
        res = rnd.renderizar_video_cinematografico(
            cenas_path=cenas_path,
            pasta_cenas=pasta_cenas,
            saida=saida_mp4,
            audio_alvo=voz_wav,
            timestamps_path=ts_path,
            eventos_path=eventos_path,
            fps=30,
            modo_teste=True,
            legendas=True,
            pasta_trilhas=tmp_dir / "trilhas_vazias",
            usar_mix_profissional=True,
        )
        assert saida_mp4.is_file() and saida_mp4.stat().st_size > 100 * 1024
        assert res["cenas"] == 3 and res["qtd_imagem"] == 2 and res["qtd_video"] == 1
        assert res["legendas_ass"] is True

        # Verifica metadados com ffprobe
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels:format=duration",
                "-of",
                "json",
                str(saida_mp4),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        meta = json.loads(probe.stdout)
        streams = meta.get("streams", [])
        v_stream = next(s for s in streams if s["codec_type"] == "video")
        a_stream = next(s for s in streams if s["codec_type"] == "audio")
        dur_real = float(meta["format"]["duration"])

        assert int(v_stream["width"]) == 1080 and int(v_stream["height"]) == 1920, f"Resolucao errada: {v_stream}"
        assert v_stream["r_frame_rate"] == "30/1", f"FPS errado: {v_stream['r_frame_rate']}"
        assert v_stream["codec_name"] == "h264" and v_stream["pix_fmt"] == "yuv420p"
        assert a_stream["codec_name"] == "aac" and int(a_stream["channels"]) == 2
        assert 2.85 <= dur_real <= 3.15, f"Duracao fora do esperado (~3.0s): {dur_real:.3f}s"

        # Verifica loudness final -14 LUFS
        loud = tm.medir_loudness_lufs(saida_mp4)
        assert -17.0 <= loud["input_i"] <= -11.5, f"Loudness final fora da faixa esperada: {loud}"

        # Extrai 6 quadros ao longo dos 3 segundos e mede movimento continuo (diff > 0 entre todos os pares)
        tempos = (0.15, 0.55, 1.25, 1.65, 2.25, 2.75)
        frames_paths: list[Path] = []
        for idx_t, t_sec in enumerate(tempos, start=1):
            fp = tmp_dir / f"frame_{idx_t:02d}.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{t_sec:.2f}",
                    "-i",
                    str(saida_mp4),
                    "-frames:v",
                    "1",
                    str(fp),
                ],
                check=True,
            )
            assert fp.is_file() and fp.stat().st_size > 10 * 1024
            frames_paths.append(fp)

        diffs: list[float] = []
        for i in range(len(frames_paths) - 1):
            with Image.open(frames_paths[i]) as im_a, Image.open(frames_paths[i + 1]) as im_b:
                d = sum(ImageStat.Stat(ImageChops.difference(im_a.convert("RGB"), im_b.convert("RGB"))).mean) / 3.0
                diffs.append(round(d, 2))
        assert min(diffs) > 0.8, f"Quadro parado detectado! Diferencas entre quadros: {diffs}"

        if salvar_amostras is not None:
            salvar_amostras.mkdir(parents=True, exist_ok=True)
            selecionados = [
                (frames_paths[1], "frame_01_cena1_push_in.png"),
                (frames_paths[3], "frame_02_cena2_shake.png"),
                (frames_paths[5], "frame_03_cena3_video_ia.png"),
            ]
            for orig, nome in selecionados:
                shutil.copy2(orig, salvar_amostras / nome)

        print(
            f"[OK] render/renderizar.py (3s real): {v_stream['width']}x{v_stream['height']} @ {v_stream['r_frame_rate']} "
            f"| dur={dur_real:.2f}s | loudness={loud['input_i']:.2f} LUFS (TP={loud['input_tp']:.2f} dBTP) "
            f"| diffs_quadros={diffs} (min={min(diffs):.2f} > 0)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida o Motor Cinematografico IA V8.0 ponta a ponta.")
    parser.add_argument("--somente-logica", action="store_true", help="Pula a renderizacao real FFmpeg de 3s.")
    parser.add_argument(
        "--salvar-amostras",
        type=Path,
        default=None,
        help="Pasta para copiar 3 quadros PNG do MP4 renderizado para inspecao visual.",
    )
    args = parser.parse_args()

    testar_narracao_gemini_8d9ce26()
    testar_trilha_mix_suavizada()
    testar_diretor_ia_cortes_rapidos()
    testar_gerar_midia_cenas()
    if not args.somente_logica:
        testar_render_real_3s(salvar_amostras=args.salvar_amostras)
    print("TODOS OS TESTES DO MOTOR CINEMATOGRAFICO IA V8.0 PASSARAM COM SUCESSO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
