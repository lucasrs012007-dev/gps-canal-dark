"""Estacao 4 (v5 otimizada): renderiza player.html (1080x1920, 30 fps) e fatia Parte 1 / Parte 2.

Uso (na raiz do repositorio):
    python3 render/renderizar.py           # render completo (output/short_06.mp4 + parte1 + parte2)
    python3 render/renderizar.py --teste   # render rapido de 2s para validacao
    python3 render/renderizar.py --legendas
    python3 render/renderizar.py --png     # transporte PNG lossless (mais lento na CPU)

Recursos V5 (video-director + trava blindada + corte automatico):
- Valida obrigatoriamente video_id, titulo, roteiro_sha256, CTA ('COMENTE EU QUERO') e corte_parte_2
  via pipeline/historico.py antes de iniciar o render quando houver audio/JSONs em audio/.
- Transporte MJPEG q=0.96 por padrao com codificacao H.264 CRF 18 (-preset fast -tune animation).
- Quando corte_parte_2 estiver definido (videos longos de 2 partes) e nao for --teste,
  fatia automaticamente short_NN_parte1.mp4 e short_NN_parte2.mp4 via FFmpeg sem re-renderizar o Chromium.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.historico import (  # noqa: E402
    caminho_saida_atual,
    caminhos_partes_atual,
    obter_video_atual,
    validar_artefatos_audio,
)

PASTA_AUDIO = RAIZ / "audio"
AUDIO_MIX = PASTA_AUDIO / "mix_final.mp3"
AUDIO_MP3 = PASTA_AUDIO / "narracao.mp3"
LARGURA = 1080
ALTURA = 1920
DURACAO_PREVIA = 109.0
FOLGA_AUDIO = 0.3


class ServidorSilencioso(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, format, *args):
        pass


def porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def iniciar_servidor() -> tuple[http.server.ThreadingHTTPServer, int]:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ServidorSilencioso)
    porta = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, porta


def encontrar_navegador(explicit: str | None = None) -> str:
    if explicit:
        caminho = shutil.which(explicit) or explicit
        if Path(caminho).is_file():
            return caminho
        raise SystemExit(f"Navegador informado nao encontrado: {explicit}")

    env_bin = os.environ.get("CHROME_BIN") or os.environ.get("BROWSER_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    nomes = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "msedge",
        "chrome",
    ]
    for nome in nomes:
        achado = shutil.which(nome)
        if achado:
            return achado

    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidatos:
        if c and Path(c).is_file():
            return c

    raise SystemExit(
        "Nenhum Chrome, Chromium ou Edge encontrado. Instale um deles ou passe --navegador <caminho>."
    )


def duracao_audio_ffprobe(caminho: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(caminho),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


class ClienteCDP:
    """Cliente WebSocket RFC 6455 minimo em stdlib para Chrome DevTools Protocol."""

    def __init__(self, ws_url: str, timeout: float = 60.0):
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._buf = bytearray()
        self._seq = 0

        chave = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {chave}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))

        cab = self._ler_ate(b"\r\n\r\n").decode("iso-8859-1")
        if " 101 " not in cab.splitlines()[0]:
            raise RuntimeError(f"Falha no handshake WebSocket CDP: {cab.splitlines()[0]}")
        esperado = base64.b64encode(
            hashlib.sha1((chave + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if esperado not in cab:
            raise RuntimeError("Resposta Sec-WebSocket-Accept invalida.")

    def _ler_ate(self, marcador: bytes) -> bytes:
        while True:
            idx = self._buf.find(marcador)
            if idx != -1:
                fim = idx + len(marcador)
                out = bytes(self._buf[:fim])
                del self._buf[:fim]
                return out
            pedaco = self.sock.recv(65536)
            if not pedaco:
                raise ConnectionError("Conexao CDP encerrada durante handshake.")
            self._buf.extend(pedaco)

    def _ler_exato(self, n: int) -> bytes:
        while len(self._buf) < n:
            pedaco = self.sock.recv(max(65536, n - len(self._buf)))
            if not pedaco:
                raise ConnectionError("Conexao CDP encerrada inesperadamente.")
            self._buf.extend(pedaco)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def _enviar_quadro(self, opcode: int, payload: bytes) -> None:
        tam = len(payload)
        cab = bytearray([0x80 | opcode])
        if tam < 126:
            cab.append(0x80 | tam)
        elif tam < 65536:
            cab.append(0x80 | 126)
            cab.extend(struct.pack("!H", tam))
        else:
            cab.append(0x80 | 127)
            cab.extend(struct.pack("!Q", tam))
        mascara = os.urandom(4)
        cab.extend(mascara)
        mascarado = bytes(b ^ mascara[i & 3] for i, b in enumerate(payload))
        self.sock.sendall(bytes(cab) + mascarado)

    def _ler_mensagem(self) -> str:
        partes = []
        while True:
            b1, b2 = self._ler_exato(2)
            fin = (b1 & 0x80) != 0
            opcode = b1 & 0x0F
            mascarado = (b2 & 0x80) != 0
            tam = b2 & 0x7F
            if tam == 126:
                (tam,) = struct.unpack("!H", self._ler_exato(2))
            elif tam == 127:
                (tam,) = struct.unpack("!Q", self._ler_exato(8))
            chave = self._ler_exato(4) if mascarado else b""
            dados = self._ler_exato(tam) if tam else b""
            if mascarado:
                dados = bytes(b ^ chave[i & 3] for i, b in enumerate(dados))

            if opcode == 0x8:
                raise ConnectionError("Navegador fechou o canal CDP.")
            if opcode == 0x9:
                self._enviar_quadro(0xA, dados)
                continue
            if opcode == 0xA:
                continue
            partes.append(dados)
            if fin:
                return b"".join(partes).decode("utf-8")

    def chamar(self, metodo: str, params: dict | None = None) -> dict:
        self._seq += 1
        req_id = self._seq
        msg = json.dumps({"id": req_id, "method": metodo, "params": params or {}})
        self._enviar_quadro(0x1, msg.encode("utf-8"))
        while True:
            resp = json.loads(self._ler_mensagem())
            if resp.get("id") == req_id:
                if "error" in resp:
                    raise RuntimeError(f"Erro CDP em {metodo}: {resp['error']}")
                return resp.get("result", {})

    def fechar(self) -> None:
        try:
            self._enviar_quadro(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


def abrir_cdp(navegador: str, porta_dbg: int, perfil_tmp: str) -> tuple[subprocess.Popen, str]:
    cmd = [
        navegador,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--mute-audio",
        f"--window-size={LARGURA},{ALTURA}",
        f"--remote-debugging-port={porta_dbg}",
        f"--user-data-dir={perfil_tmp}",
        "about:blank",
    ]
    if os.name != "nt":
        cmd.insert(2, "--no-sandbox")
        cmd.insert(3, "--disable-dev-shm-usage")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url_lista = f"http://127.0.0.1:{porta_dbg}/json/list"

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f"Navegador encerrou antes de abrir o CDP (codigo {proc.returncode}).")
        try:
            with opener.open(url_lista, timeout=1.0) as r:
                alvos = [a for a in json.loads(r.read()) if a.get("type") == "page"]
                if alvos and alvos[0].get("webSocketDebuggerUrl"):
                    return proc, alvos[0]["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError("Tempo esgotado aguardando a porta CDP do navegador.")


def avaliar_js(cdp: ClienteCDP, expressao: str):
    res = cdp.chamar(
        "Runtime.evaluate",
        {"expression": expressao, "returnByValue": True, "awaitPromise": True},
    )
    if "exceptionDetails" in res:
        raise RuntimeError(f"Erro JS no player.html: {res['exceptionDetails']}")
    return res.get("result", {}).get("value")


def montar_comando_ffmpeg(
    saida: Path,
    fps: int,
    audio_alvo: Path | None,
    duracao: float,
    usar_png: bool = False,
) -> list[str]:
    vcodec_pipe = "png" if usar_png else "mjpeg"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "image2pipe",
        "-vcodec",
        vcodec_pipe,
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
    ]
    if audio_alvo is not None:
        cmd.extend(["-i", str(audio_alvo), "-map", "0:v:0", "-map", "1:a:0", "-af", "apad"])
    else:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
            ]
        )
    cmd.extend(
        [
            "-vf",
            "noise=alls=3:allf=t",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-tune",
            "animation",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k" if audio_alvo is not None else "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            "-t",
            f"{duracao:.3f}",
            "-movflags",
            "+faststart",
            str(saida),
        ]
    )
    return cmd


def selecionar_audio() -> Path | None:
    """Prioriza audio/mix_final.mp3 (voz + sound design), com fallback para audio/narracao.mp3."""
    for candidato in (AUDIO_MIX, AUDIO_MP3):
        if candidato.is_file() and candidato.stat().st_size > 0:
            return candidato
    return None


def fatiar_partes_ffmpeg(
    saida_completa: Path,
    corte_parte_2: float,
    saidas_partes: list[Path] | None = None,
) -> tuple[Path, Path]:
    """Fatia o MP4 completo em Parte 1 (0..corte) e Parte 2 (corte..fim) com precisao de quadro sem re-renderizar."""
    if not saida_completa.is_file():
        raise RuntimeError(f"Arquivo de entrada ausente para fatiamento: {saida_completa}")

    dur_total = duracao_audio_ffprobe(saida_completa)
    if corte_parte_2 <= 0.2 or corte_parte_2 >= dur_total - 0.2:
        raise RuntimeError(
            f"corte_parte_2={corte_parte_2:.3f}s invalido para duracao total {dur_total:.3f}s."
        )

    if saidas_partes and len(saidas_partes) >= 2:
        p1, p2 = Path(saidas_partes[0]), Path(saidas_partes[1])
    else:
        p1 = saida_completa.with_name(f"{saida_completa.stem}_parte1{saida_completa.suffix}")
        p2 = saida_completa.with_name(f"{saida_completa.stem}_parte2{saida_completa.suffix}")

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    args_encode = [
        "-vf",
        "setpts=PTS-STARTPTS",
        "-af",
        "asetpts=PTS-STARTPTS",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-tune",
        "animation",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
    ]

    cmd_p1 = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(saida_completa),
        "-t",
        f"{corte_parte_2:.3f}",
        *args_encode,
        str(p1),
    ]
    # Seek preciso apos -i + setpts/asetpts zera start_time de video e audio em 0.000s no inicio da Parte 2
    cmd_p2 = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(saida_completa),
        "-ss",
        f"{corte_parte_2:.3f}",
        *args_encode,
        str(p2),
    ]

    subprocess.run(cmd_p1, check=True)
    subprocess.run(cmd_p2, check=True)
    return p1, p2


def main() -> None:
    parser = argparse.ArgumentParser(description="Renderiza player.html para MP4 9:16 (1080x1920).")
    parser.add_argument("--teste", action="store_true", help="Renderiza apenas os 2 primeiros segundos.")
    parser.add_argument("--fps", type=int, default=30, help="Quadros por segundo (padrao: 30).")
    parser.add_argument(
        "--saida",
        "-o",
        type=Path,
        default=None,
        help="Arquivo MP4 de saida (padrao: proximo numero livre em historico_videos.json).",
    )
    parser.add_argument("--legendas", action="store_true", help="Ativa as legendas sincronizadas do player.")
    parser.add_argument("--png", action="store_true", help="Usa PNG lossless no pipe (mais lento na CPU).")
    parser.add_argument("--navegador", type=str, default=None, help="Caminho manual do Chrome/Chromium/Edge.")
    parser.add_argument(
        "--player",
        type=str,
        default=None,
        help="Arquivo HTML do player relativo a raiz (padrao: campo 'player' em historico_videos.json ou player.html).",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    video_ativo = obter_video_atual(validar=True)
    player_rel = (args.player or str(video_ativo.get("player", "player.html"))).strip() or "player.html"
    player_path = Path(player_rel)
    if not player_path.is_absolute():
        player_path = (RAIZ / player_path).resolve()
    if not player_path.is_file():
        raise SystemExit(f"Player HTML nao encontrado: {player_path}")
    try:
        player_url_rel = player_path.relative_to(RAIZ).as_posix()
    except ValueError as exc:
        raise SystemExit(f"Player HTML precisa estar dentro do repositorio ({RAIZ}): {player_path}") from exc

    audio_alvo = selecionar_audio()
    tem_artefato_json = (PASTA_AUDIO / "timestamps.json").is_file() or (PASTA_AUDIO / "eventos.json").is_file()

    # Trava blindada: sempre que houver audio ou JSONs em audio/, exige integridade 100% com video_atual + CTA.
    cta_modo = str(video_ativo.get("cta_modo", "final")).strip().lower() or "final"
    corte_parte_2: float | None = None
    if audio_alvo is not None or tem_artefato_json:
        val = validar_artefatos_audio(PASTA_AUDIO)
        c = val["carimbo"]
        cta_modo = c["cta_modo"]
        ev_corte = val["eventos"].get("corte_parte_2")
        if ev_corte is not None:
            corte_parte_2 = float(ev_corte)
        extra_p2 = f", corte_parte_2={corte_parte_2:.2f}s" if corte_parte_2 is not None else ""
        print(
            f"Trava de audio OK: Video {c['video_id']:02d} '{c['titulo']}' "
            f"(sha256={c['roteiro_sha256'][:12]}, CTA confirmada [modo={cta_modo}{extra_p2}])."
        )

    saida_padrao = caminho_saida_atual()
    saida = args.saida if args.saida is not None else saida_padrao
    if not saida.is_absolute():
        saida = RAIZ / saida
    saida.parent.mkdir(parents=True, exist_ok=True)

    navegador = encontrar_navegador(args.navegador)
    print(
        f"Historico validado (Sempre Video Novo): Video {int(video_ativo['id']):02d} "
        f"'{video_ativo['titulo']}' [player={player_url_rel}] -> "
        f"{saida.relative_to(RAIZ).as_posix() if saida.is_relative_to(RAIZ) else saida}"
    )

    srv, porta_http = iniciar_servidor()
    porta_dbg = porta_livre()
    perfil_tmp = tempfile.mkdtemp(prefix="render-cdp-")
    browser_proc = None
    cdp = None
    ff = None
    inicio = time.monotonic()

    try:
        browser_proc, ws_url = abrir_cdp(navegador, porta_dbg, perfil_tmp)
        cdp = ClienteCDP(ws_url)
        cdp.chamar("Page.enable")
        cdp.chamar("Runtime.enable")
        cdp.chamar(
            "Emulation.setDeviceMetricsOverride",
            {"width": LARGURA, "height": ALTURA, "deviceScaleFactor": 1, "mobile": False},
        )
        cdp.chamar("Page.navigate", {"url": f"http://127.0.0.1:{porta_http}/{player_url_rel}"})

        pronto = False
        for _ in range(100):
            pronto = avaliar_js(
                cdp,
                "typeof window.renderAt === 'function' && "
                "document.getElementById('play') && "
                "!document.getElementById('play').disabled",
            )
            if pronto:
                break
            time.sleep(0.1)
        if not pronto:
            raise RuntimeError(f"{player_url_rel} nao ficou pronto dentro do tempo limite.")

        status_player = avaliar_js(cdp, "(document.getElementById('status')?.textContent || '').trim()")
        if status_player:
            print(f"Player: {status_player}", flush=True)

        if corte_parte_2 is None:
            corte_js = avaliar_js(
                cdp,
                "typeof window.getCorteParte2 === 'function' ? window.getCorteParte2() : null",
            )
            if corte_js is not None:
                corte_parte_2 = float(corte_js)

        dur_player = float(avaliar_js(cdp, "typeof window.getDuration === 'function' ? window.getDuration() : 109"))
        if audio_alvo is not None:
            folga = 0.05 if cta_modo in ("meio", "pausa_meio") else FOLGA_AUDIO
            duracao_real = duracao_audio_ffprobe(audio_alvo) + folga
            modo = f"com audio ({audio_alvo.name}, {duracao_real:.2f}s incluindo folga de {folga}s)"
        else:
            duracao_real = dur_player or DURACAO_PREVIA
            modo = f"mudo / Modo Previa ({duracao_real:.1f}s)"

        duracao = min(2.0, duracao_real) if args.teste else duracao_real
        total_quadros = max(1, int(round(duracao * args.fps)))
        pipe_fmt = "PNG" if args.png else "MJPEG q=0.96"

        print(f"Navegador: {navegador}")
        print(f"Modo: {modo}{' [TESTE 2s]' if args.teste else ''} | Pipe: {pipe_fmt}")
        print(f"Renderizando {total_quadros} quadros ({LARGURA}x{ALTURA} @ {args.fps} fps) -> {saida}")

        if args.legendas:
            avaliar_js(cdp, "document.getElementById('cc').click()")

        dims = avaliar_js(cdp, "(() => { const c = document.getElementById('c'); return [c.width, c.height]; })()")
        if dims != [LARGURA, ALTURA]:
            raise RuntimeError(f"Canvas com resolucao inesperada: {dims} (esperado {[LARGURA, ALTURA]}).")

        # Prepara helper enxuto de captura no contexto da pagina para reduzir overhead JS
        avaliar_js(
            cdp,
            "window.__cv = document.getElementById('c');"
            + (
                "window.__snap = t => { window.renderAt(t); return window.__cv.toDataURL('image/png').slice(22); };"
                if args.png
                else "window.__snap = t => { window.renderAt(t); return window.__cv.toDataURL('image/jpeg', 0.96).slice(23); };"
            ),
        )

        cmd_ff = montar_comando_ffmpeg(saida, args.fps, audio_alvo, duracao, usar_png=args.png)
        ff = subprocess.Popen(cmd_ff, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert ff.stdin is not None

        for i in range(total_quadros):
            t = i / args.fps
            b64 = avaliar_js(cdp, f"window.__snap({t:.6f})")
            ff.stdin.write(base64.b64decode(b64))
            if (i + 1) % args.fps == 0 or i + 1 == total_quadros:
                decorrido = time.monotonic() - inicio
                pct = (i + 1) * 100.0 / total_quadros
                fps_real = (i + 1) / max(0.01, decorrido)
                print(
                    f"  {i + 1}/{total_quadros} quadros ({pct:5.1f}%) | {decorrido:.1f}s ({fps_real:.1f} q/s)",
                    flush=True,
                )

        ff.stdin.close()
        stderr_ff = ff.stderr.read().decode("utf-8", errors="replace") if ff.stderr else ""
        ret = ff.wait()
        if ret != 0:
            raise RuntimeError(f"ffmpeg falhou (codigo {ret}): {stderr_ff}")

        print(f"Concluido em {time.monotonic() - inicio:.1f}s: {saida} ({saida.stat().st_size / 1024:.1f} KB)")

        if (not args.teste) and (corte_parte_2 is not None) and (0.5 < corte_parte_2 < duracao - 0.5):
            saidas_partes = caminhos_partes_atual() if args.saida is None else None
            t_fat = time.monotonic()
            p1, p2 = fatiar_partes_ffmpeg(saida, corte_parte_2, saidas_partes=saidas_partes)
            d1 = duracao_audio_ffprobe(p1)
            d2 = duracao_audio_ffprobe(p2)
            print(
                f"Corte automatico Parte 1 / Parte 2 concluido em {time.monotonic() - t_fat:.1f}s "
                f"(corte={corte_parte_2:.3f}s):"
            )
            print(f"  Parte 1: {p1} ({d1:.2f}s, {p1.stat().st_size / 1024:.1f} KB)")
            print(f"  Parte 2: {p2} ({d2:.2f}s, {p2.stat().st_size / 1024:.1f} KB)")
    finally:
        if ff and ff.poll() is None:
            ff.kill()
            ff.wait()
        if cdp:
            cdp.fechar()
        if browser_proc and browser_proc.poll() is None:
            browser_proc.terminate()
            try:
                browser_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_proc.kill()
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(perfil_tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
