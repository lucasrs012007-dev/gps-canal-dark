"""Teste rapido local/simulado da Estacao 3 (Motor Hibrido Storyboard IA + FFmpeg 1080p).

Valida sem rede externa e sem sujar o repositorio:
1. Sintaxe Python (`py_compile`) de gerar_cenas_visuais.py, render/renderizar.py e integracoes.
2. Ausencia de emoji e travessoes (em-dash / en-dash) nos arquivos alterados.
3. Integridade estrutural e YAML do workflow `.github/workflows/fabrica_dark.yml`.
4. Fluxo de gerar_cenas_visuais.py: URL exata do Pollinations, retry quando resposta e HTML ou <= 20 KB,
   validacao de imagem valida (> 20 KB, 1080x1920) e modo `--mock`.
5. Geracao do comando FFmpeg (zoompan alternado, xfade, vinheta, legendas ASS UTF-8 na area segura,
   flags `-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30`) e render real rapido (2s)
   verificado com ffprobe + descoberta em upload_youtube.py.

Uso:
    python3 render/testar_storyboard.py
    python3 render/testar_storyboard.py --somente-comando
"""

from __future__ import annotations

import argparse
import io
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gerar_cenas_visuais as gcv  # noqa: E402
import upload_youtube as uy  # noqa: E402
from pipeline import diretor_ia as dia  # noqa: E402
from render import renderizar as rnd  # noqa: E402


def validar_py_compile() -> None:
    alvos = [
        RAIZ / "gerar_cenas_visuais.py",
        RAIZ / "audio" / "trilha_mix.py",
        RAIZ / "render" / "renderizar.py",
        RAIZ / "render" / "testar_storyboard.py",
        RAIZ / "pipeline" / "diretor_ia.py",
        RAIZ / "upload_youtube.py",
        RAIZ / "automacao" / "enviar_telegram.py",
    ]
    for arq in alvos:
        py_compile.compile(str(arq), doraise=True)
    print(f"[OK] py_compile aprovado em {len(alvos)} arquivos Python.")


def validar_higiene() -> None:
    re_emoji = re.compile(
        "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F]+",
        flags=re.UNICODE,
    )
    for rel in (
        "gerar_cenas_visuais.py",
        "audio/trilha_mix.py",
        "render/renderizar.py",
        "render/testar_storyboard.py",
        ".github/workflows/fabrica_dark.yml",
    ):
        txt = (RAIZ / rel).read_text(encoding="utf-8")
        assert "\u2014" not in txt, f"em-dash encontrado em {rel}"
        assert "\u2013" not in txt, f"en-dash encontrado em {rel}"
        assert not re_emoji.search(txt), f"emoji encontrado em {rel}"
    print("[OK] Higiene verificada (zero emoji, zero em-dash/en-dash).")


def _carregar_yaml_workflow(wf_path: Path) -> dict:
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except ImportError:
        py_sys = "/usr/bin/python3"
        if Path(py_sys).is_file():
            out = subprocess.check_output(
                [
                    py_sys,
                    "-c",
                    "import json, yaml, sys; print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))",
                    str(wf_path),
                ],
                text=True,
            )
            return json.loads(out)
        raise RuntimeError("PyYAML indisponivel para validar .github/workflows/fabrica_dark.yml.")


def validar_workflow() -> None:
    wf_path = RAIZ / ".github" / "workflows" / "fabrica_dark.yml"
    dados = _carregar_yaml_workflow(wf_path)
    on_block = dados.get("on") or dados.get(True) or dados.get("true")
    assert isinstance(on_block, dict), "Bloco 'on' invalido no workflow."
    assert "schedule" not in on_block, "schedule nativo nao deve existir no workflow."
    assert "workflow_dispatch" in on_block, "workflow_dispatch ausente."

    steps = dados["jobs"]["produzir-e-renderizar"]["steps"]
    nomes = [str(s.get("name", "")) for s in steps]
    idx_inst = next(i for i, n in enumerate(nomes) if "Instalar dependencias Python" in n)
    idx_st3 = next(i for i, n in enumerate(nomes) if "Estacao 3" in n)
    idx_yt = next(i for i, n in enumerate(nomes) if n == "Publicar no YouTube Shorts")
    idx_tg = next(i for i, n in enumerate(nomes) if "Estacao 4" in n)

    assert idx_st3 < idx_yt < idx_tg, f"Ordem inesperada dos passos: st3={idx_st3}, yt={idx_yt}, tg={idx_tg}"

    run_inst = str(steps[idx_inst].get("run", ""))
    for pkg in ("Pillow", "google-genai", "google-api-python-client"):
        assert pkg in run_inst, f"Pacote ausente na instalacao do workflow: {pkg}"

    st3 = steps[idx_st3]
    run_st3 = str(st3.get("run", ""))
    env_st3 = st3.get("env") or {}
    assert "GEMINI_API_KEY" in env_st3, "Estacao 3 precisa receber GEMINI_API_KEY."
    assert "gerar_cenas_visuais.py" in run_st3, "Estacao 3 precisa executar gerar_cenas_visuais.py."
    assert "render/renderizar.py --legendas" in run_st3, "Estacao 3 precisa executar render/renderizar.py --legendas."
    assert run_st3.index("gerar_cenas_visuais.py") < run_st3.index("render/renderizar.py"), (
        "gerar_cenas_visuais.py precisa rodar antes de render/renderizar.py."
    )
    print(
        f"[OK] Workflow YAML valido ({len(steps)} passos | Estacao 3={idx_st3}, YouTube={idx_yt}, Telegram={idx_tg})."
    )


def validar_gerador_cenas_simulado() -> None:
    url = gcv.montar_url_pollinations("Dark hallway scene, moody lighting", seed=123456)
    assert url.startswith("https://image.pollinations.ai/prompt/"), url
    assert "width=1080&height=1920&nologo=true&seed=123456" in url, url

    with tempfile.TemporaryDirectory(prefix="teste-gcv-") as td:
        tdir = Path(td)
        # Cria JPEG real > 25 KB para simular resposta valida do Pollinations na 3a tentativa
        jpg_valido_path = tdir / "valido.jpg"
        gcv.gerar_imagem_fallback_procedural(jpg_valido_path, mood="navy", seed=777, indice=1)
        bytes_validos = jpg_valido_path.read_bytes()
        assert len(bytes_validos) > gcv.MIN_BYTES_IMAGEM

        chamadas = {"n": 0}

        class _FakeResp:
            def __init__(self, payload: bytes):
                self._buf = io.BytesIO(payload)

            def read(self) -> bytes:
                return self._buf.read()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=30):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return _FakeResp(b"<html><body>502 Bad Gateway</body></html>")
            if chamadas["n"] == 2:
                return _FakeResp(b"\xff\xd8\xff" + b"\x00" * 4096)  # <= 20 KB -> deve rejeitar
            return _FakeResp(bytes_validos)

        raw_out = tdir / "raw.bin"
        ok, det = gcv.gerar_imagem_pollinations(
            "Dark cinematic office in zero gravity",
            seed=555555,
            destino_raw=raw_out,
            max_tentativas=4,
            urlopen_fn=_fake_urlopen,
            sleep_fn=lambda _s: None,
        )
        assert ok, f"Pollinations simulado deveria aprovar na 3a tentativa: {det}"
        assert chamadas["n"] == 3, f"Esperava 3 tentativas (HTML + <20KB + valido), teve {chamadas['n']}"

        norm_jpg = tdir / "cena_01.jpg"
        gcv.normalizar_para_jpeg_1080x1920(raw_out, norm_jpg)
        ok_v, info_v = gcv.validar_arquivo_imagem(norm_jpg)
        assert ok_v, f"Imagem normalizada invalida: {info_v}"
        assert "1080x1920" in info_v, info_v

    print("[OK] gerar_cenas_visuais.py validado (URL Pollinations, retry HTML/<20KB, 1080x1920 >20KB).")


def validar_ffmpeg_storyboard(executar_render_real: bool = True) -> None:
    with tempfile.TemporaryDirectory(prefix="teste-sb-") as td:
        tdir = Path(td)
        hist_copy = tdir / "historico_videos.json"
        shutil.copy2(RAIZ / "historico_videos.json", hist_copy)

        res_dir = dia.produzir_direcao_v6(
            usar_mock=True,
            gerar_inedito=True,
            caminho_historico=hist_copy,
            dir_saida=tdir,
            atualizar_historico=True,
            pilar_editorial="cenarios_hipoteticos",
        )
        cenas_path = res_dir["cenas_path"]
        pasta_cenas = tdir / "output" / "cenas"

        manif = gcv.gerar_todas_cenas_visuais(
            cenas_path=cenas_path,
            saida_dir=pasta_cenas,
            usar_mock=True,
            max_cenas=3,
        )
        assert manif["total_cenas"] == 3
        for i in range(1, 4):
            img_p = pasta_cenas / f"cena_{i:02d}.jpg"
            ok_i, info_i = gcv.validar_arquivo_imagem(img_p)
            assert ok_i, f"{img_p.name} invalida: {info_i}"

        cenas_dados = json.loads(cenas_path.read_text(encoding="utf-8"))
        cenas_dados["cenas"] = cenas_dados["cenas"][:3]
        eventos_sim = {
            "cena_01": 0.0,
            "cena_02": 1.1,
            "cena_03": 2.2,
            "duracao_total": 3.2,
        }
        timestamps_sim = {
            "grupos": [
                {
                    "texto": "VOCÊ NÃO VAI",
                    "inicio": 0.0,
                    "fim": 1.0,
                    "palavras": [
                        {"palavra": "VOCÊ", "inicio": 0.0, "fim": 0.35},
                        {"palavra": "NÃO", "inicio": 0.35, "fim": 0.65},
                        {"palavra": "VAI", "inicio": 0.65, "fim": 1.0},
                    ],
                },
                {
                    "texto": "SAIR DO CHÃO",
                    "inicio": 1.05,
                    "fim": 2.0,
                    "palavras": [
                        {"palavra": "SAIR", "inicio": 1.05, "fim": 1.35},
                        {"palavra": "DO", "inicio": 1.35, "fim": 1.55},
                        {"palavra": "CHÃO", "inicio": 1.55, "fim": 2.0},
                    ],
                },
            ]
        }

        dur_teste = 2.0
        timeline = rnd.construir_timeline_cenas(
            cenas_dados=cenas_dados,
            eventos_dados=eventos_sim,
            duracao_total=dur_teste,
            pasta_cenas=pasta_cenas,
        )
        assert len(timeline) >= 2
        for i in range(1, len(timeline)):
            assert timeline[i]["movimento"] != timeline[i - 1]["movimento"], "Movimentos consecutivos repetidos"

        ass_path = rnd.gerar_legenda_ass(
            timestamps_dados=timestamps_sim,
            destino_ass=tdir / "legendas.ass",
            duracao_max=dur_teste,
            palavras_vermelhas=["chao", "panico"],
        )
        assert ass_path is not None and ass_path.is_file()
        ass_txt = ass_path.read_text(encoding="utf-8")
        assert "VOCÊ" in ass_txt and "CHÃO" in ass_txt and "MarginV" in ass_txt

        out_dir = tdir / "output"
        saida_mp4 = out_dir / "short_99.mp4"
        cmd = rnd.montar_comando_ffmpeg_storyboard(
            timeline=timeline,
            saida=saida_mp4,
            fps=30,
            audio_alvo=None,
            duracao=dur_teste,
            arquivo_ass=ass_path,
        )
        cmd_str = " ".join(cmd)
        assert "zoompan=" in cmd_str
        assert "vignette=" in cmd_str
        assert "xfade=" in cmd_str
        assert "ass=filename=" in cmd_str
        for flag_par in (
            ("-c:v", "libx264"),
            ("-preset", "medium"),
            ("-crf", "18"),
            ("-pix_fmt", "yuv420p"),
            ("-r", "30"),
        ):
            idx_f = cmd.index(flag_par[0])
            assert cmd[idx_f + 1] == flag_par[1], f"Flag esperada {flag_par}, encontrado {cmd[idx_f:idx_f + 2]}"
        print(f"[OK] Comando FFmpeg storyboard validado ({len(timeline)} cenas, zoompan + xfade + vignette + ASS).")

        if executar_render_real and shutil.which("ffmpeg") and shutil.which("ffprobe"):
            res = subprocess.run(cmd, capture_output=True, text=True)
            assert res.returncode == 0, f"FFmpeg falhou: {res.stderr}"
            probe = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name,width,height,pix_fmt,r_frame_rate:format=duration",
                        "-of",
                        "json",
                        str(saida_mp4),
                    ],
                    text=True,
                )
            )
            st = probe["streams"][0]
            dur_real = float(probe["format"]["duration"])
            assert st["codec_name"] == "h264", st
            assert (st["width"], st["height"]) == (1080, 1920), st
            assert st["pix_fmt"] == "yuv420p", st
            assert st["r_frame_rate"] == "30/1", st
            assert 1.85 <= dur_real <= 2.15, dur_real

            # Compatibilidade com upload_youtube.py
            achado = uy.descobrir_video_completo(out_dir)
            assert achado == saida_mp4, f"upload_youtube nao descobriu {saida_mp4}: {achado}"
            print(
                f"[OK] Render real 1080x1920 aprovado ({saida_mp4.name}: {saida_mp4.stat().st_size / 1024:.1f} KB, "
                f"{st['width']}x{st['height']} @ {st['r_frame_rate']} {st['codec_name']} {st['pix_fmt']}, dur={dur_real:.2f}s)."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste rapido local da Estacao 3 (Storyboard IA + FFmpeg 1080p).")
    parser.add_argument(
        "--somente-comando",
        action="store_true",
        help="Valida py_compile, workflow, Pollinations simulado e comando FFmpeg sem executar encode real.",
    )
    args = parser.parse_args()

    validar_py_compile()
    validar_higiene()
    validar_workflow()
    validar_gerador_cenas_simulado()
    validar_ffmpeg_storyboard(executar_render_real=not args.somente_comando)
    print("TODOS OS TESTES DA ESTACAO 3 PASSARAM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
