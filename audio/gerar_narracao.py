"""Estação 2: gera audio/narracao.mp3 e audio/timestamps.json a partir do roteiro_01.txt.

Uso (Windows 10, na raiz do repositório):
    pip install "edge-tts>=7"
    python audio/gerar_narracao.py

Lê só a coluna de narração (segunda coluna dos blocos "[tempo] | narração | visual"),
sintetiza com edge-tts e grava o tempo de cada palavra falada (eventos WordBoundary).
"""

import asyncio
import json
import re
from pathlib import Path

import edge_tts

RAIZ = Path(__file__).resolve().parent.parent
ROTEIRO = RAIZ / "roteiro_01.txt"
PASTA_AUDIO = RAIZ / "audio"
MP3 = PASTA_AUDIO / "narracao.mp3"
TIMESTAMPS = PASTA_AUDIO / "timestamps.json"
TEXTO = PASTA_AUDIO / "narracao.txt"

VOZ = "pt-BR-AntonioNeural"
VELOCIDADE = "+12%"

# Linhas de bloco começam com "[NN - NN]"; ignora o cabeçalho "[Tempo em Segundos] | ...".
LINHA_BLOCO = re.compile(r"^\[\s*\d+\s*-\s*\d+\s*\]\s*\|")

TICKS_POR_SEGUNDO = 10_000_000  # edge-tts informa offset/duração em unidades de 100 ns


def extrair_narracao(caminho: Path) -> str:
    frases = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if LINHA_BLOCO.match(linha):
            colunas = [c.strip() for c in linha.split("|")]
            frases.append(colunas[1])
    if not frases:
        raise SystemExit("Nenhum bloco de narração encontrado no roteiro.")
    return " ".join(frases)


async def sintetizar(texto: str) -> list[dict]:
    comunicar = edge_tts.Communicate(texto, VOZ, rate=VELOCIDADE, boundary="WordBoundary")
    palavras = []
    with MP3.open("wb") as arquivo:
        async for pedaco in comunicar.stream():
            if pedaco["type"] == "audio":
                arquivo.write(pedaco["data"])
            elif pedaco["type"] == "WordBoundary":
                palavras.append(
                    {
                        "indice": len(palavras),
                        "palavra": pedaco["text"],
                        "inicio": round(pedaco["offset"] / TICKS_POR_SEGUNDO, 3),
                        "duracao": round(pedaco["duration"] / TICKS_POR_SEGUNDO, 3),
                    }
                )
    return palavras


def main() -> None:
    PASTA_AUDIO.mkdir(exist_ok=True)
    texto = extrair_narracao(ROTEIRO)
    TEXTO.write_text(texto + "\n", encoding="utf-8")
    palavras = asyncio.run(sintetizar(texto))
    dados = {
        "audio": "narracao.mp3",
        "voz": VOZ,
        "velocidade": VELOCIDADE,
        "texto": texto,
        "total_palavras": len(palavras),
        "palavras": palavras,
    }
    TIMESTAMPS.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(texto.split())} palavras no texto, {len(palavras)} eventos WordBoundary")
    if palavras:
        ultima = palavras[-1]
        print(f"última palavra termina em {ultima['inicio'] + ultima['duracao']:.3f}s")


if __name__ == "__main__":
    main()
