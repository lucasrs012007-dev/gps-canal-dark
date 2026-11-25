"""Estacao 2 (V6.1): gera audio/voz_limpa.mp3, audio/timestamps.json e audio/eventos.json.

Uso (na raiz do repositorio):
    python3 audio/gerar_narracao.py          # Gemini 2.5 TTS -> ElevenLabs -> edge-tts -> gTTS
    python3 audio/gerar_narracao.py --mock   # teste automatizado local sem rede

Regras aplicadas:
- Ritmo natural e envolvente: velocidade atempo=1.02 (VELOCIDADE_VOZ) menos corrida e mais humana,
  remocao de silencios longos demais entre falas (>0.22s comprimidos preservando 0.06s de respiro
  para manter ~0.27s de respiracao natural sem cortar pausas curtas).
- Perfil vocal canonico `voz_telefone` (Fenrir no Gemini TTS + filtro telefonico no sound_design.py).
- Blindagem Gemini TTS: agrupa falas contiguas do mesmo perfil em uma unica requisicao,
  cadencia entre chamadas (GEMINI_TTS_MIN_INTERVAL_S, padrao 21.0s), ate 4 retries em HTTP 429/503
  (22s, 35s, 50s, 65s respeitando Retry-After) e log explicito sem jamais expor a chave.
- Trava de Consistencia Vocal: proibido misturar provedores no mesmo video; se qualquer bloco
  falhar definitivamente no provedor atual, descarta tudo e reinicia do bloco 1 no proximo fallback.
- Blindagem contra edge_tts.exceptions.NoAudioReceived: sanitizacao estrita de texto,
  taxas naturais (+0% a +8%), retry escalonado em 3 niveis (perfil -> rate sem pitch -> puro)
  e 4o nivel de emergencia gTTS (lang="pt", tld="com.br") + ajuste FFmpeg.
- Grava carimbo de integridade (video_id, titulo, roteiro_sha256), provedor_voz,
  blocos_api_chamadas, voz_blocos, modo de CTA e corte_parte_2 em timestamps.json e eventos.json.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pipeline.config_canal import (  # noqa: E402
    carregar_config_canal,
    obter_perfil_idioma,
)
from pipeline.historico import (  # noqa: E402
    calcular_sha256_arquivo,
    caminho_roteiro_atual,
    obter_video_atual,
    validar_artefatos_audio,
)

PASTA_AUDIO = RAIZ / "audio"
VOZ_LIMPA_MP3 = PASTA_AUDIO / "voz_limpa.mp3"
TIMESTAMPS_JSON = PASTA_AUDIO / "timestamps.json"
EVENTOS_JSON = PASTA_AUDIO / "eventos.json"
TEXTO_TXT = PASTA_AUDIO / "narracao.txt"
ARQUIVO_ENV = RAIZ / ".env"

_CFG_CANAL = carregar_config_canal()
_PERFIL_IDIOMA = obter_perfil_idioma(_CFG_CANAL["idioma"])
IDIOMA_CANAL = _PERFIL_IDIOMA["codigo"]
IDIOMA_HUMANO = _PERFIL_IDIOMA["nome_humano"]
GTTS_LANG = _PERFIL_IDIOMA["gtts_lang"]
GTTS_TLD = _PERFIL_IDIOMA["gtts_tld"]

# Perfis vocais canonicos
PERFIL_VOZ_PADRAO = "narrador_tenso"
PERFIS_VOZ_CANONICOS = (
    "narrador_tenso",
    "panico",
    "interfone_porteiro",
    "voz_telefone",
    "cta_comercial",
    "sussurro_twist",
)

# Velocidade natural lida de config_canal.json (padrao 1.02x) e limpeza de silencios longos
VELOCIDADE_VOZ_PADRAO = float(_CFG_CANAL["velocidade_voz"])
SILENCIO_INTERNO_MAX_S = 0.22
SILENCIO_INTERNO_MANTER_S = 0.06
GEMINI_TTS_MIN_INTERVAL_PADRAO = 21.0
GEMINI_RETRY_ESPERAS: tuple[float, ...] = (22.0, 35.0, 50.0, 65.0)

# Configuracoes de voz: Gemini 2.5 TTS (Principal)
GEMINI_TTS_MODELO = "gemini-2.5-flash-preview-tts"
GEMINI_VOZ_NARRADOR = "Charon"
GEMINI_VOZ_PORTEIRO = "Fenrir"
GEMINI_VOZ_TELEFONE = "Fenrir"
GEMINI_VOZ_CTA = "Charon"
GEMINI_TAXA_PCM_PADRAO = 24000

INSTRUCOES_ATUACAO_GEMINI: dict[str, str] = {
    "narrador_tenso": (
        f"Direcao vocal ({IDIOMA_HUMANO}): narrador masculino de voz grave, natural e envolvente, "
        "como alguem contando uma historia viciante de perto. Diccao nitida, ritmo fluido sem correria "
        "e sem tom robotico, mantendo respiracao natural e evitando pausas longas demais."
    ),
    "panico": (
        f"Direcao vocal ({IDIOMA_HUMANO}): narrador tenso, urgente e alterado por perigo real, "
        "ritmo firme e expressivo mantendo diccao clara, respiracao natural e sem correria exagerada."
    ),
    "interfone_porteiro": (
        f"Direcao vocal ({IDIOMA_HUMANO}): outro personagem masculino falando tenso e apressado "
        "pelo interfone, voz natural e alarmada com diccao clara e sem pausas arrastadas."
    ),
    "voz_telefone": (
        f"Direcao vocal ({IDIOMA_HUMANO}): outro personagem masculino falando alarmado e direto "
        "por ligacao telefonica, voz natural e tensa com diccao nitida."
    ),
    "cta_comercial": (
        f"Direcao vocal ({IDIOMA_HUMANO}): locutor natural, proximo e direto, falando em tom "
        "conversacional e claro, sem exageros artificiais."
    ),
    "sussurro_twist": (
        f"Direcao vocal ({IDIOMA_HUMANO}): voz baixa, proxima do microfone, fria e precisa, "
        "mantendo naturalidade e impacto ao entregar a revelacao final sem arrastar demais."
    ),
}

# Configuracoes de voz: ElevenLabs (Fallback 1)
ELEVENLABS_MODELO = "eleven_multilingual_v2"
ELEVENLABS_VOZ_PADRAO = "pNInz6obpgDQGcFmaJgB"  # Adam (masculina grave/narrativa)

PERFIS_ELEVENLABS: dict[str, dict[str, float | bool]] = {
    "narrador_tenso": {
        "stability": 0.42,
        "similarity_boost": 0.80,
        "style": 0.38,
        "use_speaker_boost": True,
    },
    "panico": {
        "stability": 0.28,
        "similarity_boost": 0.78,
        "style": 0.58,
        "use_speaker_boost": True,
    },
    "interfone_porteiro": {
        "stability": 0.26,
        "similarity_boost": 0.74,
        "style": 0.64,
        "use_speaker_boost": True,
    },
    "voz_telefone": {
        "stability": 0.26,
        "similarity_boost": 0.75,
        "style": 0.65,
        "use_speaker_boost": True,
    },
    "cta_comercial": {
        "stability": 0.50,
        "similarity_boost": 0.82,
        "style": 0.44,
        "use_speaker_boost": True,
    },
    "sussurro_twist": {
        "stability": 0.54,
        "similarity_boost": 0.84,
        "style": 0.26,
        "use_speaker_boost": True,
    },
}

# Configuracoes de voz: edge-tts multi-bloco natural (Fallback 2, taxas equilibradas +0% a +8%)
EDGE_VOZ = _PERFIL_IDIOMA["edge_voz_principal"]
EDGE_VOZ_SECUNDARIA = _PERFIL_IDIOMA["edge_voz_secundaria"]
EDGE_VOZ_PORTEIRO = EDGE_VOZ_SECUNDARIA
EDGE_PITCH = "-4Hz"
EDGE_RATE = "+4%"

PERFIS_EDGE_TTS: dict[str, dict[str, str]] = {
    "narrador_tenso": {"voice": EDGE_VOZ, "pitch": "-5Hz", "rate": "+4%"},
    "panico": {"voice": EDGE_VOZ, "pitch": "-2Hz", "rate": "+8%"},
    "interfone_porteiro": {"voice": EDGE_VOZ_SECUNDARIA, "pitch": "+2Hz", "rate": "+6%"},
    "voz_telefone": {"voice": EDGE_VOZ_SECUNDARIA, "pitch": "+2Hz", "rate": "+6%"},
    "cta_comercial": {"voice": EDGE_VOZ, "pitch": "-1Hz", "rate": "+4%"},
    "sussurro_twist": {"voice": EDGE_VOZ, "pitch": "-8Hz", "rate": "+0%"},
}

# Ritmo natural entre blocos (evita silencios mortos longos sem cortar respiracao humana)
PAUSA_PANICO = 0.12
PAUSA_PADRAO = 0.16
PAUSA_VIRADA_PERFIL = 0.18
PAUSA_ANTES_TWIST = 0.22
PAUSA_DRAMATICA = 0.22
DURACAO_BATIDAS_PORTA = 2.10
CAUDA_FINAL = 0.35

# Limite de caracteres por bloco de legenda para evitar aperto/colagem em palavras longas
MAX_CHARS_GRUPO_3 = 20
MAX_CHARS_GRUPO_2 = 22

TAXA_AMOSTRAGEM = 44100
CANAIS = 2
TICKS_POR_SEGUNDO = 10_000_000

LINHA_BLOCO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")
PADRAO_SFX = re.compile(
    r"^\[\s*SFX\s*:\s*([a-zA-Z0-9_]+)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*\]$",
    re.IGNORECASE,
)
PADRAO_CORTE_P2 = re.compile(r"^\[\s*CORTE_PARTE_2\s*\]$", re.IGNORECASE)
PADRAO_CTA_PAUSA = re.compile(
    r"^\[\s*CTA_PAUSA\s*\]([\s\S]*?)\[\s*/\s*CTA_PAUSA\s*\]$",
    re.IGNORECASE,
)
PADRAO_TAG_VOZ = re.compile(
    r"\[\s*VOZ\s*:\s*([a-zA-Z0-9_]+)\s*\]([\s\S]*?)\[\s*/\s*VOZ\s*\]",
    re.IGNORECASE,
)
PADRAO_QUALQUER_TAG_VOZ = re.compile(
    r"\[\s*/?\s*VOZ(?:\s*:\s*[a-zA-Z0-9_]+)?\s*\]",
    re.IGNORECASE,
)
PADRAO_TAGS_RESIDUAIS = re.compile(
    r"\[\s*/?\s*(?:VOZ|SFX|CTA_PAUSA|CORTE_PARTE_2)[^\]]*\]",
    re.IGNORECASE,
)
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)
PADRAO_BATIDAS = re.compile(
    r"(?:^|\s)(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?\s*(?:toque|toc)[\.\!\,]?(?=\s|$)",
    re.IGNORECASE,
)
SEPARADOR_FRASES = re.compile(r"(?<!\.\.)(?<=[\.\!\?])\s+")


def obter_velocidade_voz(caminho_config: Path | str | None = None) -> float:
    raw = os.environ.get("VELOCIDADE_VOZ", "").strip()
    if raw:
        try:
            return max(0.5, min(2.0, float(raw)))
        except ValueError:
            pass
    cfg = carregar_config_canal(caminho_config)
    return float(cfg["velocidade_voz"])


def obter_intervalo_min_gemini() -> float:
    raw = os.environ.get("GEMINI_TTS_MIN_INTERVAL_S", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return GEMINI_TTS_MIN_INTERVAL_PADRAO


def carregar_env(caminho_env: Path = ARQUIVO_ENV) -> bool:
    """Carrega variaveis do .env local apenas quando ausentes ou vazias no ambiente."""
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


def normalizar_chave(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def normalizar_perfil_voz(nome: str | None, padrao: str = PERFIL_VOZ_PADRAO) -> str:
    """Normaliza e valida o perfil vocal contra os 6 perfis canonicos V5.2."""
    if not nome:
        return padrao
    chave = re.sub(r"[^a-z0-9_]", "", nome.strip().lower())
    if chave in PERFIS_VOZ_CANONICOS:
        return chave
    return padrao


def limpar_tags_voz(texto: str) -> str:
    """Remove qualquer marcador residual [VOZ:...] ou [/VOZ] garantindo fala e legendas limpas."""
    sem_tags = PADRAO_QUALQUER_TAG_VOZ.sub(" ", str(texto or ""))
    return re.sub(r"\s+", " ", sem_tags).strip()


def sanitizar_texto_tts(texto: str) -> str:
    """Limpa tags residuais, emojis, travessoes e espacos extras antes de enviar ao TTS."""
    limpo = PADRAO_TAGS_RESIDUAIS.sub(" ", str(texto or ""))
    limpo = RE_EMOJI.sub("", limpo)
    limpo = limpo.replace("\u2014", ", ").replace("\u2013", ", ")
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo


def tem_conteudo_falavel(texto: str) -> bool:
    """Garante que o trecho nao seja vazio nem composto apenas de pontuacao."""
    return bool(re.search(r"[A-Za-zÀ-ÿ0-9]", sanitizar_texto_tts(texto)))


def extrair_segmentos_voz(texto: str, perfil_padrao: str = PERFIL_VOZ_PADRAO) -> list[tuple[str, str]]:
    """Extrai segmentos (perfil_voz, texto_limpo) suportando multiplos blocos [VOZ:perfil]...[/VOZ]."""
    padrao = normalizar_perfil_voz(perfil_padrao)
    segmentos: list[tuple[str, str]] = []
    pos = 0
    for m in PADRAO_TAG_VOZ.finditer(texto):
        if m.start() > pos:
            antes = limpar_tags_voz(texto[pos : m.start()])
            if antes and tem_conteudo_falavel(antes):
                segmentos.append((padrao, antes))
        perfil = normalizar_perfil_voz(m.group(1), padrao=padrao)
        conteudo = limpar_tags_voz(m.group(2))
        if conteudo and tem_conteudo_falavel(conteudo):
            segmentos.append((perfil, conteudo))
        pos = m.end()

    if pos < len(texto):
        resto = limpar_tags_voz(texto[pos:])
        if resto and tem_conteudo_falavel(resto):
            segmentos.append((padrao, resto))

    return segmentos


def suavizar_prosodia_legado(trecho: str) -> str:
    """Ajuste legado para roteiro_01.txt."""
    ajustes = [
        (
            "Sete da noite. Todo celular do Brasil apita ao mesmo tempo.",
            "Sete da noite, todo celular do Brasil apita ao mesmo tempo.",
        ),
        (
            "Caio ri. Acha que é teste do governo.",
            "Caio ri, achando que é teste do governo.",
        ),
        (
            "Nove da noite. Caio chega em casa.",
            "Nove da noite, Caio chega em casa.",
        ),
        (
            "Meia-noite. A luz cai no bairro inteiro.",
            "Meia-noite, a luz cai no bairro inteiro.",
        ),
    ]
    out = trecho
    for orig, fluido in ajustes:
        out = out.replace(orig, fluido)
    return out


def _interpretar_coluna_eventos(espec: str) -> tuple[list[str], list[tuple[str, str]], float | None]:
    eventos_inicio: list[str] = []
    eventos_palavra: list[tuple[str, str]] = []
    pausa_explicita: float | None = None

    for parte in espec.split(","):
        tok = parte.strip()
        if not tok:
            continue
        if tok.lower().startswith("pausa="):
            pausa_explicita = float(tok.split("=", 1)[1].strip())
        elif "@" in tok:
            ev_nome, alvo = tok.split("@", 1)
            ev_nome = ev_nome.strip()
            alvo = normalizar_chave(alvo.strip())
            if ev_nome and alvo:
                eventos_palavra.append((ev_nome, alvo))
        else:
            eventos_inicio.append(tok)
    return eventos_inicio, eventos_palavra, pausa_explicita


def extrair_itens_roteiro(caminho: Path) -> tuple[list[dict], bool]:
    """Extrai falas com perfis [VOZ:perfil], blocos SFX e marcadores V5/V5.2 ([CTA_PAUSA], [CORTE_PARTE_2])."""
    linhas_bloco: list[list[str]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if LINHA_BLOCO.match(linha):
            colunas = [c.strip() for c in linha.split("|")]
            if len(colunas) >= 2:
                linhas_bloco.append(colunas)
    if not linhas_bloco:
        raise SystemExit(f"Nenhum bloco de narracao encontrado em {caminho}.")

    usa_eventos_explicitos = any(len(cols) >= 4 and cols[3] for cols in linhas_bloco)
    marcador = " __BATIDAS_PORTA__ "
    itens: list[dict] = []

    for bloco_idx, colunas in enumerate(linhas_bloco):
        narracao = colunas[1]
        espec_eventos = colunas[3] if len(colunas) >= 4 else ""
        ev_inicio, ev_palavra, pausa_explicita = _interpretar_coluna_eventos(espec_eventos)

        if PADRAO_CORTE_P2.match(narracao):
            itens.append(
                {
                    "tipo": "corte_parte_2",
                    "bloco": bloco_idx,
                    "evento": "corte_parte_2",
                    "duracao": 0.14,
                    "offset_corte": 0.11,
                    "pausa_antes": 0.0,
                }
            )
            continue

        m_cta = PADRAO_CTA_PAUSA.match(narracao)
        if m_cta:
            miolo_cta = m_cta.group(1).strip()
            segs_cta = extrair_segmentos_voz(miolo_cta, perfil_padrao="cta_comercial")
            itens.append(
                {
                    "tipo": "silencio",
                    "bloco": bloco_idx,
                    "evento": "cta_pausa_in",
                    "sfx_nome": "cta_pausa_in",
                    "duracao": 0.22,
                    "pausa_antes": 0.06,
                    "interno_cta": True,
                }
            )
            primeira_cta = True
            for perfil_seg, texto_seg in segs_cta:
                frases_cta = [f.strip() for f in SEPARADOR_FRASES.split(texto_seg) if tem_conteudo_falavel(f)]
                for frase in frases_cta:
                    itens.append(
                        {
                            "tipo": "fala",
                            "bloco": bloco_idx,
                            "texto": frase,
                            "perfil_voz": perfil_seg,
                            "eventos_inicio": ev_inicio if primeira_cta else [],
                            "eventos_palavra": ev_palavra,
                            "pausa_antes": 0.0 if primeira_cta else 0.10,
                            "eh_cta_pausa": True,
                        }
                    )
                    primeira_cta = False
            itens.append(
                {
                    "tipo": "silencio",
                    "bloco": bloco_idx,
                    "evento": "cta_pausa_out",
                    "sfx_nome": "cta_pausa_out",
                    "duracao": 0.22,
                    "pausa_antes": 0.0,
                    "interno_cta": True,
                }
            )
            continue

        m_sfx = PADRAO_SFX.match(narracao)
        if m_sfx:
            sfx_nome = m_sfx.group(1).strip().lower()
            nome_ev = ev_inicio[0] if ev_inicio else sfx_nome
            dur_sfx = float(m_sfx.group(2))
            itens.append(
                {
                    "tipo": "silencio",
                    "bloco": bloco_idx,
                    "evento": nome_ev,
                    "sfx_nome": sfx_nome,
                    "duracao": dur_sfx,
                    "pausa_antes": pausa_explicita,
                }
            )
            continue

        if not usa_eventos_explicitos:
            narracao = suavizar_prosodia_legado(narracao)

        segmentos = extrair_segmentos_voz(narracao, perfil_padrao=PERFIL_VOZ_PADRAO)
        primeira_fala_do_bloco = True
        for perfil_seg, texto_seg in segmentos:
            substituido = PADRAO_BATIDAS.sub(marcador, texto_seg)
            partes = substituido.split("__BATIDAS_PORTA__")
            for p_idx, parte in enumerate(partes):
                trecho = parte.strip()
                if trecho and tem_conteudo_falavel(trecho):
                    frases = [f.strip() for f in SEPARADOR_FRASES.split(trecho) if tem_conteudo_falavel(f)]
                    for frase in frases:
                        itens.append(
                            {
                                "tipo": "fala",
                                "bloco": bloco_idx,
                                "texto": frase,
                                "perfil_voz": perfil_seg,
                                "eventos_inicio": ev_inicio if primeira_fala_do_bloco else [],
                                "eventos_palavra": ev_palavra,
                                "pausa_antes": pausa_explicita if primeira_fala_do_bloco else None,
                            }
                        )
                        primeira_fala_do_bloco = False
                if p_idx < len(partes) - 1:
                    itens.append(
                        {
                            "tipo": "silencio",
                            "bloco": bloco_idx,
                            "evento": "batidas_porta",
                            "sfx_nome": "batidas_porta",
                            "duracao": DURACAO_BATIDAS_PORTA,
                            "pausa_antes": None,
                        }
                    )
    return itens, usa_eventos_explicitos


def agrupar_blocos_fala(itens: list[dict]) -> list[dict]:
    """Agrupa falas consecutivas do mesmo perfil (sem [SFX], [CTA_PAUSA] ou [CORTE_PARTE_2] no meio).

    Reduz drasticamente chamadas de API ao Gemini TTS e evita quebras artificiais entre frases do mesmo bloco.
    """
    unidades: list[dict] = []
    grupo_atual: dict | None = None

    for idx, item in enumerate(itens):
        if item["tipo"] != "fala":
            if grupo_atual is not None:
                unidades.append(grupo_atual)
                grupo_atual = None
            unidades.append({"tipo": item["tipo"], "indice_primeiro": idx, "item": item})
            continue

        if not tem_conteudo_falavel(item.get("texto", "")):
            continue

        perfil = normalizar_perfil_voz(item.get("perfil_voz"))
        eh_cta = bool(item.get("eh_cta_pausa"))
        if (
            grupo_atual is not None
            and grupo_atual["perfil_voz"] == perfil
            and grupo_atual["eh_cta_pausa"] == eh_cta
        ):
            grupo_atual["itens"].append((idx, item))
        else:
            if grupo_atual is not None:
                unidades.append(grupo_atual)
            grupo_atual = {
                "tipo": "grupo_fala",
                "indice_primeiro": idx,
                "perfil_voz": perfil,
                "eh_cta_pausa": eh_cta,
                "itens": [(idx, item)],
            }

    if grupo_atual is not None:
        unidades.append(grupo_atual)

    for u in unidades:
        if u["tipo"] == "grupo_fala":
            u["texto_combinado"] = " ".join(
                sanitizar_texto_tts(it["texto"]) for _, it in u["itens"]
            ).strip()
    return unidades


def pausa_antes_do_item(itens: list[dict], idx: int) -> float:
    """Define a pausa natural entre blocos (0.12s a 0.22s, teto 0.28s sem silencios longos demais)."""
    if idx == 0:
        return 0.0
    anterior = itens[idx - 1]
    atual = itens[idx]
    if atual.get("pausa_antes") is not None:
        return min(0.28, max(0.0, float(atual["pausa_antes"])))
    if anterior["tipo"] in ("silencio", "corte_parte_2"):
        return 0.0
    if atual["tipo"] == "corte_parte_2":
        return 0.0
    if atual["tipo"] == "silencio":
        return 0.06
    if atual["tipo"] == "fala":
        chave = normalizar_chave(atual["texto"])
        if chave.startswith("silencio") or chave.startswith("e o rosto dele"):
            return PAUSA_DRAMATICA
        perfil_atual = atual.get("perfil_voz", PERFIL_VOZ_PADRAO)
        perfil_ant = anterior.get("perfil_voz", PERFIL_VOZ_PADRAO)
        if perfil_atual == "sussurro_twist":
            return PAUSA_ANTES_TWIST
        if perfil_atual != perfil_ant:
            return PAUSA_VIRADA_PERFIL
        if perfil_atual in ("panico", "interfone_porteiro", "voz_telefone"):
            return PAUSA_PANICO
    return PAUSA_PADRAO


def mapear_evento_legado(texto: str) -> str | None:
    chave = normalizar_chave(texto)
    mapa = [
        ("alerta de emergencia", "alerta_1"),
        ("caio ri", "caio_ri"),
        ("nove da noite", "hora_21"),
        ("segundo alerta", "alerta_2"),
        ("a mae para de responder", "chat_mae"),
        ("meia-noite", "hora_00"),
        ("meia noite", "hora_00"),
        ("a luz cai", "apagao_00"),
        ("so as telas", "janelas_telas"),
        ("terceiro alerta", "alerta_3"),
        ("tres da manha", "hora_03"),
        ("do outro lado da porta", "respiracao"),
        ("uma voz sussurra", "sussurro"),
        ("silencio", "silencio"),
        ("caio finalmente abre a foto", "foto_revela"),
        ("e o rosto dele", "big_face"),
        ("caio nunca esteve", "plot_twist"),
    ]
    for prefixo, evento in mapa:
        if chave.startswith(prefixo):
            return evento
    return None


def medir_duracao_ffprobe(caminho: Path) -> float:
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


def gerar_wav_silencio(caminho: Path, duracao: float) -> float:
    n_frames = max(0, int(round(duracao * TAXA_AMOSTRAGEM)))
    with wave.open(str(caminho), "wb") as wf:
        wf.setnchannels(CANAIS)
        wf.setsampwidth(2)
        wf.setframerate(TAXA_AMOSTRAGEM)
        if n_frames:
            wf.writeframes(b"\x00\x00" * CANAIS * n_frames)
    return n_frames / TAXA_AMOSTRAGEM


def sintetizar_mock(
    texto: str,
    destino_wav: Path,
    indice: int,
    perfil_voz: str = PERFIL_VOZ_PADRAO,
) -> list[dict]:
    """Gera sinal vocal simulado com silencios nas pontas e assinatura tonal por perfil V5.2."""
    palavras = sanitizar_texto_tts(texto).split()
    peso_chars = sum(max(2, len(p)) for p in palavras)
    fator_ritmo = {
        "narrador_tenso": 0.96,
        "panico": 0.86,
        "interfone_porteiro": 0.88,
        "voz_telefone": 0.88,
        "cta_comercial": 1.04,
        "sussurro_twist": 1.02,
    }.get(perfil_voz, 0.95)
    dur_ativa = max(0.60, min(14.0, (0.28 + peso_chars * 0.045) * fator_ritmo))
    pad_ini = 0.14
    pad_fim = 0.18
    dur_total = pad_ini + dur_ativa + pad_fim
    n_total = int(round(dur_total * TAXA_AMOSTRAGEM))
    base_perfil = {
        "narrador_tenso": 118.0,
        "panico": 146.0,
        "interfone_porteiro": 178.0,
        "voz_telefone": 184.0,
        "cta_comercial": 136.0,
        "sussurro_twist": 98.0,
    }.get(perfil_voz, 124.0)
    freq_base = base_perfil + (indice % 5) * 6.0

    amostras = bytearray()
    for i in range(n_total):
        t = i / TAXA_AMOSTRAGEM
        if t < pad_ini or t > pad_ini + dur_ativa:
            s = 0.0
        else:
            tr = t - pad_ini
            env = min(1.0, tr / 0.025) * min(1.0, (dur_ativa - tr) / 0.03)
            cadencia = 0.65 + 0.35 * math.sin(2.0 * math.pi * 4.2 * tr)
            f = freq_base * (1.0 - 0.08 * (tr / dur_ativa))
            s = 0.22 * env * cadencia * (
                0.75 * math.sin(2.0 * math.pi * f * tr)
                + 0.25 * math.sin(2.0 * math.pi * (f * 2.0) * tr)
            )
        val = max(-32767, min(32767, int(s * 32767)))
        amostras.extend(struct.pack("<hh", val, val))

    with wave.open(str(destino_wav), "wb") as wf:
        wf.setnchannels(CANAIS)
        wf.setsampwidth(2)
        wf.setframerate(TAXA_AMOSTRAGEM)
        wf.writeframes(bytes(amostras))
    return []


# ============================================================
# MOTOR PRINCIPAL V5.2: GEMINI 2.5 TTS REST (BLOCOS + ANTI-429)
# ============================================================

def selecionar_voz_gemini(perfil_voz: str) -> str:
    """Retorna a voz predefinida do Gemini 2.5 TTS para cada perfil (Charon vs Fenrir)."""
    perfil = normalizar_perfil_voz(perfil_voz)
    if perfil == "interfone_porteiro":
        return os.environ.get("GEMINI_TTS_VOICE_PORTEIRO", "").strip() or GEMINI_VOZ_PORTEIRO
    if perfil == "voz_telefone":
        return os.environ.get("GEMINI_TTS_VOICE_TELEFONE", "").strip() or GEMINI_VOZ_TELEFONE
    if perfil == "cta_comercial":
        return os.environ.get("GEMINI_TTS_VOICE_CTA", "").strip() or (
            os.environ.get("GEMINI_TTS_VOICE", "").strip() or GEMINI_VOZ_CTA
        )
    return os.environ.get("GEMINI_TTS_VOICE", "").strip() or GEMINI_VOZ_NARRADOR


def montar_payload_gemini_tts(
    texto: str,
    perfil_voz: str = PERFIL_VOZ_PADRAO,
    voice_override: str | None = None,
) -> dict:
    """Monta payload REST oficial do gemini-2.5-flash-preview-tts com atuacao agil inline em pt-BR."""
    perfil = normalizar_perfil_voz(perfil_voz)
    direcao = INSTRUCOES_ATUACAO_GEMINI.get(perfil, INSTRUCOES_ATUACAO_GEMINI[PERFIL_VOZ_PADRAO])
    voz = (voice_override or "").strip() or selecionar_voz_gemini(perfil)
    texto_limpo = sanitizar_texto_tts(texto)
    prompt_atuacao = (
        f"{direcao}\n"
        f"Leia apenas o texto exato abaixo em {IDIOMA_HUMANO}, com ritmo natural e envolvente, sem adicionar nem omitir palavras:\n"
        f"{texto_limpo}"
    )
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt_atuacao,
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voz,
                    }
                }
            },
        },
    }


def _extrair_rate_mime(mime_type: str, padrao: int = GEMINI_TAXA_PCM_PADRAO) -> int:
    m = re.search(r"rate\s*=\s*(\d+)", mime_type or "", flags=re.IGNORECASE)
    if m:
        taxa = int(m.group(1))
        if 8000 <= taxa <= 96000:
            return taxa
    return padrao


def decodificar_resposta_gemini_tts(dados: dict, destino_wav: Path) -> Path:
    """Decodifica o audio PCM 24kHz (base64) retornado pela API REST do Gemini TTS para WAV valido."""
    candidatos = dados.get("candidates") or []
    inline = None
    for cand in candidatos:
        content = cand.get("content") or {}
        for parte in content.get("parts") or []:
            bloco = parte.get("inlineData") or parte.get("inline_data")
            if isinstance(bloco, dict) and bloco.get("data"):
                inline = bloco
                break
        if inline:
            break

    if not inline:
        raise RuntimeError("Resposta Gemini TTS nao retornou bloco inlineData de audio.")

    bruto = base64.b64decode(inline["data"])
    if not bruto:
        raise RuntimeError("Audio base64 vazio retornado pelo Gemini TTS.")

    mime = str(inline.get("mimeType") or inline.get("mime_type") or "audio/L16;codec=pcm;rate=24000")
    mime_low = mime.lower()

    if "wav" in mime_low or bruto[:4] == b"RIFF":
        destino_wav.write_bytes(bruto)
        return destino_wav

    if "mpeg" in mime_low or "mp3" in mime_low or "ogg" in mime_low:
        tmp_src = destino_wav.with_suffix(".bin")
        tmp_src.write_bytes(bruto)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(tmp_src),
                "-ar",
                str(TAXA_AMOSTRAGEM),
                "-ac",
                str(CANAIS),
                "-c:a",
                "pcm_s16le",
                str(destino_wav),
            ],
            check=True,
        )
        tmp_src.unlink(missing_ok=True)
        return destino_wav

    taxa_hz = _extrair_rate_mime(mime, GEMINI_TAXA_PCM_PADRAO)
    if len(bruto) % 2 == 1:
        bruto = bruto[:-1]
    with wave.open(str(destino_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(taxa_hz)
        wf.writeframes(bruto)
    return destino_wav


def _extrair_retry_after(exc: urllib.error.HTTPError) -> float | None:
    try:
        hdrs = getattr(exc, "headers", None)
        if not hdrs:
            return None
        val = hdrs.get("Retry-After") or hdrs.get("retry-after")
        if val is None:
            return None
        return max(0.0, float(str(val).strip()))
    except (TypeError, ValueError):
        return None


def sintetizar_gemini_tts(
    texto: str,
    destino_wav: Path,
    api_key: str,
    perfil_voz: str = PERFIL_VOZ_PADRAO,
    modelo: str | None = None,
    urlopen_fn: Callable | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    cadencia_estado: dict | None = None,
    min_interval_s: float | None = None,
    retry_esperas: tuple[float, ...] = GEMINI_RETRY_ESPERAS,
) -> list[dict]:
    """Chama a API REST oficial do Gemini 2.5 TTS com cadencia anti-429 e ate 4 retries."""
    texto_limpo = sanitizar_texto_tts(texto)
    if not tem_conteudo_falavel(texto_limpo):
        raise ValueError("Texto vazio ou sem conteudo falavel para Gemini TTS.")

    modelo_uso = (modelo or os.environ.get("GEMINI_TTS_MODEL", "").strip() or GEMINI_TTS_MODELO)
    intervalo = obter_intervalo_min_gemini() if min_interval_s is None else max(0.0, float(min_interval_s))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_uso}:generateContent"
    payload_bytes = json.dumps(
        montar_payload_gemini_tts(texto_limpo, perfil_voz=perfil_voz),
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    opener = urlopen_fn or urllib.request.urlopen

    ultimo_erro: Exception | None = None
    max_tentativas = 1 + len(retry_esperas)

    for tentativa in range(max_tentativas):
        if tentativa == 0 and cadencia_estado is not None and intervalo > 0.0:
            ultima = cadencia_estado.get("ultima_chamada")
            if ultima is not None:
                decorrido = monotonic_fn() - float(ultima)
                falta = intervalo - decorrido
                if falta > 0.0:
                    sleep_fn(falta)
        if cadencia_estado is not None:
            cadencia_estado["ultima_chamada"] = monotonic_fn()

        req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
        try:
            with opener(req, timeout=90) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
            decodificar_resposta_gemini_tts(dados, destino_wav)
            return []
        except urllib.error.HTTPError as exc:
            ultimo_erro = exc
            motivo = _extrair_motivo_http_error(exc)
            if exc.code in (429, 500, 502, 503, 504) and tentativa < len(retry_esperas):
                espera = float(retry_esperas[tentativa])
                retry_after = _extrair_retry_after(exc)
                if retry_after is not None and retry_after > espera:
                    espera = retry_after
                print(
                    f"AVISO Gemini TTS HTTP {exc.code} ({motivo}) na tentativa {tentativa + 1}/{max_tentativas}. "
                    f"Aguardando {espera:.1f}s antes de repetir...",
                    flush=True,
                )
                sleep_fn(espera)
                continue
            print(f"ERRO Gemini TTS definitivo: HTTP {exc.code} ({motivo}).", flush=True)
            raise
        except RuntimeError as exc:
            ultimo_erro = exc
            if tentativa < min(1, len(retry_esperas)):
                sleep_fn(min(5.0, float(retry_esperas[tentativa])))
                continue
            raise

    assert ultimo_erro is not None
    raise ultimo_erro


# ============================================================
# FALLBACK 1: ELEVENLABS (VOICE_SETTINGS POR PERFIL V5.2)
# ============================================================

def alinhamento_elevenlabs_para_palavras(texto: str, alignment: dict | None) -> list[dict]:
    if not alignment:
        return []
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (chars and len(chars) == len(starts) == len(ends)):
        return []

    palavras_raw = []
    buf = []
    ini = None
    fim = None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf and ini is not None and fim is not None:
                palavras_raw.append(
                    {"palavra": "".join(buf), "inicio": float(ini), "duracao": max(0.02, float(fim - ini))}
                )
                buf = []
                ini = None
                fim = None
        else:
            if ini is None:
                ini = s
            fim = e
            buf.append(ch)
    if buf and ini is not None and fim is not None:
        palavras_raw.append(
            {"palavra": "".join(buf), "inicio": float(ini), "duracao": max(0.02, float(fim - ini))}
        )
    return palavras_raw if len(palavras_raw) == len(texto.split()) else []


def _extrair_motivo_http_error(exc: urllib.error.HTTPError) -> str:
    """Extrai o motivo detalhado devolvido pela API sem expor segredos."""
    try:
        corpo = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        corpo = ""
    if not corpo:
        return str(exc.reason or f"HTTP {exc.code}")
    try:
        dados = json.loads(corpo)
        detail = dados.get("detail") or (dados.get("error") or {}).get("message")
        if isinstance(detail, dict):
            status = detail.get("status", "")
            msg = detail.get("message", "")
            if status and msg:
                return f"{status}: {msg}"
            return str(status or msg or detail)
        if detail:
            return str(detail)
    except Exception:
        pass
    return corpo[:260]


def sintetizar_elevenlabs(
    texto: str,
    destino_mp3: Path,
    api_key: str,
    voice_id: str,
    perfil_voz: str = PERFIL_VOZ_PADRAO,
) -> list[dict]:
    texto_limpo = sanitizar_texto_tts(texto)
    perfil = normalizar_perfil_voz(perfil_voz)
    settings = PERFIS_ELEVENLABS.get(perfil, PERFIS_ELEVENLABS[PERFIL_VOZ_PADRAO])
    payload = json.dumps(
        {
            "text": texto_limpo,
            "model_id": ELEVENLABS_MODELO,
            "voice_settings": settings,
        }
    ).encode("utf-8")

    headers_json = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url_ts = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    req_ts = urllib.request.Request(url_ts, data=payload, headers=headers_json, method="POST")
    try:
        with urllib.request.urlopen(req_ts, timeout=60) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        destino_mp3.write_bytes(base64.b64decode(dados["audio_base64"]))
        return alinhamento_elevenlabs_para_palavras(texto_limpo, dados.get("alignment"))
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404, 422):
            raise

    headers_mp3 = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    req = urllib.request.Request(url, data=payload, headers=headers_mp3, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        destino_mp3.write_bytes(resp.read())
    return []


# ============================================================
# FALLBACK 2: EDGE-TTS BLINDADO CONTRA NoAudioReceived (V5.2)
# ============================================================

def config_edge_por_perfil(perfil_voz: str) -> dict[str, str]:
    """Retorna voz, rate (+14% a +22%) e pitch do edge-tts adaptados ao perfil vocal V5.2."""
    perfil = normalizar_perfil_voz(perfil_voz)
    return dict(PERFIS_EDGE_TTS.get(perfil, PERFIS_EDGE_TTS[PERFIL_VOZ_PADRAO]))


async def _sintetizar_edge_async(
    texto: str,
    destino_mp3: Path,
    voice: str,
    rate: str | None = None,
    pitch: str | None = None,
) -> list[dict]:
    import edge_tts

    kwargs: dict[str, str] = {"boundary": "WordBoundary"}
    if rate:
        kwargs["rate"] = rate
    if pitch:
        kwargs["pitch"] = pitch

    comunicar = edge_tts.Communicate(texto, voice, **kwargs)
    palavras: list[dict] = []
    bytes_audio = 0
    with destino_mp3.open("wb") as arq:
        async for pedaco in comunicar.stream():
            if pedaco["type"] == "audio":
                chunk = pedaco["data"]
                arq.write(chunk)
                bytes_audio += len(chunk)
            elif pedaco["type"] == "WordBoundary":
                palavras.append(
                    {
                        "palavra": pedaco["text"],
                        "inicio": pedaco["offset"] / TICKS_POR_SEGUNDO,
                        "duracao": pedaco["duration"] / TICKS_POR_SEGUNDO,
                    }
                )
    if bytes_audio == 0:
        raise RuntimeError("NoAudioReceived: edge-tts retornou 0 bytes de audio.")
    return palavras


def _executar_tentativa_edge(
    texto: str,
    destino_mp3: Path,
    voice: str,
    rate: str | None,
    pitch: str | None,
) -> list[dict]:
    return asyncio.run(_sintetizar_edge_async(texto, destino_mp3, voice=voice, rate=rate, pitch=pitch))


def sintetizar_edge(
    texto: str,
    destino_mp3: Path,
    perfil_voz: str = PERFIL_VOZ_PADRAO,
    runner_fn: Callable[[str, Path, str, str | None, str | None], list[dict]] | None = None,
) -> list[dict]:
    """Sintetiza com edge-tts usando sanitizacao estrita e retry escalonado em 3 niveis."""
    texto_limpo = sanitizar_texto_tts(texto)
    if not tem_conteudo_falavel(texto_limpo):
        raise ValueError("Texto vazio ou apenas pontuacao bloqueado antes do edge-tts.")

    cfg = config_edge_por_perfil(perfil_voz)
    exec_fn = runner_fn or _executar_tentativa_edge

    # Tentativa 1: voz/rate/pitch do perfil; Tentativa 2: AntonioNeural + rate (sem pitch); Tentativa 3: AntonioNeural puro
    planos: list[tuple[str, str | None, str | None, str]] = [
        (cfg["voice"], cfg["rate"], cfg["pitch"], "perfil completo"),
        (EDGE_VOZ, cfg["rate"], None, "AntonioNeural com rate (sem pitch)"),
        (EDGE_VOZ, None, None, "AntonioNeural puro (sem rate nem pitch)"),
    ]

    ultimo_erro: Exception | None = None
    for idx_t, (voz, rate, pitch, desc) in enumerate(planos, start=1):
        destino_mp3.unlink(missing_ok=True)
        try:
            palavras = exec_fn(texto_limpo, destino_mp3, voz, rate, pitch)
            if not destino_mp3.is_file() or destino_mp3.stat().st_size < 64:
                raise RuntimeError("NoAudioReceived: arquivo de audio vazio apos edge-tts.")
            return palavras
        except Exception as exc:
            ultimo_erro = exc
            print(
                f"AVISO edge-tts falhou na tentativa {idx_t}/3 [{desc}] ({type(exc).__name__}: {exc}).",
                flush=True,
            )

    assert ultimo_erro is not None
    raise ultimo_erro


# ============================================================
# FALLBACK 3 (4o NIVEL DE EMERGENCIA): gTTS + ATEMPO FFMPEG
# ============================================================

def sintetizar_gtts(
    texto: str,
    destino_mp3: Path,
    gtts_cls=None,
) -> list[dict]:
    """4o nivel de emergencia gratuito usando gTTS (lang='pt', tld='com.br')."""
    texto_limpo = sanitizar_texto_tts(texto)
    if not tem_conteudo_falavel(texto_limpo):
        raise ValueError("Texto vazio ou apenas pontuacao bloqueado antes do gTTS.")

    cls = gtts_cls
    if cls is None:
        from gtts import gTTS as cls  # type: ignore[import-not-found]

    destino_mp3.unlink(missing_ok=True)
    tts = cls(text=texto_limpo, lang=GTTS_LANG, tld=GTTS_TLD)
    tts.save(str(destino_mp3))
    if not destino_mp3.is_file() or destino_mp3.stat().st_size < 64:
        raise RuntimeError("gTTS gerou arquivo de audio vazio.")
    return []


# ============================================================
# LIMPEZA DE SILENCIOS LONGOS + VELOCIDADE NATURAL (ATEMPO 1.02X)
# ============================================================

def montar_filtro_limpeza_voz(velocidade: float = VELOCIDADE_VOZ_PADRAO) -> str:
    """Monta filtro FFmpeg: remove silencios longos (>0.22s) mantendo respiracao natural + atempo 1.02x."""
    v = max(0.5, min(2.0, float(velocidade)))
    return (
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-46dB:start_silence=0.02:"
        f"stop_periods=-1:stop_duration={SILENCIO_INTERNO_MAX_S:.2f}:"
        f"stop_silence={SILENCIO_INTERNO_MANTER_S:.2f}:stop_threshold=-45dB:detection=rms,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-46dB:start_silence=0.03:detection=rms,"
        "areverse,"
        f"atempo={v:.3f},"
        "afade=t=in:st=0:d=0.008"
    )


def limpar_silencio_frase(
    origem: Path,
    destino_wav: Path,
    velocidade: float | None = None,
) -> float:
    """Remove silencios longos demais mantendo respiracao natural, aplica atempo e normaliza PCM 44.1kHz."""
    vel = obter_velocidade_voz() if velocidade is None else max(0.5, min(2.0, float(velocidade)))
    filtro = montar_filtro_limpeza_voz(vel)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(origem),
        "-af",
        filtro,
        "-ar",
        str(TAXA_AMOSTRAGEM),
        "-ac",
        str(CANAIS),
        "-c:a",
        "pcm_s16le",
        str(destino_wav),
    ]
    subprocess.run(cmd, check=True)
    dur = medir_duracao_ffprobe(destino_wav)
    if dur < 0.08:
        cmd_raw = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(origem),
            "-af",
            f"atempo={vel:.3f}",
            "-ar",
            str(TAXA_AMOSTRAGEM),
            "-ac",
            str(CANAIS),
            "-c:a",
            "pcm_s16le",
            str(destino_wav),
        ]
        subprocess.run(cmd_raw, check=True)
        dur = medir_duracao_ffprobe(destino_wav)
    return dur


# ============================================================
# TRAVA DE CONSISTENCIA VOCAL (ROLLBACK COMPLETO SEM MISTURA)
# ============================================================

def sintetizar_todos_blocos_com_consistencia(
    unidades: list[dict],
    cadeia_provedores: list[str],
    tmp_dir: Path,
    velocidade: float,
    gemini_key: str = "",
    gemini_model: str = GEMINI_TTS_MODELO,
    eleven_key: str = "",
    voice_id: str = ELEVENLABS_VOZ_PADRAO,
    sintetizadores_override: dict[str, Callable[[str, Path, str, int], list[dict]]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    min_interval_gemini_s: float | None = None,
) -> tuple[str, str, dict[int, tuple[Path, float, list[dict]]], int]:
    """Sintetiza TODOS os blocos agrupados em um unico provedor (rollback total se qualquer bloco falhar)."""
    grupos_fala = [
        (u_idx, u) for u_idx, u in enumerate(unidades) if u["tipo"] == "grupo_fala"
    ]
    overrides = sintetizadores_override or {}
    ultimo_erro: Exception | None = None

    for p_idx, provedor in enumerate(cadeia_provedores):
        sub_dir = tmp_dir / f"tentativa_{p_idx}_{provedor}"
        sub_dir.mkdir(parents=True, exist_ok=True)
        resultados: dict[int, tuple[Path, float, list[dict]]] = {}
        cadencia_gemini: dict[str, float | None] = {"ultima_chamada": None}
        chamadas_api = 0
        falhou = False

        for b_num, (u_idx, unidade) in enumerate(grupos_fala, start=1):
            texto_bloco = unidade["texto_combinado"]
            perfil = unidade["perfil_voz"]
            ext = ".wav" if provedor in ("mock", "gemini-tts") else ".mp3"
            raw_arq = sub_dir / f"bloco_{u_idx:02d}_raw{ext}"
            limpo_wav = sub_dir / f"bloco_{u_idx:02d}_limpo.wav"

            try:
                chamadas_api += 1
                if provedor in overrides:
                    raw_words = overrides[provedor](texto_bloco, raw_arq, perfil, b_num - 1)
                elif provedor == "mock":
                    raw_words = sintetizar_mock(texto_bloco, raw_arq, b_num - 1, perfil_voz=perfil)
                elif provedor == "gemini-tts":
                    raw_words = sintetizar_gemini_tts(
                        texto_bloco,
                        raw_arq,
                        gemini_key,
                        perfil_voz=perfil,
                        modelo=gemini_model,
                        sleep_fn=sleep_fn,
                        monotonic_fn=monotonic_fn,
                        cadencia_estado=cadencia_gemini,
                        min_interval_s=min_interval_gemini_s,
                    )
                elif provedor == "elevenlabs":
                    raw_words = sintetizar_elevenlabs(
                        texto_bloco,
                        raw_arq,
                        eleven_key,
                        voice_id,
                        perfil_voz=perfil,
                    )
                elif provedor == "edge-tts":
                    raw_words = sintetizar_edge(texto_bloco, raw_arq, perfil_voz=perfil)
                elif provedor == "gtts":
                    raw_words = sintetizar_gtts(texto_bloco, raw_arq)
                else:
                    raise RuntimeError(f"Provedor desconhecido: {provedor}")

                # gTTS fala ligeiramente mais devagar nativamente; acelera no minimo em max(vel, 1.18)
                vel_bloco = max(velocidade, 1.18) if provedor == "gtts" else velocidade
                dur_limpo = limpar_silencio_frase(raw_arq, limpo_wav, velocidade=vel_bloco)
                resultados[u_idx] = (limpo_wav, dur_limpo, raw_words or [])
            except Exception as exc:
                ultimo_erro = exc
                motivo = (
                    f"HTTP {exc.code} ({_extrair_motivo_http_error(exc)})"
                    if isinstance(exc, urllib.error.HTTPError)
                    else f"{type(exc).__name__}: {exc}"
                )
                prox = cadeia_provedores[p_idx + 1] if p_idx + 1 < len(cadeia_provedores) else "NENHUM"
                print(
                    f"ROLLBACK VOCAL: provedor '{provedor}' falhou no bloco {b_num}/{len(grupos_fala)} "
                    f"({motivo}). Descartando {len(resultados)} bloco(s) parcial(is) e reiniciando "
                    f"TODOS os blocos em '{prox}' (zero mistura de vozes).",
                    flush=True,
                )
                shutil.rmtree(sub_dir, ignore_errors=True)
                falhou = True
                break

        if not falhou:
            desc_voz = {
                "mock": "mock-tone-pt-BR (perfis V5.2)",
                "gemini-tts": (
                    f"{gemini_model} (narrador={selecionar_voz_gemini('narrador_tenso')}, "
                    f"telefone={selecionar_voz_gemini('voz_telefone')})"
                ),
                "elevenlabs": f"{ELEVENLABS_MODELO}:{voice_id}",
                "edge-tts": f"edge-tts agil V5.2 ({EDGE_VOZ} + {EDGE_VOZ_SECUNDARIA})",
                "gtts": "gTTS emergencia (pt-BR + atempo FFmpeg)",
            }.get(provedor, provedor)
            return provedor, desc_voz, resultados, chamadas_api

    raise RuntimeError(
        f"Todos os provedores de voz falharam ({cadeia_provedores}). Ultimo erro: {ultimo_erro}"
    )


def alinhar_palavras_na_frase(
    texto: str,
    t_inicio: float,
    dur_frase: float,
    raw_words: list[dict],
) -> list[dict]:
    """Trava os tempos de cada palavra dentro de [t_inicio, t_inicio + dur_frase]."""
    tokens = texto.split()
    if not tokens:
        return []

    if raw_words and len(raw_words) == len(tokens):
        base = raw_words[0]["inicio"]
        fim_raw = max(w["inicio"] + w["duracao"] for w in raw_words)
        span = max(0.05, fim_raw - base)
        escala = dur_frase / span
        saida = []
        for tok, rw in zip(tokens, raw_words):
            rel_ini = max(0.0, (rw["inicio"] - base) * escala)
            rel_dur = max(0.03, rw["duracao"] * escala)
            if rel_ini + rel_dur > dur_frase:
                rel_dur = max(0.02, dur_frase - rel_ini)
            ini_abs = round(t_inicio + rel_ini, 3)
            fim_abs = round(min(t_inicio + dur_frase, t_inicio + rel_ini + rel_dur), 3)
            saida.append(
                {
                    "palavra": tok,
                    "inicio": ini_abs,
                    "duracao": round(max(0.02, fim_abs - ini_abs), 3),
                    "fim": fim_abs,
                }
            )
        return saida

    pesos = []
    for tok in tokens:
        limpa = re.sub(r"[^\wÀ-ÿ]", "", tok)
        peso = max(2.0, float(len(limpa))) + 1.2
        if tok.endswith((":", ",", ";", "...")):
            peso += 1.5
        pesos.append(peso)
    soma = sum(pesos)
    cursor = t_inicio
    saida = []
    for idx, (tok, peso) in enumerate(zip(tokens, pesos)):
        dur_w = dur_frase * (peso / soma)
        fim_w = t_inicio + dur_frase if idx == len(tokens) - 1 else cursor + dur_w
        ini_r = round(cursor, 3)
        fim_r = round(fim_w, 3)
        saida.append(
            {
                "palavra": tok,
                "inicio": ini_r,
                "duracao": round(max(0.02, fim_r - ini_r), 3),
                "fim": fim_r,
            }
        )
        cursor = fim_w
    return saida


def _distribuir_duracao_no_grupo(
    itens_grupo: list[tuple[int, dict]],
    t_inicio_bloco: float,
    dur_bloco: float,
    raw_words_bloco: list[dict],
) -> list[tuple[dict, float, float, list[dict]]]:
    """Distribui duracao e word-boundaries de um bloco agrupado nas suas frases constituintes."""
    tokens_por_frase = [it["texto"].split() for _, it in itens_grupo]
    total_tokens = sum(len(tks) for tks in tokens_por_frase)

    # Caso ideal: raw_words casam 1:1 com todas as palavras do bloco
    if raw_words_bloco and len(raw_words_bloco) == total_tokens and total_tokens > 0:
        base = raw_words_bloco[0]["inicio"]
        fim_raw = max(w["inicio"] + w["duracao"] for w in raw_words_bloco)
        span = max(0.05, fim_raw - base)
        escala = dur_bloco / span
        saida = []
        pos = 0
        for (_, it), tks in zip(itens_grupo, tokens_por_frase):
            fatia = raw_words_bloco[pos : pos + len(tks)]
            pos += len(tks)
            f_ini = t_inicio_bloco + max(0.0, (fatia[0]["inicio"] - base) * escala)
            f_fim = t_inicio_bloco + min(
                dur_bloco, max(w["inicio"] + w["duracao"] for w in fatia) - base
            ) * escala
            f_dur = max(0.05, f_fim - f_ini)
            saida.append((it, f_ini, f_dur, fatia))
        return saida

    # Distribuicao proporcional por peso fonetico de cada frase
    pesos = []
    for _, it in itens_grupo:
        tks = it["texto"].split()
        peso = sum(max(2.0, float(len(re.sub(r"[^\wÀ-ÿ]", "", tok)))) + 1.2 for tok in tks)
        pesos.append(max(2.0, peso))
    soma = sum(pesos) or 1.0
    cursor = t_inicio_bloco
    saida = []
    for i, ((_, it), peso) in enumerate(zip(itens_grupo, pesos)):
        dur_f = (t_inicio_bloco + dur_bloco - cursor) if i == len(itens_grupo) - 1 else dur_bloco * (peso / soma)
        dur_f = max(0.05, dur_f)
        saida.append((it, cursor, dur_f, []))
        cursor += dur_f
    return saida


def _tamanho_texto_grupo(lista_palavras: list[dict]) -> int:
    return sum(len(str(p["palavra"])) for p in lista_palavras) + max(0, len(lista_palavras) - 1)


def quebrar_em_grupos_legenda(palavras_frase: list[dict]) -> list[list[dict]]:
    """Agrupa palavras de UMA unica frase em blocos legiveis (max 3 palavras e teto de caracteres V5.1/V5.2)."""
    if not palavras_frase:
        return []

    clausulas: list[list[dict]] = []
    atual: list[dict] = []
    for idx, p in enumerate(palavras_frase):
        atual.append(p)
        restantes = len(palavras_frase) - idx - 1
        if p["palavra"].endswith((":", ",")) and (len(atual) >= 2 or "-" in p["palavra"]) and restantes >= 2:
            clausulas.append(atual)
            atual = []
    if atual:
        clausulas.append(atual)

    grupos: list[list[dict]] = []
    for clausula in clausulas:
        i = 0
        n = len(clausula)
        while i < n:
            falta = n - i
            if falta <= 3:
                tam = falta
            elif falta == 4:
                tam = 2
            else:
                tam = 3

            while tam == 3 and _tamanho_texto_grupo(clausula[i : i + 3]) > MAX_CHARS_GRUPO_3:
                tam = 2
            if tam == 2 and _tamanho_texto_grupo(clausula[i : i + 2]) > MAX_CHARS_GRUPO_2:
                tam = 1

            grupos.append(clausula[i : i + tam])
            i += tam
    return grupos


def consolidar_voz_blocos(frases_log: list[dict]) -> list[dict]:
    """Agrupa trechos falados continuos do mesmo perfil vocal sem cruzar blocos de SFX/corte."""
    blocos: list[dict] = []
    atual: dict | None = None

    for reg in frases_log:
        if reg.get("tipo") != "fala":
            if atual is not None:
                blocos.append(atual)
                atual = None
            continue

        perfil = normalizar_perfil_voz(reg.get("perfil_voz"))
        t0 = float(reg["inicio"])
        t1 = float(reg["fim"])
        txt = str(reg.get("texto", "")).strip()

        if atual is not None and atual["perfil"] == perfil and (t0 - atual["fim"]) <= 0.45:
            atual["fim"] = round(t1, 3)
            atual["duracao"] = round(max(0.02, atual["fim"] - atual["inicio"]), 3)
            atual["texto"] = f"{atual['texto']} {txt}".strip()
        else:
            if atual is not None:
                blocos.append(atual)
            atual = {
                "indice": len(blocos),
                "perfil": perfil,
                "inicio": round(t0, 3),
                "fim": round(t1, 3),
                "duracao": round(max(0.02, t1 - t0), 3),
                "texto": txt,
            }

    if atual is not None:
        blocos.append(atual)

    for idx, b in enumerate(blocos):
        b["indice"] = idx
    return blocos


def concatenar_wavs_para_mp3(lista_wavs: list[Path], wav_mestre: Path, destino_mp3: Path) -> float:
    with wave.open(str(wav_mestre), "wb") as out:
        out.setnchannels(CANAIS)
        out.setsampwidth(2)
        out.setframerate(TAXA_AMOSTRAGEM)
        for caminho in lista_wavs:
            with wave.open(str(caminho), "rb") as inp:
                if (
                    inp.getnchannels() != CANAIS
                    or inp.getsampwidth() != 2
                    or inp.getframerate() != TAXA_AMOSTRAGEM
                ):
                    raise RuntimeError(f"Formato WAV inconsistente em {caminho}")
                out.writeframes(inp.readframes(inp.getnframes()))

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(wav_mestre),
        "-ar",
        str(TAXA_AMOSTRAGEM),
        "-ac",
        str(CANAIS),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(destino_mp3),
    ]
    subprocess.run(cmd, check=True)
    return medir_duracao_ffprobe(destino_mp3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera voz_limpa.mp3, timestamps.json e eventos.json sincronizados com o roteiro ativo (V5.2)."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa tons sinteticos locais no lugar do TTS (apenas para teste automatizado).",
    )
    parser.add_argument(
        "--roteiro",
        type=Path,
        default=None,
        help="Caminho manual do roteiro (padrao: video ativo em historico_videos.json).",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg e ffprobe precisam estar instalados e no PATH.")

    tinha_gemini_env = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    env_carregado = carregar_env()
    video_ativo = obter_video_atual(validar=True)
    roteiro_path = args.roteiro if args.roteiro else caminho_roteiro_atual()
    if not roteiro_path.is_absolute():
        roteiro_path = RAIZ / roteiro_path
    if not roteiro_path.is_file():
        raise SystemExit(f"Roteiro nao encontrado: {roteiro_path}")

    roteiro_sha256 = calcular_sha256_arquivo(roteiro_path)
    PASTA_AUDIO.mkdir(exist_ok=True)
    itens, usa_eventos_explicitos = extrair_itens_roteiro(roteiro_path)
    unidades = agrupar_blocos_fala(itens)

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gemini_model = os.environ.get("GEMINI_TTS_MODEL", "").strip() or GEMINI_TTS_MODELO
    eleven_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or ELEVENLABS_VOZ_PADRAO
    velocidade = obter_velocidade_voz()

    if args.mock:
        cadeia_provedores = ["mock"]
        status_gemini = "modo --mock"
    else:
        cadeia_provedores = []
        if gemini_key:
            cadeia_provedores.append("gemini-tts")
            origem_gem = "ambiente" if tinha_gemini_env else ".env local"
            status_gemini = f"GEMINI_API_KEY detectada ({origem_gem})"
        else:
            status_gemini = "GEMINI_API_KEY AUSENTE no ambiente e .env"
        if eleven_key:
            cadeia_provedores.append("elevenlabs")
        cadeia_provedores.extend(["edge-tts", "gtts"])

    qtd_grupos_fala = sum(1 for u in unidades if u["tipo"] == "grupo_fala")
    print(
        f"Video {int(video_ativo['id']):02d}: {video_ativo['titulo']} | "
        f"Roteiro: {roteiro_path.name} (sha256={roteiro_sha256[:12]})"
    )
    print(
        f"Estacao 2 Voz Natural (atempo={velocidade:.2f}, silencio_longo>{SILENCIO_INTERNO_MAX_S:.2f}s, "
        f"respiro={SILENCIO_INTERNO_MANTER_S:.2f}s) | "
        f"{status_gemini} | blocos agrupados={qtd_grupos_fala} | cadeia={' -> '.join(cadeia_provedores)}",
        flush=True,
    )

    texto_falado = " ".join(sanitizar_texto_tts(it["texto"]) for it in itens if it["tipo"] == "fala")
    TEXTO_TXT.write_text(texto_falado + "\n", encoding="utf-8")

    palavras_todas: list[dict] = []
    grupos_todos: list[dict] = []
    frases_log: list[dict] = []
    sfx_eventos: list[dict] = []
    eventos: dict[str, float | int | str | list] = {
        "video_id": int(video_ativo["id"]),
        "slug": str(video_ativo["slug"]),
        "titulo": str(video_ativo["titulo"]),
        "motor": str(video_ativo.get("motor", "")),
        "parte_label": str(video_ativo.get("parte_label", "PARTE 1")),
        "roteiro": roteiro_path.name,
        "roteiro_sha256": roteiro_sha256,
    }

    cta_modo = str(video_ativo.get("cta_modo", "final")).strip().lower() or "final"
    exige_parte_2 = (
        isinstance(video_ativo.get("saidas_partes"), list)
        and len(video_ativo["saidas_partes"]) >= 2
    )
    cta_pausa_inicio: float | None = None
    cta_pausa_fim: float | None = None
    cta_fala_inicio: float | None = None
    cta_fala_fim: float | None = None

    with tempfile.TemporaryDirectory(prefix="voz-v52-") as tmp:
        tmp_dir = Path(tmp)

        provedor_final, voz_usada, blocos_prontos, blocos_api_chamadas = sintetizar_todos_blocos_com_consistencia(
            unidades=unidades,
            cadeia_provedores=cadeia_provedores,
            tmp_dir=tmp_dir,
            velocidade=velocidade,
            gemini_key=gemini_key,
            gemini_model=gemini_model,
            eleven_key=eleven_key,
            voice_id=voice_id,
        )

        wavs_concat: list[Path] = []
        cursor = 0.0
        frase_idx = 0

        for u_idx, unidade in enumerate(unidades):
            pausa = pausa_antes_do_item(itens, unidade["indice_primeiro"])
            if pausa > 0:
                p_wav = tmp_dir / f"pausa_{u_idx:02d}.wav"
                dur_p = gerar_wav_silencio(p_wav, pausa)
                wavs_concat.append(p_wav)
                cursor += dur_p

            if unidade["tipo"] == "corte_parte_2":
                item = unidade["item"]
                c_wav = tmp_dir / f"corte_p2_{u_idx:02d}.wav"
                t_ini = round(cursor, 3)
                dur_s = gerar_wav_silencio(c_wav, item["duracao"])
                wavs_concat.append(c_wav)
                offset_corte = float(item.get("offset_corte", dur_s * 0.5))
                t_corte = round(cursor + min(dur_s - 0.02, offset_corte), 3)
                eventos["corte_parte_2"] = t_corte
                eventos["corte_parte_2_duracao"] = round(dur_s, 3)
                frases_log.append(
                    {
                        "tipo": "corte_parte_2",
                        "evento": "corte_parte_2",
                        "inicio": t_ini,
                        "corte": t_corte,
                        "fim": round(cursor + dur_s, 3),
                        "duracao": round(dur_s, 3),
                    }
                )
                cursor += dur_s
                continue

            if unidade["tipo"] == "silencio":
                item = unidade["item"]
                s_wav = tmp_dir / f"silencio_{u_idx:02d}.wav"
                t_ini = round(cursor, 3)
                dur_s = gerar_wav_silencio(s_wav, item["duracao"])
                wavs_concat.append(s_wav)
                ev_nome = item["evento"]
                sfx_nome = str(item.get("sfx_nome") or ev_nome).strip().lower()
                eventos[ev_nome] = t_ini
                eventos[f"{ev_nome}_duracao"] = round(dur_s, 3)
                if ev_nome not in ("cta_pausa_in", "cta_pausa_out"):
                    sfx_eventos.append(
                        {
                            "nome": sfx_nome,
                            "evento": ev_nome,
                            "inicio": t_ini,
                            "duracao": round(dur_s, 3),
                        }
                    )
                if ev_nome == "cta_pausa_in":
                    cta_pausa_inicio = t_ini
                elif ev_nome == "cta_pausa_out":
                    cta_pausa_fim = round(cursor + dur_s, 3)
                if ev_nome == "batidas_porta":
                    eventos["batidas_tempos"] = [
                        round(t_ini + 0.0, 3),
                        round(t_ini + 0.65, 3),
                        round(t_ini + 1.30, 3),
                    ]
                frases_log.append(
                    {
                        "tipo": "silencio",
                        "evento": ev_nome,
                        "inicio": t_ini,
                        "fim": round(cursor + dur_s, 3),
                        "duracao": round(dur_s, 3),
                    }
                )
                cursor += dur_s
                continue

            limpo_wav, dur_bloco, raw_words_bloco = blocos_prontos[u_idx]
            wavs_concat.append(limpo_wav)
            t_bloco_ini = cursor

            if unidade["eh_cta_pausa"]:
                if cta_fala_inicio is None:
                    cta_fala_inicio = round(t_bloco_ini, 3)
                cta_fala_fim = round(t_bloco_ini + dur_bloco, 3)

            frases_dist = _distribuir_duracao_no_grupo(
                unidade["itens"], t_bloco_ini, dur_bloco, raw_words_bloco
            )

            for item, t_ini, dur_frase, raw_words_f in frases_dist:
                texto = sanitizar_texto_tts(item["texto"])
                perfil_voz = normalizar_perfil_voz(item.get("perfil_voz"))
                palavras_frase = alinhar_palavras_na_frase(texto, t_ini, dur_frase, raw_words_f)

                evento_principal = None
                if usa_eventos_explicitos:
                    for ev_nome in item.get("eventos_inicio", []):
                        if ev_nome not in eventos:
                            eventos[ev_nome] = round(t_ini, 3)
                        if evento_principal is None:
                            evento_principal = ev_nome
                    for ev_nome, alvo in item.get("eventos_palavra", []):
                        if ev_nome in eventos:
                            continue
                        encontrou = False
                        for p in palavras_frase:
                            limpa_p = re.sub(r"[^a-z0-9]", "", normalizar_chave(p["palavra"]))
                            if limpa_p.startswith(alvo):
                                eventos[ev_nome] = p["inicio"]
                                if evento_principal is None:
                                    evento_principal = ev_nome
                                encontrou = True
                                break
                        if not encontrou and ev_nome.startswith("hit_") and palavras_frase:
                            eventos[ev_nome] = palavras_frase[len(palavras_frase) // 2]["inicio"]
                else:
                    evento_principal = mapear_evento_legado(texto)
                    if evento_principal and evento_principal not in eventos:
                        eventos[evento_principal] = round(t_ini, 3)
                    chave_f = normalizar_chave(texto)
                    if "apita" in chave_f and "mapa_apito" not in eventos:
                        for p in palavras_frase:
                            if normalizar_chave(p["palavra"]).startswith("apita"):
                                eventos["mapa_apito"] = p["inicio"]
                                break
                    if "a luz cai" in chave_f and "apagao_00" not in eventos:
                        for idx_p, p in enumerate(palavras_frase):
                            if normalizar_chave(p["palavra"]).startswith("luz"):
                                t_ap = palavras_frase[idx_p - 1]["inicio"] if idx_p > 0 else p["inicio"]
                                eventos["apagao_00"] = t_ap
                                break

                grupos_frase = quebrar_em_grupos_legenda(palavras_frase)
                for grp in grupos_frase:
                    g_idx = len(grupos_todos)
                    palavras_grp = []
                    for p in grp:
                        p_idx = len(palavras_todas)
                        registro = {
                            "indice": p_idx,
                            "frase_indice": frase_idx,
                            "grupo_indice": g_idx,
                            "palavra": p["palavra"],
                            "inicio": p["inicio"],
                            "duracao": p["duracao"],
                            "fim": p["fim"],
                        }
                        palavras_todas.append(registro)
                        palavras_grp.append(
                            {
                                "indice": p_idx,
                                "palavra": p["palavra"],
                                "inicio": p["inicio"],
                                "duracao": p["duracao"],
                                "fim": p["fim"],
                            }
                        )
                    g_ini = palavras_grp[0]["inicio"]
                    g_fim = palavras_grp[-1]["fim"]
                    grupos_todos.append(
                        {
                            "indice": g_idx,
                            "frase_indice": frase_idx,
                            "texto": " ".join(p["palavra"] for p in palavras_grp),
                            "inicio": g_ini,
                            "fim": g_fim,
                            "duracao": round(max(0.02, g_fim - g_ini), 3),
                            "palavras": palavras_grp,
                        }
                    )

                frases_log.append(
                    {
                        "tipo": "fala",
                        "frase_indice": frase_idx,
                        "perfil_voz": perfil_voz,
                        "texto": texto,
                        "evento": evento_principal,
                        "inicio": round(t_ini, 3),
                        "fim": round(t_ini + dur_frase, 3),
                        "duracao": round(dur_frase, 3),
                    }
                )
                frase_idx += 1

            cursor += dur_bloco

        cauda = 0.22 if cta_modo in ("meio", "pausa_meio") else CAUDA_FINAL
        if cauda > 0:
            cauda_wav = tmp_dir / "cauda_final.wav"
            cursor += gerar_wav_silencio(cauda_wav, cauda)
            wavs_concat.append(cauda_wav)

        wav_mestre = tmp_dir / "voz_limpa_mestre.wav"
        dur_mp3 = concatenar_wavs_para_mp3(wavs_concat, wav_mestre, VOZ_LIMPA_MP3)

    duracao_total = round(dur_mp3, 3)
    voz_blocos = consolidar_voz_blocos(frases_log)
    eventos["duracao_total"] = duracao_total
    eventos["provedor_voz"] = provedor_final
    eventos["blocos_api_chamadas"] = blocos_api_chamadas
    eventos["velocidade_voz"] = round(velocidade, 3)
    eventos["frases"] = frases_log
    eventos["voz_blocos"] = voz_blocos
    eventos["cta_modo"] = cta_modo
    if sfx_eventos:
        eventos["sfx_eventos"] = sfx_eventos
    katana_tempos = sorted(
        float(v)
        for k, v in eventos.items()
        if re.fullmatch(r"hit_\d+", str(k)) and isinstance(v, (int, float))
    )
    if katana_tempos:
        eventos["katana_eventos"] = katana_tempos

    cta_meio_inicio: float | None = None
    cta_meio_fim: float | None = None
    cta_texto = "COMENTE EU QUERO"

    if cta_modo == "pausa_meio":
        if cta_pausa_inicio is None or cta_pausa_fim is None:
            raise RuntimeError(
                "cta_modo='pausa_meio' (V5/V5.2/V6) exige bloco [CTA_PAUSA]...[/CTA_PAUSA] no roteiro."
            )
        if exige_parte_2 and "corte_parte_2" not in eventos:
            raise RuntimeError(
                "cta_modo='pausa_meio' com saidas_partes exige marcador [CORTE_PARTE_2] no roteiro."
            )
        cta_meio_inicio = cta_pausa_inicio
        cta_meio_fim = cta_pausa_fim
        eventos["cta_meio_inicio"] = cta_meio_inicio
        eventos["cta_meio_fim"] = cta_meio_fim
        if cta_fala_inicio is not None:
            eventos["cta_fala_inicio"] = cta_fala_inicio
        if cta_fala_fim is not None:
            eventos["cta_fala_fim"] = cta_fala_fim
        eventos["cta_texto"] = cta_texto
    elif cta_modo == "meio":
        if "cta_meio" in eventos:
            alvo_ini = float(eventos["cta_meio"])
            cta_meio_inicio = round(max(duracao_total * 0.44, min(duracao_total * 0.58, alvo_ini)), 3)
        else:
            cta_meio_inicio = round(duracao_total * 0.48, 3)
        cta_meio_fim = round(min(duracao_total - 1.2, cta_meio_inicio + 2.2), 3)
        eventos["cta_meio_inicio"] = cta_meio_inicio
        eventos["cta_meio_fim"] = cta_meio_fim
        eventos["cta_texto"] = cta_texto
    elif exige_parte_2 and "corte_parte_2" not in eventos:
        raise RuntimeError(
            "Video com saidas_partes exige marcador [CORTE_PARTE_2] no roteiro."
        )

    obrigatorios_por_roteiro = {
        "roteiro_02.txt": [
            "gancho", "hora_02", "gps_rota", "sem_destino", "rua_escura",
            "retrovisor", "destino_acidente", "hora_0206", "freio", "caminhao",
            "quase", "sussurro", "plot_twist", "proximo_acidente", "cta", "cta_acao",
            "duracao_total",
        ],
        "roteiro_03.txt": [
            "gancho", "vibra_cama", "pix_1", "marina_ri", "congela", "nao_acende",
            "hora_0313", "pix_2", "desc_2", "tranca_porta", "corredor_breu",
            "pix_3", "fecha_janela", "trava_janela", "hora_0314", "pix_4",
            "msg_final", "plot_twist", "guarda_roupa", "abre_devagar",
            "cta", "cta_acao", "duracao_total",
        ],
        "roteiro_04.txt": [
            "gancho", "acorda_sussurro", "baba_som", "sussurro",
            "olha_tela", "berco_vazio", "coracao_dispara", "sombra_corredor",
            "passos_corredor", "corre_quarto", "abre_porta", "acende_luz",
            "bebe_dormindo", "alivio", "olha_volta", "camera_vazio",
            "alguem_parado", "atras_porta", "olha_lente", "plot_twist",
            "impacto_twist", "luz_apaga", "apaga_hit",
            "cta", "cta_acao", "duracao_total",
        ],
        "roteiro_05.txt": [
            "gancho", "vibra_1", "pedido_chegou", "congela", "nao_pediu",
            "tela_interfone", "entregador", "sem_piscar", "interfone",
            "corre_porta", "passa_corrente", "porta_impacto",
            "olha_volta", "portaria_vazia", "vibra_2", "cta_meio",
            "pedido_entregue", "foto_anexo", "abre_imagem", "impacto_twist",
            "sacola_mesa", "mesa_cozinha", "foto_corredor", "atras_dela",
            "plot_twist", "duracao_total",
        ],
        "roteiro_06.txt": [
            "gancho", "entra_elevador", "andar_12", "aperta_terreo",
            "portas_fecham", "porta_elevador", "painel_desce",
            "num_11", "num_10", "num_09", "luz_pisca", "trava_seco",
            "andar_06", "tranco_elevador", "painel_apaga", "olha_espelho",
            "reflexo_atrasado", "cta_pausa", "cta_meio_inicio", "cta_meio_fim",
            "luz_volta", "passa_terreo", "passa_g1", "passa_g2",
            "botao_emergencia", "alarme_interfone", "dois_subsolos",
            "visor_s3", "portas_abrem_s3", "corredor_escuro", "corte_parte_2",
            "lado_fora", "cadeira_metal", "esmaga_botao", "interfone_chia",
            "interfone", "voz_porteiro", "nao_sai", "cinco_minutos",
            "alguem_dentro", "olha_camera", "espelho_novo", "voltou_terreo",
            "celular_vibra", "msg_amigo", "igual_voce", "camera_hall",
            "impacto_twist", "final_espelho", "reflexo_sorri", "plot_twist",
            "duracao_total",
        ],
        "roteiro_07.txt": [
            "gancho", "pede_carro", "tela_app", "nota_49", "carro_encosta",
            "entra_carro", "coloca_fone", "porta_impacto", "sem_boa_noite",
            "acelera_avenida", "motor_acelerando", "celular_vibra", "ligacao_app",
            "atende_erro", "voz_motorista_1", "nao_e_ele", "cta_pausa",
            "cta_meio_inicio", "cta_meio_fim", "diego_congela", "olha_retrovisor",
            "sem_piscar", "puxa_macaneta", "trava_acionada", "trava_porta_carro",
            "gps_desvio", "estrada_terra", "corte_parte_2", "finge_calma",
            "esquina_delegacia", "nao_cai", "velocimetro_120", "motor_acelerando_2",
            "motorista_grita", "fez_ontem", "olha_carona", "inclina_corpo",
            "quatro_celulares", "ligacoes_perdidas", "celular_tocando",
            "rua_sem_saida", "impacto_twist", "final_retrovisor", "olhos_sorriem",
            "plot_twist", "duracao_total",
        ],
    }
    if roteiro_path.name in obrigatorios_por_roteiro:
        faltando = [k for k in obrigatorios_por_roteiro[roteiro_path.name] if k not in eventos]
        if faltando:
            raise RuntimeError(f"Eventos obrigatorios ausentes para {roteiro_path.name}: {faltando}")

    dados_timestamps = {
        "video_id": int(video_ativo["id"]),
        "slug": str(video_ativo["slug"]),
        "titulo": str(video_ativo["titulo"]),
        "parte_label": str(video_ativo.get("parte_label", "PARTE 1")),
        "cta_modo": cta_modo,
        "roteiro": roteiro_path.name,
        "roteiro_sha256": roteiro_sha256,
        "audio": VOZ_LIMPA_MP3.name,
        "motor": provedor_final,
        "provedor_voz": provedor_final,
        "blocos_api_chamadas": blocos_api_chamadas,
        "velocidade_voz": round(velocidade, 3),
        "voz": voz_usada,
        "duracao_total": duracao_total,
        "texto": texto_falado,
        "max_palavras_por_grupo": 3,
        "total_palavras": len(palavras_todas),
        "total_grupos": len(grupos_todos),
        "voz_blocos": voz_blocos,
        "grupos": grupos_todos,
        "palavras": palavras_todas,
    }
    if cta_modo in ("meio", "pausa_meio"):
        dados_timestamps["cta_meio_inicio"] = cta_meio_inicio
        dados_timestamps["cta_meio_fim"] = cta_meio_fim
        dados_timestamps["cta_texto"] = cta_texto
        if cta_modo == "pausa_meio":
            if cta_fala_inicio is not None:
                dados_timestamps["cta_fala_inicio"] = cta_fala_inicio
            if cta_fala_fim is not None:
                dados_timestamps["cta_fala_fim"] = cta_fala_fim
    if "corte_parte_2" in eventos:
        dados_timestamps["corte_parte_2"] = eventos["corte_parte_2"]

    TIMESTAMPS_JSON.write_text(
        json.dumps(dados_timestamps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    EVENTOS_JSON.write_text(
        json.dumps(eventos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if args.roteiro is None:
        validar_artefatos_audio(PASTA_AUDIO)

    contagem_perfis: dict[str, int] = {}
    for vb in voz_blocos:
        contagem_perfis[vb["perfil"]] = contagem_perfis.get(vb["perfil"], 0) + 1
    resumo_perfis = ", ".join(f"{k}={v}" for k, v in sorted(contagem_perfis.items()))

    print(
        f"Gerado {VOZ_LIMPA_MP3.name}: {duracao_total:.3f}s | provedor_voz={provedor_final} "
        f"(chamadas={blocos_api_chamadas}, atempo={velocidade:.2f}) | "
        f"{len(palavras_todas)} palavras em {len(grupos_todos)} grupos | "
        f"voz_blocos ({len(voz_blocos)}): {resumo_perfis}"
    )
    if cta_modo == "pausa_meio" and cta_meio_inicio is not None and cta_meio_fim is not None:
        if "corte_parte_2" in eventos:
            corte_p2 = float(eventos["corte_parte_2"])
            pct_corte = (corte_p2 / max(0.1, duracao_total)) * 100.0
            corte_txt = f"Corte Parte 2 em {corte_p2:.2f}s ({pct_corte:.1f}%)"
        else:
            corte_txt = "Short unico (sem corte Parte 2)"
        print(
            f"CTA tela cheia V5.2 em {cta_meio_inicio:.2f}s..{cta_meio_fim:.2f}s ({cta_meio_fim - cta_meio_inicio:.2f}s) | "
            f"{corte_txt} | Plot twist em {eventos.get('plot_twist')}s"
        )
    elif cta_modo == "meio" and cta_meio_inicio is not None and cta_meio_fim is not None:
        pct0 = (cta_meio_inicio / max(0.1, duracao_total)) * 100.0
        pct1 = (cta_meio_fim / max(0.1, duracao_total)) * 100.0
        print(
            f"Plot twist em {eventos.get('plot_twist')}s | "
            f"CTA unica no meio em {cta_meio_inicio:.2f}s..{cta_meio_fim:.2f}s ({pct0:.0f}%..{pct1:.0f}%, sem CTA final)"
        )
    elif "cta" in eventos:
        cta_dur = duracao_total - float(eventos["cta"])
        print(f"Plot twist em {eventos.get('plot_twist')}s | CTA em {eventos['cta']}s (ultimos {cta_dur:.2f}s)")


if __name__ == "__main__":
    main()
