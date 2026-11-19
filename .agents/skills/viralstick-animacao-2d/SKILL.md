---
name: viralstick-animacao-2d
description: "Regras obrigatorias V3 (Dopamina Visual) para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920): rig articulado de 10 pontos flat em capsula, Depth of Field blur(8px), fundos vibrantes pulsando na tensao, particulas continuas, cortes dinamicos a cada 1,0s a 1,8s, screen shake nos impactos, legendas pop-in em amarelo/vermelho, regra Sempre Video Novo e checklist visual de 5 etapas. Use sempre que construir ou revisar o player Canvas de um Short animado por codigo."
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16) - Motor V3

Skill permanente de direcao de arte, rigging, dopamina visual e camera para YouTube Shorts verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)` e verificacao de plano via `window.getShots()`.

## 0. Regra permanente "Sempre Video Novo"

- Antes de gerar qualquer novo Short, consulte `historico_videos.json` atraves de `pipeline/historico.py`.
- Nunca repita tema, slug, roteiro ou palavras-chave centrais de um video ja registrado.
- Todo novo video recebe automaticamente a proxima numeracao livre (`output/short_02.mp4`, `output/short_03.mp4`, ...), preservando intactos os videos ja publicados.

## 1. Personagem flat em capsula e rig articulado de 10 pontos

Padrao visual oficial: **estilo flat limpo em capsula**, com tronco arredondado solido sem contornos pretos pesados, cabeca redonda expressiva com cabelo natural sem costura e gola/capuz aberto sobre os ombros (nunca um anel fechado que lembre "capacete de astronauta"), e olhos grandes que arregalam dramaticamente no choque.

O corpo segue coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros:
1. `cabeca`: centro craniano com inclinacao dinamica (`headTilt`), cabelo recortado e expressao limpa sem bordas pesadas.
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (angulo anatomico coerente com a direcao do olhar).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda limitada para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, volante, macaneta, porta).
7. `quadril`: pivo central do tronco em capsula e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda.
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`) em planos de corpo inteiro, com sombra de contato visivel.

## 2. Motor V3: fundos vibrantes, pulso de tensao, particulas e profundidade de campo

- **Paleta V3 de dopamina visual (zero fundos chapados mortos)**:
  - Fundos base vibrantes: azul-marinho eletrico (`#0A0F1D`) e roxo profundo cinematografico (`#130926`), sempre com gradiente atmosferico e luz volumetrica sutil.
  - **Pulso emocional nos picos de tensao**: transicione e pulse o fundo para **vermelho-alerta (`#3B0A0A`)** nos momentos de perigo, susto e plot twist, ou para **amarelo-eletrico (`#261E0A`)** nos avisos anomalos e chamadas de atencao.
- **Particulas flutuantes continuas no fundo**: mantenha duas camadas de particulas deterministicas (derivadas de `t`, nunca `Math.random()`) flutuando sem interrupcao com paralaxe suave e cor adaptada ao estado emocional (ciano frio, violeta, ambar ou brasa vermelha).
- **Uma cor de destaque fixa no protagonista**: o protagonista veste sempre a mesma cor de destaque bem recortada contra o cenario noturno, garantindo leitura instantanea na tela do celular.
- **Profundidade de campo obrigatoria (Depth of Field)**: aplique `ctx.filter = 'blur(8px)'` no plano de fundo (preferencialmente via canvas auxiliar para manter alta velocidade no render) sempre que celular, notificacao, retrovisor, foto revelada, CTA ou close dramatico (`bigFace`) estiver em primeiro plano. Restaure `ctx.filter = 'none'` logo apos.
- **Rim light coerente com a fonte**: a borda iluminada do personagem acompanha exatamente a luz dominante da cena (painel/celular frio, farol ambar ou alerta vermelho).
- **Um relogio por vez**: na mudanca de horario, nunca desenhe dois horarios simultaneamente no mesmo quadro; oculte o relogio durante a tela final de CTA.

## 3. Troca de expressao escondida na piscada (2 frames antes da palavra)

- Nunca troque a expressao facial de forma seca com os olhos abertos.
- Toda mudanca de estado emocional (neutro, cetico, preocupado, medo, choque) dispara uma piscada curta (`~0.16s`, cerca de 5 quadros a 30 fps) iniciada **2 frames (`0.067s`) antes** do timestamp do evento-gatilho em `audio/eventos.json`.
- A troca de sobrancelhas, abertura ocular e tamanho de pupila ocorre exatamente no apice da palpebra fechada.

## 4. Modulo `bigFace` no climax

- No momento de choque ou virada central, corte para o modulo dedicado `bigFace`: close extremo no rosto sobre fundo desfocado (`blur(8px)`) pulsando em `#3B0A0A`.
- Elementos obrigatorios: olhos grandes bem abertos com pupilas contraidas dentro da esclera branca, gota de suor frio, screen shake de alta frequencia e rim light dramatico coerente com a cena.

## 5. Ritmo V3: camera viva, cortes a cada 1,0s a 1,8s e screen shake

- **Zero planos estaticos longos**: garanta mudanca clara de enquadramento, zoom dinamico de camera ou novo elemento visual a cada **1,0s a 1,8s** durante todo o video.
- Exponha `window.getShots()` retornando a lista de planos com inicio, fim e duracao para auditoria automatizada (nenhum shot pode exceder `1,85s`).
- Combine movimento continuo (zoom dinamico, pan suave, punch-in/punch-out e handheld deterministico via `noise(t)`) com **screen shake amortecido** em todo impacto fisico ou sonoro (alerta repentino, freada, passagem de caminhao, batida ou revelacao do plot twist).

## 6. Legendas V3 com animacao pop-in (2 a 3 palavras, MAIUSCULAS, amarelo e vermelho)

- Leia os blocos ja segmentados de `audio/timestamps.json` (`grupos`), com **2 a 3 palavras por bloco**, nunca misturando o fim de uma frase com o inicio da seguinte.
- **Animacao pop-in obrigatoria**:
  - Cada bloco de legenda entra com curva elastica curta (`scale 0.68 -> 1.10 -> 1.00` nos primeiros `0,11s`).
  - A palavra ativa recebe micro-pop de enfase (`1.00 -> 1.12 -> 1.07`) ao ser pronunciada.
- **Estilo visual obrigatorio**:
  - Texto em **CAIXA ALTA (MAIUSCULAS)**, fonte grossa condensada.
  - Preenchimento branco (`#FFFFFF`) com **contorno preto espesso** (`strokeText` arredondado) e sombra suave.
  - Palavra-chave ativa destacada em **AMARELO (`#FFD400`)** ou **VERMELHO (`#FF3B30`)** para palavras de alerta, perigo, acidente ou terror.
  - Posicionada no terco inferior acima dos botoes nativos do YouTube Shorts, sem nunca cobrir o rosto, o relogio ou o botao visual da CTA final.

## 7. Bloco final de CTA (ultimos ~3,5s)

- Apos o plot twist, reserve os ultimos ~3,5 segundos para a CTA de engajamento (ex.: `"Quer aprender a fazer videos assim no automatico? Comente EU QUERO."`).
- O cartao visual da CTA deve manter o ritmo V3 (troca de elemento/enquadramento a cada 1,0s a 1,8s), exibir uma pilula amarela `#FFD400` com entrada pop-in e nunca sobrepor as legendas do terco inferior.

## 8. Checklist visual obrigatorio de 5 etapas

Antes de aprovar qualquer player ou render, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Zero sobreposicao critica**: relogio (apenas um horario visivel por vez), notificacoes, cartao CTA e legendas nunca cobrem o rosto ou se atropelam entre si.
2. **Enquadramento e anatomia limpos**: em corpo inteiro, pes firmes no chao com sombra de contato; em planos internos (ex.: carro), proporcoes limpas, maos coerentes e sem efeito "capacete de astronauta".
3. **Ritmo V3 medido**: `window.getShots()` confirma cortes/variacoes entre `1,0s` e `1,8s`, com fundos vibrantes pulsando na tensao, particulas continuas e screen shake nos impactos.
4. **Profundidade de campo e legendas pop-in**: fundo desfocado (`blur(8px)`) nos closes/celulares e legendas em MAIUSCULAS com pop-in e destaque em `#FFD400` ou `#FF3B30`.
5. **Determinismo e integridade do twist + CTA**: chamar `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, com zero erros de console, preservando o plot twist e a CTA final.
