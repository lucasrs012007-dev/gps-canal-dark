---
name: biblioteca-sfx-reais
description: Gerencia, gera (via ElevenLabs Sound Effects ou acervos CC0), padroniza e mixa efeitos sonoros reais na pasta assets/sfx/ integrados ao audio/sound_design.py e audio/eventos.json, mantendo fallback procedural automatico e masterizacao em -14 LUFS. Use quando quiser trocar ou reforcar efeitos sinteticos por SFX reais em um Short.
---

# Biblioteca de SFX Reais (`assets/sfx/`) + Mixagem Hibrida

Skill especializada para elevar o realismo sonoro da fabrica de Shorts combinando efeitos reais em `assets/sfx/` com a sincronia matematica de `audio/eventos.json` e o pipeline de masterizacao de `audio/sound_design.py`.

## 1. Estrutura e convencao de arquivos

Armazene apenas efeitos licenciados ou gerados via API (CC0 ou ElevenLabs Sound Effects) com nomes descritivos em minusculas e sem espacos:

```text
assets/
  sfx/
    catalogo.json          # nome, origem/licenca, duracao_s, ganho_db, pico_dbfs
    drone_suspense.wav     # cama continua opcional (loop limpo)
    alerta_gps.wav         # notificacao de navegador
    alerta_emergencia.wav  # alerta critico de celular
    freada_pneu.wav        # freada brusca em asfalto
    caminhao_doppler.wav   # buzina + passagem de caminhao
    batida_madeira_01.wav  # impactos fisicos individuais
    sub_boom.wav           # impacto grave no climax/plot twist
    cta_pop.wav            # som limpo de notificacao na CTA
```

Regras de repositorio:
- Nunca commite arquivos de audio com direitos autorais ou sem registro em `assets/sfx/catalogo.json`.
- Mantenha cada SFX enxuto (preferencialmente `<= 5s` em `.wav` ou `.flac` limpo; cama em loop curto).

## 2. Padronizacao tecnica obrigatoria (FFmpeg)

Antes de entrar no catalogo, normalize todo arquivo novo para o formato exato esperado pelo `audio/sound_design.py` (`44100 Hz`, 16-bit PCM, estereo, sem silencio morto no inicio):

```bash
ffmpeg -y -i entrada_bruta.mp3 \
  -af "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB:detection=peak,loudnorm=I=-18:TP=-3:LRA=9" \
  -ar 44100 -ac 2 -c:a pcm_s16le assets/sfx/<nome>.wav
```

## 3. Geracao sob demanda via ElevenLabs Sound Effects

Quando um evento novo nao existir em `assets/sfx/`, combine esta skill com a skill oficial `sound-effects` (`elevenlabs/skills`):
- Leia `ELEVENLABS_API_KEY` exclusivamente do ambiente ou do `.env` local (nunca hardcode no codigo).
- Use prompts objetivos em ingles descrevendo ambiente, distancia e textura (sem musica de fundo):
  - Exemplo freada: `"Hard car tire screech braking sharply on wet asphalt at night, close perspective, dry studio quality, no music"`
  - Exemplo caminhao: `"Heavy semi truck air horn with fast doppler whoosh passing right in front of car at night, cinematic, no music"`
  - Exemplo impacto: `"Deep cinematic sub bass boom impact with short dark tail, suspense thriller trailer, no music"`
- Defina `duration_seconds` igual ou menor que a janela disponivel no `audio/eventos.json` (ex.: `1.75` para o bloco `[SFX:caminhao:1.75]`).
- Salve o resultado normalizado em `assets/sfx/` e registre no `assets/sfx/catalogo.json` para reutilizacao sem gastar novos creditos.

## 4. Integracao hibrida com `audio/sound_design.py`

A regra de ouro e **zero quebra do pipeline offline**:
1. Para cada evento mapeado em `audio/eventos.json`, procure primeiro `assets/sfx/<arquivo>.wav`.
2. Se o arquivo existir, carregue em stereo `44100 Hz` (via `wave` / `numpy`), aplique fade-in (`5ms`) e fade-out (`15ms`) e ajuste o ganho relativo para respeitar o ducking da voz.
3. Se o arquivo nao existir ainda, use automaticamente o sintetizador procedural correspondente ja implementado em `audio/sound_design.py`.
4. Sempre finalize pela etapa de mixagem com `sidechaincompress` acionado pela voz e masterizacao 2-pass em `-14 LUFS` (`TP -1.5 dBTP`).

## 5. Checklist de aprovacao

- [ ] Nenhum arquivo de SFX tem atraso/silencio morto no ataque (transiente comeca em `t <= 0.015s`).
- [ ] Todos os arquivos estao em `44100 Hz`, 16-bit, estereo, registrados em `assets/sfx/catalogo.json`.
- [ ] `python3 audio/sound_design.py` roda sem erros tanto com `assets/sfx/` preenchida quanto vazia (fallback procedural).
- [ ] Mix final validado com `ffprobe` e `loudnorm` em torno de `-14 LUFS` sem clipar (`TP <= -0.5 dBTP`).
