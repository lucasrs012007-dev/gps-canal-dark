---
name: audio-sound-design-suspense
description: "Regras obrigatorias V5.2 de voz atuada por blocos [VOZ:perfil] (incluindo voz_telefone), Ritmo 2x (silenceremove interno max 0.09s + atempo=1.14), agrupamento de blocos no Gemini 2.5 TTS com cadencia anti-429, trava de consistencia vocal (zero mistura de provedores), retry blindado do edge-tts contra NoAudioReceived + fallback de emergencia gTTS, audio diegetico por cena e masterizacao final em -14 LUFS."
---

# Audio e Sound Design para Shorts de Suspense (V5.2)

Skill permanente para construcao de narracao atuada por blocos em ritmo agil, processamento de audio diegetico por cena, sincronia matematica de eventos/legendas e masterizacao cinematografica para YouTube Shorts de micro-suspense.

## 0. Regra de Evolucao Continua, "Sempre Video Novo" e seguranca de chaves

- **Regra de Evolucao Continua**: nunca retrabalhar um video ja pronto; todo upgrade estreia criando o proximo video inedito (`id + 1` em `historico_videos.json`) e salvando backup do `player.html` anterior em `arquivo/video_NN/player.html`.
- Leia o roteiro ativo automaticamente de `historico_videos.json` via `pipeline/historico.py` (impedindo repeticao de temas e mantendo o video atual alinhado ao numero de saida).
- **Zero vazamento de credenciais**: nunca grave `GEMINI_API_KEY` ou `ELEVENLABS_API_KEY` em arquivos `.py`, `.html`, `.json`, `.md` ou `.ipynb` rastreados pelo Git, nem imprima valores de chaves nos logs.
- Carregue automaticamente o arquivo `.env` local (listado no `.gitignore`) quando as chaves nao estiverem no ambiente, e no GitHub Actions injete `GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}` explicitamente no `env` do job e nas estacoes de roteiro e audio.

## 1. Tags de atuacao vocal `[VOZ:perfil]` e `voz_blocos` (V5.2)

- Envolva trechos de narracao no roteiro com `[VOZ:perfil] ... [/VOZ]`.
- Todas as tags `[VOZ:...]`, `[/VOZ]`, `[SFX:...]`, `[CTA_PAUSA]` e `[CORTE_PARTE_2]` devem ser removidas da fala enviada ao TTS, do `audio/narracao.txt` e das legendas, mas seus intervalos exatos (`inicio`, `fim`, `duracao`, `perfil`, `texto`) sao gravados em `voz_blocos` dentro de `audio/eventos.json` e `audio/timestamps.json`.
- **Perfis canonicos V5.2**:
  - `narrador_tenso`: voz grave, firme, ritmo agil e urgente de suspense psicologico (sem arrastar silabas).
  - `panico`: ritmo bem acelerado, respiracao curta, senso imediato de perigo e diccao nitida.
  - `interfone_porteiro`: voz assustada, tremula e apressada de outro personagem falando pelo interfone (`Fenrir` no Gemini TTS).
  - `voz_telefone`: voz urgente e tensa de outro personagem falando em ligacao telefonica (`Fenrir` no Gemini TTS, com filtro passa-banda telefonico em `audio/sound_design.py`).
  - `cta_comercial`: voz limpa, firme, direta e energica na pausa de tela cheia (`[CTA_PAUSA]`).
  - `sussurro_twist`: voz baixa, seca, proxima do microfone, tensa e precisa (sem lentidao excessiva) no golpe final.

## 2. Regra de Ritmo 2x (Zero Voz Lenta) e pausas enxutas

- **Nunca entregar voz lenta**: todas as instrucoes de atuacao do Gemini 2.5 TTS exigem diccao nitida e ritmo agil/urgente, sem arrastar silabas.
- **Corte de silencios mortos + `atempo=1.14` (`VELOCIDADE_VOZ`)**:
  - Aplique em cada bloco sintetizado o filtro FFmpeg com corte nas pontas, compressao de silencios mortos internos (`silenceremove` com `stop_duration=0.09` max) e aceleracao `atempo=1.14` (padrao configuravel por `VELOCIDADE_VOZ`, preservando o timbre grave) antes de normalizar para PCM `44100 Hz` 16-bit estereo.
- **Pausas dramaticas curtas (`0.10s` a `0.18s`)**:
  - Dentro de `panico` / `voz_telefone` / `interfone_porteiro`: `0.10s`.
  - Entre frases padrao: `0.12s`.
  - Nas viradas de perfil vocal: `0.15s`.
  - Antes do `sussurro_twist` / pausa dramatica curta: `0.18s`.
  - Blocos `[SFX:nome:duracao]` nunca sao narrados: viram janelas de silencio cronometradas onde entram os SFX reais/HD.
  - `[CORTE_PARTE_2]`: janela curta (`0.14s`) com `corte_parte_2` gravado `0.03s` antes da 1a palavra da Parte 2 para abertura imediata da legenda em `0:00`.

## 3. Blindagem Gemini 2.5 TTS, Consistencia Vocal e Cadeia de 4 Niveis (V5.2)

1. **Agrupamento de blocos do mesmo perfil**: agrupe falas consecutivas com o mesmo `perfil` (sem `[SFX:...]`, `[CTA_PAUSA]` ou `[CORTE_PARTE_2]` no meio) numa unica chamada de API ao Gemini TTS, reduzindo requisicoes e melhorando a naturalidade.
2. **Cadencia e retries anti-429/503**:
   - Respeite intervalo minimo entre chamadas (`GEMINI_TTS_MIN_INTERVAL_S`, padrao `21.0s`).
   - Execute ate 4 retries em HTTP 429/503 com esperas escalonadas (`22s`, `35s`, `50s`, `65s`), respeitando o header `Retry-After` quando presente.
   - Registre em log se `GEMINI_API_KEY` foi detectada no ambiente/`.env` e qual codigo HTTP falhou (sem jamais imprimir o valor da chave).
3. **Trava de Consistencia Vocal (Zero Mistura de Provedores)**:
   - E estritamente proibido misturar dois provedores de voz no mesmo video.
   - Se qualquer bloco falhar definitivamente no provedor atual, descarte todos os blocos ja gerados e reinicie do bloco 1 no proximo nivel da cadeia:
     - Nivel 1: Gemini 2.5 TTS REST (`gemini-2.5-flash-preview-tts`, `Charon` narrador / `Fenrir` telefone e interfone).
     - Nivel 2: ElevenLabs (`eleven_multilingual_v2`, quando `ELEVENLABS_API_KEY` estiver configurada).
     - Nivel 3: `edge-tts` com texto sanitizado (nunca enviar texto vazio ou so pontuacao), taxas rapidas validas (`+14%` a `+22%`) e retry escalonado contra `NoAudioReceived`: tentativa 1 (`voice` + `rate` + `pitch`), tentativa 2 (`pt-BR-AntonioNeural` + `rate` sem `pitch`), tentativa 3 (`pt-BR-AntonioNeural` puro sem `rate` nem `pitch`).
     - Nivel 4 (emergencia): `gTTS` (`lang="pt"`, `tld="com.br"`) + aceleracao FFmpeg `atempo`.
   - Grave `provedor_voz` e `blocos_api_chamadas` em `audio/eventos.json` e `audio/timestamps.json`.

## 4. Sincronia matematica e grupos de legenda anti-colagem

- **`audio/timestamps.json`** e **`audio/eventos.json`**: contem carimbo de integridade (`video_id`, `titulo`, `roteiro_sha256`), `provedor_voz`, `blocos_api_chamadas`, `voz_blocos`, `cta_modo`, `cta_meio_inicio`, `cta_meio_fim`, `corte_parte_2` e `duracao_total`.
- **Regra anti-colagem de legendas**: cada grupo tem no maximo **3 palavras** e respeita teto de caracteres (`<= 20` para 3 palavras, `<= 22` para 2 palavras), nunca cruzando fim de frase nem colando palavras no Canvas.

## 5. Audio diegetico por cena (`audio/sound_design.py`)

Antes da mixagem com drone e SFX, processe `voz_blocos` com crossfade de `15ms`:
- **`interfone_porteiro`**: passa-banda `320 Hz` a `2600 Hz`, saturacao analogica leve e estatica discreta.
- **`voz_telefone`**: passa-banda telefonico (`340 Hz` a `3000 Hz`), compressao de linha celular, leve micro-chiado GSM e foco central.
- **`narrador_tenso` e `panico`**: reflexoes curtas e sutis de cabine/interior fechado sem embolar diccao.
- **`sussurro_twist`**: equalizacao seca e proxima do microfone (zero reverb) com corte seco do drone.
- **`cta_comercial`**: voz 100% seca, clara e energica na pausa de tela cheia (drone silenciado).

## 6. Cama sonora, SFX hibridos e masterizacao em -14 LUFS

- Carregue SFX reais de `assets/sfx/` quando presentes, com fallback acustico procedural HD automatico.
- Aplique ducking (`sidechaincompress` acionado pela voz) sobre drone e SFX.
- Masterize em 2 passagens `ffmpeg loudnorm` mirando `-14 LUFS` (`TP -1.5 dBTP`, `LRA=7`) gerando `audio/mix_final.mp3` e copiando para `audio/narracao.mp3`.
- Valide sempre com `pipeline/historico.py validar-audio`, `ffprobe` e medicao `loudnorm`.
