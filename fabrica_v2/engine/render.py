#!/usr/bin/env python3
"""Renderizador headless do showcase sandbox_opus.

Serve sandbox_opus/ num HTTP local efemero, abre Chrome headless via CDP (mesmas flags
comprovadas em render/renderizar.py, usado aqui apenas como referencia), chama
window.renderAt(i/30) quadro a quadro e envia JPEGs para o FFmpeg, que muxa
sandbox_opus/mix_final.wav (gerado por gerar_audio.py).

Uso:
  python3 sandbox_opus/render.py                       # video completo -> opus_showcase.mp4
  python3 sandbox_opus/render.py --stills 0.5,8,20     # PNGs de inspecao em /tmp/opus_check
  python3 sandbox_opus/render.py --auditoria           # maior intervalo sem mudanca visual
  python3 sandbox_opus/render.py --inicio 9 --fim 14 --saida /tmp/rascunho.mp4
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

ENGINE_DIR = Path(__file__).resolve().parent
EP_PADRAO = ENGINE_DIR.parent / "episodios" / "ep01_velocidade"
LARGURA, ALTURA, FPS = 1080, 1920, 30


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _criar_handler(engine_dir: Path, ep_dir: Path):
    class _FabricaHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def translate_path(self, path: str) -> str:
            limpo = path.split("?", 1)[0].split("#", 1)[0]
            if limpo == "/ep" or limpo.startswith("/ep/"):
                rel = limpo[4:].lstrip("/")
                return str((ep_dir / rel).resolve())
            rel = limpo.lstrip("/")
            return str((engine_dir / rel).resolve())

    return _FabricaHandler


def iniciar_http(ep_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    porta = porta_livre()
    handler = _criar_handler(ENGINE_DIR, ep_dir)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, porta


def achar_chrome() -> str:
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(nome)
        if p:
            return p
    raise SystemExit("Chrome/Chromium nao encontrado no PATH.")


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, max_size=None, timeout=120, suppress_origin=True)
        self.n = 0

    def call(self, metodo: str, params: dict | None = None) -> dict:
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": metodo, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str, aguardar: bool = False):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": aguardar})
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS falhou: {r['exceptionDetails'].get('exception', {}).get('description') or r['exceptionDetails']}")
        return r.get("result", {}).get("value")


def abrir_chrome(perfil: str) -> tuple[subprocess.Popen, str]:
    porta = porta_livre()
    cmd = [achar_chrome(), "--headless=new", "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
           "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
           "--disable-extensions", "--hide-scrollbars", "--mute-audio", "--remote-debugging-address=127.0.0.1",
           f"--window-size={LARGURA},{ALTURA}", f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}", "about:blank"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    fim = time.monotonic() + 45
    while time.monotonic() < fim:
        try:
            with opener.open(f"http://127.0.0.1:{porta}/json/list", timeout=1.5) as r:
                alvos = [a for a in json.loads(r.read()) if a.get("type") == "page"]
                if alvos:
                    return proc, alvos[0]["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.2)
    proc.kill()
    raise SystemExit("Chrome nao abriu a porta CDP em 45s.")


def preparar(cdp: CDP, porta_http: int) -> float:
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    cdp.call("Emulation.setDeviceMetricsOverride", {"width": LARGURA, "height": ALTURA, "deviceScaleFactor": 1, "mobile": False})
    cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{porta_http}/player.html?ep=/ep"})
    for _ in range(300):
        time.sleep(0.1)
        try:
            if cdp.js("window.__ready === true"):
                break
            erro = cdp.js("window.__erro || null")
            if erro:
                raise SystemExit(f"Player falhou: {erro}")
        except RuntimeError:
            continue
    else:
        raise SystemExit("player.html nao ficou pronto.")
    dims = cdp.js("[document.getElementById('c').width, document.getElementById('c').height]")
    if dims != [LARGURA, ALTURA]:
        raise SystemExit(f"Canvas com tamanho inesperado: {dims}")
    fontes = cdp.js("document.fonts.check('92px \"Luckiest Guy\"') && document.fonts.check('76px \"Anton\"')")
    print(f"Player pronto | fontes Anton + Luckiest Guy carregadas: {fontes}", flush=True)
    cdp.js("window.__cv = document.getElementById('c');"
           "window.__snap = (t, q) => { window.renderAt(t); return q ? window.__cv.toDataURL('image/jpeg', q).slice(23) : window.__cv.toDataURL('image/png').slice(22); };")
    return float(cdp.js("window.getDuration()"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", default=str(EP_PADRAO), help="diretorio do episodio (padrao: fabrica_v2/episodios/ep01_velocidade)")
    ap.add_argument("--saida", default="", help="caminho do MP4 de saida (padrao: <ep>/video_final.mp4)")
    ap.add_argument("--stills", default="", help="lista de tempos (s) separados por virgula")
    ap.add_argument("--dir-stills", default="/tmp/fabrica_v2_check")
    ap.add_argument("--auditoria", action="store_true")
    ap.add_argument("--inicio", type=float, default=0.0)
    ap.add_argument("--fim", type=float, default=None)
    ap.add_argument("--qualidade-jpeg", type=float, default=0.95)
    args = ap.parse_args()

    ep_dir = Path(args.ep).resolve()
    saida = Path(args.saida).resolve() if args.saida else (ep_dir / "video_final.mp4")
    audio = ep_dir / "mix_final.wav"
    if not (ep_dir / "scenes.js").exists():
        raise SystemExit(f"Arquivo nao encontrado: {ep_dir / 'scenes.js'}")
    if not (ep_dir / "timestamps.json").exists() or not audio.exists():
        raise SystemExit(f"Rode antes: python3 fabrica_v2/engine/gerar_audio.py --ep {args.ep}")

    srv, porta_http = iniciar_http(ep_dir)
    perfil = tempfile.mkdtemp(prefix="fabrica_v2_chrome_")
    proc = None
    try:
        proc, ws_url = abrir_chrome(perfil)
        cdp = CDP(ws_url)
        dur = preparar(cdp, porta_http)
        print(f"Episodio: {ep_dir.name} | Duracao do roteiro: {dur:.3f}s", flush=True)

        if args.auditoria:
            ev = cdp.js("window.getVisualEvents()")
            gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
            gaps.append((dur - ev[-1], ev[-1]))
            maior = max(gaps)
            print(f"Eventos visuais: {len(ev)} | maior intervalo sem mudanca: {maior[0]:.2f}s (a partir de {maior[1]:.2f}s)")
            for g, a in sorted(gaps, reverse=True)[:5]:
                print(f"  {g:.2f}s em {a:.2f}s")
            return

        if args.stills:
            out = Path(args.dir_stills)
            out.mkdir(parents=True, exist_ok=True)
            for tx in [float(x) for x in args.stills.split(",") if x.strip()]:
                b64 = cdp.js(f"window.__snap({tx:.4f}, 0)")
                p = out / f"check_{tx:06.2f}.png"
                p.write_bytes(base64.b64decode(b64))
                cena = cdp.js(f"window.getSceneAt({tx})")
                print(f"still {tx:.2f}s ({cena}) -> {p}", flush=True)
            return

        fim = min(dur, args.fim) if args.fim else dur
        q0, q1 = int(round(args.inicio * FPS)), int(round(fim * FPS))
        n = q1 - q0
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS), "-i", "-",
               "-ss", f"{q0 / FPS:.4f}", "-t", f"{n / FPS:.4f}", "-i", str(audio),
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-crf", "22", "-preset", "medium", "-tune", "animation", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-movflags", "+faststart", "-shortest", str(saida)]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.monotonic()
        for i in range(q0, q1):
            b64 = cdp.js(f"window.__snap({i / FPS:.6f}, {args.qualidade_jpeg})")
            ff.stdin.write(base64.b64decode(b64))
            k = i - q0 + 1
            if k % 60 == 0 or k == n:
                el = time.monotonic() - t0
                print(f"  {k}/{n} quadros ({100 * k / n:5.1f}%) | {el:.0f}s | {k / max(el, 1e-3):.1f} q/s", flush=True)
        ff.stdin.close()
        if ff.wait() != 0:
            raise SystemExit("FFmpeg falhou.")
        print(f"OK: {saida} ({saida.stat().st_size / 1e6:.2f} MB) em {time.monotonic() - t0:.0f}s")
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        srv.shutdown()
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
