"""Pool central de chaves Gemini, rotacao de modelos e deteccao fail-fast de cota diaria.

Elimina travamentos por limite diario (ex.: 20 req/dia no free tier do Gemini):
1. Carrega automaticamente todas as chaves validas nas variaveis de ambiente:
   `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` (com fallback para `.env` local).
2. Detecta erros de cota diaria (`free_tier_requests`, `PerDay`, `limit: 20` ou
   `RESOURCE_EXHAUSTED` recorrente) e marca imediatamente a combinacao `(chave, modelo)`
   como esgotada nesta execucao, trocando na hora para a proxima chave ou proximo modelo
   sem ficar minutos dormindo em retry na mesma combinacao morta.
3. Fornece mascaramento seguro de chaves para logs e leitura opcional de `GROQ_API_KEY`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Iterator

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_ENV_PADRAO = RAIZ / ".env"

NOMES_ENV_CHAVES_GEMINI: tuple[str, ...] = (
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_2",
    "GEMINI_API_KEY_3",
)

MODELOS_TEXTO_GEMINI_PADRAO: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELO_PADRAO = "llama-3.3-70b-versatile"

_PLACEHOLDERS_CHAVE: tuple[str, ...] = (
    "sua_chave",
    "your_api_key",
    "changeme",
    "replace_me",
    "placeholder",
    "coloque_aqui",
    "coloque-aqui",
)

_RE_LIMITE_DIARIO_BAIXO = re.compile(
    r"\blimit\s*[:=]\s*(?:0|5|10|15|20|25|50)\b",
    flags=re.IGNORECASE,
)

_MARCADORES_COTA_DIARIA: tuple[str, ...] = (
    "free_tier_requests",
    "generate_content_free_tier",
    "generaterequestsperday",
    "requestsperday",
    "requests_per_day",
    "perday",
    "per_day",
    "per day",
    "daily limit",
    "daily quota",
    "quota exceeded for metric",
)

_MARCADORES_CHAVE_INVALIDA: tuple[str, ...] = (
    "api key not valid",
    "api_key_invalid",
    "invalid api key",
    "api key expired",
    "consumer has been suspended",
    "billing account",
)

_MARCADORES_MODELO_INDISPONIVEL: tuple[str, ...] = (
    "not found",
    "not_found",
    "is not found",
    "not supported",
    "does not support",
    "not enabled",
    "response_mime_type",
    "json mode",
    "deprecated",
)


def carregar_env_se_existir(caminho_env: Path = ARQUIVO_ENV_PADRAO) -> bool:
    """Carrega variaveis de `.env` local apenas quando ainda nao definidas no ambiente."""
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


def chave_parece_valida(valor: str | None) -> bool:
    """Confere formato minimo de API key sem aceitar placeholders ou espacos."""
    chave = str(valor or "").strip()
    if len(chave) < 10 or any(ch.isspace() for ch in chave):
        return False
    low = chave.lower()
    return not any(p in low for p in _PLACEHOLDERS_CHAVE)


def mascarar_chave(valor: str) -> str:
    """Retorna identificacao curta segura da chave para logs sem expor o segredo."""
    v = str(valor or "").strip()
    if len(v) <= 8:
        return "***"
    return f"{v[:4]}...{v[-4:]}"


def sanitizar_texto_sem_chaves(texto: str, chaves: Iterable[str]) -> str:
    """Remove qualquer API key conhecida de mensagens de erro antes de logar."""
    limpo = str(texto or "")
    for ch in chaves:
        c = str(ch or "").strip()
        if c and len(c) >= 8 and c in limpo:
            limpo = limpo.replace(c, "***API_KEY***")
    return limpo


def carregar_chaves_gemini(
    *,
    nomes_env: tuple[str, ...] = NOMES_ENV_CHAVES_GEMINI,
    chave_primaria: str | None = None,
    ler_env_arquivo: bool = True,
    incluir_ambiente: bool = True,
) -> list[tuple[str, str]]:
    """Retorna lista ordenada e deduplicada de `(nome_env, valor_chave)` validos."""
    if ler_env_arquivo and incluir_ambiente:
        carregar_env_se_existir()

    resultado: list[tuple[str, str]] = []
    vistas: set[str] = set()

    if chave_primaria is not None:
        prim = str(chave_primaria).strip()
        if chave_parece_valida(prim):
            nome_prim = "GEMINI_API_KEY"
            if incluir_ambiente:
                for nome in nomes_env:
                    if os.environ.get(nome, "").strip() == prim:
                        nome_prim = nome
                        break
            resultado.append((nome_prim, prim))
            vistas.add(prim)

    if incluir_ambiente:
        for nome in nomes_env:
            val = os.environ.get(nome, "").strip()
            if chave_parece_valida(val) and val not in vistas:
                resultado.append((nome, val))
                vistas.add(val)

    return resultado


def obter_groq_api_key(*, ler_env_arquivo: bool = True) -> str:
    """Retorna GROQ_API_KEY valida quando configurada, ou string vazia."""
    if ler_env_arquivo:
        carregar_env_se_existir()
    val = os.environ.get("GROQ_API_KEY", "").strip()
    return val if chave_parece_valida(val) else ""


def normalizar_nome_modelo(modelo: str) -> str:
    nome = str(modelo or "").strip()
    if nome.startswith("models/"):
        nome = nome[len("models/") :]
    return nome


def eh_erro_cota_diaria(
    mensagem: str,
    status_code: int | None = None,
    *,
    ocorrencias_429_seguidas: int = 0,
) -> bool:
    """Detecta erro de cota diaria (20 req/dia free tier, PerDay) ou RESOURCE_EXHAUSTED recorrente."""
    low = str(mensagem or "").lower()

    # Marcadores explicitos de limite diario no payload da Google API
    if any(m in low for m in _MARCADORES_COTA_DIARIA):
        # Evita falso positivo quando o texto diz explicitamente apenas PerMinute sem marcador diario
        tem_explicitamente_diario = any(
            m in low
            for m in (
                "free_tier_requests",
                "generate_content_free_tier",
                "generaterequestsperday",
                "requestsperday",
                "requests_per_day",
                "perday",
                "per_day",
                "per day",
                "daily",
            )
        )
        if tem_explicitamente_diario or _RE_LIMITE_DIARIO_BAIXO.search(low):
            return True

    if _RE_LIMITE_DIARIO_BAIXO.search(low) and (
        status_code == 429 or "quota" in low or "resource_exhausted" in low or "rate" in low
    ):
        return True

    if "daily" in low and any(tok in low for tok in ("quota", "limit", "exceeded", "exhausted")):
        return True

    # RESOURCE_EXHAUSTED ou HTTP 429 recorrente na mesma combinacao (chave, modelo)
    eh_429_ou_exhausted = (
        status_code == 429
        or "resource_exhausted" in low
        or "429" in low
        or "too many requests" in low
    )
    if eh_429_ou_exhausted and ocorrencias_429_seguidas >= 2:
        return True

    return False


def eh_erro_chave_invalida(mensagem: str, status_code: int | None = None) -> bool:
    """Detecta chave rejeitada/expirada (HTTP 401/403 ou API_KEY_INVALID)."""
    low = str(mensagem or "").lower()
    if status_code in (401, 403):
        return True
    if any(m in low for m in _MARCADORES_CHAVE_INVALIDA):
        return True
    if status_code == 400 and ("api key" in low or "api_key" in low):
        return True
    return False


def eh_erro_modelo_indisponivel(mensagem: str, status_code: int | None = None) -> bool:
    """Detecta modelo inexistente, sem suporte ou incompativel com o endpoint."""
    low = str(mensagem or "").lower()
    if status_code == 404:
        return True
    if any(m in low for m in _MARCADORES_MODELO_INDISPONIVEL):
        # Nao confunde erro de chave invalida com modelo indisponivel
        if not eh_erro_chave_invalida(low, status_code=status_code):
            return True
    return False


class GeminiPool:
    """Gerencia rotacao inteligente de `(chave, modelo)` com memoria de cotas esgotadas na execucao."""

    def __init__(
        self,
        chaves: list[tuple[str, str]],
        modelos: Iterable[str],
    ) -> None:
        self._chaves: list[tuple[str, str]] = []
        vistas_ch: set[str] = set()
        for nome, valor in chaves:
            val = str(valor or "").strip()
            if chave_parece_valida(val) and val not in vistas_ch:
                self._chaves.append((str(nome or "GEMINI_API_KEY"), val))
                vistas_ch.add(val)

        self._modelos: list[str] = []
        self.adicionar_modelos(modelos)

        self.esgotados: dict[tuple[str, str], str] = {}
        self.chaves_invalidas: dict[str, str] = {}
        self.modelos_indisponiveis: dict[str, str] = {}
        self.recorrencias_429: dict[tuple[str, str], int] = {}
        self.ultimo_ativo: tuple[str, str] | None = None

    @classmethod
    def from_env(
        cls,
        modelos: Iterable[str],
        *,
        chave_primaria: str | None = None,
        ler_env_arquivo: bool = True,
        incluir_ambiente: bool = True,
    ) -> "GeminiPool":
        chaves = carregar_chaves_gemini(
            chave_primaria=chave_primaria,
            ler_env_arquivo=ler_env_arquivo,
            incluir_ambiente=incluir_ambiente,
        )
        return cls(chaves=chaves, modelos=modelos)

    @property
    def chaves(self) -> list[tuple[str, str]]:
        return list(self._chaves)

    @property
    def modelos(self) -> list[str]:
        return list(self._modelos)

    @property
    def valores_chaves(self) -> list[str]:
        return [v for _, v in self._chaves]

    def total_chaves(self) -> int:
        return len(self._chaves)

    def nomes_chaves(self) -> list[str]:
        return [n for n, _ in self._chaves]

    def adicionar_modelos(self, novos_modelos: Iterable[str]) -> list[str]:
        adicionados: list[str] = []
        for m in novos_modelos:
            norm = normalizar_nome_modelo(m)
            if norm and norm not in self._modelos:
                self._modelos.append(norm)
                adicionados.append(norm)
        return adicionados

    def sanitizar(self, texto: str) -> str:
        return sanitizar_texto_sem_chaves(texto, self.valores_chaves)

    def esta_disponivel(self, nome_chave: str, modelo: str) -> bool:
        mod = normalizar_nome_modelo(modelo)
        if nome_chave in self.chaves_invalidas:
            return False
        if mod in self.modelos_indisponiveis:
            return False
        if (nome_chave, mod) in self.esgotados:
            return False
        return True

    def marcar_esgotado(self, nome_chave: str, modelo: str, motivo: str) -> None:
        mod = normalizar_nome_modelo(modelo)
        self.esgotados[(nome_chave, mod)] = self.sanitizar(motivo)[:240]
        if self.ultimo_ativo == (nome_chave, mod):
            self.ultimo_ativo = None

    def marcar_chave_invalida(self, nome_chave: str, motivo: str) -> None:
        self.chaves_invalidas[nome_chave] = self.sanitizar(motivo)[:240]
        if self.ultimo_ativo and self.ultimo_ativo[0] == nome_chave:
            self.ultimo_ativo = None

    def marcar_modelo_indisponivel(self, modelo: str, motivo: str) -> None:
        mod = normalizar_nome_modelo(modelo)
        self.modelos_indisponiveis[mod] = self.sanitizar(motivo)[:240]
        if self.ultimo_ativo and self.ultimo_ativo[1] == mod:
            self.ultimo_ativo = None

    def registrar_sucesso(self, nome_chave: str, modelo: str) -> None:
        mod = normalizar_nome_modelo(modelo)
        self.recorrencias_429[(nome_chave, mod)] = 0
        self.ultimo_ativo = (nome_chave, mod)

    def registrar_429(
        self,
        nome_chave: str,
        modelo: str,
        detalhe: str,
        *,
        status_code: int | None = 429,
    ) -> bool:
        """Registra erro 429/RESOURCE_EXHAUSTED; retorna True se cota diaria esgotou (fail-fast)."""
        mod = normalizar_nome_modelo(modelo)
        par = (nome_chave, mod)
        cont = self.recorrencias_429.get(par, 0) + 1
        self.recorrencias_429[par] = cont
        if eh_erro_cota_diaria(detalhe, status_code=status_code, ocorrencias_429_seguidas=cont):
            self.marcar_esgotado(nome_chave, mod, detalhe)
            return True
        return False

    def chaves_saudaveis_para_modelo(self, modelo: str) -> list[tuple[str, str]]:
        mod = normalizar_nome_modelo(modelo)
        return [(n, v) for n, v in self._chaves if self.esta_disponivel(n, mod)]

    def tem_outra_combinacao_disponivel(self, nome_chave_atual: str, modelo_atual: str) -> bool:
        mod_atual = normalizar_nome_modelo(modelo_atual)
        for nome, _ in self._chaves:
            for mod in self._modelos:
                if (nome, mod) != (nome_chave_atual, mod_atual) and self.esta_disponivel(nome, mod):
                    return True
        return False

    def iterar_combinacoes(
        self,
        *,
        estrategia: str = "chave_depois_modelo",
        modelo_preferido: str | None = None,
    ) -> Iterator[tuple[str, str, str]]:
        """Itera `(nome_chave, api_key, modelo)` pulando combinacoes esgotadas ou invalidas.

        Prioriza sempre `ultimo_ativo` (cache de sucesso na execucao atual) e em seguida:
        - `chave_depois_modelo`: esgota todas as chaves no modelo prioritario antes de descer de modelo.
        - `modelo_depois_chave`: testa todos os modelos na chave 1 antes de ir para a chave 2.
        """
        if not self._chaves or not self._modelos:
            return

        mapa_chaves = dict(self._chaves)
        modelos_ordem = list(self._modelos)
        if modelo_preferido:
            pref = normalizar_nome_modelo(modelo_preferido)
            if pref in modelos_ordem:
                modelos_ordem = [pref] + [m for m in modelos_ordem if m != pref]

        emitidos: set[tuple[str, str]] = set()

        # 1. Prioriza combinacao ja comprovada como ativa nesta execucao
        if self.ultimo_ativo is not None:
            nome_u, mod_u = self.ultimo_ativo
            if nome_u in mapa_chaves and mod_u in modelos_ordem and self.esta_disponivel(nome_u, mod_u):
                emitidos.add((nome_u, mod_u))
                yield nome_u, mapa_chaves[nome_u], mod_u

        # 2. Demais combinacoes saudaveis conforme estrategia
        if estrategia == "modelo_depois_chave":
            for nome, valor in self._chaves:
                for mod in modelos_ordem:
                    if (nome, mod) in emitidos or not self.esta_disponivel(nome, mod):
                        continue
                    emitidos.add((nome, mod))
                    yield nome, valor, mod
        else:
            for mod in modelos_ordem:
                for nome, valor in self._chaves:
                    if (nome, mod) in emitidos or not self.esta_disponivel(nome, mod):
                        continue
                    emitidos.add((nome, mod))
                    yield nome, valor, mod

    def resumo_estado(self) -> str:
        chaves_str = ", ".join(self.nomes_chaves()) or "nenhuma"
        esg = [f"{k}:{m}" for k, m in sorted(self.esgotados.keys())]
        inv = sorted(self.chaves_invalidas.keys())
        ind = sorted(self.modelos_indisponiveis.keys())
        return (
            f"chaves=[{chaves_str}] | modelos={self._modelos} | "
            f"esgotados={esg} | chaves_invalidas={inv} | modelos_indisponiveis={ind}"
        )
