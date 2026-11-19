---
name: olheiro-virais-youtube
description: Monitora canais gringos de micro-suspense e curiosidades via YouTube Data API v3, calcula Outlier Score para detectar Shorts virais fora da curva, cruza contra historico_videos.json para impedir repeticao e gera pautas ineditas adaptadas ao Brasil. Use quando quiser minerar temas virais da gringa para o proximo Video NN.
---

# Olheiro da Gringa: Mineracao de Virais com YouTube Data API v3

Skill de inteligencia editorial para descobrir padroes que ja estouraram em visualizacoes em canais internacionais (EUA, UK, ES) e transforma-los em historias 100% ineditas ambientadas no Brasil.

## 1. Regra de economia extrema de cota da YouTube Data API v3

A cota padrao gratuita e de `10.000 unidades/dia`.
- **NUNCA use `search.list` em loop** (custa `100 unidades` por chamada!).
- **SEMPRE use o fluxo economico (~3 unidades por canal)**:
  1. Converta o `channel_id` (`UC...`) para a playlist de uploads trocando o prefixo `UC` por `UU` (`0 unidades`, ou 1 chamada unica em `channels.list?part=contentDetails` armazenada em cache local).
  2. Chame `playlistItems.list?part=contentDetails&playlistId=UU...&maxResults=30` (`1 unidade`).
  3. Agrupe os 30 `videoId` em **uma unica chamada** `videos.list?part=snippet,statistics,contentDetails&id=id1,id2,...` (`1 unidade`).
- Com esse padrao, monitorar **50 canais gringos por dia** consome menos de `150 unidades` (< 2% da cota diaria!).
- Leia `YOUTUBE_API_KEY` somente do ambiente ou `.env` local (nunca versionar no Git).

## 2. Formula matematica de deteccao de Outliers (Shorts)

1. **Filtro de Short**: parseie `contentDetails.duration` (ISO 8601, ex. `PT42S`) e mantenha apenas videos com duracao `<= 65s` e publicados nos ultimos `90 dias` (ou janela configuravel).
2. **Baseline do canal**: calcule a **mediana** (nunca a media, que e distorcida por 1 video gigante) de `viewCount` dos ultimos 20 a 30 Shorts do mesmo canal.
3. **Outlier Score**:
   - `outlier_ratio = viewCount / max(mediana_canal, 1000)`
   - `views_por_hora = viewCount / max(horas_desde_publicacao, 1)`
   - `engajamento = (likeCount + commentCount * 3) / max(viewCount, 1)`
4. **Criterio de aprovacao de pauta**:
   - `outlier_ratio >= 3.0` (video performou pelo menos 3x acima do normal daquele canal)
   - `viewCount >= 100_000` (ou `>= 30_000` se publicado ha menos de 48h com `views_por_hora >= 1_000`)

## 3. Regra anti-plagio e adaptacao cultural para o Brasil

**Nunca traduza nem copie o roteiro gringo.** Extraia apenas a **mecanica psicologica vencedora**:
- Qual e o gatilho de curiosidade dos 0-3s? (ex.: tecnologia cotidiana que preve perigo, regra absurda de sobrevivencia, objeto comum que trai o protagonista)
- Qual e a curva de escalada? (3 sinais crescentes + silencio de tensao)
- Qual e a estrutura do plot twist? (inversao de perspectiva, revelacao de tempo, armadilha escondida na pista 1)

Em seguida:
1. Cruza a ideia contra `historico_videos.json` via `pipeline/historico.py` para garantir **zero repeticao** com videos ja publicados ou em producao.
2. Reconstroi do zero um cenario **100% brasileiro** (ex.: Marginal, apartamento 302, metro a noite, estrada de serra, elevador de predio antigo, audio no WhatsApp, Pix da madrugada, camera de porteiro).

## 4. Formato de saida da mineracao (`radar_virais.json` / pauta)

Salve o ranking gerado localmente (ignorado ou versionado apenas sem chaves) e entregue ao usuario 3 opcoes de pauta contendo:
- Link e metricas reais medidas do outlier de referencia (`outlier_ratio`, `views`, `duracao`).
- Mecanica psicologica identificada (por que segurou retencao).
- Proposta 100% inedita para o proximo `Video NN` com titulo, gancho "E se...?" (<= 14 palavras), relogio/elemento visual central e resumo do plot twist.
