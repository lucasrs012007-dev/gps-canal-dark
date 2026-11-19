---
name: viralstick-animacao-2d
description: Regras obrigatorias para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920): rig articulado de 10 pontos, silhueta com rim light, troca de expressao escondida na piscada, modulo bigFace, ritmo de cortes de camera, legendas de 2 a 3 palavras e checklist visual de 5 etapas. Use sempre que construir ou revisar o player Canvas de um Short animado por codigo.
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16)

Skill permanente de direcao de arte, rigging e camera para YouTube Shorts verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)`.

## 1. Personagem flat em capsula e rig articulado de 10 pontos

Padrao visual oficial: **estilo flat limpo em capsula**, com tronco arredondado solido sem contornos pretos pesados, cabeca redonda expressiva com cabelo natural e capuz aberto sobre os ombros (nunca um anel fechado que lembre "capacete de astronauta"), e olhos grandes que arregalam dramaticamente no choque.

O corpo segue coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros:
1. `cabeca`: centro craniano com inclinacao dinamica (`headTilt`), cabelo recortado e expressao limpa sem bordas pesadas.
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (angulo anatomico coerente com a direcao do olhar).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda limitada para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, macaneta, batida na porta).
7. `quadril`: pivo central do tronco em capsula e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda.
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`), com sombra de contato sob os calcanhares.

## 2. Silhueta limpa, iluminacao, profundidade de campo (Depth of Field) e atmosfera

- **Uma cor de destaque fixa**: o protagonista veste sempre a mesma cor de destaque (ex.: moletom laranja flat bem recortado) contra cenarios frios e escuros, garantindo leitura instantanea em tela de celular.
- **Profundidade de campo obrigatoria (Depth of Field)**: aplique `ctx.filter = 'blur(8px)'` no plano de fundo sempre que um celular, notificacao, chat, foto revelada ou close dramatico (`bigFace`) estiver em primeiro plano. Restaure `ctx.filter = 'none'` imediatamente apos desenhar o fundo desfocado.
- **Rim light coerente com a fonte**: cada cena tem uma fonte dominante (azul frio de tela de celular, ambar quente piscando no corredor ou apagao total). A borda iluminada do personagem acompanha exatamente essa fonte.
- **Um relogio por vez**: na mudanca de horario (`19:00`, `21:00`, `00:00`, `03:00`, `03:01`), nunca desenhe dois horarios simultaneamente no mesmo quadro; use transicao limpa de saida e entrada sem sobreposicao.
- **Atmosfera em movimento continuo**: particulas de poeira flutuando, leve oscilacao de lampada, vinheta dinamica, brilho suave do celular e grao de filme deterministico (derivado de `t`, nunca `Math.random()`).

## 3. Troca de expressao escondida na piscada (2 frames antes da palavra)

- Nunca troque a expressao facial de forma seca com os olhos abertos.
- Toda mudanca de estado emocional (neutro, sorriso cetico, preocupado, medo, choque) dispara uma piscada curta (`~0.16s`, cerca de 5 quadros a 30 fps) iniciada **2 frames (`0.067s`) antes** do timestamp da palavra-gatilho em `audio/eventos.json` ou `audio/timestamps.json`.
- A troca de sobrancelhas, abertura ocular e tamanho de pupila ocorre exatamente no apice da palpebra fechada, tornando a transicao organica.

## 4. Modulo `bigFace` no climax

- No momento de choque ou revelacao central (marco `big_face` em `audio/eventos.json`), corte para um modulo dedicado `bigFace`: close extremo no rosto sobre fundo desfocado (`blur(8px)`).
- Elementos obrigatorios do `bigFace`: olhos grandes bem abertos com pupilas contraidas dentro da esclera branca, gota de suor frio, micro-tremor de camera de alta frequencia e rim light azul intenso vindo da tela do celular.

## 5. Camera sempre viva e cortes a cada 1,5s a 2,5s

- Nenhum plano pode ficar estatico por mais de `2,5s` (nunca deixar o boneco parado 8s+ no mesmo enquadramento).
- Garanta mudanca clara de plano, enquadramento ou elemento grafico a cada `1,5s` a `2,5s` (mapa com ondas, close celular URGENTE, reacao do personagem, fachada/porta, chat desfocado, apagao nas janelas, close na macaneta, batidas com shake, foto revelada, `bigFace`, recuo revelador) sincronizada a `audio/eventos.json`.
- Combine sempre movimento continuo: zoom lento, pan suave, handheld sutil (`noise(t)` deterministico) e camera shake amortecido nos impactos fisicos.

## 6. Legendas de retencao (2 a 3 palavras, MAIUSCULAS, amarelo e vermelho)

- Leia os blocos ja segmentados de `audio/timestamps.json` (`grupos`), com **2 a 3 palavras por bloco**, nunca misturando o fim de uma frase com o inicio da seguinte.
- **Estilo visual obrigatorio**:
  - Texto em **CAIXA ALTA (MAIUSCULAS)**, fonte grossa condensada.
  - Preenchimento branco (`#FFFFFF`) com **contorno preto espesso** (`strokeText` arredondado) e sombra suave para leitura perfeita sobre qualquer fundo.
  - Palavra-chave ativa destacada em **AMARELO (`#FFD400`)** ou **VERMELHO (`#FF3B30`)** para palavras de alerta, perigo ou terror.
  - Posicionada no terco inferior acima dos botoes nativos do YouTube Shorts, longe do rosto e do relogio, com ajuste automatico de tamanho para nunca cortar nas bordas de `1080px`.

## 7. Checklist visual obrigatorio de 5 etapas

Antes de considerar qualquer player ou render aprovado, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Zero sobreposicao critica**: relogio (apenas um horario visivel por vez), notificacoes e legendas nunca cobrem o rosto ou os olhos de nenhum personagem.
2. **Pes firmes no chao**: em todo plano de corpo inteiro, os pes tocam exatamente a linha do piso com sombra de contato visivel (sem flutuar nem afundar).
3. **Rosto flat limpo e legivel**: sem efeito "capacete de astronauta"; maos, bracos ou objetos nunca atravessam o rosto; olhos expressivos legiveis em tela de celular.
4. **Ritmo e profundidade de campo**: mudanca visual clara a cada `1,5s` a `2,5s`, fundo desfocado (`blur(8px)`) nos closes/celulares e legendas em MAIUSCULAS sem misturar frases.
5. **Determinismo e integridade do twist**: chamar `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, com zero erros de console, e a revelacao final preserva todas as pistas do roteiro.
