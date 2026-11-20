---
name: viralstick-animacao-2d
description: "Regras obrigatorias V5 (Dopamina Visual + Tipografia Cinetica Katana + CTA Dedicada em Tela Cheia no Meio + Videos Longos 1m30-2m com Corte Automatico PARTE 1 / PARTE 2) para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920). Use sempre que construir ou revisar o player Canvas de um Short ou serie em duas partes."
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16) - Motor V5 (Katana + CTA Tela Cheia + Parte 1 / Parte 2)

Skill permanente de direcao de arte, rigging, dopamina visual, tipografia cinetica, retencao e corte automatico em duas partes para YouTube Shorts e Reels verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)`, auditoria de planos via `window.getShots()`, impactos via `window.getKatanaHits()`, CTA dedicada via `window.getMidCta()` e ponto de corte via `window.getCorteParte2()`.

## 0. Regra permanente "Sempre Video Novo"

- Antes de gerar qualquer novo Short, consulte `historico_videos.json` atraves de `pipeline/historico.py`.
- Nunca repita tema, slug, roteiro ou palavras-chave centrais de um video ja registrado.
- Todo novo video recebe automaticamente a proxima numeracao livre (`output/short_05.mp4`, `output/short_06.mp4`, ...), preservando intactos os videos ja publicados e salvando backup do `player.html` anterior em `arquivo/video_NN/player.html`.

## 1. Personagem flat em capsula e rig articulado de 10 pontos

Padrao visual oficial: **estilo flat limpo em capsula**, com tronco arredondado solido sem contornos pretos pesados, cabeca redonda expressiva com cabelo natural sem costura e gola/capuz aberto sobre os ombros (nunca um anel fechado que lembre "capacete de astronauta"), e olhos grandes que arregalam dramaticamente no choque.

O corpo segue coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros:
1. `cabeca`: centro craniano com inclinacao dinamica (`headTilt`), cabelo recortado e expressao limpa sem bordas pesadas.
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (angulo anatomico coerente com a direcao do olhar).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda limitada para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, painel do elevador, interfone, macaneta).
7. `quadril`: pivo central do tronco em capsula e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda.
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`) em planos de corpo inteiro, com sombra de contato visivel.

## 2. Motor V5: fundos vibrantes, pulso de tensao, particulas e profundidade de campo

- **Paleta de dopamina visual (zero fundos chapados mortos)**:
  - Fundos base vibrantes: azul-marinho eletrico (`#0A0F1D`) e roxo profundo cinematografico (`#130926`), sempre com gradiente atmosferico e luz volumetrica sutil.
  - **Pulso emocional nos picos de tensao**: transicione e pulse o fundo para **vermelho-alerta (`#3B0A0A`)** nos momentos de perigo, susto e plot twist, ou para **amarelo-eletrico (`#261E0A`)** nos avisos anomalos e chamadas de atencao.
- **Particulas flutuantes continuas no fundo**: mantenha duas camadas de particulas deterministicas (derivadas de `t`, nunca `Math.random()`) flutuando sem interrupcao com paralaxe suave.
- **Uma cor de destaque fixa no protagonista**: o protagonista veste sempre a mesma cor de destaque bem recortada contra o cenario noturno.
- **Profundidade de campo obrigatoria (Depth of Field otimizado)**: aplique blur via buffer reduzido (`1/8` resolucao, ex. `135x240`, com `blur` leve equivalente a `blur(8px)`) sempre que celular, painel, interfone, foto revelada, CTA ou close dramatico (`bigFace`) estiver em primeiro plano. Pre-renderize a vinheta fora do loop e evite granulado tile-by-tile no Canvas (use filtro `noise` no FFmpeg).
- **Um relogio por vez**: nunca desenhe dois horarios simultaneamente no mesmo quadro; oculte o relogio durante closes de aparelhos com relogio proprio, durante hits Katana e durante a tela cheia da CTA.

## 3. Regra permanente do selo dinamico "PARTE 1" / "PARTE 2" (V5)

Todo video da serie exibe uma badge fixa, discreta e configuravel no topo esquerdo:
- **Posicao na zona segura superior esquerda**: `x: 64`, `y: 165` em `1080x1920`, fundo `rgba(10, 15, 29, 0.72)`, borda fina sutil (`2px`), cantos arredondados (`12px`) e texto em **CAIXA ALTA** (`26px`, `800`).
- **Troca automatica em videos de 2 partes (`[CORTE_PARTE_2]`)**:
  - Antes de `corte_parte_2` (ou em videos de parte unica), exibe `"PARTE 1"` (configuravel via `parteLabel`).
  - A partir de `t >= corte_parte_2`, muda automaticamente para `"PARTE 2"`.
- **Ciclo de visibilidade**: visivel durante toda a historia e **oculto durante a tela cheia da CTA** (`cta_modo: "pausa_meio"`).

## 4. Motor estilo Katana: tipografia cinetica de impacto

Nos **3 a 5 picos de choque** da historia (ex.: `"TRAVOU"`, `"S3"`, `"5 MINUTOS"`, `"SORRIU"`), acione o modulo reutilizavel de tipografia cinetica estilo Katana sincronizado aos timestamps de `audio/eventos.json`:
- **Palavras gigantes ajustadas por `measureText`**: ate `920px` de largura em `1080px`, nunca vazando da tela em fontes do Linux/Colab.
- **Animacao elastica com overshoot e stretch**: entrada ultra-rapida (`0.11s`) com squash-and-stretch assimetrico + assentamento em mola fechada derivada apenas de `t`, leve rotacao angular e rasgo diagonal estilo lamina.
- **Flashes curtos de 2 a 4 quadros**: alternancia branco (`#F8FAFC`), preto (`#05070E`) e vermelho-alerta (`#E11D2E`) nos 4 primeiros quadros com contraste maximo do texto.
- **Zoom punch-in de camera + screen shake** em `cameraFor(shot, t)` e supressao das legendas inferiores durante a janela do hit (`~0.42s` a `0.50s`).

## 5. Troca de expressao escondida na piscada e modulo `bigFace`

- Toda mudanca de estado emocional dispara uma piscada curta (`~0.16s`) iniciada **2 frames (`0.067s`) antes** do evento-gatilho em `audio/eventos.json`.
- No climax, corte para `bigFace`: close extremo no rosto sobre fundo desfocado (DOF) pulsando em `#3B0A0A`, pupilas contraidas, gota de suor frio, screen shake e rim light coerente.

## 6. Ritmo V5: cortes a cada 1,0s a 1,8s e legendas pop-in

- **Zero planos estaticos longos**: mesmo em videos longos de `1m30` a `2m`, mantenha mudanca clara de enquadramento, zoom dinamico ou elemento visual a cada **1,0s a 1,8s** (`window.getShots()` sem nenhum plano > `1,85s`).
- **Legendas pop-in**: blocos de 2 a 3 palavras de `audio/timestamps.json`, caixa alta, fonte grossa condensada, branco com contorno preto espesso, palavra ativa em `#FFD400` ou `#FF3B30`, posicionadas em `y: 1495` (ocultas durante hits Katana e durante a tela cheia da CTA para nao duplicar o texto do cartao).

## 7. Regra V5: CTA dedicada em tela cheia no meio (`cta_modo: "pausa_meio"`) + Corte Automatico Parte 1 / Parte 2

Para videos longos (`1m30` a `2m`) pensados para virar 1 video completo + 2 Shorts prontos (Parte 1 e Parte 2) com maxima retencao:
- **Marcador `[CTA_PAUSA] ... [/CTA_PAUSA]` no meio da Parte 1**:
  - A historia interrompe seco com efeito sonoro `glitch_cta` de freio/interrupcao.
  - O drone de suspense silencia completamente durante a janela `[cta_meio_inicio, cta_meio_fim]` (`~2,8s` a `4,5s`, duracao exata da fala + margens de entrada/saida).
  - O `player.html` ocupa **100% da tela** exibindo um cartao dedicado de altissimo contraste: fundo escuro cinematografico com borda amarela `#FFD400`, titulo `"QUER FAZER VÍDEOS ASSIM NO AUTOMÁTICO?"` e pilula amarela gigante `"COMENTE EU QUERO"` (100% medido com `drawFittedText` e padding lateral >= `56px` para nunca estourar em Linux/Colab), ocultando o selo `PARTE 1`, o relogio e as legendas redundantes durante o bloco.
  - A narracao fala exatamente: `"Quer aprender a fazer vídeos assim no automático? Comente EU QUERO."`
  - Ao encerrar a janela, entra novo `glitch_cta` curto e a historia retoma imediatamente no ponto de tensao.
- **Zero CTA no final (loop seco)**: tanto o final da Parte 1 (`corte_parte_2`) quanto o final da Parte 2 (`duracao_total`) cortam secos no climax/gancho sem card final e sem tela preta.
- **Marcador `[CORTE_PARTE_2]` e fatiamento automatico FFmpeg**:
  - `[CORTE_PARTE_2]` define `corte_parte_2` em `audio/eventos.json` e `audio/timestamps.json` (entre `35%` e `65%` da duracao total, sem ser narrado).
  - `render/renderizar.py` renderiza o video completo (`output/short_NN.mp4`) uma unica vez no Chromium e, quando `corte_parte_2` existe fora de `--teste`, fatia automaticamente via FFmpeg em `output/short_NN_parte1.mp4` (`0` ate `corte_parte_2`) e `output/short_NN_parte2.mp4` (`corte_parte_2` ate o final) sem re-renderizar o navegador.
- **Validacao blindada (`pipeline/historico.py`)**: valida `video_id`, `titulo`, `roteiro_sha256`, `cta_modo == "pausa_meio"`, permanencia da janela (`2.2s` a `5.5s`), presenca real das palavras `"COMENTE EU QUERO"` dentro da janela em `timestamps.json` e `corte_parte_2` valido em `[35%, 65%]`.

## 8. Checklist visual obrigatorio de 5 etapas

Antes de aprovar qualquer player ou render, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Selo dinamico PARTE 1 / PARTE 2 e tela cheia da CTA**: `"PARTE 1"` nitido em `(64, 165)` na Parte 1, oculto na tela cheia da CTA (`"QUER FAZER VÍDEOS ASSIM NO AUTOMÁTICO?"` + `"COMENTE EU QUERO"` sem estouro de borda), trocando para `"PARTE 2"` a partir de `corte_parte_2`, e encerramento seco sem card final.
2. **Enquadramento, anatomia e relogio unico**: pes firmes no chao com sombra de contato em corpo inteiro; apenas um horario visivel por quadro; proporcoes limpas sem efeito "capacete".
3. **Ritmo V5 e hits Katana medidos**: `window.getShots()` confirma cortes entre `1,0s` e `1,8s` ao longo de todo o video; `window.getKatanaHits()` confirma os impactos com flashes curtos e punch-in sem vazar a largura da tela.
4. **Profundidade de campo e legendas pop-in**: fundo desfocado (DOF rapido) nos closes/telas e legendas em MAIUSCULAS com pop-in em `#FFD400` ou `#FF3B30`.
5. **Determinismo e fatiamento Parte 1 / Parte 2**: `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, zero erros de console, e fatiamento FFmpeg validado com `ffprobe`.
