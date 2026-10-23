import { parseVideoUrl, PLATFORMS } from './platforms.js';

const HOST = 'com.instantvideodownloader.companion';
let port;
const pending = new Map();
let state = { status: 'idle', url: '', useLogin: true, outputMode: 'original', helper: null, metadata: null, progress: null, result: null, error: null };
const loaded = chrome.storage.session.get('state').then((saved) => {
  if (saved.state) state = { ...state, ...saved.state, helper: null };
  if (['inspecting', 'downloading'].includes(state.status)) {
    state.status = 'error';
    state.error = 'Chrome restarted the companion connection. Inspect the video again to continue.';
  }
});

async function update(patch) {
  Object.assign(state, patch);
  // Never store cookies, extraction payloads, or media download URLs.
  await chrome.storage.session.set({ state: { ...state } });
  chrome.runtime.sendMessage({ type: 'state', state: { ...state } }).catch(() => {});
}

function connect() {
  if (port) return port;
  const connection = chrome.runtime.connectNative(HOST);
  port = connection;
  connection.onMessage.addListener((message) => {
    const operation = pending.get(message.id);
    if (!operation) return;
    if (message.type === 'progress') {
      operation.progress?.(message.data);
      return;
    }
    pending.delete(message.id);
    if (message.type === 'error') operation.reject(new Error(message.data.message));
    else operation.resolve(message.data);
  });
  connection.onDisconnect.addListener(() => {
    // Read lastError to prevent an unhandled Chrome error; keep details out of the UI.
    const reason = chrome.runtime.lastError?.message || '';
    if (port === connection) port = undefined;
    const message = /not found|not registered|forbidden/i.test(reason)
      ? 'Install the local companion for this extension ID, then select Reconnect.'
      : 'The local companion disconnected. Reconnect and inspect the video again.';
    for (const operation of pending.values()) operation.reject(new Error(message));
    pending.clear();
    update({ helper: null }).catch(() => {});
  });
  return connection;
}

function native(action, data = {}, progress) {
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID();
    pending.set(id, { resolve, reject, progress });
    try { connect().postMessage({ id, action, ...data }); }
    catch {
      pending.delete(id);
      reject(new Error('The local companion could not start. Follow the setup guide, then reconnect.'));
    }
  });
}

async function sessionCookies(platform, useLogin) {
  if (!useLogin) return [];
  const domain = PLATFORMS[platform].domain;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const stores = await chrome.cookies.getAllCookieStores();
  const storeId = stores.find((store) => store.tabIds.includes(tab?.id))?.id;
  const records = await chrome.cookies.getAll({ domain, ...(storeId ? { storeId } : {}) });
  return records.filter((cookie) => !cookie.partitionKey).map((cookie) => ({
    name: cookie.name, value: cookie.value, domain: cookie.domain, path: cookie.path,
    secure: cookie.secure, httpOnly: cookie.httpOnly, hostOnly: cookie.hostOnly,
    session: cookie.session, expirationDate: cookie.expirationDate,
  }));
}

async function media(action, input) {
  if (['inspecting', 'downloading'].includes(state.status)) throw new Error('A video is already being processed.');
  const parsed = parseVideoUrl(input.url);
  if (action === 'download' && (!state.metadata || state.url !== parsed.url)) {
    throw new Error('Inspect this video before downloading it.');
  }
  const useLogin = input.useLogin !== false;
  const outputMode = input.outputMode || 'original';
  if (!['original', 'quicktime'].includes(outputMode)) throw new Error('Choose Original quality or QuickTime playback.');
  await update({
    status: action === 'inspect' ? 'inspecting' : 'downloading', url: parsed.url, useLogin, outputMode,
    metadata: action === 'inspect' ? null : state.metadata,
    progress: { stage: 'inspecting', percent: null }, result: null, error: null,
  });
  // Run independently of popup lifetime; connectNative keeps the service worker alive.
  (async () => {
    if (action === 'download' && outputMode === 'quicktime') {
      const helper = await native('ping');
      await update({ helper });
      if (!helper.capabilities?.includes('quicktime-source')) {
        throw new Error('The local companion needs updating for compatible H.264/AAC playback. Update the companion files in the installed project folder, then reload Instant in chrome://extensions.');
      }
    }
    const cookies = await sessionCookies(parsed.platform, useLogin);
    const result = await native(action, { url: parsed.url, cookies, userAgent: navigator.userAgent, quality: input.quality || 'best', outputMode }, (progress) => {
      update({ progress }).catch(() => {});
    });
    if (action === 'download' && outputMode === 'quicktime' && !result.media?.quicktimeCompatible) {
      throw new Error('The companion did not verify a compatible H.264/AAC video track. Update both the extension and companion, then try again.');
    }
    if (action === 'inspect') await update({ status: 'ready', metadata: result, progress: null });
    else await update({ status: 'complete', result, metadata: result.metadata, progress: null });
  })().catch((error) => update({ status: 'error', error: error.message, progress: null }));
  return { ok: true };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || message.type === 'state') return;
  (async () => {
    await loaded;
    switch (message.type) {
      case 'getState': return { state, extensionId: chrome.runtime.id };
      case 'connect': {
        const helper = await native('ping');
        await update({ helper });
        return { ok: true };
      }
      case 'inspect': return media('inspect', message);
      case 'download': return media('download', message);
      case 'cancel': return native('cancel');
      case 'openFolder': return native('open_folder');
      default: throw new Error('Unknown extension action.');
    }
  })().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
  return true;
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: 'instant-save', title: 'Inspect video with Instant', contexts: ['link', 'page'], documentUrlPatterns: Object.values(PLATFORMS).map(({ domain }) => `https://*.${domain}/*`) });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== 'instant-save') return;
  await loaded;
  try { await media('inspect', { url: info.linkUrl || info.pageUrl, useLogin: state.useLogin }); }
  catch (error) { await update({ error: error.message }); }
  chrome.action.openPopup().catch(() => {});
});
