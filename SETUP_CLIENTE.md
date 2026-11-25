# Guia de Setup do Cliente (Fabrica Multi-Canal)

Este repositorio funciona como um motor completo e reutilizavel de producao e publicacao automatica de videos curtos verticais (1080x1920, 9:16). Toda a identidade do canal fica centralizada em um unico arquivo: `config_canal.json`.

Em cada execucao na nuvem (GitHub Actions), a fabrica:
1. Cria um roteiro inedito sem repetir temas anteriores e dirige animacao 2D unica por fala (`pipeline/diretor_ia.py`).
2. Gera a narracao natural com a velocidade configurada (`audio/gerar_narracao.py`) e aplica trilha ambiente com ducking automatico e normalizacao `-14 LUFS` (`audio/trilha_mix.py`).
3. Renderiza animacao 2D real quadro a quadro em 1080x1920 @ 30fps no HTML5 Canvas (`player_universal.html` + `render/renderizar.py`) com cenarios animados, personagem vivo, HUD de dados e legendas sincronizadas.
4. Publica automaticamente nos canais habilitados (YouTube Shorts, Instagram Reels, TikTok) e entrega o pacote pronto no Telegram.

---

## Pre-requisitos

- Uma conta gratuita no GitHub.
- Uma chave da API do Google Gemini (`GEMINI_API_KEY`, gratuita no Google AI Studio).
- Contas nas redes onde deseja publicar automaticamente (YouTube, Telegram, Instagram profissional e/ou TikTok). Qualquer rede sem credenciais configuradas e ignorada automaticamente sem quebrar a pipeline.

---

## Passo 1: Clonar ou criar sua copia no GitHub

Escolha uma das duas opcoes:

### Opcao A: Usar como Template / Novo repositorio no GitHub
1. Crie um novo repositorio na sua conta GitHub (por exemplo, `meu-canal-automatico`).
2. No seu computador, clone este projeto e aponte para o seu repositorio:

```bash
git clone https://github.com/lucasrs012007-dev/gps-canal-dark.git meu-canal-automatico
cd meu-canal-automatico
git remote set-url origin https://github.com/SEU_USUARIO/meu-canal-automatico.git
git push -u origin main
```

### Opcao B: Ativar permissoes do GitHub Actions (obrigatorio)
1. No seu repositorio no GitHub, abra **Settings -> Actions -> General**.
2. Em **Workflow permissions**, selecione **Read and write permissions**.
3. Clique em **Save**.

Essa permissao e necessaria para a fabrica atualizar `historico_videos.json` automaticamente na branch `main` (evitando temas repetidos) e criar/apagar o asset temporario de Release quando o Instagram estiver ativado.

---

## Passo 2: Personalizar o canal em `config_canal.json`

Abra o arquivo `config_canal.json` na raiz do repositorio e edite apenas os valores do seu canal:

| Campo | O que controla | Exemplo |
|---|---|---|
| `nome_canal` | Nome do canal usado nos prompts de roteiro e titulos de fallback | `"Mente Blindada"` |
| `idioma` | Codigo BCP-47 do idioma do roteiro, vozes e metadados do YouTube (`pt-BR`, `en-US`, `es-MX`, `pt-PT`, `fr-FR`) | `"pt-BR"` |
| `pilares_editoriais` | Lista de temas/pilares que a IA alterna automaticamente a cada episodio (aceita objetos completos com `id`, `nome`, `gancho`, `instrucoes`, `exemplos` ou uma lista simples de textos) | `["Financas praticas", "Psicologia do dinheiro"]` |
| `estilo_visual_prompt` | Estilo visual em ingles aplicado a todas as imagens do storyboard | `"stylized 2.5D dark cinematic digital illustration, moody dramatic lighting, vertical 9:16 composition, no text, no watermark"` |
| `velocidade_voz` | Velocidade da narracao (`0.5` a `2.0`; recomendado entre `1.00` e `1.08`) | `1.02` |
| `cta_final` | Frase curta de chamada para acao usada no fechamento do video e nas legendas | `"Qual dessas dicas voce vai testar hoje? Comente aqui embaixo."` |
| `hashtags_padrao` | Lista de hashtags base (sem `#`), adaptadas automaticamente para YouTube (`#shorts`), Instagram (`#reels`) e TikTok (`#fyp`) | `["shorts", "financas", "dinheiro", "habitos"]` |
| `privacidade_youtube` | Privacidade padrao dos envios no YouTube (`public`, `unlisted` ou `private`) | `"public"` |

### Exemplo minimo para outro nicho

Se preferir comecar rapido, voce pode usar `pilares_editoriais` como lista simples de frases:

```json
{
  "nome_canal": "Historia em 60 Segundos",
  "idioma": "pt-BR",
  "pilares_editoriais": [
    "Batalhas e estrategias pouco conhecidas",
    "Invenções antigas que mudaram o mundo",
    "Biografias relampago de figuras historicas"
  ],
  "estilo_visual_prompt": "cinematic oil painting dark historical illustration, dramatic chiaroscuro lighting, vertical 9:16 composition, no text, no watermark",
  "velocidade_voz": 1.02,
  "cta_final": "Qual episodio historico voce quer ver amanha? Comente aqui embaixo.",
  "hashtags_padrao": ["shorts", "historia", "curiosidades", "fatosreais"],
  "privacidade_youtube": "unlisted"
}
```

### Comecando do Video 01 (opcional)

Se quiser zerar a memoria de episodios do canal de exemplo antes de lancar seu novo nicho, substitua o conteudo de `historico_videos.json` por:

```json
{
  "versao": 1,
  "regra": "Sempre Video Novo: cada producao exige tema inedito em relacao aos videos anteriores.",
  "video_atual": 0,
  "videos": []
}
```

Na primeira execucao apos zerar `historico_videos.json`, mantenha `usar_video_atual` desmarcado (`false`) para que a Estacao 1 crie e registre automaticamente o Video 01.

Depois, salve e envie suas alteracoes:

```bash
git add config_canal.json historico_videos.json
git commit -m "chore(canal): configura identidade do novo canal"
git push origin main
```

---

## Passo 3: Configurar os Secrets no GitHub

No repositorio no GitHub, acesse **Settings -> Secrets and variables -> Actions -> New repository secret**.

### 1. Obrigatorio (Roteiro + Voz + Imagens)

| Secret | Descricao |
|---|---|
| `GEMINI_API_KEY` | Chave de API do Google Gemini (criada em aistudio.google.com/apikey) |

### 2. YouTube Shorts (Estacao 5A, opcional)

| Secret | Descricao |
|---|---|
| `YOUTUBE_CLIENT_ID` | Client ID OAuth 2.0 do Google Cloud Console (YouTube Data API v3) |
| `YOUTUBE_CLIENT_SECRET` | Client Secret OAuth 2.0 do Google Cloud Console |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token OAuth 2.0 com escopo `https://www.googleapis.com/auth/youtube.upload` |

### 3. Telegram (Estacao 4, opcional)

| Secret | Descricao |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do bot criado no `@BotFather` |
| `TELEGRAM_CHAT_ID` | ID do chat, grupo ou canal que recebera os videos e avisos |

### 4. Instagram Reels (Estacao 5B, opcional)

| Secret | Descricao |
|---|---|
| `IG_USER_ID` | ID numerico da conta profissional do Instagram na Meta Graph API |
| `IG_ACCESS_TOKEN` | Token de acesso de longa duracao com permissao `instagram_content_publish` |
| `PUBLIC_VIDEO_URL` | Opcional: deixe vazio para usar o asset temporario automatico de GitHub Release (o repositorio precisa ser publico para a Meta baixar o arquivo) |

### 5. TikTok (Estacao 5C, opcional)

| Secret / Variable | Tipo | Descricao |
|---|---|---|
| `TIKTOK_ACCESS_TOKEN` | Secret | Access token OAuth 2.0 da TikTok Content Posting API |
| `TIKTOK_REFRESH_TOKEN` | Secret | Refresh token OAuth 2.0 |
| `TIKTOK_CLIENT_KEY` | Secret (opcional) | Habilita renovacao automatica se o token expirar (HTTP 401) |
| `TIKTOK_CLIENT_SECRET` | Secret (opcional) | Par do `TIKTOK_CLIENT_KEY` para renovacao automatica |
| `TIKTOK_MODE` | Variable (aba Variables) | `inbox` (padrao, envia para Rascunhos/Inbox) ou `direct` (publicacao direta) |
| `TIKTOK_PRIVACY` | Variable (aba Variables) | Usado apenas no modo `direct`: `PUBLIC_TO_EVERYONE` ou `SELF_ONLY` (apps ainda nao auditados) |

### 6. Voz alternativa (opcional)

| Secret | Descricao |
|---|---|
| `ELEVENLABS_API_KEY` | Chave da ElevenLabs usada como fallback caso o Gemini TTS atinja limite |
| `ELEVENLABS_VOICE_ID` | ID da voz escolhida na ElevenLabs |

---

## Passo 4: Rodar o primeiro teste manual

1. No GitHub, abra a aba **Actions**.
2. Selecione o workflow **Fabrica Dark V7 (Animacao 2D 30fps + Telegram)**.
3. Clique em **Run workflow** e preencha para o teste rapido:
   - `usar_video_atual`: desmarcado (`false`)
   - `modo_teste`: marcado (`true`, renderiza apenas 3 segundos / 90 quadros @ 30fps para validar tudo rapido)
   - `youtube_privacidade`: `unlisted` (ou `config` para usar `config_canal.json`)
   - `tiktok_modo`: `inbox`
4. Clique em **Run workflow** e acompanhe os logs passo a passo.
5. Quando tudo ficar verde, rode novamente com `modo_teste` desmarcado (`false`) para gerar seu primeiro video completo em 1080p @ 30fps.

---

## Passo 5: Ligar o canal automatico diario (cron-job.org)

O workflow usa `repository_dispatch` (`novo_roteiro`) para disparos pontuais sem atrasos do agendador nativo do GitHub.

1. No GitHub, gere um **Fine-grained Personal Access Token** (ou Classic Token) com permissao `Contents: Read and write` apenas neste repositorio.
2. Crie uma conta gratuita em `cron-job.org` e adicione um novo cronjob:
   - **URL:** `https://api.github.com/repos/SEU_USUARIO/SEU_REPOSITORIO/dispatches`
   - **Metodo:** `POST`
   - **Horario:** escolha os horarios diarios desejados (ex.: 11:00 e 18:00 no seu fuso horario).
   - **Headers:**
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer SEU_TOKEN_GITHUB`
     - `Content-Type: application/json`
     - `X-GitHub-Api-Version: 2022-11-28`
   - **Body (JSON):**

```json
{
  "event_type": "novo_roteiro",
  "client_payload": {
    "usar_video_atual": false,
    "enviar_telegram": true,
    "modo_teste": false
  }
}
```

3. Salve e clique em **Test Run** no `cron-job.org`. Um novo run deve aparecer imediatamente na aba **Actions** do GitHub.

---

## Passo 6: Personalizacoes extras (opcional)

- **Trilhas musicais proprias:** coloque arquivos `.mp3` ou `.wav` na pasta `assets/trilhas/`. A fabrica escolhe uma trilha aleatoria em loop com ducking automatico sob a voz. Se a pasta ficar vazia, uma trilha ambiente dark e sintetizada automaticamente via FFmpeg.
- **Validacao local rapida:** antes de subir alteracoes no codigo ou no `config_canal.json`, voce pode validar tudo localmente:

```bash
python3 -c "from pipeline.config_canal import carregar_config_canal; print(carregar_config_canal()['nome_canal'])"
python3 render/testar_animacao_2d.py
```
