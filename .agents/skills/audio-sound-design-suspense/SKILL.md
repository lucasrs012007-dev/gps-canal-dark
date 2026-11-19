---
name: audio-sound-design-suspense
description: "Regras obrigatorias de narracao, ritmo, sound design procedural e masterizacao para YouTube Shorts de suspense: corte de pausas mortas (0,18s padrao e 0,45s dramatica), proibicao de narrar onomatopeias de acao, ElevenLabs prioritario via .env ou Colab Secrets com fallback edge-tts grave, cama sonora + SFX sincronizados por eventos.json e masterizacao final em -14 LUFS com ducking. Use sempre que gerar ou revisar audio de um Short."
---

# Audio e Sound Design para Shorts de Suspense

Skill permanente para construcao de narracao cinematografica, sincronia matematica de eventos/legendas e mixagem procedural para YouTube Shorts de micro-suspense.

## 0. Regra permanente "Sempre Video Novo" e seguranca de chaves

- Leia o roteiro ativo automaticamente de `historico_videos.json` via `pipeline/historico.py` (impedindo repeticao de temas e mantendo o video atual alinhado ao numero de saida).
- **Zero vazamento de credenciais**: nunca grave `ELEVENLABS_API_KEY` em arquivos `.py`, `.html`, `.json` ou `.ipynb` rastreados pelo Git.
- Carregue automaticamente o arquivo `.env` local (listado no `.gitignore`) quando `ELEVENLABS_API_KEY` nao estiver no ambiente, e no Google Colab tente ler dos Secrets (`google.colab.userdata`) caso o campo `#@param` esteja vazio.

## 1. Prosodia conversacional e ritmo cinematografico sem pausas mortas

- **Regra de prosodia fluida**: escreva e leia as frases com fluidez conversacional, evitando pontos finais picotados demais que deixam a sintese robotica, mantendo pontos curtos apenas em pausas dramaticas intencionais e na virada do plot twist.
- Sintetize a narracao **frase por frase** (nunca um bloco corrido unico sujeito a pausas aleatorias do TTS).
- Em cada frase gerada, remova silencios mortos nas pontas com `ffmpeg` (`silenceremove` no inicio e no fim) e converta para WAV PCM uniforme (`44100 Hz`, 16-bit, estereo) antes da concatenacao para evitar deriva acumulada de quadros MP3.
- Meca a duracao real de cada frase limpa e monte a faixa `audio/voz_limpa.mp3` usando pausas exatas:
  - **Pausa padrao entre frases**: `0,18s`.
  - **Pausa dramatica antes de viradas/revelacoes**: `0,45s`.
  - **Pausa de acao fisica**: blocos dedicados de silencio (`[SFX:nome:duracao]`) para efeitos sonoros protagonizarem a cena.

## 2. Nunca narrar onomatopeias de acao

- Onomatopeias como `"Toc. Toc. Toc."`, `"Biii!"` ou `"Vrum!"` jamais devem ser faladas pelo locutor.
- Remova essas expressoes do texto enviado ao motor de voz e substitua por um bloco exato de silencio cronometrado (ex.: `[SFX:caminhao:1.75]` ou `[SFX:batidas_porta:2.10]`), registrado com inicio e duracao em `audio/eventos.json`.
- O som fisico real entra na camada de sound design exatamente dentro desse intervalo silencioso.

## 3. Motor de voz: ElevenLabs prioritario + fallback edge-tts grave

- **Prioridade 1 (ElevenLabs)**: motor principal sempre que `ELEVENLABS_API_KEY` estiver definida no ambiente, no `.env` local ou nos Secrets do Colab. Use o modelo `eleven_multilingual_v2`, voz configuravel por `ELEVENLABS_VOICE_ID` (padrao: voz masculina grave/narrativa) e `voice_settings` ajustados para interpretacao dramatica com emocao e variacao de tom: `stability=0.42`, `similarity_boost=0.80`, `style=0.35`, `use_speaker_boost=true`.
- **Prioridade 2 (Fallback gratuito `edge-tts`)**: quando nao houver chave ElevenLabs, use `edge-tts` com `pt-BR-AntonioNeural`, `pitch="-6Hz"` e `rate="+6%"` para obter timbre mais grave, contido e distante do ritmo de telejornal.
- **Modo automatizado (`--mock`)**: disponivel apenas para testes locais em ambientes sem acesso a WebSocket/API, gerando tons curtos para validar concatenacao, `eventos.json`, `timestamps.json` e mixagem.

## 4. Sincronia matematica (`timestamps.json` e `eventos.json`)

- Toda temporizacao deriva diretamente da duracao medida de cada WAV apos o `silenceremove` somada as pausas exatas inseridas.
- **`audio/timestamps.json`**: contem `video_id`, `titulo`, `roteiro`, palavras individuais e grupos prontos para legenda (`grupos`), com no maximo **3 palavras por bloco**, nunca atravessando o fim de uma frase.
- **`audio/eventos.json`**: contem `video_id`, `titulo`, `roteiro`, todos os marcos narrativos e intra-frase definidos no roteiro ativo (ex.: `gancho`, `hora_02`, `gps_rota`, `sem_destino`, `rua_escura`, `retrovisor`, `destino_acidente`, `hora_0206`, `freio`, `caminhao`, `quase`, `sussurro`, `plot_twist`, `proximo_acidente`, `cta`, `cta_acao`, `duracao_total`) e a lista completa de `frases`.

## 5. Cama sonora procedural + SFX sincronizados (stdlib + ffmpeg)

- Sintetize todos os efeitos localmente em WAV (Python `math`/`wave`/`struct`, acelerado por `numpy` quando disponivel), sem depender de downloads externos.
- Mantenha a cama continua de suspense (drone grave evolutivo + textura atmosferica discreta) evoluindo ate o climax e realizando **corte subito no `plot_twist`**.
- Sincronize todos os SFX pelo timestamp exato em `audio/eventos.json` (alertas/chimes, quedas, freadas, buzina + passagem Doppler de caminhao, batidas em madeira, riser crescente, sub-bass boom no climax e toque limpo na CTA).

## 6. Masterizacao final em -14 LUFS com ducking

- Processe a voz com filtro passa-alta suave (`~75 Hz`) e compressao leve para clareza em alto-falante de celular.
- Aplique **ducking** (`sidechaincompress` acionado pela faixa de voz) sobre o drone e a cama sonora, garantindo que a voz nunca fique encoberta e que os SFX ganhem protagonismo nos intervalos de silencio.
- Masterize o mix final em **2 passagens** com `ffmpeg loudnorm` mirando **`-14 LUFS`** (True Peak `-1.5 dBTP`, `LRA=7`) gerando `audio/mix_final.mp3` e sincronizando `audio/narracao.mp3` para compatibilidade com o player e o renderizador.
- Sempre valide o arquivo final com `ffprobe` e `loudnorm` antes de concluir.
