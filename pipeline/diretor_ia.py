"""Estacao 1 (Motor V6.0): Diretor IA que cria ou adapta um roteiro em producao completa.

Aceita texto livre (`--roteiro-texto`, `--arquivo`) OU geracao 100% autonoma (`--gerar-inedito`),
gerando automaticamente:
1. Novo registro inedito em `historico_videos.json` (motor="v6", player="player_universal.html",
   cta_modo="pausa_meio", parte_label="PARTE 1" e saidas_partes quando > 130 palavras).
2. `roteiro_XX.txt` pronto para o pipeline V5.2 (tags [VOZ:perfil], [SFX:...], [CTA_PAUSA]
   e [CORTE_PARTE_2] automatico acima de 130 palavras).
3. `cenas.json` (schema versionado "6.0", validado e auto-corrigido em Python) guiando os
   9 modulos visuais do `player_universal.html`, paleta, protagonista, relogio e 3 a 5 hits Katana.

Uso (na raiz do repositorio):
    python3 pipeline/diretor_ia.py --gerar-inedito --exigir-gemini
    python3 pipeline/diretor_ia.py --roteiro-texto "Era 02:47 quando..." --titulo "A Ligacao"
    python3 pipeline/diretor_ia.py --arquivo entrada.txt
    python3 pipeline/diretor_ia.py --gerar-inedito --mock
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.historico import (  # noqa: E402
    ARQUIVO_HISTORICO,
    _similares,
    carregar_historico,
    normalizar_texto,
    proximo_numero_livre,
    tokens_tema,
    validar_historico,
)

SCHEMA_VERSION = "6.0"
GEMINI_MODELO_PADRAO = "gemini-3.5-flash-lite"
GEMINI_MODELOS_FALLBACK: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-4-hydrogen",
)
ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_CATALOGO_SFX = RAIZ / "assets" / "sfx" / "catalogo.json"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
CTA_FALA_PADRAO = "Quer aprender a fazer vídeos assim no automático? Comente EU QUERO."
LIMITE_PALAVRAS_PARTE_2 = 130

MODULOS_CENARIO: tuple[str, ...] = (
    "quarto_noturno",
    "corredor_escuro",
    "celular_notificacao",
    "camera_cctv",
    "elevador_cabine",
    "carro_noite",
    "sala_cozinha",
    "big_face",
    "blecaute_olhos",
)

PERFIS_VOZ: tuple[str, ...] = (
    "narrador_tenso",
    "panico",
    "interfone_porteiro",
    "voz_telefone",
    "cta_comercial",
    "sussurro_twist",
)

MOODS_VALIDOS: tuple[str, ...] = ("navy", "violet", "red", "yellow", "cctv", "dark")
EXPRESSOES_VALIDAS: tuple[str, ...] = ("neutral", "worry", "fear", "shock", "sinister_smile")
CAMERAS_VALIDAS: tuple[str, ...] = (
    "push_in",
    "pull_out",
    "pan_left",
    "pan_right",
    "tight_close",
    "wide_still",
)

PALETA_JAQUETAS: tuple[tuple[str, str, str], ...] = (
    ("#0F766E", "#0B534D", "#06312E"),
    ("#1D4ED8", "#1E40AF", "#172554"),
    ("#9A3412", "#7C2D12", "#431407"),
    ("#4338CA", "#3730A3", "#1E1B4B"),
    ("#3F6212", "#365314", "#1A2E05"),
    ("#9F1239", "#881337", "#4C0519"),
)

PALETA_PADRAO = {
    "bg_navy": "#0A0F1D",
    "bg_violet": "#130926",
    "bg_red": "#3B0A0A",
    "accent": "#38D9FF",
    "alert": "#FF3B30",
    "yellow": "#FFD400",
}

CTA_PADRAO = {
    "eyebrow": "PAUSA RÁPIDA NA HISTÓRIA",
    "titulo_linha_1": "QUER FAZER VÍDEOS ASSIM",
    "titulo_linha_2": "NO AUTOMÁTICO?",
    "botao": "COMENTE EU QUERO",
    "subtitulo": "EU TE ENVIO TUDO NO DIRECT",
    "rodape": "A HISTÓRIA CONTINUA EM INSTANTES",
}

STOPWORDS_PT = {
    "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no",
    "nas", "nos", "um", "uma", "uns", "umas", "para", "pra", "pro", "por", "com",
    "sem", "que", "se", "ao", "aos", "mas", "ou", "ele", "ela", "eles", "elas",
    "seu", "sua", "seus", "suas", "meu", "minha", "voce", "nao", "mais", "muito",
    "como", "quando", "onde", "porque", "entao", "depois", "antes", "sobre",
    "entre", "ate", "isso", "isto", "aquilo", "essa", "esse", "esta", "este",
    "era", "foi", "esta", "estava", "tinha", "tem", "ter", "vai", "foi", "sao",
    "so", "ja", "ainda", "aqui", "ali", "la", "bem", "tudo", "nada", "quem",
}

NOMES_COMUNS_EXCLUIR = {
    "era", "uma", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "mas", "quando", "entao", "depois", "antes",
    "ele", "ela", "ninguem", "alguem", "nada", "tudo", "agora", "hoje", "ontem",
    "noite", "madrugada", "celular", "porta", "quarto", "corredor", "elevador",
    "camera", "carro", "sala", "cozinha", "espelho", "janela", "interfone",
    "subsolo", "predio", "garagem", "rua", "estrada", "gps", "sinal", "som",
    "luz", "voz", "tela", "foto", "audio", "video", "mensagem", "ligacao",
    "parte", "horas", "minutos", "segundos", "alerta", "aviso", "socorro",
}

RE_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)
RE_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RE_HORARIO = re.compile(r"\b([01]?\d|2[0-3])\s*[:hH]\s*([0-5]\d)\b")
RE_SEPARAR_FRASES = re.compile(r"(?<=[.!?])\s+|\n+")


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


def carregar_catalogo_sfx(caminho: Path = ARQUIVO_CATALOGO_SFX) -> dict[str, float]:
    """Retorna {nome_sfx: duracao_alvo_s} a partir de assets/sfx/catalogo.json."""
    padrao = {
        "sub_boom": 1.4,
        "whoosh": 0.85,
        "riser": 2.2,
        "heartbeat": 2.0,
        "sussurro": 1.2,
        "passos_corredor": 1.3,
        "porta_impacto": 0.9,
        "glitch_tv": 0.55,
        "impacto_twist": 1.4,
        "guarda_roupa": 1.6,
        "interfone": 1.2,
        "porta_elevador": 1.1,
        "tranco_elevador": 1.2,
        "alarme_interfone": 1.1,
        "glitch_cta": 0.38,
        "cta_pop": 0.22,
        "motor_acelerando": 1.1,
        "trava_porta_carro": 1.1,
        "celular_tocando": 1.2,
    }
    if not caminho.is_file():
        return padrao
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        efeitos = dados.get("efeitos") or []
        mapa: dict[str, float] = {}
        for ef in efeitos:
            nome = str(ef.get("nome", "")).strip().lower()
            dur = float(ef.get("duracao_alvo_s", 1.1) or 1.1)
            if nome:
                mapa[nome] = round(max(0.25, min(2.4, dur)), 2)
        return mapa or padrao
    except (OSError, ValueError, json.JSONDecodeError):
        return padrao


def sanitizar_texto(texto: str) -> str:
    """Remove emojis, travessoes (em/en-dash) e marcadores residuais do texto."""
    limpo = str(texto or "")
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = limpo.replace("|", " ")
    limpo = re.sub(r"\[\s*/?\s*(?:VOZ|SFX|CTA_PAUSA|CORTE_PARTE_2)[^\]]*\]", " ", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"[ \t]+", " ", limpo)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo)
    return limpo.strip()


def gerar_slug(titulo: str, fallback: str = "historia-dark") -> str:
    base = normalizar_texto(titulo)
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug[:60] or fallback


def _validar_hex(cor: str | None, fallback: str) -> str:
    if isinstance(cor, str) and RE_HEX.fullmatch(cor.strip()):
        return cor.strip().upper()
    return fallback


def _escurecer_hex(cor_hex: str, fator: float) -> str:
    cor = _validar_hex(cor_hex, "#0F766E").lstrip("#")
    r = max(0, min(255, int(int(cor[0:2], 16) * fator)))
    g = max(0, min(255, int(int(cor[2:4], 16) * fator)))
    b = max(0, min(255, int(int(cor[4:6], 16) * fator)))
    return f"#{r:02X}{g:02X}{b:02X}"


def extrair_horario(texto: str) -> str:
    m = RE_HORARIO.search(texto)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"
    norm = normalizar_texto(texto)
    pares_extenso = [
        (r"\btres da manha\b", "03:00"),
        (r"\bduas da manha\b", "02:00"),
        (r"\buma da manha\b", "01:00"),
        (r"\bmeia noite\b", "00:00"),
        (r"\bquatro da manha\b", "04:00"),
    ]
    for pad, hora in pares_extenso:
        if re.search(pad, norm):
            return hora
    return "02:47"


def extrair_nome_protagonista(texto: str) -> str:
    for m in re.finditer(r"(?<!^)(?<![.!?]\s)\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,14})\b", texto):
        cand = m.group(1)
        if normalizar_texto(cand) not in NOMES_COMUNS_EXCLUIR:
            return cand
    for m in re.finditer(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,14})\b", texto):
        cand = m.group(1)
        if normalizar_texto(cand) not in NOMES_COMUNS_EXCLUIR:
            return cand
    return "Protagonista"


def inferir_modulo_por_texto(texto: str, idx: int, total: int) -> str:
    """Seleciona um dos 9 modulos visuais do player_universal.html conforme pistas do texto."""
    norm = normalizar_texto(texto)
    if idx == total - 1 and total >= 3:
        if any(k in norm for k in ("olho", "olhos", "escuro", "blecaute", "apagou", "apaga", "sombra", "sorri", "atras")):
            return "blecaute_olhos"
        return "blecaute_olhos" if idx % 2 == 1 else "big_face"
    if idx == total - 2 and total >= 4:
        if any(k in norm for k in ("choque", "gelou", "congelou", "grito", "arrepio", "panico", "coracao", "rosto", "pavor")):
            return "big_face"

    regras: list[tuple[str, tuple[str, ...]]] = [
        ("celular_notificacao", ("celular", "mensagem", "notificacao", "whatsapp", "tela", "ligacao", "chamada", "audio", "foto", "sms", "vibra", "vibrou", "toca", "tocou")),
        ("camera_cctv", ("camera", "cctv", "monitor", "gravacao", "gravando", "lente", "baba eletronica", "portaria", "vigilancia", "filmando")),
        ("elevador_cabine", ("elevador", "subsolo", "andar", "botoeira", "espelho", "cabine", "terreo")),
        ("carro_noite", ("carro", "estrada", "rodovia", "gps", "farol", "volante", "motorista", "retrovisor", "asfalto", "pista", "freio")),
        ("corredor_escuro", ("corredor", "escada", "cadeira", "passos", "hall", "porta", "macaneta", "fechadura", "batida", "batendo")),
        ("quarto_noturno", ("quarto", "cama", "travesseiro", "cobertor", "guarda roupa", "armario", "acorda", "acordou", "dormindo", "janela", "cortina")),
        ("sala_cozinha", ("sala", "cozinha", "sofa", "mesa", "geladeira", "televisao", "tv", "sacola", "apartamento", "casa")),
        ("big_face", ("congelou", "gelou", "coracao", "suor", "olhou", "rosto", "respiracao", "panico", "medo")),
        ("blecaute_olhos", ("blecaute", "breu", "apagao", "escuridao", "olhos", "vulto", "sombra")),
    ]
    melhor_mod = "quarto_noturno"
    melhor_score = 0
    for mod, termos in regras:
        score = sum(1 for termo in termos if termo in norm)
        if score > melhor_score:
            melhor_score = score
            melhor_mod = mod
    if melhor_score > 0:
        return melhor_mod

    ciclo = ("quarto_noturno", "corredor_escuro", "sala_cozinha", "big_face", "blecaute_olhos")
    return ciclo[idx % len(ciclo)]


def inferir_sfx_para_texto(texto: str, catalogo: dict[str, float]) -> str | None:
    norm = normalizar_texto(texto)
    mapa = [
        ("tranco_elevador", ("tranco", "travou", "cabo", "caiu o elevador")),
        ("porta_elevador", ("elevador", "cabine", "subsolo")),
        ("alarme_interfone", ("emergencia", "alarme", "campainha")),
        ("interfone", ("interfone", "porteiro", "portaria", "ligacao", "chiado")),
        ("guarda_roupa", ("guarda roupa", "armario", "rangido", "rangeu")),
        ("passos_corredor", ("passos", "corredor", "andando", "pisada")),
        ("porta_impacto", ("porta", "bateu", "batida", "trancou", "macaneta")),
        ("sussurro", ("sussurro", "sussurrou", "respiracao", "voz baixa")),
        ("glitch_tv", ("camera", "cctv", "tela", "monitor", "estatica", "sinal")),
        ("heartbeat", ("coracao", "batimento", "pulso", "panico")),
        ("whoosh", ("vulto", "sombra", "sumiu", "espelho")),
    ]
    for nome, termos in mapa:
        if nome in catalogo and any(t in norm for t in termos):
            return nome
    return None


def extrair_citacao_tela(texto: str, limite: int = 88) -> str:
    """Extrai trecho curto de fala/mensagem para exibir no celular ou CCTV."""
    m = re.search(r"[\"'«]([^\"'»]{6,110})[\"'»]", texto)
    if m:
        trecho = sanitizar_texto(m.group(1))
        return trecho[:limite].strip()
    if ":" in texto:
        depois = sanitizar_texto(texto.split(":", 1)[1])
        if len(depois) >= 6:
            return depois[:limite].strip()
    limpo = sanitizar_texto(texto)
    if len(limpo) <= limite:
        return limpo
    corte = limpo[:limite].rsplit(" ", 1)[0]
    return (corte or limpo[:limite]).strip() + "..."


def _extrair_palavras_chave(titulo: str, texto: str, qtd: int = 7) -> list[str]:
    norm = normalizar_texto(f"{titulo} {texto}")
    contagem: dict[str, int] = {}
    ordem: list[str] = []
    for tok in norm.split():
        if len(tok) < 4 or tok in STOPWORDS_PT or tok.isdigit():
            continue
        if tok not in contagem:
            ordem.append(tok)
        contagem[tok] = contagem.get(tok, 0) + 1
    ranqueadas = sorted(ordem, key=lambda w: (-contagem[w], -len(w)))
    return ranqueadas[:qtd] or ["suspense", "madrugada", "misterio", "vulto", "alerta"]


def _dividir_em_blocos_narrativos(roteiro_bruto: str) -> list[str]:
    """Divide o roteiro bruto em 6 a 14 blocos narrativos equilibrados para cenas."""
    limpo = sanitizar_texto(roteiro_bruto)
    frases = [f.strip() for f in RE_SEPARAR_FRASES.split(limpo) if f.strip()]
    if not frases:
        raise ValueError("Roteiro bruto vazio apos sanitizacao.")

    # Garante pontuacao final em cada frase
    frases_fmt: list[str] = []
    for f in frases:
        if not f.endswith((".", "!", "?")):
            f = f + "."
        frases_fmt.append(f)

    total_palavras = sum(len(f.split()) for f in frases_fmt)
    alvo_blocos = 10 if total_palavras > LIMITE_PALAVRAS_PARTE_2 else 7
    if len(frases_fmt) <= alvo_blocos:
        # Se houver frases longas e poucos blocos, divide em virgulas ou ponto medio garantindo >= 3 blocos
        min_blocos = 4 if total_palavras >= 28 else 3
        while len(frases_fmt) < min_blocos:
            idx_maior = max(range(len(frases_fmt)), key=lambda i: len(frases_fmt[i].split()))
            maior = frases_fmt[idx_maior]
            palavras_m = maior.split()
            if len(palavras_m) < 6:
                break
            if "," in maior:
                partes = [p.strip() for p in maior.split(",") if p.strip()]
                meio = max(1, len(partes) // 2)
                p1 = ", ".join(partes[:meio]).rstrip(".,!?") + "."
                p2 = ", ".join(partes[meio:])
            else:
                meio = len(palavras_m) // 2
                p1 = " ".join(palavras_m[:meio]).rstrip(".,!?") + "."
                p2 = " ".join(palavras_m[meio:])
            if p2:
                p2 = p2[0].upper() + p2[1:]
                if not p2.endswith((".", "!", "?")):
                    p2 += "."
            frases_fmt = frases_fmt[:idx_maior] + [p1, p2] + frases_fmt[idx_maior + 1 :]
        return frases_fmt

    # Agrupa frases curtas consecutivas mantendo ultima frase isolada para o plot twist
    ultima = frases_fmt[-1]
    corpo = frases_fmt[:-1]
    max_corpo = max(4, alvo_blocos - 1)
    palavras_por_bloco = max(12, int(sum(len(f.split()) for f in corpo) / max_corpo))

    blocos: list[str] = []
    atual: list[str] = []
    p_atual = 0
    for f in corpo:
        pf = len(f.split())
        if atual and (p_atual + pf > palavras_por_bloco + 6) and len(blocos) < max_corpo - 1:
            blocos.append(" ".join(atual))
            atual = [f]
            p_atual = pf
        else:
            atual.append(f)
            p_atual += pf
    if atual:
        blocos.append(" ".join(atual))
    blocos.append(ultima)
    return blocos


def _escolher_katana_hits(blocos: list[dict], total_desejado: int = 4) -> list[dict]:
    """Seleciona 3 a 5 palavras de impacto reais presentes nos blocos para Katana Hits."""
    palavras_impacto = (
        "travou", "sumiu", "vazio", "vazia", "ninguem", "alguem", "sorriu", "sorri",
        "atras", "dentro", "olhos", "apagou", "apaga", "nunca", "morto", "morta",
        "sangue", "grito", "sombra", "vulto", "espelho", "camera", "subsolo",
        "minutos", "horas", "ligacao", "mensagem", "porta", "janela", "silencio",
        "voce", "igual", "outro", "outra", "errado", "falso", "armario", "cama",
    )
    n = len(blocos)
    if n == 0:
        return []
    alvo = max(3, min(5, total_desejado if n >= 5 else 3))

    indices_candidatos: list[int] = []
    if n >= alvo:
        passo = (n - 1) / float(alvo)
        for k in range(alvo):
            idx = min(n - 1, max(1 if n > 2 else 0, int(round((k + 1) * passo))))
            if idx not in indices_candidatos:
                indices_candidatos.append(idx)
    while len(indices_candidatos) < min(alvo, n):
        for i in range(n - 1, -1, -1):
            if i not in indices_candidatos:
                indices_candidatos.append(i)
                break
    indices_candidatos.sort()

    hits: list[dict] = []
    usadas: set[str] = set()
    cores = ("red", "yellow", "white", "red", "yellow")

    for h_i, b_idx in enumerate(indices_candidatos[:5], start=1):
        texto_b = str(blocos[b_idx].get("texto", ""))
        tokens = [re.sub(r"[^A-Za-zÀ-ÿ0-9]", "", t) for t in texto_b.split()]
        tokens = [t for t in tokens if len(t) >= 3]

        escolhida = ""
        for tok in tokens:
            chave = normalizar_texto(tok)
            if chave in palavras_impacto and chave not in usadas:
                escolhida = tok
                break
        if not escolhida:
            for tok in reversed(tokens):
                chave = normalizar_texto(tok)
                if len(chave) >= 4 and chave not in STOPWORDS_PT and chave not in usadas:
                    escolhida = tok
                    break
        if not escolhida and tokens:
            escolhida = tokens[-1]
        if not escolhida:
            escolhida = "CHOQUE"

        gatilho = re.sub(r"[^a-z0-9]", "", normalizar_texto(escolhida)) or "choque"
        usadas.add(gatilho)
        palavra_upper = escolhida.upper()
        eh_ultimo = h_i == len(indices_candidatos[:5])
        hits.append(
            {
                "id": f"hit_{h_i:02d}",
                "evento": f"hit_{h_i:02d}",
                "bloco_idx": b_idx,
                "palavra_gatilho": gatilho,
                "linhas": [palavra_upper],
                "duracao": 0.45 if eh_ultimo else 0.40,
                "cor": "red" if eh_ultimo else cores[(h_i - 1) % len(cores)],
            }
        )
    return hits


def diretor_mock_deterministico(
    roteiro_bruto: str,
    titulo_forcado: str | None = None,
    catalogo_sfx: dict[str, float] | None = None,
) -> dict:
    """Modo deterministico offline (--mock e fallback de seguranca do Gemini)."""
    catalogo = catalogo_sfx or carregar_catalogo_sfx()
    limpo = sanitizar_texto(roteiro_bruto)
    blocos_txt = _dividir_em_blocos_narrativos(limpo)
    horario = extrair_horario(limpo)
    nome_prot = extrair_nome_protagonista(limpo)

    if titulo_forcado and sanitizar_texto(titulo_forcado):
        titulo = sanitizar_texto(titulo_forcado)[:72]
    else:
        primeiras = blocos_txt[0].rstrip(".!?").split()
        titulo = " ".join(primeiras[:6]).strip() or "Suspense da Madrugada"
        titulo = titulo[0].upper() + titulo[1:]

    tema = sanitizar_texto(blocos_txt[0] + " " + (blocos_txt[-1] if len(blocos_txt) > 1 else ""))[:180]
    palavras_chave = _extrair_palavras_chave(titulo, limpo, qtd=7)

    n = len(blocos_txt)
    cameras_ciclo = ("push_in", "pan_right", "tight_close", "pan_left", "pull_out", "push_in")
    blocos: list[dict] = []
    ultimo_mod = ""

    for i, txt in enumerate(blocos_txt):
        norm = normalizar_texto(txt)
        mod = inferir_modulo_por_texto(txt, i, n)
        if i == 0 and any(k in norm for k in ("quarto", "acorda", "acordou", "cama")) and mod == "celular_notificacao":
            mod = "quarto_noturno"
        if mod == ultimo_mod:
            alternativas = [
                m for m in ("big_face", "corredor_escuro", "sala_cozinha", "quarto_noturno", "blecaute_olhos")
                if m != ultimo_mod
            ]
            if i == n - 1:
                mod = "blecaute_olhos" if ultimo_mod != "blecaute_olhos" else "big_face"
            elif i == n - 2:
                mod = "big_face" if ultimo_mod != "big_face" else "corredor_escuro"
            else:
                mod = alternativas[i % len(alternativas)]
        ultimo_mod = mod

        if i == n - 1:
            perfil = "sussurro_twist"
            mood = "red" if mod == "big_face" else "dark"
            expr = "shock" if mod == "big_face" else "sinister_smile"
        elif any(k in norm for k in ("ligacao", "chamada", "telefone", "na linha", "celular")) and (":" in txt or '"' in txt):
            perfil = "voz_telefone"
            mood = "violet"
            expr = "fear"
        elif any(k in norm for k in ("interfone", "porteiro")) and (":" in txt or '"' in txt):
            perfil = "interfone_porteiro"
            mood = "cctv" if mod == "camera_cctv" else "violet"
            expr = "fear"
        elif i >= max(1, int(n * 0.55)) or any(k in norm for k in ("panico", "correu", "corre", "desesper", "grito", "travou", "bateu", "esmag", "coracao")):
            perfil = "panico"
            mood = "red" if i >= n - 3 else "violet"
            expr = "shock" if i >= n - 2 else "fear"
        else:
            perfil = "narrador_tenso"
            mood = "cctv" if mod == "camera_cctv" else ("navy" if i % 2 == 0 else "violet")
            expr = "worry" if i > 0 else "neutral"

        citacao = extrair_citacao_tela(txt, limite=84)
        props = {
            "objeto": "guarda_roupa" if "armario" in norm or "guarda roupa" in norm else "janela",
            "vulto": i >= max(2, n // 2),
            "celular_app": "ALERTA" if any(k in norm for k in ("alerta", "emergencia", "banco", "pix")) else "MENSAGEM",
            "celular_remetente": "NÚMERO OCULTO" if "oculto" in norm or "desconhecido" in norm else "CONTATO",
            "celular_mensagem": citacao,
            "celular_mensagem_2": "NÃO OLHE PARA TRÁS." if i >= n - 3 else "",
            "cctv_cam": f"CAM 0{(i % 3) + 1}",
            "cctv_local": "CORREDOR" if "corredor" in norm else ("QUARTO" if "quarto" in norm else "ACESSO"),
            "cctv_status": "MOVIMENTO DETECTADO" if i < n - 2 else "ALERTA DE PRESENÇA",
            "elevador_andar": "S3" if "subsolo" in norm or "s3" in norm else "06",
            "gps_destino": "DESTINO: SUA CASA" if "casa" in norm else "DESTINO DESCONHECIDO",
            "gps_alerta": "ROTA RECALCULADA" if "gps" in norm or "rota" in norm else "ALERTA DE TRAJETO",
            "corredor_objeto": "cadeira" if "cadeira" in norm else ("vulto" if i >= n // 2 else "porta"),
            "pose": "panic" if perfil == "panico" else ("phone" if mod == "celular_notificacao" else ("walk" if "corredor" in norm else "idle")),
        }

        blocos.append(
            {
                "perfil_voz": perfil,
                "texto": txt,
                "modulo": mod,
                "mood": mood,
                "expressao": expr,
                "camera": cameras_ciclo[i % len(cameras_ciclo)],
                "props": props,
                "sfx_depois": None,
            }
        )

    # Insere 1 a 2 SFX diegeticos no meio + obrigatoriamente impacto_twist antes do bloco final
    sfx_colocados = 0
    for idx_b in range(1, max(1, n - 1)):
        if sfx_colocados >= 2:
            break
        sfx_cand = inferir_sfx_para_texto(blocos[idx_b]["texto"], catalogo)
        if sfx_cand and sfx_cand != "impacto_twist":
            blocos[idx_b]["sfx_depois"] = sfx_cand
            sfx_colocados += 1
    if n >= 2:
        blocos[n - 2]["sfx_depois"] = "impacto_twist"

    katana_hits = _escolher_katana_hits(blocos, total_desejado=4 if n >= 6 else 3)

    cor_idx = abs(sum(ord(c) for c in titulo)) % len(PALETA_JAQUETAS)
    jaq, jaq_s, jaq_e = PALETA_JAQUETAS[cor_idx]

    return {
        "titulo": titulo,
        "tema": tema,
        "palavras_chave": palavras_chave,
        "horario": horario,
        "protagonista": {
            "nome": nome_prot,
            "jaqueta": jaq,
            "jaqueta_sombra": jaq_s,
            "jaqueta_escura": jaq_e,
            "pele": "#E0B292",
            "cabelo": "#141720",
        },
        "paleta": dict(PALETA_PADRAO),
        "blocos": blocos,
        "katana_hits": katana_hits,
    }


def _montar_prompt_gemini(
    roteiro_bruto: str,
    titulo_sugerido: str | None,
    sfx_validos: list[str],
) -> str:
    titulo_hint = f"Titulo sugerido pelo usuario: {titulo_sugerido}\n" if titulo_sugerido else ""
    return (
        "Voce e o Diretor IA V6 de uma fabrica de YouTube Shorts de micro-suspense psicologico em pt-BR.\n"
        "Transforme o roteiro bruto abaixo em um plano estruturado JSON estrito.\n"
        "REGRAS OBRIGATORIAS:\n"
        "1. ZERO emoji e ZERO travessao (em-dash ou en-dash) em qualquer texto.\n"
        "2. Preserve fielmente a historia do roteiro bruto em portugues natural, dividida em 6 a 12 blocos narrativos.\n"
        "3. Cada bloco escolhe:\n"
        f"   - perfil_voz: um de {list(PERFIS_VOZ)} (use sussurro_twist no bloco final de revelacao; nunca use cta_comercial nos blocos de historia).\n"
        f"   - modulo: um de {list(MODULOS_CENARIO)}.\n"
        f"   - mood: um de {list(MOODS_VALIDOS)}.\n"
        f"   - expressao: um de {list(EXPRESSOES_VALIDAS)}.\n"
        f"   - camera: um de {list(CAMERAS_VALIDAS)}.\n"
        f"   - sfx_depois: null ou um de {sfx_validos} (coloque impacto_twist no penultimo bloco antes da revelacao final; no maximo 3 SFX no total).\n"
        "   - props: objeto com textos curtos reais quando aplicavel (celular_app, celular_remetente, celular_mensagem, celular_mensagem_2, cctv_cam, cctv_local, cctv_status, elevador_andar, gps_destino, gps_alerta, corredor_objeto, objeto, vulto, pose).\n"
        "4. katana_hits: lista de 3 a 5 impactos curtos (1 a 2 palavras em MAIUSCULAS), cada um com bloco_idx (indice 0-based do bloco), palavra_gatilho (uma palavra exata sem acento/pontuacao presente no texto daquele bloco), linhas (lista de 1 a 2 strings curtas), duracao (0.36 a 0.48), cor ('red', 'yellow' ou 'white').\n"
        "5. horario: string HH:MM mencionada no roteiro (ou horario noturno coerente como '02:47').\n"
        "6. Responda APENAS com JSON valido no formato:\n"
        "{\n"
        '  "titulo": "...",\n'
        '  "tema": "resumo curto em 1 frase",\n'
        '  "palavras_chave": ["kw1", "kw2", "kw3", "kw4", "kw5"],\n'
        '  "horario": "02:47",\n'
        '  "protagonista": {"nome": "...", "jaqueta": "#0F766E", "pele": "#E0B292", "cabelo": "#141720"},\n'
        '  "paleta": {"bg_navy": "#0A0F1D", "bg_violet": "#130926", "bg_red": "#3B0A0A", "accent": "#38D9FF", "alert": "#FF3B30", "yellow": "#FFD400"},\n'
        '  "blocos": [{"perfil_voz": "...", "texto": "...", "modulo": "...", "mood": "...", "expressao": "...", "camera": "...", "sfx_depois": null, "props": {}}],\n'
        '  "katana_hits": [{"bloco_idx": 2, "palavra_gatilho": "travou", "linhas": ["TRAVOU"], "duracao": 0.42, "cor": "red"}]\n'
        "}\n\n"
        f"{titulo_hint}"
        "ROTEIRO BRUTO:\n"
        f"{roteiro_bruto}\n"
    )


def validar_gemini_api_key(api_key: str | None) -> str:
    """Valida formato minimo de GEMINI_API_KEY antes de chamar a API para falhar com mensagem clara."""
    chave = str(api_key or "").strip()
    if not chave:
        raise RuntimeError(
            "GEMINI_API_KEY ausente. Configure o secret GEMINI_API_KEY em Repository Secrets (Actions) ou no .env."
        )
    if any(ch.isspace() for ch in chave):
        raise RuntimeError("GEMINI_API_KEY invalida: contem espacos ou quebras de linha.")
    low = chave.lower()
    placeholders = ("sua_chave", "your_api_key", "changeme", "replace_me", "placeholder", "coloque_aqui")
    if len(chave) < 10 or any(p in low for p in placeholders):
        raise RuntimeError(
            "GEMINI_API_KEY invalida (curta demais ou texto de exemplo). Verifique o valor salvo nos Secrets."
        )
    return chave


def _extrair_json_resposta(texto: str) -> dict:
    """Limpa fences/BOM/virgulas sobrando e valida que o retorno do Gemini e um objeto JSON nao vazio."""
    bruto = str(texto or "").lstrip("\ufeff").strip()
    if not bruto:
        raise ValueError("Resposta vazia do Gemini ao esperar JSON.")
    if "```" in bruto:
        m_fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", bruto, flags=re.IGNORECASE)
        if m_fence:
            bruto = m_fence.group(1).strip()
        else:
            bruto = re.sub(r"^```(?:json)?\s*", "", bruto, flags=re.IGNORECASE)
            bruto = re.sub(r"\s*```$", "", bruto).strip()
    inicio = bruto.find("{")
    fim = bruto.rfind("}")
    if inicio >= 0 and fim > inicio:
        bruto = bruto[inicio : fim + 1]
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        # Remove virgulas finais invalidas antes de } ou ] antes de desistir
        corrigido = re.sub(r",\s*([}\]])", r"\1", bruto)
        dados = json.loads(corrigido)
    if not isinstance(dados, dict) or not dados:
        raise ValueError("JSON retornado pelo Gemini precisa ser um objeto nao vazio.")
    return dados


def _extrair_retry_after_s(exc: urllib.error.HTTPError, padrao: float) -> float:
    """Respeita cabecalho Retry-After (limitado a 30s) quando devolvido em HTTP 429/503."""
    try:
        hdrs = getattr(exc, "headers", None)
        if hdrs is not None:
            raw = hdrs.get("Retry-After")
            if raw is not None:
                val = float(str(raw).strip())
                if val > 0:
                    return min(30.0, max(padrao, val))
    except Exception:
        pass
    return padrao


def _extrair_erro_http_gemini(exc: urllib.error.HTTPError, api_key: str) -> str:
    """Extrai status e mensagem reais devolvidos pela API Gemini sem vazar a chave."""
    bruto = ""
    try:
        bruto = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        bruto = ""
    msg = bruto
    if bruto:
        try:
            obj = json.loads(bruto)
            err = obj.get("error") if isinstance(obj, dict) else None
            if isinstance(err, dict):
                status = str(err.get("status", "")).strip()
                detalhe = str(err.get("message", "")).strip()
                msg = f"{status}: {detalhe}" if status and detalhe else (detalhe or status or bruto)
        except Exception:
            pass
    msg = re.sub(r"\s+", " ", msg).strip()[:400]
    if api_key:
        msg = msg.replace(api_key, "***API_KEY***")
    return msg or str(exc.reason or f"HTTP {exc.code}")


def _montar_lista_modelos(modelo_preferido: str | None) -> list[str]:
    env_mod = os.environ.get("GEMINI_DIRETOR_MODEL", "").strip()
    ordem: list[str] = []
    for m in (modelo_preferido, env_mod, *GEMINI_MODELOS_FALLBACK):
        nome = str(m or "").strip()
        if nome.startswith("models/"):
            nome = nome[len("models/") :]
        if nome and nome not in ordem:
            ordem.append(nome)
    return ordem


def _descobrir_modelos_gemini_disponiveis(
    api_key: str,
    urlopen_fn: Callable | None = None,
) -> list[str]:
    """Consulta GET /v1beta/models para autodescobrir modelos ativos com suporte a generateContent."""
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "x-goog-api-key": api_key},
        method="GET",
    )
    opener = urlopen_fn or urllib.request.urlopen
    try:
        with opener(req, timeout=30) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    excluir = (
        "tts",
        "image",
        "imagen",
        "live",
        "embedding",
        "aqa",
        "omni",
        "robotics",
        "veo",
        "lyria",
        "audio",
        "transcribe",
        "translate",
        "research",
        "decision",
        "computer-use",
        "gemini-1.",
        "gemini-2.0",
    )
    candidatos: list[str] = []
    for item in dados.get("models") or []:
        metodos = item.get("supportedGenerationMethods") or []
        if "generateContent" not in metodos:
            continue
        nome = str(item.get("name", "")).strip()
        if nome.startswith("models/"):
            nome = nome[len("models/") :]
        low = nome.lower()
        if not low.startswith("gemini-"):
            continue
        if any(tok in low for tok in excluir):
            continue
        candidatos.append(nome)

    def _prioridade(nome: str) -> tuple[int, int, str]:
        low = nome.lower()
        legado_25 = 1 if "gemini-2.5" in low else 0
        if "flash-lite" in low:
            return (legado_25, 0, low)
        if "flash" in low and "preview" not in low:
            return (legado_25, 1, low)
        if "hydrogen" in low:
            return (legado_25, 2, low)
        if "flash" in low:
            return (legado_25, 3, low)
        return (legado_25, 4, low)

    candidatos.sort(key=_prioridade)
    return candidatos[:8]


def _chamar_gemini_json(
    prompt: str,
    api_key: str,
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    retry_esperas: tuple[float, ...] = (3.0, 8.0, 18.0),
    modelo_ativo_ref: dict[str, str] | None = None,
) -> dict:
    """Chama Gemini REST API com JSON estruturado, 3 retries com backoff e fallback de modelos."""
    api_key = validar_gemini_api_key(api_key)
    # Sem temperature/top_p/top_k: removidos/depreciados a partir do Gemini 3.5/3.6/3.8/4
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    opener = urlopen_fn or urllib.request.urlopen
    max_t = 1 + len(retry_esperas)

    modelos_fila = _montar_lista_modelos(modelo)
    testados: set[str] = set()
    autodescoberta_feita = False
    ultimo_erro_msg = "Falha desconhecida ao consultar a API Gemini."

    idx_m = 0
    while idx_m < len(modelos_fila):
        modelo_atual = modelos_fila[idx_m]
        idx_m += 1
        if modelo_atual in testados:
            continue
        testados.add(modelo_atual)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_atual}:generateContent"
        avancar_modelo = False

        for tentativa in range(max_t):
            req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
            try:
                with opener(req, timeout=60) as resp:
                    corpo = resp.read().decode("utf-8")
                envelope = json.loads(corpo)
                candidatos = envelope.get("candidates") or []
                if not candidatos:
                    raise RuntimeError(f"Resposta do Gemini ({modelo_atual}) sem 'candidates'.")
                partes = (candidatos[0].get("content") or {}).get("parts") or []
                # Ignora blocos internos de pensamento (thought=True) dos modelos Gemini 3.x / 4
                partes_resp = [p for p in partes if not p.get("thought")] or partes
                texto_json = "".join(str(p.get("text", "")) for p in partes_resp)
                if not texto_json.strip():
                    raise RuntimeError(f"Resposta do Gemini ({modelo_atual}) sem conteudo textual.")
                dados_json = _extrair_json_resposta(texto_json)
                if modelo_ativo_ref is not None:
                    modelo_ativo_ref["modelo"] = modelo_atual
                return dados_json
            except urllib.error.HTTPError as exc:
                detalhe = _extrair_erro_http_gemini(exc, api_key)
                detalhe_low = detalhe.lower()
                ultimo_erro_msg = f"Gemini [{modelo_atual}] HTTP {exc.code}: {detalhe}"

                if exc.code in (401, 403) or (
                    exc.code == 400 and ("api key" in detalhe_low or "api_key" in detalhe_low)
                ):
                    print(f"ERRO autenticacao/permissao {ultimo_erro_msg}", flush=True)
                    raise RuntimeError(
                        f"Chave GEMINI_API_KEY invalida, rejeitada ou sem permissao ({ultimo_erro_msg})."
                    ) from None

                if exc.code == 404:
                    print(
                        f"AVISO modelo indisponivel ({ultimo_erro_msg}). Tentando proximo modelo ativo...",
                        flush=True,
                    )
                    avancar_modelo = True
                    break

                if exc.code == 400 and any(
                    tok in detalhe_low
                    for tok in ("response_mime_type", "json mode", "not supported", "not enabled")
                ):
                    print(
                        f"AVISO modelo incompativel ({ultimo_erro_msg}). Tentando proximo modelo ativo...",
                        flush=True,
                    )
                    avancar_modelo = True
                    break

                if exc.code in (429, 500, 502, 503, 504):
                    if tentativa < len(retry_esperas):
                        espera = _extrair_retry_after_s(exc, float(retry_esperas[tentativa]))
                        print(
                            f"AVISO {ultimo_erro_msg} na tentativa {tentativa + 1}/{max_t}. "
                            f"Aguardando {espera:.1f}s...",
                            flush=True,
                        )
                        sleep_fn(espera)
                        continue
                    print(
                        f"AVISO {ultimo_erro_msg} esgotou {len(retry_esperas)} retries; tentando proximo modelo da cascata...",
                        flush=True,
                    )
                    avancar_modelo = True
                    break

                print(f"ERRO definitivo {ultimo_erro_msg}", flush=True)
                raise RuntimeError(ultimo_erro_msg) from None
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
                ultimo_erro_msg = f"Gemini [{modelo_atual}] {type(exc).__name__}: {exc}"
                if tentativa < len(retry_esperas):
                    espera = float(retry_esperas[tentativa])
                    print(
                        f"AVISO {ultimo_erro_msg} na tentativa {tentativa + 1}/{max_t}. "
                        f"Aguardando {espera:.1f}s...",
                        flush=True,
                    )
                    sleep_fn(espera)
                    continue
                avancar_modelo = True
                break

        if avancar_modelo and idx_m >= len(modelos_fila) and not autodescoberta_feita:
            autodescoberta_feita = True
            descobertos = [
                m for m in _descobrir_modelos_gemini_disponiveis(api_key, urlopen_fn=opener) if m not in testados
            ]
            if descobertos:
                print(
                    f"AVISO autodescoberta /v1beta/models encontrou modelos ativos: {descobertos}",
                    flush=True,
                )
                modelos_fila.extend(descobertos)

    raise RuntimeError(f"Todos os modelos Gemini falharam ({sorted(testados)}). Ultimo erro: {ultimo_erro_msg}")


def _resumir_historico_proibido(dados_hist: dict) -> str:
    linhas: list[str] = []
    for v in dados_hist.get("videos", []):
        vid = int(v.get("id", 0))
        titulo = str(v.get("titulo", "")).strip()
        tema = str(v.get("tema", "")).strip()
        kws = ", ".join(str(k) for k in v.get("palavras_chave", [])[:6])
        linhas.append(f"- Video {vid:02d}: '{titulo}' | Tema: {tema} | Palavras-chave: {kws}")
    return "\n".join(linhas) if linhas else "- (nenhum video anterior)"


def _montar_prompt_roteiro_inedito(
    dados_hist: dict,
    proximo_id: int,
    titulo_sugerido: str | None = None,
    motivo_rejeicao: str | None = None,
) -> str:
    proibidos = _resumir_historico_proibido(dados_hist)
    dica_titulo = (
        f"Use ou adapte este titulo solicitado pelo usuario: '{titulo_sugerido}'.\n"
        if titulo_sugerido
        else "Crie um titulo curto, magnetico e inedito em portugues do Brasil (3 a 6 palavras).\n"
    )
    aviso_rej = (
        f"\nATENCAO: a tentativa anterior foi rejeitada por similaridade ({motivo_rejeicao}). "
        "Mude COMPLETAMENTE o cenario, os personagens, o objeto central e o plot twist!\n"
        if motivo_rejeicao
        else ""
    )
    return (
        f"Voce e o roteirista-chefe de um canal viral de YouTube Shorts / Reels de micro-suspense "
        f"psicologico em portugues do Brasil (Video {proximo_id:02d}).\n"
        "Sua missao e criar uma historia 100% INEDITA, realista, cotidiana e arrepiante.\n\n"
        "TEMAS JA PRODUZIDOS (PROIBIDO REPETIR CENARIO, PREMISSA, OBJETO OU PLOT TWIST):\n"
        f"{proibidos}\n"
        f"{aviso_rej}\n"
        "REGRAS OBRIGATORIAS DO ROTEIRO:\n"
        f"1. {dica_titulo}"
        "2. Escreva entre 185 e 245 palavras (ritmo rapido para renderizar Parte 1 e Parte 2 automaticas).\n"
        "3. Comece com um horario exato da madrugada ou noite (ex.: 'Duas e dezessete da manha.') e um "
        "protagonista com nome brasileiro comum em uma situacao cotidiana concreta e diferente dos videos "
        "anteriores (ex.: lavanderia 24 horas, ultimo vagao do metro, quarto de hotel, plantao noturno, "
        "estacionamento de shopping, onibus interestadual, farmacia de madrugada, caixa eletronico, "
        "cabine de pedagio, quarto de Airbnb).\n"
        "4. Use frases curtas, diretas e cinematograficas, com escalada de tensao ate um plot twist seco "
        "e perturbador na ultima frase.\n"
        "5. ZERO emoji, ZERO travessao (em-dash ou en-dash), ZERO tags [VOZ] ou [SFX], ZERO CTA "
        "(a CTA e as tags serao inseridas automaticamente na etapa seguinte).\n"
        "6. Responda APENAS com JSON valido no formato:\n"
        "{\n"
        '  "titulo": "Titulo Inedito Curto",\n'
        '  "tema": "Resumo objetivo em 1 frase da premissa inedita",\n'
        '  "roteiro_bruto": "Texto corrido completo da historia em pt-BR (185 a 245 palavras)."\n'
        "}\n"
    )


def gerar_roteiro_inedito_gemini(
    dados_hist: dict,
    titulo_sugerido: str | None,
    api_key: str,
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    modelo_ativo_ref: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Gera obrigatoriamente um titulo e roteiro bruto 100% ineditos via Gemini (contra historico)."""
    prox_id = proximo_numero_livre(dados_hist)
    motivo_rej: str | None = None
    ultimo_erro = "Gemini nao retornou um roteiro inedito valido."
    ref_local = modelo_ativo_ref if modelo_ativo_ref is not None else {}

    for tentativa in range(1, 4):
        prompt = _montar_prompt_roteiro_inedito(
            dados_hist,
            proximo_id=prox_id,
            titulo_sugerido=titulo_sugerido,
            motivo_rejeicao=motivo_rej,
        )
        dados = _chamar_gemini_json(
            prompt=prompt,
            api_key=api_key,
            modelo=ref_local.get("modelo", modelo),
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
            modelo_ativo_ref=ref_local,
        )
        titulo_gerado = sanitizar_texto(str(dados.get("titulo", "") or titulo_sugerido or "")).strip()
        tema_gerado = sanitizar_texto(str(dados.get("tema", "") or "")).strip()
        roteiro_gerado = sanitizar_texto(str(dados.get("roteiro_bruto", "") or "")).strip()

        if len(roteiro_gerado.split()) < 60:
            ultimo_erro = f"Roteiro inedito curto demais ({len(roteiro_gerado.split())} palavras)."
            motivo_rej = ultimo_erro
            continue

        if not titulo_gerado:
            titulo_gerado = f"O Turno das 02h{10 + (prox_id % 45):02d}"

        candidato = {
            "titulo": titulo_gerado,
            "slug": gerar_slug(titulo_gerado, fallback=f"video-{prox_id:02d}"),
            "tema": tema_gerado or roteiro_gerado[:160],
            "palavras_chave": _extrair_palavras_chave(titulo_gerado, roteiro_gerado, qtd=6),
        }
        conflito: str | None = None
        for v_ant in dados_hist.get("videos", []):
            rep, mot = _similares(v_ant, candidato)
            if rep:
                conflito = f"parecido com Video {int(v_ant.get('id', 0)):02d}: {mot}"
                break
        if conflito:
            print(
                f"AVISO roteiro inedito tentativa {tentativa}/3 rejeitado ({conflito}). Regerando...",
                flush=True,
            )
            motivo_rej = conflito
            ultimo_erro = conflito
            continue

        return titulo_gerado, roteiro_gerado

    raise RuntimeError(f"Nao foi possivel gerar episodio inedito via Gemini: {ultimo_erro}")


def gerar_roteiro_inedito_mock(dados_hist: dict, titulo_sugerido: str | None = None) -> tuple[str, str]:
    """Gerador deterministico offline apenas para testes locais (--mock)."""
    prox_id = proximo_numero_livre(dados_hist)
    hora = f"02:{15 + (prox_id * 7) % 40:02d}"
    titulo = sanitizar_texto(titulo_sugerido) if titulo_sugerido else f"A Lavanderia das {hora.replace(':', 'h')}"
    roteiro = (
        f"Eram {hora} da madrugada. Bruno entra numa lavanderia vinte e quatro horas completamente vazia "
        f"no fim da rua para secar o uniforme do turno da manha. "
        f"Ele coloca as moedas na maquina numero quatro e se senta perto da vitrine molhada. "
        f"O tambor gira devagar fazendo um estalo metalico ritmado. "
        f"Cinco minutos depois, o vidro da lavanderia embaca por dentro mesmo com o ar frio ligado. "
        f"Bruno olha pro painel digital da maquina: o contador para em treze minutos e nao desce mais. "
        f"Ele levanta para checar a trava da porta automatica da entrada. A luz verde do sensor apaga. "
        f"De repente o telefone fixo de emergencia na parede comeca a tocar no escuro. "
        f"Bruno atende tremendo. Do outro lado, a voz da atendente da central de monitoramento pergunta: "
        f"Senhor, por que voce ligou todas as seis secadoras se a camera mostra voce parado fora da loja "
        f"olhando pela vitrine? Bruno vira o pescoco devagar em direcao a rua deserta. "
        f"Do lado de fora, encostado no vidro embacado, um homem com o mesmo uniforme dele levanta a mao "
        f"e escreve ao contrario no vidro: ja deu o meu tempo, agora e a sua vez."
    )
    return titulo, roteiro


def chamar_gemini_diretor(
    roteiro_bruto: str,
    titulo_sugerido: str | None,
    api_key: str,
    catalogo_sfx: dict[str, float],
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    modelo_ativo_ref: dict[str, str] | None = None,
) -> dict:
    """Chama Gemini REST API (stdlib urllib) passando a chave no header x-goog-api-key."""
    prompt = _montar_prompt_gemini(roteiro_bruto, titulo_sugerido, sorted(catalogo_sfx.keys()))
    return _chamar_gemini_json(
        prompt=prompt,
        api_key=api_key,
        modelo=modelo,
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
        modelo_ativo_ref=modelo_ativo_ref,
    )


def validar_e_corrigir_plano(
    plano_bruto: dict | None,
    roteiro_bruto: str,
    titulo_forcado: str | None,
    catalogo_sfx: dict[str, float],
) -> tuple[dict, list[str]]:
    """Valida estritamente o plano do Diretor IA e corrige qualquer campo ausente/invalido."""
    avisos: list[str] = []
    fallback = diretor_mock_deterministico(roteiro_bruto, titulo_forcado=titulo_forcado, catalogo_sfx=catalogo_sfx)
    if not isinstance(plano_bruto, dict):
        avisos.append("Plano invalido (nao e dict): fallback deterministico aplicado.")
        return fallback, avisos

    titulo = sanitizar_texto(titulo_forcado or plano_bruto.get("titulo") or fallback["titulo"])[:72]
    if not titulo:
        titulo = fallback["titulo"]
        avisos.append("Titulo ausente: preenchido pelo fallback.")

    tema = sanitizar_texto(plano_bruto.get("tema") or fallback["tema"])[:200]
    if len(tema) < 12:
        tema = fallback["tema"]

    kws_raw = plano_bruto.get("palavras_chave")
    kws: list[str] = []
    if isinstance(kws_raw, list):
        for k in kws_raw:
            limpa = sanitizar_texto(str(k)).lower()
            if len(limpa) >= 3 and limpa not in kws:
                kws.append(limpa)
    if len(kws) < 4:
        for k in fallback["palavras_chave"]:
            if k not in kws:
                kws.append(k)
    kws = kws[:8]

    hor_raw = str(plano_bruto.get("horario", "")).strip()
    m_h = RE_HORARIO.search(hor_raw)
    horario = f"{int(m_h.group(1)):02d}:{int(m_h.group(2)):02d}" if m_h else fallback["horario"]

    prot_in = plano_bruto.get("protagonista") if isinstance(plano_bruto.get("protagonista"), dict) else {}
    jaq = _validar_hex(prot_in.get("jaqueta"), fallback["protagonista"]["jaqueta"])
    protagonista = {
        "nome": sanitizar_texto(prot_in.get("nome") or fallback["protagonista"]["nome"])[:28] or "Protagonista",
        "jaqueta": jaq,
        "jaqueta_sombra": _validar_hex(prot_in.get("jaqueta_sombra"), _escurecer_hex(jaq, 0.72)),
        "jaqueta_escura": _validar_hex(prot_in.get("jaqueta_escura"), _escurecer_hex(jaq, 0.44)),
        "pele": _validar_hex(prot_in.get("pele"), "#E0B292"),
        "cabelo": _validar_hex(prot_in.get("cabelo"), "#141720"),
    }

    pal_in = plano_bruto.get("paleta") if isinstance(plano_bruto.get("paleta"), dict) else {}
    paleta = {
        k: _validar_hex(pal_in.get(k), v) for k, v in PALETA_PADRAO.items()
    }

    blocos_in = plano_bruto.get("blocos")
    blocos_validos: list[dict] = []
    sfx_permitidos = set(catalogo_sfx.keys()) - {"glitch_cta", "cta_pop"}

    if isinstance(blocos_in, list) and len(blocos_in) >= 3:
        sfx_count = 0
        for idx, b in enumerate(blocos_in):
            if not isinstance(b, dict):
                continue
            txt = sanitizar_texto(b.get("texto", ""))
            if not txt:
                continue
            if not txt.endswith((".", "!", "?")):
                txt += "."
            perfil = str(b.get("perfil_voz", "narrador_tenso")).strip().lower()
            if perfil not in PERFIS_VOZ or perfil == "cta_comercial":
                perfil = "narrador_tenso"
                avisos.append(f"Bloco {idx + 1}: perfil_voz corrigido para narrador_tenso.")
            modulo = str(b.get("modulo", "")).strip().lower()
            if modulo not in MODULOS_CENARIO:
                modulo = inferir_modulo_por_texto(txt, idx, len(blocos_in))
                avisos.append(f"Bloco {idx + 1}: modulo invalido substituido por '{modulo}'.")
            mood = str(b.get("mood", "navy")).strip().lower()
            if mood not in MOODS_VALIDOS:
                mood = "cctv" if modulo == "camera_cctv" else "navy"
            expr = str(b.get("expressao", "neutral")).strip().lower()
            if expr not in EXPRESSOES_VALIDAS:
                expr = "fear" if perfil == "panico" else "neutral"
            cam = str(b.get("camera", "push_in")).strip().lower()
            if cam not in CAMERAS_VALIDAS:
                cam = "push_in"
            sfx_dep = b.get("sfx_depois")
            sfx_limpo: str | None = None
            if isinstance(sfx_dep, str) and sfx_dep.strip():
                cand_sfx = re.sub(r"[^a-z0-9_]", "", sfx_dep.strip().lower())
                if cand_sfx in sfx_permitidos and sfx_count < 3:
                    sfx_limpo = cand_sfx
                    sfx_count += 1
                else:
                    avisos.append(f"Bloco {idx + 1}: sfx_depois '{sfx_dep}' ignorado.")

            props_in = b.get("props") if isinstance(b.get("props"), dict) else {}
            citacao = extrair_citacao_tela(txt, limite=84)
            props = {
                "objeto": sanitizar_texto(str(props_in.get("objeto", "janela")))[:32] or "janela",
                "vulto": bool(props_in.get("vulto", idx >= max(2, len(blocos_in) // 2))),
                "celular_app": sanitizar_texto(str(props_in.get("celular_app", "MENSAGEM")))[:24].upper() or "MENSAGEM",
                "celular_remetente": sanitizar_texto(str(props_in.get("celular_remetente", "DESCONHECIDO")))[:28].upper() or "DESCONHECIDO",
                "celular_mensagem": sanitizar_texto(str(props_in.get("celular_mensagem", "")))[:92] or citacao,
                "celular_mensagem_2": sanitizar_texto(str(props_in.get("celular_mensagem_2", "")))[:92],
                "cctv_cam": sanitizar_texto(str(props_in.get("cctv_cam", "CAM 01")))[:18].upper() or "CAM 01",
                "cctv_local": sanitizar_texto(str(props_in.get("cctv_local", "CORREDOR")))[:24].upper() or "CORREDOR",
                "cctv_status": sanitizar_texto(str(props_in.get("cctv_status", "MOVIMENTO DETECTADO")))[:36].upper() or "MOVIMENTO DETECTADO",
                "elevador_andar": sanitizar_texto(str(props_in.get("elevador_andar", "S3")))[:6].upper() or "S3",
                "gps_destino": sanitizar_texto(str(props_in.get("gps_destino", "SEM DESTINO")))[:32].upper() or "SEM DESTINO",
                "gps_alerta": sanitizar_texto(str(props_in.get("gps_alerta", "ROTA RECALCULADA")))[:40].upper() or "ROTA RECALCULADA",
                "corredor_objeto": sanitizar_texto(str(props_in.get("corredor_objeto", "porta")))[:20].lower() or "porta",
                "pose": sanitizar_texto(str(props_in.get("pose", "idle")))[:20].lower() or "idle",
            }
            blocos_validos.append(
                {
                    "perfil_voz": perfil,
                    "texto": txt,
                    "modulo": modulo,
                    "mood": mood,
                    "expressao": expr,
                    "camera": cam,
                    "props": props,
                    "sfx_depois": sfx_limpo,
                }
            )

    if len(blocos_validos) < 3:
        avisos.append("Blocos insuficientes no retorno do Gemini: blocos gerados pelo fallback deterministico.")
        blocos_validos = fallback["blocos"]

    # Garante fechamento de impacto (impacto_twist no penultimo e sussurro_twist no ultimo)
    if len(blocos_validos) >= 2:
        blocos_validos[-1]["perfil_voz"] = "sussurro_twist"
        blocos_validos[-1]["sfx_depois"] = None
        if not any(b.get("sfx_depois") == "impacto_twist" for b in blocos_validos):
            blocos_validos[-2]["sfx_depois"] = "impacto_twist"

    # Valida e normaliza 3 a 5 katana_hits ligados a palavras reais dos blocos
    hits_in = plano_bruto.get("katana_hits")
    hits_validos: list[dict] = []
    blocos_com_hit: set[int] = set()
    if isinstance(hits_in, list):
        for h in hits_in:
            if not isinstance(h, dict) or len(hits_validos) >= 5:
                continue
            try:
                b_idx = int(h.get("bloco_idx", -1))
            except (TypeError, ValueError):
                b_idx = -1
            if b_idx < 0 or b_idx >= len(blocos_validos) or b_idx in blocos_com_hit:
                continue
            linhas_raw = h.get("linhas")
            if isinstance(linhas_raw, str):
                linhas_raw = [linhas_raw]
            linhas = [
                sanitizar_texto(str(ln)).upper()[:22]
                for ln in (linhas_raw or [])
                if sanitizar_texto(str(ln))
            ][:2]
            if not linhas:
                continue
            gat_raw = re.sub(r"[^a-z0-9]", "", normalizar_texto(str(h.get("palavra_gatilho", ""))))
            tokens_bloco = [
                re.sub(r"[^a-z0-9]", "", normalizar_texto(tok))
                for tok in blocos_validos[b_idx]["texto"].split()
            ]
            tokens_bloco = [t for t in tokens_bloco if len(t) >= 2]
            if not gat_raw or not any(tb.startswith(gat_raw) for tb in tokens_bloco):
                # Tenta casar primeira palavra da linha Katana
                cand = re.sub(r"[^a-z0-9]", "", normalizar_texto(linhas[0].split()[0]))
                if cand and any(tb.startswith(cand) for tb in tokens_bloco):
                    gat_raw = cand
                elif tokens_bloco:
                    gat_raw = tokens_bloco[len(tokens_bloco) // 2]
                else:
                    continue
            cor = str(h.get("cor", "red")).strip().lower()
            if cor not in ("red", "yellow", "white"):
                cor = "red"
            try:
                dur_h = float(h.get("duracao", 0.42))
            except (TypeError, ValueError):
                dur_h = 0.42
            dur_h = round(max(0.32, min(0.50, dur_h)), 2)

            blocos_com_hit.add(b_idx)
            hid = f"hit_{len(hits_validos) + 1:02d}"
            hits_validos.append(
                {
                    "id": hid,
                    "evento": hid,
                    "bloco_idx": b_idx,
                    "palavra_gatilho": gat_raw,
                    "linhas": linhas,
                    "duracao": dur_h,
                    "cor": cor,
                }
            )

    if len(hits_validos) < 3:
        avisos.append("Menos de 3 Katana hits validos: completando automaticamente com base no roteiro.")
        hits_validos = _escolher_katana_hits(blocos_validos, total_desejado=4 if len(blocos_validos) >= 6 else 3)

    # Ordena hits cronologicamente e renumera hit_01..hit_NN
    hits_validos.sort(key=lambda x: x["bloco_idx"])
    for idx_h, h in enumerate(hits_validos, start=1):
        hid = f"hit_{idx_h:02d}"
        h["id"] = hid
        h["evento"] = hid

    return (
        {
            "titulo": titulo,
            "tema": tema,
            "palavras_chave": kws,
            "horario": horario,
            "protagonista": protagonista,
            "paleta": paleta,
            "blocos": blocos_validos,
            "katana_hits": hits_validos,
        },
        avisos,
    )


def compor_roteiro_e_cenas(
    plano: dict,
    video_id: int,
    slug: str,
    catalogo_sfx: dict[str, float],
) -> tuple[str, dict, bool]:
    """Gera o texto de roteiro_XX.txt, o dict de cenas.json (schema 6.0) e flag tem_parte_2."""
    blocos = plano["blocos"]
    hits_por_bloco: dict[int, dict] = {int(h["bloco_idx"]): h for h in plano["katana_hits"]}

    palavras_por_bloco = [len(b["texto"].split()) for b in blocos]
    total_palavras = sum(palavras_por_bloco)
    tem_parte_2 = total_palavras > LIMITE_PALAVRAS_PARTE_2

    # Escolhe posicoes ideais para [CTA_PAUSA] e (se >130 palavras) [CORTE_PARTE_2]
    acum = 0
    idx_corte: int | None = None
    if tem_parte_2 and len(blocos) >= 4:
        alvo_corte = total_palavras * 0.46
        melhor_idx = max(2, len(blocos) // 2)
        melhor_dist = float("inf")
        for i in range(1, len(blocos) - 1):
            acum += palavras_por_bloco[i - 1]
            dist = abs(acum - alvo_corte)
            if dist < melhor_dist and i >= 2 and i <= len(blocos) - 2:
                melhor_dist = dist
                melhor_idx = i
        idx_corte = melhor_idx

    # CTA fica no meio da Parte 1 (quando ha Parte 2) ou no meio da historia (Short unico)
    limite_cta = idx_corte if idx_corte is not None else len(blocos)
    palavras_p1 = sum(palavras_por_bloco[:limite_cta])
    alvo_cta = palavras_p1 * 0.52
    acum_cta = 0
    idx_cta = max(1, limite_cta // 2)
    melhor_dist_cta = float("inf")
    for i in range(1, max(2, limite_cta)):
        acum_cta += palavras_por_bloco[i - 1]
        dist = abs(acum_cta - alvo_cta)
        if dist < melhor_dist_cta:
            melhor_dist_cta = dist
            idx_cta = i
    if idx_corte is not None and idx_cta >= idx_corte:
        idx_cta = max(1, idx_corte - 1)

    linhas_rot: list[str] = [
        f'ROTEIRO {video_id:02d}: "{plano["titulo"].upper()}"',
        f"Formato: YouTube Shorts / Reels 9:16 (1080x1920) | {'Serie em 2 Partes' if tem_parte_2 else 'Short Unico'} (Motor V6.0)",
        "Gerado automaticamente por pipeline/diretor_ia.py | Player: player_universal.html + cenas.json",
        f"Protagonista: {plano['protagonista']['nome']} (jaqueta {plano['protagonista']['jaqueta']})",
        "Perfis vocais V5.1: narrador_tenso, panico, interfone_porteiro, cta_comercial, sussurro_twist.",
        "CTA dedicada: bloco [CTA_PAUSA] em tela cheia (~3.5s) no meio; zero CTA no final para loop seco.",
        "",
        "Estrutura de cada bloco:",
        "[Tempo em Segundos] | [Texto Exato da Narracao com Tags VOZ] | [Direcao visual e modulo] | [Eventos e pausas]",
        "",
        "============================================================",
        "",
        f"PARTE 1: {plano['titulo'].upper()} ({plano['horario']})",
        "",
    ]

    cenas_json_lista: list[dict] = []
    t_cursor = 0.0
    palavras_vermelhas: set[str] = {
        "sozinho", "sozinha", "escuro", "escura", "vulto", "sombra", "silencio",
        "sangue", "medo", "panico", "olhos", "sorriu", "sorri", "atras", "dentro",
        "vazio", "vazia", "ninguem", "alguem", "camera", "espelho", "porta", "travou",
    }

    for i, b in enumerate(blocos):
        if i == idx_cta:
            t0_c = int(round(t_cursor))
            t1_c = t0_c + 4
            linhas_rot.extend(
                [
                    "------------------------------------------------------------",
                    "BLOCO DEDICADO DE CTA EM TELA CHEIA NO MEIO",
                    f"[{t0_c:02d} - {t1_c:02d}] | [CTA_PAUSA] [VOZ:cta_comercial] {CTA_FALA_PADRAO} [/VOZ] [/CTA_PAUSA] | Cartao dedicado ocupando 100% da tela com pilula amarela COMENTE EU QUERO. | cta_pausa",
                    "------------------------------------------------------------",
                    "",
                ]
            )
            t_cursor += 3.8

        if idx_corte is not None and i == idx_corte:
            t_c = int(round(t_cursor))
            linhas_rot.extend(
                [
                    "============================================================",
                    f"[{t_c:02d} - {t_c:02d}] | [CORTE_PARTE_2] | Ponto de corte automatico FFmpeg entre Parte 1 e Parte 2. | corte_parte_2",
                    "============================================================",
                    "",
                    "PARTE 2: A REVELACAO",
                    "",
                ]
            )

        cena_id = f"cena_{i + 1:02d}"
        dur_est = max(2.2, len(b["texto"].split()) / 2.65)
        t0 = int(round(t_cursor))
        t1 = max(t0 + 1, int(round(t_cursor + dur_est)))
        t_cursor += dur_est

        eventos_bloco: list[str] = [cena_id]
        if i == 0:
            eventos_bloco.insert(0, "gancho")

        hit = hits_por_bloco.get(i)
        if hit is not None:
            eventos_bloco.append(f"{hit['evento']}@{hit['palavra_gatilho']}")
            palavras_vermelhas.add(hit["palavra_gatilho"])

        if i == len(blocos) - 1:
            if hit is not None:
                eventos_bloco.append(f"plot_twist@{hit['palavra_gatilho']}")
            else:
                eventos_bloco.append("plot_twist")

        if i == len(blocos) - 1:
            eventos_bloco.append("pausa=0.16")

        ev_str = ", ".join(eventos_bloco)
        perfil = b["perfil_voz"]
        direcao = f"Modulo {b['modulo']} (mood={b['mood']}, expr={b['expressao']}, cam={b['camera']})"
        linhas_rot.append(
            f"[{t0:02d} - {t1:02d}] | [VOZ:{perfil}] {b['texto']} [/VOZ] | {direcao} | {ev_str}"
        )

        sfx_dep = b.get("sfx_depois")
        # Evita colocar SFX colado exatamente antes do corte Parte 2 para manter corte limpo
        if sfx_dep and sfx_dep in catalogo_sfx:
            dur_sfx = float(catalogo_sfx[sfx_dep])
            ts0 = int(round(t_cursor))
            ts1 = max(ts0 + 1, int(round(t_cursor + dur_sfx)))
            t_cursor += dur_sfx
            linhas_rot.append(
                f"[{ts0:02d} - {ts1:02d}] | [SFX:{sfx_dep}:{dur_sfx:.1f}] | Bloco SFX puro do catalogo ({sfx_dep}). | {sfx_dep}"
            )

        cenas_json_lista.append(
            {
                "id": cena_id,
                "evento_inicio": cena_id,
                "modulo": b["modulo"],
                "mood": b["mood"],
                "expressao": b["expressao"],
                "camera": b["camera"],
                "vig": 0.72 if b["mood"] in ("red", "dark") else 0.58,
                "props": b["props"],
            }
        )

    linhas_rot.extend(
        [
            "",
            "============================================================",
            "NOTAS TECNICAS V6.0",
            f"- Palavras faladas da historia: {total_palavras} ({'com [CORTE_PARTE_2]' if tem_parte_2 else 'Short unico sem corte Parte 2'}).",
            f"- Modulos usados em cenas.json: {', '.join(c['modulo'] for c in cenas_json_lista)}.",
            f"- Katana Hits ({len(plano['katana_hits'])}): {', '.join(' / '.join(h['linhas']) for h in plano['katana_hits'])}.",
            "",
        ]
    )

    katana_saida = [
        {
            "id": h["id"],
            "evento": h["evento"],
            "palavra_gatilho": h["palavra_gatilho"],
            "linhas": h["linhas"],
            "duracao": h["duracao"],
            "cor": h["cor"],
        }
        for h in plano["katana_hits"]
    ]

    for kw in plano["palavras_chave"]:
        for tok in normalizar_texto(kw).split():
            if len(tok) >= 4:
                palavras_vermelhas.add(tok)

    cenas_json = {
        "schema_version": SCHEMA_VERSION,
        "video_id": video_id,
        "slug": slug,
        "titulo": plano["titulo"],
        "parte_label": "PARTE 1",
        "horario": plano["horario"],
        "cta_modo": "pausa_meio",
        "tem_parte_2": tem_parte_2,
        "paleta": plano["paleta"],
        "protagonista": plano["protagonista"],
        "cta": dict(CTA_PADRAO),
        "cenas": cenas_json_lista,
        "katana_hits": katana_saida,
        "palavras_vermelhas": sorted(palavras_vermelhas),
    }

    return "\n".join(linhas_rot), cenas_json, tem_parte_2


def validar_cenas_json(cenas: dict) -> list[str]:
    """Validador estrito do schema cenas.json V6.0 (retorna lista de erros; vazia = valido)."""
    erros: list[str] = []
    if not isinstance(cenas, dict):
        return ["cenas.json precisa ser um objeto JSON."]
    if cenas.get("schema_version") != SCHEMA_VERSION:
        erros.append(f"schema_version={cenas.get('schema_version')!r} (esperado {SCHEMA_VERSION!r}).")
    if not isinstance(cenas.get("video_id"), int) or cenas["video_id"] < 1:
        erros.append("video_id precisa ser inteiro >= 1.")
    if not str(cenas.get("titulo", "")).strip():
        erros.append("titulo ausente.")
    if not RE_HORARIO.fullmatch(str(cenas.get("horario", ""))):
        erros.append(f"horario invalido: {cenas.get('horario')!r}.")

    prot = cenas.get("protagonista")
    if not isinstance(prot, dict) or not RE_HEX.fullmatch(str(prot.get("jaqueta", ""))):
        erros.append("protagonista.jaqueta precisa ser cor hexadecimal #RRGGBB.")

    pal = cenas.get("paleta")
    if not isinstance(pal, dict):
        erros.append("paleta ausente.")
    else:
        for k in PALETA_PADRAO:
            if not RE_HEX.fullmatch(str(pal.get(k, ""))):
                erros.append(f"paleta.{k} invalida: {pal.get(k)!r}.")

    lista_cenas = cenas.get("cenas")
    if not isinstance(lista_cenas, list) or len(lista_cenas) < 3:
        erros.append("cenas precisa ter pelo menos 3 itens.")
    else:
        for idx, c in enumerate(lista_cenas):
            if not isinstance(c, dict):
                erros.append(f"cenas[{idx}] invalido.")
                continue
            if c.get("modulo") not in MODULOS_CENARIO:
                erros.append(f"cenas[{idx}].modulo invalido: {c.get('modulo')!r}.")
            if c.get("mood") not in MOODS_VALIDOS:
                erros.append(f"cenas[{idx}].mood invalido: {c.get('mood')!r}.")
            if c.get("expressao") not in EXPRESSOES_VALIDAS:
                erros.append(f"cenas[{idx}].expressao invalida: {c.get('expressao')!r}.")
            if not isinstance(c.get("props"), dict):
                erros.append(f"cenas[{idx}].props precisa ser objeto.")

    hits = cenas.get("katana_hits")
    if not isinstance(hits, list) or not (3 <= len(hits) <= 5):
        erros.append(f"katana_hits precisa ter entre 3 e 5 itens (recebido {len(hits) if isinstance(hits, list) else 0}).")
    else:
        for idx, h in enumerate(hits):
            if not isinstance(h, dict) or not h.get("evento") or not h.get("linhas"):
                erros.append(f"katana_hits[{idx}] incompleto.")

    return erros


def _garantir_unicidade_registro(
    dados_hist: dict,
    novo_reg: dict,
    roteiro_bruto: str,
) -> dict:
    """Garante unicidade de slug e palavras-chave contra historico sem mascarar tema duplicado."""
    slugs_existentes = {normalizar_texto(v.get("slug", "")) for v in dados_hist.get("videos", [])}
    slug = novo_reg["slug"]
    if normalizar_texto(slug) in slugs_existentes:
        slug = f"{slug}-v{novo_reg['id']:02d}"
        novo_reg["slug"] = slug

    # Evita falso positivo em palavras_chave genericas (ex.: "camera", "corredor")
    kws_anteriores = {
        normalizar_texto(k)
        for v in dados_hist.get("videos", [])
        for k in v.get("palavras_chave", [])
    }
    especificas = [k for k in novo_reg["palavras_chave"] if normalizar_texto(k) not in kws_anteriores]
    if len(especificas) < 4:
        extras = _extrair_palavras_chave(novo_reg["titulo"], roteiro_bruto, qtd=18)
        for ex in extras:
            if normalizar_texto(ex) not in kws_anteriores and ex not in especificas:
                especificas.append(ex)
            if len(especificas) >= 6:
                break
        if len(especificas) < 4:
            especificas.append(f"historia-{novo_reg['id']:02d}")
            especificas.append(slug.replace("-", " "))
        novo_reg["palavras_chave"] = especificas[:7]
    return novo_reg


def _preparar_novo_registro_historico(
    plano: dict,
    roteiro_bruto: str,
    tem_parte_2: bool,
    caminho_historico: Path = ARQUIVO_HISTORICO,
) -> tuple[int, str, dict, dict]:
    """Prepara e valida o proximo registro V6 em memoria antes de gravar qualquer arquivo."""
    dados = carregar_historico(caminho_historico)
    id_anterior = int(dados.get("video_atual") or 0)
    novo_id = proximo_numero_livre(dados)
    if novo_id <= id_anterior:
        raise RuntimeError(
            f"Falha ao incrementar episodio: novo_id={novo_id:02d} nao supera video_atual={id_anterior:02d}."
        )
    slug = gerar_slug(plano["titulo"], fallback=f"video-{novo_id:02d}")

    registro: dict = {
        "id": novo_id,
        "slug": slug,
        "titulo": plano["titulo"],
        "tema": plano["tema"],
        "palavras_chave": list(plano["palavras_chave"]),
        "roteiro": f"roteiro_{novo_id:02d}.txt",
        "cenas": "cenas.json",
        "player": "player_universal.html",
        "saida": f"output/short_{novo_id:02d}.mp4",
        "status": "em_producao",
        "motor": "v6",
        "parte_label": "PARTE 1",
        "cta_modo": "pausa_meio",
    }
    if tem_parte_2:
        registro["saidas_partes"] = [
            f"output/short_{novo_id:02d}_parte1.mp4",
            f"output/short_{novo_id:02d}_parte2.mp4",
        ]

    registro = _garantir_unicidade_registro(dados, registro, roteiro_bruto)

    copia_dados = json.loads(json.dumps(dados))
    for v_ant in copia_dados.get("videos", []):
        if str(v_ant.get("status", "")).strip() == "em_producao":
            v_ant["status"] = "arquivado"
    copia_dados["versao"] = max(int(copia_dados.get("versao", 6)), novo_id)
    copia_dados["video_atual"] = novo_id
    copia_dados["videos"].append(registro)

    # Valida regra permanente "Sempre Video Novo" antes de gravar!
    validar_historico(copia_dados)
    return novo_id, registro["slug"], registro, copia_dados


def _validar_texto_roteiro_gerado(texto_roteiro: str, tem_parte_2: bool) -> list[str]:
    """Confere marcadores obrigatorios V5.2/V6 e ausencia de emoji/travessao antes de salvar."""
    erros: list[str] = []
    if "[VOZ:" not in texto_roteiro:
        erros.append("roteiro gerado sem tags [VOZ:perfil].")
    if "[CTA_PAUSA]" not in texto_roteiro or "COMENTE EU QUERO" not in texto_roteiro.upper():
        erros.append("roteiro gerado sem bloco obrigatorio [CTA_PAUSA] / COMENTE EU QUERO.")
    if tem_parte_2 and "[CORTE_PARTE_2]" not in texto_roteiro:
        erros.append("roteiro longo sem marcador obrigatorio [CORTE_PARTE_2].")
    if RE_EMOJI.search(texto_roteiro):
        erros.append("roteiro gerado contem emoji proibido.")
    if "\u2014" in texto_roteiro or "\u2013" in texto_roteiro:
        erros.append("roteiro gerado contem travessao (em-dash/en-dash) proibido.")
    return erros


def registrar_novo_video_historico(
    plano: dict,
    roteiro_bruto: str,
    tem_parte_2: bool,
    caminho_historico: Path = ARQUIVO_HISTORICO,
    salvar: bool = True,
) -> tuple[int, str, dict]:
    """Cria o proximo registro V6 em historico_videos.json e valida Sempre Video Novo."""
    novo_id, slug, registro, copia_dados = _preparar_novo_registro_historico(
        plano=plano,
        roteiro_bruto=roteiro_bruto,
        tem_parte_2=tem_parte_2,
        caminho_historico=caminho_historico,
    )
    if salvar:
        caminho_historico.write_text(
            json.dumps(copia_dados, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return novo_id, slug, registro


def produzir_direcao_v6(
    roteiro_bruto: str | None = None,
    titulo: str | None = None,
    usar_mock: bool = False,
    gerar_inedito: bool = False,
    exigir_gemini: bool = False,
    modelo: str = GEMINI_MODELO_PADRAO,
    caminho_historico: Path = ARQUIVO_HISTORICO,
    dir_saida: Path = RAIZ,
    atualizar_historico: bool = True,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Executa o fluxo completo do Diretor IA V6 e grava roteiro_XX.txt, cenas.json e historico."""
    carregar_env()
    catalogo_sfx = carregar_catalogo_sfx()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if exigir_gemini:
        if usar_mock:
            raise RuntimeError("Modo --mock e incompativel com --exigir-gemini.")
        api_key = validar_gemini_api_key(api_key)
    elif api_key and not usar_mock:
        api_key = validar_gemini_api_key(api_key)

    avisos: list[str] = []
    titulo_efetivo = titulo
    texto_entrada = str(roteiro_bruto or "").strip()
    veio_de_inedito = False
    modelo_ativo_ref: dict[str, str] = {}

    if gerar_inedito or not texto_entrada:
        dados_hist = carregar_historico(caminho_historico)
        veio_de_inedito = True
        if usar_mock or not api_key:
            if not usar_mock and not api_key:
                avisos.append("GEMINI_API_KEY ausente: gerando episodio inedito deterministico offline.")
            titulo_gerado, texto_entrada = gerar_roteiro_inedito_mock(dados_hist, titulo_sugerido=titulo)
        else:
            titulo_gerado, texto_entrada = gerar_roteiro_inedito_gemini(
                dados_hist,
                titulo_sugerido=titulo,
                api_key=api_key,
                modelo=modelo,
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
            )
        titulo_efetivo = titulo or titulo_gerado

    limpo_in = sanitizar_texto(texto_entrada)
    if len(limpo_in.split()) < 15:
        raise ValueError("Roteiro bruto muito curto (minimo 15 palavras para gerar Short V6).")

    origem = "mock"
    plano_bruto: dict | None = None

    if usar_mock or not api_key:
        if not usar_mock and not api_key:
            avisos.append("GEMINI_API_KEY ausente: usando modo deterministico offline.")
        plano_bruto = diretor_mock_deterministico(limpo_in, titulo_forcado=titulo_efetivo, catalogo_sfx=catalogo_sfx)
        origem = "mock_inedito" if veio_de_inedito else "mock"
    else:
        try:
            plano_bruto = chamar_gemini_diretor(
                limpo_in,
                titulo_sugerido=titulo_efetivo,
                api_key=api_key,
                catalogo_sfx=catalogo_sfx,
                modelo=modelo_ativo_ref.get("modelo", modelo),
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
            )
            modelo_usado = modelo_ativo_ref.get("modelo", modelo)
            origem = f"gemini_inedito:{modelo_usado}" if veio_de_inedito else f"gemini:{modelo_usado}"
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, RuntimeError, ValueError, TimeoutError) as exc:
            if exigir_gemini:
                raise RuntimeError(
                    f"Falha no Gemini Diretor IA em modo --exigir-gemini ({type(exc).__name__}: {exc})."
                ) from exc
            avisos.append(f"Falha no Gemini ({type(exc).__name__}: {exc}): fallback deterministico ativado.")
            plano_bruto = diretor_mock_deterministico(
                limpo_in, titulo_forcado=titulo_efetivo, catalogo_sfx=catalogo_sfx
            )
            origem = "fallback_mock"

    plano, avisos_val = validar_e_corrigir_plano(plano_bruto, limpo_in, titulo_efetivo, catalogo_sfx)
    avisos.extend(avisos_val)

    total_palavras = sum(len(b["texto"].split()) for b in plano["blocos"])
    tem_parte_2 = total_palavras > LIMITE_PALAVRAS_PARTE_2

    # Valida integralmente historico, roteiro e cenas.json em memoria antes de gravar qualquer arquivo
    video_id, slug, registro, copia_historico = _preparar_novo_registro_historico(
        plano=plano,
        roteiro_bruto=limpo_in,
        tem_parte_2=tem_parte_2,
        caminho_historico=caminho_historico,
    )

    texto_roteiro, cenas_json, tem_parte_2 = compor_roteiro_e_cenas(
        plano, video_id=video_id, slug=slug, catalogo_sfx=catalogo_sfx
    )
    erros_schema = validar_cenas_json(cenas_json)
    if erros_schema:
        raise RuntimeError(f"cenas.json gerado falhou na validacao de schema: {erros_schema}")
    erros_rot = _validar_texto_roteiro_gerado(texto_roteiro, tem_parte_2=tem_parte_2)
    if erros_rot:
        raise RuntimeError(f"roteiro_{video_id:02d}.txt falhou na validacao de contrato: {erros_rot}")

    dir_saida.mkdir(parents=True, exist_ok=True)
    roteiro_path = dir_saida / f"roteiro_{video_id:02d}.txt"
    cenas_path = dir_saida / "cenas.json"
    roteiro_path.write_text(texto_roteiro, encoding="utf-8")
    cenas_path.write_text(json.dumps(cenas_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if atualizar_historico:
        caminho_historico.write_text(
            json.dumps(copia_historico, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "origem": origem,
        "video_id": video_id,
        "slug": slug,
        "titulo": plano["titulo"],
        "palavras_historia": total_palavras,
        "tem_parte_2": tem_parte_2,
        "roteiro_path": roteiro_path,
        "cenas_path": cenas_path,
        "registro": registro,
        "cenas": cenas_json,
        "avisos": avisos,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diretor IA V6: cria episodio inedito ou converte roteiro bruto em roteiro_XX.txt, cenas.json e historico."
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--roteiro-texto", type=str, help="Texto bruto do roteiro em linha de comando.")
    grupo.add_argument("--arquivo", type=Path, help="Caminho de arquivo .txt com o roteiro bruto.")
    grupo.add_argument(
        "--gerar-inedito",
        action="store_true",
        help="Cria automaticamente um roteiro 100%% inedito via Gemini evitando temas do historico_videos.json.",
    )
    parser.add_argument("--titulo", type=str, default=None, help="Titulo opcional do video.")
    parser.add_argument(
        "--modelo",
        type=str,
        default=GEMINI_MODELO_PADRAO,
        help=f"Modelo Gemini preferido (padrao: {GEMINI_MODELO_PADRAO}; com fallback automatico).",
    )
    parser.add_argument("--mock", action="store_true", help="Executa em modo deterministico offline sem chamar a API.")
    parser.add_argument(
        "--exigir-gemini",
        action="store_true",
        help="Falha explicitamente se GEMINI_API_KEY estiver ausente ou a chamada Gemini falhar (proibe fallback silencioso).",
    )
    parser.add_argument(
        "--nao-atualizar-historico",
        action="store_true",
        help="Gera arquivos de teste sem sobrescrever historico_videos.json.",
    )
    args = parser.parse_args()

    texto_bruto: str | None = None
    if args.arquivo is not None:
        arq = args.arquivo if args.arquivo.is_absolute() else (RAIZ / args.arquivo)
        if not arq.is_file():
            raise SystemExit(f"Arquivo de roteiro nao encontrado: {arq}")
        texto_bruto = arq.read_text(encoding="utf-8")
    elif args.roteiro_texto is not None:
        texto_bruto = args.roteiro_texto

    res = produzir_direcao_v6(
        roteiro_bruto=texto_bruto,
        titulo=args.titulo,
        usar_mock=args.mock,
        gerar_inedito=args.gerar_inedito,
        exigir_gemini=args.exigir_gemini,
        modelo=args.modelo,
        atualizar_historico=not args.nao_atualizar_historico,
    )

    for av in res["avisos"]:
        print(f"AVISO Diretor IA: {av}", flush=True)

    cenas = res["cenas"]
    modulos = ", ".join(c["modulo"] for c in cenas["cenas"])
    hits = ", ".join(" ".join(h["linhas"]) for h in cenas["katana_hits"])
    print(
        f"Diretor IA V6 concluido ({res['origem']}): Video {res['video_id']:02d} '{res['titulo']}' "
        f"[slug={res['slug']}, palavras={res['palavras_historia']}, "
        f"{'Parte 1 + Parte 2' if res['tem_parte_2'] else 'Short unico'}]"
    )
    print(f"  Roteiro: {res['roteiro_path']}")
    print(f"  Cenas:   {res['cenas_path']} (schema v{cenas['schema_version']}, {len(cenas['cenas'])} cenas)")
    print(f"  Modulos: {modulos}")
    print(f"  Katana:  {hits}")


if __name__ == "__main__":
    main()
