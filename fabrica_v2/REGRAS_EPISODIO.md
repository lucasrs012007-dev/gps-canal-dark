# Regras obrigatorias para novos episodios (ep03+)

Checklist tecnico e editorial para manter o padrao da `fabrica_v2`:

- [ ] **Voz em 1 chamada unica:** rodar `python3 fabrica_v2/engine/gerar_audio.py --ep fabrica_v2/episodios/<ep> --engine gemini --mode batch` (modelo `gemini-3.8-flash-tts`, voz `Mako`). Nunca rodar modo segmento por padrao.
- [ ] **Duracao e formato:** alvo de `65s` a `85s`, resolucao `1080x1920`, `30fps`, mixagem normalizada em `-14 LUFS` (True Peak maximo `-1.5 dBTP`).
- [ ] **CTA falada no loop final:** o segmento `loop` DEVE conter uma chamada curta falada convidando o espectador a comentar (ex.: "Comenta ai!" ou "Comenta o dia aqui embaixo!").
- [ ] **Corte seco no final (`0.25s`):** configurar `"cauda_final": 0.25` no `roteiro.json` (ou omitir para herdar o padrao `0.25s` do motor) para loop imediato sem silencio morto e sem cortar a ultima silaba.
- [ ] **Duas entregas obrigatorias:** gerar `video_final.mp4` (master de alta qualidade) e `video_leve.mp4` (mobile `< 18 MB`, `-movflags +faststart`, `1080x1920`, `30fps`, `aac 128k`).
- [ ] **Integridade do motor visual:** manter `fabrica_v2/engine/character.js` e `fabrica_v2/engine/hud.js` 100% intactos (identicos ao cofre `sandbox_opus/`).
- [ ] **Auditoria visual antes do render completo:** rodar `render.py --ep <ep> --auditoria` e inspecionar stills de todas as cenas (`--stills`) antes de disparar o render completo do MP4.
- [ ] **Higiene de repositorio:** zero emoji, zero travessao e zero meia-risca em codigo, JSON e documentacao; nunca versionar `.mp4`, `.wav`, `.mp3`, `build/`, `tts_cache/`, `sandbox_opus/` ou chaves `.env`.

## Regra de Ganchos (Anti-Repeticao)

- **PROIBIDO** usar `"Voce! E, voce mesmo!"` ou qualquer frase fixa repetida nos primeiros 3 segundos.
- Antes de escrever qualquer episodio novo, ler obrigatoriamente o campo `hook` de todos os episodios anteriores em `fabrica_v2/episodios/*/roteiro.json` para garantir abertura 100% inedita.
- Rotacionar obrigatoriamente entre estes **5 modelos de gancho** (maximo 2,5 segundos, impacto imediato):
  1. **Choque de numero absurdo** (ex: comeca pequeno, explode em colapso global).
  2. **No meio do caos** (acao absurda acontecendo ja no segundo 0).
  3. **Desafio de ego** (ex: "Quase ninguem passa do Dia X...").
  4. **Falsa vantagem + quebra** (ex: "Parece o sonho perfeito, ate voce...").
  5. **Contagem regressiva / aviso** (ex: "Voce tem X dias antes de...").

