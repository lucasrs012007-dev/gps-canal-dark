---
name: audio-sound-design-suspense
description: "Regras obrigatorias V5.1 de voz atuada por blocos [VOZ:perfil], motor principal Gemini 2.5 TTS com fallback ElevenLabs e edge-tts multi-bloco expressivo, processamento de audio diegetico por cena (interfone, cabine, sussurro seco e CTA comercial), SFX sincronizados por eventos.json e masterizacao final em -14 LUFS com ducking. Use sempre que gerar ou revisar audio de um Short."
---

# Audio e Sound Design para Shorts de Suspense (V5.1)

Skill permanente para construcao de narracao atuada por blocos, processamento de audio diegetico por cena, sincronia matematica de eventos/legendas e masterizacao cinematografica para YouTube Shorts de micro-suspense.

## 0. Regra permanente "Sempre Video Novo" e seguranca de chaves

- Leia o roteiro ativo automaticamente de `historico_videos.json` via `pipeline/historico.py` (impedindo repeticao de temas e mantendo o video atual alinhado ao numero de saida).
- **Zero vazamento de credenciais**: nunca grave `GEMINI_API_KEY` ou `ELEVENLABS_API_KEY` em arquivos `.py`, `.html`, `.json`, `.md` ou `.ipynb` rastreados pelo Git.
- Carregue automaticamente o arquivo `.env` local (listado no `.gitignore`) quando as chaves nao estiverem no ambiente, e no Google Colab tente ler dos Secrets (`google.colab.userdata`) caso os campos `#@param` estejam vazios.

## 1. Tags de atuacao vocal `[VOZ:perfil]` e `voz_blocos` (V5.1)

- Envolva trechos de narracao no roteiro com `[VOZ:perfil] ... [/VOZ]` (suportando multiplos perfis na mesma linha, ex.: narrador introduzindo a fala do porteiro e troca imediata para o personagem no interfone).
- Todas as tags `[VOZ:...]` e `[/VOZ]` devem ser removidas da fala enviada ao TTS, do `audio/narracao.txt` e das legendas, mas seus intervalos exatos (`inicio`, `fim`, `duracao`, `perfil`, `texto`) sao gravados em `voz_blocos` dentro de `audio/eventos.json` e `audio/timestamps.json`.
- **Perfis canonicos V5.1**:
  - `narrador_tenso`: voz grave, pausada, clima de suspense psicologico intimo.
  - `panico`: ritmo acelerado, respiracao curta, senso de urgencia.
  - `interfone_porteiro`: voz assustada, tremula e apressada de outro personagem falando pelo interfone.
  - `cta_comercial`: voz limpa, firme, direta e energica na pausa de tela cheia (`[CTA_PAUSA]`).
  - `sussurro_twist`: voz bem baixa, seca, proxima do microfone e lenta no golpe final.

## 2. Prosodia conversacional, ritmo e nunca narrar onomatopeias

- Sintetize a narracao **frase por frase** (nunca um bloco corrido unico sujeito a pausas aleatorias do TTS).
- Em cada frase gerada, remova silencios mortos nas pontas com `ffmpeg` (`silenceremove` no inicio e no fim) e converta para WAV PCM uniforme (`44100 Hz`, 16-bit, estereo) antes da concatenacao.
- Meca a duracao real de cada frase limpa e monte `audio/voz_limpa.mp3` respeitando pausas exatas:
  - **Pausa rapida dentro de `panico` / `interfone_porteiro`**: `0,12s`.
  - **Pausa padrao entre frases**: `0,16s`.
  - **Pausa dramatica curta nas viradas de tensao/perfil**: `0,24s` a `0,28s` (antes de `sussurro_twist`).
  - **Blocos de acao fisica (`[SFX:nome:duracao]`)**: nunca narrar onomatopeias como `"Toc. Toc."` ou `"Biii!"`; substitua por bloco silencioso cronometrado onde entra o SFX real/HD.
  - **Corte Parte 2 (`[CORTE_PARTE_2]`)**: pausa curta (`0,14s`) com `corte_parte_2` gravado `0,03s` antes da 1a palavra da Parte 2 para abertura imediata da legenda em `0:00`.

## 3. Motor principal Gemini 2.5 TTS + cadeia de fallback blindada (V5.1)

1. **Prioridade 1 (Gemini 2.5 TTS REST)**: `gemini-2.5-flash-preview-tts` via `POST /v1beta/models/{model}:generateContent` com header `x-goog-api-key` (lendo `GEMINI_API_KEY` do ambiente ou `.env`, usando apenas stdlib `urllib` + `wave`/`ffmpeg`, sem SDK pesado).
   - Envie instrucoes explicitas de atuacao em portugues do Brasil inline em `contents[0].parts[0].text` (nunca `systemInstruction`, rejeitado pelos modelos preview TTS) e configure `generationConfig.responseModalities: ["AUDIO"]` + `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName` (voz principal do narrador `Charon` e voz distinta `Fenrir` para `interfone_porteiro`).
   - Decodifique o PCM 24kHz base64 (`audio/L16;codec=pcm;rate=24000`) para WAV valido e normalize para `44100 Hz` estereo.
2. **Prioridade 2 (Fallback ElevenLabs)**: se `GEMINI_API_KEY` estiver ausente ou falhar, use `eleven_multilingual_v2` quando `ELEVENLABS_API_KEY` estiver disponivel, variando `voice_settings` conforme o perfil `[VOZ:perfil]`.
3. **Prioridade 3 (Fallback gratuito `edge-tts` multi-bloco expressivo)**: se ambos falharem ou nao houver chave paga, gere bloco por bloco variando `rate`, `pitch` e voz secundaria (`pt-BR-FabioNeural` para `interfone_porteiro` vs `pt-BR-AntonioNeural` com presets proprios para cada perfil).
4. **Modo automatizado (`--mock`)**: gera sinais tonais com assinatura por perfil para validar parser, `voz_blocos`, audio diegetico, sincronia e fatiamento sem rede.

## 4. Sincronia matematica e grupos de legenda anti-colagem

- **`audio/timestamps.json`**: contem carimbo de integridade (`video_id`, `titulo`, `roteiro_sha256`), `voz_blocos`, `cta_modo`, `cta_meio_inicio`, `cta_meio_fim`, `corte_parte_2`, palavras individuais e `grupos`.
- **Regra anti-colagem de legendas**: cada grupo tem no maximo **3 palavras** e respeita teto de caracteres (`<= 20` para 3 palavras, `<= 22` para 2 palavras), nunca cruzando o fim de frase nem juntando palavras longas que se sobreponham durante o pop-in no Canvas.
- **`audio/eventos.json`**: contem todos os marcos narrativos, `voz_blocos`, `frases`, `cta_meio_inicio`/`cta_meio_fim`, `corte_parte_2` e `duracao_total`.

## 5. Audio diegetico por cena (`audio/sound_design.py`)

Antes da mixagem com drone e SFX, leia `voz_blocos` de `audio/eventos.json` e processe a trilha de voz por trecho (com crossfade de `15ms` nas bordas para zero estalos):
- **`interfone_porteiro`**: filtro passa-banda de interfone (`320 Hz` a `2600 Hz`), leve saturacao analogica e cama discreta de chiado eletrico/estatica aplicada somente durante a fala do porteiro.
- **`narrador_tenso` e `panico`**: reflexoes curtas e sutis de cabine/corredor fechado (cauda filtrada acima de `150 Hz` para manter diccao limpa).
- **`sussurro_twist`**: equalizacao seca e proxima do microfone (reforco leve de graves de proximidade `85-260 Hz` e presenca `2.4-5.4 kHz`, zero reverb) com corte seco do drone ambiente.
- **`cta_comercial`**: voz 100% seca, clara e com leve compressao de anuncio durante a tela cheia da CTA (drone silenciado).

## 6. Cama sonora, SFX hibridos e masterizacao em -14 LUFS

- Carregue SFX reais de `assets/sfx/` quando presentes, com fallback acustico procedural HD automatico.
- Aplique **ducking** (`sidechaincompress` acionado pela faixa de voz diegetica) sobre o drone e os SFX.
- Masterize o mix final em **2 passagens** com `ffmpeg loudnorm` mirando **`-14 LUFS`** (True Peak `-1.5 dBTP`, `LRA=7`) gerando `audio/mix_final.mp3` e copiando para `audio/narracao.mp3`.
- Valide sempre com `pipeline/historico.py validar-audio`, `ffprobe` e medicao `loudnorm`.
