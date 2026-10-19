import assert from 'node:assert/strict';
import test from 'node:test';
import { parseVideoUrl } from '../extension/platforms.js';

const handlers = [];
const nativeRequests = [];
const snapshots = [];
let stored;
let hold = false;
let currentPort;
let supportsQuicktime = true;
const metadata = { title: 'Fixture', platform: 'instagram', creator: 'Fixture', heights: [1920], qualities: [{ value: '1920', label: '1080 × 1920' }] };
const event = () => {
  const listeners = [];
  return { addListener: (listener) => listeners.push(listener), emit: (...args) => listeners.forEach((listener) => listener(...args)) };
};

globalThis.chrome = {
  storage: { session: {
    get: async () => ({}),
    set: async ({ state }) => { stored = structuredClone(state); snapshots.push(structuredClone(state)); },
  } },
  tabs: { query: async () => [{ id: 42 }] },
  cookies: {
    getAllCookieStores: async () => [{ id: 'chosen-profile', tabIds: [42] }],
    getAll: async ({ domain, storeId }) => {
      assert.equal(storeId, 'chosen-profile');
      return [
        { domain: `.${domain}`, name: 'session', value: `dummy-session-${domain}`, path: '/', secure: true },
        { domain: `.${domain}`, name: 'partitioned', value: 'must-not-transfer', partitionKey: { topLevelSite: 'https://other.test' } },
      ];
    },
  },
  runtime: {
    id: 'a'.repeat(32),
    onMessage: { addListener: (handler) => handlers.push(handler) },
    onInstalled: event(),
    sendMessage: async () => {},
    connectNative: (host) => {
      assert.equal(host, 'com.instantvideodownloader.companion');
      currentPort = {
        onMessage: event(), onDisconnect: event(),
        postMessage(request) {
          nativeRequests.push(structuredClone(request));
          if (hold && ['inspect', 'download'].includes(request.action)) return;
          queueMicrotask(() => this.onMessage.emit({
            id: request.id, type: 'result',
            data: request.action === 'ping' ? { ffmpeg: true, extractorVersion: 'fixture', version: '0.1.2', capabilities: supportsQuicktime ? ['quicktime-source'] : [] }
              : request.action === 'download' ? { metadata, outputMode: request.outputMode, media: { quicktimeCompatible: true } } : metadata,
          }));
        },
      };
      return currentPort;
    },
  },
  contextMenus: { create() {}, onClicked: event() },
  action: { openPopup: async () => {} },
};

await import('../extension/background.js');

function request(message) {
  return new Promise((resolve) => {
    const keepOpen = handlers[0](message, { id: chrome.runtime.id }, resolve);
    assert.equal(keepOpen, true);
  });
}

async function waitFor(predicate) {
  const until = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > until) throw new Error('Background state did not settle');
    await new Promise((resolve) => setImmediate(resolve));
  }
}

test('background keeps login data local to native messages and preserves job state', async (suite) => {
  await suite.test('rejects unsupported or deceptive platform URLs', async () => {
    for (const url of ['https://youtube.com/shorts/1', 'https://facebook.com.evil.test/reel/1', 'https://user:pass@instagram.com/reel/Test/']) {
      assert.throws(() => parseVideoUrl(url));
      const response = await request({ type: 'inspect', url });
      assert.ok(response.error);
    }
    assert.equal(nativeRequests.length, 0);
  });

  await suite.test('passes only the selected platform and profile cookies over native messaging', async () => {
    for (const [domain, url] of [
      ['instagram.com', 'https://instagram.com/reel/Test/'],
      ['facebook.com', 'https://facebook.com/reel/123/'],
      ['tiktok.com', 'https://tiktok.com/@creator/video/123'],
    ]) {
      const response = await request({ type: 'inspect', url, useLogin: true });
      assert.equal(response.ok, true);
      await waitFor(() => stored?.status === 'ready');
      const last = nativeRequests.at(-1);
      assert.equal(last.cookies.length, 1);
      assert.equal(last.cookies[0].domain, `.${domain}`);
      assert.equal(last.cookies[0].value, `dummy-session-${domain}`);
    }
    assert.equal(JSON.stringify(snapshots).includes('dummy-session'), false);
    assert.equal(JSON.stringify(snapshots).includes('must-not-transfer'), false);
  });

  await suite.test('anonymous inspection sends no cookies and removes tracking parameters', async () => {
    await request({ type: 'inspect', url: 'https://instagram.com/reel/Test/?igsh=tracking', useLogin: false });
    await waitFor(() => stored?.status === 'ready');
    assert.deepEqual(nativeRequests.at(-1).cookies, []);
    assert.equal(nativeRequests.at(-1).url, 'https://instagram.com/reel/Test/');
    assert.equal(stored.useLogin, false);
  });

  await suite.test('QuickTime selection reaches the companion and requires a verified result', async () => {
    await request({ type: 'download', url: 'https://instagram.com/reel/Test/', outputMode: 'quicktime', useLogin: false });
    await waitFor(() => stored?.status === 'complete');
    assert.equal(nativeRequests.at(-1).outputMode, 'quicktime');
    assert.equal(stored.outputMode, 'quicktime');
    assert.equal(stored.result.media.quicktimeCompatible, true);
    await request({ type: 'inspect', url: 'https://instagram.com/reel/Test/', useLogin: false });
    await waitFor(() => stored?.status === 'ready');
  });

  await suite.test('a stale companion cannot silently ignore QuickTime mode', async () => {
    supportsQuicktime = false;
    const downloadCount = nativeRequests.filter((r) => r.action === 'download').length;
    await request({ type: 'download', url: 'https://instagram.com/reel/Test/', outputMode: 'quicktime', useLogin: false });
    await waitFor(() => stored?.status === 'error');
    assert.match(stored.error, /companion needs updating/);
    assert.equal(nativeRequests.filter((r) => r.action === 'download').length, downloadCount);
    supportsQuicktime = true;
    await request({ type: 'inspect', url: 'https://instagram.com/reel/Test/', useLogin: false });
    await waitFor(() => stored?.status === 'ready');
  });

  await suite.test('rejects stale downloads and overlapping operations', async () => {
    const stale = await request({ type: 'download', url: 'https://instagram.com/reel/Other/' });
    assert.match(stale.error, /Inspect this video/);
    hold = true;
    await request({ type: 'inspect', url: 'https://instagram.com/reel/Busy/' });
    await waitFor(() => nativeRequests.at(-1).url?.endsWith('/Busy/'));
    const overlap = await request({ type: 'inspect', url: 'https://instagram.com/reel/Second/' });
    assert.match(overlap.error, /already being processed/);
    const held = nativeRequests.at(-1);
    currentPort.onMessage.emit({ id: held.id, type: 'result', data: metadata });
    await waitFor(() => stored.status === 'ready');
  });

  await suite.test('reports companion disconnection instead of leaving an active job stuck', async () => {
    await request({ type: 'download', url: 'https://instagram.com/reel/Busy/', quality: '1920' });
    await waitFor(() => nativeRequests.at(-1).action === 'download');
    assert.equal(nativeRequests.at(-1).quality, '1920');
    chrome.runtime.lastError = { message: 'Native host disconnected' };
    currentPort.onDisconnect.emit();
    delete chrome.runtime.lastError;
    await waitFor(() => stored.status === 'error');
    assert.match(stored.error, /disconnected/);
    assert.equal(stored.helper, null);
    hold = false;
  });
});
