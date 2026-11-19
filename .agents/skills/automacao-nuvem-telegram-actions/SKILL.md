---
name: automacao-nuvem-telegram-actions
description: Especifica e implementa a automacao em nuvem da fabrica de Shorts usando GitHub Actions (runner Linux ubuntu-latest com Chrome headless, FFmpeg e Secrets) disparada e monitorada por um Bot do Telegram (gatilho por mensagem e devolucao do MP4 pronto no chat). Use quando for configurar renderizacao automatica na nuvem ou controle remoto via Telegram.
---

# Automacao em Nuvem: GitHub Actions + Bot do Telegram

Skill de arquitetura para sair da execucao manual no Colab e operar a fabrica de Shorts 100% na nuvem com disparo por mensagem no Telegram e renderizacao em Linux headless via GitHub Actions.

## 1. Arquitetura do fluxo ponta a ponta

```text
[Celular / Telegram]
   |  mensagem: /render  ou  /novo <tema>
   v
[Bot do Telegram (Webhook leve / Cloudflare Worker / Vercel Function)]
   |  POST /repos/{owner}/{repo}/actions/workflows/render-short.yml/dispatches
   |  Authorization: Bearer <GH_WORKFLOW_TOKEN>
   v
[GitHub Actions (ubuntu-latest)]
   |-- 1. Valida historico_videos.json (pipeline/historico.py verificar)
   |-- 2. Instala/reaproveita cache de ffmpeg + google-chrome-stable + Python
   |-- 3. Roda audio/gerar_narracao.py (usa secret ELEVENLABS_API_KEY)
   |-- 4. Roda audio/sound_design.py (-14 LUFS)
   |-- 5. Roda render/renderizar.py --legendas -> output/short_NN.mp4
   |-- 6. Valida com ffprobe (1080x1920, 30fps, h264, aac)
   |-- 7. Envia MP4 direto no Telegram via Bot API (sendVideo) + salva Artifact
   v
[Celular / Telegram recebe o video pronto + duracao + status]
```

## 2. Regras de seguranca e Secrets obrigatorios

Nunca grave tokens ou chaves em arquivos `.yml`, `.py` ou logs do Actions. Configure apenas em **GitHub Repository Settings -> Secrets and variables -> Actions**:
- `ELEVENLABS_API_KEY`: chave da ElevenLabs (opcional; sem ela cai no `edge-tts`).
- `ELEVENLABS_VOICE_ID`: ID da voz preferida (opcional).
- `TELEGRAM_BOT_TOKEN`: token gerado pelo `@BotFather`.
- `TELEGRAM_CHAT_ID`: ID numerico do chat/canal autorizado (obrigatorio para restringir quem pode disparar o bot!).
- No endpoint do bot (Cloudflare Worker / webhook), configure tambem `GH_WORKFLOW_TOKEN` (Fine-grained PAT com permissao minima `Actions: Read and write` somente neste repositorio) e valide `message.chat.id == TELEGRAM_CHAT_ID` antes de disparar qualquer workflow.

## 3. Contrato do Workflow `.github/workflows/render-short.yml`

Combine sempre esta skill com `github-actions-efficiency` para otimizar tempo e minutos de CI:
- Gatilhos: `workflow_dispatch` com inputs `modo_teste` (boolean, padrao `false`) e `usar_legendas` (boolean, padrao `true`).
- `concurrency`: grupo `render-short` com `cancel-in-progress: false` (para nao abortar um render pago da ElevenLabs no meio).
- `timeout-minutes: 15` (seguranca contra travamentos de navegador).
- Permissoes minimas: `permissions: { contents: read }`.
- Cache: usar `actions/cache` para pacotes pip/apt ou baixar apenas o necessario; o runner `ubuntu-latest` ja costuma trazer `google-chrome` e `ffmpeg` preinstalados (verificar com `command -v` antes de rodar `apt-get`!).
- Validacao antes do envio: rodar `ffprobe` confirmando `1080x1920` e tamanho `<= 49 MB` (limite padrao do `sendVideo` do Telegram Bot API; acima disso enviar link do GitHub Artifact).

## 4. Entrega no Telegram (Bot API via curl/Python stdlib)

No passo final do workflow (tambem com `if: failure()` para avisar em caso de erro):
- Em sucesso: enviar via `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendVideo` com `chat_id`, `video=@output/short_NN.mp4`, `supports_streaming=true` e `caption` contendo titulo, duracao, LUFS e hash do commit.
- Em falha: enviar mensagem curta via `sendMessage` com o nome do job e o link da execucao (`${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`).

## 5. Checklist antes de colocar em producao

- [ ] `workflow_dispatch` testado primeiro com `modo_teste=true` (2 segundos, zero desperdicio).
- [ ] Nenhum segredo aparece em `echo`, `print` ou logs de erro (`::add-mask::` se necessario).
- [ ] Bot valida `TELEGRAM_CHAT_ID` estritamente (rejeita mensagens de desconhecidos).
- [ ] Workflow respeita `pipeline/historico.py verificar` e baixa/entrega o `short_NN.mp4` dinamico sem nome fixo `short_01.mp4`.
