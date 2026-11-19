"""Regra permanente 'Sempre Video Novo' e controle de numeracao do pipeline.

Le `historico_videos.json` na raiz do repositorio para:
1. Garantir que o video em producao tenha tema, slug e roteiro ineditos em relacao aos anteriores.
2. Resolver automaticamente o arquivo de roteiro ativo e o caminho de saida livre
   (`output/short_02.mp4`, `output/short_03.mp4`, ...), sem sobrescrever videos publicados.

Uso CLI (na raiz do repositorio):
    python3 pipeline/historico.py verificar
    python3 pipeline/historico.py saida
    python3 pipeline/historico.py roteiro
    python3 pipeline/historico.py status
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_HISTORICO = RAIZ / "historico_videos.json"

STOPWORDS_TEMA = {
    "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no",
    "nas", "nos", "para", "por", "com", "que", "um", "uma", "sobre", "seu", "sua",
    "se", "ao", "ate", "mas", "ou", "sem", "proprio", "propria", "exata", "exato",
}


def normalizar_texto(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn"
    )
    limpo = re.sub(r"[^a-z0-9\s]", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", limpo).strip()


def tokens_tema(texto: str) -> set[str]:
    return {
        tok
        for tok in normalizar_texto(texto).split()
        if len(tok) >= 3 and tok not in STOPWORDS_TEMA
    }


def carregar_historico(caminho: Path = ARQUIVO_HISTORICO) -> dict:
    if not caminho.is_file():
        raise SystemExit(f"Arquivo de historico nao encontrado: {caminho}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("videos"), list):
        raise SystemExit(f"Formato invalido em {caminho}: campo 'videos' ausente.")
    return dados


def _similares(video_a: dict, video_b: dict) -> tuple[bool, str]:
    slug_a = normalizar_texto(video_a.get("slug", ""))
    slug_b = normalizar_texto(video_b.get("slug", ""))
    if slug_a and slug_a == slug_b:
        return True, f"slug duplicado '{video_a.get('slug')}'"

    rot_a = str(video_a.get("roteiro", "")).strip()
    rot_b = str(video_b.get("roteiro", "")).strip()
    if rot_a and rot_a == rot_b:
        return True, f"roteiro reutilizado '{rot_a}'"

    tema_a = normalizar_texto(video_a.get("tema", ""))
    tema_b = normalizar_texto(video_b.get("tema", ""))
    if tema_a and tema_a == tema_b:
        return True, "tema identico"

    kw_a = {normalizar_texto(k) for k in video_a.get("palavras_chave", []) if str(k).strip()}
    kw_b = {normalizar_texto(k) for k in video_b.get("palavras_chave", []) if str(k).strip()}
    if kw_a and kw_b:
        inter = kw_a & kw_b
        menor = min(len(kw_a), len(kw_b))
        if menor > 0 and (len(inter) / menor) >= 0.5:
            return True, f"palavras-chave repetidas ({sorted(inter)})"

    toks_a = tokens_tema(video_a.get("tema", "") + " " + video_a.get("titulo", ""))
    toks_b = tokens_tema(video_b.get("tema", "") + " " + video_b.get("titulo", ""))
    if toks_a and toks_b:
        inter_t = toks_a & toks_b
        menor_t = min(len(toks_a), len(toks_b))
        if menor_t >= 3 and (len(inter_t) / menor_t) >= 0.55:
            return True, f"sobreposicao alta de tema ({sorted(inter_t)})"

    return False, ""


def proximo_numero_livre(dados: dict | None = None) -> int:
    dados = dados or carregar_historico()
    usados = {int(v["id"]) for v in dados.get("videos", []) if "id" in v}
    n = 1
    while n in usados:
        n += 1
    return n


def validar_historico(dados: dict | None = None) -> dict:
    dados = dados or carregar_historico()
    videos = dados["videos"]
    if not videos:
        raise SystemExit("historico_videos.json nao possui nenhum video registrado.")

    ids_vistos: set[int] = set()
    saidas_vistas: set[str] = set()
    for v in videos:
        vid = int(v["id"])
        if vid in ids_vistos:
            raise SystemExit(f"ID duplicado no historico_videos.json: {vid}")
        ids_vistos.add(vid)

        saida_esperada = f"output/short_{vid:02d}.mp4"
        saida_reg = str(v.get("saida", "")).strip()
        if saida_reg != saida_esperada:
            raise SystemExit(
                f"Video {vid} com caminho de saida inconsistente: '{saida_reg}' (esperado '{saida_esperada}')."
            )
        if saida_reg in saidas_vistas:
            raise SystemExit(f"Caminho de saida duplicado no historico: {saida_reg}")
        saidas_vistas.add(saida_reg)

    # Verifica unicidade de tema entre todos os pares registrados.
    for i in range(len(videos)):
        for j in range(i + 1, len(videos)):
            repetido, motivo = _similares(videos[i], videos[j])
            if repetido:
                raise SystemExit(
                    f"Regra 'Sempre Video Novo' violada entre Video {videos[i]['id']:02d} "
                    f"e Video {videos[j]['id']:02d}: {motivo}."
                )

    id_atual = dados.get("video_atual")
    atual = None
    if id_atual is not None:
        for v in videos:
            if int(v["id"]) == int(id_atual):
                atual = v
                break
    if atual is None:
        em_prod = [v for v in videos if v.get("status") == "em_producao"]
        atual = em_prod[-1] if em_prod else videos[-1]

    if atual.get("status") == "publicado":
        prox = proximo_numero_livre(dados)
        raise SystemExit(
            f"O video_atual ({atual['id']:02d} - {atual.get('titulo')}) ja esta marcado como 'publicado'. "
            f"Registre o proximo video inedito (id={prox}, output/short_{prox:02d}.mp4) em historico_videos.json."
        )

    return atual


def obter_video_atual(validar: bool = True) -> dict:
    dados = carregar_historico()
    if validar:
        return validar_historico(dados)
    id_atual = dados.get("video_atual")
    for v in dados["videos"]:
        if int(v["id"]) == int(id_atual):
            return v
    return dados["videos"][-1]


def caminho_roteiro_atual() -> Path:
    atual = obter_video_atual(validar=True)
    caminho = RAIZ / str(atual["roteiro"])
    if not caminho.is_file():
        raise SystemExit(f"Roteiro do video atual nao encontrado: {caminho}")
    return caminho


def caminho_saida_atual() -> Path:
    dados = carregar_historico()
    atual = validar_historico(dados)
    vid = int(atual["id"])
    # Protecao extra: impede sobrescrever qualquer short marcado como publicado.
    saidas_publicadas = {
        str(v.get("saida", "")).strip()
        for v in dados["videos"]
        if v.get("status") == "publicado"
    }
    saida_rel = f"output/short_{vid:02d}.mp4"
    if saida_rel in saidas_publicadas:
        prox = proximo_numero_livre(dados)
        saida_rel = f"output/short_{prox:02d}.mp4"
    return RAIZ / saida_rel


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida e consulta historico_videos.json.")
    parser.add_argument(
        "acao",
        nargs="?",
        default="status",
        choices=["status", "verificar", "saida", "roteiro", "proximo"],
        help="Informacao ou validacao desejada.",
    )
    args = parser.parse_args()

    dados = carregar_historico()
    if args.acao == "proximo":
        n = proximo_numero_livre(dados)
        print(f"output/short_{n:02d}.mp4")
        return

    atual = validar_historico(dados)
    if args.acao == "saida":
        print(caminho_saida_atual().relative_to(RAIZ).as_posix())
    elif args.acao == "roteiro":
        print(caminho_roteiro_atual().relative_to(RAIZ).as_posix())
    elif args.acao == "verificar":
        total = len(dados["videos"])
        pub = sum(1 for v in dados["videos"] if v.get("status") == "publicado")
        print(
            f"Historico OK ({total} videos registrados, {pub} publicado(s)). "
            f"Ativo: Video {int(atual['id']):02d} '{atual['titulo']}' "
            f"({atual['roteiro']} -> {atual['saida']})."
        )
    else:
        print(json.dumps({"video_atual": atual, "proximo_livre": proximo_numero_livre(dados)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
