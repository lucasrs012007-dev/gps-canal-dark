---
name: viralstick-animacao-2d
description: Regras obrigatorias para animacao 2D minimalista de suspense em HTML5 Canvas 9:16 (1080x1920): rig articulado de 10 pontos, silhueta com rim light, troca de expressao escondida na piscada, modulo bigFace, ritmo de cortes de camera, legendas de 2 a 3 palavras e checklist visual de 5 etapas. Use sempre que construir ou revisar o player Canvas de um Short animado por codigo.
---

# ViralStick Animacao 2D em HTML5 Canvas (9:16)

Skill permanente de direcao de arte, rigging e camera para YouTube Shorts verticais (`1080x1920`, `30 fps`) animados 100% por codigo em HTML5 Canvas 2D, com funcao deterministica `window.renderAt(t)`.

## 1. Rig articulado de 10 pontos (nunca boneco rigido ou "capacete")

Todo personagem principal deve ser desenhado por coordenadas articuladas com cinematica inversa (IK) de 2 segmentos nos membros. Proibido usar torso cilindro estatico ou contorno circular fechado que lembre capacete de astronauta.

Os 10 pontos obrigatorios do rig:
1. `cabeca`: centro craniano com leve inclinacao dinamica (`headTilt`), queixo/mandibula definidos e cabelo ou capuz integrado ao pescoco (nunca um anel fechado em volta do rosto).
2. `pescoco_ombros`: linha de ombros inclinavel com respiracao continua (`sin` deterministico em funcao de `t`) e encolhimento de tensao/ombros.
3. `cotovelo_esq`: articulacao IK do braco esquerdo (com angulo anatomico coerente com o lado para onde o personagem olha).
4. `cotovelo_dir`: articulacao IK do braco direito.
5. `mao_esq`: extremidade esquerda com limite de altura para nunca atravessar a cabeca nem o rosto.
6. `mao_dir`: extremidade direita com encaixe firme para objetos (celular, macaneta, batida na porta).
7. `quadril`: pivo central do tronco e das pernas, permitindo leve mudanca de peso.
8. `joelho_esq`: articulacao IK da perna esquerda (flexao natural ao caminhar, parar ou agachar).
9. `joelho_dir`: articulacao IK da perna direita.
10. `pes`: apoio esquerdo e direito sempre travados no plano do chao (`gy`), com sombra de contato sob os calcanhares.

## 2. Silhueta limpa, iluminacao e atmosfera viva

- **Uma cor de destaque fixa**: o protagonista veste sempre a mesma cor de destaque (ex.: moletom ambar/mostarda) contra cenarios frios e escuros, garantindo leitura instantanea em tela de celular.
- **Rim light coerente com a fonte**: cada cena tem uma fonte dominante (azul frio de tela de celular, ambar quente piscando no corredor ou apagao total). A borda iluminada do personagem e dos objetos acompanha exatamente a direcao dessa fonte.
- **Atmosfera em movimento continuo**: particulas de poeira flutuando, leve oscilacao de lampada, vinheta dinamica, brilho suave do celular e grao de filme deterministico (derivado de `t`, nunca `Math.random()`).

## 3. Troca de expressao escondida na piscada (2 frames antes da palavra)

- Nunca troque a expressao facial de forma seca com os olhos abertos.
- Toda mudanca de estado emocional (neutro, cetico, preocupado, medo, choque) dispara uma piscada curta (`~0.16s`, cerca de 5 quadros a 30 fps) iniciada **2 frames (`0.067s`) antes** do timestamp da palavra-gatilho em `audio/eventos.json` ou `audio/timestamps.json`.
- A troca de sobrancelhas, abertura ocular e tamanho de pupila ocorre exatamente no apice da palpebra fechada, tornando a transicao organica.

## 4. Modulo `bigFace` no climax

- No momento de choque ou revelacao central (marco `big_face` em `audio/eventos.json`), corte para um modulo dedicado `bigFace`: close extremo no rosto ocupando grande parte da largura do quadro.
- Elementos obrigatorios do `bigFace`: pupilas contraidas dentro da esclera branca, gota de suor ou tensao de sobrancelha, micro-tremor de camera de alta frequencia, rim light intenso vindo da fonte da revelacao (ex.: tela do celular) e ausencia de elementos distrativos no fundo.

## 5. Camera sempre viva e cortes a cada 1,5s a 2,0s

- Nenhum plano pode ficar congelado ou sem variacao visual por mais de `2,0s`.
- Alterne planos a cada `1,5s` a `2,0s` (plano geral, medio, detalhe de tela/mao, contraplano, `bigFace`, recuo revelador) sincronizados aos marcos de `audio/eventos.json`.
- Combine sempre pelo menos um movimento continuo: zoom lento (push-in ou pull-out), pan suave, handheld sutil (`noise(t)` deterministico) e camera shake amortecido nos impactos fisicos (batidas na porta, susto, apagao).

## 6. Legendas cinematograficas de 2 a 3 palavras

- Leia os blocos ja segmentados de `audio/timestamps.json` (`grupos`), com no maximo **2 a 3 palavras por bloco**.
- **Regra absoluta de fronteira**: nunca misture o fim de uma frase com o inicio da frase seguinte no mesmo bloco de legenda.
- Posicione as legendas na zona segura inferior do YouTube Shorts (acima dos controles de interface do app, longe do rosto e do relogio), com destaque de cor na palavra ativa e limite de largura para nunca cortar nas bordas de `1080px`.

## 7. Checklist visual obrigatorio de 5 etapas

Antes de considerar qualquer player ou render aprovado, execute `window.renderAt(t)` nos principais timestamps em navegador headless e verifique visualmente:

1. **Zero sobreposicao critica**: relogio, notificacoes e legendas nunca cobrem o rosto ou os olhos de nenhum personagem.
2. **Pes firmes no chao**: em todo plano de corpo inteiro, os pes tocam exatamente a linha do piso com sombra de contato visivel (sem flutuar nem afundar).
3. **Rosto e silhueta legiveis**: maos, bracos, capuz ou objetos nunca atravessam o rosto; a expressao continua legivel mesmo reduzida ao tamanho de celular.
4. **Ritmo sem segundos mortos**: ha corte, novo plano ou acao visual clara a cada `1,5s` a `2,0s`, e as legendas nunca cruzam fronteiras de frase.
5. **Determinismo e integridade do twist**: chamar `window.renderAt(t)` fora de ordem produz exatamente os mesmos pixels, com zero erros de console, e a revelacao final preserva todas as pistas do roteiro.
