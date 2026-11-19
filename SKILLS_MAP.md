# SKILLS_MAP: Mapa Oficial de Agent Skills do Repositorio

Catalogo central das Agent Skills instaladas em `.agents/skills/` e rastreadas em `skills-lock.json`.
Todas as skills externas abaixo foram auditadas via `gh` e `npx skills` (`Gen: Safe`, `Socket: 0 alerts`), instaladas em modo `--copy` para funcionar de forma universal (Antigravity, Claude Code, Codex, Cursor e compativeis).

## 1. Skills Instaladas do GitHub (5 pilares)

| Skill | Pilar | Repositorio de Origem | Auditoria (estrelas / licenca / seguranca) | Prompt curto para acionar |
|---|---|---|---|---|
| `text-to-speech` | 1. Voz e Audio | [elevenlabs/skills](https://github.com/elevenlabs/skills) (`text-to-speech`) | Oficial ElevenLabs, 578 stars, MIT, Gen Safe, 0 alertas Socket | `"Use a skill text-to-speech para ajustar a sintese ElevenLabs em audio/gerar_narracao.py"` |
| `sound-effects` | 1. Voz e Audio | [elevenlabs/skills](https://github.com/elevenlabs/skills) (`sound-effects`) | Oficial ElevenLabs, 578 stars, MIT, Gen Safe, 0 alertas Socket | `"Use a skill sound-effects para gerar SFX reais de suspense para assets/sfx/"` |
| `video-director` | 2. Video e Animacao por Codigo | [win4r/video-director](https://github.com/win4r/video-director) (`video-director`) | 503 stars, MIT, Gen Safe, 0 alertas Socket | `"Use a skill video-director para revisar ritmo, timeline e QA visual do player.html"` |
| `github-actions-efficiency` | 3. Automacao em Nuvem | [github/awesome-copilot](https://github.com/github/awesome-copilot) (`github-actions-efficiency`) | Oficial GitHub, 41.357 stars, MIT, Gen Safe, 0 alertas Socket | `"Use a skill github-actions-efficiency para otimizar e enxugar o workflow .github/workflows/"` |
| `social` | 5. Retencao e Conversao | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) (`social`) | 61.460 stars, MIT, Gen Safe, 0 alertas Socket | `"Use a skill social para criar ganchos, legendas de post e estrategia de distribuicao de Shorts/Reels"` |

Para restaurar ou atualizar as skills externas no futuro:

```bash
npx skills list
npx skills update
```

## 2. Skills Proprias da Fabrica de Canal Dark (`.agents/skills/`)

| Skill | Pilar | Caminho | Objetivo no Pipeline | Prompt curto para acionar |
|---|---|---|---|---|
| `audio-sound-design-suspense` | 1. Voz e Audio | `.agents/skills/audio-sound-design-suspense/SKILL.md` | Prosodia fluida, corte de pausas (`0,18s` / `0,45s`), zero onomatopeias faladas, `.env`/Colab Secrets, cama sonora, ducking e master `-14 LUFS` | `"Aplique audio-sound-design-suspense para gerar e masterizar o audio do Video NN"` |
| `biblioteca-sfx-reais` | 1. Voz e Audio | `.agents/skills/biblioteca-sfx-reais/SKILL.md` | Catalogo e normalizacao (`44.1kHz`, `-18 dBFS`) de SFX reais em `assets/sfx/` com fallback procedural no `audio/sound_design.py` | `"Use biblioteca-sfx-reais para integrar SFX reais de assets/sfx/ no sound_design.py"` |
| `viralstick-animacao-2d` | 2. Video e Animacao por Codigo | `.agents/skills/viralstick-animacao-2d/SKILL.md` | Motor V3 (Dopamina Visual): rig flat em capsula, Depth of Field `blur(8px)`, cortes `1,0s-1,8s`, fundos pulsantes, particulas, `bigFace`, legendas pop-in e regra Sempre Video Novo | `"Aplique viralstick-animacao-2d para construir o player.html V3 do proximo Short"` |
| `automacao-nuvem-telegram-actions` | 3. Automacao em Nuvem | `.agents/skills/automacao-nuvem-telegram-actions/SKILL.md` | Workflow GitHub Actions (`ubuntu-latest`, Chrome headless + FFmpeg + Secrets) disparado por Bot do Telegram com devolucao do `.mp4` no chat | `"Use automacao-nuvem-telegram-actions para criar o workflow de render na nuvem + bot Telegram"` |
| `olheiro-virais-youtube` | 4. Mineracao de Virais | `.agents/skills/olheiro-virais-youtube/SKILL.md` | Olheiro da Gringa via YouTube Data API v3 (~3 unidades de cota/canal), Outlier Score `>= 3x`, trava contra `historico_videos.json` e adaptacao inedita para o Brasil | `"Use olheiro-virais-youtube para minerar 3 outliers da gringa e propor o Video 03"` |
| `roteiro-retencao-funil-manychat` | 5. Retencao e Conversao | `.agents/skills/roteiro-retencao-funil-manychat/SKILL.md` | Roteiros "E se...?" em 7 blocos (`35s-45s`, `95-115` palavras) + CTA final `"COMENTE EU QUERO"` conectada ao funil de Direct automatico no ManyChat/Instagram | `"Use roteiro-retencao-funil-manychat para escrever roteiro_03.txt e o fluxo ManyChat"` |

## 3. Skills-Base de Engenharia, Motion e UI ja Presentes em `.agents/skills/`

Estas skills ja faziam parte do kit base do repositorio e continuam disponiveis como apoio tecnico:

| Grupo | Skills em `.agents/skills/` | Quando acionar |
|---|---|---|
| Roteamento | `central-mestre-43-skills` | `"Use central-mestre-43-skills para escolher a skill certa para esta tarefa"` |
| Motion e Performance Web | `animate`, `choreograph`, `animation-performance`, `animation-vocabulary`, `improve-animations` | `"Use choreograph ou animation-performance para refinar curvas e FPS no player.html"` |
| Interface e Qualidade | `frontend-ui-engineering`, `ui-ux-pro-max`, `browser-testing-with-devtools`, `code-review-and-quality` | `"Use browser-testing-with-devtools para auditar o player em Chrome headless"` |
| Engenharia e Seguranca | `security-and-hardening`, `systematic-debugging`, `debugging-and-error-recovery`, `test-driven-development`, `verification-before-completion`, `performance-optimization`, `planning-and-task-breakdown`, `writing-plans`, `executing-plans`, `incremental-implementation`, `shipping-and-launch` | `"Use security-and-hardening antes de subir novas integracoes de API ou tokens"` |

## 4. Radar de Skills do GitHub (proximos sprints)

Candidatas reais encontradas e verificadas no GitHub / `npx skills` que foram mantidas fora da instalacao inicial para evitar sobrecarga de contexto, mas valem avaliacao nos proximos sprints:

| # | Repositorio / Skill | Pilar | Metricas verificadas | Por que observar nos proximos sprints | Comando futuro (`npx skills`) |
|---|---|---|---|---|---|
| 1 | [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (`ffmpeg-skill`) | 1. Voz e Audio | 8.259 stars, MIT, 42 ferramentas locais FFmpeg | Excelente para edicao local avancada, corte de silencio, loudness e checagem multi-plataforma (requer FFmpeg 6.1+) | `npx skills add kajisho5/ffmpeg-skill` |
| 2 | [remotion-dev/skills](https://github.com/remotion-dev/skills) (`remotion-best-practices`) | 2. Video por Codigo | 7.555 stars, 861K+ installs (oficial Remotion) | Padrao ouro caso decidamos evoluir de HTML5 Canvas puro para composicoes React/Remotion com 3D/WebGL | `npx skills add remotion-dev/skills --skill remotion-best-practices` |
| 3 | [artemnovitckii/claude-animation-skills](https://github.com/artemnovitckii/claude-animation-skills) (`stick-figure`, `map-route`, `kurzgesagt`) | 2. Video por Codigo | 945 stars, 11 estilos de animacao para Reels | Referencia forte para novos estilos visuais em series paralelas (mapas 3D, stick figure, estilo Kurzgesagt) | `npx skills add artemnovitckii/claude-animation-skills --list` |
| 4 | [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli) (`playwright-cli`) | 2. Video / QA Browser | 15.311 stars, Apache-2.0, 220K+ installs (oficial Microsoft) | Automacao de navegador via CLI para QA visual e capturas de tela sem escrever scripts CDP manuais | `npx skills add microsoft/playwright-cli --skill playwright-cli` |
| 5 | [github/awesome-copilot](https://github.com/github/awesome-copilot) (`github-actions-hardening`) | 3. Automacao em Nuvem | 41.357 stars, MIT (oficial GitHub) | Blindagem de seguranca em GitHub Actions (pinning de SHA, permissoes minimas, protecao de Secrets) | `npx skills add github/awesome-copilot --skill github-actions-hardening` |
| 6 | [serejaris/telegram-skills](https://github.com/serejaris/telegram-skills) | 3. Automacao em Nuvem | 41 stars, MIT, HTTP puro sem framework pesado | Referencia direta para mensagens ricas, botoes inline e envio de midia na Telegram Bot API | `npx skills add serejaris/telegram-skills --list` |
| 7 | [AgriciDaniel/claude-youtube](https://github.com/AgriciDaniel/claude-youtube) (`claude-youtube`) | 4. Mineracao / YouTube | 813 stars, MIT, 14 sub-skills de YouTube | Util quando o canal escalar para auditoria completa de canal, SEO de titulos, thumbnails e calendario editorial | `npx skills add AgriciDaniel/claude-youtube` |
| 8 | [jimliu/baoyu-skills](https://github.com/jimliu/baoyu-skills) (`baoyu-youtube-transcript`) | 4. Mineracao de Virais | 23K+ installs no catalogo `skills.sh` | Extrai transcricoes de videos/Shorts de referencia para estudar ritmo de gancho e estrutura de retencao | `npx skills add jimliu/baoyu-skills --skill baoyu-youtube-transcript` |
| 9 | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) (`copywriting`) | 5. Retencao e Conversao | 61.460 stars, MIT | Complemento direto para paginas de captura, ofertas e textos de conversao apos o clique no link do Direct | `npx skills add coreyhaines31/marketingskills --skill copywriting` |

## 5. Regra de Seguranca e Continuidade

- **Segredos isolados**: chaves de API (`ELEVENLABS_API_KEY`, `YOUTUBE_API_KEY`, `TELEGRAM_BOT_TOKEN`) ficam exclusivamente em `.env` local (ignorado em `.gitignore`), nos **Colab Secrets** ou nos **GitHub Actions Secrets**.
- **Sem quebra do Video 02 (V3)**: o pipeline principal (`pipeline/historico.py` -> `audio/gerar_narracao.py` -> `audio/sound_design.py` -> `player.html` -> `render/renderizar.py`) permanece 100% independente das skills instaladas e pronto para gerar `output/short_02.mp4` ("Rota recalculada").
