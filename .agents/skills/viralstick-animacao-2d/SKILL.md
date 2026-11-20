---
name: viralstick-animacao-2d
description: "Regras obrigatorias V4.1 (Dopamina Visual + Tipografia Cinetica Katana + Selo PARTE 1 + CTA Unica no Meio com Loop Seco) para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920): rig articulado de 10 pontos flat em capsula, Depth of Field otimizado, fundos vibrantes pulsando na tensao, particulas continuas, cortes dinamicos a cada 1,0s a 1,8s, screen shake nos impactos, selo PARTE 1 no topo esquerdo, hits Katana nos picos de choque, CTA visual unica no meio (~48% a 56%) sem card final, legendas pop-in em amarelo/vermelho, regra Sempre Video Novo e checklist visual de 5 etapas. Use sempre que construir ou revisar o player Canvas de um Short animado por codigo."
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16) - Motor V4.1 (Katana + Parte 1 + CTA Unica no Meio)

Skill permanente de direcao de arte, rigging, dopamina visual, tipografia cinetica e camera para YouTube Shorts verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)`, verificacao de planos via `window.getShots()` e auditoria de impactos via `window.getKatanaHits()`.

## 0. Regra permanente "Sempre Video Novo"

- Antes de gerar qualquer novo Short, consulte `historico_videos.json` atraves de `pipeline/historico.py`.
- Nunca repita tema, slug, roteiro ou palavras-chave centrais de um video ja registrado.
- Todo novo video recebe automaticamente a proxima numeracao livre (`output/short_02.mp4`, `output/short_03.mp4`, `output/short_04.mp4`, `output/short_05.mp4`, ...), preservando intactos os videos ja publicados e salvando backup do `player.html` anterior em `arquivo/video_NN/player.html`.

## 1. Personagem flat em capsula e rig articulado de 10 pontos

Padrao visual oficial: **estilo flat limpo em capsula**, com tronco arredondado solido sem contornos pretos pesados, cabeca redonda expressiva com cabelo natural sem costura e gola/capuz aberto sobre os ombros (nunca um anel fechado que lembre "capacete de astronauta"), e olhos grandes que arregalam dramaticamente no choque.

O corpo segue coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros:
1. `cabeca`: centro craniano com inclinacao dinamica (`headTilt`), cabelo recortado e expressao limpa sem bordas pesadas.
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (angulo anatomico coerente com a direcao do olhar).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda limitada para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, baba eletronica, interfone, corrente da porta, volante).
7. `quadril`: pivo central do tronco em capsula e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda.
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`) em planos de corpo inteiro, com sombra de contato visivel.

## 2. Motor V3/V4.1: fundos vibrantes, pulso de tensao, particulas e profundidade de campo

- **Paleta de dopamina visual (zero fundos chapados mortos)**:
  - Fundos base vibrantes: azul-marinho eletrico (`#0A0F1D`) e roxo profundo cinematografico (`#130926`), sempre com gradiente atmosferico e luz volumetrica sutil.
  - **Pulso emocional nos picos de tensao**: transicione e pulse o fundo para **vermelho-alerta (`#3B0A0A`)** nos momentos de perigo, susto e plot twist, ou para **amarelo-eletrico (`#261E0A`)** nos avisos anomalos e chamadas de atencao.
- **Particulas flutuantes continuas no fundo**: mantenha duas camadas de particulas deterministicas (derivadas de `t`, nunca `Math.random()`) flutuando sem interrupcao com paralaxe suave e cor adaptada ao estado emocional (ciano frio, verde visao noturna, chuva noturna, violeta, ambar ou brasa vermelha).
- **Uma cor de destaque fixa no protagonista**: o protagonista veste sempre a mesma cor de destaque bem recortada contra o cenario noturno, garantindo leitura instantanea na tela do celular.
- **Profundidade de campo obrigatoria (Depth of Field otimizado)**: aplique blur no plano de fundo via buffer reduzido (`1/8` resolucao, ex. `135x240`, com `blur` leve equivalente a `blur(8px)` em 1080x1920) sempre que celular, interfone, monitor, notificacao, foto revelada ou close dramatico (`bigFace`) estiver em primeiro plano. Restaure `ctx.filter = 'none'` logo apos. Pre-renderize a vinheta uma unica vez fora do loop e evite granulado tile-by-tile no Canvas (use filtro `noise` no FFmpeg).
- **Rim light coerente com a fonte**: a borda iluminada do personagem acompanha exatamente a luz dominante da cena (tela do celular, interfone CCTV, luz fria da cozinha ou alerta vermelho).
- **Um relogio por vez**: na mudanca de horario, nunca desenhe dois horarios simultaneamente no mesmo quadro (incluindo telas de celular, interfone ou baba eletronica que ja exibem o horario no proprio visor); oculte o relogio durante a janela da CTA visual do meio e durante hits Katana.

## 3. Regra permanente do selo "PARTE 1" (V4 / V4.1)

Todo Short da serie exibe uma badge fixa, discreta e configuravel de continuidade no topo esquerdo:
- **Texto configuravel**: propriedade `parteLabel` (padrao `"PARTE 1"`, aceitando override via `eventos.json` campo `parte_label`, `window.parteLabel` ou query string `?parte=`).
- **Posicao na zona segura superior esquerda**: `x: 64`, `y: 165` em `1080x1920` (longe da margem cortada pelo YouTube Shorts/Reels e sem jamais encostar no relogio central ou no rosto).
- **Estilo obrigatorio**: fundo escuro semitransparente `rgba(10, 15, 29, 0.72)`, borda fina sutil (`1.5px` a `2px` clara semitransparente), cantos arredondados (`12px` a `14px`) e texto em **CAIXA ALTA** com cerca de `26px` (`bold`/`800`), medido dinamicamente para caber com folga interna.
- **Ciclo de visibilidade (V4.1)**: visivel durante toda a historia; oculta-se brevemente apenas durante os `~2,2s` da CTA visual do meio (para evitar poluicao na faixa superior) ou, no modo legado `cta_modo: "final"`, no card final.

## 4. Motor V4/V4.1 estilo Katana: tipografia cinetica de impacto

Nos **3 a 4 picos de choque** da historia (ex.: `"NAO PEDIU"`, `"SUMIU"`, `"ATRAS DELA"`), acione o modulo reutilizavel de tipografia cinetica estilo Katana sincronizado aos timestamps de `audio/eventos.json`:
- **Palavras gigantes ocupando a largura da tela**: texto em CAIXA ALTA ocupando ate ~88% da largura util (`maxW = 920px` em 1080px), sempre ajustado com `measureText` (`drawFittedText`) para nunca estourar a tela independentemente das fontes instaladas no sistema (Windows, macOS ou Linux/Colab). Frases de 2 a 3 palavras podem empilhar em 2 linhas gigantes centradas.
- **Animacao elastica com overshoot e stretch**: entrada ultra-rapida (`0.08s` a `0.12s`) com squash-and-stretch assimetrico (`scaleX` alargado + `scaleY` comprimido no impacto -> overshoot elastico -> assentamento em mola fechada derivada apenas de `t`), leve rotacao angular (`-3deg` a `+3deg`) e rasgo diagonal estilo lamina atras do texto.
- **Flashes curtos de 2 a 4 quadros**: nos primeiros `2 a 4` quadros (`0.067s` a `0.133s` a 30 fps) do hit, alterne flashes secos de alto contraste entre fundo preto (`#05070E`), branco (`#F8FAFC`) e vermelho-alerta (`#E11D2E`), mantendo alto contraste do texto em todos os quadros.
- **Zoom punch-in de camera**: cada hit soma um impulso imediato de zoom (`+0.14` a `+0.22`) e screen shake seco amortecido em `cameraFor(shot, t)`.
- **Determinismo, CPU e higiene visual**: zero `Math.random()`, zero filtros pesados extras por frame; durante a janela ativa do hit Katana (`~0.40s` a `0.50s`), suprima as legendas inferiores e a CTA visual para evitar texto duplicado na tela e exponha `window.getKatanaHits()` para auditoria automatizada.

## 5. Troca de expressao escondida na piscada (2 frames antes da palavra)

- Nunca troque a expressao facial de forma seca com os olhos abertos.
- Toda mudanca de estado emocional (neutro, alivio, cetico, preocupado, medo, choque) dispara uma piscada curta (`~0.16s`, cerca de 5 quadros a 30 fps) iniciada **2 frames (`0.067s`) antes** do timestamp do evento-gatilho em `audio/eventos.json`.
- A troca de sobrancelhas, abertura ocular e tamanho de pupila ocorre exatamente no apice da palpebra fechada.

## 6. Modulo `bigFace` no climax

- No momento de choque ou virada central, corte para o modulo dedicado `bigFace`: close extremo no rosto sobre fundo desfocado (DOF) pulsando em `#3B0A0A`.
- Elementos obrigatorios: olhos grandes bem abertos com pupilas contraidas dentro da esclera branca, gota de suor frio, screen shake de alta frequencia e rim light dramatico coerente com a cena.

## 7. Ritmo V4.1: camera viva, cortes a cada 1,0s a 1,8s e screen shake

- **Zero planos estaticos longos**: garanta mudanca clara de enquadramento, zoom dinamico de camera ou novo elemento visual a cada **1,0s a 1,7s** durante todo o video.
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
  - Palavra-chave ativa destacada em **AMARELO (`#FFD400`)** ou **VERMELHO (`#FF3B30`)** para palavras de alerta, perigo, invasor ou terror.
  - Posicionada no terco inferior (`y: 1495`) acima dos botoes nativos do YouTube Shorts, sem nunca cobrir o rosto, o relogio, o selo `"PARTE 1"` ou a CTA visual do meio (e suprimida durante hits Katana em tela cheia).

## 9. Nova regra V4.1: CTA unica no meio do video e corte seco no final (Loop Imediato)

Para maximizar retencao media e disparos de loop automatico no YouTube Shorts e Reels:
- **Zero CTA no final**: remova completamente a CTA falada e o cartao CTA final nos videos com `cta_modo: "meio"`. O ultimo frame deve cortar seco exatamente no climax/plot twist (sem tela preta final de 0,20s e sem despedida).
- **CTA visual unica no meio (~48% a 56% da duracao, ~2,2s de permanencia)**:
  - Coordenadas e tempos sincronizados por `cta_meio_inicio` e `cta_meio_fim` em `audio/eventos.json` e `audio/timestamps.json` (com `cta_modo: "meio"` e `cta_texto: "COMENTE EU QUERO"` validados obrigatoriamente por `pipeline/historico.py`).
  - **Posicao segura**: zona superior-central (`x: 540`, faixa `y: 150..295` em `1080x1920`), longe do rosto do personagem e completamente separada das legendas inferiores (`y: 1495`).
  - **Estilo e blindagem**: banner/pilula de altissimo contraste (amarelo `#FFD400` e preto `#090B12`, borda nitida, entrada rapida com micro-glitch/pop elastico e saida limpa) contendo o texto `"QUER FAZER NO AUTOMATICO? COMENTE EU QUERO"`, sempre ajustado com `drawFittedText` e margem interna generosa para nunca estourar bordas em Linux/Colab.
  - **Higiene visual**: durante esses `~2,2s`, oculte o relogio do topo e, se ocupar a faixa lateral esquerda, oculte brevemente o selo `"PARTE 1"`; nunca sobreponha um hit Katana.
  - Exponha `window.getMidCta()` retornando `{ modo, inicio, fim, texto }` para auditoria automatizada.

## 10. Checklist visual obrigatorio de 5 etapas

Antes de aprovar qualquer player ou render, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Selo PARTE 1 + CTA unica no meio + encerramento seco**: selo `"PARTE 1"` nitido em `(64, 165)` durante a historia; CTA visual do meio (`"QUER FAZER NO AUTOMATICO? COMENTE EU QUERO"`) sem estourar bordas nem tampar rosto/legendas; final seco no climax sem card CTA final e sem tela preta.
2. **Enquadramento e anatomia limpos**: em corpo inteiro, pes firmes no chao com sombra de contato; apenas um horario visivel por quadro; proporcoes limpas sem efeito "capacete de astronauta".
3. **Ritmo V4.1 e hits Katana medidos**: `window.getShots()` confirma cortes entre `1,0s` e `1,7s`; `window.getKatanaHits()` confirma 3 a 4 impactos com flashes curtos, stretch elastico e punch-in sem vazar a largura da tela.
4. **Profundidade de campo e legendas pop-in**: fundo desfocado (DOF rapido) nos closes/telas e legendas em MAIUSCULAS com pop-in e destaque em `#FFD400` ou `#FF3B30`.
5. **Determinismo e integridade do twist**: chamar `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, com zero erros de console, preservando o plot twist e o corte seco de loop.
