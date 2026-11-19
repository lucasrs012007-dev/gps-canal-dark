---
name: roteiro-retencao-funil-manychat
description: Escreve roteiros de micro-suspense psicologico "E se...?" de alta retencao (35s a 45s, 95 a 115 palavras) no formato exato de roteiro_NN.txt e projeta a CTA de comentarios ("EU QUERO") integrada ao funil de Direct automatico no ManyChat/Instagram. Use quando for criar um novo roteiro de Short ou montar o funil de conversao no Direct.
---

# Roteiros de Alta Retencao ("E se...?") + Funil ManyChat

Skill de copywriting, retencao e conversao pensada especificamente para o formato de Canal Dark em 9:16 do repositorio `gps-canal-dark`.

## 1. Estrutura obrigatoria do roteiro (7 blocos, 35s a 45s)

Antes de escrever, consulte `historico_videos.json` (`python3 pipeline/historico.py verificar`) para respeitar a regra permanente **"Sempre Video Novo"**.

| Bloco | Janela alvo | Objetivo psicologico | Regra tecnica |
|---|---|---|---|
| 1. Gancho | `00s - 03s` | Parar o dedo no 1o segundo com pergunta **"E se...?"** ou anomalia imediata | 10 a 14 palavras; zero saudacao ("Oi galera") e zero introducao |
| 2. Ambientacao | `03s - 07s` | Ancorar lugar brasileiro real, horario e protagonista com 1 cor fixa | Prosodia fluida (virgulas naturais, sem frases picotadas) |
| 3. Anomalia | `07s - 14s` | Primeiro evento impossivel que planta a pista secreta do twist | Evento visual claro em celular, relogio ou objeto |
| 4. Escalada | `14s - 22s` | Dois sinais crescentes que fecham as saidas do protagonista | Mudanca de plano/zoom a cada `1,0s a 1,8s` no visual |
| 5. Climax + SFX | `22s - 31s` | Pico de perigo (`bigFace`) + bloco silencioso `[SFX:nome:duracao]` | **Nunca narrar onomatopeias** ("toc toc", "biii", "vrum") |
| 6. Plot Twist | `31s - 37s` | Pausa dramatica `0.45s` + virada curta que reinterpreta a historia | Corte seco do drone no `plot_twist` |
| 7. CTA Final | `ultimos ~3,5s` | Converter retencao em comentario com palavra-chave de Direct | Frase exata validada: `"Quer aprender a fazer videos assim no automatico? Comente EU QUERO."` |

## 2. Contrato tecnico de `roteiro_NN.txt`

- Extensao total: **95 a 115 palavras faladas** (garante 35s a 45s reais na ElevenLabs `eleven_multilingual_v2`).
- Cada linha de producao segue exatamente 4 colunas:
  `[NN - NN] | Texto exato da narracao | Direcao visual e relogio | eventos, evento@palavra, pausa=0.45`
- Blocos de acao sonora pura usam `[SFX:nome_evento:duracao_s]` na coluna 2.
- Zero emojis e zero travessoes (`em-dash`/`en-dash`) no arquivo.

## 3. Funil de Conversao: Comentario -> Direct Automatico (ManyChat / Instagram)

Conecte a CTA dos ultimos 3,5 segundos diretamente a uma automacao de comentarios no ManyChat (ou API oficial do Instagram Messaging):

1. **Gatilho de comentario**:
   - Palavra-chave principal: `EU QUERO` (incluir variacoes sem acento/caixa: `eu quero`, `quero`, `QUERO`).
   - Aplicado a Reels/Posts especificos da serie ou a todos os Reels do canal.
2. **Resposta publica no comentario (anti-spam + boost de algoritmo)**:
   - Configure 3 a 5 variacoes curtas e naturais com atraso aleatorio de 20s a 90s (evita bloqueio da Meta):
     - `"Te mandei no Direct agora!"`
     - `"Acabei de enviar no seu Direct, da uma olhada la."`
     - `"Pronto! Enviei o passo a passo no seu Direct."`
3. **Fluxo de Direct em 2 toques (aumenta taxa de abertura e evita filtro de spam)**:
   - **Mensagem 1 (Opt-in rapido com botao)**:
     - Texto: `"Vi que voce comentou EU QUERO no video [Titulo]. Quer receber o link do passo a passo para gerar esses Shorts no automatico?"`
     - Botao: `"Sim, me envia!"`
   - **Mensagem 2 (Apos o clique no botao)**:
     - Entrega o link da aula, comunidade, ferramenta ou isca digital + tag `interessado_shorts_auto` no CRM do ManyChat.
   - **Follow-up unico (23h depois, dentro da janela oficial de 24h da Meta, apenas para quem nao clicou)**:
     - Lembrete leve e unico sem insistencia.

## 4. Checklist de revisao antes de gravar audio

- [ ] Tema validado como inedito contra `historico_videos.json`.
- [ ] Contagem entre 95 e 115 palavras faladas, zero onomatopeias narradas.
- [ ] Pista do plot twist plantada antes dos 15 segundos e recompensada sem furo logico.
- [ ] CTA ocupa os ultimos ~3,5s com a palavra-chave exata configurada no gatilho do ManyChat.
- [ ] Legenda da publicacao (descricao do Reels/Shorts) reforca na 1a linha a palavra-chave `"Comente EU QUERO"`.
