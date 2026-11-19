# Biblioteca de SFX Reais (`assets/sfx/`)

Pasta oficial de efeitos sonoros reais (`.wav` ou `.mp3`) carregados automaticamente por `audio/sound_design.py`, conforme a skill `biblioteca-sfx-reais`.

## Padrao tecnico obrigatorio

- Formato preferencial: `WAV PCM 16-bit`, `44100 Hz`, estereo (`2` canais).
- Silencio inicial removido (`ataque <= 0.015s`) e loudness normalizado em `-18 LUFS` (`TP <= -3 dBTP`).
- Se um arquivo `.wav` ou `.mp3` com o nome canonico (`sub_boom`, `whoosh`, `riser`, `heartbeat`, `sussurro`, `passos_corredor`, `porta_impacto`, `glitch_tv`, `impacto_twist`, `guarda_roupa`, `cta_pop`) existir nesta pasta, `audio/sound_design.py` usa o arquivo real automaticamente.
- Se nao existir ainda, o pipeline aciona automaticamente o sintetizador acustico procedural de alta fidelidade como fallback, garantindo operacao 100% offline.

## Comandos uteis (na raiz do repositorio)

```bash
# Auditar o que esta instalado em assets/sfx/ e o que usa fallback
python3 audio/baixar_sfx.py --verificar

# Importar e padronizar um arquivo local (.wav ou .mp3) CC0 baixado manualmente
python3 audio/baixar_sfx.py --importar sussurro /caminho/para/whisper.mp3

# Gerar SFX reais sob demanda via ElevenLabs Sound Effects (usa ELEVENLABS_API_KEY do ambiente/.env)
python3 audio/baixar_sfx.py --elevenlabs

# Tentar baixar fontes CC0 curadas (quando configuradas com URL direta)
python3 audio/baixar_sfx.py --baixar
```
