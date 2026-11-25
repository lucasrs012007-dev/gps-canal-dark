"""Estacao 1 (Motor V8.0 Cinematografico IA 30fps): Diretor IA de cortes rapidos (3s-4s).

Aceita texto livre (`--roteiro-texto`, `--arquivo`) OU geracao 100% autonoma (`--gerar-inedito`),
gerando automaticamente:
1. Novo registro inedito em `historico_videos.json` (motor="cinematografico_ia_30fps",
   cta_modo="final" e saidas_partes quando > 130 palavras).
2. `roteiro_XX.txt` pronto para a Estacao 2 (tags [VOZ:perfil], [SFX:...], gancho/CTA curto
   de 1 frase apenas no final sem pausa comercial no meio, e [CORTE_PARTE_2] acima de 130 palavras).
3. `cenas.json` (schema versionado "8.0", validado e auto-corrigido em Python) com 14 a 18 cenas
   curtas (1 corte visual a cada 3s-4s) e campo obrigatorio `prompt_imagem` em ingles descrevendo
   LITERALMENTE o objeto/cena exata daquela fala com estilo 3D cinematografico UE5 consistente.

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

from pipeline.config_canal import (  # noqa: E402
    carregar_config_canal,
    obter_perfil_idioma,
)
from pipeline.gemini_pool import (  # noqa: E402
    GROQ_API_URL,
    GROQ_MODELO_PADRAO,
    MODELOS_TEXTO_GEMINI_PADRAO,
    GeminiPool,
    carregar_chaves_gemini,
    eh_erro_chave_invalida,
    eh_erro_cota_diaria,
    eh_erro_modelo_indisponivel,
    obter_groq_api_key,
)
from pipeline.historico import (  # noqa: E402
    ARQUIVO_HISTORICO,
    _similares,
    carregar_historico,
    normalizar_texto,
    proximo_numero_livre,
    tokens_tema,
    validar_historico,
)

SCHEMA_VERSION = "8.0"
MOTOR_RENDER_PADRAO = "cinematografico_ia_30fps"
GEMINI_MODELO_PADRAO = MODELOS_TEXTO_GEMINI_PADRAO[0]
GEMINI_MODELOS_FALLBACK: tuple[str, ...] = MODELOS_TEXTO_GEMINI_PADRAO
ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_CATALOGO_SFX = RAIZ / "assets" / "sfx" / "catalogo.json"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
LIMITE_PALAVRAS_PARTE_2 = 130
MAX_PALAVRAS_POR_TOMADA = 13
PALAVRAS_POR_SEGUNDO_EST = 2.95

CONFIG_CANAL: dict = {}
CANAL_NOME: str = "E Se Você?"
IDIOMA_CANAL: str = "pt-BR"
IDIOMA_HUMANO: str = "português do Brasil"
CTA_FINAL_PADRAO: str = "E você, o que faria nessa situação, me conta aqui nos comentários?"
ESTILO_VISUAL_PROMPT_IMAGEM: str = (
    "hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, "
    "Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, "
    "no text, no letters, no watermark"
)
PILARES_EDITORIAIS: tuple[dict[str, str], ...] = ()
PILARES_POR_ID: dict[str, dict[str, str]] = {}


def recarregar_config_canal(caminho: Path | str | None = None) -> dict:
    """Recarrega config_canal.json e atualiza constantes globais do Diretor IA."""
    global CONFIG_CANAL, CANAL_NOME, IDIOMA_CANAL, IDIOMA_HUMANO
    global CTA_FINAL_PADRAO, ESTILO_VISUAL_PROMPT_IMAGEM, PILARES_EDITORIAIS, PILARES_POR_ID

    cfg = carregar_config_canal(caminho)
    perfil_idioma = obter_perfil_idioma(cfg["idioma"])

    CONFIG_CANAL = cfg
    CANAL_NOME = str(cfg["nome_canal"])
    IDIOMA_CANAL = str(perfil_idioma["codigo"])
    IDIOMA_HUMANO = str(perfil_idioma["nome_humano"])
    CTA_FINAL_PADRAO = str(cfg["cta_final"])
    ESTILO_VISUAL_PROMPT_IMAGEM = str(cfg["estilo_visual_prompt"])
    PILARES_EDITORIAIS = tuple(dict(p) for p in cfg["pilares_editoriais"])
    PILARES_POR_ID = {p["id"]: p for p in PILARES_EDITORIAIS}
    return cfg


recarregar_config_canal()

CENARIOS_ANIMADOS: tuple[str, ...] = (
    "oceano_ilha",
    "espaco_orbita",
    "cidade_rua",
    "floresta_noite",
    "laboratorio",
    "ceu_nuvens",
    "escritorio",
    "sala_cozinha",
    "arena_comparacao",
    "big_face",
)
MODULOS_CENARIO: tuple[str, ...] = CENARIOS_ANIMADOS

ACOES_CENA_VALIDAS: tuple[str, ...] = (
    "barco_navegando",
    "chuva_flechas",
    "helicoptero_sobrevoando",
    "onda_gigante",
    "radar_alerta",
    "corrida_fuga",
    "flutuando_gravidade",
    "explosao_choque",
    "contador_escala",
    "investigando_pista",
)

POSES_VALIDAS: tuple[str, ...] = (
    "em_pe",
    "falando",
    "apontando",
    "assustado",
    "pensando",
    "correndo",
    "pulando",
    "flutuando",
    "caindo",
    "comemorando",
)

PROPS_FLUTUANTES_VALIDOS: tuple[str, ...] = (
    "lapiseira",
    "xicara_cafe",
    "cadeiras",
    "silhuetas_janela",
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
EXPRESSOES_VALIDAS: tuple[str, ...] = ("neutral", "worry", "shock", "fear", "smug", "focus")
CAMERAS_VALIDAS: tuple[str, ...] = (
    "push_in",
    "pull_out",
    "pan_diag_tl",
    "pan_diag_br",
    "pan_left",
    "pan_right",
    "shake_impact",
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


PT_ACENTOS_EXATOS: dict[str, str] = {
    "voce": "você", "voces": "vocês", "nao": "não", "mao": "mão", "maos": "mãos",
    "pes": "pés", "direcao": "direção", "direcoes": "direções", "levitacao": "levitação",
    "levitaçao": "levitação", "escritorio": "escritório", "escritorios": "escritórios",
    "xicara": "xícara", "xicaras": "xícaras", "cafe": "café", "cafes": "cafés",
    "chao": "chão", "panico": "pânico", "pulmao": "pulmão", "pulmoes": "pulmões",
    "ceu": "céu", "ceus": "céus", "balao": "balão", "baloes": "balões",
    "comeca": "começa", "comecam": "começam", "comecou": "começou", "armario": "armário",
    "armarios": "armários", "movimentacao": "movimentação", "caotica": "caótica",
    "caotico": "caótico", "vidraca": "vidraça", "forca": "força", "ja": "já",
    "so": "só", "ate": "até", "entao": "então", "tambem": "também",
    "ninguem": "ninguém", "alguem": "alguém", "atras": "atrás", "silencio": "silêncio",
    "escuridao": "escuridão", "camera": "câmera", "cameras": "câmeras", "relogio": "relógio",
    "oxigenio": "oxigênio", "cerebro": "cérebro", "pressao": "pressão", "explosoes": "explosões",
    "ligacao": "ligação", "notificacao": "notificação", "coracao": "coração",
    "respiracao": "respiração", "gravacao": "gravação", "estacao": "estação",
    "atencao": "atenção", "decisao": "decisão", "revelacao": "revelação",
    "comunicacao": "comunicação", "situacao": "situação", "sensacao": "sensação",
    "sao": "são", "estao": "estão", "alivio": "alívio", "ultimo": "último", "ultima": "última",
    "unico": "único", "unica": "única", "numero": "número", "proximo": "próximo",
    "proxima": "próxima", "rapido": "rápido", "rapida": "rápida", "automatico": "automático",
    "automatica": "automática", "eletrico": "elétrico", "eletronico": "eletrônico",
    "metalico": "metálico", "subterraneo": "subterrâneo", "terreo": "térreo",
    "espaco": "espaço", "braco": "braço", "bracos": "braços", "cabeca": "cabeça",
    "baba": "babá", "berco": "berço", "macaneta": "maçaneta", "historia": "história",
    "misterio": "mistério", "cenario": "cenário", "cenarios": "cenários", "fenomeno": "fenômeno",
    "hipotetico": "hipotético", "hipoteticos": "hipotéticos", "emergencia": "emergência",
    "visao": "visão", "presenca": "presença", "video": "vídeo", "videos": "vídeos",
    "audio": "áudio", "predio": "prédio", "tunel": "túnel", "vagao": "vagão",
    "aviao": "avião", "metro": "metrô", "horario": "horário", "apos": "após",
    "la": "lá", "ha": "há", "porem": "porém", "alem": "além", "atraves": "através",
    "dioxido": "dióxido", "vigesima": "vigésima", "valvula": "válvula", "oceanico": "oceânico",
    "biologico": "biológico", "agencias": "agências", "satelites": "satélites",
    "estacoes": "estações", "hidrofones": "hidrofones", "acustica": "acústica",
    "artico": "Ártico", "autorizacao": "autorização", "milhao": "milhão", "milhoes": "milhões",
    "funcionarios": "funcionários", "ficcao": "ficção", "cientifica": "científica",
}

RE_PALAVRA_PT = re.compile(r"[A-Za-zÀ-ÿ]+")


def _preservar_caixa(orig: str, alvo: str) -> str:
    if orig.isupper():
        return alvo.upper()
    if orig[:1].isupper() and orig[1:].islower():
        return alvo[:1].upper() + alvo[1:]
    return alvo


def restaurar_acentos_ptbr(texto: str) -> str:
    """Preserva UTF-8 completo e restaura acentos inequivocos em pt-BR caso venham omitidos."""
    bruto = unicodedata.normalize("NFC", str(texto or ""))
    if not bruto:
        return ""

    def _sub(match: re.Match[str]) -> str:
        palavra = match.group(0)
        low = palavra.lower()
        alvo = PT_ACENTOS_EXATOS.get(low)
        if alvo is None:
            if low.endswith("çao") and len(low) > 3:
                alvo = low[:-3] + "ção"
            elif low.endswith("çoes") and len(low) > 4:
                alvo = low[:-4] + "ções"
        return _preservar_caixa(palavra, alvo) if alvo else palavra

    return RE_PALAVRA_PT.sub(_sub, bruto)


def texto_indica_gravidade_zero(texto: str) -> bool:
    norm = normalizar_texto(texto)
    termos = (
        "gravidade", "flutua", "flutuam", "flutuando", "flutuar", "levita", "levitar",
        "levitacao", "sem peso", "peso zero", "leveza", "perderam o contato",
        "subindo aos ceus", "subindo como baloes", "baloes soltos", "despenca",
        "queda livre", "caindo", "teto de gesso", "sai do chao",
    )
    return any(t in norm for t in termos)


def texto_indica_escritorio(texto: str) -> bool:
    norm = normalizar_texto(texto)
    termos = (
        "escritorio", "teto de gesso", "piso acarpetado", "acarpetado", "carpete",
        "monitor", "monitores", "computador", "lapiseira", "xicara de cafe",
        "andar inteiro", "janelas de vidro", "vidraca", "cadeiras", "armarios",
        "predio comercial", "mesa de trabalho", "baia", "reuniao", "colegas",
    )
    return any(t in norm for t in termos)


def texto_indica_vulto(texto: str) -> bool:
    norm = normalizar_texto(texto)
    termos = (
        "vulto", "sombra", "silhueta atras", "alguem atras", "atras de voce",
        "atras da porta", "olhos no escuro", "invasor", "sorrindo", "sorriu",
        "espelho", "reflexo", "encara", "baba eletronica", "guarda roupa",
        "lado de fora", "olhando pra lente", "olhando para a lente",
    )
    return any(t in norm for t in termos)


def inferir_pose_por_texto(
    texto: str,
    modulo: str,
    perfil: str,
    gravidade_zero: bool = False,
) -> str:
    norm = normalizar_texto(texto)
    if any(k in norm for k in ("despenca", "queda livre", "caindo", "direcao ao chao", "chao de concreto", "cai com toda")):
        return "caindo"
    if any(k in norm for k in ("segurar na mesa", "segura na mesa", "agarrar na mesa", "agarra a mesa", "pes ja perderam", "perderam o contato")):
        return "segurando_mesa"
    if any(k in norm for k in ("flutua", "flutuam", "flutuando", "flutuar", "levita", "levitar", "levitacao", "teto de gesso", "leveza", "centro da sala", "subindo", "contra as janelas")):
        return "flutuando"
    if gravidade_zero and modulo in ("escritorio", "sala_cozinha"):
        return "flutuando"
    if perfil == "panico":
        return "panic"
    if modulo == "celular_notificacao":
        return "phone"
    if "corredor" in norm or "andando" in norm or "caminh" in norm:
        return "walk"
    return "idle"


def inferir_props_flutuantes(
    texto: str,
    objeto_atual: str = "",
    gravidade_zero: bool = False,
) -> list[str]:
    norm_txt = normalizar_texto(texto)
    norm_obj = normalizar_texto(objeto_atual)
    norm_all = f"{norm_txt} {norm_obj}".strip()
    itens: list[str] = []
    if any(k in norm_all for k in ("lapiseira", "caneta", "lapis", "papel", "folha")):
        itens.append("lapiseira")
    if any(k in norm_all for k in ("xicara", "cafe", "caneca", "gotas", "esferas")):
        itens.append("xicara_cafe")
    if any(k in norm_all for k in ("cadeira", "cadeiras", "armario", "armarios", "empilhando", "teto de gesso", "mesa", "andar inteiro")):
        itens.append("cadeiras")
    if any(k in norm_txt for k in ("janela", "janelas", "vidraca", "vidro", "horizonte", "pedestres", "carros", "baloes", "ceus", "silhueta", "lado de fora")):
        itens.append("silhuetas_janela")
    if gravidade_zero and not itens:
        itens = ["lapiseira", "xicara_cafe", "cadeiras"]
    return itens


def inferir_modulo_por_texto(
    texto: str,
    idx: int,
    total: int,
    contexto_global: str = "",
) -> str:
    """Seleciona um dos 10 modulos visuais do player_universal.html conforme pistas do texto."""
    norm = normalizar_texto(texto)
    ctx_escritorio = texto_indica_escritorio(contexto_global) if contexto_global else False
    ctx_zero_g = texto_indica_gravidade_zero(contexto_global) if contexto_global else False

    if idx == total - 1 and total >= 3:
        if any(k in norm for k in ("olho", "olhos", "escuro", "blecaute", "apagou", "apaga", "sombra", "sorri", "atras")):
            return "blecaute_olhos"
        if ctx_escritorio and any(k in norm for k in ("despenca", "queda", "chao", "concreto", "gravidade")):
            return "escritorio"
        if ctx_zero_g and any(k in norm for k in ("despenca", "queda", "chao", "gravidade")):
            return "escritorio" if ctx_escritorio else "big_face"
        return "blecaute_olhos" if idx % 2 == 1 else "big_face"
    if idx == total - 2 and total >= 4:
        if any(k in norm for k in ("contador", "mente", "choque", "gelou", "congelou", "grito", "arrepio", "panico", "coracao", "rosto", "pavor")) and not any(k in norm for k in ("janela", "vidraca", "cadeira", "teto", "lapiseira")):
            return "big_face"

    regras: list[tuple[str, tuple[str, ...]]] = [
        ("escritorio", ("escritorio", "teto de gesso", "acarpetado", "carpete", "lapiseira", "xicara de cafe", "monitores", "computador", "andar inteiro", "janelas de vidro", "vidraca", "cadeiras", "armarios", "reuniao", "colegas")),
        ("celular_notificacao", ("celular", "mensagem", "notificacao", "whatsapp", "tela", "ligacao", "chamada", "audio", "foto", "sms", "vibra", "vibrou", "toca", "tocou", "alerta", "sinal", "radio")),
        ("camera_cctv", ("camera", "cctv", "gravacao", "gravando", "lente", "baba eletronica", "portaria", "vigilancia", "filmando", "satelite", "radar", "arquivo", "cientista", "laboratorio", "expedicao", "ilha", "oceano", "deserto")),
        ("elevador_cabine", ("elevador", "subsolo", "botoeira", "espelho", "cabine", "terreo", "submarino", "capsula", "bunker", "cofre", "teleferico", "sala branca")),
        ("carro_noite", ("carro", "estrada", "rodovia", "gps", "farol", "volante", "motorista", "retrovisor", "asfalto", "pista", "freio", "aviao", "navio", "trem", "metro", "vagao")),
        ("corredor_escuro", ("corredor", "escada", "passos", "hall", "porta", "macaneta", "fechadura", "batida", "batendo", "tunel", "caverna", "subterraneo", "ruina")),
        ("quarto_noturno", ("quarto", "cama", "travesseiro", "cobertor", "guarda roupa", "acorda", "acordou", "dormindo", "cortina", "hotel")),
        ("sala_cozinha", ("cozinha", "sofa", "geladeira", "televisao", "tv", "sacola", "apartamento", "casa")),
        ("big_face", ("congelou", "gelou", "coracao", "suor", "olhou", "rosto", "respiracao", "panico", "medo", "cerebro", "mente", "oxigenio", "pressao", "pulmoes", "contador")),
        ("blecaute_olhos", ("blecaute", "breu", "apagao", "escuridao", "olhos", "vulto", "sombra", "silencio", "vazio")),
    ]
    melhor_mod = "escritorio" if ctx_escritorio else "quarto_noturno"
    melhor_score = 0
    for mod, termos in regras:
        score = sum(1 for termo in termos if termo in norm)
        if score > melhor_score:
            melhor_score = score
            melhor_mod = mod
    if melhor_score > 0:
        if ctx_escritorio and melhor_mod in ("carro_noite", "sala_cozinha") and not any(k in norm for k in ("volante", "estrada", "rodovia", "motorista", "cozinha", "geladeira", "sofa")):
            return "escritorio"
        return melhor_mod

    if ctx_escritorio:
        return "escritorio"
    ciclo = ("quarto_noturno", "corredor_escuro", "sala_cozinha", "escritorio", "big_face", "blecaute_olhos")
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


def _eh_bloco_cta_final(texto: str) -> bool:
    """Identifica se o bloco final ja e um gancho/CTA curto de 1 frase no finalzinho do video."""
    limpo = sanitizar_texto(texto)
    palavras = limpo.split()
    if not palavras or len(palavras) > 26:
        return False
    norm = normalizar_texto(limpo)
    marcadores = (
        "comenta",
        "comente",
        "comentario",
        "comentarios",
        "me diz",
        "me conta",
        "conta ai",
        "diz ai",
        "o que voce faria",
        "voce aguentaria",
        "voce teria coragem",
        "voce encararia",
        "segue",
        "siga",
        "curte",
        "curta",
        "salva esse",
        "manda pra",
        "eu quero",
    )
    return any(m in norm for m in marcadores)


_NUMEROS_EXTENSO_PT: dict[str, int] = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12,
    "quinze": 15, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "cem": 100, "cento": 100, "duzentos": 200, "trezentos": 300,
    "quinhentos": 500, "mil": 1000,
}

_CENARIO_ALIASES: dict[str, str] = {
    "quarto_noturno": "sala_cozinha",
    "corredor_escuro": "cidade_rua",
    "celular_notificacao": "sala_cozinha",
    "camera_cctv": "laboratorio",
    "elevador_cabine": "escritorio",
    "carro_noite": "cidade_rua",
    "blecaute_olhos": "big_face",
}

_POSE_ALIASES: dict[str, str] = {
    "idle": "em_pe",
    "standing": "em_pe",
    "parado": "em_pe",
    "speaking": "falando",
    "talking": "falando",
    "pointing": "apontando",
    "press": "apontando",
    "reach": "apontando",
    "phone": "falando",
    "panic": "assustado",
    "scared": "assustado",
    "segurando_mesa": "assustado",
    "thinking": "pensando",
    "walk": "correndo",
    "walking": "correndo",
    "running": "correndo",
    "jumping": "pulando",
    "floating": "flutuando",
    "levitando": "flutuando",
    "falling": "caindo",
    "queda": "caindo",
    "celebrating": "comemorando",
}

_EXPR_ALIASES: dict[str, str] = {
    "sinister_smile": "smug",
    "scared": "fear",
    "panico": "shock",
    "focused": "focus",
    "focado": "focus",
    "serio": "focus",
    "confiante": "smug",
}

_CAM_ALIASES: dict[str, str] = {
    "tight_close": "shake_impact",
    "wide_still": "float_cam",
    "zoom_in": "push_in",
    "zoom_out": "pull_out",
}


def _normalizar_hud_raw(hud_raw: object) -> dict | None:
    if not isinstance(hud_raw, dict):
        return None
    rotulo = restaurar_acentos_ptbr(sanitizar_texto(str(hud_raw.get("rotulo", ""))))[:28].upper()
    valor = restaurar_acentos_ptbr(sanitizar_texto(str(hud_raw.get("valor", ""))))[:22].upper()
    if not rotulo or not valor:
        return None
    try:
        prog = float(hud_raw.get("progresso", 0.72))
    except (TypeError, ValueError):
        prog = 0.72
    prog = round(max(0.05, min(1.0, prog)), 2)
    return {"rotulo": rotulo, "valor": valor, "progresso": prog}


def extrair_hud_dado(texto: str, hud_raw: object = None) -> dict | None:
    """Extrai medidor/contador animado (rotulo, valor, progresso) sempre que a fala citar dados numericos."""
    valido = _normalizar_hud_raw(hud_raw)
    if valido is not None:
        return valido

    limpo = sanitizar_texto(texto)
    norm = normalizar_texto(limpo)

    # 1. Porcentagens (ex.: 90%, 99,5%, 50 por cento)
    m_pct = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:%|por\s+cento\b)", limpo, flags=re.IGNORECASE)
    if m_pct:
        num_s = m_pct.group(1).replace(",", ".")
        try:
            num_f = float(num_s)
        except ValueError:
            num_f = 50.0
        val_txt = m_pct.group(1).replace(".", ",") + "%"
        return {"rotulo": "TAXA / ÍNDICE", "valor": val_txt, "progresso": round(max(0.08, min(1.0, num_f / 100.0)), 2)}

    # 2. Velocidades (ex.: 120 km/h)
    m_vel = re.search(r"(\d+(?:[.,]\d+)?)\s*(km/h|m/s|quil[oô]metros\s+por\s+hora)", limpo, flags=re.IGNORECASE)
    if m_vel:
        num_s = m_vel.group(1).replace(",", ".")
        num_f = float(num_s) if num_s.replace(".", "", 1).isdigit() else 100.0
        unid = "M/S" if "m/s" in m_vel.group(2).lower() else "KM/H"
        return {"rotulo": "VELOCIDADE", "valor": f"{m_vel.group(1)} {unid}", "progresso": round(max(0.15, min(1.0, num_f / 300.0)), 2)}

    # 3. Distancias (ex.: 5 km, 300 metros, 2600 quilometros)
    m_dist = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(km|quil[oô]metros?|metros?|m\b|milhas?)",
        limpo,
        flags=re.IGNORECASE,
    )
    if m_dist:
        num_str = m_dist.group(1)
        unid_raw = m_dist.group(2).lower()
        unid = "KM" if ("km" in unid_raw or "quil" in unid_raw) else ("MILHAS" if "milha" in unid_raw else "M")
        rot = "ZONA PROIBIDA" if any(k in norm for k in ("proibid", "ilha", "exclusao", "limite", "perimetro")) else (
            "PROFUNDIDADE" if any(k in norm for k in ("profund", "submarino", "fundo", "oceano", "abismo")) else "DISTÂNCIA"
        )
        try:
            num_f = float(num_str.replace(",", "."))
        except ValueError:
            num_f = 5.0
        prog = min(1.0, max(0.25, num_f / (10.0 if num_f <= 10 else (500.0 if num_f <= 500 else 5000.0))))
        return {"rotulo": rot, "valor": f"{num_str} {unid}", "progresso": round(prog, 2)}

    # 4. Anos (ex.: 2004, 2006, 1997)
    m_ano = re.search(r"\b(19\d{2}|20\d{2})\b", limpo)
    if m_ano:
        ano = int(m_ano.group(1))
        rot = "TSUNAMI" if "tsunami" in norm else (
            "RESGATE / CASO" if any(k in norm for k in ("pescador", "helicoptero", "resgate", "barco")) else "REGISTRO OFICIAL"
        )
        prog = round(max(0.20, min(0.98, (ano - 1950) / 80.0)), 2)
        return {"rotulo": rot, "valor": str(ano), "progresso": prog}

    # 5. Temperaturas (ex.: -18 graus, 6 graus)
    m_temp = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:°c|graus?(?:\s+negativos?)?)", limpo, flags=re.IGNORECASE)
    if m_temp:
        neg = "negativo" in m_temp.group(0).lower() and not m_temp.group(1).startswith("-")
        val_t = f"-{m_temp.group(1)} °C" if neg else f"{m_temp.group(1)} °C"
        return {"rotulo": "TEMPERATURA", "valor": val_t, "progresso": 0.78}

    # 6. Duracoes (ex.: 48 horas, 60 segundos, 30 dias, 40 minutos)
    m_dur = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(segundos?|minutos?|horas?|dias?|anos?)",
        limpo,
        flags=re.IGNORECASE,
    )
    if m_dur:
        num_str = m_dur.group(1)
        unid = m_dur.group(2).upper()
        rot = "OXIGÊNIO" if "oxigenio" in norm else ("CONTAGEM" if "segundo" in unid.lower() else "TEMPO")
        try:
            num_f = float(num_str.replace(",", "."))
        except ValueError:
            num_f = 30.0
        prog = round(max(0.20, min(0.95, num_f / (60.0 if num_f <= 60 else 120.0))), 2)
        return {"rotulo": rot, "valor": f"{num_str} {unid}", "progresso": prog}

    # 7. Grandes escalas / quantias (ex.: 10 milhoes, 1 milhao, 5 mil)
    m_esc = re.search(r"(\d+(?:[.,]\d+)?)\s*(milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil)\b", limpo, flags=re.IGNORECASE)
    if m_esc:
        return {"rotulo": "ESCALA", "valor": f"{m_esc.group(1)} {m_esc.group(2).upper()}", "progresso": 0.86}

    # 8. Numeros por extenso comuns com unidade (ex.: "cinco quilometros", "quarenta e oito horas", "trezentos metros")
    m_ext = re.search(
        r"\b(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|doze|quinze|vinte|trinta|quarenta|cinquenta|sessenta|cem|cento|duzentos|trezentos|quinhentos|mil)\b"
        r"(?:\s+e\s+(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|vinte|trinta|quarenta|cinquenta|sessenta|oitenta|noventa))?"
        r"\s+(quilometros?|metros?|horas?|minutos?|segundos?|dias?|anos?|graus?|milhoes?|milhao|bilhoes?)",
        norm,
    )
    if m_ext:
        n1 = _NUMEROS_EXTENSO_PT.get(m_ext.group(1), 0)
        n2 = _NUMEROS_EXTENSO_PT.get(m_ext.group(2) or "", 0)
        total_n = n1 + n2
        unid_raw = m_ext.group(3)
        if total_n > 0:
            if "quilometro" in unid_raw:
                unid_fmt, rot = "KM", ("ZONA PROIBIDA" if "proibid" in norm or "ilha" in norm else "DISTÂNCIA")
            elif "metro" in unid_raw:
                unid_fmt, rot = "M", ("PROFUNDIDADE" if "profund" in norm or "submarino" in norm else "ESCALA")
            elif "grau" in unid_raw:
                sinal = "-" if "negativo" in norm else ""
                return {"rotulo": "TEMPERATURA", "valor": f"{sinal}{total_n} °C", "progresso": 0.76}
            elif "milh" in unid_raw:
                unid_fmt, rot = "MILHÕES", "ESCALA"
            elif "bilh" in unid_raw:
                unid_fmt, rot = "BILHÕES", "ESCALA"
            else:
                unid_fmt = unid_raw.upper()
                rot = "OXIGÊNIO" if "oxigenio" in norm else "CONTAGEM"
            prog = round(max(0.22, min(0.95, total_n / (10.0 if total_n <= 10 else (100.0 if total_n <= 100 else 500.0)))), 2)
            return {"rotulo": rot, "valor": f"{total_n} {unid_fmt}", "progresso": prog}

    return None


def inferir_cenario_animado(
    texto: str,
    idx: int,
    total: int,
    *,
    anterior: str = "",
    contexto_global: str = "",
    hud_dado: dict | None = None,
    eh_cta: bool = False,
    eh_twist: bool = False,
) -> str:
    """Escolhe o cenario 2D animado exato para a fala atual, sem nunca repetir o cenario anterior."""
    norm = normalizar_texto(texto)
    norm_g = normalizar_texto(contexto_global)

    if eh_cta:
        for cand in ("big_face", "arena_comparacao", "cidade_rua"):
            if cand != anterior:
                return cand

    pontos: dict[str, float] = {c: 0.0 for c in CENARIOS_ANIMADOS}

    regras: dict[str, tuple[tuple[str, ...], float]] = {
        "oceano_ilha": (
            ("ilha", "sentinela", "mar", "oceano", "barco", "pescador", "tsunami", "onda", "navio", "submarino", "costa", "praia", "agua", "pacifico", "ponto nemo", "marinha", "casco", "escotilha"),
            4.0,
        ),
        "espaco_orbita": (
            ("espaco", "orbita", "planeta", "terra", "lua", "marte", "satelite", "asteroide", "estrela", "estacao espacial", "nave", "galaxia", "universo", "foguete", "gravidade zero", "cosmo"),
            4.2,
        ),
        "ceu_nuvens": (
            ("ceu", "nuvem", "nuvens", "aviao", "helicoptero", "sobrevo", "voar", "voando", "altitude", "tempestade", "raio", "trov", "paraquedas", "teleferico", "atmosfera", "helice", "resgate aereo"),
            4.0,
        ),
        "floresta_noite": (
            ("floresta", "mata", "selva", "arvore", "arvores", "tribo", "flecha", "flechas", "arco", "lanca", "trilha", "neblina", "animais", "caverna", "ilha fechada", "escuro na mata", "vagalume"),
            4.0,
        ),
        "laboratorio": (
            ("laboratorio", "cientista", "ciencia", "experimento", "radar", "sonar", "microfone", "hidrofone", "sensor", "estudo", "pesquisa", "dna", "cerebro", "cofre", "semente", "svalbard", "radio", "sinal", "camera", "protocolo", "governo", "arquivo", "satelite militar"),
            3.8,
        ),
        "cidade_rua": (
            ("cidade", "rua", "avenida", "predio", "transito", "metro", "vagao", "tunel", "estacao", "carro", "estacionamento", "ponte", "sirene", "policia", "hotel", "hospital", "pedagio", "corredor", "apartamento"),
            3.8,
        ),
        "escritorio": (
            ("escritorio", "monitor", "monitores", "mesa", "computador", "teclado", "lapiseira", "xicara", "teto de gesso", "carpete", "chefe", "empresa", "reuniao", "andar comercial", "cadeira"),
            3.9,
        ),
        "sala_cozinha": (
            ("casa", "cozinha", "sala", "quarto", "porta", "sofa", "geladeira", "cama", "espelho", "janela de casa", "apartamento", "celular", "interfone", "baba eletronica"),
            3.6,
        ),
        "arena_comparacao": (
            ("comparacao", "vezes maior", "escala", "quilometro", "metros", "milhoes", "bilhoes", "por cento", "recorde", "ranking", "velocidade", "temperatura", "profundidade", "distancia", "limite", "perimetro"),
            3.4,
        ),
        "big_face": (
            ("coracao", "panico", "susto", "terror", "olhos", "sem piscar", "sorrindo", "atras de voce", "voce paralisa", "silencio", "ninguem voltou", "nunca mais", "revelacao", "choque", "medo"),
            3.2,
        ),
    }

    for cen, (termos, peso) in regras.items():
        for termo in termos:
            if termo in norm:
                pontos[cen] += peso
            elif termo in norm_g:
                pontos[cen] += peso * 0.18

    if hud_dado is not None:
        pontos["arena_comparacao"] += 2.2
        pontos["laboratorio"] += 0.9
    if eh_twist:
        pontos["big_face"] += 4.5
    elif idx == max(1, total - 3):
        pontos["big_face"] += 2.0

    # Ordena por pontuacao mantendo determinismo e proibindo repetir o cenario anterior
    ordenados = sorted(
        CENARIOS_ANIMADOS,
        key=lambda c: (pontos[c], -abs((CENARIOS_ANIMADOS.index(c) - idx) % len(CENARIOS_ANIMADOS))),
        reverse=True,
    )
    for cand in ordenados:
        if cand != anterior and pontos[cand] > 0.2:
            return cand

    # Rotacao tematica limpa caso a frase seja puramente narrativa/transicional
    ciclo_fallback = (
        "oceano_ilha", "laboratorio", "cidade_rua", "arena_comparacao",
        "ceu_nuvens", "floresta_noite", "espaco_orbita", "big_face",
        "escritorio", "sala_cozinha",
    )
    for offset in range(len(ciclo_fallback)):
        cand = ciclo_fallback[(idx + offset) % len(ciclo_fallback)]
        if cand != anterior:
            return cand
    return "big_face" if anterior != "big_face" else "laboratorio"


def inferir_acao_cena(
    texto: str,
    cenario: str,
    *,
    hud_dado: dict | None = None,
    gravidade_zero: bool = False,
) -> str:
    """Seleciona a animacao especifica da fala (acao_cena) dentre as 10 acoes canonicas."""
    norm = normalizar_texto(texto)
    if any(k in norm for k in ("flecha", "flechas", "arco", "lanca", "ataque", "atiram", "dispar")):
        return "chuva_flechas"
    if any(k in norm for k in ("tsunami", "onda gigante", "onda enorme", "mare", "inund")):
        return "onda_gigante"
    if any(k in norm for k in ("helicoptero", "helice", "sobrevo", "resgate aereo", "aviao")):
        return "helicoptero_sobrevoando"
    if any(k in norm for k in ("radar", "sonar", "alerta", "zona", "perimetro", "fronteira", "sinal", "microfone", "hidrofone", "sensor")):
        return "radar_alerta"
    if any(k in norm for k in ("barco", "navio", "pescador", "submarino", "naveg", "deriva")):
        return "barco_navegando"
    if gravidade_zero or any(k in norm for k in ("flutu", "levit", "gravidade", "orbita", "sem peso", "espaco", "satelite")):
        return "flutuando_gravidade"
    if any(k in norm for k in ("explos", "choque", "impacto", "colis", "despenca", "queda", "raio", "estrondo", "bateu", "susto")):
        return "explosao_choque"
    if any(k in norm for k in ("corr", "fuga", "fugir", "escap", "persegu", "apressad")):
        return "corrida_fuga"
    if hud_dado is not None or cenario == "arena_comparacao":
        return "contador_escala"
    if cenario == "oceano_ilha":
        return "barco_navegando"
    if cenario == "espaco_orbita":
        return "flutuando_gravidade"
    if cenario == "ceu_nuvens":
        return "helicoptero_sobrevoando"
    if cenario == "laboratorio":
        return "radar_alerta"
    if cenario == "big_face":
        return "explosao_choque"
    return "investigando_pista"


def inferir_pose_animada(
    texto: str,
    cenario: str,
    acao_cena: str,
    perfil: str,
    *,
    gravidade_zero: bool = False,
    eh_cta: bool = False,
) -> str:
    """Seleciona uma das 10 poses animadas coerente com a fala e acao da cena."""
    norm = normalizar_texto(texto)
    if eh_cta:
        return "apontando"
    if any(k in norm for k in ("despenca", "queda livre", "caindo", "caiu", "direcao ao chao")):
        return "caindo"
    if gravidade_zero or acao_cena == "flutuando_gravidade" or any(k in norm for k in ("flutu", "levit", "gravidade", "orbita")):
        return "flutuando"
    if acao_cena == "corrida_fuga" or any(k in norm for k in ("correu", "corre", "correndo", "fuga", "fugir", "escap")):
        return "correndo"
    if any(k in norm for k in ("pulou", "pula", "salta", "saltou", "pular")):
        return "pulando"
    if any(k in norm for k in ("venceu", "sobreviveu", "conseguiu", "comemor", "milhoes", "premio")):
        return "comemorando"
    if perfil == "panico" or acao_cena in ("chuva_flechas", "onda_gigante", "explosao_choque") or any(k in norm for k in ("panico", "medo", "susto", "terror", "choque", "assust", "perigo")):
        return "assustado"
    if acao_cena in ("contador_escala", "radar_alerta") or cenario == "arena_comparacao":
        return "apontando"
    if any(k in norm for k in ("misterio", "ninguem sabe", "sem explicacao", "pergunta", "sera que", "pensa", "imagine")):
        return "pensando"
    return "falando"


def inferir_expressao_animada(
    texto: str,
    perfil: str,
    acao_cena: str,
    *,
    eh_twist: bool = False,
    eh_cta: bool = False,
) -> str:
    """Seleciona uma das 6 expressoes canonicas (neutral, worry, shock, fear, smug, focus)."""
    norm = normalizar_texto(texto)
    if eh_cta:
        return "smug"
    if eh_twist or acao_cena in ("explosao_choque", "onda_gigante"):
        return "shock"
    if perfil == "panico" or acao_cena in ("chuva_flechas", "corrida_fuga") or any(k in norm for k in ("panico", "medo", "assust", "terror", "perigo", "morre")):
        return "fear"
    if acao_cena in ("radar_alerta", "contador_escala", "investigando_pista"):
        return "focus"
    if any(k in norm for k in ("erro", "cuidado", "aviso", "problema", "proibid", "silencio", "estranho")):
        return "worry"
    if any(k in norm for k in ("segredo", "truque", "ninguem sabia", "verdade")):
        return "smug"
    return "focus" if perfil == "sussurro_twist" else "neutral"


def escolher_camera_alternada(
    sugestao: str | None,
    acao_cena: str,
    cenario: str,
    idx: int,
    anterior: str = "",
    *,
    mood: str = "navy",
) -> str:
    """Alterna continuamente entre movimentos cinematograficos sem repetir duas cenas seguidas."""
    cand = _CAM_ALIASES.get(str(sugestao or "").strip().lower(), str(sugestao or "").strip().lower())
    if cand in CAMERAS_VALIDAS and cand != anterior:
        return cand

    if (
        mood == "red"
        or acao_cena in ("explosao_choque", "chuva_flechas", "onda_gigante")
    ) and anterior != "shake_impact":
        return "shake_impact"

    ciclo = ("push_in", "pan_diag_tl", "pull_out", "pan_right", "pan_diag_br", "pan_left", "shake_impact")
    for offset in range(len(ciclo)):
        c = ciclo[(idx + offset) % len(ciclo)]
        if c != anterior:
            return c
    return "push_in" if anterior != "push_in" else "pull_out"


def garantir_estilo_prompt_imagem(prompt_en: str) -> str:
    """Garante estilo cinematografico UE5 vertical 9:16 sem texto ou marca d'agua no prompt_imagem."""
    base = sanitizar_texto(prompt_en)
    base = re.sub(r"\s+", " ", base).strip(" ,.;:")
    estilo = ESTILO_VISUAL_PROMPT_IMAGEM.strip()
    base_low = base.lower()
    if "unreal engine 5" in base_low and "no watermark" in base_low and "9:16" in base_low:
        return base
    # Remove sufixos antigos parciais para nao duplicar
    base = re.sub(
        r",?\s*(?:stylized 2\.5d|hyper-detailed 3d)[^.]{0,180}(?:watermark|framing|composition)\b",
        "",
        base,
        flags=re.IGNORECASE,
    ).strip(" ,.;:")
    if not base:
        return f"Dark cinematic atmospheric suspense scene with dramatic volumetric light, {estilo}"
    return f"{base}, {estilo}"


_REGRAS_PROMPT_LITERAL: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("pedagio", "cabine de pedagio", "cancela", "guiche"),
        "Isolated highway toll booth enveloped in dense nocturnal fog, flickering sodium overhead lamp, wet black asphalt and glowing red barrier arm",
    ),
    (
        ("nota de vinte", "nota de 20", "nota suja", "dinheiro", "cedula", "lama", "mao palida"),
        "Extreme close-up of a pale cold hand emerging from shadow holding a crumpled muddy banknote smeared with wet dark dirt, dramatic rim light on fingers",
    ),
    (
        ("submarino", "escotilha", "profundidade", "casco de aco", "lastro", "valvula"),
        "Claustrophobic steel submarine interior flooded in crimson emergency alert lights, riveted metal hatch, condensation droplets and glowing pressure gauges",
    ),
    (
        ("ilha", "sentinela", "praia", "coqueiro", "tribo", "flecha", "flechas", "arco"),
        "Forbidden dark tropical island shrouded in storm mist rising from rough midnight ocean waves, dense shadowy jungle shoreline and wooden boat at a distance",
    ),
    (
        ("tsunami", "onda gigante", "mare", "oceano", "mar", "ponto nemo", "pacifico", "navio"),
        "Towering dark ocean swell under lightning-lit storm clouds, turbulent sea spray and deep abyssal blue water seen from a dramatic low angle",
    ),
    (
        ("helicoptero", "helice", "sobrevo", "resgate aereo", "holofote"),
        "Dark rescue helicopter hovering through heavy storm clouds at night, slicing volumetric white searchlight beam piercing rain and fog below",
    ),
    (
        ("satelite", "orbita", "estacao espacial", "espaco", "planeta", "lua", "asteroide"),
        "Dramatic orbital view of Earth dark terminator line from space, sleek metallic satellite drifting above glowing cyan atmosphere and deep starfield",
    ),
    (
        ("cofre", "svalbard", "gelo", "artico", "geleira", "montanha congelada", "neve"),
        "Massive brutalist concrete vault entrance embedded into a frozen Arctic snow mountain at twilight, icy fog drifting around glowing security beacons",
    ),
    (
        ("metro", "vagao", "tunel", "trilhos", "estacao fechada", "letreiro"),
        "Empty late-night subway train car stalled inside a dark subterranean tunnel, flickering cold fluorescent overhead tubes and eerie reflections in black windows",
    ),
    (
        ("elevador", "subsolo", "botoeira", "terreo", "andar"),
        "Dimly lit metallic elevator cabin with glowing red floor indicator panel, reflections on scratched steel doors and uneasy shadows in corners",
    ),
    (
        ("carro", "estrada", "rodovia", "farol", "volante", "retrovisor", "asfalto", "motorista"),
        "Interior POV of a car driving along a misty empty night highway, rain beads on the windshield, dim dashboard glow and eerie rearview mirror reflection",
    ),
    (
        ("interfone", "portaria", "celular", "mensagem", "notificacao", "ligacao", "tela", "whatsapp"),
        "Tight macro close-up of a glowing smartphone screen illuminating a tense face in a pitch-dark room, cold cyan screen light and deep shadows",
    ),
    (
        ("camera", "cctv", "vigilancia", "monitor", "laboratorio", "cientista", "radar", "sonar", "hidrofone", "semente"),
        "Dark high-tech monitoring laboratory with glowing oscilloscope monitors, sweeping green radar display and flickering security camera feeds",
    ),
    (
        ("espelho", "reflexo", "banheiro", "vidro", "sorrindo", "sorriu"),
        "Chilling close-up of a dimly lit foggy mirror reflecting an unsettling silhouette standing just behind the viewer in shadow",
    ),
    (
        ("floresta", "mata", "selva", "arvore", "neblina", "trilha", "caverna"),
        "Dense nocturnal forest trail shrouded in cold silver mist, towering dark pine silhouettes and a single flashlight beam cutting through fog",
    ),
    (
        ("escritorio", "lapiseira", "xicara", "cafe", "teto de gesso", "gravidade", "flutua", "levita"),
        "Modern glass skyscraper office at night with floating chairs, suspended coffee droplets and glowing computer monitors drifting in zero gravity",
    ),
    (
        ("porta", "macaneta", "fechadura", "corredor", "hall", "hotel", "hospital", "quarto", "cama"),
        "Long eerie dimly lit night corridor leading to a slightly ajar dark wooden door, cold rim light spilling across the empty floor",
    ),
)

_ENQUADRAMENTOS_CENA: tuple[str, ...] = (
    "dramatic wide establishing shot",
    "tight cinematic close-up shot",
    "low-angle atmospheric shot looking up",
    "over-the-shoulder suspenseful framing",
    "macro detail shot with shallow depth of field",
    "high-contrast dutch-angle cinematic shot",
)


def gerar_prompt_imagem_literal(
    texto: str,
    titulo: str,
    idx: int,
    total: int,
    *,
    mood: str = "navy",
    prompts_usados: set[str] | None = None,
) -> str:
    """Gera prompt em ingles literal e unico baseado diretamente nos elementos concretos da frase."""
    norm = normalizar_texto(texto)
    norm_all = normalizar_texto(f"{texto} {titulo}")

    desc_base = ""
    melhor_score = 0
    for termos, descricao in _REGRAS_PROMPT_LITERAL:
        score = sum(3 for termo in termos if termo in norm) + sum(1 for termo in termos if termo in norm_all)
        if score > melhor_score:
            melhor_score = score
            desc_base = descricao

    if not desc_base:
        desc_base = (
            "Suspenseful dark atmospheric scene illustrating an eerie real-world mystery, "
            "dramatic mist, sharp silhouette and rich environmental textures"
        )

    # Enriquecimento literal de detalhes concretos mencionados na frase
    extras: list[str] = []
    if any(k in norm for k in ("neblina", "nevoa", "fumaca")):
        extras.append("thick drifting volumetric fog")
    if any(k in norm for k in ("chuva", "molhad", "tempestade", "raio")):
        extras.append("rain streaks reflecting cold light on wet surfaces")
    if any(k in norm for k in ("vermelh", "alerta", "emergencia", "panico", "sirene")) or mood == "red":
        extras.append("intense crimson emergency accent light cutting through deep dark shadows")
    elif mood == "yellow":
        extras.append("warm amber tungsten beam contrasting against cold midnight blue shadows")
    else:
        extras.append("cold cyan volumetric rim light and deep abyssal blue shadows")
    if any(k in norm for k in ("olhos", "olhou", "olhando", "encara", "rosto", "pavor", "choque")):
        extras.append("expressive intense gaze catching dramatic specular highlights")
    if any(k in norm for k in ("mao", "maos", "dedo", "segura", "gira", "puxa")):
        extras.append("tactile foreground focus on trembling hands interacting with the object")
    if idx == total - 1:
        extras.append("lingering eerie wide composition inviting the viewer into the mystery")

    enquadramento = _ENQUADRAMENTOS_CENA[idx % len(_ENQUADRAMENTOS_CENA)]
    candidato = f"{enquadramento}, {desc_base}, {', '.join(extras)}"

    if prompts_usados is not None:
        chave = candidato.lower()
        if chave in prompts_usados:
            var_angulos = (
                "from an alternate side perspective with foreground depth",
                "from a tighter intense telephoto angle",
                "from a dramatic overhead surveillance perspective",
                "with dramatic backlit mist and sharp rim highlights",
            )
            candidato = f"{candidato}, {var_angulos[idx % len(var_angulos)]}"
        prompts_usados.add(candidato.lower())

    return garantir_estilo_prompt_imagem(candidato)


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


def _dividir_fala_em_tomadas_curtas(
    texto: str,
    max_palavras: int = MAX_PALAVRAS_POR_TOMADA,
) -> list[str]:
    """Divide qualquer fala > ~4s (> max_palavras) em 2 ou 3 tomadas visuais curtas e naturais."""
    limpo = sanitizar_texto(texto)
    if not limpo:
        return []
    palavras = limpo.split()
    if len(palavras) <= max_palavras:
        return [limpo]

    # 1. Primeiro divide por frases completas (. ! ?)
    frases = [f.strip() for f in RE_SEPARAR_FRASES.split(limpo) if f.strip()]
    resultado: list[str] = []
    conjuncoes = frozenset({"e", "mas", "quando", "porque", "onde", "enquanto", "entao", "ate", "como", "que", "so"})

    for frase in frases:
        pals = frase.split()
        if len(pals) <= max_palavras:
            resultado.append(frase)
            continue

        # 2. Divide frase longa em 2 ou 3 tomadas respeitando virgulas/ponto-e-virgula ou conjuncoes
        num_partes = 3 if len(pals) > max_palavras * 2 else 2
        alvo = max(5, round(len(pals) / num_partes))
        cursor = 0
        for p_idx in range(num_partes):
            if cursor >= len(pals):
                break
            if p_idx == num_partes - 1:
                trecho = " ".join(pals[cursor:]).strip()
                if trecho:
                    resultado.append(trecho)
                break
            fim_ideal = min(len(pals) - 4, cursor + alvo)
            if fim_ideal <= cursor + 3:
                trecho = " ".join(pals[cursor:]).strip()
                if trecho:
                    resultado.append(trecho)
                break

            # Procura melhor ponto de corte proximo a fim_ideal (virgula/dois-pontos ou conjuncao)
            melhor_corte = fim_ideal
            melhor_dist = 999
            janela_ini = max(cursor + 4, fim_ideal - 4)
            janela_fim = min(len(pals) - 3, fim_ideal + 4)
            for k in range(janela_ini, janela_fim + 1):
                tok_ant = pals[k - 1]
                tok_atu = normalizar_texto(pals[k])
                dist = abs(k - fim_ideal)
                if tok_ant.endswith((",", ";", ":")):
                    if dist < melhor_dist:
                        melhor_dist = dist
                        melhor_corte = k
                elif tok_atu in conjuncoes and (dist + 1) < melhor_dist:
                    melhor_dist = dist + 1
                    melhor_corte = k

            trecho = " ".join(pals[cursor:melhor_corte]).strip()
            if trecho:
                resultado.append(trecho)
            cursor = melhor_corte

    # Reagrupa fragmentos minusculos (< 4 palavras) ao vizinho quando possivel
    compactado: list[str] = []
    for seg in resultado:
        if compactado and len(seg.split()) < 4 and len(compactado[-1].split()) + len(seg.split()) <= max_palavras + 3:
            compactado[-1] = f"{compactado[-1]} {seg}".strip()
        else:
            compactado.append(seg)
    return compactado or [limpo]


def _dividir_em_blocos_narrativos(roteiro_bruto: str) -> list[str]:
    """Divide o roteiro em tomadas visuais rapidas (1 corte a cada 3s-4s, ~14 a 18 cenas em 60s)."""
    limpo = sanitizar_texto(roteiro_bruto)
    frases = [f.strip() for f in RE_SEPARAR_FRASES.split(limpo) if f.strip()]
    if not frases:
        raise ValueError("Roteiro bruto vazio apos sanitizacao.")

    tomadas: list[str] = []
    for f in frases:
        for sub in _dividir_fala_em_tomadas_curtas(f, max_palavras=MAX_PALAVRAS_POR_TOMADA):
            sub_limpo = sub.strip()
            if not sub_limpo:
                continue
            if not sub_limpo.endswith((".", "!", "?", ",", ";", ":")):
                sub_limpo = sub_limpo + "."
            tomadas.append(sub_limpo)

    # Se houver frases muito curtas seguidas (< 6 palavras) e total > 18, une pares contiguos
    # mantendo o limite <= 13 palavras (~4s) e preservando twist e CTA final intactos
    if len(tomadas) > 18:
        preservar_fim = 2 if len(tomadas) >= 4 and _eh_bloco_cta_final(tomadas[-1]) else 1
        corpo = tomadas[:-preservar_fim]
        finais = tomadas[-preservar_fim:]
        unidas: list[str] = []
        for seg in corpo:
            if (
                unidas
                and len(unidas) + (len(corpo) - len(unidas)) > 16
                and len(unidas[-1].split()) + len(seg.split()) <= MAX_PALAVRAS_POR_TOMADA
            ):
                unidas[-1] = f"{unidas[-1]} {seg}".strip()
            else:
                unidas.append(seg)
        tomadas = unidas + finais

    # Se o roteiro for muito curto e gerar menos de 4 tomadas, subdivide a maior
    total_palavras = sum(len(t.split()) for t in tomadas)
    min_tomadas = 4 if total_palavras >= 28 else 3
    while len(tomadas) < min_tomadas:
        idx_maior = max(range(len(tomadas)), key=lambda i: len(tomadas[i].split()))
        pals = tomadas[idx_maior].split()
        if len(pals) < 6:
            break
        meio = len(pals) // 2
        p1 = " ".join(pals[:meio]).strip()
        p2 = " ".join(pals[meio:]).strip()
        if not p1.endswith((".", "!", "?", ",")):
            p1 += ","
        if p2 and not p2.endswith((".", "!", "?")):
            p2 += "."
        tomadas = tomadas[:idx_maior] + [p1, p2] + tomadas[idx_maior + 1 :]

    return tomadas


def _escolher_katana_hits(blocos: list[dict], total_desejado: int = 4) -> list[dict]:
    """Seleciona 3 a 5 palavras de impacto reais presentes nos blocos para destaque vermelho."""
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
        palavra_upper = restaurar_acentos_ptbr(escolhida).upper()
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
    """Modo deterministico offline (--mock e fallback de seguranca do Gemini) com cortes 3s-4s."""
    catalogo = catalogo_sfx or carregar_catalogo_sfx()
    limpo = restaurar_acentos_ptbr(sanitizar_texto(roteiro_bruto))
    blocos_txt = _dividir_em_blocos_narrativos(limpo)
    if not blocos_txt or not _eh_bloco_cta_final(blocos_txt[-1]):
        blocos_txt.append(CTA_FINAL_PADRAO)

    horario = extrair_horario(limpo)
    nome_prot = extrair_nome_protagonista(limpo)
    ctx_zero_g = texto_indica_gravidade_zero(limpo)

    if titulo_forcado and sanitizar_texto(titulo_forcado):
        titulo = restaurar_acentos_ptbr(sanitizar_texto(titulo_forcado))[:72]
    else:
        primeiras = blocos_txt[0].rstrip(".!?,").split()
        titulo = " ".join(primeiras[:6]).strip() or "Suspense da Madrugada"
        titulo = titulo[0].upper() + titulo[1:]

    cor_idx = abs(sum(ord(c) for c in titulo)) % len(PALETA_JAQUETAS)
    jaq, jaq_s, jaq_e = PALETA_JAQUETAS[cor_idx]
    protagonista_cfg = {
        "nome": nome_prot,
        "jaqueta": jaq,
        "jaqueta_sombra": jaq_s,
        "jaqueta_escura": jaq_e,
        "pele": "#E0B292",
        "cabelo": "#141720",
    }

    idx_twist = len(blocos_txt) - 2 if len(blocos_txt) >= 3 and _eh_bloco_cta_final(blocos_txt[-1]) else len(blocos_txt) - 1
    tema = restaurar_acentos_ptbr(
        sanitizar_texto(blocos_txt[0] + " " + (blocos_txt[idx_twist] if idx_twist > 0 else ""))
    )[:180]
    palavras_chave = _extrair_palavras_chave(titulo, limpo, qtd=7)

    n = len(blocos_txt)
    blocos: list[dict] = []
    ultimo_cenario = ""
    ultima_camera = ""
    prompts_usados: set[str] = set()

    for i, txt in enumerate(blocos_txt):
        norm = normalizar_texto(txt)
        eh_final_cta = (i == n - 1) and _eh_bloco_cta_final(txt)
        eh_twist = i == idx_twist

        grav_zero = (not eh_final_cta) and (texto_indica_gravidade_zero(txt) or (ctx_zero_g and i >= 1))

        cenario = inferir_cenario_animado(
            txt,
            i,
            n,
            anterior=ultimo_cenario,
            contexto_global=limpo,
            hud_dado=None,
            eh_cta=eh_final_cta,
            eh_twist=eh_twist,
        )
        ultimo_cenario = cenario

        acao_cena = inferir_acao_cena(
            txt,
            cenario,
            hud_dado=None,
            gravidade_zero=grav_zero,
        )

        if eh_final_cta:
            perfil = "narrador_tenso"
            mood = "navy"
        elif eh_twist:
            perfil = "sussurro_twist"
            mood = "red"
        elif any(k in norm for k in ("ligacao", "chamada", "telefone", "na linha", "celular")) and (":" in txt or '"' in txt):
            perfil = "voz_telefone"
            mood = "violet"
        elif any(k in norm for k in ("interfone", "porteiro")) and (":" in txt or '"' in txt):
            perfil = "interfone_porteiro"
            mood = "violet"
        elif i >= max(1, int(idx_twist * 0.65)) or any(k in norm for k in ("panico", "correu", "corre", "desesper", "grito", "travou", "bateu", "esmag", "coracao", "despenca", "flecha", "tsunami")):
            perfil = "panico"
            mood = "red" if (i >= max(1, idx_twist - 3) or acao_cena in ("chuva_flechas", "onda_gigante", "explosao_choque")) else "violet"
        else:
            perfil = "narrador_tenso"
            mood = "yellow" if acao_cena == "radar_alerta" else ("navy" if i % 2 == 0 else "violet")

        pose = inferir_pose_animada(
            txt,
            cenario,
            acao_cena,
            perfil,
            gravidade_zero=grav_zero,
            eh_cta=eh_final_cta,
        )
        expr = inferir_expressao_animada(
            txt,
            perfil,
            acao_cena,
            eh_twist=eh_twist,
            eh_cta=eh_final_cta,
        )
        cam = escolher_camera_alternada(None, acao_cena, cenario, i, anterior=ultima_camera, mood=mood)
        ultima_camera = cam

        prompt_imagem = gerar_prompt_imagem_literal(
            texto=txt,
            titulo=titulo,
            idx=i,
            total=n,
            mood=mood,
            prompts_usados=prompts_usados,
        )

        blocos.append(
            {
                "perfil_voz": perfil,
                "texto": txt,
                "prompt_imagem": prompt_imagem,
                "cenario": cenario,
                "modulo": cenario,
                "acao_cena": acao_cena,
                "pose": pose,
                "mood": mood,
                "expressao": expr,
                "camera": cam,
                "sfx_depois": None,
            }
        )

    # Insere 1 a 2 SFX diegeticos no meio + obrigatoriamente impacto_twist antes do bloco de twist
    sfx_colocados = 0
    for idx_b in range(1, max(1, idx_twist)):
        if sfx_colocados >= 2:
            break
        sfx_cand = inferir_sfx_para_texto(blocos[idx_b]["texto"], catalogo)
        if sfx_cand and sfx_cand != "impacto_twist":
            blocos[idx_b]["sfx_depois"] = sfx_cand
            sfx_colocados += 1
    if idx_twist >= 1:
        blocos[idx_twist - 1]["sfx_depois"] = "impacto_twist"

    blocos_historia = blocos[: idx_twist + 1] if idx_twist >= 2 else blocos
    katana_hits = _escolher_katana_hits(blocos_historia, total_desejado=4 if len(blocos_historia) >= 6 else 3)

    return {
        "titulo": titulo,
        "tema": tema,
        "palavras_chave": palavras_chave,
        "horario": horario,
        "protagonista": protagonista_cfg,
        "paleta": dict(PALETA_PADRAO),
        "blocos": blocos,
        "katana_hits": katana_hits,
    }


def _montar_prompt_gemini(
    roteiro_bruto: str,
    titulo_sugerido: str | None,
    sfx_validos: list[str],
    pilar: dict[str, str] | None = None,
) -> str:
    titulo_hint = f"Título sugerido pelo usuário: {titulo_sugerido}\n" if titulo_sugerido else ""
    pilar_hint = (
        f"Pilar editorial deste episódio: {pilar['nome']} (id={pilar['id']}).\n"
        if pilar is not None
        else ""
    )
    horario_ex = pilar["horario_padrao"] if pilar is not None else "23:18"
    resumo_pilares = ", ".join(p["nome"] for p in PILARES_EDITORIAIS)
    return (
        f"Você é o Diretor Cinematográfico de Cortes Rápidos do canal '{CANAL_NOME}' "
        f"(YouTube Shorts / Reels em {IDIOMA_CANAL}: {resumo_pilares}).\n"
        "Transforme o roteiro bruto abaixo em um plano JSON estrito de ALTÍSSIMA RETENÇÃO com 1 corte visual novo a cada 3 a 4 segundos.\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. ZERO emoji e ZERO travessão (em-dash ou en-dash) em qualquer texto.\n"
        f"2. ORTOGRAFIA COMPLETA EM {IDIOMA_HUMANO.upper()} (UTF-8): preserve TODOS os acentos, cedilhas e números/anos inteiros "
        "(ex.: 2004, 2006, 5 km, 20 reais, você, não, mão, pés, direção). Nunca remova acentos nem altere palavras do roteiro.\n"
        "3. CORTES RÁPIDOS DE 3 A 4 SEGUNDOS (14 A 18 CENAS POR VÍDEO DE 60s): divida automaticamente qualquer fala longa "
        "(com mais de 12 palavras / 4 segundos) em 2 ou 3 tomadas visuais curtas consecutivas (7 a 12 palavras por bloco), "
        "mantendo o texto falado fluido e natural sem pausas artificiais.\n"
        "4. ZERO CTA NO MEIO: PROIBIDO inserir pausa comercial, propaganda ou CTA no meio do vídeo. "
        "Deixe APENAS um gancho/CTA curto de 1 única frase como último bloco.\n"
        "5. PROMPT DE IMAGEM LITERAL E CINEMATOGRÁFICO EM INGLÊS (`prompt_imagem`) PARA CADA CENA:\n"
        "   - Descreva LITERALMENTE o objeto, ambiente, ação e ângulo de câmera exatos do que está sendo dito naquela frase "
        "(ex.: se a frase fala de cabine de pedágio na neblina, descreva a cabine de pedágio na neblina com luz de sódio; "
        "se fala de uma mão pálida entregando uma nota de 20 reais suja de lama, descreva um close extremo da mão pálida segurando a nota suja de lama).\n"
        "   - NUNCA use descrições genéricas repetidas nem peça texto/letras/números desenhados dentro da imagem.\n"
        "   - Evite palavras que disparem filtros de segurança (evite 'blood', 'corpse', 'gore', 'murder', 'dead body'; "
        "use equivalentes cinematográficos atmosféricos como 'eerie shadow', 'crimson reflection', 'abandoned scene', 'mysterious silhouette').\n"
        f"   - TERMINE TODO `prompt_imagem` com exatamente este estilo consistente: \"{ESTILO_VISUAL_PROMPT_IMAGEM}\".\n"
        "6. CAMPOS DE CADA BLOCO EM `blocos`:\n"
        f"   - perfil_voz: um de {list(PERFIS_VOZ)} (mantenha 'narrador_tenso' na maior parte para preservar a voz contínua do Gemini TTS; use 'sussurro_twist' na revelação final; NUNCA use 'cta_comercial').\n"
        "   - texto: trecho curto falado (7 a 12 palavras) preservando 100% do sentido do roteiro.\n"
        "   - prompt_imagem: descrição visual LITERAL em inglês + estilo cinematográfico travado acima.\n"
        f"   - camera: um de {list(CAMERAS_VALIDAS)} (use 'shake_impact' em cenas de tensão/clímax; NUNCA repita a mesma câmera em duas cenas seguidas).\n"
        f"   - mood: um de {list(MOODS_VALIDOS)} ('red' para tensão/clímax, 'navy'/'violet'/'yellow' para suspense).\n"
        f"   - sfx_depois: null ou um de {sfx_validos} (coloque 'impacto_twist' imediatamente antes do bloco da revelação final; máximo 3 SFX no total).\n"
        "7. katana_hits: lista de 3 a 5 palavras de impacto reais do roteiro (MAIÚSCULAS com acento UTF-8) para destaque vermelho nas legendas.\n"
        f"8. horario: string HH:MM coerente com o episódio (ex.: '{horario_ex}').\n"
        "9. Responda APENAS com JSON válido no formato:\n"
        "{\n"
        '  "titulo": "...",\n'
        '  "tema": "resumo curto em 1 frase",\n'
        '  "palavras_chave": ["kw1", "kw2", "kw3", "kw4", "kw5"],\n'
        f'  "horario": "{horario_ex}",\n'
        '  "protagonista": {"nome": "Você", "jaqueta": "#0F766E", "pele": "#E0B292", "cabelo": "#141720"},\n'
        '  "paleta": {"bg_navy": "#0A0F1D", "bg_violet": "#130926", "bg_red": "#3B0A0A", "accent": "#38D9FF", "alert": "#FF3B30", "yellow": "#FFD400"},\n'
        '  "blocos": [{"perfil_voz": "narrador_tenso", "texto": "A cabine de pedágio sumiu na neblina densa da rodovia.", "prompt_imagem": "Wide cinematic shot of an isolated highway toll booth swallowed by dense nocturnal fog, flickering amber sodium lamp, wet black asphalt, hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, no text, no letters, no watermark", "camera": "push_in", "mood": "navy", "sfx_depois": null}],\n'
        '  "katana_hits": [{"bloco_idx": 2, "palavra_gatilho": "neblina", "linhas": ["NEBLINA"], "duracao": 0.42, "cor": "red"}]\n'
        "}\n\n"
        f"{pilar_hint}"
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
        geracao = 0 if "gemini-2.5" in low else (1 if "gemini-2.0" in low else 2)
        if "flash-lite" in low:
            return (geracao, 0, low)
        if "flash" in low and "preview" not in low:
            return (geracao, 1, low)
        if "flash" in low:
            return (geracao, 2, low)
        return (geracao, 3, low)

    candidatos.sort(key=_prioridade)
    return candidatos[:10]


def chamar_groq_json(
    prompt: str,
    groq_api_key: str,
    modelo: str | None = None,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    modelo_ativo_ref: dict[str, str] | None = None,
) -> dict:
    """Fallback gratuito via Groq (OpenAI-compatible) usando llama-3.3-70b-versatile em modo JSON."""
    chave = str(groq_api_key or "").strip()
    if not chave:
        raise RuntimeError("GROQ_API_KEY ausente para fallback.")

    modelo_uso = (modelo or os.environ.get("GROQ_MODEL", "").strip() or GROQ_MODELO_PADRAO)
    opener = urlopen_fn or urllib.request.urlopen
    headers = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "gps-canal-dark/8.1",
    }

    system_msg = (
        "Voce e uma API JSON precisa. Responda sempre com um unico objeto JSON valido "
        "seguindo exatamente o esquema pedido, sem cercas markdown e com acentuacao UTF-8 correta."
    )

    ultimo_erro = "Falha desconhecida ao chamar Groq."
    for usar_response_format in (True, False):
        payload: dict = {
            "model": modelo_uso,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }
        if usar_response_format:
            payload["response_format"] = {"type": "json_object"}
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        for tentativa in range(2):
            req = urllib.request.Request(GROQ_API_URL, data=payload_bytes, headers=headers, method="POST")
            try:
                with opener(req, timeout=60) as resp:
                    corpo = resp.read().decode("utf-8")
                envelope = json.loads(corpo)
                choices = envelope.get("choices") or []
                if not choices:
                    raise RuntimeError(f"Resposta do Groq ({modelo_uso}) sem 'choices'.")
                msg = choices[0].get("message") or {}
                conteudo = str(msg.get("content", "") or "").strip()
                if not conteudo:
                    raise RuntimeError(f"Resposta do Groq ({modelo_uso}) sem conteudo textual.")
                dados = _extrair_json_resposta(conteudo)
                if modelo_ativo_ref is not None:
                    modelo_ativo_ref["modelo"] = f"groq:{modelo_uso}"
                    modelo_ativo_ref["provedor"] = "groq"
                print(f"Fallback gratuito Groq OK ({modelo_uso}).", flush=True)
                return dados
            except urllib.error.HTTPError as exc:
                detalhe = _extrair_erro_http_gemini(exc, chave)
                ultimo_erro = f"Groq [{modelo_uso}] HTTP {exc.code}: {detalhe}"
                # Se falhou validacao estrita de json_object (HTTP 400), tenta sem response_format
                if exc.code == 400 and usar_response_format and "json" in detalhe.lower():
                    print(
                        f"AVISO {ultimo_erro}; repetindo no Groq sem response_format estrito...",
                        flush=True,
                    )
                    break
                if exc.code in (429, 500, 502, 503, 504) and tentativa == 0:
                    espera = min(4.0, _extrair_retry_after_s(exc, 2.5))
                    print(f"AVISO {ultimo_erro}; aguardando {espera:.1f}s antes de repetir Groq...", flush=True)
                    sleep_fn(espera)
                    continue
                raise RuntimeError(ultimo_erro) from None
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
                ultimo_erro = f"Groq [{modelo_uso}] {type(exc).__name__}: {exc}"
                if tentativa == 0:
                    sleep_fn(2.0)
                    continue
                if usar_response_format:
                    break
                raise RuntimeError(ultimo_erro) from None

    raise RuntimeError(ultimo_erro)


def _chamar_gemini_json(
    prompt: str,
    api_key: str = "",
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    retry_esperas: tuple[float, ...] = (2.0, 5.0),
    modelo_ativo_ref: dict[str, str] | None = None,
    pool: GeminiPool | None = None,
    groq_api_key: str | None = None,
) -> dict:
    """Chama Gemini via GeminiPool (multi-chave + rotacao de modelos + fail-fast cota diaria) com fallback Groq."""
    opener = urlopen_fn or urllib.request.urlopen
    modelos_iniciais = _montar_lista_modelos(modelo)

    if pool is None:
        chave_limpa = str(api_key or "").strip()
        if chave_limpa:
            chave_limpa = validar_gemini_api_key(chave_limpa)
        pool = GeminiPool.from_env(
            modelos=modelos_iniciais,
            chave_primaria=chave_limpa or None,
            ler_env_arquivo=False,
            incluir_ambiente=True,
        )
    else:
        pool.adicionar_modelos(modelos_iniciais)

    groq_key = (
        obter_groq_api_key(ler_env_arquivo=False)
        if groq_api_key is None
        else str(groq_api_key or "").strip()
    )

    if pool.total_chaves() == 0:
        if groq_key:
            print(
                f"AVISO nenhuma chave Gemini ativa; usando fallback gratuito Groq ({GROQ_MODELO_PADRAO}).",
                flush=True,
            )
            return chamar_groq_json(
                prompt,
                groq_key,
                urlopen_fn=opener,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
            )
        validar_gemini_api_key(api_key)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    max_t = 1 + len(retry_esperas)

    autodescoberta_feita = False
    ultimo_erro_msg = "Falha desconhecida ao consultar a API Gemini."
    combinacoes_testadas: list[str] = []

    while True:
        modelo_pref = None
        if modelo_ativo_ref and modelo_ativo_ref.get("provedor") != "groq":
            modelo_pref = modelo_ativo_ref.get("modelo") or None
        combinacoes = list(
            pool.iterar_combinacoes(
                estrategia="chave_depois_modelo",
                modelo_preferido=modelo_pref or modelo,
            )
        )
        if not combinacoes:
            if not autodescoberta_feita:
                autodescoberta_feita = True
                chave_disc = next(
                    (v for n, v in pool.chaves if n not in pool.chaves_invalidas),
                    None,
                )
                if chave_disc:
                    descobertos = pool.adicionar_modelos(
                        _descobrir_modelos_gemini_disponiveis(chave_disc, urlopen_fn=opener)
                    )
                    if descobertos:
                        print(
                            f"AVISO autodescoberta /v1beta/models adicionou modelos ao pool: {descobertos}",
                            flush=True,
                        )
                        continue
            break

        houve_avanco = False
        for nome_chave, chave_valor, modelo_atual in combinacoes:
            if not pool.esta_disponivel(nome_chave, modelo_atual):
                continue
            houve_avanco = True
            combinacoes_testadas.append(f"{nome_chave}:{modelo_atual}")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_atual}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": chave_valor,
            }

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
                    pool.registrar_sucesso(nome_chave, modelo_atual)
                    if modelo_ativo_ref is not None:
                        modelo_ativo_ref["modelo"] = modelo_atual
                        modelo_ativo_ref["chave"] = nome_chave
                        modelo_ativo_ref["provedor"] = "gemini"
                    return dados_json
                except urllib.error.HTTPError as exc:
                    detalhe = pool.sanitizar(_extrair_erro_http_gemini(exc, chave_valor))
                    ultimo_erro_msg = f"Gemini [{nome_chave}/{modelo_atual}] HTTP {exc.code}: {detalhe}"

                    if eh_erro_chave_invalida(detalhe, status_code=exc.code):
                        pool.marcar_chave_invalida(nome_chave, detalhe)
                        print(
                            f"AVISO chave rejeitada/sem permissao ({ultimo_erro_msg}). Trocando para proxima chave...",
                            flush=True,
                        )
                        break

                    if eh_erro_modelo_indisponivel(detalhe, status_code=exc.code):
                        pool.marcar_modelo_indisponivel(modelo_atual, detalhe)
                        print(
                            f"AVISO modelo indisponivel ({ultimo_erro_msg}). Trocando para proximo modelo...",
                            flush=True,
                        )
                        break

                    if exc.code == 429 or "resource_exhausted" in detalhe.lower():
                        esgotou_diaria = pool.registrar_429(
                            nome_chave,
                            modelo_atual,
                            detalhe,
                            status_code=exc.code,
                        )
                        if esgotou_diaria:
                            print(
                                f"AVISO COTA DIARIA ESGOTADA ({ultimo_erro_msg}). "
                                "Marcando combinacao como esgotada e trocando imediatamente (fail-fast, 0s sleep)...",
                                flush=True,
                            )
                            break
                        # Se ha outra combinacao disponivel no pool, evita dormir longo e tenta proxima combinacao
                        if tentativa < len(retry_esperas):
                            espera = min(10.0, _extrair_retry_after_s(exc, float(retry_esperas[tentativa])))
                            print(
                                f"AVISO 429 transitorio ({ultimo_erro_msg}) tentativa {tentativa + 1}/{max_t}. "
                                f"Aguardando {espera:.1f}s...",
                                flush=True,
                            )
                            sleep_fn(espera)
                            continue
                        pool.marcar_esgotado(nome_chave, modelo_atual, detalhe)
                        print(
                            f"AVISO {ultimo_erro_msg} persistiu apos retries; trocando de combinacao...",
                            flush=True,
                        )
                        break

                    if exc.code in (500, 502, 503, 504):
                        if tentativa < len(retry_esperas):
                            espera = min(10.0, _extrair_retry_after_s(exc, float(retry_esperas[tentativa])))
                            print(
                                f"AVISO {ultimo_erro_msg} na tentativa {tentativa + 1}/{max_t}. "
                                f"Aguardando {espera:.1f}s...",
                                flush=True,
                            )
                            sleep_fn(espera)
                            continue
                        print(
                            f"AVISO {ultimo_erro_msg} esgotou retries; tentando proxima combinacao do pool...",
                            flush=True,
                        )
                        break

                    print(f"AVISO erro definitivo na combinacao ({ultimo_erro_msg}); avancando no pool...", flush=True)
                    break
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
                    ultimo_erro_msg = f"Gemini [{nome_chave}/{modelo_atual}] {type(exc).__name__}: {pool.sanitizar(str(exc))}"
                    if tentativa < len(retry_esperas):
                        espera = float(retry_esperas[tentativa])
                        print(
                            f"AVISO {ultimo_erro_msg} na tentativa {tentativa + 1}/{max_t}. "
                            f"Aguardando {espera:.1f}s...",
                            flush=True,
                        )
                        sleep_fn(espera)
                        continue
                    break

        if not houve_avanco:
            break

        # Apos esgotar a fila inicial, tenta autodescoberta uma unica vez se ainda houver chave valida
        if not autodescoberta_feita:
            autodescoberta_feita = True
            chave_disc = next(
                (v for n, v in pool.chaves if n not in pool.chaves_invalidas),
                None,
            )
            if chave_disc:
                descobertos = pool.adicionar_modelos(
                    _descobrir_modelos_gemini_disponiveis(chave_disc, urlopen_fn=opener)
                )
                if descobertos:
                    print(
                        f"AVISO autodescoberta /v1beta/models adicionou modelos ao pool: {descobertos}",
                        flush=True,
                    )
                    continue
        break

    if groq_key:
        print(
            f"AVISO todas as combinacoes Gemini esgotadas/falharam ({pool.resumo_estado()}). "
            f"Acionando fallback gratuito Groq ({GROQ_MODELO_PADRAO})...",
            flush=True,
        )
        return chamar_groq_json(
            prompt,
            groq_key,
            urlopen_fn=opener,
            sleep_fn=sleep_fn,
            modelo_ativo_ref=modelo_ativo_ref,
        )

    raise RuntimeError(
        f"Todas as combinacoes Gemini falharam ({combinacoes_testadas} | {pool.resumo_estado()}). "
        f"Ultimo erro: {ultimo_erro_msg}"
    )


def selecionar_proximo_pilar(
    dados_hist: dict,
    proximo_id: int,
    pilar_forcado: str | None = None,
) -> dict[str, str]:
    """Alterna automaticamente entre os 4 pilares do canal 'E Se Voce?' sem repetir o anterior."""
    if pilar_forcado:
        chave = str(pilar_forcado).strip().lower()
        if chave not in PILARES_POR_ID:
            validos = ", ".join(PILARES_POR_ID.keys())
            raise ValueError(f"Pilar editorial invalido: {pilar_forcado!r}. Opcoes validas: {validos}.")
        return PILARES_POR_ID[chave]

    videos = dados_hist.get("videos") or []
    ultimo_pilar: str | None = None
    for v in reversed(videos):
        p_id = str(v.get("pilar", "") or "").strip().lower()
        if p_id in PILARES_POR_ID:
            ultimo_pilar = p_id
            break

    if ultimo_pilar is not None:
        ordem_ids = [p["id"] for p in PILARES_EDITORIAIS]
        idx_prox = (ordem_ids.index(ultimo_pilar) + 1) % len(PILARES_EDITORIAIS)
        return PILARES_EDITORIAIS[idx_prox]

    # Apos o Video 08 (suspense/terror), inicia a rotacao no pilar 0 ('cenarios_hipoteticos') para o Video 09
    idx_padrao = max(0, int(proximo_id) - 9) % len(PILARES_EDITORIAIS)
    return PILARES_EDITORIAIS[idx_padrao]


def _resumir_historico_proibido(dados_hist: dict) -> str:
    linhas: list[str] = []
    for v in dados_hist.get("videos", []):
        vid = int(v.get("id", 0))
        titulo = str(v.get("titulo", "")).strip()
        tema = str(v.get("tema", "")).strip()
        pilar_tag = f" | Pilar: {v['pilar']}" if v.get("pilar") else ""
        kws = ", ".join(str(k) for k in v.get("palavras_chave", [])[:6])
        linhas.append(f"- Video {vid:02d}: '{titulo}'{pilar_tag} | Tema: {tema} | Palavras-chave: {kws}")
    return "\n".join(linhas) if linhas else "- (nenhum video anterior)"


def _montar_prompt_roteiro_inedito(
    dados_hist: dict,
    proximo_id: int,
    titulo_sugerido: str | None = None,
    motivo_rejeicao: str | None = None,
    pilar: dict[str, str] | None = None,
) -> str:
    pilar_ativo = pilar or selecionar_proximo_pilar(dados_hist, proximo_id)
    proibidos = _resumir_historico_proibido(dados_hist)
    resumo_pilares = ", ".join(p["nome"] for p in PILARES_EDITORIAIS)
    dica_titulo = (
        f"Use ou adapte este título solicitado pelo usuário: '{titulo_sugerido}'.\n"
        if titulo_sugerido
        else f"Crie um título curto, magnético e inédito em {IDIOMA_HUMANO} (3 a 7 palavras) alinhado ao pilar.\n"
    )
    aviso_rej = (
        f"\nATENÇÃO: a tentativa anterior foi rejeitada por similaridade ({motivo_rejeicao}). "
        "Mude COMPLETAMENTE o assunto, o cenário, os elementos centrais e a revelação final!\n"
        if motivo_rejeicao
        else ""
    )
    return (
        f"Você é o roteirista-chefe do canal '{CANAL_NOME}' (YouTube Shorts / Reels de altíssima retenção "
        f"em {IDIOMA_HUMANO} [{IDIOMA_CANAL}], episódio Vídeo {proximo_id:02d}).\n"
        f"O canal alterna entre {len(PILARES_EDITORIAIS)} pilar(es) editorial(is): {resumo_pilares}.\n\n"
        f"PILAR OBRIGATÓRIO DESTE EPISÓDIO: {pilar_ativo['nome']} (id={pilar_ativo['id']})\n"
        f"- Gancho inicial obrigatório: {pilar_ativo['gancho']}\n"
        f"- Desenvolvimento editorial: {pilar_ativo['instrucoes']}\n"
        f"- Territórios de inspiração (escolha algo inédito que NÃO esteja no histórico): {pilar_ativo['exemplos']}.\n\n"
        "TEMAS JÁ PRODUZIDOS (PROIBIDO REPETIR TEMA, CENÁRIO, OBJETO CENTRAL OU REVELAÇÃO):\n"
        f"{proibidos}\n"
        f"{aviso_rej}\n"
        "REGRAS OBRIGATÓRIAS DO ROTEIRO:\n"
        f"1. {dica_titulo}"
        "2. Escreva entre 185 e 245 palavras em ritmo contínuo e envolvente.\n"
        "3. Siga estritamente o pilar obrigatório acima (não fuja do foco editorial configurado para este episódio).\n"
        "4. VOZ HUMANA E VICIANTE (ZERO TOM ROBÓTICO): escreva em frases curtas, diretas e faladas como um humano "
        "contando algo viciante para um amigo. Ritmo conversacional real, verbos concretos e imagens mentais imediatas. "
        "PROIBIDO usar clichês de IA ou linguagem de redação formal como 'mergulhe nessa história', 'prepare-se para descobrir', "
        "'em um mundo onde', 'você não vai acreditar', 'a resposta vai te surpreender', 'no cenário atual', 'nesse contexto', "
        "'além disso', 'por outro lado' ou 'sem dúvida'.\n"
        "5. RETENÇÃO SEM INTERRUPÇÃO: abra com um gancho impossível de ignorar nos primeiros 3 segundos e mantenha "
        "a tensão crescente até a virada final seca e memorável. PROIBIDO inserir qualquer pausa comercial, propaganda, "
        "anúncio ou CTA no meio do vídeo (jamais interrompa a história por volta do segundo 14 ou no meio do roteiro). "
        "Deixe APENAS um gancho/CTA curto e natural de 1 única frase no finalzinho do vídeo "
        f"(referência do canal: '{CTA_FINAL_PADRAO}').\n"
        f"6. ORTOGRAFIA COMPLETA EM {IDIOMA_HUMANO.upper()} (UTF-8): escreva com acentuação e grafia UTF-8 100% corretas "
        "em TODAS as palavras. Nunca remova acentos nem cedilhas.\n"
        "7. ZERO emoji, ZERO travessão (em-dash ou en-dash), ZERO tags [VOZ], [SFX] ou [CTA_PAUSA] "
        "(a marcação técnica será feita na etapa seguinte).\n"
        "8. Responda APENAS com JSON válido no formato:\n"
        "{\n"
        '  "titulo": "Título Inédito Curto",\n'
        '  "tema": "Resumo objetivo em 1 frase da premissa inédita",\n'
        f'  "roteiro_bruto": "Texto corrido completo do roteiro em {IDIOMA_CANAL} falado natural com grafia UTF-8 100% correta, sem pausa comercial no meio e fechando com 1 frase curta de gancho/CTA no finalzinho (185 a 245 palavras)."\n'
        "}\n"
    )


def gerar_roteiro_inedito_gemini(
    dados_hist: dict,
    titulo_sugerido: str | None,
    api_key: str = "",
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    modelo_ativo_ref: dict[str, str] | None = None,
    pilar: dict[str, str] | None = None,
    pool: GeminiPool | None = None,
    groq_api_key: str | None = None,
) -> tuple[str, str]:
    """Gera obrigatoriamente um titulo e roteiro bruto 100% ineditos via GeminiPool (com fallback Groq)."""
    prox_id = proximo_numero_livre(dados_hist)
    pilar_ativo = pilar or selecionar_proximo_pilar(dados_hist, prox_id)
    print(
        f"Diretor IA ('{CANAL_NOME}'): Video {prox_id:02d} -> pilar '{pilar_ativo['id']}' ({pilar_ativo['nome']}).",
        flush=True,
    )
    motivo_rej: str | None = None
    ultimo_erro = "Gemini/Groq nao retornou um roteiro inedito valido."
    ref_local = modelo_ativo_ref if modelo_ativo_ref is not None else {}

    for tentativa in range(1, 4):
        prompt = _montar_prompt_roteiro_inedito(
            dados_hist,
            proximo_id=prox_id,
            titulo_sugerido=titulo_sugerido,
            motivo_rejeicao=motivo_rej,
            pilar=pilar_ativo,
        )
        mod_pref = ref_local.get("modelo", modelo) if ref_local.get("provedor") != "groq" else modelo
        dados = _chamar_gemini_json(
            prompt=prompt,
            api_key=api_key,
            modelo=mod_pref,
            urlopen_fn=urlopen_fn,
            sleep_fn=sleep_fn,
            modelo_ativo_ref=ref_local,
            pool=pool,
            groq_api_key=groq_api_key,
        )
        titulo_gerado = restaurar_acentos_ptbr(sanitizar_texto(str(dados.get("titulo", "") or titulo_sugerido or ""))).strip()
        tema_gerado = restaurar_acentos_ptbr(sanitizar_texto(str(dados.get("tema", "") or ""))).strip()
        roteiro_gerado = restaurar_acentos_ptbr(sanitizar_texto(str(dados.get("roteiro_bruto", "") or ""))).strip()

        if len(roteiro_gerado.split()) < 60:
            ultimo_erro = f"Roteiro inedito curto demais ({len(roteiro_gerado.split())} palavras)."
            motivo_rej = ultimo_erro
            continue

        if not titulo_gerado:
            titulo_gerado = f"{pilar_ativo['titulo_fallback']} {prox_id:02d}"

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


def gerar_roteiro_inedito_mock(
    dados_hist: dict,
    titulo_sugerido: str | None = None,
    pilar: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Gerador deterministico offline cobrindo os 4 pilares do canal apenas para testes locais (--mock)."""
    prox_id = proximo_numero_livre(dados_hist)
    pilar_ativo = pilar or selecionar_proximo_pilar(dados_hist, prox_id)
    pid = pilar_ativo["id"]

    modelos_mock: dict[str, tuple[str, str]] = {
        "cenarios_hipoteticos": (
            f"E Se Você Acordasse Preso no Submarino {prox_id:02d}",
            (
                "E se você acordasse agora preso dentro de um submarino a trezentos metros de profundidade? "
                "As luzes principais apagaram. Só o painel de emergência brilha em vermelho. "
                "O visor marca quarenta e oito horas de oxigênio, e o rádio da superfície está mudo. "
                "Seu primeiro instinto é correr e bater no casco de aço pedindo socorro. Só que esse é o pior erro possível. "
                "Cada movimento apressado dobra o gasto de ar e enche a cabine de gás carbônico. "
                "Com doze horas, o frio bate seis graus. O silêncio de metal começa a pregar peças na sua cabeça, "
                "como se alguém estivesse andando lá fora. Na hora vinte e quatro, o ar fica pesado e sua vista escurece nas bordas. "
                "Você acha uma válvula manual de lastro no corredor central e gira o ferro com as mãos tremendo. "
                "O submarino inclina devagar, mas o painel acende um alerta impossível: a escotilha externa já tinha sido aberta "
                "pelo lado de fora antes mesmo de você acordar. "
                "Me conta nos comentários: você tentaria abrir essa escotilha ou ficaria lá dentro?"
            ),
        ),
        "curiosidades_bizarras": (
            f"O Fenômeno Real do Ponto Nemo {prox_id:02d}",
            (
                "Existe um lugar no oceano tão isolado que, se você cair lá, as pessoas mais perto de você não estão na Terra. "
                "Elas estão passando lá em cima, na Estação Espacial Internacional. "
                "Esse ponto real se chama Ponto Nemo, no meio do Pacífico Sul, a mais de dois mil e seiscentos quilômetros de qualquer ilha habitada. "
                "As correntes giram em volta e quase não deixam nutrientes entrar. A água vira um deserto quase sem peixes. "
                "Por ser tão vazio, agências espaciais usam o lugar como o maior cemitério de naves do planeta. "
                "Centenas de satélites mortos e restos de estações já foram jogados de propósito ali no fundo. "
                "Só que o mais estranho rolou em noventa e sete. Microfones militares no fundo do mar captaram um barulho colossal vindo dali, "
                "ouvido a cinco mil quilômetros de distância. A explicação oficial falou em um bloco de gelo se partindo, "
                "mas ninguém nunca gravou outro som igual até hoje. "
                "E você, acha que era só gelo ou tem coisa escondida lá embaixo, comenta aí?"
            ),
        ),
        "misterios_reais": (
            f"O Cofre Proibido no Gelo de Svalbard {prox_id:02d}",
            (
                "Existe uma porta de concreto cravada numa montanha congelada do Ártico onde quase ninguém no mundo pode entrar. "
                "É o Cofre Global de Sementes de Svalbard, enfiado cento e vinte metros dentro do gelo, na Noruega. "
                "Ele foi feito para sobreviver a terremotos, explosões, apagões e até ao derretimento das geleiras. "
                "Lá dentro ficam mais de um milhão de amostras de sementes guardadas a dezoito graus negativos. "
                "Tem sensor de movimento, portas blindadas duplas e uma trava rígida: sem credencial diplomática, ninguém passa do primeiro corredor. "
                "Não existe equipe morando lá dentro, mas câmeras vigiam cada grau de temperatura o tempo todo. "
                "Até hoje, só um país precisou abrir sua caixa lacrada depois de uma guerra. "
                "Isso mostra uma coisa bem real: o cofre não é exagero de filme, ele existe porque governos já têm plano pronto se a comida do planeta acabar. "
                "Você sabia que esse cofre existia, me diz aqui nos comentários?"
            ),
        ),
        "suspense_urbano": (
            f"O Último Vagão da Linha Sul {prox_id:02d}",
            (
                "Eram onze e dezoito da noite quando Mateus entrou no último vagão vazio do metrô. "
                "Ele sentou perto da janela escura e pôs o fone para abafar o barulho dos trilhos. "
                "Quando o trem entrou no túnel longo, a luz do teto piscou duas vezes. "
                "O letreiro em cima da porta travou no nome de uma estação fechada há quase trinta anos. "
                "Mateus tirou o fone e percebeu um silêncio total, sem nenhum som de motor. "
                "No reflexo do vidro, todos os bancos estavam vazios, menos o banco logo atrás dele. "
                "Tinha um homem de capa escura sentado ali, de cabeça baixa. Mateus virou o pescoço na hora: o banco real atrás dele estava vazio. "
                "O interfone perto da porta chiou alto e uma voz assustada da central perguntou como ele tinha entrado ali, "
                "porque aquele trem estava desligado na garagem há quarenta minutos. "
                "Mateus olhou de volta para o vidro. O homem do reflexo agora estava de pé atrás da nuca dele, sorrindo. "
                "Me diz nos comentários: você puxava o freio de emergência ou corria pro outro vagão?"
            ),
        ),
    }

    if pid in modelos_mock:
        titulo_padrao, roteiro = modelos_mock[pid]
    else:
        nome_pilar = str(pilar_ativo.get("nome") or pid.replace("_", " ").title()).strip()
        titulo_fb = str(pilar_ativo.get("titulo_fallback") or nome_pilar[:44]).strip()
        titulo_padrao = f"{titulo_fb} {prox_id:02d}"
        roteiro = (
            f"Quase ninguém percebe o que realmente acontece quando o assunto é {nome_pilar}. "
            f"No canal {CANAL_NOME}, a gente olhou os detalhes que passam batido todo dia. "
            "No primeiro minuto tudo parece comum e previsível, sem nenhum sinal de alerta. "
            "Só que uma pequena escolha repetida em silêncio muda completamente o resultado final. "
            "Quem entende esse mecanismo cedo consegue virar o jogo antes de perder tempo e energia. "
            "Quando você junta as peças na ordem certa, o padrão fica impossível de ignorar. "
            "O detalhe que quase todo mundo deixa de lado é exatamente o ponto onde tudo muda de direção. "
            "No fim das contas, a diferença entre quem trava e quem avança está nesse único ajuste prático. "
            f"{CTA_FINAL_PADRAO}"
        )
    titulo = restaurar_acentos_ptbr(sanitizar_texto(titulo_sugerido)) if titulo_sugerido else titulo_padrao
    return titulo, roteiro


def chamar_gemini_diretor(
    roteiro_bruto: str,
    titulo_sugerido: str | None,
    api_key: str = "",
    catalogo_sfx: dict[str, float] | None = None,
    modelo: str = GEMINI_MODELO_PADRAO,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    modelo_ativo_ref: dict[str, str] | None = None,
    pilar: dict[str, str] | None = None,
    pool: GeminiPool | None = None,
    groq_api_key: str | None = None,
) -> dict:
    """Chama GeminiPool (multi-chave + rotacao de modelos + fail-fast) com fallback gratuito Groq."""
    sfx_keys = sorted((catalogo_sfx or {}).keys())
    prompt = _montar_prompt_gemini(roteiro_bruto, titulo_sugerido, sfx_keys, pilar=pilar)
    return _chamar_gemini_json(
        prompt=prompt,
        api_key=api_key,
        modelo=modelo,
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn,
        modelo_ativo_ref=modelo_ativo_ref,
        pool=pool,
        groq_api_key=groq_api_key,
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

    ctx_escritorio = texto_indica_escritorio(roteiro_bruto)
    ctx_zero_g = texto_indica_gravidade_zero(roteiro_bruto)

    titulo = restaurar_acentos_ptbr(sanitizar_texto(titulo_forcado or plano_bruto.get("titulo") or fallback["titulo"]))[:72]
    if not titulo:
        titulo = fallback["titulo"]
        avisos.append("Titulo ausente: preenchido pelo fallback.")

    tema = restaurar_acentos_ptbr(sanitizar_texto(plano_bruto.get("tema") or fallback["tema"]))[:200]
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
        "nome": restaurar_acentos_ptbr(sanitizar_texto(prot_in.get("nome") or fallback["protagonista"]["nome"]))[:28] or "Protagonista",
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
    prompts_usados: set[str] = set()

    ultimo_cenario = ""
    ultima_camera = ""

    if isinstance(blocos_in, list) and len(blocos_in) >= 3:
        sfx_count = 0
        total_in = len(blocos_in)
        for idx, b in enumerate(blocos_in):
            if not isinstance(b, dict):
                continue
            txt_raw = str(b.get("texto", ""))
            txt = restaurar_acentos_ptbr(
                sanitizar_texto(re.sub(r"\[/?(?:CTA_PAUSA|VOZ(?::[a-zA-Z0-9_]+)?)\]", "", txt_raw, flags=re.IGNORECASE))
            )
            if not txt:
                continue
            if not txt.endswith((".", "!", "?", ",", ";", ":")):
                txt += "."
            norm_txt = normalizar_texto(txt)
            perfil_orig = str(b.get("perfil_voz", "narrador_tenso")).strip().lower()
            eh_ultimo_in = idx == total_in - 1
            eh_cta_in = eh_ultimo_in and _eh_bloco_cta_final(txt)

            # Bloqueia qualquer pausa comercial ou CTA no meio do video
            if not eh_ultimo_in and (
                "[cta_pausa]" in txt_raw.lower()
                or perfil_orig == "cta_comercial"
                or "comente eu quero" in norm_txt
                or "fazer videos assim no automatico" in norm_txt
            ):
                avisos.append(f"Bloco {idx + 1}: pausa comercial/CTA no meio removida automaticamente.")
                continue

            perfil = perfil_orig
            if perfil not in PERFIS_VOZ or perfil == "cta_comercial":
                perfil = "narrador_tenso"
                avisos.append(f"Bloco {idx + 1}: perfil_voz corrigido para narrador_tenso.")

            mood_raw = str(b.get("mood", "navy")).strip().lower()
            mood = mood_raw if mood_raw in MOODS_VALIDOS else ("red" if perfil in ("panico", "sussurro_twist") else "navy")

            sfx_dep = b.get("sfx_depois")
            sfx_limpo: str | None = None
            if isinstance(sfx_dep, str) and sfx_dep.strip():
                cand_sfx = re.sub(r"[^a-z0-9_]", "", sfx_dep.strip().lower())
                if cand_sfx in sfx_permitidos and sfx_count < 3:
                    sfx_limpo = cand_sfx
                    sfx_count += 1
                else:
                    avisos.append(f"Bloco {idx + 1}: sfx_depois '{sfx_dep}' ignorado.")

            # Subdivide automaticamente falas > 4s (> MAX_PALAVRAS_POR_TOMADA palavras) em 2 ou 3 tomadas curtas
            sub_falas = (
                [txt]
                if eh_cta_in or len(txt.split()) <= MAX_PALAVRAS_POR_TOMADA + 1
                else _dividir_fala_em_tomadas_curtas(txt, max_palavras=MAX_PALAVRAS_POR_TOMADA)
            )
            prompt_bruto = sanitizar_texto(str(b.get("prompt_imagem", "")))
            tomadas_prompts_raw = b.get("tomadas_prompts") if isinstance(b.get("tomadas_prompts"), list) else []

            for sub_i, sub_txt in enumerate(sub_falas):
                sub_txt_fmt = sub_txt.strip()
                if not sub_txt_fmt:
                    continue
                if not sub_txt_fmt.endswith((".", "!", "?", ",", ";", ":")):
                    sub_txt_fmt += "."
                eh_ultima_sub = sub_i == len(sub_falas) - 1

                cen_norm = inferir_cenario_animado(
                    sub_txt_fmt,
                    len(blocos_validos),
                    max(total_in, len(blocos_validos) + 2),
                    anterior=ultimo_cenario,
                    contexto_global=roteiro_bruto,
                    hud_dado=None,
                    eh_cta=eh_cta_in,
                    eh_twist=(idx == total_in - 2 and eh_ultima_sub),
                )
                ultimo_cenario = cen_norm

                acao_norm = inferir_acao_cena(
                    sub_txt_fmt,
                    cen_norm,
                    hud_dado=None,
                    gravidade_zero=texto_indica_gravidade_zero(sub_txt_fmt),
                )
                cam = escolher_camera_alternada(
                    b.get("camera") if sub_i == 0 else None,
                    acao_norm,
                    cen_norm,
                    len(blocos_validos),
                    anterior=ultima_camera,
                    mood=mood,
                )
                ultima_camera = cam

                # Resolve prompt_imagem literal e unico para cada tomada
                p_cand = ""
                if sub_i < len(tomadas_prompts_raw) and isinstance(tomadas_prompts_raw[sub_i], str):
                    p_cand = sanitizar_texto(tomadas_prompts_raw[sub_i])
                elif sub_i == 0 and len(prompt_bruto) >= 24:
                    p_cand = prompt_bruto

                if len(p_cand) >= 24:
                    prompt_final = garantir_estilo_prompt_imagem(p_cand)
                    if prompt_final.lower() in prompts_usados:
                        prompt_final = gerar_prompt_imagem_literal(
                            texto=sub_txt_fmt,
                            titulo=titulo,
                            idx=len(blocos_validos),
                            total=max(total_in, len(blocos_validos) + 2),
                            mood=mood,
                            prompts_usados=prompts_usados,
                        )
                    else:
                        prompts_usados.add(prompt_final.lower())
                else:
                    prompt_final = gerar_prompt_imagem_literal(
                        texto=sub_txt_fmt,
                        titulo=titulo,
                        idx=len(blocos_validos),
                        total=max(total_in, len(blocos_validos) + 2),
                        mood=mood,
                        prompts_usados=prompts_usados,
                    )

                blocos_validos.append(
                    {
                        "perfil_voz": perfil,
                        "texto": sub_txt_fmt,
                        "prompt_imagem": prompt_final,
                        "cenario": cen_norm,
                        "modulo": cen_norm,
                        "acao_cena": acao_norm,
                        "pose": inferir_pose_animada(sub_txt_fmt, cen_norm, acao_norm, perfil, eh_cta=eh_cta_in),
                        "mood": mood,
                        "expressao": inferir_expressao_animada(
                            sub_txt_fmt,
                            perfil,
                            acao_norm,
                            eh_twist=(idx == total_in - 2 and eh_ultima_sub),
                            eh_cta=eh_cta_in,
                        ),
                        "camera": cam,
                        "sfx_depois": sfx_limpo if eh_ultima_sub else None,
                    }
                )

    if len(blocos_validos) < 3:
        avisos.append("Blocos insuficientes no retorno do Gemini: blocos gerados pelo fallback deterministico.")
        blocos_validos = fallback["blocos"]
        ultima_camera = blocos_validos[-1]["camera"]
        prompts_usados = {b["prompt_imagem"].lower() for b in blocos_validos}

    # Garante apenas 1 frase curta de gancho/CTA no finalzinho do video (nunca no meio)
    if not _eh_bloco_cta_final(blocos_validos[-1]["texto"]):
        cen_cta = "big_face" if blocos_validos[-1]["cenario"] != "big_face" else "arena_comparacao"
        cam_cta = escolher_camera_alternada(
            "pull_out",
            "investigando_pista",
            cen_cta,
            len(blocos_validos),
            anterior=blocos_validos[-1]["camera"],
            mood="navy",
        )
        prompt_cta = gerar_prompt_imagem_literal(
            texto=CTA_FINAL_PADRAO,
            titulo=titulo,
            idx=len(blocos_validos),
            total=len(blocos_validos) + 1,
            mood="navy",
            prompts_usados=prompts_usados,
        )
        blocos_validos.append(
            {
                "perfil_voz": "narrador_tenso",
                "texto": CTA_FINAL_PADRAO,
                "prompt_imagem": prompt_cta,
                "cenario": cen_cta,
                "modulo": cen_cta,
                "acao_cena": "investigando_pista",
                "pose": "apontando",
                "mood": "navy",
                "expressao": "smug",
                "camera": cam_cta,
                "sfx_depois": None,
            }
        )

    # Garante fechamento de impacto (impacto_twist antes do twist, sussurro_twist no twist, voz natural na CTA final)
    idx_twist = len(blocos_validos) - 2 if len(blocos_validos) >= 3 and _eh_bloco_cta_final(blocos_validos[-1]["texto"]) else len(blocos_validos) - 1
    if len(blocos_validos) >= 3 and idx_twist == len(blocos_validos) - 2:
        blocos_validos[-1]["perfil_voz"] = "narrador_tenso"
        blocos_validos[-1]["sfx_depois"] = None
        blocos_validos[idx_twist]["perfil_voz"] = "sussurro_twist"
        blocos_validos[idx_twist]["sfx_depois"] = None
        if not any(b.get("sfx_depois") == "impacto_twist" for b in blocos_validos[:idx_twist]):
            blocos_validos[idx_twist - 1]["sfx_depois"] = "impacto_twist"
    elif len(blocos_validos) >= 2:
        blocos_validos[-1]["perfil_voz"] = "sussurro_twist"
        blocos_validos[-1]["sfx_depois"] = None
        if not any(b.get("sfx_depois") == "impacto_twist" for b in blocos_validos):
            blocos_validos[-2]["sfx_depois"] = "impacto_twist"

    # Valida e normaliza 3 a 5 palavras de impacto (katana_hits) ligadas aos blocos reais da historia
    hits_in = plano_bruto.get("katana_hits")
    hits_validos: list[dict] = []
    blocos_com_hit: set[int] = set()
    max_hit_idx = idx_twist if idx_twist >= 2 else len(blocos_validos) - 1
    if isinstance(hits_in, list):
        for h in hits_in:
            if not isinstance(h, dict) or len(hits_validos) >= 5:
                continue
            try:
                b_idx = int(h.get("bloco_idx", -1))
            except (TypeError, ValueError):
                b_idx = -1
            if b_idx < 0 or b_idx > max_hit_idx or b_idx in blocos_com_hit:
                continue
            linhas_raw = h.get("linhas")
            if isinstance(linhas_raw, str):
                linhas_raw = [linhas_raw]
            linhas = [
                restaurar_acentos_ptbr(sanitizar_texto(str(ln))).upper()[:22]
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
        avisos.append("Menos de 3 destaques de impacto validos: completando automaticamente com base no roteiro.")
        blocos_hist = blocos_validos[: max_hit_idx + 1]
        hits_validos = _escolher_katana_hits(blocos_hist, total_desejado=4 if len(blocos_hist) >= 6 else 3)

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
    """Gera roteiro_XX.txt, cenas.json (schema 8.0 cinematografico IA 30fps) e flag tem_parte_2."""
    blocos = plano["blocos"]
    hits_por_bloco: dict[int, dict] = {int(h["bloco_idx"]): h for h in plano["katana_hits"]}

    palavras_por_bloco = [len(b["texto"].split()) for b in blocos]
    total_palavras = sum(palavras_por_bloco)
    tem_parte_2 = total_palavras > LIMITE_PALAVRAS_PARTE_2
    tem_cta_final = len(blocos) >= 3 and _eh_bloco_cta_final(blocos[-1]["texto"])
    idx_twist = len(blocos) - 2 if tem_cta_final else len(blocos) - 1

    # Sem pausa comercial no meio; define apenas [CORTE_PARTE_2] quando > 130 palavras
    acum = 0
    idx_corte: int | None = None
    if tem_parte_2 and len(blocos) >= 4:
        alvo_corte = total_palavras * 0.48
        melhor_idx = max(2, len(blocos) // 2)
        melhor_dist = float("inf")
        limite_sup_corte = max(2, idx_twist - 1)
        for i in range(1, len(blocos) - 1):
            acum += palavras_por_bloco[i - 1]
            dist = abs(acum - alvo_corte)
            if dist < melhor_dist and 2 <= i <= limite_sup_corte:
                melhor_dist = dist
                melhor_idx = i
        idx_corte = melhor_idx

    linhas_rot: list[str] = [
        f'ROTEIRO {video_id:02d}: "{plano["titulo"].upper()}"',
        f"Formato: YouTube Shorts / Reels 9:16 (1080x1920 @ 30fps) | {'Serie em 2 Partes' if tem_parte_2 else 'Short Unico'} (Motor V8.0 Cinematografico IA)",
        "Gerado automaticamente por pipeline/diretor_ia.py | Estacao 3: gerar_midia_cenas.py + render/renderizar.py",
        "Perfis vocais: narrador_tenso, panico, interfone_porteiro, voz_telefone, sussurro_twist.",
        "Retencao continua: 1 corte visual novo a cada 3s-4s; zero pausa comercial no meio; apenas 1 frase curta no final.",
        "",
        "Estrutura de cada bloco:",
        "[Tempo em Segundos] | [Texto Exato da Narracao com Tags VOZ] | [Direcao visual cinematografica] | [Eventos e pausas]",
        "",
        "============================================================",
        "",
        f"BLOCO INICIAL: {plano['titulo'].upper()} ({plano['horario']})",
        "",
    ]

    cenas_json_lista: list[dict] = []
    t_cursor = 0.0
    palavras_vermelhas: set[str] = {
        "sozinho", "sozinha", "escuro", "escura", "vulto", "sombra", "silencio",
        "sangue", "medo", "panico", "olhos", "sorriu", "sorri", "atras", "dentro",
        "vazio", "vazia", "ninguem", "alguem", "camera", "espelho", "porta", "travou",
        "neblina", "pedagio", "lama", "palida", "morto", "morta", "proibido", "proibida",
    }

    for i, b in enumerate(blocos):
        if idx_corte is not None and i == idx_corte:
            t_c = int(round(t_cursor))
            linhas_rot.extend(
                [
                    "============================================================",
                    f"[{t_c:02d} - {t_c:02d}] | [CORTE_PARTE_2] | Ponto de corte automatico FFmpeg entre Parte 1 e Parte 2. | corte_parte_2",
                    "============================================================",
                    "",
                    "CONTINUACAO: A REVELACAO",
                    "",
                ]
            )

        cena_id = f"cena_{i + 1:02d}"
        dur_est = max(2.2, len(b["texto"].split()) / PALAVRAS_POR_SEGUNDO_EST)
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

        if i == idx_twist:
            if hit is not None:
                eventos_bloco.append(f"plot_twist@{hit['palavra_gatilho']}")
            else:
                eventos_bloco.append("plot_twist")

        if tem_cta_final and i == len(blocos) - 1:
            eventos_bloco.append("cta")
            eventos_bloco.append("pausa=0.20")
        elif i == len(blocos) - 1:
            eventos_bloco.append("pausa=0.18")

        ev_str = ", ".join(eventos_bloco)
        perfil = b["perfil_voz"]
        prompt_img = garantir_estilo_prompt_imagem(str(b.get("prompt_imagem", "")))
        direcao = f"Tomada {cena_id} (cam={b['camera']}, mood={b['mood']}): {prompt_img[:90]}"
        linhas_rot.append(
            f"[{t0:02d} - {t1:02d}] | [VOZ:{perfil}] {b['texto']} [/VOZ] | {direcao} | {ev_str}"
        )

        sfx_dep = b.get("sfx_depois")
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
                "fala": b["texto"],
                "prompt_imagem": prompt_img,
                "camera": b["camera"],
                "mood": b["mood"],
                "vig": 0.72 if b["mood"] in ("red", "dark") else 0.58,
                "duracao_estimada_s": round(dur_est, 2),
                "tensao": b["mood"] == "red" or b["camera"] == "shake_impact" or i == idx_twist,
            }
        )

    linhas_rot.extend(
        [
            "",
            "============================================================",
            "NOTAS TECNICAS V8.0 (MOTOR CINEMATOGRAFICO DE CORTES RAPIDOS IA 30FPS)",
            f"- Palavras faladas: {total_palavras} | Total de cenas visuais: {len(cenas_json_lista)} (~{t_cursor / max(1, len(cenas_json_lista)):.1f}s por corte).",
            f"- Palavras de destaque vermelho: {', '.join(' / '.join(h['linhas']) for h in plano['katana_hits'])}.",
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

    cta_final_texto = blocos[-1]["texto"] if tem_cta_final else CTA_FINAL_PADRAO
    cenas_json = {
        "schema_version": SCHEMA_VERSION,
        "motor": MOTOR_RENDER_PADRAO,
        "video_id": video_id,
        "slug": slug,
        "titulo": plano["titulo"],
        "parte_label": "",
        "horario": plano["horario"],
        "cta_modo": "final",
        "tem_parte_2": tem_parte_2,
        "estilo_visual_prompt": ESTILO_VISUAL_PROMPT_IMAGEM,
        "paleta": plano["paleta"],
        "protagonista": plano["protagonista"],
        "cta": {
            "modo": "final",
            "texto": cta_final_texto,
        },
        "cenas": cenas_json_lista,
        "katana_hits": katana_saida,
        "palavras_vermelhas": sorted(palavras_vermelhas),
    }

    return "\n".join(linhas_rot), cenas_json, tem_parte_2


def validar_cenas_json(cenas: dict) -> list[str]:
    """Validador estrito do schema cenas.json V8.0 (Motor Cinematografico IA 30fps; lista vazia = valido)."""
    erros: list[str] = []
    if not isinstance(cenas, dict):
        return ["cenas.json precisa ser um objeto JSON."]
    if cenas.get("schema_version") != SCHEMA_VERSION:
        erros.append(f"schema_version={cenas.get('schema_version')!r} (esperado {SCHEMA_VERSION!r}).")
    if cenas.get("motor") != MOTOR_RENDER_PADRAO:
        erros.append(f"motor={cenas.get('motor')!r} (esperado {MOTOR_RENDER_PADRAO!r}).")
    if not isinstance(cenas.get("video_id"), int) or cenas["video_id"] < 1:
        erros.append("video_id precisa ser inteiro >= 1.")
    if not str(cenas.get("titulo", "")).strip():
        erros.append("titulo ausente.")
    if not RE_HORARIO.fullmatch(str(cenas.get("horario", ""))):
        erros.append(f"horario invalido: {cenas.get('horario')!r}.")

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
        cam_anterior = ""
        prompts_vistos: set[str] = set()
        for idx, c in enumerate(lista_cenas):
            if not isinstance(c, dict):
                erros.append(f"cenas[{idx}] invalido.")
                continue
            p_img = str(c.get("prompt_imagem", "")).strip()
            if len(p_img) < 40:
                erros.append(f"cenas[{idx}].prompt_imagem ausente ou curto demais.")
            else:
                p_low = p_img.lower()
                if "no watermark" not in p_low or "9:16" not in p_low:
                    erros.append(f"cenas[{idx}].prompt_imagem sem estilo cinematografico travado (9:16 / no watermark).")
                if p_low in prompts_vistos:
                    erros.append(f"cenas[{idx}].prompt_imagem duplicado de cena anterior.")
                prompts_vistos.add(p_low)

            if c.get("mood") not in MOODS_VALIDOS:
                erros.append(f"cenas[{idx}].mood invalido: {c.get('mood')!r}.")

            cam = c.get("camera")
            if cam not in CAMERAS_VALIDAS:
                erros.append(f"cenas[{idx}].camera invalida: {cam!r}.")
            elif cam == cam_anterior:
                erros.append(f"cenas[{idx}].camera repete a camera consecutiva anterior ({cam!r}).")
            cam_anterior = str(cam or "")

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
    pilar: str | None = None,
) -> tuple[int, str, dict, dict]:
    """Prepara e valida o proximo registro V8 em memoria antes de gravar qualquer arquivo."""
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
        "saida": f"output/short_{novo_id:02d}.mp4",
        "status": "em_producao",
        "motor": MOTOR_RENDER_PADRAO,
        "parte_label": "",
        "cta_modo": "final",
    }
    if pilar and pilar in PILARES_POR_ID:
        registro["pilar"] = pilar
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
    """Confere marcadores obrigatorios V6, ausencia de pausa comercial no meio e ausencia de emoji/travessao."""
    erros: list[str] = []
    if "[VOZ:" not in texto_roteiro:
        erros.append("roteiro gerado sem tags [VOZ:perfil].")
    if "[CTA_PAUSA]" in texto_roteiro or "[VOZ:cta_comercial]" in texto_roteiro:
        erros.append("roteiro gerado nao pode conter pausa comercial [CTA_PAUSA] ou [VOZ:cta_comercial] no meio.")
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
    pilar: str | None = None,
) -> tuple[int, str, dict]:
    """Cria o proximo registro V6 em historico_videos.json e valida Sempre Video Novo."""
    novo_id, slug, registro, copia_dados = _preparar_novo_registro_historico(
        plano=plano,
        roteiro_bruto=roteiro_bruto,
        tem_parte_2=tem_parte_2,
        caminho_historico=caminho_historico,
        pilar=pilar,
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
    pilar_editorial: str | None = None,
) -> dict:
    """Executa o fluxo completo do Diretor IA V8 (GeminiPool multi-chave + Groq fallback) e grava artefatos."""
    carregar_env()
    catalogo_sfx = carregar_catalogo_sfx()
    chaves_gemini = carregar_chaves_gemini(ler_env_arquivo=False)
    groq_key = obter_groq_api_key(ler_env_arquivo=False)
    pool_gemini = GeminiPool(chaves=chaves_gemini, modelos=_montar_lista_modelos(modelo))
    tem_ia_online = (pool_gemini.total_chaves() > 0) or bool(groq_key)
    api_key = chaves_gemini[0][1] if chaves_gemini else ""

    if exigir_gemini:
        if usar_mock:
            raise RuntimeError("Modo --mock e incompativel com --exigir-gemini.")
        if not tem_ia_online:
            raise RuntimeError(
                "Nenhuma credencial de IA valida encontrada em GEMINI_API_KEY, GEMINI_API_KEY_2, "
                "GEMINI_API_KEY_3 ou GROQ_API_KEY."
            )

    if not usar_mock and tem_ia_online:
        nomes_ch = ", ".join(pool_gemini.nomes_chaves()) or "nenhuma"
        print(
            f"Pool IA Estacao 1: {pool_gemini.total_chaves()} chave(s) Gemini [{nomes_ch}] "
            f"| modelos={len(pool_gemini.modelos)} | Groq fallback={'ATIVO (' + GROQ_MODELO_PADRAO + ')' if groq_key else 'desativado'}",
            flush=True,
        )

    avisos: list[str] = []
    titulo_efetivo = titulo
    texto_entrada = str(roteiro_bruto or "").strip()
    veio_de_inedito = False
    modelo_ativo_ref: dict[str, str] = {}
    pilar_selecionado: dict[str, str] | None = None

    if pilar_editorial:
        pilar_selecionado = selecionar_proximo_pilar({}, 1, pilar_forcado=pilar_editorial)

    if gerar_inedito or not texto_entrada:
        dados_hist = carregar_historico(caminho_historico)
        prox_id = proximo_numero_livre(dados_hist)
        pilar_selecionado = selecionar_proximo_pilar(
            dados_hist, prox_id, pilar_forcado=pilar_editorial
        )
        veio_de_inedito = True
        if usar_mock or not tem_ia_online:
            if not usar_mock and not tem_ia_online:
                avisos.append("GEMINI_API_KEY e GROQ_API_KEY ausentes: gerando episodio inedito deterministico offline.")
            titulo_gerado, texto_entrada = gerar_roteiro_inedito_mock(
                dados_hist, titulo_sugerido=titulo, pilar=pilar_selecionado
            )
        else:
            titulo_gerado, texto_entrada = gerar_roteiro_inedito_gemini(
                dados_hist,
                titulo_sugerido=titulo,
                api_key=api_key,
                modelo=modelo,
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
                pilar=pilar_selecionado,
                pool=pool_gemini,
                groq_api_key=groq_key,
            )
        titulo_efetivo = titulo or titulo_gerado

    limpo_in = sanitizar_texto(texto_entrada)
    if len(limpo_in.split()) < 15:
        raise ValueError("Roteiro bruto muito curto (minimo 15 palavras para gerar Short V8).")

    origem = "mock"
    plano_bruto: dict | None = None

    if usar_mock or not tem_ia_online:
        if not usar_mock and not tem_ia_online:
            avisos.append("GEMINI_API_KEY e GROQ_API_KEY ausentes: usando modo deterministico offline.")
        plano_bruto = diretor_mock_deterministico(limpo_in, titulo_forcado=titulo_efetivo, catalogo_sfx=catalogo_sfx)
        origem = "mock_inedito" if veio_de_inedito else "mock"
    else:
        try:
            mod_dir = (
                modelo_ativo_ref.get("modelo", modelo)
                if modelo_ativo_ref.get("provedor") != "groq"
                else modelo
            )
            plano_bruto = chamar_gemini_diretor(
                limpo_in,
                titulo_sugerido=titulo_efetivo,
                api_key=api_key,
                catalogo_sfx=catalogo_sfx,
                modelo=mod_dir,
                urlopen_fn=urlopen_fn,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
                pilar=pilar_selecionado,
                pool=pool_gemini,
                groq_api_key=groq_key,
            )
            modelo_usado = modelo_ativo_ref.get("modelo", modelo)
            prov_usado = modelo_ativo_ref.get("provedor", "gemini")
            if prov_usado == "groq":
                origem = f"groq_inedito:{modelo_usado}" if veio_de_inedito else f"groq:{modelo_usado}"
            else:
                origem = f"gemini_inedito:{modelo_usado}" if veio_de_inedito else f"gemini:{modelo_usado}"
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, RuntimeError, ValueError, TimeoutError) as exc:
            if exigir_gemini:
                raise RuntimeError(
                    f"Falha no Diretor IA (GeminiPool + Groq) em modo --exigir-gemini ({type(exc).__name__}: {exc})."
                ) from exc
            avisos.append(f"Falha no GeminiPool/Groq ({type(exc).__name__}: {exc}): fallback deterministico ativado.")
            plano_bruto = diretor_mock_deterministico(
                limpo_in, titulo_forcado=titulo_efetivo, catalogo_sfx=catalogo_sfx
            )
            origem = "fallback_mock"

    plano, avisos_val = validar_e_corrigir_plano(plano_bruto, limpo_in, titulo_efetivo, catalogo_sfx)
    avisos.extend(avisos_val)

    total_palavras = sum(len(b["texto"].split()) for b in plano["blocos"])
    tem_parte_2 = total_palavras > LIMITE_PALAVRAS_PARTE_2
    pilar_id = pilar_selecionado["id"] if pilar_selecionado is not None else None

    # Valida integralmente historico, roteiro e cenas.json em memoria antes de gravar qualquer arquivo
    video_id, slug, registro, copia_historico = _preparar_novo_registro_historico(
        plano=plano,
        roteiro_bruto=limpo_in,
        tem_parte_2=tem_parte_2,
        caminho_historico=caminho_historico,
        pilar=pilar_id,
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
        "pilar": pilar_id,
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
        description=(
            f"Diretor IA V6 ('{CANAL_NOME}'): cria episodio inedito nos "
            f"{len(PILARES_EDITORIAIS)} pilar(es) de config_canal.json ou converte roteiro bruto."
        )
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--roteiro-texto", type=str, help="Texto bruto do roteiro em linha de comando.")
    grupo.add_argument("--arquivo", type=Path, help="Caminho de arquivo .txt com o roteiro bruto.")
    grupo.add_argument(
        "--gerar-inedito",
        action="store_true",
        help="Cria automaticamente um roteiro 100%% inedito via Gemini alternando os pilares de config_canal.json.",
    )
    parser.add_argument("--titulo", type=str, default=None, help="Titulo opcional do video.")
    parser.add_argument(
        "--pilar",
        type=str,
        choices=tuple(p["id"] for p in PILARES_EDITORIAIS),
        default=None,
        help="Forca um dos pilares editoriais de config_canal.json (padrao: alternancia automatica pelo historico).",
    )
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
        pilar_editorial=args.pilar,
    )

    for av in res["avisos"]:
        print(f"AVISO Diretor IA: {av}", flush=True)

    cenas = res["cenas"]
    modulos = ", ".join(c["modulo"] for c in cenas["cenas"])
    hits = ", ".join(" ".join(h["linhas"]) for h in cenas["katana_hits"])
    pilar_info = f", pilar={res['pilar']}" if res.get("pilar") else ""
    print(
        f"Diretor IA V6 concluido ({res['origem']}): Video {res['video_id']:02d} '{res['titulo']}' "
        f"[slug={res['slug']}{pilar_info}, palavras={res['palavras_historia']}, "
        f"{'Parte 1 + Parte 2' if res['tem_parte_2'] else 'Short unico'}]"
    )
    print(f"  Roteiro: {res['roteiro_path']}")
    print(f"  Cenas:   {res['cenas_path']} (schema v{cenas['schema_version']}, {len(cenas['cenas'])} cenas)")
    print(f"  Modulos: {modulos}")
    print(f"  Katana:  {hits}")


if __name__ == "__main__":
    main()
