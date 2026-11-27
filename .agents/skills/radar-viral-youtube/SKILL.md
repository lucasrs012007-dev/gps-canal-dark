---
name: radar-viral-youtube
description: Executa varredura ao vivo multiplataforma gratuita (YouTube Shorts, TikTok e Instagram Reels em EN, ES e PT) com fabrica_v2/radar/radar_viral.py, memoria de frescor vistos.json (--apenas-novos), analise universal --analisar-url (4 frames visuais + fallback Whisper local para TikTok/Reels) e propostas ineditas para a fabrica_v2. Acione automaticamente sempre que o usuario pedir algo como "varre o youtube", "varre youtube, tiktok e insta", "busca no tiktok", "roda o radar", "radar viral", "procura videos virais", "busca temas novos", "busca temas virais", "so coisas novas", "minerar youtube", "analisa esse video", "analisa esse tiktok", "analisa esse reel" ou "ganchos que retem".
---

# Radar Viral Multiplataforma (Modo 2 Gratuito para Fabrica V2)

Skill operacional de inteligencia editorial ao vivo para a `fabrica_v2`. Varre YouTube Shorts, TikTok e Instagram Reels em ingles, espanhol e portugues sem depender de cota da YouTube Data API, sem login/cookies e sem reutilizar varreduras antigas.

## Regras obrigatorias de execucao

Sempre que esta skill for acionada, siga exatamente esta sequencia:

### 1. Varredura 100% ao vivo e multiplataforma (zero cache obsoleto)
- **NUNCA** reaproveite resultados antigos de `fabrica_v2/radar/output/` como se fossem atuais.
- Antes de rodar, confirme se `yt-dlp` esta disponivel (`yt-dlp --version`); se nao estiver instalado, execute `pip install -U yt-dlp`.
- Execute sempre uma nova varredura ao vivo via `fabrica_v2/radar/radar_viral.py`:
  - Varredura multiplataforma aberta (padrao: `youtube,tiktok,instagram`):
    ```bash
    python3 fabrica_v2/radar/radar_viral.py --plataformas youtube,tiktok,instagram --dias 180 --max-per-query 8 --limite 15
    ```
  - Varredura com assunto especifico (ex.: `"busca no tiktok sobre gravidade"`, `"varre youtube, tiktok e insta sobre sono"`):
    ```bash
    python3 fabrica_v2/radar/radar_viral.py --plataformas youtube,tiktok,instagram --tema "<assunto>" --dias 180 --max-per-query 8 --limite 15
    ```
  - Se o usuario pedir uma plataforma especifica (ex.: `"busca no tiktok"`), ajuste `--plataformas tiktok` ou `--plataformas youtube,tiktok`.
  - Se o usuario pedir `"so coisas novas"` ou evitar videos ja vistos em rodadas anteriores, passe `--apenas-novos` (filtra automaticamente usando a memoria `fabrica_v2/radar/output/vistos.json`).

### 2. Anti-repeticao e alinhamento editorial da Fabrica V2
- Leia `fabrica_v2/episodios/*/roteiro.json` e `fabrica_v2/REGRAS_EPISODIO.md` antes de montar suas recomendacoes.
- Confira as flags `ja_produzido` (contra `ep01`+) e `ja_visto` (contra `vistos.json`) em `fabrica_v2/radar/output/radar_dados.json`.
- Garanta aderencia estrita a `fabrica_v2/REGRAS_EPISODIO.md`: padrao `61s` a `65s` (`11` a `12` cenas de ritmo ultra-rapido), rotacao obrigatoria entre os 5 modelos oficiais de gancho (proibido repetir `"Voce! E, voce mesmo!"`), CTA falada no `loop` e cauda seca de `0,25s`.

### 3. Entrega completa dos outliers e leads multiplataforma
- Leia `fabrica_v2/radar/output/radar_dados.json` e apresente **TODOS** os melhores outliers frescos do YouTube Shorts (padrao `10` a `15`, ou a quantidade pedida pelo usuario) **mais** os leads descobertos no TikTok e Instagram Reels (informando com transparencia quando alguma rede limitar metadados sem login).
- Para cada item, informe dados medidos diretamente do JSON gerado:
  - Plataforma (`YOUTUBE`, `TIKTOK`, `INSTAGRAM`), status de frescor (`NOVO` vs `VISTO`) e status no canal (`INEDITO` vs `JA PRODUZIDO`)
  - Titulo, canal/perfil e link clicavel
  - `views`, `views_por_dia`, `outlier_ratio`, `engajamento_taxa` e `duracao_s` (quando disponiveis)
  - Gancho real falado (`gancho_transcricao`), quando capturado
- Informe tambem os caminhos atualizados de `fabrica_v2/radar/output/relatorio_viral.html` e `fabrica_v2/radar/output/radar_resumo.md`.

### 4. Modo analise universal de URL (`--analisar-url`: YouTube, TikTok e Reels)
- Sempre que o usuario enviar um link do **YouTube**, **TikTok** ou **Instagram Reel** (ex.: `"analisa esse video"`, `"analisa esse tiktok"`, `"analisa esse reel"`, `"por que esse video reteve"`):
  1. Execute:
     ```bash
     python3 fabrica_v2/radar/radar_viral.py --analisar-url "<URL>"
     ```
     O script detecta automaticamente a plataforma, coleta metadados via `yt-dlp`, extrai 4 frames visuais (`frame_0.5s.jpg`, `frame_1.5s.jpg`, `frame_3.0s.jpg`, `frame_5.0s.jpg`) em `/tmp/radar_frames/` e captura o gancho verbal `0-15s` (usando legenda nativa no YouTube e **fallback automatico para Whisper local** via `ffmpeg` 16kHz mono no TikTok ou videos sem legenda).
  2. Abra com a ferramenta de visao (`view_file`) todos os 4 frames extraidos em `/tmp/radar_frames/` (`frame_0.5s.jpg`, `frame_1.5s.jpg`, `frame_3.0s.jpg`, `frame_5.0s.jpg`) e tambem `/tmp/radar_frames/thumbnail_hd.jpg` quando disponivel.
  3. Decomponha objetivamente:
     - **Tecnica e gancho visual (0s a 5s):** estilo de animacao/edicao, contraste, elemento que trava o scroll, mudanca visual entre 0.5s, 1.5s, 3.0s e 5.0s, texto em tela.
     - **Gancho verbal (0s a 15s):** frase real obtida pela legenda ou Whisper local, ritmo e promessa de curiosidade.
     - **Como traduzir e superar na `fabrica_v2`:** adaptacao 100% original (nunca plagio) para o motor Canvas 2D Opus (`scenes.js`), Beto, HUD dedicado e ritmo de `61s-65s`.

### 5. Fechamento obrigatorio com propostas prontas para a Fabrica V2
- Encerre **toda** execucao com **3 a 5 propostas de episodios 100% ineditos e adaptados culturalmente ao Brasil** no padrao `61s` a `65s` (`11` a `12` cenas ultra-rapidas), prontas para entrar em producao na `fabrica_v2` com uma unica confirmacao do usuario.
- Cada proposta deve conter:
  1. **Slug sugerido** (proximo `epXX_<tema>`) e titulo PT-BR com `#Shorts`.
  2. **Referencia de inspiracao** (plataforma + metrica medida do outlier/lead, sem copiar roteiro).
  3. **Modelo de gancho** (1 a 5 da `REGRAS_EPISODIO.md`) e **frase de abertura inedita** (maximo 2,5s).
  4. **Elemento visual / HUD central** na estetica Opus (medidor vertical, barra VU, cronometro ou contador exponencial).
  5. **Escalada compacta (11-12 cenas) + Plot Twist + CTA falada no loop final**.

## Restricoes de seguranca e higiene
- **Zero chamadas a API do Gemini** durante a varredura do radar.
- **Zero segredos, cookies ou chaves** em logs, comandos ou arquivos versionados.
- **Zero emoji, zero travessao e zero meia-risca** em todos os arquivos gerados ou editados.
- Nunca versionar `fabrica_v2/radar/output/` (`vistos.json`, relatorios) ou `/tmp/radar_frames/` no Git.
