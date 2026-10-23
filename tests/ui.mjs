import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

// This checks the real popup code with a simulated Chrome API. It does not claim
// extension installation, permissions, or privileged/native browser integration.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extension = path.join(root, 'extension');
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript' };
const server = http.createServer(async (request, response) => {
  try {
    const name = path.basename(new URL(request.url, 'http://localhost').pathname);
    const body = await fs.readFile(path.join(extension, name || 'popup.html'));
    response.writeHead(200, { 'Content-Type': mime[path.extname(name)] || 'text/plain' });
    response.end(body);
  } catch { response.writeHead(404).end(); }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 440, height: 900 }, deviceScaleFactor: 2 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const testPlatform = process.env.TEST_PLATFORM || 'mac';
  await page.addInitScript((platform) => {
    const listeners = [];
    const requests = [];
    const initial = { status: 'idle', url: '', useLogin: true, helper: null, metadata: null, progress: null, result: null, error: null };
    let state = { ...initial };
    const emit = (patch) => {
      state = { ...state, ...patch };
      listeners.forEach((listener) => listener({ type: 'state', state }));
    };
    const metadata = {
      title: 'Small moments, big memories.', creator: '@personal.library', platform: 'instagram',
      duration: 25, thumbnail: null, heights: [1920, 1280], maxHeight: 1920,
      qualities: [{ value: '1920', label: '1080 × 1920' }, { value: '1280', label: '720 × 1280' }],
      quicktime: { available: true, qualities: [{ value: '1280', label: '720 × 1280' }] },
    };
    globalThis.testHarness = { emit, requests, metadata };
    globalThis.chrome = {
      tabs: { query: async () => [{ id: 1, url: 'https://www.instagram.com/reel/Fixture/?igsh=tracking' }] },
      runtime: {
        getPlatformInfo: async () => ({ os: platform }),
        onMessage: { addListener: (listener) => listeners.push(listener) },
        sendMessage: async (message) => {
          requests.push(message);
          if (message.type === 'getState') return { state, extensionId: 'a'.repeat(32) };
          if (message.type === 'connect') throw new Error('Install the local companion for this extension ID, then select Reconnect.');
          if (message.type === 'inspect') {
            emit({ status: 'inspecting', url: message.url, useLogin: message.useLogin });
            setTimeout(() => emit({ status: 'ready', metadata }), 50);
          }
          if (message.type === 'download') {
            emit({ status: 'downloading', outputMode: message.outputMode, progress: { stage: 'downloading', percent: 41, downloaded: 4e6, total: 10e6, speed: 2e6, eta: 3 } });
          }
          if (message.type === 'cancel') emit({ status: 'error', progress: null, error: 'Cancelled. Partial media files can be resumed by downloading again.' });
          return { ok: true };
        },
      },
    };
  }, testPlatform);
  await page.goto(`http://127.0.0.1:${server.address().port}/popup.html`);
  await page.waitForFunction(() => document.getElementById('setup').open);
  assert.equal(await page.locator('#video-url').inputValue(), 'https://www.instagram.com/reel/Fixture/');
  assert.match(await page.locator('#install-command').innerText(), /a{32}/);
  assert.equal(await page.locator('#use-login').isChecked(), true);
  assert.match(await page.locator('#device-name').innerText(), testPlatform === 'win' ? /your PC/ : /your Mac/);
  if (testPlatform === 'win') {
    assert.match(await page.locator('#install-command').innerText(), /^py -3 /);
    assert.match(await page.locator('#prerequisite-command').innerText(), /winget install/);
    assert.equal(await page.locator('#open-folder').innerText(), 'Show in Explorer');
    assert.match(await page.locator('#playback option[value=quicktime]').innerText(), /Media Player/);
  }
  console.log('PASS: Current tab normalization, login default, and actionable companion setup.');

  await page.locator('#setup summary').click();
  await page.locator('#video-url').fill('https://www.youtube.com/shorts/123');
  await page.locator('#inspect').click();
  assert.match(await page.locator('#error').innerText(), /Facebook Reel, Instagram Reel, or TikTok/);
  const earlyRequests = await page.evaluate(() => testHarness.requests);
  assert.equal(earlyRequests.filter((request) => request.type === 'inspect').length, 0);
  console.log('PASS: Unsupported platform rejected before requesting extraction.');

  await page.locator('#video-url').fill('https://www.instagram.com/reel/Fixture/?igsh=tracking');
  await page.locator('#use-login').uncheck();
  await page.locator('#inspect').click();
  await page.waitForFunction(() => !document.getElementById('video-card').hidden);
  assert.equal(await page.locator('#quality').inputValue(), 'best');
  assert.equal(await page.locator('#quality option').count(), 3);
  assert.equal(await page.locator('#max-quality').innerText(), '1080 × 1920');
  const inspection = await page.evaluate(() => testHarness.requests.find((request) => request.type === 'inspect'));
  assert.equal(inspection.useLogin, false);
  assert.equal(inspection.url, 'https://www.instagram.com/reel/Fixture/');
  console.log('PASS: Inspect wiring, anonymous option, portrait dimensions, highest-quality default.');

  await page.evaluate(() => testHarness.emit({ metadata: { ...testHarness.metadata, title: '<img src=x onerror=alert(1)> unsafe title' } }));
  assert.equal(await page.locator('#video-title img').count(), 0);
  assert.match(await page.locator('#video-title').innerText(), /<img/);
  await page.evaluate(() => testHarness.emit({ metadata: testHarness.metadata, helper: { extractorVersion: '2026.8.19', ffmpeg: true }, useLogin: true }));
  await fs.mkdir(path.join(root, '.test-artifacts'), { recursive: true });
  await page.screenshot({ path: path.join(root, '.test-artifacts/extension-ready.png'), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  assert.equal(overflow, false);
  console.log('PASS: Title escaping and popup layout without horizontal overflow.');

  await page.locator('#playback').selectOption('quicktime');
  assert.equal(await page.locator('#quality option').count(), 2);
  assert.equal(await page.locator('#max-quality').innerText(), '720 × 1280');
  assert.match(await page.locator('#playback-note').innerText(), /Resolution may be lower/);
  await page.evaluate(() => testHarness.emit({ metadata: { ...testHarness.metadata, quicktime: { available: false, qualities: [] } } }));
  assert.equal(await page.locator('#download').isDisabled(), true);
  assert.match(await page.locator('#playback-note').innerText(), /No H.264\/AAC source/);
  await page.evaluate(() => testHarness.emit({ metadata: testHarness.metadata }));
  assert.equal(await page.locator('#download').isEnabled(), true);
  console.log('PASS: QuickTime sources show their actual resolution and unavailable compatible sources cannot download.');

  await page.locator('#quality').selectOption('1280');
  await page.locator('#download').click();
  assert.equal(await page.locator('#video-url').isDisabled(), true);
  assert.equal(await page.locator('#download').isDisabled(), true);
  assert.equal(await page.locator('#progress').getAttribute('value'), '41');
  const download = await page.evaluate(() => testHarness.requests.find((request) => request.type === 'download'));
  assert.equal(download.quality, '1280');
  assert.equal(download.outputMode, 'quicktime');
  await page.locator('#cancel').click();
  assert.match(await page.locator('#error').innerText(), /Cancelled/);
  console.log('PASS: Selected quality, progress, busy controls, and cancellation wiring.');

  await page.evaluate(() => testHarness.emit({ status: 'complete', error: null, result: { filename: 'A memory [123].mp4', media: { videoCodec: 'av1', audioCodec: 'aac', width: 1080, height: 1920, quicktimeCompatible: false } } }));
  assert.equal(await page.locator('#success').isVisible(), true);
  assert.equal(await page.locator('#filename').innerText(), 'A memory [123].mp4');
  assert.match(await page.locator('#media-details').innerText(), /AV1/);
  assert.equal(await page.locator('#compatibility-warning').isVisible(), true);
  assert.match(await page.locator('#compatibility-warning').innerText(), /QuickTime may play only audio|may need a video codec/);
  await page.locator('#open-folder').click();
  assert.equal(await page.evaluate(() => testHarness.requests.some((r) => r.type === 'openFolder')), true);
  await page.locator('#video-url').fill('https://www.tiktok.com/@creator/video/123');
  assert.equal(await page.locator('#video-card').isVisible(), false);
  console.log('PASS: Completion, Finder action, and invalidation after editing the link.');
  assert.deepEqual(errors, []);
  console.log('All browser UI checks passed (Chrome API simulated).');
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
