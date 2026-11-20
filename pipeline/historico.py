"""Regra permanente 'Sempre Video Novo', numeracao automatica e trava blindada contra audio velho.

Le `historico_videos.json` na raiz do repositorio para:
1. Garantir que o video em producao tenha tema, slug e roteiro ineditos em relacao aos anteriores.
2. Resolver automaticamente o arquivo de roteiro ativo e o caminho de saida livre
   (`output/short_03.mp4`, `output/short_04.mp4`, ...), sem sobrescrever videos publicados.
3. Validar carimbo de integridade (`video_id`, `titulo`, `roteiro_sha256`) e presenca da CTA
   obrigatoria ("COMENTE EU QUERO") em `audio/timestamps.json` e `audio/eventos.json` antes
   do sound design e da renderizacao.

Uso CLI (na raiz do repositorio):
    python3 pipeline/historico.py verificar
    python3 pipeline/historico.py validar-audio
    python3 pipeline/historico.py saida
    python3 pipeline/historico.py roteiro
    python3 pipeline/historico.py status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_HISTORICO = RAIZ / "historico_videos.json"
CTA_OBRIGATORIA = "comente eu quero"

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


def calcular_sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    h.update(caminho.read_bytes())
    return h.hexdigest()


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


def carimbo_roteiro_atual() -> dict:
    atual = obter_video_atual(validar=True)
    roteiro = caminho_roteiro_atual()
    cta_modo = str(atual.get("cta_modo", "final")).strip().lower() or "final"
    return {
        "video_id": int(atual["id"]),
        "slug": str(atual["slug"]),
        "titulo": str(atual["titulo"]),
        "parte_label": str(atual.get("parte_label", "PARTE 1")),
        "cta_modo": cta_modo,
        "roteiro": roteiro.name,
        "roteiro_sha256": calcular_sha256_arquivo(roteiro),
    }


def caminho_saida_atual() -> Path:
    dados = carregar_historico()
    atual = validar_historico(dados)
    vid = int(atual["id"])
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


def validar_artefatos_audio(
    pasta_audio: Path | None = None,
    exigir_cta: bool = True,
) -> dict:
    """Trava blindada contra audio velho: confere video_id, titulo, roteiro_sha256 e CTA obrigatoria.

    Suporta:
    - cta_modo == "meio" (V4.1): valida cta_modo, cta_meio_inicio, cta_meio_fim e cta_texto ("COMENTE EU QUERO")
      em ambos timestamps.json e eventos.json, sem exigir CTA falada no final.
    - cta_modo == "final" (legado V2-V4): valida "COMENTE EU QUERO" no final de timestamps.json.
    """
    pasta = pasta_audio or (RAIZ / "audio")
    ts_path = pasta / "timestamps.json"
    ev_path = pasta / "eventos.json"
    esperado = carimbo_roteiro_atual()

    dica = (
        "Apague audio/mix_final.mp3, audio/voz_limpa.mp3, audio/narracao.mp3, "
        "audio/timestamps.json e audio/eventos.json e rode novamente: "
        "python3 audio/gerar_narracao.py && python3 audio/sound_design.py"
    )

    for arq in (ts_path, ev_path):
        if not arq.is_file():
            raise SystemExit(f"BLOQUEADO (integridade de audio): arquivo ausente {arq.name}. {dica}")

    try:
        ts_dados = json.loads(ts_path.read_text(encoding="utf-8"))
        ev_dados = json.loads(ev_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"BLOQUEADO (integridade de audio): JSON corrompido ({exc}). {dica}")

    erros: list[str] = []
    for nome_arq, dados in (("timestamps.json", ts_dados), ("eventos.json", ev_dados)):
        vid_arq = dados.get("video_id")
        if vid_arq != esperado["video_id"]:
            erros.append(
                f"{nome_arq}: video_id={vid_arq!r} difere do video_atual={esperado['video_id']}"
            )
        tit_arq = dados.get("titulo")
        if tit_arq != esperado["titulo"]:
            erros.append(
                f"{nome_arq}: titulo={tit_arq!r} difere do esperado={esperado['titulo']!r}"
            )
        hash_arq = dados.get("roteiro_sha256")
        if not hash_arq or hash_arq != esperado["roteiro_sha256"]:
            erros.append(
                f"{nome_arq}: roteiro_sha256={(str(hash_arq)[:12] if hash_arq else None)!r} "
                f"difere do hash atual {esperado['roteiro_sha256'][:12]!r} ({esperado['roteiro']})"
            )

    if exigir_cta:
        modo_esperado = esperado["cta_modo"]
        if modo_esperado == "meio":
            dur_ref = float(ev_dados.get("duracao_total") or ts_dados.get("duracao_total") or 0.0)
            for nome_arq, dados in (("timestamps.json", ts_dados), ("eventos.json", ev_dados)):
                modo_arq = str(dados.get("cta_modo", "")).strip().lower()
                if modo_arq != "meio":
                    erros.append(
                        f"{nome_arq}: cta_modo={modo_arq!r} difere do esperado 'meio' (V4.1)"
                    )
                cta_txt = normalizar_texto(dados.get("cta_texto", ""))
                if CTA_OBRIGATORIA not in cta_txt:
                    erros.append(
                        f"{nome_arq}: cta_texto obrigatorio 'COMENTE EU QUERO' ausente ou invalido "
                        f"(recebido: {dados.get('cta_texto')!r})"
                    )
                ini = dados.get("cta_meio_inicio")
                fim = dados.get("cta_meio_fim")
                try:
                    ini_f = float(ini)
                    fim_f = float(fim)
                except (TypeError, ValueError):
                    erros.append(
                        f"{nome_arq}: cta_meio_inicio={ini!r} / cta_meio_fim={fim!r} invalidos"
                    )
                else:
                    perm = fim_f - ini_f
                    if ini_f <= 1.0 or fim_f <= ini_f or (dur_ref > 0 and fim_f >= dur_ref - 0.5):
                        erros.append(
                            f"{nome_arq}: janela cta_meio ({ini_f:.3f}s..{fim_f:.3f}s) fora do meio do video (dur={dur_ref:.3f}s)"
                        )
                    elif perm < 1.5 or perm > 3.5:
                        erros.append(
                            f"{nome_arq}: permanencia da CTA do meio ({perm:.2f}s) fora da faixa [1.5s, 3.5s]"
                        )
        else:
            palavras = ts_dados.get("palavras") or []
            ultimas_palavras = " ".join(str(p.get("palavra", "")) for p in palavras[-14:])
            cauda_texto = normalizar_texto(ultimas_palavras or str(ts_dados.get("texto", ""))[-120:])
            if CTA_OBRIGATORIA not in cauda_texto:
                erros.append(
                    "timestamps.json: CTA obrigatoria 'COMENTE EU QUERO' nao encontrada no final da narracao "
                    f"(trecho final lido: {ultimas_palavras!r})"
                )

    if erros:
        detalhes = "\n  - ".join(erros)
        raise SystemExit(
            f"BLOQUEADO (trava contra audio velho / cache corrompido):\n  - {detalhes}\n"
            f"Acao obrigatoria: {dica}"
        )

    return {
        "carimbo": esperado,
        "timestamps": ts_dados,
        "eventos": ev_dados,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida e consulta historico_videos.json.")
    parser.add_argument(
        "acao",
        nargs="?",
        default="status",
        choices=["status", "verificar", "validar-audio", "saida", "roteiro", "proximo"],
        help="Informacao ou validacao desejada.",
    )
    args = parser.parse_args()

    dados = carregar_historico()
    if args.acao == "proximo":
        n = proximo_numero_livre(dados)
        print(f"output/short_{n:02d}.mp4")
        return

    atual = validar_historico(dados)
    if args.acao == "validar-audio":
        res = validar_artefatos_audio()
        c = res["carimbo"]
        ev = res["eventos"]
        det_cta = (
            f"CTA 'COMENTE EU QUERO' confirmada [modo=meio, {float(ev['cta_meio_inicio']):.2f}s..{float(ev['cta_meio_fim']):.2f}s]"
            if c["cta_modo"] == "meio"
            else "CTA 'COMENTE EU QUERO' confirmada [modo=final]"
        )
        print(
            f"Integridade de audio OK: Video {c['video_id']:02d} '{c['titulo']}' "
            f"(sha256={c['roteiro_sha256'][:12]}, {det_cta})."
        )
    elif args.acao == "saida":
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
        print(
            json.dumps(
                {
                    "video_atual": atual,
                    "carimbo": carimbo_roteiro_atual(),
                    "proximo_livre": proximo_numero_livre(dados),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
