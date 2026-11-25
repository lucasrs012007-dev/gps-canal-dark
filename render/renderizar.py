"""Estacao 3 (Motor Hibrido V7): Storyboard por IA + movimento de camera FFmpeg em 1080x1920 @ 30fps.

Uso (na raiz do repositorio):
    python3 render/renderizar.py --legendas          # render completo (output/short_NN.mp4 + parte1 + parte2)
    python3 render/renderizar.py --legendas --teste  # render rapido de 2s para validacao
    python3 render/renderizar.py --legendas --dry-run-ffmpeg
    python3 render/renderizar.py --motor canvas      # motor HTML5 Canvas legado (opcional)

Recursos V7:
- Sincroniza cada imagem `output/cenas/cena_NN.jpg` com a duracao exata da cena no audio (`audio/eventos.json`).
- Aplica movimentos cinematograficos alternados com `zoompan` (zoom-in, zoom-out, pan horizontal e vertical),
  transicoes suaves (`xfade`), vinheta escura (`vignette`) e legendas ASS sincronizadas na area segura de Shorts/Reels.
- Exporta em Full HD vertical 1080x1920 (`-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30`),
  mantendo compatibilidade total com `upload_youtube.py`, `automacao/enviar_telegram.py` e corte Parte 1 / Parte 2.
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

    def guess_type(self, path):
        ctype = super().guess_type(path)
        if ctype in ("text/html", "application/json", "text/javascript", "application/javascript", "text/css"):
            return f"{ctype}; charset=utf-8"
        return ctype

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


CDP_TIMEOUT_PADRAO_S = 45.0
CDP_MAX_TENTATIVAS = 3
CDP_POLL_INTERVALO_S = 0.2


def _encerrar_processo_navegador(proc: subprocess.Popen | None) -> None:
    """Encerra o processo do Chromium com terminate -> wait -> kill para nao deixar orfaos."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
    except Exception:
        pass


def _ler_stderr_log(caminho: Path, max_chars: int = 2000) -> str:
    try:
        if not caminho.is_file():
            return ""
        texto = caminho.read_text(encoding="utf-8", errors="replace").strip()
        if len(texto) > max_chars:
            return "...[truncado]...\n" + texto[-max_chars:]
        return texto
    except Exception:
        return ""


def montar_cmd_chromium_cdp(navegador: str, porta_dbg: int, perfil_dir: str) -> list[str]:
    """Monta linha de comando estavel do Chromium/Chrome headless para Linux/GitHub Actions e local."""
    cmd = [
        navegador,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-extensions",
        "--hide-scrollbars",
        "--mute-audio",
        "--remote-debugging-address=127.0.0.1",
        f"--window-size={LARGURA},{ALTURA}",
        f"--remote-debugging-port={porta_dbg}",
        f"--user-data-dir={perfil_dir}",
        "about:blank",
    ]
    if os.name != "nt":
        cmd.insert(2, "--no-sandbox")
        cmd.insert(3, "--disable-setuid-sandbox")
        cmd.insert(4, "--disable-dev-shm-usage")
    return cmd


def abrir_cdp(
    navegador: str,
    porta_dbg: int,
    perfil_tmp: str,
    *,
    timeout_s: float = CDP_TIMEOUT_PADRAO_S,
    max_tentativas: int = CDP_MAX_TENTATIVAS,
    poll_intervalo_s: float = CDP_POLL_INTERVALO_S,
    popen_fn=None,
    opener_fn=None,
    porta_fn=None,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> tuple[subprocess.Popen, str]:
    """Abre o Chromium headless com timeout de 45s, ate 3 tentativas e log de stderr em caso de falha."""
    max_t = max(1, int(max_tentativas))
    timeout_real = max(1.0, float(timeout_s))
    iniciar_proc = popen_fn or subprocess.Popen
    obter_porta = porta_fn or porta_livre
    opener = opener_fn or urllib.request.build_opener(urllib.request.ProxyHandler({}))

    ultimo_erro = "Tempo esgotado aguardando a porta CDP do navegador."
    ultimo_stderr = ""

    for tentativa in range(1, max_t + 1):
        porta_atual = porta_dbg if tentativa == 1 else obter_porta()
        perfil_tentativa = Path(perfil_tmp) / f"tentativa_{tentativa}_{porta_atual}"
        shutil.rmtree(perfil_tentativa, ignore_errors=True)
        perfil_tentativa.mkdir(parents=True, exist_ok=True)
        stderr_log = perfil_tentativa / "chrome_stderr.log"

        cmd = montar_cmd_chromium_cdp(navegador, porta_atual, str(perfil_tentativa))
        proc: subprocess.Popen | None = None
        stderr_fp = stderr_log.open("wb")
        try:
            proc = iniciar_proc(cmd, stdout=subprocess.DEVNULL, stderr=stderr_fp)
        except Exception as exc:
            stderr_fp.close()
            shutil.rmtree(perfil_tentativa, ignore_errors=True)
            ultimo_erro = f"Falha ao iniciar o navegador ({type(exc).__name__}: {exc})."
            print(
                f"AVISO abrir_cdp tentativa {tentativa}/{max_t} falhou: {ultimo_erro}",
                flush=True,
            )
            if tentativa < max_t:
                sleep_fn(1.0)
            continue
        finally:
            try:
                stderr_fp.close()
            except Exception:
                pass

        url_lista = f"http://127.0.0.1:{porta_atual}/json/list"
        deadline = monotonic_fn() + timeout_real
        motivo_falha = f"Tempo esgotado ({timeout_real:.0f}s) aguardando a porta CDP {porta_atual} do navegador."
        encerrou_cedo = False

        while monotonic_fn() < deadline:
            ret_code = proc.poll()
            if ret_code is not None:
                motivo_falha = f"Navegador encerrou antes de abrir o CDP (codigo {ret_code})."
                encerrou_cedo = True
                break
            try:
                with opener.open(url_lista, timeout=1.5) as r:
                    alvos = [a for a in json.loads(r.read()) if a.get("type") == "page"]
                    if alvos and alvos[0].get("webSocketDebuggerUrl"):
                        if tentativa > 1:
                            print(
                                f"CDP conectado com sucesso na tentativa {tentativa}/{max_t} (porta {porta_atual}).",
                                flush=True,
                            )
                        return proc, alvos[0]["webSocketDebuggerUrl"]
            except Exception:
                pass
            if monotonic_fn() >= deadline:
                break
            sleep_fn(poll_intervalo_s)

        _encerrar_processo_navegador(proc)
        stderr_txt = _ler_stderr_log(stderr_log)
        ultimo_erro = motivo_falha
        ultimo_stderr = stderr_txt

        print(
            f"AVISO abrir_cdp tentativa {tentativa}/{max_t} falhou (porta {porta_atual}): {motivo_falha}",
            flush=True,
        )
        if stderr_txt:
            print(
                f"--- stderr do navegador (tentativa {tentativa}/{max_t}) ---\n"
                f"{stderr_txt}\n"
                f"--- fim stderr ---",
                flush=True,
            )
        else:
            print(
                f"(stderr do navegador vazio na tentativa {tentativa}/{max_t}; "
                f"encerrou_cedo={encerrou_cedo})",
                flush=True,
            )

        shutil.rmtree(perfil_tentativa, ignore_errors=True)
        if tentativa < max_t:
            sleep_fn(1.0)

    detalhe_stderr = f"\nstderr do navegador:\n{ultimo_stderr}" if ultimo_stderr else ""
    raise RuntimeError(f"{ultimo_erro} (apos {max_t} tentativa(s)).{detalhe_stderr}")


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
            "medium",
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


# ============================================================
# MOTOR HIBRIDO V7: STORYBOARD POR IA + MOVIMENTO DE CAMERA FFMPEG
# ============================================================

PASTA_CENAS_VISUAIS = RAIZ / "output" / "cenas"
ARQUIVO_CENAS_JSON = RAIZ / "cenas.json"
TRANSICAO_XFADE_PADRAO_S = 0.25
OVERSAMPLE_LARGURA = 1296
OVERSAMPLE_ALTURA = 2304
MOVIMENTOS_CAMERA: tuple[str, ...] = (
    "zoom_in",
    "pan_lr",
    "zoom_out",
    "pan_ud",
    "zoom_in",
    "pan_rl",
    "zoom_out",
    "pan_du",
)
MAPA_CAMERA_MOVIMENTO: dict[str, str] = {
    "push_in": "zoom_in",
    "tight_close": "zoom_in",
    "pull_out": "zoom_out",
    "pan_right": "pan_lr",
    "pan_left": "pan_rl",
    "wide_still": "pan_ud",
}


def _normalizar_chave_palavra(texto: str) -> str:
    import re
    import unicodedata

    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())


def _escapar_texto_ass(texto: str) -> str:
    return (
        str(texto or "")
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", " ")
        .strip()
    )


def _formatar_tempo_ass(segundos: float) -> str:
    s = max(0.0, float(segundos))
    horas = int(s // 3600)
    minutos = int((s % 3600) // 60)
    segs = int(s % 60)
    centesimos = int(round((s - int(s)) * 100))
    if centesimos >= 100:
        centesimos = 0
        segs += 1
        if segs >= 60:
            segs = 0
            minutos += 1
            if minutos >= 60:
                minutos = 0
                horas += 1
    return f"{horas}:{minutos:02d}:{segs:02d}.{centesimos:02d}"


def _escapar_caminho_filtro_ffmpeg(caminho: Path) -> str:
    txt = caminho.resolve().as_posix()
    return (
        txt.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def gerar_legenda_ass(
    timestamps_dados: dict,
    destino_ass: Path,
    *,
    duracao_max: float | None = None,
    palavras_vermelhas: list[str] | set[str] | None = None,
    fonte: str = "DejaVu Sans",
) -> Path | None:
    """Gera arquivo ASS 1080x1920 com legendas grandes, centralizadas e destaque palavra por palavra."""
    grupos = timestamps_dados.get("grupos") if isinstance(timestamps_dados, dict) else None
    if not isinstance(grupos, list) or not grupos:
        return None

    destaques_vermelhos = {
        _normalizar_chave_palavra(w) for w in (palavras_vermelhas or ()) if _normalizar_chave_palavra(w)
    }

    cabecalho = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {LARGURA}",
        f"PlayResY: {ALTURA}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Fonte limpa branca, contorno preto grosso (6px), sombra suave, centralizada dentro da area segura Shorts/Reels
        f"Style: Shorts,{fonte},74,&H00FFFFFF,&H0000D4FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,6,3,2,96,96,480,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    eventos_ass: list[str] = []
    for grp in grupos:
        if not isinstance(grp, dict):
            continue
        palavras = grp.get("palavras")
        if not isinstance(palavras, list) or not palavras:
            g_ini = float(grp.get("inicio", 0.0))
            g_fim = float(grp.get("fim", g_ini + 0.4))
            if duracao_max is not None:
                if g_ini >= duracao_max:
                    continue
                g_fim = min(g_fim, duracao_max)
            if g_fim - g_ini < 0.04:
                continue
            texto_grp = _escapar_texto_ass(str(grp.get("texto", "")).upper())
            if texto_grp:
                eventos_ass.append(
                    f"Dialogue: 0,{_formatar_tempo_ass(g_ini)},{_formatar_tempo_ass(g_fim)},Shorts,,0,0,0,,{texto_grp}"
                )
            continue

        for idx_p, pal in enumerate(palavras):
            t_ini = float(pal.get("inicio", grp.get("inicio", 0.0)))
            if idx_p + 1 < len(palavras):
                t_fim = float(palavras[idx_p + 1].get("inicio", pal.get("fim", t_ini + 0.15)))
            else:
                t_fim = float(pal.get("fim", grp.get("fim", t_ini + 0.18)))
            if duracao_max is not None:
                if t_ini >= duracao_max:
                    continue
                t_fim = min(t_fim, duracao_max)
            if t_fim <= t_ini + 0.02:
                t_fim = min(duracao_max if duracao_max is not None else t_ini + 0.08, t_ini + 0.08)
            if t_fim <= t_ini + 0.01:
                continue

            partes_txt: list[str] = []
            for j, item_w in enumerate(palavras):
                palavra_up = _escapar_texto_ass(str(item_w.get("palavra", "")).upper())
                if not palavra_up:
                    continue
                chave_w = _normalizar_chave_palavra(palavra_up)
                if j == idx_p:
                    if chave_w in destaques_vermelhos:
                        partes_txt.append(r"{\c&H00303BFF&\fscx108\fscy108}" + palavra_up + r"{\c&H00FFFFFF&\fscx100\fscy100}")
                    else:
                        partes_txt.append(r"{\c&H0000D4FF&\fscx106\fscy106}" + palavra_up + r"{\c&H00FFFFFF&\fscx100\fscy100}")
                else:
                    partes_txt.append(palavra_up)
            linha_txt = " ".join(partes_txt).strip()
            if linha_txt:
                eventos_ass.append(
                    f"Dialogue: 0,{_formatar_tempo_ass(t_ini)},{_formatar_tempo_ass(t_fim)},Shorts,,0,0,0,,{linha_txt}"
                )

    if not eventos_ass:
        return None

    destino_ass.parent.mkdir(parents=True, exist_ok=True)
    destino_ass.write_text("\n".join(cabecalho + eventos_ass) + "\n", encoding="utf-8")
    return destino_ass


def escolher_movimento_cena(camera_hint: str | None, idx: int, anterior: str | None) -> str:
    """Alterna zoom-in, zoom-out e pan horizontal/vertical evitando repetir o mesmo movimento em sequencia."""
    sugerido = MAPA_CAMERA_MOVIMENTO.get(str(camera_hint or "").strip().lower())
    if sugerido and sugerido != anterior:
        return sugerido
    for desloc in range(len(MOVIMENTOS_CAMERA)):
        cand = MOVIMENTOS_CAMERA[(idx + desloc) % len(MOVIMENTOS_CAMERA)]
        if cand != anterior:
            return cand
    return "zoom_in"


def expressao_zoompan_cena(movimento: str, total_frames: int, fps: int) -> str:
    """Constroi filtro zoompan suave com oversampling 1296x2304 -> 1080x1920."""
    n_frames = max(2, int(total_frames))
    denom = max(1, n_frames - 1)
    if movimento == "zoom_out":
        expr = f"z='1.12-0.12*(on/{denom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif movimento == "pan_lr":
        expr = f"z='1.12':x='(iw-iw/zoom)*(on/{denom})':y='ih/2-(ih/zoom/2)'"
    elif movimento == "pan_rl":
        expr = f"z='1.12':x='(iw-iw/zoom)*(1-on/{denom})':y='ih/2-(ih/zoom/2)'"
    elif movimento == "pan_ud":
        expr = f"z='1.12':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{denom})'"
    elif movimento == "pan_du":
        expr = f"z='1.12':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{denom})'"
    else:
        expr = f"z='1+0.12*(on/{denom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    return (
        f"scale={OVERSAMPLE_LARGURA}:{OVERSAMPLE_ALTURA}:force_original_aspect_ratio=increase,"
        f"crop={OVERSAMPLE_LARGURA}:{OVERSAMPLE_ALTURA},"
        f"zoompan={expr}:d={n_frames}:s={LARGURA}x{ALTURA}:fps={int(fps)}"
    )


def construir_timeline_cenas(
    cenas_dados: dict,
    eventos_dados: dict | None,
    duracao_total: float,
    pasta_cenas: Path = PASTA_CENAS_VISUAIS,
) -> list[dict]:
    """Sincroniza exatamente cada imagem output/cenas/cena_NN.jpg com a duracao do audio daquela cena."""
    lista = cenas_dados.get("cenas") if isinstance(cenas_dados, dict) else None
    if not isinstance(lista, list) or not lista:
        raise RuntimeError("cenas.json nao possui lista valida em 'cenas'.")

    ev = eventos_dados if isinstance(eventos_dados, dict) else {}
    dur = max(0.5, float(duracao_total))
    n = len(lista)

    inicios: list[float] = []
    for idx, c in enumerate(lista):
        chave = str(c.get("evento_inicio") or c.get("id") or f"cena_{idx + 1:02d}")
        val = ev.get(chave)
        if isinstance(val, (int, float)) and val >= 0.0:
            inicios.append(float(val))
        else:
            dur_ref = max(dur, float(ev.get("duracao_total") or dur))
            inicios.append((idx / n) * dur_ref)

    inicios[0] = 0.0
    for i in range(1, n):
        if inicios[i] <= inicios[i - 1] + 0.25:
            inicios[i] = inicios[i - 1] + 0.45

    imagens_disponiveis = sorted(pasta_cenas.glob("cena_*.jpg"))
    if not imagens_disponiveis:
        raise FileNotFoundError(
            f"Nenhuma imagem cena_*.jpg encontrada em {pasta_cenas}. Rode python3 gerar_cenas_visuais.py primeiro."
        )

    timeline: list[dict] = []
    mov_anterior: str | None = None

    for idx, c in enumerate(lista):
        t_ini = inicios[idx]
        if t_ini >= dur - 0.15:
            break
        t_fim = inicios[idx + 1] if idx + 1 < n else dur
        t_fim = min(dur, max(t_ini + 0.15, t_fim))
        dur_cena = round(t_fim - t_ini, 4)
        if dur_cena < 0.10:
            continue

        img_esperada = pasta_cenas / f"cena_{idx + 1:02d}.jpg"
        if img_esperada.is_file() and img_esperada.stat().st_size > 0:
            img_path = img_esperada
        else:
            img_path = imagens_disponiveis[idx % len(imagens_disponiveis)]

        mov = escolher_movimento_cena(c.get("camera"), idx, mov_anterior)
        mov_anterior = mov
        timeline.append(
            {
                "indice": idx + 1,
                "id": str(c.get("id") or f"cena_{idx + 1:02d}"),
                "imagem": img_path,
                "inicio": round(t_ini, 4),
                "fim": round(t_fim, 4),
                "duracao": dur_cena,
                "movimento": mov,
                "mood": str(c.get("mood", "navy")),
            }
        )

    if not timeline:
        raise RuntimeError("Timeline de cenas vazia apos sincronizacao com a duracao do audio.")

    # Garante fechamento exato na duracao total do video
    timeline[-1]["fim"] = round(dur, 4)
    timeline[-1]["duracao"] = round(max(0.15, dur - timeline[-1]["inicio"]), 4)
    return timeline


def montar_comando_ffmpeg_storyboard(
    timeline: list[dict],
    saida: Path,
    fps: int,
    audio_alvo: Path | None,
    duracao: float,
    *,
    arquivo_ass: Path | None = None,
    transicao_s: float = TRANSICAO_XFADE_PADRAO_S,
) -> list[str]:
    """Monta comando FFmpeg 1080x1920: zoompan dinamico + xfade + vinheta escura + legendas ASS + H.264 CRF 18."""
    if not timeline:
        raise ValueError("Timeline de cenas vazia.")

    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for item in timeline:
        cmd.extend(["-i", str(item["imagem"])])

    audio_input_idx = len(timeline)
    if audio_alvo is not None:
        cmd.extend(["-i", str(audio_alvo)])
    else:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]
        )

    n = len(timeline)
    transicoes: list[float] = []
    for i in range(n - 1):
        d_atual = float(timeline[i]["duracao"])
        d_prox = float(timeline[i + 1]["duracao"])
        if transicao_s > 0.0 and min(d_atual, d_prox) >= max(0.85, transicao_s * 2.5):
            transicoes.append(round(transicao_s, 3))
        else:
            transicoes.append(0.0)

    partes_fc: list[str] = []
    for i, item in enumerate(timeline):
        sobreposicao = transicoes[i] if i < n - 1 else 0.0
        dur_clip = float(item["duracao"]) + sobreposicao
        total_frames = max(2, int(round(dur_clip * fps)) + 1)
        zp = expressao_zoompan_cena(item["movimento"], total_frames=total_frames, fps=fps)
        partes_fc.append(
            f"[{i}:v]{zp},format=yuv420p,setsar=1,settb=AVTB,"
            f"trim=duration={dur_clip:.4f},setpts=PTS-STARTPTS[v{i}]"
        )

    label_atual = "v0"
    tempo_acum = float(timeline[0]["duracao"])
    for i in range(1, n):
        t_xf = transicoes[i - 1]
        prox_label = f"xf{i}"
        if t_xf > 0.0:
            tipo_xf = "fadeblack" if (i == n - 1 and n >= 3) else "fade"
            partes_fc.append(
                f"[{label_atual}][v{i}]xfade=transition={tipo_xf}:duration={t_xf:.3f}:offset={tempo_acum:.4f}[{prox_label}]"
            )
        else:
            partes_fc.append(f"[{label_atual}][v{i}]concat=n=2:v=1:a=0[{prox_label}]")
        label_atual = prox_label
        tempo_acum += float(timeline[i]["duracao"])

    pos_filtros = ["vignette=PI/4.4"]
    if arquivo_ass is not None and arquivo_ass.is_file():
        ass_esc = _escapar_caminho_filtro_ffmpeg(arquivo_ass)
        pos_filtros.append(f"ass=filename='{ass_esc}'")
    partes_fc.append(f"[{label_atual}]{','.join(pos_filtros)}[vout]")

    filter_complex = ";".join(partes_fc)
    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", f"{audio_input_idx}:a:0"])
    if audio_alvo is not None:
        cmd.extend(["-af", "apad"])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(int(fps)),
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
    """Fatia o MP4 completo em Parte 1 (0..corte) e Parte 2 (corte..fim) com precisao de quadro."""
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
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
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


def _garantir_imagens_storyboard(
    cenas_path: Path,
    pasta_cenas: Path,
    *,
    usar_mock: bool = False,
    max_cenas: int | None = None,
) -> None:
    """Gera automaticamente output/cenas/cena_NN.jpg se ainda nao estiverem presentes."""
    cenas_dados = json.loads(cenas_path.read_text(encoding="utf-8"))
    total_esperado = len(cenas_dados.get("cenas") or [])
    if max_cenas is not None and max_cenas > 0:
        total_esperado = min(total_esperado, int(max_cenas))
    existentes = [
        pasta_cenas / f"cena_{i:02d}.jpg"
        for i in range(1, total_esperado + 1)
        if (pasta_cenas / f"cena_{i:02d}.jpg").is_file()
        and (pasta_cenas / f"cena_{i:02d}.jpg").stat().st_size > 20 * 1024
    ]
    if total_esperado > 0 and len(existentes) >= total_esperado:
        return

    from gerar_cenas_visuais import gerar_todas_cenas_visuais

    gerar_todas_cenas_visuais(
        cenas_path=cenas_path,
        saida_dir=pasta_cenas,
        usar_mock=usar_mock,
        max_cenas=max_cenas,
    )


def renderizar_storyboard_ffmpeg(
    args: argparse.Namespace,
    video_ativo: dict,
    saida: Path,
    audio_alvo: Path | None,
    cta_modo: str,
    corte_parte_2: float | None,
    eventos_dados: dict,
    timestamps_dados: dict,
) -> None:
    """Executa o Motor Hibrido de Storyboard por IA + FFmpeg (1080x1920 @ 30fps)."""
    cenas_path = args.cenas if args.cenas.is_absolute() else (RAIZ / args.cenas)
    pasta_cenas = args.pasta_cenas if args.pasta_cenas.is_absolute() else (RAIZ / args.pasta_cenas)

    if not cenas_path.is_file():
        raise SystemExit(
            f"Arquivo cenas.json nao encontrado ({cenas_path}). Rode a Estacao 1 ou use --motor canvas."
        )

    cenas_dados = json.loads(cenas_path.read_text(encoding="utf-8"))
    if audio_alvo is not None:
        folga = 0.05 if cta_modo in ("meio", "pausa_meio") else FOLGA_AUDIO
        duracao_real = duracao_audio_ffprobe(audio_alvo) + folga
        modo_audio = f"com audio ({audio_alvo.name}, {duracao_real:.2f}s incluindo folga de {folga}s)"
    else:
        duracao_real = float(eventos_dados.get("duracao_total") or 36.0)
        modo_audio = f"mudo / Modo Previa ({duracao_real:.1f}s)"

    duracao = min(2.0, duracao_real) if args.teste else duracao_real

    _garantir_imagens_storyboard(
        cenas_path=cenas_path,
        pasta_cenas=pasta_cenas,
        usar_mock=bool(args.mock_cenas),
        max_cenas=2 if args.teste else None,
    )

    timeline = construir_timeline_cenas(
        cenas_dados=cenas_dados,
        eventos_dados=eventos_dados,
        duracao_total=duracao,
        pasta_cenas=pasta_cenas,
    )

    print(
        f"Estacao 3 (Motor Hibrido Storyboard IA + FFmpeg): Video {int(video_ativo['id']):02d} "
        f"'{video_ativo['titulo']}' -> "
        f"{saida.relative_to(RAIZ).as_posix() if saida.is_relative_to(RAIZ) else saida}",
        flush=True,
    )
    print(
        f"  Modo: {modo_audio}{' [TESTE 2s]' if args.teste else ''} | "
        f"Cenas={len(timeline)} | 1080x1920 @ {args.fps}fps | libx264 preset=medium crf=18",
        flush=True,
    )
    for item in timeline:
        print(
            f"  - {item['id']}: {item['imagem'].name} [{item['inicio']:.2f}s..{item['fim']:.2f}s, "
            f"dur={item['duracao']:.2f}s, camera={item['movimento']}]",
            flush=True,
        )

    inicio = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="render-storyboard-") as tmp:
        tmp_dir = Path(tmp)
        arquivo_ass: Path | None = None
        if args.legendas and timestamps_dados:
            palavras_verm = cenas_dados.get("palavras_vermelhas") or []
            arquivo_ass = gerar_legenda_ass(
                timestamps_dados=timestamps_dados,
                destino_ass=tmp_dir / "legendas.ass",
                duracao_max=duracao,
                palavras_vermelhas=palavras_verm,
            )
            if arquivo_ass is not None:
                print(f"  Legendas ASS sincronizadas: {arquivo_ass.name} (area segura Shorts/Reels)", flush=True)

        cmd_ff = montar_comando_ffmpeg_storyboard(
            timeline=timeline,
            saida=saida,
            fps=args.fps,
            audio_alvo=audio_alvo,
            duracao=duracao,
            arquivo_ass=arquivo_ass,
        )

        if args.dry_run_ffmpeg:
            print("[DRY-RUN FFMPEG] Comando gerado:")
            print(" ".join(cmd_ff))
            return

        res = subprocess.run(cmd_ff, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg storyboard falhou (codigo {res.returncode}): {res.stderr.strip()}")

    print(
        f"Concluido em {time.monotonic() - inicio:.1f}s: {saida} ({saida.stat().st_size / 1024:.1f} KB)",
        flush=True,
    )

    if (not args.teste) and (corte_parte_2 is not None) and (0.5 < corte_parte_2 < duracao - 0.5):
        saidas_partes = caminhos_partes_atual() if args.saida is None else None
        t_fat = time.monotonic()
        p1, p2 = fatiar_partes_ffmpeg(saida, corte_parte_2, saidas_partes=saidas_partes)
        d1 = duracao_audio_ffprobe(p1)
        d2 = duracao_audio_ffprobe(p2)
        print(
            f"Corte automatico Parte 1 / Parte 2 concluido em {time.monotonic() - t_fat:.1f}s "
            f"(corte={corte_parte_2:.3f}s):",
            flush=True,
        )
        print(f"  Parte 1: {p1} ({d1:.2f}s, {p1.stat().st_size / 1024:.1f} KB)", flush=True)
        print(f"  Parte 2: {p2} ({d2:.2f}s, {p2.stat().st_size / 1024:.1f} KB)", flush=True)


def renderizar_canvas_legado(
    args: argparse.Namespace,
    video_ativo: dict,
    saida: Path,
    audio_alvo: Path | None,
    cta_modo: str,
    corte_parte_2: float | None,
) -> None:
    """Motor legado em HTML5 Canvas via Chromium CDP (mantido apenas via --motor canvas)."""
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

    navegador = encontrar_navegador(args.navegador)
    print(
        f"Historico validado (Motor Canvas Legado): Video {int(video_ativo['id']):02d} "
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
        _encerrar_processo_navegador(browser_proc)
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(perfil_tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estacao 3: renderiza Short 9:16 (1080x1920 @ 30fps) via Storyboard IA + FFmpeg."
    )
    parser.add_argument(
        "--motor",
        choices=("storyboard", "canvas"),
        default="storyboard",
        help="Motor de renderizacao (padrao: 'storyboard' IA + FFmpeg zoompan; 'canvas' para player HTML legado).",
    )
    parser.add_argument("--teste", action="store_true", help="Renderiza apenas os 2 primeiros segundos.")
    parser.add_argument("--fps", type=int, default=30, help="Quadros por segundo (padrao: 30).")
    parser.add_argument(
        "--saida",
        "-o",
        type=Path,
        default=None,
        help="Arquivo MP4 de saida (padrao: output/short_NN.mp4 conforme historico_videos.json).",
    )
    parser.add_argument("--legendas", action="store_true", help="Ativa legendas sincronizadas grandes e centralizadas.")
    parser.add_argument("--cenas", type=Path, default=ARQUIVO_CENAS_JSON, help="Caminho de cenas.json.")
    parser.add_argument(
        "--pasta-cenas",
        type=Path,
        default=PASTA_CENAS_VISUAIS,
        help="Pasta das imagens cena_NN.jpg (padrao: output/cenas).",
    )
    parser.add_argument("--mock-cenas", action="store_true", help="Usa geracao local de imagens ao testar sem rede.")
    parser.add_argument(
        "--dry-run-ffmpeg",
        action="store_true",
        help="Apenas imprime o comando FFmpeg montado sem executar a renderizacao.",
    )
    parser.add_argument("--png", action="store_true", help="Apenas --motor canvas: usa PNG lossless no pipe.")
    parser.add_argument("--navegador", type=str, default=None, help="Apenas --motor canvas: caminho do Chrome/Chromium.")
    parser.add_argument("--player", type=str, default=None, help="Apenas --motor canvas: arquivo HTML do player.")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    video_ativo = obter_video_atual(validar=True)
    audio_alvo = selecionar_audio()
    ts_path = PASTA_AUDIO / "timestamps.json"
    ev_path = PASTA_AUDIO / "eventos.json"
    tem_artefato_json = ts_path.is_file() or ev_path.is_file()

    cta_modo = str(video_ativo.get("cta_modo", "final")).strip().lower() or "final"
    corte_parte_2: float | None = None
    eventos_dados: dict = {}
    timestamps_dados: dict = {}

    if audio_alvo is not None or tem_artefato_json:
        val = validar_artefatos_audio(PASTA_AUDIO)
        c = val["carimbo"]
        cta_modo = c["cta_modo"]
        eventos_dados = val["eventos"]
        timestamps_dados = val["timestamps"]
        ev_corte = eventos_dados.get("corte_parte_2")
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

    if args.motor == "canvas":
        renderizar_canvas_legado(
            args=args,
            video_ativo=video_ativo,
            saida=saida,
            audio_alvo=audio_alvo,
            cta_modo=cta_modo,
            corte_parte_2=corte_parte_2,
        )
        return

    renderizar_storyboard_ffmpeg(
        args=args,
        video_ativo=video_ativo,
        saida=saida,
        audio_alvo=audio_alvo,
        cta_modo=cta_modo,
        corte_parte_2=corte_parte_2,
        eventos_dados=eventos_dados,
        timestamps_dados=timestamps_dados,
    )


if __name__ == "__main__":
    main()
