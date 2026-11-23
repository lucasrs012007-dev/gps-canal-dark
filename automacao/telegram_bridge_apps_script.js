/**
 * Ponte Telegram 24/7 Gratuita (Google Apps Script) -> GitHub Actions (Fabrica Dark V6)
 *
 * Configuracao obrigatoria em Project Settings -> Script Properties:
 *   TELEGRAM_BOT_TOKEN : Token do bot criado no @BotFather
 *   ALLOWED_CHAT_ID    : ID numerico do seu chat privado no Telegram (ex.: 123456789)
 *   GH_PAT             : Personal Access Token do GitHub com permissao Contents (Read & Write)
 *   GH_OWNER           : Dono do repositorio (ex.: lucasrs012007-dev)
 *   GH_REPO            : Nome do repositorio (ex.: gps-canal-dark)
 *
 * Comandos aceitos pelo Bot:
 *   /video <roteiro bruto>   -> dispara Diretor IA + Audio + Render V6 + entrega do MP4 no chat
 *   <texto longo >= 60 ch>   -> tambem inicia automaticamente sem precisar digitar /video
 *   /render                  -> renderiza o video ativo atual em historico_videos.json
 *   /ajuda                   -> mostra instrucoes rapidas
 */

function obterConfig_() {
  const props = PropertiesService.getScriptProperties();
  return {
    botToken: (props.getProperty('TELEGRAM_BOT_TOKEN') || '').trim(),
    allowedChatId: (props.getProperty('ALLOWED_CHAT_ID') || '').trim(),
    ghPat: (props.getProperty('GH_PAT') || '').trim(),
    ghOwner: (props.getProperty('GH_OWNER') || 'lucasrs012007-dev').trim(),
    ghRepo: (props.getProperty('GH_REPO') || 'gps-canal-dark').trim()
  };
}

function enviarTelegram_(botToken, chatId, texto) {
  const url = 'https://api.telegram.org/bot' + botToken + '/sendMessage';
  UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify({
      chat_id: String(chatId),
      text: String(texto).slice(0, 3900),
      disable_web_page_preview: true
    })
  });
}

function dispararGitHubActions_(cfg, payload) {
  const url = 'https://api.github.com/repos/' + cfg.ghOwner + '/' + cfg.ghRepo + '/dispatches';
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: {
      Authorization: 'Bearer ' + cfg.ghPat,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'FabricaDarkV6-TelegramBridge'
    },
    payload: JSON.stringify({
      event_type: 'novo_roteiro',
      client_payload: payload
    })
  });
  return {
    code: resp.getResponseCode(),
    body: resp.getContentText().slice(0, 300)
  };
}

function extrairTituloERoteiro_(textoBruto) {
  const limpo = String(textoBruto || '').trim();
  const linhas = limpo.split(/\r?\n/);
  if (linhas.length >= 2 && /^t[ií]tulo\s*:/i.test(linhas[0].trim())) {
    const titulo = linhas[0].replace(/^t[ií]tulo\s*:/i, '').trim();
    const roteiro = linhas.slice(1).join('\n').trim();
    return { titulo: titulo, roteiro: roteiro };
  }
  return { titulo: '', roteiro: limpo };
}

function doPost(e) {
  const okResp = ContentService.createTextOutput('OK').setMimeType(ContentService.MimeType.TEXT);
  try {
    const cfg = obterConfig_();
    if (!cfg.botToken || !cfg.allowedChatId || !cfg.ghPat) {
      return okResp;
    }
    if (!e || !e.postData || !e.postData.contents) {
      return okResp;
    }

    const update = JSON.parse(e.postData.contents);
    const msg = update.message || update.edited_message;
    if (!msg || !msg.chat || !msg.text) {
      return okResp;
    }

    const chatId = String(msg.chat.id);
    // Trava estrita de seguranca: ignora qualquer chat diferente de ALLOWED_CHAT_ID
    if (chatId !== cfg.allowedChatId) {
      return okResp;
    }

    const texto = String(msg.text || '').trim();
    if (!texto) {
      return okResp;
    }

    if (texto === '/start' || texto === '/ajuda' || texto === '/help') {
      enviarTelegram_(
        cfg.botToken,
        chatId,
        'Fabrica Dark V6 conectada.\n\n' +
        'Como usar:\n' +
        '1) Envie /video seguido do seu roteiro bruto (ou cole o roteiro direto com mais de 60 caracteres).\n' +
        '   Dica: voce pode colocar "Titulo: Meu Titulo" na primeira linha.\n' +
        '2) Envie /render para renderizar o video ativo atual do repositorio.'
      );
      return okResp;
    }

    if (texto === '/render') {
      enviarTelegram_(cfg.botToken, chatId, 'Pedido recebido! Iniciando renderizacao do video ativo na nuvem...');
      const resRender = dispararGitHubActions_(cfg, {
        titulo: '',
        roteiro: '',
        usar_video_atual: 'true',
        enviar_telegram: 'true',
        modo_teste: 'false'
      });
      if (resRender.code !== 204) {
        enviarTelegram_(
          cfg.botToken,
          chatId,
          'Erro ao acionar GitHub Actions (HTTP ' + resRender.code + '). Verifique o GH_PAT e as permissoes do repositorio.'
        );
      }
      return okResp;
    }

    let corpoRoteiro = '';
    if (/^\/video\b/i.test(texto)) {
      corpoRoteiro = texto.replace(/^\/video\b/i, '').trim();
    } else if (!texto.startsWith('/') && texto.length >= 60) {
      corpoRoteiro = texto;
    } else {
      enviarTelegram_(
        cfg.botToken,
        chatId,
        'Envie /video <seu roteiro completo> (minimo 15 palavras), cole um roteiro longo direto, ou use /render.'
      );
      return okResp;
    }

    const parsed = extrairTituloERoteiro_(corpoRoteiro);
    const qtdPalavras = parsed.roteiro.split(/\s+/).filter(Boolean).length;
    if (qtdPalavras < 15) {
      enviarTelegram_(
        cfg.botToken,
        chatId,
        'Roteiro muito curto (' + qtdPalavras + ' palavras). Envie pelo menos 15 palavras para iniciar a Fabrica V6.'
      );
      return okResp;
    }

    enviarTelegram_(
      cfg.botToken,
      chatId,
      'Roteiro recebido! Fabrica V6 iniciada na nuvem. Assim que terminar, envio o MP4 pronto direto aqui.'
    );

    const res = dispararGitHubActions_(cfg, {
      titulo: parsed.titulo,
      roteiro: parsed.roteiro,
      usar_video_atual: 'false',
      enviar_telegram: 'true',
      modo_teste: 'false'
    });

    if (res.code !== 204) {
      enviarTelegram_(
        cfg.botToken,
        chatId,
        'Nao foi possivel disparar o GitHub Actions (HTTP ' + res.code + '). Confira GH_PAT, GH_OWNER e GH_REPO nas Script Properties.'
      );
    }
  } catch (err) {
    Logger.log('Erro no webhook Fabrica V6: ' + err);
  }
  return okResp;
}

function doGet() {
  return ContentService.createTextOutput('Fabrica Dark V6 Telegram Bridge ativa.').setMimeType(
    ContentService.MimeType.TEXT
  );
}

/**
 * Rode esta funcao manualmente 1 vez no editor do Apps Script passando a URL do Web App publicado
 * (ou configurando WEB_APP_URL nas Script Properties) para registrar o webhook no Telegram.
 */
function configurarWebhook(webAppUrlOpcional) {
  const props = PropertiesService.getScriptProperties();
  const cfg = obterConfig_();
  const webAppUrl = (webAppUrlOpcional || props.getProperty('WEB_APP_URL') || '').trim();
  if (!cfg.botToken || !webAppUrl) {
    throw new Error('Defina TELEGRAM_BOT_TOKEN e WEB_APP_URL nas Script Properties antes de rodar configurarWebhook().');
  }
  const url = 'https://api.telegram.org/bot' + cfg.botToken + '/setWebhook';
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ url: webAppUrl })
  });
  Logger.log('setWebhook resposta: ' + resp.getContentText());
}
