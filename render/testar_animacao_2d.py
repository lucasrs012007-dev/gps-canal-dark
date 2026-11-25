"""Suite de validacao do Motor de Animacao 2D Real 30fps (Estacao 3 V7).

Uso (na raiz do repositorio):
    python3 render/testar_animacao_2d.py
    python3 render/testar_animacao_2d.py --salvar-amostras /tmp/amostras_v7
    python3 render/testar_animacao_2d.py --somente-logica

Valida:
1. Diretor IA V7: gera cenas.json (schema 7.0, motor=canvas_2d_30fps), sem repetir cenarios ou cameras
   em falas consecutivas e gerando hud_dado para anos/numeros (5 km, 2004, 2006).
2. Legendas sincronizadas: garante que anos (2004, 2006) e medidas (5 km) nao sao quebrados.
3. Renderizador travado em canvas + audio profissional (sidechaincompress + loudnorm -14 LUFS).
4. Render real de 3 segundos (90 quadros @ 30fps, 1080x1920) provando via diferenca de pixels entre
   quadros consecutivos que ha animacao continua em todos os segundos e zero JPEGs estaticos.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from audio.gerar_narracao import alinhar_palavras_na_frase, quebrar_em_grupos_legenda  # noqa: E402
from audio.trilha_mix import medir_loudness_lufs  # noqa: E402
from pipeline.diretor_ia import (  # noqa: E402
    compor_roteiro_e_cenas,
    diretor_mock_deterministico,
    validar_cenas_json,
)
from render.renderizar import (  # noqa: E402
    ALTURA,
    LARGURA,
    ClienteCDP,
    _encerrar_processo_navegador,
    abrir_cdp,
    avaliar_js,
    encontrar_navegador,
    iniciar_servidor,
    montar_comando_ffmpeg,
    porta_livre,
)


def testar_diretor_e_legendas() -> dict:
    blocos = [
        "[VOZ:suspense] Existe uma ilha onde nenhum barco pode chegar a menos de 5 km.",
        "[VOZ:urgencia] Em 2004, um tsunami gigante atingiu o oceano inteiro.",
        "[VOZ:terror] Um helicoptero sobrevoou a ilha e levou uma chuva de flechas.",
        "[VOZ:suspense] Em 2006, dois pescadores cruzaram o limite e nunca voltaram.",
        "[VOZ:calmo] Ate satelites em orbita monitoram o perimetro isolado em tempo real.",
        "[VOZ:urgencia] Cientistas analisam os dados no laboratorio ha decadas.",
        "[VOZ:calmo] E se voce pousasse la agora? Comente aqui embaixo.",
    ]
    roteiro_bruto = "\n".join(blocos)
    plano = diretor_mock_deterministico(
        roteiro_bruto=roteiro_bruto,
        titulo_forcado="Ilha Sentinela: o lugar proibido",
        catalogo_sfx={},
    )
    _roteiro_fmt, cenas, _tem_p2 = compor_roteiro_e_cenas(
        plano=plano,
        video_id=99,
        slug="ilha-sentinela",
        catalogo_sfx={},
    )
    erros = validar_cenas_json(cenas)
    assert not erros, f"validar_cenas_json falhou: {erros}"
    assert cenas.get("schema_version") == "7.0", f"schema_version inesperado: {cenas.get('schema_version')}"
    assert cenas.get("motor") == "canvas_2d_30fps", f"motor inesperado: {cenas.get('motor')}"

    lista = cenas["cenas"]
    assert len(lista) >= 6, f"Esperado >= 6 cenas, veio {len(lista)}"

    # Nenhum cenario ou camera repetido em falas consecutivas
    for i in range(1, len(lista)):
        assert lista[i]["cenario"] != lista[i - 1]["cenario"], (
            f"Cenario repetido nas cenas {i} e {i + 1}: {lista[i]['cenario']}"
        )
        assert lista[i]["camera"] != lista[i - 1]["camera"], (
            f"Camera repetida nas cenas {i} e {i + 1}: {lista[i]['camera']}"
        )

    huds = [c.get("hud_dado") for c in lista if c.get("hud_dado")]
    valores_hud = [str(h.get("valor", "")).upper() for h in huds]
    assert any("5 KM" in v for v in valores_hud), f"HUD '5 KM' ausente: {valores_hud}"
    assert any("2004" in v for v in valores_hud), f"HUD '2004' ausente: {valores_hud}"
    assert any("2006" in v for v in valores_hud), f"HUD '2006' ausente: {valores_hud}"

    # Verifica protecao de anos (2004, 2006) e medidas (5 km) nas legendas
    palavras_teste = alinhar_palavras_na_frase(
        "Em 2004 o tsunami atingiu a ilha e em 2006 o limite de 5 km continuou fechado.",
        0.0,
        4.8,
        [],
    )
    grupos = quebrar_em_grupos_legenda(palavras_teste)
    textos_grupos = [" ".join(p["palavra"] for p in g).upper() for g in grupos]
    assert any("EM 2004" in t for t in textos_grupos), f"'EM 2004' foi quebrado nas legendas: {textos_grupos}"
    assert any("EM 2006" in t for t in textos_grupos), f"'EM 2006' foi quebrado nas legendas: {textos_grupos}"
    assert any("5 KM" in t for t in textos_grupos), f"'5 KM' foi quebrado nas legendas: {textos_grupos}"

    print(
        f"[OK] Diretor IA V7 ({len(lista)} cenas sem repeticao consecutiva, HUDs={valores_hud}) "
        f"+ Legendas protegidas ({len(grupos)} grupos, 2004/2006/5 KM intactos).",
        flush=True,
    )
    return cenas


def testar_comando_ffmpeg() -> None:
    cmd = montar_comando_ffmpeg(
        saida=Path("/tmp/teste_cmd_canvas.mp4"),
        fps=30,
        audio_alvo=Path("/tmp/voz_fake.mp3"),
        duracao=3.0,
        usar_png=False,
        trilha_audio=None,
        usar_mix_profissional=True,
    )
    cmd_str = " ".join(cmd)
    assert "image2pipe" in cmd_str, "Comando FFmpeg nao usa image2pipe."
    assert "sidechaincompress" in cmd_str, "Comando FFmpeg sem ducking sidechaincompress."
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in cmd_str, "Comando FFmpeg sem normalizacao -14 LUFS."
    assert "zoompan" not in cmd_str, "Filtro zoompan de imagem estatica ainda presente!"

    # Garante que --motor storyboard e recusado
    res = subprocess.run(
        [sys.executable, str(RAIZ / "render" / "renderizar.py"), "--motor", "storyboard", "--dry-run-ffmpeg"],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, "renderizar.py deveria recusar --motor storyboard!"
    print("[OK] Comando FFmpeg Canvas validado (image2pipe + sidechaincompress + loudnorm -14 LUFS + bloqueio storyboard).", flush=True)


def _gerar_voz_sintetica_teste(destino_wav: Path, duracao: float = 3.5) -> None:
    """Gera audio vocal sintetico modulando fala/pausa para validar ducking e -14 LUFS."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=195:sample_rate=44100:duration={duracao:.2f}",
        "-af",
        "volume='if(lt(mod(t,1.2),0.85),0.45,0.02)':eval=frame",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(destino_wav),
    ]
    subprocess.run(cmd, check=True)


def testar_render_real_3s(salvar_amostras: Path | None = None) -> dict:
    """Executa render real de 3 segundos (90 quadros @ 30fps) via Chromium + FFmpeg e mede diferenca entre frames."""
    navegador = encontrar_navegador()
    duracao = 3.0
    fps = 30
    total_quadros = int(round(duracao * fps))

    cenas_dir_antigo = RAIZ / "output" / "cenas"
    jpegs_antes = list(cenas_dir_antigo.glob("*.jpg")) if cenas_dir_antigo.is_dir() else []

    with tempfile.TemporaryDirectory(prefix="teste-anim2d-") as tmp:
        tmp_dir = Path(tmp)
        voz_wav = tmp_dir / "voz_teste.wav"
        saida_mp4 = tmp_dir / "teste_3s_30fps.mp4"
        frames_dir = tmp_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        _gerar_voz_sintetica_teste(voz_wav, duracao=3.5)

        srv, porta_http = iniciar_servidor()
        porta_dbg = porta_livre()
        perfil_tmp = tempfile.mkdtemp(prefix="teste-cdp-")
        browser_proc = None
        cdp = None
        ff = None

        try:
            browser_proc, ws_url = abrir_cdp(navegador, porta_dbg, perfil_tmp)
            cdp = ClienteCDP(ws_url)
            cdp.chamar("Page.enable")
            cdp.chamar("Runtime.enable")
            cdp.chamar(
                "Emulation.setDeviceMetricsOverride",
                {"width": LARGURA, "height": ALTURA, "deviceScaleFactor": 1, "mobile": False},
            )
            cdp.chamar("Page.navigate", {"url": f"http://127.0.0.1:{porta_http}/player_universal.html"})

            pronto = False
            for _ in range(120):
                pronto = avaliar_js(
                    cdp,
                    "typeof window.renderAt === 'function' && "
                    "document.getElementById('play') && "
                    "!document.getElementById('play').disabled",
                )
                if pronto:
                    break
                time.sleep(0.1)
            assert pronto, "player_universal.html nao inicializou no tempo limite."

            # Ativa legendas para validar renderizacao visual completa
            avaliar_js(cdp, "document.getElementById('cc').click()")

            avaliar_js(
                cdp,
                "window.__cv = document.getElementById('c');"
                "window.__snap = t => { window.renderAt(t); return window.__cv.toDataURL('image/jpeg', 0.96).slice(23); };"
                "window.__snapPng = t => { window.renderAt(t); return window.__cv.toDataURL('image/png').slice(22); };",
            )

            cmd_ff = montar_comando_ffmpeg(
                saida=saida_mp4,
                fps=fps,
                audio_alvo=voz_wav,
                duracao=duracao,
                usar_png=False,
                trilha_audio=None,
                usar_mix_profissional=True,
            )
            ff = subprocess.Popen(cmd_ff, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            assert ff.stdin is not None

            t0 = time.monotonic()
            for i in range(total_quadros):
                t = i / fps
                b64 = avaliar_js(cdp, f"window.__snap({t:.6f})")
                ff.stdin.write(base64.b64decode(b64))
            ff.stdin.close()
            stderr_ff = ff.stderr.read().decode("utf-8", errors="replace") if ff.stderr else ""
            ret = ff.wait()
            assert ret == 0, f"ffmpeg falhou ({ret}): {stderr_ff}"
            tempo_render = time.monotonic() - t0

            if salvar_amostras is not None:
                salvar_amostras.mkdir(parents=True, exist_ok=True)
                shots_js = avaliar_js(cdp, "window.getShots()") or []
                vistos: set[str] = set()
                for sh in shots_js:
                    cen = str(sh.get("cenario") or sh.get("modulo") or "")
                    if not cen or cen in vistos:
                        continue
                    vistos.add(cen)
                    t_mid = (float(sh["start"]) + float(sh["end"])) * 0.5
                    b64_png = avaliar_js(cdp, f"window.__snapPng({t_mid:.4f})")
                    (salvar_amostras / f"cenario_{len(vistos):02d}_{cen}.png").write_bytes(base64.b64decode(b64_png))
        finally:
            if ff and ff.poll() is None:
                ff.kill()
                ff.wait()
            if cdp:
                cdp.fechar()
            _encerrar_processo_navegador(browser_proc)
            srv.shutdown()
            srv.server_close()
            shutil.rmtree(perfil_tmp, ignore_errors=True)

        # Valida stream de video e audio com ffprobe
        probe_res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames:format=duration",
                "-of",
                "json",
                str(saida_mp4),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        probe = json.loads(probe_res.stdout)
        v_streams = [s for s in probe["streams"] if s.get("codec_type") == "video"]
        a_streams = [s for s in probe["streams"] if s.get("codec_type") == "audio"]
        assert len(v_streams) == 1, f"Esperado 1 stream de video: {v_streams}"
        assert len(a_streams) == 1, f"Esperado 1 stream de audio: {a_streams}"
        vs = v_streams[0]
        assert int(vs["width"]) == LARGURA and int(vs["height"]) == ALTURA, f"Resolucao incorreta: {vs}"
        assert vs["r_frame_rate"] == "30/1", f"FPS inesperado: {vs['r_frame_rate']}"
        dur_out = float(probe["format"]["duration"])
        assert 2.8 <= dur_out <= 3.2, f"Duracao fora do esperado (~3.0s): {dur_out}"

        loud = medir_loudness_lufs(saida_mp4)

        # Extrai todos os 90 quadros e mede diferenca media absoluta entre quadros consecutivos em cada segundo
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(saida_mp4),
                str(frames_dir / "frame_%03d.png"),
            ],
            check=True,
        )
        arquivos_frames = sorted(frames_dir.glob("frame_*.png"))
        assert len(arquivos_frames) >= 85, f"Poucos quadros extraidos: {len(arquivos_frames)}"

        diffs_por_segundo: dict[int, list[float]] = {0: [], 1: [], 2: []}
        prev_img = Image.open(arquivos_frames[0]).convert("RGB")
        for idx in range(1, len(arquivos_frames)):
            cur_img = Image.open(arquivos_frames[idx]).convert("RGB")
            diff_img = ImageChops.difference(cur_img, prev_img)
            stat = ImageStat.Stat(diff_img)
            diff_val = float(sum(stat.mean) / len(stat.mean))
            sec_idx = min(2, (idx - 1) // fps)
            diffs_por_segundo[sec_idx].append(diff_val)
            prev_img = cur_img

        resumo_diffs: dict[str, dict[str, float]] = {}
        for sec, vals in diffs_por_segundo.items():
            assert vals, f"Segundo {sec} sem pares de quadros!"
            mn = min(vals)
            avg = sum(vals) / len(vals)
            mx = max(vals)
            assert mn > 0.0, f"Quadros congelados detectados no segundo {sec} (min_diff={mn})"
            resumo_diffs[f"segundo_{sec + 1}"] = {
                "pares": len(vals),
                "min_diff": round(mn, 4),
                "media_diff": round(avg, 4),
                "max_diff": round(mx, 4),
            }

        if salvar_amostras is not None:
            salvar_amostras.mkdir(parents=True, exist_ok=True)
            indices_amostra = [5, 45, min(len(arquivos_frames) - 1, 82)]
            for idx_a in indices_amostra:
                shutil.copy2(arquivos_frames[idx_a], salvar_amostras / f"amostra_f{idx_a + 1:03d}.png")

        jpegs_depois = list(cenas_dir_antigo.glob("*.jpg")) if cenas_dir_antigo.is_dir() else []
        assert len(jpegs_depois) == len(jpegs_antes) == 0, f"JPEGs estaticos detectados em {cenas_dir_antigo}: {jpegs_depois}"

        resultado = {
            "resolucao": f"{vs['width']}x{vs['height']}",
            "fps": vs["r_frame_rate"],
            "quadros_extraidos": len(arquivos_frames),
            "duracao_s": round(dur_out, 3),
            "tamanho_kb": round(saida_mp4.stat().st_size / 1024.0, 1),
            "tempo_render_s": round(tempo_render, 2),
            "lufs": round(loud["input_i"], 2),
            "true_peak_dbtp": round(loud["input_tp"], 2),
            "jpegs_estaticos": len(jpegs_depois),
            "diferenca_pixels_consecutivos": resumo_diffs,
        }
        print("[OK] Render real 3s @ 30fps aprovado:", json.dumps(resultado, ensure_ascii=False), flush=True)
        return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida o Motor de Animacao 2D Real 30fps (V7).")
    parser.add_argument(
        "--somente-logica",
        action="store_true",
        help="Roda apenas testes de Diretor IA, legendas e comando FFmpeg sem abrir Chromium.",
    )
    parser.add_argument(
        "--salvar-amostras",
        type=Path,
        default=None,
        help="Diretorio opcional para salvar 3 quadros PNG de inspecao visual.",
    )
    args = parser.parse_args()

    testar_diretor_e_legendas()
    testar_comando_ffmpeg()
    if not args.somente_logica:
        testar_render_real_3s(salvar_amostras=args.salvar_amostras)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
