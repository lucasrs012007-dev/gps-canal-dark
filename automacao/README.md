# Automacao Ponta a Ponta (Fabrica Dark V6.0)

Este diretorio conecta seu celular (Telegram) ao GitHub Actions para transformar um roteiro bruto em MP4 9:16 pronto e devolve-lo direto no chat, sem precisar abrir computador nem Google Colab.

Fluxo completo:
1. Voce envia o roteiro bruto no Telegram (`/video <roteiro>` ou texto direto).
2. A ponte gratuita no Google Apps Script (`automacao/telegram_bridge_apps_script.js`) valida seu `ALLOWED_CHAT_ID` e dispara o evento `novo_roteiro` (`repository_dispatch`) no GitHub.
3. O workflow `.github/workflows/fabrica_dark.yml` roda na nuvem:
   - `pipeline/diretor_ia.py`: cria `roteiro_XX.txt`, `cenas.json` e registra o novo video em `historico_videos.json` (`motor: "v6"`, `player: "player_universal.html"`).
   - `audio/gerar_narracao.py` + `audio/sound_design.py`: gera voz atuada por blocos, audio diegetico, SFX e masterizacao em -14 LUFS.
   - `render/renderizar.py --legendas`: renderiza 1080x1920 @ 30fps com Chrome headless e fatia Parte 1 / Parte 2 automaticamente quando o roteiro passa de 130 palavras.
   - `automacao/enviar_telegram.py`: entrega os MP4s prontos no seu Telegram (e publica tambem como Artifact do GitHub Actions).

---

## Passo 1: Criar o Bot do Telegram e descobrir seu Chat ID

1. No Telegram, abra `@BotFather`, envie `/newbot`, escolha nome e username, e salve o token gerado (`TELEGRAM_BOT_TOKEN`).
2. Envie uma mensagem qualquer (`/start`) para o seu novo bot.
3. Descubra seu ID numerico de chat enviando uma mensagem ao `@userinfobot` ou abrindo no navegador:
   `https://api.telegram.org/bot<SEU_BOT_TOKEN>/getUpdates`
   Anote o numero de `message.chat.id` (`TELEGRAM_CHAT_ID` / `ALLOWED_CHAT_ID`).

---

## Passo 2: Configurar Secrets no GitHub

No repositorio do GitHub, abra **Settings -> Secrets and variables -> Actions -> New repository secret** e cadastre:

| Secret | Obrigatorio | Para que serve |
|---|---|---|
| `GEMINI_API_KEY` | Sim | Diretor IA (`gemini-2.5-flash`) e voz principal (`gemini-2.5-flash-preview-tts`) |
| `TELEGRAM_BOT_TOKEN` | Sim (para envio no chat) | Token do bot criado no `@BotFather` |
| `TELEGRAM_CHAT_ID` | Sim (para envio no chat) | ID numerico do seu chat privado |
| `ELEVENLABS_API_KEY` | Opcional | Fallback 1 de voz caso o Gemini TTS esteja indisponivel |
| `ELEVENLABS_VOICE_ID` | Opcional | ID da voz ElevenLabs customizada |

---

## Passo 3: Criar o Token do GitHub (`GH_PAT`) para a ponte do Telegram

1. No GitHub, abra **Settings (da conta) -> Developer settings -> Personal access tokens -> Fine-grained tokens -> Generate new token**.
2. Selecione apenas o repositorio `gps-canal-dark`.
3. Em **Repository permissions**, conceda **Contents: Read and write** (necessario para `repository_dispatch`).
4. Gere e copie o token (`GH_PAT`).

---

## Passo 4: Publicar a Ponte 24/7 no Google Apps Script

1. Acesse [script.google.com](https://script.google.com) e crie um novo projeto (ex.: `Fabrica Dark V6 Bridge`).
2. Apague o codigo padrao e cole todo o conteudo de `automacao/telegram_bridge_apps_script.js`.
3. Clique na engrenagem **Project Settings -> Script Properties -> Add script property** e adicione:
   - `TELEGRAM_BOT_TOKEN`: token do seu bot
   - `ALLOWED_CHAT_ID`: seu chat ID numerico
   - `GH_PAT`: token criado no Passo 3
   - `GH_OWNER`: `lucasrs012007-dev`
   - `GH_REPO`: `gps-canal-dark`
4. Clique em **Deploy -> New deployment**:
   - Tipo: **Web app**
   - Execute as: **Me**
   - Who has access: **Anyone** (necessario para o webhook do Telegram conseguir chamar a URL; a trava de seguranca no codigo bloqueia qualquer chat diferente de `ALLOWED_CHAT_ID`).
5. Copie a **Web app URL** gerada (termina em `/exec`).
6. Salve essa URL na Script Property `WEB_APP_URL` e execute a funcao `configurarWebhook` uma unica vez no editor do Apps Script (ou registre via `curl`):
   ```bash
   curl -X POST "https://api.telegram.org/bot<SEU_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "<SUA_WEB_APP_URL>"}'
   ```

---

## Como usar no dia a dia

- **Novo Short pelo celular (Telegram):**
  Envie `/video` seguido do roteiro bruto (ou cole diretamente o texto com 60+ caracteres). Para definir titulo manual, coloque na primeira linha:
  ```text
  /video
  Titulo: A Ligacao das 03h17
  Era 03:17 da madrugada quando o celular tocou...
  ```
- **Renderizar o video ativo atual pelo Telegram:**
  Envie `/render`.
- **Disparo manual pelo navegador (sem Telegram):**
  Abra a aba **Actions -> Fabrica Dark V6 (Render na Nuvem + Telegram) -> Run workflow**, preencha `roteiro` (e `titulo` opcional) ou marque `usar_video_atual` e clique em **Run workflow**.

Observacao de tamanho: arquivos ate 49 MB sao entregues diretamente no chat via `sendVideo` (com fallback automatico para `sendDocument`). Se um MP4 passar de 49 MB, o bot envia automaticamente o link do Artifact no GitHub Actions.
