---
name: viralstick-animacao-2d
description: "Regras obrigatorias V4 (Dopamina Visual + Tipografia Cinetica Katana + Selo PARTE 1) para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920): rig articulado de 10 pontos flat em capsula, Depth of Field otimizado, fundos vibrantes pulsando na tensao, particulas continuas, cortes dinamicos a cada 1,0s a 1,8s, screen shake nos impactos, selo PARTE 1 no topo esquerdo, hits Katana nos picos de choque, legendas pop-in em amarelo/vermelho, regra Sempre Video Novo e checklist visual de 5 etapas. Use sempre que construir ou revisar o player Canvas de um Short animado por codigo."
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16) - Motor V4 (Katana + Parte 1)

Skill permanente de direcao de arte, rigging, dopamina visual, tipografia cinetica e camera para YouTube Shorts verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)`, verificacao de planos via `window.getShots()` e auditoria de impactos via `window.getKatanaHits()`.

## 0. Regra permanente "Sempre Video Novo"

- Antes de gerar qualquer novo Short, consulte `historico_videos.json` atraves de `pipeline/historico.py`.
- Nunca repita tema, slug, roteiro ou palavras-chave centrais de um video ja registrado.
- Todo novo video recebe automaticamente a proxima numeracao livre (`output/short_02.mp4`, `output/short_03.mp4`, `output/short_04.mp4`, ...), preservando intactos os videos ja publicados e salvando backup do `player.html` anterior em `arquivo/video_NN/player.html`.

## 1. Personagem flat em capsula e rig articulado de 10 pontos

Padrao visual oficial: **estilo flat limpo em capsula**, com tronco arredondado solido sem contornos pretos pesados, cabeca redonda expressiva com cabelo natural sem costura e gola/capuz aberto sobre os ombros (nunca um anel fechado que lembre "capacete de astronauta"), e olhos grandes que arregalam dramaticamente no choque.

O corpo segue coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros:
1. `cabeca`: centro craniano com inclinacao dinamica (`headTilt`), cabelo recortado e expressao limpa sem bordas pesadas.
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (angulo anatomico coerente com a direcao do olhar).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda limitada para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, baba eletronica, volante, macaneta, porta).
7. `quadril`: pivo central do tronco em capsula e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda.
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`) em planos de corpo inteiro, com sombra de contato visivel.

## 2. Motor V3/V4: fundos vibrantes, pulso de tensao, particulas e profundidade de campo

- **Paleta de dopamina visual (zero fundos chapados mortos)**:
  - Fundos base vibrantes: azul-marinho eletrico (`#0A0F1D`) e roxo profundo cinematografico (`#130926`), sempre com gradiente atmosferico e luz volumetrica sutil.
  - **Pulso emocional nos picos de tensao**: transicione e pulse o fundo para **vermelho-alerta (`#3B0A0A`)** nos momentos de perigo, susto e plot twist, ou para **amarelo-eletrico (`#261E0A`)** nos avisos anomalos e chamadas de atencao.
- **Particulas flutuantes continuas no fundo**: mantenha duas camadas de particulas deterministicas (derivadas de `t`, nunca `Math.random()`) flutuando sem interrupcao com paralaxe suave e cor adaptada ao estado emocional (ciano frio, verde visao noturna, violeta, ambar ou brasa vermelha).
- **Uma cor de destaque fixa no protagonista**: o protagonista veste sempre a mesma cor de destaque bem recortada contra o cenario noturno, garantindo leitura instantanea na tela do celular.
- **Profundidade de campo obrigatoria (Depth of Field otimizado)**: aplique blur no plano de fundo via buffer reduzido (`1/8` resolucao, ex. `135x240`, com `blur` leve equivalente a `blur(8px)` em 1080x1920) sempre que celular, monitor, notificacao, retrovisor, foto revelada, CTA ou close dramatico (`bigFace`) estiver em primeiro plano. Restaure `ctx.filter = 'none'` logo apos. Pre-renderize a vinheta uma unica vez fora do loop e evite granulado tile-by-tile no Canvas (use filtro `noise` no FFmpeg).
- **Rim light coerente com a fonte**: a borda iluminada do personagem acompanha exatamente a luz dominante da cena (painel/celular frio, monitor verde visao noturna, luz quente do quarto ou alerta vermelho).
- **Um relogio por vez**: na mudanca de horario, nunca desenhe dois horarios simultaneamente no mesmo quadro (incluindo telas de celular ou baba eletronica que ja exibem o horario no proprio visor); oculte o relogio durante a tela final de CTA.

## 3. Regra permanente do selo "PARTE 1" (V4)

Todo Short da serie exibe uma badge fixa, discreta e configuravel de continuidade no topo esquerdo:
- **Texto configuravel**: propriedade `parteLabel` (padrao `"PARTE 1"`, aceitando override via `eventos.json` campo `parte_label`, `window.parteLabel` ou query string `?parte=`).
- **Posicao na zona segura superior esquerda**: `x: 64`, `y: 165` em `1080x1920` (longe da margem cortada pelo YouTube Shorts/Reels e sem jamais encostar no relogio central ou no rosto).
- **Estilo obrigatorio**: fundo escuro semitransparente `rgba(10, 15, 29, 0.72)`, borda fina sutil (`1.5px` a `2px` clara semitransparente), cantos arredondados (`12px` a `14px`) e texto em **CAIXA ALTA** com cerca de `26px` (`bold`/`800`), medido dinamicamente para caber com folga interna.
- **Ciclo de visibilidade**: visivel durante toda a historia (`0 <= t < EV.cta - 0.08`) e **oculto automaticamente** no card final da CTA.

## 4. Motor V4 estilo Katana: tipografia cinetica de impacto

Nos **3 a 4 picos de choque** da historia (ex.: `"VAZIO"`, `"SOMBRA"`, `"ATRAS DA PORTA"`, `"APAGA"`), acione o modulo reutilizavel de tipografia cinetica estilo Katana sincronizado aos timestamps de `audio/eventos.json`:
- **Palavras gigantes ocupando a largura da tela**: texto em CAIXA ALTA ocupando ate ~88% da largura util (`maxW = 940px` em 1080px), sempre ajustado com `measureText` (`drawFittedText`) para nunca estourar a tela independentemente das fontes instaladas no sistema (Windows, macOS ou Linux/Colab). Frases de 2 a 3 palavras podem empilhar em 2 linhas gigantes centradas.
- **Animacao elastica com overshoot e stretch**: entrada ultra-rapida (`0.08s` a `0.12s`) com squash-and-stretch assimetrico (`scaleX` alargado + `scaleY` comprimido no impacto -> overshoot elastico -> assentamento em mola fechada derivada apenas de `t`), leve rotacao angular (`-3deg` a `+3deg`) e rasgo diagonal estilo lamina atras do texto.
- **Flashes curtos de 2 a 4 quadros**: nos primeiros `2 a 4` quadros (`0.067s` a `0.133s` a 30 fps) do hit, alterne flashes secos de alto contraste entre fundo preto (`#05070E`), branco (`#F8FAFC`) e vermelho-alerta (`#FF2A24` / `#3B0A0A`), retornando ao fundo escuro de alto impacto antes do corte limpo de volta a cena.
- **Zoom punch-in de camera**: cada hit soma um impulso imediato de zoom (`+0.12` a `+0.22`) e screen shake seco amortecido em `cameraFor(shot, t)`.
- **Determinismo, CPU e higiene visual**: zero `Math.random()`, zero filtros pesados extras por frame; durante a janela ativa do hit Katana (`~0.42s` a `0.55s`), suprima as legendas inferiores para evitar texto duplicado na tela e exponha `window.getKatanaHits()` para auditoria automatizada.

## 5. Troca de expressao escondida na piscada (2 frames antes da palavra)

- Nunca troque a expressao facial de forma seca com os olhos abertos.
- Toda mudanca de estado emocional (neutro, alivio, cetico, preocupado, medo, choque) dispara uma piscada curta (`~0.16s`, cerca de 5 quadros a 30 fps) iniciada **2 frames (`0.067s`) antes** do timestamp do evento-gatilho em `audio/eventos.json`.
- A troca de sobrancelhas, abertura ocular e tamanho de pupila ocorre exatamente no apice da palpebra fechada.

## 6. Modulo `bigFace` no climax

- No momento de choque ou virada central, corte para o modulo dedicado `bigFace`: close extremo no rosto sobre fundo desfocado (DOF) pulsando em `#3B0A0A`.
- Elementos obrigatorios: olhos grandes bem abertos com pupilas contraidas dentro da esclera branca, gota de suor frio, screen shake de alta frequencia e rim light dramatico coerente com a cena.

## 7. Ritmo V4: camera viva, cortes a cada 1,0s a 1,8s e screen shake

- **Zero planos estaticos longos**: garanta mudanca clara de enquadramento, zoom dinamico de camera ou novo elemento visual a cada **1,0s a 1,8s** durante todo o video.
- Exponha `window.getShots()` retornando a lista de planos com inicio, fim e duracao para auditoria automatizada (nenhum shot pode exceder `1,85s`).
- Combine movimento continuo (zoom dinamico, pan suave, punch-in/punch-out e handheld deterministico via `noise(t)`) com **screen shake amortecido** em todo impacto fisico, sonoro ou hit Katana.

## 8. Legendas pop-in (2 a 3 palavras, MAIUSCULAS, amarelo e vermelho)

- Leia os blocos ja segmentados de `audio/timestamps.json` (`grupos`), com **2 a 3 palavras por bloco**, nunca misturando o fim de uma frase com o inicio da seguinte.
- **Animacao pop-in obrigatoria**:
  - Cada bloco de legenda entra com curva elastica curta (`scale 0.68 -> 1.10 -> 1.00` nos primeiros `0,11s`).
  - A palavra ativa recebe micro-pop de enfase (`1.00 -> 1.12 -> 1.07`) ao ser pronunciada.
- **Estilo visual obrigatorio**:
  - Texto em **CAIXA ALTA (MAIUSCULAS)**, fonte grossa condensada.
  - Preenchimento branco (`#FFFFFF`) com **contorno preto espesso** (`strokeText` arredondado) e sombra suave.
  - Palavra-chave ativa destacada em **AMARELO (`#FFD400`)** ou **VERMELHO (`#FF3B30`)** para palavras de alerta, perigo, acidente ou terror.
  - Posicionada no terco inferior acima dos botoes nativos do YouTube Shorts, sem nunca cobrir o rosto, o relogio, o selo `"PARTE 1"` ou o botao visual da CTA final (e suprimida durante hits Katana em tela cheia).

## 9. Bloco final de CTA (ultimos ~3,5s)

- Apos o plot twist, reserve os ultimos ~3,5 segundos para a CTA de engajamento (`"Quer aprender a fazer videos assim no automatico? Comente EU QUERO."`).
- O cartao visual da CTA deve manter o ritmo de cortes (1,0s a 1,8s), ocultar o relogio e o selo `"PARTE 1"`, exibir uma pilula amarela ampla `#FFD400` com `drawFittedText` (padding lateral >= `56px`) e nunca estourar bordas em nenhuma fonte do sistema.

## 10. Checklist visual obrigatorio de 5 etapas

Antes de aprovar qualquer player ou render, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Zero sobreposicao critica e selo PARTE 1**: selo `"PARTE 1"` nitido em `(64, 165)` durante toda a historia e oculto na CTA; apenas um horario visivel por quadro; cartao CTA e legendas sem estourar margens ou cobrir o rosto.
2. **Enquadramento e anatomia limpos**: em corpo inteiro, pes firmes no chao com sombra de contato; proporcoes limpas, maos coerentes e sem efeito "capacete de astronauta".
3. **Ritmo V4 e hits Katana medidos**: `window.getShots()` confirma cortes entre `1,0s` e `1,8s`; `window.getKatanaHits()` confirma 3 a 4 impactos com flashes curtos, stretch elastico e punch-in sem vazar a largura da tela.
4. **Profundidade de campo e legendas pop-in**: fundo desfocado (DOF rapido) nos closes/telas e legendas em MAIUSCULAS com pop-in e destaque em `#FFD400` ou `#FF3B30`.
5. **Determinismo e integridade do twist + CTA**: chamar `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, com zero erros de console, preservando o plot twist e a CTA final.
