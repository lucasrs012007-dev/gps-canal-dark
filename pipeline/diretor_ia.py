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

SCHEMA_VERSION = "7.0"
MOTOR_RENDER_PADRAO = "canvas_2d_30fps"
GEMINI_MODELO_PADRAO = MODELOS_TEXTO_GEMINI_PADRAO[0]
GEMINI_MODELOS_FALLBACK: tuple[str, ...] = MODELOS_TEXTO_GEMINI_PADRAO
ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_CATALOGO_SFX = RAIZ / "assets" / "sfx" / "catalogo.json"
ARQUIVO_CENAS_PADRAO = RAIZ / "cenas.json"
LIMITE_PALAVRAS_PARTE_2 = 130
MAX_PALAVRAS_POR_TOMADA = 9
PALAVRAS_POR_SEGUNDO_EST = 3.15

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
    "corredor_escuro",
    "quarto_noturno",
    "elevador_cabine",
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
    "pan_left",
    "pan_right",
    "shake_impact",
    "float_cam",
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


RE_MOEDA_BRL_REDUNDANTE = re.compile(
    r"\b(R\$\s*\d+(?:[.,]\d+)*(?:\s+(?:milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil))?)"
    r"\s+(?:de\s+)?rea(?:is|l)\b",
    flags=re.IGNORECASE,
)
RE_MOEDA_USD_REDUNDANTE = re.compile(
    r"\b(US\$\s*\d+(?:[.,]\d+)*(?:\s+(?:milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil))?)"
    r"\s+(?:de\s+)?d[oó]lar(?:es)?\b",
    flags=re.IGNORECASE,
)


def normalizar_moeda_redundante(texto: str) -> str:
    """Remove redundancia de moeda apos R$/US$ (ex.: 'R$ 48 reais' -> 'R$ 48'), preservando mil/milhoes/bilhoes."""
    out = str(texto or "")
    out = RE_MOEDA_BRL_REDUNDANTE.sub(r"\1", out)
    out = RE_MOEDA_USD_REDUNDANTE.sub(r"\1", out)
    out = re.sub(r"\b(R\$|US\$)\s*(\d)", r"\1 \2", out)
    return out


def sanitizar_texto(texto: str) -> str:
    """Remove emojis, travessoes (em/en-dash), redundancias de moeda e marcadores residuais do texto."""
    limpo = str(texto or "")
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = limpo.replace("|", " ")
    limpo = re.sub(r"\[\s*/?\s*(?:VOZ|SFX|CTA_PAUSA|CORTE_PARTE_2)[^\]]*\]", " ", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"[ \t]+", " ", limpo)
    limpo = normalizar_moeda_redundante(limpo)
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
        "o que faria",
        "voce faria",
        "faria o que",
        "qual seria sua reacao",
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
    "hospital": "corredor_escuro",
    "hospital_corredor": "corredor_escuro",
    "corredor": "corredor_escuro",
    "corredor_hospital": "corredor_escuro",
    "uti": "corredor_escuro",
    "quarto": "quarto_noturno",
    "banheiro": "quarto_noturno",
    "elevador": "elevador_cabine",
    "celular_notificacao": "sala_cozinha",
    "camera_cctv": "laboratorio",
    "carro_noite": "cidade_rua",
    "blecaute_olhos": "big_face",
}

_CENARIOS_INDOOR_ESCUROS: frozenset[str] = frozenset(
    {
        "corredor_escuro",
        "quarto_noturno",
        "elevador_cabine",
        "sala_cozinha",
        "escritorio",
        "laboratorio",
        "big_face",
    }
)

_POSES_CELEBRATORIAS: frozenset[str] = frozenset({"comemorando", "pulando"})

_TERMOS_INDOOR: tuple[str, ...] = (
    "hospital", "uti", "leito", "corredor", "quarto", "sala", "predio",
    "elevador", "porta", "casa", "banheiro", "enfermaria", "enfermeir",
    "clinica", "plantao", "maca", "apartamento", "hotel", "cozinha",
    "escritorio", "cama", "pronto socorro", "recepcao", "portaria",
    "subsolo", "hall", "escada", "escadaria", "macaneta", "fechadura",
)

_TERMOS_RUA_EXTERNA: tuple[str, ...] = (
    "rua", "avenida", "estrada", "rodovia", "asfalto", "transito",
    "carro", "carros", "viatura", "pedagio", "ponte", "semaforo",
    "calcada", "estacionamento",
)

_TERMOS_TERROR_SUSPENSE: tuple[str, ...] = (
    "medo", "panico", "terror", "susto", "horror", "sangue", "morte",
    "morrer", "morto", "morta", "perigo", "ameaca", "assust", "vulto",
    "sombra", "olhos", "atras de voce", "pelas costas", "filmando",
    "espiao", "invasor", "escondido", "grito", "sussurr", "corredor",
    "uti", "leito", "hospital", "escuro", "escuridao", "blecaute",
    "apagao", "sem piscar", "sorrindo", "sorriu", "trancad", "preso",
    "presa", "silencio", "socorro", "fuga", "fugir", "coracao",
    "arrepio", "gelou", "congelou", "paralis", "reflexo", "espelho",
    "vigilancia", "cadaver", "respiracao", "passos", "batida",
    "macaneta", "emergencia", "desaparec", "ameac", "sozinho", "sozinha",
    "ninguem", "alguem", "persegu", "armadilha", "envenen", "asfix",
)

_TERMOS_GRAFICO_ESCALA: tuple[str, ...] = (
    "comparacao", "comparado", "comparar", "vezes maior", "vezes menor",
    "vezes mais", "dobro", "triplo", "multiplic", "crescimento",
    "cresceu", "cresce", "escala", "proporcao", "ranking", "recorde",
    "estatistica", "por cento", "taxa de", "indice", "faturamento",
    "lucro", "investimento", "rendimento", "juros", "mil vezes",
    "2x", "3x", "5x", "10x", "100x",
)

_TERMOS_EXATOS_PALAVRA: frozenset[str] = frozenset(
    {
        "uti", "sala", "casa", "rua", "mar", "ceu", "lua", "ala",
        "maca", "cama", "dna", "hall", "2x", "3x", "5x", "10x", "100x",
        "leito", "porta", "carro", "ponte", "trem", "ilha", "nave",
        "medo", "fuga", "morte", "preso", "presa", "grito", "susto",
        "costa", "onda", "gelo", "agua",
    }
)


def _termo_no_texto(termo: str, norm: str) -> bool:
    """Casamento seguro por palavra inteira para termos curtos e substring para radicais."""
    if not termo or not norm:
        return False
    if termo in _TERMOS_EXATOS_PALAVRA or len(termo) <= 4:
        return bool(re.search(rf"\b{re.escape(termo)}\b", norm))
    return termo in norm


def _eh_contexto_indoor(texto: str) -> bool:
    """Retorna True se o texto indicar ambiente interno (hospital, UTI, corredor, quarto, sala, predio, casa, banheiro)."""
    norm = normalizar_texto(texto)
    return any(_termo_no_texto(t, norm) for t in _TERMOS_INDOOR)


def _tem_pista_rua_externa(texto: str) -> bool:
    """Retorna True apenas quando a fala cita explicitamente rua, transito ou carros externos."""
    norm = normalizar_texto(texto)
    return any(_termo_no_texto(t, norm) for t in _TERMOS_RUA_EXTERNA)


def _eh_cena_terror_ou_suspense(texto: str, mood: str = "", perfil: str = "") -> bool:
    """Identifica cenas de terror, suspense, medo, perigo ou ameaca."""
    m = str(mood or "").strip().lower()
    p = str(perfil or "").strip().lower()
    if m in ("red", "dark", "cctv"):
        return True
    if p in ("panico", "sussurro_twist", "voz_telefone", "interfone_porteiro"):
        return True
    norm = normalizar_texto(texto)
    return any(_termo_no_texto(t, norm) for t in _TERMOS_TERROR_SUSPENSE)


def _texto_permite_grafico_comparacao(
    texto: str,
    mood: str = "",
    perfil: str = "",
    eh_cta: bool = False,
    contexto_terror: bool = False,
) -> bool:
    """Permite arena_comparacao (BASE/2X/MAX) apenas para crescimento/multiplicadores/comparacoes/escala fora de terror/CTA."""
    if eh_cta or _eh_bloco_cta_final(texto):
        return False
    if contexto_terror or _eh_cena_terror_ou_suspense(texto, mood=mood, perfil=perfil):
        return False
    if "%" in str(texto or ""):
        return True
    norm = normalizar_texto(texto)
    return any(_termo_no_texto(t, norm) for t in _TERMOS_GRAFICO_ESCALA)


def _sanitizar_pose_para_tom(
    pose: str,
    texto: str,
    mood: str,
    perfil: str,
    acao_cena: str,
    *,
    eh_cta: bool = False,
    contexto_terror: bool = False,
) -> str:
    """Proibe poses festivas (comemorando/pulando) em cenas de terror, suspense, perigo, mood dark/red ou CTA."""
    pose_limpa = _POSE_ALIASES.get(str(pose or "").strip().lower(), str(pose or "").strip().lower())
    if pose_limpa not in POSES_VALIDAS:
        pose_limpa = "falando"
    if pose_limpa not in _POSES_CELEBRATORIAS:
        return pose_limpa
    if eh_cta:
        return "apontando"
    if contexto_terror or _eh_cena_terror_ou_suspense(texto, mood=mood, perfil=perfil):
        norm = normalizar_texto(texto)
        if acao_cena == "corrida_fuga" or any(k in norm for k in ("correu", "corre", "correndo", "fuga", "fugir", "escap")):
            return "correndo"
        if (
            str(mood or "").strip().lower() in ("red", "dark")
            or str(perfil or "").strip().lower() in ("panico", "sussurro_twist")
            or any(
                _termo_no_texto(k, norm)
                for k in (
                    "medo", "panico", "terror", "susto", "perigo", "ameaca",
                    "assust", "vulto", "sombra", "filmando", "pelas costas",
                    "atras de voce", "olhos", "sangue", "grito", "paralis",
                )
            )
        ):
            return "assustado"
        return "pensando"
    return pose_limpa


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
    "pan_diag_tl": "pan_left",
    "pan_diag_br": "pan_right",
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


_ABERTURAS_LENTAS_PROIBIDAS: tuple[str, ...] = (
    "oi pessoal",
    "ola pessoal",
    "fala galera",
    "e ai galera",
    "e ai pessoal",
    "bem vindo",
    "bem vindos",
    "hoje vamos",
    "hoje eu vou",
    "hoje voce vai",
    "nesse video",
    "neste video",
    "no video de hoje",
    "voce sabia",
    "voce ja parou",
    "voce ja pensou",
    "era uma vez",
    "existe um lugar",
    "existe uma porta",
    "imagine um mundo",
    "quase ninguem percebe",
    "olha pra tela",
    "olha para a tela",
    "olha para tela",
    "olhe pra tela",
    "olhe para a tela",
    "olhe para tela",
    "presta atencao",
    "preste atencao",
    "escuta isso",
    "escute isso",
    "escuta so",
    "escute so",
    "escuta bem",
    "escute bem",
    "ouve isso",
    "ouca isso",
    "ouve so",
    "ouca so",
    "para de rolar",
    "pare de rolar",
    "nao pula esse video",
    "nao passe esse video",
    "fica ate o final",
    "assista ate o final",
)


def _eh_abertura_lenta(texto: str) -> bool:
    """Retorna True se a abertura do roteiro usar saudacao, meta-abertura generica ou gancho lento proibido."""
    inicio = normalizar_texto(texto)[:90]
    if not inicio:
        return True
    return any(inicio.startswith(pref) or f" {pref}" in inicio[:55] for pref in _ABERTURAS_LENTAS_PROIBIDAS)


def _alternar_estado_visual_consecutivo(
    pose_atual: str,
    expr_atual: str,
    pose_ant: str,
    expr_ant: str,
    idx: int,
    *,
    eh_terror: bool = False,
) -> tuple[str, str]:
    """Garante variacao visual de pose ou expressao entre blocos consecutivos (1.5s a 2.5s)."""
    if not pose_ant and not expr_ant:
        return pose_atual, expr_atual
    if pose_atual != pose_ant or expr_atual != expr_ant:
        return pose_atual, expr_atual
    ciclo_poses = (
        ("assustado", "pensando", "correndo", "apontando", "em_pe", "falando")
        if eh_terror
        else ("apontando", "assustado", "falando", "pensando", "correndo", "em_pe")
    )
    ciclo_exprs = ("shock", "fear", "worry", "focus") if eh_terror else ("shock", "focus", "fear", "worry", "smug")
    nova_pose = next((p for p in ciclo_poses[idx % len(ciclo_poses):] + ciclo_poses[:idx % len(ciclo_poses)] if p != pose_ant), pose_atual)
    nova_expr = next((e for e in ciclo_exprs[idx % len(ciclo_exprs):] + ciclo_exprs[:idx % len(ciclo_exprs)] if e != expr_ant), expr_atual)
    return nova_pose, nova_expr


def _parse_num_ptbr(raw: str) -> float:
    s = str(raw or "").strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 1.0


def extrair_hud_dado(texto: str, hud_raw: object = None) -> dict | None:
    """Extrai medidor/contador animado (rotulo, valor, progresso) para numeros, dias, niveis, dinheiro e medidas."""
    valido = _normalizar_hud_raw(hud_raw)
    if valido is not None:
        return valido

    limpo = sanitizar_texto(texto)
    norm = normalizar_texto(limpo)
    num_pat = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"

    # 0A. Dinheiro / valores monetarios (ex.: R$ 100, R$ 50 mil, R$ 10 milhoes, 500 reais, US$ 1 milhao)
    m_din = re.search(
        rf"(?:(R\$|US\$|\$)\s*({num_pat})(?:\s*(milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil))?"
        rf"|({num_pat})(?:\s*(milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil))?\s*(?:de\s+)?(reais|real|d[oó]lares|d[oó]lar|euros?))",
        limpo,
        flags=re.IGNORECASE,
    )
    if m_din:
        if m_din.group(1):
            moeda = m_din.group(1).upper()
            n_str = m_din.group(2)
            escala = (m_din.group(3) or "").upper()
            val = f"{moeda} {n_str}" + (f" {escala}" if escala else "")
        else:
            n_str = m_din.group(4)
            escala = (m_din.group(5) or "").upper()
            unid_m = m_din.group(6).lower()
            pref = "US$" if "dol" in unid_m or "dól" in unid_m else ("EUR" if "eur" in unid_m else "R$")
            val = f"{pref} {n_str}" + (f" {escala}" if escala else "")
        rot = "PRÊMIO" if any(k in norm for k in ("premio", "ganhar", "pagar", "receber", "aceitaria")) else "VALOR"
        return {"rotulo": rot, "valor": val[:22], "progresso": 0.88}

    # 0B. Niveis / estagios / categorias (ex.: nivel 5, estagio 3, alerta 4, categoria 5)
    m_niv = re.search(
        r"\b(n[ií]vel|est[aá]gio|categoria|alerta|fase|grau)\s+(?:de\s+alerta\s+)?(\d{1,2})\b",
        limpo,
        flags=re.IGNORECASE,
    )
    if m_niv:
        rot_raw = m_niv.group(1).upper()
        n_val = int(m_niv.group(2))
        prog = round(max(0.18, min(1.0, n_val / (5.0 if n_val <= 5 else 10.0))), 2)
        rot = "NÍVEL DE ALERTA" if "nivel" in normalizar_texto(rot_raw) or "alerta" in normalizar_texto(rot_raw) else rot_raw
        return {"rotulo": rot, "valor": f"{rot_raw} {n_val}", "progresso": prog}

    # 0C. Marcador explicito de dia (ex.: Dia 1, Dia 14, Dia 30)
    m_dia_mar = re.search(r"\bdia\s+(\d{1,3})\b", limpo, flags=re.IGNORECASE)
    if m_dia_mar:
        n_dia = int(m_dia_mar.group(1))
        prog = round(max(0.12, min(1.0, n_dia / (30.0 if n_dia <= 30 else 100.0))), 2)
        return {"rotulo": "CRONÔMETRO", "valor": f"DIA {n_dia}", "progresso": prog}

    # 1. Porcentagens (ex.: 90%, 99,5%, 50 por cento)
    m_pct = re.search(rf"({num_pat})\s*(?:%|por\s+cento\b)", limpo, flags=re.IGNORECASE)
    if m_pct:
        num_f = _parse_num_ptbr(m_pct.group(1))
        val_txt = m_pct.group(1).replace(".", ",") + "%"
        return {"rotulo": "TAXA / ÍNDICE", "valor": val_txt, "progresso": round(max(0.08, min(1.0, num_f / 100.0)), 2)}

    # 2. Velocidades (ex.: 120 km/h)
    m_vel = re.search(rf"({num_pat})\s*(km/h|m/s|quil[oô]metros\s+por\s+hora)", limpo, flags=re.IGNORECASE)
    if m_vel:
        num_f = _parse_num_ptbr(m_vel.group(1))
        unid = "M/S" if "m/s" in m_vel.group(2).lower() else "KM/H"
        return {"rotulo": "VELOCIDADE", "valor": f"{m_vel.group(1)} {unid}", "progresso": round(max(0.15, min(1.0, num_f / 300.0)), 2)}

    # 3. Distancias (ex.: 5 km, 300 metros, 2.600 km, 5.000 quilometros)
    m_dist = re.search(
        rf"({num_pat})\s*(km|quil[oô]metros?|metros?|m\b|milhas?)",
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
        num_f = _parse_num_ptbr(num_str)
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
    m_temp = re.search(rf"(-?{num_pat})\s*(?:°c|graus?(?:\s+negativos?)?)", limpo, flags=re.IGNORECASE)
    if m_temp:
        neg = "negativo" in m_temp.group(0).lower() and not m_temp.group(1).startswith("-")
        val_t = f"-{m_temp.group(1)} °C" if neg else f"{m_temp.group(1)} °C"
        return {"rotulo": "TEMPERATURA", "valor": val_t, "progresso": 0.78}

    # 6. Duracoes (ex.: 48 horas, 60 segundos, 30 dias, 40 minutos)
    m_dur = re.search(
        rf"({num_pat})\s*(segundos?|minutos?|horas?|dias?|anos?)",
        limpo,
        flags=re.IGNORECASE,
    )
    if m_dur:
        num_str = m_dur.group(1)
        unid = m_dur.group(2).upper()
        rot = (
            "OXIGÊNIO" if "oxigenio" in norm else (
                "CONTAGEM DE DIAS" if "DIA" in unid else ("CONTAGEM" if "SEGUNDO" in unid else "TEMPO")
            )
        )
        num_f = _parse_num_ptbr(num_str)
        prog = round(max(0.20, min(0.95, num_f / (60.0 if num_f <= 60 else 120.0))), 2)
        return {"rotulo": rot, "valor": f"{num_str} {unid}", "progresso": prog}

    # 7. Grandes escalas / quantias (ex.: 10 milhoes, 1 milhao, 5 mil)
    m_esc = re.search(rf"({num_pat})\s*(milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|mil)\b", limpo, flags=re.IGNORECASE)
    if m_esc:
        return {"rotulo": "ESCALA", "valor": f"{m_esc.group(1)} {m_esc.group(2).upper()}", "progresso": 0.86}

    # 8. Numeros por extenso comuns com unidade (ex.: "cinco quilometros", "quarenta e oito horas", "trinta dias", "dez mil reais")
    m_ext = re.search(
        r"\b(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|doze|quinze|vinte|trinta|quarenta|cinquenta|sessenta|cem|cento|duzentos|trezentos|quinhentos|mil)\b"
        r"(?:\s+e\s+(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|vinte|trinta|quarenta|cinquenta|sessenta|oitenta|noventa))?"
        r"\s+(quilometros?|metros?|horas?|minutos?|segundos?|dias?|anos?|graus?|reais|dolares|milhoes?|milhao|bilhoes?)",
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
            elif "reais" in unid_raw or "dolar" in unid_raw:
                pref = "US$" if "dolar" in unid_raw else "R$"
                return {"rotulo": "VALOR", "valor": f"{pref} {total_n}", "progresso": 0.84}
            elif "milh" in unid_raw:
                unid_fmt, rot = "MILHÕES", "ESCALA"
            elif "bilh" in unid_raw:
                unid_fmt, rot = "BILHÕES", "ESCALA"
            else:
                unid_fmt = unid_raw.upper()
                rot = "OXIGÊNIO" if "oxigenio" in norm else ("CONTAGEM DE DIAS" if "dia" in unid_raw else "CONTAGEM")
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
    mood: str = "",
    perfil: str = "",
) -> str:
    """Escolhe o cenario 2D animado fiel as palavras-chave reais da fala atual."""
    norm = normalizar_texto(texto)
    norm_g = normalizar_texto(contexto_global)
    ctx_indoor = _eh_contexto_indoor(contexto_global) if contexto_global else False
    local_indoor = _eh_contexto_indoor(texto)
    tem_rua_local = _tem_pista_rua_externa(texto)
    bloquear_rua = (local_indoor or ctx_indoor) and not tem_rua_local
    eh_terror_global = bool(contexto_global) and _eh_cena_terror_ou_suspense(contexto_global)
    eh_terror_local = _eh_cena_terror_ou_suspense(texto, mood=mood, perfil=perfil)
    permite_grafico = _texto_permite_grafico_comparacao(
        texto,
        mood=mood,
        perfil=perfil,
        eh_cta=eh_cta,
        contexto_terror=eh_terror_local or eh_terror_global,
    )

    if eh_cta or _eh_bloco_cta_final(texto):
        cands_cta = (
            ("big_face", "corredor_escuro", "quarto_noturno", "sala_cozinha")
            if (ctx_indoor or local_indoor)
            else ("big_face", "laboratorio", "escritorio", "sala_cozinha")
        )
        for cand in cands_cta:
            if cand != anterior:
                return cand
        return "big_face"

    pontos_local: dict[str, float] = {c: 0.0 for c in CENARIOS_ANIMADOS}
    pontos_ctx: dict[str, float] = {c: 0.0 for c in CENARIOS_ANIMADOS}

    regras: dict[str, tuple[tuple[str, ...], float]] = {
        "corredor_escuro": (
            (
                "hospital", "uti", "enfermaria", "enfermeir", "clinica", "pronto socorro",
                "corredor", "corredor branco", "corredor escuro", "predio", "hall",
                "escada", "escadaria", "porta", "macaneta", "fechadura", "subsolo",
                "recepcao", "portaria", "plantao", "maca", "ala",
            ),
            4.8,
        ),
        "quarto_noturno": (
            (
                "quarto", "leito", "cama", "travesseiro", "cobertor", "guarda roupa",
                "armario", "dormindo", "acorda", "acordou", "banheiro", "chuveiro",
                "cortina", "hotel",
            ),
            4.7,
        ),
        "elevador_cabine": (
            (
                "elevador", "cabine", "botoeira", "terreo",
            ),
            4.8,
        ),
        "oceano_ilha": (
            (
                "ilha", "ilhas", "sentinela", "mar", "oceano", "barco", "pescador",
                "tsunami", "onda", "navio", "submarino", "costa", "praia", "agua",
                "peixe", "peixes", "pacifico", "ponto nemo", "marinha", "casco",
                "escotilha", "gelo", "debaixo da agua", "fundo do mar",
                "abismo", "profundidade", "ilha isolada", "resgate no mar",
            ),
            4.5,
        ),
        "espaco_orbita": (
            (
                "espaco", "espacia", "orbita", "planeta", "lua", "marte", "satelite",
                "satelites", "asteroide", "estrela", "estacao espacial", "nave",
                "naves", "galaxia", "universo", "foguete", "gravidade zero", "cosmo",
            ),
            4.6,
        ),
        "ceu_nuvens": (
            (
                "ceu", "nuvem", "nuvens", "aviao", "helicoptero", "sobrevo", "voar",
                "voando", "altitude", "tempestade", "raio", "trov", "paraquedas",
                "teleferico", "atmosfera", "helice", "resgate aereo",
            ),
            4.2,
        ),
        "floresta_noite": (
            (
                "floresta", "mata", "selva", "arvore", "arvores", "tribo", "flecha",
                "flechas", "arco", "lanca", "trilha", "neblina", "animais", "caverna",
                "ilha fechada", "escuro na mata", "vagalume",
            ),
            4.2,
        ),
        "laboratorio": (
            (
                "laboratorio", "cientista", "ciencia", "experimento", "radar", "sonar",
                "microfone", "microfones", "hidrofone", "sensor", "sensores", "estudo",
                "pesquisa", "dna", "cerebro", "cofre", "semente", "sementes", "svalbard",
                "radio", "sinal", "camera", "filmando", "vigilancia", "monitor cardiaco",
                "protocolo", "governo", "governos", "arquivo", "gravaram", "rugido",
                "captaram",
            ),
            4.0,
        ),
        "cidade_rua": (
            (
                "cidade", "rua", "avenida", "transito", "asfalto", "metro", "vagao",
                "tunel", "estacao", "carro", "carros", "estacionamento", "ponte",
                "sirene", "viatura", "pedagio", "estrada", "rodovia", "calcada",
                "semaforo", "trem", "trilhos", "garagem",
            ),
            4.0,
        ),
        "escritorio": (
            (
                "escritorio", "monitor", "monitores", "mesa", "computador", "teclado",
                "lapiseira", "xicara", "teto de gesso", "carpete", "chefe", "empresa",
                "reuniao", "andar comercial", "cadeira",
            ),
            4.0,
        ),
        "sala_cozinha": (
            (
                "casa", "cozinha", "sala", "sofa", "geladeira", "apartamento",
                "espelho", "janela de casa", "celular", "interfone",
                "baba eletronica", "reflexo", "vidro",
            ),
            4.1,
        ),
        "arena_comparacao": (
            (
                "comparacao", "comparado", "comparar", "vezes maior", "vezes menor",
                "vezes mais", "dobro", "triplo", "multiplic", "crescimento",
                "cresceu", "escala", "proporcao", "ranking", "recorde",
                "estatistica", "por cento", "faturamento", "lucro", "investimento",
                "rendimento", "juros", "2x", "3x", "5x", "10x", "100x",
            ),
            3.8,
        ),
        "big_face": (
            (
                "coracao", "panico", "susto", "terror", "olhos", "sem piscar", "sorrindo",
                "atras de voce", "pelas costas", "voce paralisa", "silencio",
                "ninguem voltou", "nunca mais", "revelacao", "choque", "medo",
                "alerta maximo", "escondido",
            ),
            3.8,
        ),
    }

    for cen, (termos, peso) in regras.items():
        if cen == "arena_comparacao" and not permite_grafico:
            continue
        if cen == "cidade_rua" and bloquear_rua:
            continue
        for termo in termos:
            if _termo_no_texto(termo, norm):
                pontos_local[cen] += peso
            elif norm_g and _termo_no_texto(termo, norm_g) and cen not in ("espaco_orbita", "arena_comparacao", "cidade_rua"):
                pontos_ctx[cen] += peso * 0.14

    if bloquear_rua:
        pontos_local["cidade_rua"] = 0.0
        pontos_ctx["cidade_rua"] = 0.0
    if not permite_grafico:
        pontos_local["arena_comparacao"] = 0.0
        pontos_ctx["arena_comparacao"] = 0.0

    # 1. Palavras-chave diretas da fala atual SEMPRE vencem
    melhor_local = max(CENARIOS_ANIMADOS, key=lambda c: (pontos_local[c], 1 if c != anterior else 0))
    if pontos_local[melhor_local] >= 3.0:
        return melhor_local

    # 2. Para falas puramente narrativas/numericas sem palavra de cenario direta:
    pontos_totais = {c: pontos_local[c] + pontos_ctx[c] for c in CENARIOS_ANIMADOS}
    if hud_dado is not None:
        if permite_grafico:
            pontos_totais["arena_comparacao"] += 2.6
        elif ctx_indoor or local_indoor:
            pontos_totais["corredor_escuro"] += 1.4
            pontos_totais["laboratorio"] += 1.0
        else:
            pontos_totais["laboratorio"] += 1.4
    if eh_twist:
        pontos_totais["big_face"] += 4.5

    ordenados = sorted(
        CENARIOS_ANIMADOS,
        key=lambda c: (pontos_totais[c], -abs((CENARIOS_ANIMADOS.index(c) - idx) % len(CENARIOS_ANIMADOS))),
        reverse=True,
    )
    for cand in ordenados:
        if cand == "espaco_orbita" and pontos_local["espaco_orbita"] <= 0:
            continue
        if cand == "arena_comparacao" and not permite_grafico:
            continue
        if cand == "cidade_rua" and bloquear_rua:
            continue
        if bloquear_rua and cand not in _CENARIOS_INDOOR_ESCUROS:
            continue
        if cand != anterior and pontos_totais[cand] > 0.2:
            return cand

    # Fallback neutro seguro (indoor permanece indoor; nunca usa arena_comparacao ou espaco_orbita como fallback)
    if bloquear_rua:
        ciclo_fallback = (
            "corredor_escuro", "quarto_noturno", "big_face",
            "sala_cozinha", "laboratorio", "escritorio",
        )
    else:
        ciclo_fallback = (
            "corredor_escuro", "laboratorio", "big_face", "oceano_ilha",
            "ceu_nuvens", "cidade_rua", "floresta_noite", "escritorio", "sala_cozinha",
        )
    for offset in range(len(ciclo_fallback)):
        cand = ciclo_fallback[(idx + offset) % len(ciclo_fallback)]
        if cand != anterior:
            return cand
    return "corredor_escuro" if (bloquear_rua and anterior != "corredor_escuro") else (
        "big_face" if anterior != "big_face" else "laboratorio"
    )


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
    if re.search(r"\b(correu|correndo|corre|correr|corrida|fuga|fugir|fugiu|escap\w*|persegu\w*|apressad\w*)\b", norm):
        return "corrida_fuga"
    if cenario == "arena_comparacao" or (hud_dado is not None and _texto_permite_grafico_comparacao(texto)):
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
    mood: str = "navy",
    contexto_terror: bool = False,
) -> str:
    """Seleciona uma das 10 poses animadas coerente com a fala e acao da cena (sem comemoracao em terror/suspense)."""
    norm = normalizar_texto(texto)
    eh_terror = contexto_terror or _eh_cena_terror_ou_suspense(texto, mood=mood, perfil=perfil)
    if eh_cta:
        return "apontando"
    if any(k in norm for k in ("despenca", "queda livre", "caindo", "caiu", "direcao ao chao")):
        return "caindo"
    if gravidade_zero or acao_cena == "flutuando_gravidade" or any(k in norm for k in ("flutu", "levit", "gravidade", "orbita")):
        return "flutuando"
    if acao_cena == "corrida_fuga" or re.search(r"\b(correu|correndo|corre|correr|fuga|fugir|fugiu|escap\w*)\b", norm):
        return "correndo"
    if (
        eh_terror
        or perfil in ("panico", "sussurro_twist")
        or acao_cena in ("chuva_flechas", "onda_gigante", "explosao_choque")
    ):
        if (
            perfil in ("panico", "sussurro_twist")
            or str(mood or "").strip().lower() in ("red", "dark")
            or acao_cena in ("chuva_flechas", "onda_gigante", "explosao_choque")
            or any(
                _termo_no_texto(k, norm)
                for k in (
                    "panico", "medo", "susto", "terror", "choque", "assust", "perigo",
                    "ameaca", "filmando", "pelas costas", "atras de voce", "vulto",
                    "sombra", "olhos", "sangue", "grito", "paralis", "trancad",
                )
            )
        ):
            return "assustado"
        return "pensando"
    if any(k in norm for k in ("pulou", "pula", "salta", "saltou", "pular")):
        return "pulando"
    if any(k in norm for k in ("venceu", "sobreviveu", "conseguiu", "comemor", "milhoes", "premio")):
        return "comemorando"
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
    if (acao_cena == "flutuando_gravidade" or cenario in ("espaco_orbita", "oceano_ilha", "ceu_nuvens")) and anterior != "float_cam":
        return "float_cam"

    ciclo = ("push_in", "pan_right", "pull_out", "pan_left", "float_cam", "shake_impact")
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


_NAO_TERMINAR_CHUNK: frozenset[str] = frozenset(
    {
        "o", "a", "os", "as", "um", "uma", "uns", "umas",
        "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
        "por", "pelo", "pela", "para", "pro", "pra", "com", "sem", "sob", "sobre",
        "entre", "ate", "que", "e", "ou", "mas", "nem", "se", "como", "quando", "onde",
        "era", "sao", "estao", "esta", "foi", "vai", "tem", "r$", "us$", "nivel", "dia",
        "la", "ca", "debaixo", "acima", "dentro", "fora",
    }
)
_UNIDADES_NUM_CHUNK: frozenset[str] = frozenset(
    {
        "km", "m", "metro", "metros", "quilometro", "quilometros", "milha", "milhas",
        "mil", "milhao", "milhoes", "bilhao", "bilhoes", "real", "reais", "dolar", "dolares",
        "dia", "dias", "hora", "horas", "minuto", "minutos", "segundo", "segundos",
        "ano", "anos", "grau", "graus", "por", "cento", "%",
    }
)


def _dividir_fala_em_tomadas_curtas(
    texto: str,
    max_palavras: int = MAX_PALAVRAS_POR_TOMADA,
) -> list[str]:
    """Divide qualquer fala longa em tomadas curtas naturais sem cortar artigos/preposicoes nem unidades."""
    limpo = sanitizar_texto(texto)
    if not limpo:
        return []
    palavras = limpo.split()
    if len(palavras) <= max_palavras:
        return [limpo]

    # 1. Primeiro divide por frases completas (. ! ?)
    frases = [f.strip() for f in RE_SEPARAR_FRASES.split(limpo) if f.strip()]
    resultado: list[str] = []
    conjuncoes = frozenset({"e", "mas", "quando", "porque", "onde", "enquanto", "entao", "ate", "como", "que", "so", "nem"})
    preposicoes_inicio = frozenset({"de", "do", "da", "em", "no", "na", "para", "com", "um", "uma", "por"})

    for frase in frases:
        pals = frase.split()
        if len(pals) <= max_palavras:
            resultado.append(frase)
            continue

        # 2. Divide frase longa respeitando pausas naturais, nunca deixando artigo/preposicao solto no fim
        num_partes = 3 if len(pals) > max_palavras * 2 else 2
        alvo = max(4, round(len(pals) / num_partes))
        cursor = 0
        for p_idx in range(num_partes):
            if cursor >= len(pals):
                break
            if p_idx == num_partes - 1:
                trecho = " ".join(pals[cursor:]).strip()
                if trecho:
                    resultado.append(trecho)
                break
            fim_ideal = min(len(pals) - 3, cursor + alvo)
            if fim_ideal <= cursor + 2:
                trecho = " ".join(pals[cursor:]).strip()
                if trecho:
                    resultado.append(trecho)
                break

            melhor_corte = fim_ideal
            melhor_score = 999.0
            janela_ini = max(cursor + 3, fim_ideal - 4)
            janela_fim = min(len(pals) - 2, fim_ideal + 3)
            for k in range(janela_ini, janela_fim + 1):
                tok_ant_raw = pals[k - 1]
                tok_atu_raw = pals[k]
                tok_ant = normalizar_texto(tok_ant_raw)
                tok_atu = normalizar_texto(tok_atu_raw)
                score = float(abs(k - fim_ideal))

                # Forte bonus apos virgula/ponto-e-virgula/dois-pontos
                if tok_ant_raw.endswith((",", ";", ":")):
                    score -= 4.0
                elif tok_atu in conjuncoes:
                    score -= 2.5
                elif tok_atu in preposicoes_inicio:
                    score -= 1.2

                # Penaliza fortemente deixar preposicao/artigo/auxiliar pendurado no fim do chunk
                if tok_ant in _NAO_TERMINAR_CHUNK or tok_ant_raw.lower() in ("r$", "us$"):
                    score += 18.0
                # Penaliza cortar entre numero/moeda e unidade (ex.: "10" + "milhoes", "2.600" + "km", "15" + "dias")
                if (re.search(r"\d", tok_ant_raw) and (tok_atu in _UNIDADES_NUM_CHUNK or re.search(r"\d", tok_atu_raw))) or (
                    tok_ant in ("nivel", "dia", "hora", "r", "us") and re.search(r"\d", tok_atu_raw)
                ):
                    score += 24.0

                if score < melhor_score:
                    melhor_score = score
                    melhor_corte = k

            trecho = " ".join(pals[cursor:melhor_corte]).strip()
            if trecho:
                resultado.append(trecho)
            cursor = melhor_corte

    # Reagrupa fragmentos minusculos (< 3 palavras) ao vizinho quando possivel
    compactado: list[str] = []
    for seg in resultado:
        if compactado and len(seg.split()) < 3 and len(compactado[-1].split()) + len(seg.split()) <= max_palavras + 3:
            compactado[-1] = f"{compactado[-1]} {seg}".strip()
        else:
            compactado.append(seg)
    return compactado or [limpo]


def _dividir_em_blocos_narrativos(roteiro_bruto: str) -> list[str]:
    """Divide o roteiro em tomadas visuais rapidas (1.5s a 2.5s) sem inserir ponto final no meio da frase."""
    limpo = sanitizar_texto(roteiro_bruto)
    frases = [f.strip() for f in RE_SEPARAR_FRASES.split(limpo) if f.strip()]
    if not frases:
        raise ValueError("Roteiro bruto vazio apos sanitizacao.")

    tomadas: list[str] = []
    for f in frases:
        subs = _dividir_fala_em_tomadas_curtas(f, max_palavras=MAX_PALAVRAS_POR_TOMADA)
        for s_idx, sub in enumerate(subs):
            sub_limpo = sub.strip()
            if not sub_limpo:
                continue
            # Apenas o fim real da frase preserva/recebe pontuacao final; nunca carimba '.' no meio de uma frase dividida
            if s_idx == len(subs) - 1 and not sub_limpo.endswith((".", "!", "?", ",", ";", ":")):
                sub_limpo = sub_limpo + "."
            tomadas.append(sub_limpo)

    # Compacta fragmentos curtissimos (< 4 palavras, como "VOCE! E, VOCE MESMO!") com o vizinho ate MAX_PALAVRAS_POR_TOMADA
    compactadas: list[str] = []
    for seg in tomadas:
        if (
            compactadas
            and (len(compactadas[-1].split()) < 4 or len(seg.split()) < 4)
            and len(compactadas[-1].split()) + len(seg.split()) <= MAX_PALAVRAS_POR_TOMADA
        ):
            compactadas[-1] = f"{compactadas[-1]} {seg}".strip()
        else:
            compactadas.append(seg)
    tomadas = compactadas

    # Se houver muitas tomadas pequenas, une pares contiguos preservando o teto de 9 palavras (~2.5s) e o gancho/twist/CTA
    if len(tomadas) > 22:
        preservar_fim = 2 if len(tomadas) >= 4 and _eh_bloco_cta_final(tomadas[-1]) else 1
        corpo = tomadas[:-preservar_fim]
        finais = tomadas[-preservar_fim:]
        unidas: list[str] = [corpo[0]] if corpo else []
        for seg in corpo[1:]:
            if (
                len(unidas) > 1
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
        if p2 and not p2.endswith((".", "!", "?")):
            p2 += "."
        tomadas = tomadas[:idx_maior] + [p1, p2] + tomadas[idx_maior + 1 :]

    return tomadas


_STOPWORDS_KATANA: frozenset[str] = STOPWORDS_PT | frozenset(
    {
        "voce", "voces", "dias", "dia", "horas", "hora", "minutos", "minuto", "segundos",
        "anos", "ano", "acha", "hoje", "aqui", "agora", "tudo", "mesmo", "mesma", "outro",
        "outra", "qualquer", "menos", "mais", "igual", "nada", "algo", "coisa", "gente",
        "mundo", "lugar", "ponto", "sobre", "antes", "depois", "ainda", "apenas", "quase",
    }
)


def _escolher_katana_hits(blocos: list[dict], total_desejado: int = 4) -> list[dict]:
    """Seleciona 3 a 5 palavras reais de alto impacto dramatico (nunca pronomes ou unidades como VOCE/DIAS)."""
    palavras_impacto = (
        "travou", "sumiu", "vazio", "vazia", "ninguem", "sorriu", "sorri",
        "atras", "olhos", "apagou", "apaga", "nunca", "morto", "morta", "mortos",
        "sangue", "grito", "sombra", "vulto", "espelho", "camera", "subsolo",
        "silencio", "errado", "falso", "armario", "isolamento", "cemiterio",
        "rugido", "colossal", "alerta", "maximo", "escondido", "proibido",
        "proibida", "explosao", "tsunami", "flechas", "salvar", "panico", "choque",
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
        tokens = [t for t in tokens if len(t) >= 4]

        escolhida = ""
        for tok in tokens:
            chave = normalizar_texto(tok)
            if chave in palavras_impacto and chave not in usadas and chave not in _STOPWORDS_KATANA:
                escolhida = tok
                break
        if not escolhida:
            for tok in reversed(tokens):
                chave = normalizar_texto(tok)
                if len(chave) >= 5 and chave not in _STOPWORDS_KATANA and chave not in usadas and not chave.isdigit():
                    escolhida = tok
                    break
        if not escolhida:
            escolhida = "ALERTA" if "alerta" not in usadas else "CHOQUE"

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
    ultima_pose = ""
    ultima_expr = ""
    ctx_terror_global = _eh_cena_terror_ou_suspense(limpo)
    ctx_indoor_global = _eh_contexto_indoor(limpo)

    for i, txt in enumerate(blocos_txt):
        norm = normalizar_texto(txt)
        eh_final_cta = (i == n - 1) and _eh_bloco_cta_final(txt)
        eh_ultimo = i == n - 1
        eh_twist = i == idx_twist

        hud_dado = None if eh_final_cta else extrair_hud_dado(txt)
        grav_zero = (not eh_final_cta) and (texto_indica_gravidade_zero(txt) or (ctx_zero_g and i >= 1))

        if i == 0:
            # Cena 1 (0s-3s): gancho agressivo obrigatorio com close extremo, choque e shake_impact
            cenario = "big_face"
            acao_cena = "explosao_choque"
            perfil = "panico"
            mood = "red"
            pose = "assustado"
            expr = "shock"
            cam = "shake_impact"
        else:
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
            elif i >= max(1, int(idx_twist * 0.65)) or any(k in norm for k in ("panico", "correu", "correndo", "desesper", "grito", "travou", "bateu", "esmag", "coracao", "despenca", "flecha", "tsunami")):
                perfil = "panico"
                mood = "red" if (i >= max(1, idx_twist - 3) or any(k in norm for k in ("flecha", "tsunami", "explos", "choque", "susto", "pelas costas", "filmando"))) else "violet"
            else:
                perfil = "narrador_tenso"
                mood = "navy" if i % 2 == 0 else "violet"

            cenario = inferir_cenario_animado(
                txt,
                i,
                n,
                anterior=ultimo_cenario,
                contexto_global=limpo,
                hud_dado=hud_dado,
                eh_cta=eh_final_cta or eh_ultimo,
                eh_twist=eh_twist,
                mood=mood,
                perfil=perfil,
            )
            acao_cena = inferir_acao_cena(
                txt,
                cenario,
                hud_dado=hud_dado,
                gravidade_zero=grav_zero,
            )
            if not eh_final_cta and not eh_twist and perfil == "narrador_tenso" and acao_cena == "radar_alerta":
                mood = "yellow"
            elif perfil == "panico" and acao_cena in ("chuva_flechas", "onda_gigante", "explosao_choque"):
                mood = "red"

            eh_terror_bloco = ctx_terror_global or _eh_cena_terror_ou_suspense(txt, mood=mood, perfil=perfil)
            if cenario == "arena_comparacao" and (
                eh_final_cta
                or eh_ultimo
                or not _texto_permite_grafico_comparacao(
                    txt,
                    mood=mood,
                    perfil=perfil,
                    eh_cta=eh_final_cta or eh_ultimo,
                    contexto_terror=eh_terror_bloco,
                )
            ):
                cands_seg = (
                    ("corredor_escuro", "quarto_noturno", "big_face", "laboratorio")
                    if ctx_indoor_global
                    else ("big_face", "laboratorio", "escritorio", "sala_cozinha")
                )
                cenario = next((c for c in cands_seg if c != ultimo_cenario), "big_face")

            pose = inferir_pose_animada(
                txt,
                cenario,
                acao_cena,
                perfil,
                gravidade_zero=grav_zero,
                eh_cta=eh_final_cta,
                mood=mood,
                contexto_terror=eh_terror_bloco,
            )
            expr = inferir_expressao_animada(
                txt,
                perfil,
                acao_cena,
                eh_twist=eh_twist,
                eh_cta=eh_final_cta,
            )
            pose, expr = _alternar_estado_visual_consecutivo(
                pose, expr, ultima_pose, ultima_expr, i, eh_terror=eh_terror_bloco
            )
            pose = _sanitizar_pose_para_tom(
                pose,
                txt,
                mood,
                perfil,
                acao_cena,
                eh_cta=eh_final_cta,
                contexto_terror=eh_terror_bloco,
            )
            cam = escolher_camera_alternada(None, acao_cena, cenario, i, anterior=ultima_camera, mood=mood)

        ultimo_cenario = cenario
        ultima_camera = cam
        ultima_pose = pose
        ultima_expr = expr

        obj_principal = (
            "lapiseira" if "lapiseira" in norm
            else ("xicara_cafe" if ("xicara" in norm or "cafe" in norm)
                  else ("guarda_roupa" if ("armario" in norm or "guarda roupa" in norm) else "janela"))
        )
        flutuantes = inferir_props_flutuantes(txt, objeto_atual=obj_principal, gravidade_zero=grav_zero) if grav_zero else []
        tem_vulto = (not eh_final_cta) and texto_indica_vulto(txt) and not (
            grav_zero and not any(k in norm for k in ("vulto", "sombra", "olhos", "invasor"))
        )
        citacao = extrair_citacao_tela(txt, limite=84)
        props = {
            "objeto": obj_principal,
            "vulto": tem_vulto,
            "gravidade_zero": grav_zero,
            "objetos_flutuantes": flutuantes,
            "silhuetas_janela": "silhuetas_janela" in flutuantes,
            "celular_mensagem": citacao,
            "pose": pose,
            "acao_cena": acao_cena,
            "hud_dado": hud_dado,
        }

        blocos.append(
            {
                "perfil_voz": perfil,
                "texto": txt,
                "cenario": cenario,
                "modulo": cenario,
                "acao_cena": acao_cena,
                "pose": pose,
                "mood": mood,
                "expressao": expr,
                "camera": cam,
                "hud_dado": hud_dado,
                "props": props,
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
    horario_ex = pilar["horario_padrao"] if pilar is not None else "15:00"
    resumo_pilares = ", ".join(p["nome"] for p in PILARES_EDITORIAIS)
    return (
        f"Você é o Diretor de Animação 2D 30fps do canal '{CANAL_NOME}' "
        f"(YouTube Shorts / Reels em {IDIOMA_CANAL}: {resumo_pilares}).\n"
        "Transforme o roteiro bruto abaixo em um plano estruturado JSON estrito onde CADA FALA (1.5s a 2.5s) gera uma cena 2D animada única.\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. ZERO emoji e ZERO travessão (em-dash ou en-dash) em qualquer texto.\n"
        f"2. ORTOGRAFIA COMPLETA EM {IDIOMA_HUMANO.upper()} (UTF-8): preserve TODOS os acentos, cedilhas e números/anos inteiros "
        "(ex.: 2004, 2006, 5 km, R$ 100 mil, R$ 48, Dia 30, Nível 5, você, não, mão, pés). Nunca escreva 'R$ 48 reais' (use apenas 'R$ 48').\n"
        "3. GANCHO AGRESSIVO 0-3s NA CENA 1 (PROIBIDO INTRO LENTA, SAUDACAO OU META-ABERTURA):\n"
        "   - NUNCA abra com 'Oi pessoal', 'Você sabia', 'Existe um lugar', 'Hoje vamos falar', 'Era uma vez', 'Olha pra tela', 'Presta atenção' ou 'Escuta isso'.\n"
        "   - O Bloco 1 (0s a 3s, 6 a 9 palavras) DEVE abrir direto dentro do conflito ou ameaça em 2ª pessoa PT-BR com choque/urgência "
        "(ex.: 'VOCÊ ACORDOU NO LEITO 402 TRANCADO POR FORA!').\n"
        "   - O Bloco 1 DEVE usar obrigatoriamente: cenario='big_face', acao_cena='explosao_choque', pose='assustado', expressao='shock', camera='shake_impact', mood='red', perfil_voz='panico'.\n"
        "4. RITMO DE RETENÇÃO (MUDANÇA VISUAL A CADA 1.5s A 2.5s): divida em 12 a 20 blocos bem curtos (6 a 9 palavras por bloco). "
        "PROIBIDO inserir pausa comercial, propaganda ou CTA no meio do vídeo. Deixe o gancho/CTA curto de 1 frase APENAS como último bloco.\n"
        "5. DIREÇÃO DE ANIMAÇÃO 2D ÚNICA POR FALA (altere cenario, camera e pose/expressao entre cenas seguidas):\n"
        f"   - perfil_voz: um de {list(PERFIS_VOZ)} (use 'panico' no Bloco 1 e clímax, 'sussurro_twist' na revelação final, 'narrador_tenso' no restante; NUNCA use 'cta_comercial').\n"
        f"   - cenario: um de {list(CENARIOS_ANIMADOS)}. Para histórias em ambiente interno (hospital, UTI, leito, corredor, quarto, sala, prédio, elevador, casa, banheiro), use 'corredor_escuro', 'quarto_noturno', 'elevador_cabine', 'sala_cozinha', 'escritorio', 'laboratorio' ou 'big_face' (NUNCA 'cidade_rua'). Use 'arena_comparacao' APENAS para crescimento, multiplicadores ou escala estatística (PROIBIDO em terror/suspense e na cena final/CTA).\n"
        f"   - acao_cena: um de {list(ACOES_CENA_VALIDAS)}.\n"
        f"   - pose: um de {list(POSES_VALIDAS)} (varie com frequência a cada 1.5s-2.5s; PROIBIDO usar 'comemorando' ou 'pulando' em cenas de terror, suspense, medo ou mood dark/red).\n"
        f"   - expressao: um de {list(EXPRESSOES_VALIDAS)} (varie junto com a pose).\n"
        f"   - camera: um de {list(CAMERAS_VALIDAS)}. Alterne SEMPRE (nunca repita a mesma camera em duas falas seguidas).\n"
        f"   - mood: um de {list(MOODS_VALIDOS)}.\n"
        "   - hud_dado: OBRIGATÓRIO sempre que a fala citar números, dias (Dia 30), níveis (Nível 5), dinheiro (R$ 100 MIL, R$ 48), anos (2004, 1997), distâncias (2.600 KM) ou porcentagens: "
        'preencha {"rotulo": "NÍVEL DE ALERTA", "valor": "NÍVEL 5", "progresso": 0.90} (progresso entre 0.0 e 1.0); caso contrário, null.\n'
        f"   - sfx_depois: null ou um de {sfx_validos} (coloque 'impacto_twist' imediatamente antes do bloco da revelação final; máximo 3 SFX no total).\n"
        f"   - props: objeto opcional com gravidade_zero (bool), objetos_flutuantes (subconjunto de {list(PROPS_FLUTUANTES_VALIDOS)}), silhuetas_janela (bool) e vulto (bool).\n"
        "6. katana_hits: lista de 3 a 5 impactos curtos (1 a 2 palavras em MAIÚSCULAS COM ACENTUAÇÃO UTF-8 CORRETA), cada um com bloco_idx (0-based), palavra_gatilho, linhas (1 a 2 strings curtas), duracao (0.36 a 0.48), cor ('red', 'yellow' ou 'white').\n"
        f"7. horario: string HH:MM coerente com o episódio (como '{horario_ex}').\n"
        "8. protagonista.nome: nome do personagem ou 'Você'.\n"
        "9. Responda APENAS com um objeto JSON estrito (sem markdown, sem comentários) no formato:\n"
        "{\n"
        '  "titulo": "...",\n'
        f'  "pilar": "{pilar["id"] if pilar is not None else "suspense_urbano"}",\n'
        '  "tema": "resumo curto em 1 frase",\n'
        '  "palavras_chave": ["kw1", "kw2", "kw3", "kw4", "kw5"],\n'
        f'  "horario": "{horario_ex}",\n'
        '  "protagonista": {"nome": "Você", "jaqueta": "#0F766E", "pele": "#E0B292", "cabelo": "#141720"},\n'
        '  "paleta": {"bg_navy": "#0A0F1D", "bg_violet": "#130926", "bg_red": "#3B0A0A", "accent": "#38D9FF", "alert": "#FF3B30", "yellow": "#FFD400"},\n'
        '  "blocos": [{"perfil_voz": "panico", "texto": "VOCÊ! É, VOCÊ MESMO! PARA TUDO AGORA!", "cenario": "big_face", "acao_cena": "explosao_choque", "pose": "assustado", "expressao": "shock", "camera": "shake_impact", "mood": "red", "hud_dado": null, "sfx_depois": null, "props": {"gravidade_zero": false, "objetos_flutuantes": [], "silhuetas_janela": false, "vulto": false}}],\n'
        '  "katana_hits": [{"bloco_idx": 2, "palavra_gatilho": "alerta", "linhas": ["NÍVEL", "MÁXIMO"], "duracao": 0.42, "cor": "red"}]\n'
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
    """Limpa fences/BOM/virgulas/caracteres de controle e valida que o retorno da IA e um objeto JSON nao vazio."""
    bruto = str(texto or "").lstrip("\ufeff").strip()
    if not bruto:
        raise ValueError("Resposta vazia do modelo ao esperar JSON.")
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
        corrigido = re.sub(r",\s*([}\]])", r"\1", bruto)
        try:
            dados = json.loads(corrigido)
        except json.JSONDecodeError:
            # Remove caracteres de controle/quebras literais ilegais dentro de strings JSON
            sanit = re.sub(r"[\x00-\x1f]+", " ", corrigido)
            dados = json.loads(sanit)
    if not isinstance(dados, dict) or not dados:
        raise ValueError("JSON retornado pela IA precisa ser um objeto nao vazio.")
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
    """Motor primario gratuito via Groq (OpenAI-compatible) usando llama-3.3-70b-versatile em JSON estrito."""
    chave = str(groq_api_key or "").strip()
    if not chave:
        raise RuntimeError("GROQ_API_KEY ausente.")

    modelo_uso = (modelo or os.environ.get("GROQ_MODEL", "").strip() or GROQ_MODELO_PADRAO)
    opener = urlopen_fn or urllib.request.urlopen
    headers = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "gps-canal-dark/8.2",
    }

    system_msg = (
        "Voce e uma API JSON estrita (RFC-8259) especializada em roteiros e direcao de animacao 2D 30fps "
        "para videos curtos verticais. Regras obrigatorias: "
        "(1) Responda SOMENTE com um unico objeto JSON valido, sem texto extra e sem cercas markdown. "
        "(2) Siga exatamente os nomes de campos pedidos no prompt (incluindo titulo, pilar, tema, roteiro_bruto "
        "ou blocos com cenario, acao_cena, pose, expressao, camera, mood, hud_dado e props). "
        "(3) Preserve 100% da acentuacao UTF-8 em portugues, com ZERO emoji e ZERO travessao."
    )

    ultimo_erro = "Falha desconhecida ao chamar Groq."
    for usar_response_format in (True, False):
        payload: dict = {
            "model": modelo_uso,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.65,
            "max_tokens": 4096,
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
                print(f"Groq API OK ({modelo_uso}).", flush=True)
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
                    espera = min(3.0, _extrair_retry_after_s(exc, 2.0))
                    print(f"AVISO {ultimo_erro}; aguardando {espera:.1f}s antes de repetir Groq...", flush=True)
                    sleep_fn(espera)
                    continue
                raise RuntimeError(ultimo_erro) from None
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
                ultimo_erro = f"Groq [{modelo_uso}] {type(exc).__name__}: {exc}"
                if tentativa == 0:
                    sleep_fn(1.5)
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
    """Chama texto em JSON priorizando Groq (Llama 3.3 70B) com fallback automatico para GeminiPool."""
    opener = urlopen_fn or urllib.request.urlopen

    groq_key = (
        obter_groq_api_key(ler_env_arquivo=False)
        if groq_api_key is None
        else str(groq_api_key or "").strip()
    )

    erro_groq: str | None = None
    if groq_key:
        try:
            return chamar_groq_json(
                prompt,
                groq_key,
                urlopen_fn=opener,
                sleep_fn=sleep_fn,
                modelo_ativo_ref=modelo_ativo_ref,
            )
        except Exception as exc_groq:
            erro_groq = str(exc_groq)
            print(
                f"AVISO Groq primario falhou ({erro_groq}). Acionando fallback automatico no GeminiPool...",
                flush=True,
            )

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

    if pool.total_chaves() == 0:
        if erro_groq is not None:
            raise RuntimeError(
                f"Groq primario falhou ({erro_groq}) e nenhuma chave Gemini esta disponivel para fallback."
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

    prefixo_groq = f"Groq primario falhou ({erro_groq}) e " if erro_groq else ""
    raise RuntimeError(
        f"{prefixo_groq}todas as combinacoes Gemini falharam ({combinacoes_testadas} | {pool.resumo_estado()}). "
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
        "2. Escreva entre 185 e 245 palavras em ritmo contínuo, urgente e viciante.\n"
        "3. Siga estritamente o pilar obrigatório acima (não fuja do foco editorial configurado para este episódio).\n"
        "4. GANCHO AGRESSIVO 0-3s (QUEBRA DE PADRÃO EM 2ª PESSOA PT-BR: PROIBIDO INTRO LENTA OU META-ABERTURA):\n"
        "   - PROIBIDO abrir com cumprimentos, apresentações ou meta-aberturas genéricas ('Oi pessoal', 'Você sabia que', "
        "'Hoje vamos falar', 'Nesse vídeo', 'Existe um lugar', 'Era uma vez', 'Imagine um mundo', 'Olha pra tela', "
        "'Presta atenção', 'Escuta isso', 'Para de rolar').\n"
        "   - A Cena 1 (primeiras 6 a 9 palavras, 0 a 3 segundos) DEVE abrir direto dentro do conflito ou ameaça em 2ª pessoa PT-BR "
        "(ex.: 'VOCÊ ACORDOU NO LEITO 402 E A PORTA ESTÁ TRANCADA POR FORA!', "
        "'TEM ALGUÉM FILMANDO VOCÊ PELAS COSTAS NESTE EXATO SEGUNDO!').\n"
        "5. VOZ HUMANA E DADOS CONCRETOS PARA HUD: escreva em frases curtas (6 a 10 palavras) com verbos concretos e "
        "inclua números reais, dias (Dia 1, Dia 30), níveis (Nível 5), dinheiro (R$ 100 mil, R$ 48, sem repetir 'reais' após R$), "
        "anos ou distâncias (2.600 km) para disparar os medidores visuais na tela. PROIBIDO clichês de IA ('mergulhe nessa história', "
        "'prepare-se para descobrir', 'você não vai acreditar', 'a resposta vai te surpreender', 'além disso', 'sem dúvida').\n"
        "6. RETENÇÃO SEM INTERRUPÇÃO: mantenha a tensão crescente até a virada final seca e memorável. PROIBIDO inserir qualquer "
        "pausa comercial, propaganda, anúncio ou CTA no meio do vídeo. Deixe APENAS um gancho/CTA curto e natural de 1 única frase "
        f"no finalzinho do vídeo (referência do canal: '{CTA_FINAL_PADRAO}').\n"
        f"7. ORTOGRAFIA COMPLETA EM {IDIOMA_HUMANO.upper()} (UTF-8): escreva com acentuação e grafia UTF-8 100% corretas "
        "em TODAS as palavras. Nunca remova acentos nem cedilhas.\n"
        "8. ZERO emoji, ZERO travessão (em-dash ou en-dash), ZERO tags [VOZ], [SFX] ou [CTA_PAUSA] "
        "(a marcação técnica será feita na etapa seguinte).\n"
        "9. Responda APENAS com um objeto JSON estrito (sem markdown, sem comentários) no formato:\n"
        "{\n"
        '  "titulo": "Título Inédito Curto",\n'
        f'  "pilar": "{pilar_ativo["id"]}",\n'
        '  "tema": "Resumo objetivo em 1 frase da premissa inédita",\n'
        f'  "roteiro_bruto": "Texto corrido completo do roteiro em {IDIOMA_CANAL} abrindo com quebra de padrão agressiva em 2ª pessoa nos 0-3s, frases curtas com números/dias/níveis/valores concretos, sem pausa comercial no meio e fechando com 1 frase curta de gancho/CTA no finalzinho (185 a 245 palavras)."\n'
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
    """Gera obrigatoriamente um titulo e roteiro bruto 100% ineditos via Groq primario (fallback GeminiPool)."""
    prox_id = proximo_numero_livre(dados_hist)
    pilar_ativo = pilar or selecionar_proximo_pilar(dados_hist, prox_id)
    print(
        f"Diretor IA ('{CANAL_NOME}'): Video {prox_id:02d} -> pilar '{pilar_ativo['id']}' ({pilar_ativo['nome']}).",
        flush=True,
    )
    motivo_rej: str | None = None
    ultimo_erro = "Groq/Gemini nao retornou um roteiro inedito valido."
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
        titulo_gerado = restaurar_acentos_ptbr(
            sanitizar_texto(str(dados.get("titulo") or dados.get("title") or titulo_sugerido or ""))
        ).strip()
        tema_gerado = restaurar_acentos_ptbr(
            sanitizar_texto(str(dados.get("tema") or dados.get("theme") or ""))
        ).strip()
        roteiro_raw = (
            dados.get("roteiro_bruto")
            or dados.get("roteiro")
            or dados.get("script")
            or dados.get("texto")
            or ""
        )
        roteiro_gerado = restaurar_acentos_ptbr(sanitizar_texto(str(roteiro_raw))).strip()

        if len(roteiro_gerado.split()) < 60:
            ultimo_erro = f"Roteiro inedito curto demais ({len(roteiro_gerado.split())} palavras)."
            motivo_rej = ultimo_erro
            continue

        if tentativa < 3 and _eh_abertura_lenta(roteiro_gerado):
            ultimo_erro = (
                "Abertura lenta ou saudacao proibida detectada nos primeiros 3s; "
                "abra com quebra de padrao agressiva em 2a pessoa PT-BR."
            )
            print(f"AVISO roteiro inedito tentativa {tentativa}/3 rejeitado ({ultimo_erro}). Regerando...", flush=True)
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
                "VOCÊ! É, VOCÊ MESMO! PARA TUDO AGORA! "
                "Você acordou trancado num submarino a 300 metros de profundidade. "
                "O painel acendeu em Alerta Nível 5 com só 48 horas de oxigênio. "
                "Se você aceitar ficar até o Dia 3, o prêmio passa de R$ 500 mil. "
                "Seu primeiro instinto é correr e bater no casco de aço. "
                "Só que cada movimento rápido dobra o gasto de ar na cabine. "
                "Com 12 horas, o frio despenca para 6 graus e o rádio morre. "
                "Na hora 24, sua visão escurece e passos ecoam fora do metal. "
                "Você acha a válvula de lastro no corredor e gira com as mãos tremendo. "
                "O visor pisca o aviso impossível: a escotilha externa já estava aberta antes de você acordar. "
                "Me conta nos comentários: você abriria essa escotilha ou ficaria lá dentro?"
            ),
        ),
        "curiosidades_bizarras": (
            f"O Fenômeno Real do Ponto Nemo {prox_id:02d}",
            (
                "VOCÊ! É, VOCÊ MESMO! PARA TUDO AGORA! "
                "Se você cair nesse ponto do oceano, ninguém na Terra consegue te salvar. "
                "Você estaria a 2.600 km de qualquer ilha habitada no Pacífico Sul. "
                "Os humanos mais perto de você estão a 400 km lá em cima, na Estação Espacial. "
                "O isolamento ali bate Nível 5 e nem os peixes sobrevivem nessa água morta. "
                "Nem pagando R$ 10 milhões um resgate chegaria em menos de 15 dias. "
                "Por isso, agências espaciais jogam satélites mortos ali como um cemitério gigante. "
                "Só que em 1997, microfones militares captaram um rugido colossal vindo do fundo. "
                "O som viajou 5.000 km debaixo da água e entrou em alerta máximo. "
                "A versão oficial falou em gelo partindo, mas nunca gravaram nada igual até hoje. "
                "E você, acha que era só gelo ou tem algo escondido lá embaixo, comenta aí?"
            ),
        ),
        "misterios_reais": (
            f"O Cofre Proibido no Gelo de Svalbard {prox_id:02d}",
            (
                "PARA TUDO! OLHA PRA TELA AGORA! "
                "Se você tentar cruzar essa porta no Ártico, o alarme dispara em Nível 5. "
                "O Cofre Global de Svalbard fica 120 metros dentro de uma montanha congelada. "
                "Lá dentro, mais de 1 milhão de sementes dormem a -18 graus negativos. "
                "O projeto custou R$ 45 milhões para aguentar terremotos, explosões e apagões. "
                "No Dia 1 sem comida no planeta, esse corredor blindado vira a última esperança humana. "
                "Não existe equipe morando ali, mas sensores vigiam cada grau 24 horas por dia. "
                "Sem credencial diplomática, ninguém passa da segunda porta de aço. "
                "Até hoje, só um país abriu sua caixa lacrada depois de uma guerra real. "
                "Os governos não construíram isso por filme, eles já têm data e plano pro colapso. "
                "Você sabia que esse cofre existia, me diz aqui nos comentários?"
            ),
        ),
        "suspense_urbano": (
            f"O Último Vagão da Linha Sul {prox_id:02d}",
            (
                "VOCÊ! É, VOCÊ MESMO! NÃO ENTRA NESSE VAGÃO! "
                "Às 23:18, Mateus entrou no último trem vazio da Linha Sul. "
                "Quando cruzou o túnel, a luz piscou e o painel marcou Alerta Nível 4. "
                "O letreiro travou numa estação fechada há 30 anos. "
                "Mateus tirou o fone e percebeu 100% de silêncio sem som de motor. "
                "No vidro escuro, um homem de capa olhava fixo para a nuca dele. "
                "Mateus virou o pescoço na hora: o banco real atrás dele estava vazio. "
                "O interfone chiou alto e a central gritou em pânico na linha. "
                "Aquele trem estava desligado na garagem há 40 minutos. "
                "Mateus olhou de volta para o vidro e o reflexo agora estava sorrindo colado nele. "
                "Me diz nos comentários: você puxava o freio ou corria pro outro vagão?"
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
            f"VOCÊ! É, VOCÊ MESMO! PARA TUDO AGORA! "
            f"Você está ignorando o segredo de Nível 5 por trás de {nome_pilar}. "
            "No Dia 1 tudo parece comum, mas o risco já passou de 90% sem você notar. "
            "Muita gente perde mais de R$ 10 mil antes de perceber o padrão escondido. "
            "Em 48 horas, uma única escolha errada muda completamente o resultado final. "
            "Quem enxerga esse mecanismo cedo vira o jogo antes do prazo acabar. "
            "Quando você junta as pistas na ordem certa, a verdade fica impossível de ignorar. "
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
    ctx_indoor = _eh_contexto_indoor(roteiro_bruto)
    ctx_terror = _eh_cena_terror_ou_suspense(roteiro_bruto)

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
    if not isinstance(blocos_in, list) or len(blocos_in) < 3:
        blocos_in = plano_bruto.get("cenas")
    blocos_validos: list[dict] = []
    sfx_permitidos = set(catalogo_sfx.keys()) - {"glitch_cta", "cta_pop"}
    prompts_usados: set[str] = set()

    ultimo_cenario = ""
    ultima_camera = ""
    ultima_pose = ""
    ultima_expr = ""

    if isinstance(blocos_in, list) and len(blocos_in) >= 3:
        sfx_count = 0
        total_in = len(blocos_in)
        for idx, b in enumerate(blocos_in):
            if not isinstance(b, dict):
                continue
            txt_raw = str(b.get("texto") or b.get("fala") or b.get("narration") or "")
            txt = restaurar_acentos_ptbr(
                sanitizar_texto(re.sub(r"\[/?(?:CTA_PAUSA|VOZ(?::[a-zA-Z0-9_]+)?)\]", "", txt_raw, flags=re.IGNORECASE))
            )
            if not txt:
                continue
            prox_txt = ""
            if idx + 1 < total_in and isinstance(blocos_in[idx + 1], dict):
                prox_txt = str(
                    blocos_in[idx + 1].get("texto")
                    or blocos_in[idx + 1].get("fala")
                    or blocos_in[idx + 1].get("narration")
                    or ""
                ).strip()
            eh_continuacao = bool(prox_txt) and prox_txt[0].islower()
            if (not eh_continuacao) and (not txt.endswith((".", "!", "?", ",", ";", ":"))):
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

            # Subdivide automaticamente falas > 2.5s (> MAX_PALAVRAS_POR_TOMADA palavras) em tomadas curtas
            sub_falas = (
                [txt]
                if eh_cta_in or len(txt.split()) <= MAX_PALAVRAS_POR_TOMADA + 1
                else _dividir_fala_em_tomadas_curtas(txt, max_palavras=MAX_PALAVRAS_POR_TOMADA)
            )
            props_in = b.get("props") if isinstance(b.get("props"), dict) else {}

            for sub_i, sub_txt in enumerate(sub_falas):
                sub_txt_fmt = sub_txt.strip()
                if not sub_txt_fmt:
                    continue
                eh_ultima_sub = sub_i == len(sub_falas) - 1
                if eh_ultima_sub and (not eh_continuacao) and not sub_txt_fmt.endswith((".", "!", "?", ",", ";", ":")):
                    sub_txt_fmt += "."
                eh_cena_1 = len(blocos_validos) == 0
                hud_dado = None if eh_cta_in else extrair_hud_dado(sub_txt_fmt, hud_raw=b.get("hud_dado") if sub_i == 0 else None)
                grav_zero = (not eh_cta_in) and (
                    bool(props_in.get("gravidade_zero")) or texto_indica_gravidade_zero(sub_txt_fmt)
                )

                if eh_cena_1:
                    if _eh_abertura_lenta(sub_txt_fmt):
                        avisos.append("Cena 1: abertura lenta/generica detectada; prefira gancho agressivo 0-3s em 2a pessoa PT-BR.")
                    cen_norm = "big_face"
                    acao_norm = "explosao_choque"
                    cam = "shake_impact"
                    pose_norm = "assustado"
                    expr_norm = "shock"
                    mood_bloco = "red"
                    perfil_bloco = "panico"
                else:
                    mood_bloco = mood
                    perfil_bloco = perfil
                    eh_terror_bloco = ctx_terror or _eh_cena_terror_ou_suspense(
                        sub_txt_fmt, mood=mood_bloco, perfil=perfil_bloco
                    )
                    bloquear_rua_bloco = (
                        _eh_contexto_indoor(sub_txt_fmt) or ctx_indoor
                    ) and not _tem_pista_rua_externa(sub_txt_fmt)
                    eh_ultima_cena_in = eh_ultimo_in and eh_ultima_sub
                    permite_grafico_bloco = (not eh_ultima_cena_in) and _texto_permite_grafico_comparacao(
                        sub_txt_fmt,
                        mood=mood_bloco,
                        perfil=perfil_bloco,
                        eh_cta=eh_cta_in,
                        contexto_terror=eh_terror_bloco,
                    )
                    cen_inferido = inferir_cenario_animado(
                        sub_txt_fmt,
                        len(blocos_validos),
                        max(total_in, len(blocos_validos) + 2),
                        anterior=ultimo_cenario,
                        contexto_global=roteiro_bruto,
                        hud_dado=hud_dado,
                        eh_cta=eh_cta_in or eh_ultima_cena_in,
                        eh_twist=(idx == total_in - 2 and eh_ultima_sub),
                        mood=mood_bloco,
                        perfil=perfil_bloco,
                    )
                    cen_raw_orig = str(b.get("cenario") or b.get("modulo") or "").strip().lower() if sub_i == 0 else ""
                    cen_raw = _CENARIO_ALIASES.get(cen_raw_orig, cen_raw_orig)
                    cen_raw_bloqueado = (
                        cen_raw not in CENARIOS_ANIMADOS
                        or (cen_raw == "espaco_orbita" and cen_inferido == "oceano_ilha")
                        or (bloquear_rua_bloco and cen_raw == "cidade_rua")
                        or (_eh_contexto_indoor(sub_txt_fmt) and cen_raw not in _CENARIOS_INDOOR_ESCUROS)
                        or (cen_raw == "arena_comparacao" and not permite_grafico_bloco)
                    )
                    cen_norm = cen_inferido if cen_raw_bloqueado else cen_raw
                    if cen_norm == "arena_comparacao" and not permite_grafico_bloco:
                        cands_sem_graf = (
                            ("corredor_escuro", "quarto_noturno", "big_face", "laboratorio")
                            if bloquear_rua_bloco
                            else ("big_face", "laboratorio", "escritorio", "sala_cozinha")
                        )
                        cen_norm = next((c for c in cands_sem_graf if c != ultimo_cenario), "big_face")

                    acao_raw = str(b.get("acao_cena") or "").strip().lower() if sub_i == 0 else ""
                    acao_norm = (
                        acao_raw
                        if acao_raw in ACOES_CENA_VALIDAS
                        else inferir_acao_cena(
                            sub_txt_fmt,
                            cen_norm,
                            hud_dado=hud_dado,
                            gravidade_zero=grav_zero,
                        )
                    )
                    cam = escolher_camera_alternada(
                        b.get("camera") if sub_i == 0 else None,
                        acao_norm,
                        cen_norm,
                        len(blocos_validos),
                        anterior=ultima_camera,
                        mood=mood_bloco,
                    )

                    pose_raw = sanitizar_texto(str((b.get("pose") or props_in.get("pose") or "") if sub_i == 0 else "")).lower()
                    pose_norm = _POSE_ALIASES.get(pose_raw, pose_raw)
                    if pose_norm not in POSES_VALIDAS:
                        pose_norm = inferir_pose_animada(
                            sub_txt_fmt,
                            cen_norm,
                            acao_norm,
                            perfil_bloco,
                            gravidade_zero=grav_zero,
                            eh_cta=eh_cta_in,
                            mood=mood_bloco,
                            contexto_terror=eh_terror_bloco,
                        )
                    pose_norm = _sanitizar_pose_para_tom(
                        pose_norm,
                        sub_txt_fmt,
                        mood_bloco,
                        perfil_bloco,
                        acao_norm,
                        eh_cta=eh_cta_in,
                        contexto_terror=eh_terror_bloco,
                    )

                    expr_raw = str(b.get("expressao") or "").strip().lower() if sub_i == 0 else ""
                    expr_norm = _EXPR_ALIASES.get(expr_raw, expr_raw)
                    if expr_norm not in EXPRESSOES_VALIDAS:
                        expr_norm = inferir_expressao_animada(
                            sub_txt_fmt,
                            perfil_bloco,
                            acao_norm,
                            eh_twist=(idx == total_in - 2 and eh_ultima_sub),
                            eh_cta=eh_cta_in,
                        )
                    pose_norm, expr_norm = _alternar_estado_visual_consecutivo(
                        pose_norm, expr_norm, ultima_pose, ultima_expr, len(blocos_validos), eh_terror=eh_terror_bloco
                    )
                    pose_norm = _sanitizar_pose_para_tom(
                        pose_norm,
                        sub_txt_fmt,
                        mood_bloco,
                        perfil_bloco,
                        acao_norm,
                        eh_cta=eh_cta_in,
                        contexto_terror=eh_terror_bloco,
                    )

                ultimo_cenario = cen_norm
                ultima_camera = cam
                ultima_pose = pose_norm
                ultima_expr = expr_norm

                obj_str = sanitizar_texto(str(props_in.get("objeto", "janela")))[:32] or "janela"
                flut_list: list[str] = []
                if grav_zero or any(k in normalizar_texto(obj_str) for k in ("lapiseira", "xicara", "cafe", "cadeira")):
                    for inf_it in inferir_props_flutuantes(sub_txt_fmt, objeto_atual=obj_str, gravidade_zero=grav_zero):
                        if inf_it not in flut_list:
                            flut_list.append(inf_it)
                silhuetas_jan = bool(props_in.get("silhuetas_janela")) or ("silhuetas_janela" in flut_list)
                if silhuetas_jan and "silhuetas_janela" not in flut_list:
                    flut_list.append("silhuetas_janela")
                tem_vulto = (not eh_cta_in) and (
                    bool(props_in.get("vulto")) if "vulto" in props_in else texto_indica_vulto(sub_txt_fmt)
                )
                citacao = extrair_citacao_tela(sub_txt_fmt, limite=84)
                props_bloco = {
                    "objeto": obj_str,
                    "vulto": tem_vulto,
                    "gravidade_zero": grav_zero,
                    "objetos_flutuantes": flut_list,
                    "silhuetas_janela": silhuetas_jan,
                    "celular_mensagem": restaurar_acentos_ptbr(sanitizar_texto(str(props_in.get("celular_mensagem", ""))))[:92] or citacao,
                    "pose": pose_norm,
                    "acao_cena": acao_norm,
                    "hud_dado": hud_dado,
                }

                blocos_validos.append(
                    {
                        "perfil_voz": perfil_bloco,
                        "texto": sub_txt_fmt,
                        "cenario": cen_norm,
                        "modulo": cen_norm,
                        "acao_cena": acao_norm,
                        "pose": pose_norm,
                        "mood": mood_bloco,
                        "expressao": expr_norm,
                        "camera": cam,
                        "hud_dado": hud_dado,
                        "props": props_bloco,
                        "sfx_depois": sfx_limpo if eh_ultima_sub else None,
                    }
                )

    if len(blocos_validos) < 3:
        avisos.append("Blocos insuficientes no retorno da IA: blocos gerados pelo fallback deterministico.")
        blocos_validos = fallback["blocos"]
        ultima_camera = str(blocos_validos[-1].get("camera") or "push_in")

    # Garante apenas 1 frase curta de gancho/CTA no finalzinho do video (nunca no meio, nunca grafico BASE/2X/MAX)
    if not _eh_bloco_cta_final(str(blocos_validos[-1].get("texto") or "")):
        cands_cta = (
            ("big_face", "corredor_escuro", "quarto_noturno", "sala_cozinha")
            if ctx_indoor
            else ("big_face", "laboratorio", "escritorio", "sala_cozinha")
        )
        cen_cta = next((c for c in cands_cta if c != blocos_validos[-1].get("cenario")), "big_face")
        cam_cta = escolher_camera_alternada(
            "pull_out",
            "investigando_pista",
            cen_cta,
            len(blocos_validos),
            anterior=str(blocos_validos[-1].get("camera") or "push_in"),
            mood="navy",
        )
        props_cta = {
            "objeto": "janela",
            "vulto": False,
            "gravidade_zero": False,
            "objetos_flutuantes": [],
            "silhuetas_janela": False,
            "celular_mensagem": "",
            "pose": "apontando",
            "acao_cena": "investigando_pista",
            "hud_dado": None,
        }
        blocos_validos.append(
            {
                "perfil_voz": "narrador_tenso",
                "texto": CTA_FINAL_PADRAO,
                "cenario": cen_cta,
                "modulo": cen_cta,
                "acao_cena": "investigando_pista",
                "pose": "apontando",
                "mood": "navy",
                "expressao": "smug",
                "camera": cam_cta,
                "hud_dado": None,
                "props": props_cta,
                "sfx_depois": None,
            }
        )

    # Garante que a cena final/CTA nunca use grafico de barras (arena_comparacao) nem rua em historia indoor
    ultimo_bloco = blocos_validos[-1]
    penultimo_cen = blocos_validos[-2].get("cenario") if len(blocos_validos) >= 2 else ""
    if ultimo_bloco.get("cenario") == "arena_comparacao" or (ctx_indoor and ultimo_bloco.get("cenario") == "cidade_rua"):
        cands_ult = (
            ("big_face", "corredor_escuro", "quarto_noturno", "sala_cozinha")
            if ctx_indoor
            else ("big_face", "laboratorio", "escritorio", "sala_cozinha")
        )
        novo_cen_ult = next((c for c in cands_ult if c != penultimo_cen), "big_face")
        ultimo_bloco["cenario"] = novo_cen_ult
        ultimo_bloco["modulo"] = novo_cen_ult

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
        f"Formato: YouTube Shorts / Reels 9:16 (1080x1920 @ 30fps) | {'Serie em 2 Partes' if tem_parte_2 else 'Short Unico'} (Motor V7.0 Animacao 2D Canvas)",
        "Gerado automaticamente por pipeline/diretor_ia.py | Estacao 3: render/renderizar.py --motor canvas (player_universal.html)",
        "Perfis vocais: narrador_tenso, panico, interfone_porteiro, voz_telefone, sussurro_twist.",
        "Retencao continua: cada fala aciona um cenario 2D animado unico; zero pausa comercial no meio; apenas 1 frase curta no final.",
        "",
        "Estrutura de cada bloco:",
        "[Tempo em Segundos] | [Texto Exato da Narracao com Tags VOZ] | [Direcao visual 2D animada] | [Eventos e pausas]",
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
        perfil = str(b.get("perfil_voz") or "narrador_tenso")
        cen = str(b.get("cenario") or b.get("modulo") or "oceano_ilha")
        acao = str(b.get("acao_cena") or "investigando_pista")
        props_b = b.get("props") if isinstance(b.get("props"), dict) else {}
        pose_b = str(b.get("pose") or props_b.get("pose") or "falando")
        expr_b = str(b.get("expressao") or "focus")
        cam_b = str(b.get("camera") or "push_in")
        mood_b = str(b.get("mood") or "navy")
        texto_b = str(b.get("texto") or "")
        direcao = f"Cenario {cen} (acao={acao}, pose={pose_b}, mood={mood_b}, expr={expr_b}, cam={cam_b})"
        linhas_rot.append(
            f"[{t0:02d} - {t1:02d}] | [VOZ:{perfil}] {texto_b} [/VOZ] | {direcao} | {ev_str}"
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
                "cenario": cen,
                "modulo": cen,
                "acao_cena": acao,
                "pose": pose_b,
                "mood": mood_b,
                "expressao": expr_b,
                "camera": cam_b,
                "vig": 0.72 if mood_b in ("red", "dark") else 0.58,
                "hud_dado": b.get("hud_dado"),
                "fala": texto_b,
                "props": props_b or {
                    "objeto": "janela",
                    "vulto": False,
                    "gravidade_zero": False,
                    "objetos_flutuantes": [],
                    "silhuetas_janela": False,
                    "celular_mensagem": "",
                    "pose": pose_b,
                    "acao_cena": acao,
                    "hud_dado": b.get("hud_dado"),
                },
            }
        )

    linhas_rot.extend(
        [
            "",
            "============================================================",
            "NOTAS TECNICAS V7.0 (MOTOR 2D ANIMADO 30FPS)",
            f"- Palavras faladas: {total_palavras} | Total de cenas 2D animadas: {len(cenas_json_lista)}.",
            f"- Cenarios animados 30fps em cenas.json: {', '.join(c['cenario'] for c in cenas_json_lista)}.",
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
    """Validador estrito do schema cenas.json V7.0 (Motor 2D Animado 30fps; lista vazia = valido)."""
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
        cam_anterior = ""
        for idx, c in enumerate(lista_cenas):
            if not isinstance(c, dict):
                erros.append(f"cenas[{idx}] invalido.")
                continue
            cen = c.get("cenario") or c.get("modulo")
            if cen not in CENARIOS_ANIMADOS:
                erros.append(f"cenas[{idx}].cenario invalido: {cen!r}.")

            acao = c.get("acao_cena")
            if acao not in ACOES_CENA_VALIDAS:
                erros.append(f"cenas[{idx}].acao_cena invalida: {acao!r}.")

            pose_c = c.get("pose")
            if pose_c not in POSES_VALIDAS:
                erros.append(f"cenas[{idx}].pose invalida: {pose_c!r}.")

            if c.get("mood") not in MOODS_VALIDOS:
                erros.append(f"cenas[{idx}].mood invalido: {c.get('mood')!r}.")

            if c.get("expressao") not in EXPRESSOES_VALIDAS:
                erros.append(f"cenas[{idx}].expressao invalida: {c.get('expressao')!r}.")

            cam = c.get("camera")
            if cam not in CAMERAS_VALIDAS:
                erros.append(f"cenas[{idx}].camera invalida: {cam!r}.")
            elif cam == cam_anterior:
                erros.append(f"cenas[{idx}].camera repete a camera consecutiva anterior ({cam!r}).")
            cam_anterior = str(cam or "")

            if idx == 0:
                if cen != "big_face":
                    erros.append(f"cenas[0].cenario precisa ser 'big_face' para gancho agressivo 0-3s (recebido {cen!r}).")
                if cam != "shake_impact":
                    erros.append(f"cenas[0].camera precisa ser 'shake_impact' na Cena 1 (recebido {cam!r}).")
                if c.get("expressao") not in ("shock", "fear"):
                    erros.append(f"cenas[0].expressao precisa ser 'shock' ou 'fear' na Cena 1 (recebido {c.get('expressao')!r}).")

            hud = c.get("hud_dado")
            if hud is not None:
                if not isinstance(hud, dict):
                    erros.append(f"cenas[{idx}].hud_dado precisa ser objeto ou null.")
                else:
                    if not str(hud.get("rotulo", "")).strip() or not str(hud.get("valor", "")).strip():
                        erros.append(f"cenas[{idx}].hud_dado precisa ter rotulo e valor nao vazios.")
                    prog_h = hud.get("progresso")
                    if not isinstance(prog_h, (int, float)) or not (0.0 <= float(prog_h) <= 1.0):
                        erros.append(f"cenas[{idx}].hud_dado.progresso fora de 0.0..1.0: {prog_h!r}.")

            props_c = c.get("props")
            if not isinstance(props_c, dict):
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
    """Prepara e valida o proximo registro V7 (Motor 2D Canvas) em memoria antes de gravar qualquer arquivo."""
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
        if groq_key:
            print(
                f"Motor IA Estacao 1: PRIMARIO=Groq ({GROQ_MODELO_PADRAO}) "
                f"| FALLBACK=GeminiPool ({pool_gemini.total_chaves()} chave(s): [{nomes_ch}], {len(pool_gemini.modelos)} modelos)",
                flush=True,
            )
        else:
            print(
                f"Motor IA Estacao 1: PRIMARIO=GeminiPool ({pool_gemini.total_chaves()} chave(s): [{nomes_ch}], "
                f"{len(pool_gemini.modelos)} modelos) | Groq desativado (GROQ_API_KEY vazia)",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"Diretor IA V8 ('{CANAL_NOME}'): cria episodio inedito nos "
            f"{len(PILARES_EDITORIAIS)} pilar(es) de config_canal.json ou converte roteiro bruto."
        )
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--roteiro-texto", type=str, help="Texto bruto do roteiro em linha de comando.")
    grupo.add_argument("--arquivo", type=Path, help="Caminho de arquivo .txt com o roteiro bruto.")
    grupo.add_argument(
        "--gerar-inedito",
        action="store_true",
        help="Cria automaticamente um roteiro 100%% inedito via Groq/Gemini alternando os pilares de config_canal.json.",
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
        help=f"Modelo Gemini de fallback preferido (padrao: {GEMINI_MODELO_PADRAO}; Groq e primario quando GROQ_API_KEY existe).",
    )
    parser.add_argument("--mock", action="store_true", help="Executa em modo deterministico offline sem chamar a API.")
    parser.add_argument(
        "--exigir-gemini",
        action="store_true",
        help="Falha explicitamente se nenhuma chave de IA (GROQ_API_KEY / GEMINI_API_KEY) estiver ativa ou todas falharem.",
    )
    parser.add_argument(
        "--nao-atualizar-historico",
        action="store_true",
        help="Gera arquivos de teste sem sobrescrever historico_videos.json.",
    )
    parser.add_argument(
        "--historico",
        type=Path,
        default=None,
        help="Caminho opcional para historico_videos.json (padrao: historico_videos.json na raiz).",
    )
    parser.add_argument(
        "--dir-saida",
        type=Path,
        default=None,
        help="Diretorio opcional de saida para roteiro_XX.txt e cenas.json (padrao: raiz do repositorio).",
    )
    args = parser.parse_args(argv)

    texto_bruto: str | None = None
    if args.arquivo is not None:
        arq = args.arquivo if args.arquivo.is_absolute() else (RAIZ / args.arquivo)
        if not arq.is_file():
            raise SystemExit(f"Arquivo de roteiro nao encontrado: {arq}")
        texto_bruto = arq.read_text(encoding="utf-8")
    elif args.roteiro_texto is not None:
        texto_bruto = args.roteiro_texto

    caminho_hist = (
        (args.historico if args.historico.is_absolute() else (RAIZ / args.historico))
        if args.historico is not None
        else ARQUIVO_HISTORICO
    )
    dir_saida = (
        (args.dir_saida if args.dir_saida.is_absolute() else (RAIZ / args.dir_saida))
        if args.dir_saida is not None
        else RAIZ
    )

    res = produzir_direcao_v6(
        roteiro_bruto=texto_bruto,
        titulo=args.titulo,
        usar_mock=args.mock,
        gerar_inedito=args.gerar_inedito,
        exigir_gemini=args.exigir_gemini,
        modelo=args.modelo,
        caminho_historico=caminho_hist,
        dir_saida=dir_saida,
        atualizar_historico=not args.nao_atualizar_historico,
        pilar_editorial=args.pilar,
    )

    for av in res.get("avisos") or []:
        print(f"AVISO Diretor IA: {av}", flush=True)

    cenas = res.get("cenas") or {}
    lista_cenas = cenas.get("cenas") or []
    motor_atual = str(cenas.get("motor") or MOTOR_RENDER_PADRAO)
    if motor_atual == MOTOR_RENDER_PADRAO:
        resumo_visual = ", ".join(
            f"{c.get('cenario') or c.get('modulo') or 'oceano_ilha'}({c.get('camera') or 'push_in'})"
            for c in lista_cenas
            if isinstance(c, dict)
        )
        rotulo_visual = "Cenarios"
    else:
        resumo_visual = ", ".join(
            str(c.get("cenario") or c.get("camera") or c.get("mood") or c.get("modulo") or "cena_2d")
            for c in lista_cenas
            if isinstance(c, dict)
        )
        rotulo_visual = "Cenas"
    hits = ", ".join(
        " ".join(h.get("linhas") or [])
        for h in (cenas.get("katana_hits") or [])
        if isinstance(h, dict)
    )
    pilar_info = f", pilar={res['pilar']}" if res.get("pilar") else ""
    print(
        f"Diretor IA V7 concluido ({res.get('origem', 'ia')}): Video {int(res['video_id']):02d} '{res['titulo']}' "
        f"[slug={res['slug']}{pilar_info}, palavras={res['palavras_historia']}, "
        f"{'Parte 1 + Parte 2' if res.get('tem_parte_2') else 'Short unico'}]"
    )
    print(f"  Roteiro: {res['roteiro_path']}")
    print(
        f"  Cenas:   {res['cenas_path']} "
        f"(schema v{cenas.get('schema_version', SCHEMA_VERSION)}, motor={motor_atual}, {len(lista_cenas)} cenas)"
    )
    print(f"  {rotulo_visual}: {resumo_visual}")
    print(f"  Katana:  {hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
