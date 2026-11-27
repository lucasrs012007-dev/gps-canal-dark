---
name: radar-viral-youtube
description: Executa varredura ao vivo no YouTube Shorts (EN, ES e PT) via yt-dlp com fabrica_v2/radar/radar_viral.py para descobrir outliers virais recentes, extrair ganchos reais de abertura, inspecionar frames de concorrentes e propor episodios ineditos para a fabrica_v2. Acione automaticamente sempre que o usuario pedir algo como "varre o youtube", "roda o radar", "radar viral", "procura videos virais", "busca temas novos", "busca temas virais", "minerar youtube", "analisa esse video", "analisa esse video concorrente" ou "ganchos que retem".
---

# Radar Viral YouTube (Varredura Ao Vivo para Fabrica V2)

Skill operacional de inteligencia editorial ao vivo para o canal da `fabrica_v2`. Descobre YouTube Shorts virais fora da curva em ingles, espanhol e portugues sem depender de cota da YouTube Data API e sem reutilizar resultados antigos.

## Regras obrigatorias de execucao

Sempre que esta skill for acionada, siga exatamente esta sequencia:

### 1. Varredura 100% ao vivo (zero cache obsoleto)
- **NUNCA** reaproveite resultados antigos de `fabrica_v2/radar/output/` como se fossem atuais.
- Antes de rodar, confirme se `yt-dlp` esta disponivel (`yt-dlp --version`); se nao estiver instalado, execute `pip install -U yt-dlp`.
- Execute sempre uma nova varredura ao vivo via `fabrica_v2/radar/radar_viral.py`:
  - Pedido aberto (ex.: `"varre o youtube"`, `"roda o radar"`, `"busca temas virais"`):
    ```bash
    python3 fabrica_v2/radar/radar_viral.py --dias 180 --max-per-query 8 --limite 15
    ```
  - Pedido com assunto especifico (ex.: `"roda o radar sobre gravidade"`, `"busca temas virais sobre sono"`):
    ```bash
    python3 fabrica_v2/radar/radar_viral.py --tema "<assunto>" --dias 180 --max-per-query 8 --limite 15
    ```
  - Se o usuario pedir uma janela diferente (ex.: "ultimos 30 dias") ou quantidade diferente (ex.: "traz 20 videos"), repasse `--dias <N>` e `--limite <N>` diretamente.

### 2. Anti-repeticao e alinhamento editorial da Fabrica V2
- Leia `fabrica_v2/episodios/*/roteiro.json` e `fabrica_v2/REGRAS_EPISODIO.md` antes de montar suas recomendacoes.
- Confira a flag `ja_produzido` retornada em `fabrica_v2/radar/output/radar_dados.json` e cruze manualmente com todos os `titulo` e `hook` ja existentes em `fabrica_v2/episodios/*/roteiro.json`.
- Garanta aderencia estrita a `Regra de Ganchos (Anti-Repeticao)` de `fabrica_v2/REGRAS_EPISODIO.md`: proibido repetir `"Voce! E, voce mesmo!"` ou qualquer abertura fixa ja usada; rotacione sempre entre os 5 modelos oficiais de gancho (Choque de numero absurdo, No meio do caos, Desafio de ego, Falsa vantagem + quebra, Contagem regressiva / aviso).

### 3. Entrega completa dos outliers encontrados
- Leia `fabrica_v2/radar/output/radar_dados.json` e apresente **TODOS** os melhores outliers frescos encontrados na rodada (padrao de `10` a `15` resultados, ou a quantidade pedida pelo usuario, nunca cortando arbitrariamente em 5).
- Para cada outlier apresentado, informe dados medidos diretamente do JSON gerado:
  - Posicao no ranking, idioma e status (`INEDITO` ou `JA PRODUZIDO`)
  - Titulo, canal e link clicavel do Short
  - `views`, `views_por_dia`, `outlier_ratio` (`views / max(inscritos, 1000)`), `engajamento_taxa` e `duracao_s`
  - Gancho real falado nos primeiros segundos (`gancho_transcricao`), quando capturado
- Informe tambem os caminhos atualizados de `fabrica_v2/radar/output/relatorio_viral.html` e `fabrica_v2/radar/output/radar_resumo.md`.

### 4. Modo analise profunda de concorrente (`--analisar-url`)
- Sempre que o usuario enviar uma URL do YouTube ou pedir para analisar visual/retencao de um video especifico (ex.: `"analisa esse video"`, `"analisa esse video concorrente"`, `"por que esse video reteve"`):
  1. Execute:
     ```bash
     python3 fabrica_v2/radar/radar_viral.py --analisar-url "<URL_DO_YOUTUBE>"
     ```
  2. Abra com a ferramenta de visao (`view_file`) os 4 frames extraidos em `/tmp/radar_frames/` (`frame_0.5s.jpg`, `frame_1.5s.jpg`, `frame_3.0s.jpg`, `frame_5.0s.jpg`) e tambem `/tmp/radar_frames/thumbnail_hd.jpg` quando disponivel.
  3. Decomponha objetivamente:
     - **Gancho visual (0s a 5s):** enquadramento, contraste, elemento de choque imediato, mudanca visual entre 0.5s, 1.5s, 3.0s e 5.0s, texto em tela.
     - **Gancho verbal (0s a 15s):** frase de abertura real da transcricao, promessa de curiosidade, ritmo de palavras.
     - **Mecanica de retencao:** qual tensao ou escala numerica obriga o espectador a ficar ate o final e comentar.
     - **Como superar no estilo Opus da `fabrica_v2`:** adaptacao 100% original (nunca plagio) usando Beto, HUD dedicado e escala dramatica.

### 5. Fechamento obrigatorio com propostas prontas para a Fabrica V2
- Encerre **toda** execucao com **3 a 5 propostas de episodios 100% ineditos e adaptados culturalmente ao Brasil** (moeda em reais, cotidiano brasileiro, referencias locais naturais), prontas para entrar em producao na `fabrica_v2` com uma unica confirmacao do usuario.
- Cada proposta deve conter:
  1. **Slug sugerido** (proximo `epXX_<tema>`) e titulo PT-BR com `#Shorts`.
  2. **Referencia de inspiracao** (qual mecanica psicologica veio de qual outlier medido, sem copiar roteiro).
  3. **Modelo de gancho** (1 a 5 da `REGRAS_EPISODIO.md`) e **frase de abertura inedita** (maximo 2,5s).
  4. **Elemento visual / HUD central** na estetica Opus (medidor vertical, cronometro, barra de risco, contador exponencial).
  5. **Escalada + Plot Twist + CTA falada no loop final** (para gerar comentarios e replay imediato).

## Restricoes de seguranca e higiene
- **Zero chamadas a API do Gemini** durante a varredura do radar.
- **Zero segredos** em logs, comandos ou arquivos de saida.
- **Zero emoji, zero travessao e zero meia-risca** em todos os arquivos gerados ou editados.
- Nunca versionar `fabrica_v2/radar/output/` ou `/tmp/radar_frames/` no Git.
