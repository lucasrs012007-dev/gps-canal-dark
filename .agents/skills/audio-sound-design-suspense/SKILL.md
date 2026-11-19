---
name: audio-sound-design-suspense
description: Regras obrigatorias de narracao, ritmo, sound design procedural e masterizacao para YouTube Shorts de suspense: corte de pausas mortas (0,18s padrao e 0,45s dramatica), proibicao de narrar onomatopeias de acao, ElevenLabs prioritario com fallback edge-tts grave, cama sonora + SFX sincronizados por eventos.json e masterizacao final em -14 LUFS com ducking. Use sempre que gerar ou revisar audio de um Short.
---

# Audio e Sound Design para Shorts de Suspense

Skill permanente para construcao de narracao cinematografica, sincronia matematica de eventos/legendas e mixagem procedural para YouTube Shorts de micro-suspense.

## 1. Ritmo cinematografico sem pausas mortas

- Sintetize a narracao **frase por frase** (nunca um bloco corrido unico sujeito a pausas aleatorias do TTS).
- Em cada frase gerada, remova silencios mortos nas pontas com `ffmpeg` (`silenceremove` no inicio e no fim) e converta para WAV PCM uniforme (`44100 Hz`, 16-bit, estereo) antes da concatenacao para evitar deriva acumulada de quadros MP3.
- Meca a duracao real de cada frase limpa e monte a faixa `audio/voz_limpa.mp3` usando pausas exatas:
  - **Pausa padrao entre frases**: `0,18s`.
  - **Pausa dramatica antes de viradas/revelacoes**: `0,45s` (por exemplo, antes de `"Silencio."` e antes de `"E o rosto dele."`).
  - **Pausa de acao fisica**: blocos dedicados de silencio para efeitos sonoros protagonizarem a cena.

## 2. Nunca narrar onomatopeias de acao

- Onomatopeias como `"Toc. Toc. Toc."` ou `"Toque. Toque. Toque."` jamais devem ser faladas pelo locutor.
- Remova essas expressoes do texto enviado ao motor de voz e substitua por um bloco exato de silencio cronometrado (ex.: `2,1s` registrado como evento `batidas_porta` em `audio/eventos.json`).
- O som fisico real (3 batidas secas em porta de madeira oca) entra na camada de sound design exatamente dentro desse intervalo silencioso.

## 3. Motor de voz: ElevenLabs prioritario + fallback edge-tts grave

- **Prioridade 1 (ElevenLabs)**: quando `ELEVENLABS_API_KEY` estiver definida no ambiente, sintetize via API ElevenLabs com modelo `eleven_multilingual_v2`, voz configuravel por `ELEVENLABS_VOICE_ID` (padrao: voz masculina grave/narrativa) e parametros voltados a suspense controlado.
- **Prioridade 2 (Fallback gratuito `edge-tts`)**: quando nao houver chave ElevenLabs, use `edge-tts` com `pt-BR-AntonioNeural`, `pitch="-6Hz"` e `rate="+6%"` para obter timbre mais grave, contido e distante do ritmo de telejornal.
- **Modo automatizado (`--mock`)**: disponivel apenas para testes locais em ambientes sem acesso a WebSocket/API, gerando tons curtos para validar concatenacao, `eventos.json`, `timestamps.json` e mixagem.

## 4. Sincronia matematica (`timestamps.json` e `eventos.json`)

- Toda temporizacao deriva diretamente da duracao medida de cada WAV apos o `silenceremove` somada as pausas exatas inseridas.
- **`audio/timestamps.json`**: contem tanto as palavras individuais quanto os grupos prontos para legenda (`grupos`), com no maximo **3 palavras por bloco**, nunca atravessando o fim de uma frase.
- **`audio/eventos.json`**: contem os segundos exatos (em ponto flutuante) de todos os marcos narrativos e tecnicos (`alerta_1`, `hora_21`, `alerta_2`, `apagao_00`, `alerta_3`, `hora_03`, `batidas_porta`, `sussurro`, `silencio`, `foto_revela`, `big_face`, `plot_twist`, `duracao_total`).

## 5. Cama sonora procedural + SFX sincronizados (stdlib + ffmpeg)

- Sintetize todos os efeitos localmente em WAV (Python `math`/`wave`/`struct`, acelerado por `numpy` quando disponivel), sem depender de downloads externos:
  - **Alertas de emergencia (`alerta_1`, `alerta_2`, `alerta_3`)**: bipe duplo agudo estilo EAS/Defesa Civil.
  - **Queda de energia (`apagao_00`)**: estalo de disjuntor seguido de pitch drop eletrico grave.
  - **Batidas na porta (`batidas_porta`)**: 3 batidas secas em madeira oca em `+0,00s`, `+0,65s` e `+1,30s` dentro do bloco de `2,1s`.
  - **Climax e revelacao (`foto_revela`, `big_face`, `plot_twist`)**: riser crescente de tensao, impacto sub-bass boom no `big_face` e corte subito do drone exatamente no `plot_twist`.
  - **Cama continua**: drone grave de suspense (sub-bass + textura sombria discreta) evoluindo ate o climax e respeitando o silencio dramatico.

## 6. Masterizacao final em -14 LUFS com ducking

- Processe a voz com filtro passa-alta suave (`~75 Hz`) e compressao leve para clareza em alto-falante de celular.
- Aplique **ducking** (`sidechaincompress` acionado pela faixa de voz) sobre o drone e a cama sonora, garantindo que a voz nunca fique encoberta e que os SFX ganhem protagonismo nos intervalos de silencio.
- Masterize o mix final em **2 passagens** com `ffmpeg loudnorm` mirando **`-14 LUFS`** (True Peak `-1.5 dBTP`, `LRA=7`) gerando `audio/mix_final.mp3` e sincronizando `audio/narracao.mp3` para compatibilidade com o player e o renderizador.
- Sempre valide o arquivo final com `ffprobe` e `loudnorm`/`volumedetect` antes de concluir.
