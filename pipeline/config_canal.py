"""Carregador centralizado e tolerante a falhas de `config_canal.json` (motor multi-canal).

Permite transformar o repositorio em um template reutilizavel para qualquer nicho,
idioma ou identidade visual editando apenas `config_canal.json` na raiz. Caso o
arquivo esteja ausente, corrompido ou com campos faltando, cada chave recai com
seguranca nos valores padrao do canal "E Se Você?".
"""

from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG_CANAL = RAIZ / "config_canal.json"

PRIVACIDADES_YOUTUBE_VALIDAS: tuple[str, ...] = ("public", "unlisted", "private")

PILARES_PADRAO: tuple[dict[str, str], ...] = (
    {
        "id": "cenarios_hipoteticos",
        "nome": "Cenários hipotéticos ('E se você...?')",
        "gancho": (
            "Comece direto em segunda pessoa com uma pergunta ou situação extrema de "
            "sobrevivência/decisão ('E se você ficasse preso em...', 'E se você acordasse...', "
            "'E se o mundo parasse por...')."
        ),
        "instrucoes": (
            "Conduza o espectador passo a passo em segunda pessoa ('você') pelos minutos ou horas "
            "seguintes, mostrando reações físicas reais, dilemas psicológicos e escalada de tensão "
            "até uma consequência final surpreendente e memorável na última frase."
        ),
        "exemplos": (
            "ficar preso dentro de um submarino sem comunicação, acordar sendo a única pessoa na "
            "cidade, aceitar ficar 30 dias numa sala branca sem relógio por 10 milhões, perder a "
            "gravidade por 60 segundos, ficar preso num teleférico durante tempestade, acordar 24 "
            "horas antes de um apagão global"
        ),
        "horario_padrao": "15:00",
        "titulo_fallback": "E Se Você Acordasse Sozinho",
    },
    {
        "id": "curiosidades_bizarras",
        "nome": "Curiosidades bizarras e fatos pouco conhecidos",
        "gancho": (
            "Abra com um fato real chocante, contraintuitivo ou que quase ninguém sabe "
            "('Você sabia que existe...', 'Existe um fenômeno real...', "
            "'Seu cérebro esconde um mecanismo bizarro...')."
        ),
        "instrucoes": (
            "Apresente um fato real e documentado de ciência, psicologia, biologia humana, "
            "engenharia, natureza extrema ou história pouco conhecida. Estruture em camadas: "
            "o que parece comum, a explicação surpreendente por trás e o detalhe final "
            "inquietante que prende a atenção."
        ),
        "exemplos": (
            "o som oceânico The Bloop e o Ponto Nemo, a síndrome da mão alheia, a Zona de Silêncio "
            "no deserto, por que o espaço tem cheiro de metal queimado, protocolos reais ocultos "
            "de aviação ou usinas, o fenômeno da paralisia de decisão em ambientes extremos, "
            "cidades subterrâneas reais"
        ),
        "horario_padrao": "14:20",
        "titulo_fallback": "O Fato Bizarro Que Poucos Sabem",
    },
    {
        "id": "misterios_reais",
        "nome": "Mistérios reais e lugares proibidos",
        "gancho": (
            "Abra apresentando um lugar proibido real, um sinal sem explicação ou um caso "
            "documentado ('Existe um lugar no planeta onde entrar é crime...', "
            "'Há um mistério real que ninguém resolveu...')."
        ),
        "instrucoes": (
            "Narre um mistério real ou local de acesso vetado por governos/ciência com detalhes "
            "concretos (localização, datas, protocolos de segurança ou registros oficiais), "
            "aumentando o clima investigativo até o enigma sem resposta que fecha o episódio."
        ),
        "exemplos": (
            "Ilha Sentinela do Norte, Cofre Global de Sementes de Svalbard, Caverna de Lascaux "
            "fechada ao público, Ilha da Queimada Grande, estação de rádio fantasma UVB-76, "
            "área de exclusão em ilhas remotas, arquivos secretos de expedições polares ou "
            "navios encontrados à deriva"
        ),
        "horario_padrao": "21:40",
        "titulo_fallback": "O Lugar Proibido Que Ninguém Entra",
    },
    {
        "id": "suspense_urbano",
        "nome": "Relatos curtos de suspense urbano",
        "gancho": (
            "Abra situando rapidamente um personagem comum em um cenário urbano cotidiano realista "
            "(metrô, hotel, hospital, estacionamento, entrega, portaria, escritório vazio) com um "
            "detalhe fora do normal."
        ),
        "instrucoes": (
            "Desenvolva um micro-suspense psicológico realista e cinematográfico sem repetir "
            "cenários do histórico (evite repetir madrugada no quarto ou espelho se já apareceram "
            "recentemente), escalando a tensão até um plot twist seco e perturbador na última frase."
        ),
        "exemplos": (
            "último vagão do metrô parado no túnel, câmera de segurança de estacionamento "
            "subterrâneo, quarto de hotel com recado escrito no mesmo dia, plantão noturno em "
            "hospital, cabine de pedágio isolada, entrega de encomenda sem remetente"
        ),
        "horario_padrao": "23:18",
        "titulo_fallback": "O Aviso no Último Vagão",
    },
)

CONFIG_PADRAO: dict[str, Any] = {
    "nome_canal": "E Se Você?",
    "idioma": "pt-BR",
    "pilares_editoriais": [dict(p) for p in PILARES_PADRAO],
    "estilo_visual_prompt": (
        "hyper-detailed 3D dark cinematic digital illustration, moody volumetric lighting, "
        "Unreal Engine 5 quality, dramatic shadows, vertical 9:16 framing, "
        "no text, no letters, no watermark"
    ),
    "velocidade_voz": 1.02,
    "cta_final": "E você, o que faria nessa situação, me conta aqui nos comentários?",
    "hashtags_padrao": ["shorts", "curiosidades", "ese", "suspense"],
    "privacidade_youtube": "public",
}

PERFIS_IDIOMA: dict[str, dict[str, str]] = {
    "pt-br": {
        "codigo": "pt-BR",
        "nome_humano": "português do Brasil",
        "edge_voz_principal": "pt-BR-AntonioNeural",
        "edge_voz_secundaria": "pt-BR-FabioNeural",
        "gtts_lang": "pt",
        "gtts_tld": "com.br",
    },
    "pt-pt": {
        "codigo": "pt-PT",
        "nome_humano": "português de Portugal",
        "edge_voz_principal": "pt-PT-DuarteNeural",
        "edge_voz_secundaria": "pt-PT-RaquelNeural",
        "gtts_lang": "pt",
        "gtts_tld": "pt",
    },
    "en-us": {
        "codigo": "en-US",
        "nome_humano": "English (US)",
        "edge_voz_principal": "en-US-AndrewNeural",
        "edge_voz_secundaria": "en-US-BrianNeural",
        "gtts_lang": "en",
        "gtts_tld": "com",
    },
    "en-gb": {
        "codigo": "en-GB",
        "nome_humano": "English (UK)",
        "edge_voz_principal": "en-GB-RyanNeural",
        "edge_voz_secundaria": "en-GB-ThomasNeural",
        "gtts_lang": "en",
        "gtts_tld": "co.uk",
    },
    "es-es": {
        "codigo": "es-ES",
        "nome_humano": "español",
        "edge_voz_principal": "es-ES-AlvaroNeural",
        "edge_voz_secundaria": "es-ES-TrianaNeural",
        "gtts_lang": "es",
        "gtts_tld": "es",
    },
    "es-mx": {
        "codigo": "es-MX",
        "nome_humano": "español latinoamericano",
        "edge_voz_principal": "es-MX-JorgeNeural",
        "edge_voz_secundaria": "es-MX-DaliaNeural",
        "gtts_lang": "es",
        "gtts_tld": "com.mx",
    },
    "fr-fr": {
        "codigo": "fr-FR",
        "nome_humano": "français",
        "edge_voz_principal": "fr-FR-HenriNeural",
        "edge_voz_secundaria": "fr-FR-RemyMultilingualNeural",
        "gtts_lang": "fr",
        "gtts_tld": "fr",
    },
}

RE_EMOJI = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)
RE_IDIOMA = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,4})?$")


def _limpar_texto(valor: Any) -> str:
    txt = unicodedata.normalize("NFC", str(valor or ""))
    txt = RE_EMOJI.sub("", txt)
    txt = txt.replace("\u2014", ", ").replace("\u2013", ", ")
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt.strip()


def _slug_id(texto: str, fallback: str) -> str:
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(ch) != "Mn"
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", sem_acento).strip("_").lower()
    return slug[:40] or fallback


def _slug_hashtag(texto: str) -> str:
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"[^a-zA-Z0-9]+", "", sem_acento.lstrip("#")).lower()


def _normalizar_pilares(bruto: Any) -> list[dict[str, str]]:
    """Normaliza pilares_editoriais aceitando objetos completos, parciais ou strings simples."""
    if not isinstance(bruto, list) or not bruto:
        return [dict(p) for p in PILARES_PADRAO]

    padroes_por_id = {p["id"]: p for p in PILARES_PADRAO}
    normalizados: list[dict[str, str]] = []
    ids_vistos: set[str] = set()

    for idx, item in enumerate(bruto, start=1):
        if isinstance(item, str):
            nome = _limpar_texto(item)
            if not nome:
                continue
            pid_base = _slug_id(nome, fallback=f"pilar_{idx}")
            pid = pid_base
            suf = 2
            while pid in ids_vistos:
                pid = f"{pid_base}_{suf}"
                suf += 1
            ids_vistos.add(pid)
            base = padroes_por_id.get(pid, {})
            normalizados.append(
                {
                    "id": pid,
                    "nome": nome,
                    "gancho": base.get("gancho")
                    or f"Abra nos primeiros 3 segundos com um gancho direto e impossivel de ignorar sobre {nome}.",
                    "instrucoes": base.get("instrucoes")
                    or f"Desenvolva o episodio sobre {nome} em frases curtas, ritmo crescente e fechamento memoravel.",
                    "exemplos": base.get("exemplos") or f"temas ineditos e concretos dentro de {nome}",
                    "horario_padrao": base.get("horario_padrao") or "15:00",
                    "titulo_fallback": base.get("titulo_fallback") or nome[:48],
                }
            )
            continue

        if not isinstance(item, dict):
            continue
        nome = _limpar_texto(item.get("nome") or item.get("titulo") or item.get("id") or "")
        pid_raw = _limpar_texto(item.get("id") or "")
        if not nome and not pid_raw:
            continue
        pid_base = _slug_id(pid_raw or nome, fallback=f"pilar_{idx}")
        pid = pid_base
        suf = 2
        while pid in ids_vistos:
            pid = f"{pid_base}_{suf}"
            suf += 1
        ids_vistos.add(pid)

        base = padroes_por_id.get(pid, {})
        nome_final = nome or base.get("nome") or pid.replace("_", " ").title()
        gancho = _limpar_texto(item.get("gancho")) or base.get("gancho") or (
            f"Abra nos primeiros 3 segundos com um gancho direto e envolvente sobre {nome_final}."
        )
        instrucoes = _limpar_texto(item.get("instrucoes")) or base.get("instrucoes") or (
            f"Conduza o episodio sobre {nome_final} com fatos concretos, ritmo humano e virada forte no final."
        )
        exemplos = _limpar_texto(item.get("exemplos")) or base.get("exemplos") or (
            f"temas ineditos e concretos dentro de {nome_final}"
        )
        horario = _limpar_texto(item.get("horario_padrao")) or base.get("horario_padrao") or "15:00"
        titulo_fb = _limpar_texto(item.get("titulo_fallback")) or base.get("titulo_fallback") or nome_final[:48]
        normalizados.append(
            {
                "id": pid,
                "nome": nome_final,
                "gancho": gancho,
                "instrucoes": instrucoes,
                "exemplos": exemplos,
                "horario_padrao": horario,
                "titulo_fallback": titulo_fb,
            }
        )

    return normalizados if normalizados else [dict(p) for p in PILARES_PADRAO]


def _normalizar_hashtags(bruto: Any) -> list[str]:
    if isinstance(bruto, str):
        itens = re.split(r"[\s,;]+", bruto)
    elif isinstance(bruto, list):
        itens = bruto
    else:
        return list(CONFIG_PADRAO["hashtags_padrao"])

    limpas: list[str] = []
    vistas: set[str] = set()
    for raw in itens:
        slug = _slug_hashtag(str(raw))
        if len(slug) >= 2 and slug not in vistas:
            vistas.add(slug)
            limpas.append(slug)
    return limpas if limpas else list(CONFIG_PADRAO["hashtags_padrao"])


def _normalizar_velocidade(bruto: Any) -> float:
    if bruto is None or isinstance(bruto, bool):
        return float(CONFIG_PADRAO["velocidade_voz"])
    try:
        val = float(bruto)
    except (TypeError, ValueError):
        return float(CONFIG_PADRAO["velocidade_voz"])
    return round(max(0.5, min(2.0, val)), 3)


def _normalizar_privacidade(bruto: Any) -> str:
    raw = str(bruto or "").strip().lower()
    if raw in PRIVACIDADES_YOUTUBE_VALIDAS:
        return raw
    return str(CONFIG_PADRAO["privacidade_youtube"])


def _normalizar_idioma(bruto: Any) -> str:
    raw = str(bruto or "").strip().replace("_", "-")
    if RE_IDIOMA.match(raw):
        partes = raw.split("-")
        if len(partes) == 2:
            return f"{partes[0].lower()}-{partes[1].upper()}"
        return partes[0].lower()
    return str(CONFIG_PADRAO["idioma"])


def resolver_caminho_config(caminho: Path | str | None = None) -> Path:
    if caminho is not None:
        return Path(caminho)
    env_path = os.environ.get("CONFIG_CANAL_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else (RAIZ / p)
    return ARQUIVO_CONFIG_CANAL


def carregar_config_canal(caminho: Path | str | None = None) -> dict[str, Any]:
    """Carrega e normaliza `config_canal.json`, aplicando fallback seguro em campos ausentes."""
    alvo = resolver_caminho_config(caminho)
    bruto: dict[str, Any] = {}
    if alvo.is_file():
        try:
            lido = json.loads(alvo.read_text(encoding="utf-8"))
            if isinstance(lido, dict):
                bruto = lido
            else:
                print(
                    f"AVISO config_canal.json ({alvo.name}) nao e um objeto JSON; usando padroes.",
                    flush=True,
                )
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"AVISO falha ao ler {alvo.name} ({exc}); usando configuracao padrao do canal.",
                flush=True,
            )

    cfg = copy.deepcopy(CONFIG_PADRAO)
    nome = _limpar_texto(bruto.get("nome_canal"))
    if nome:
        cfg["nome_canal"] = nome

    cfg["idioma"] = _normalizar_idioma(bruto.get("idioma"))
    cfg["pilares_editoriais"] = _normalizar_pilares(bruto.get("pilares_editoriais"))

    estilo = _limpar_texto(bruto.get("estilo_visual_prompt"))
    if estilo:
        cfg["estilo_visual_prompt"] = estilo

    cfg["velocidade_voz"] = _normalizar_velocidade(bruto.get("velocidade_voz"))

    cta = _limpar_texto(bruto.get("cta_final"))
    if cta:
        cfg["cta_final"] = cta

    cfg["hashtags_padrao"] = _normalizar_hashtags(bruto.get("hashtags_padrao"))
    cfg["privacidade_youtube"] = _normalizar_privacidade(bruto.get("privacidade_youtube"))
    return cfg


def obter_hashtags_plataforma(
    plataforma: str,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Adapta `hashtags_padrao` para YouTube Shorts, Instagram Reels, TikTok ou Telegram."""
    cfg = config if isinstance(config, dict) else carregar_config_canal()
    base_cfg = _normalizar_hashtags(cfg.get("hashtags_padrao"))
    plat = str(plataforma or "").strip().lower()

    if plat == "youtube":
        prefixo = ["shorts"]
        ignorar: set[str] = {"reels"}
    elif plat == "instagram":
        prefixo = ["reels"]
        ignorar = {"shorts"}
    elif plat == "tiktok":
        prefixo = []
        ignorar = {"shorts", "reels"}
    else:
        prefixo = ["shorts"] if "shorts" not in base_cfg else []
        ignorar = set()

    saida: list[str] = []
    vistas: set[str] = set()
    for tag in prefixo + base_cfg + (["fyp"] if plat == "tiktok" else []):
        if tag in ignorar or tag in vistas:
            continue
        vistas.add(tag)
        saida.append(tag)
    return saida or list(CONFIG_PADRAO["hashtags_padrao"])


def obter_perfil_idioma(idioma: str | None = None) -> dict[str, str]:
    """Retorna vozes Edge-TTS, configuracao gTTS e nome humano para o idioma do canal."""
    codigo = _normalizar_idioma(idioma)
    chave = codigo.lower()
    if chave in PERFIS_IDIOMA:
        return dict(PERFIS_IDIOMA[chave])
    pref = chave.split("-", 1)[0]
    for k, perfil in PERFIS_IDIOMA.items():
        if k.startswith(pref + "-"):
            copia = dict(perfil)
            copia["codigo"] = codigo
            return copia
    return {
        "codigo": codigo,
        "nome_humano": codigo,
        "edge_voz_principal": "pt-BR-AntonioNeural",
        "edge_voz_secundaria": "pt-BR-FabioNeural",
        "gtts_lang": pref or "pt",
        "gtts_tld": "com",
    }
