import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { chromium } from 'playwright';
import { parseVideoUrl } from '../extension/platforms.js';

if (process.platform !== 'linux') {
  throw new Error('The isolated native Chrome test currently requires Linux. Run npm run test:browser for the cross-platform UI suite, and follow the documented native Chrome acceptance checks on Windows/macOS.');
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = path.join(root, '.test-artifacts');
await fs.mkdir(artifacts, { recursive: true });
const runDir = await fs.mkdtemp(path.join(artifacts, 'browser-'));
const configDir = path.join(runDir, 'config');
const extensionDir = path.join(root, 'extension');
const context = await chromium.launchPersistentContext(path.join(runDir, 'profile'), {
  headless: true,
  executablePath: process.env.CHROMIUM_PATH || undefined,
  ignoreDefaultArgs: ['--disable-extensions'],
  args: ['--enable-unsafe-extension-debugging', `--disable-extensions-except=${extensionDir}`, `--load-extension=${extensionDir}`],
  env: { ...process.env, XDG_CONFIG_HOME: configDir },
});
context.setDefaultTimeout(15000);

const errors = [];
try {
  const cdp = await context.browser().newBrowserCDPSession();
  await cdp.send('Extensions.loadUnpacked', { path: extensionDir });
  await cdp.detach();
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent('serviceworker');
  const extensionId = new URL(worker.url()).host;
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await page.waitForFunction(() => document.getElementById('setup').open);
  assert.match(await page.locator('#companion-title').innerText(), /companion needed/);
  assert.match(await page.locator('#install-command').innerText(), new RegExp(extensionId));
  console.log('PASS: Extension loads with actionable missing-companion setup.');

  const registration = spawnSync(path.join(root, '.venv/bin/python'), [
    path.join(root, 'scripts/install_companion.py'), '--extension-id', extensionId,
    '--manifest-dir', path.join(configDir, 'chromium/NativeMessagingHosts'), '--skip-deps',
  ], { cwd: root, encoding: 'utf8' });
  assert.equal(registration.status, 0, registration.stderr);
  await page.locator('#reconnect').click();
  await page.waitForFunction(() => document.getElementById('companion').classList.contains('connected'));
  assert.match(await page.locator('#companion-detail').innerText(), /FFmpeg ready/);
  console.log('PASS: Real Chromium → native messaging → Python → FFmpeg health check.');

  // Inject only sanitized UI state. Native media processing is tested separately.
  const fixture = {
    status: 'ready', url: 'https://www.instagram.com/reel/Fixture/', useLogin: true,
    helper: { extractorVersion: 'fixture', ffmpeg: true }, progress: null, result: null, error: null,
    metadata: {
      title: '<img src=x onerror=alert(1)> A moment worth keeping', creator: 'Personal library',
      platform: 'instagram', duration: 25, thumbnail: null, heights: [1920, 1280],
      maxHeight: 1920, qualities: [{ value: '1920', label: '1080 × 1920' }, { value: '1280', label: '720 × 1280' }],
    },
  };
  await worker.evaluate(async (state) => {
    await chrome.storage.session.set({ state });
    await chrome.runtime.sendMessage({ type: 'state', state }).catch(() => {});
  }, fixture);
  await page.waitForFunction(() => !document.getElementById('video-card').hidden);
  assert.equal(await page.locator('#video-title img').count(), 0, 'Video title must be rendered as text');
  assert.equal(await page.locator('#quality option').count(), 3);
  assert.equal(await page.locator('#quality').inputValue(), 'best');
  assert.equal(await page.locator('#max-quality').innerText(), '1080 × 1920');
  assert.equal(await page.locator('#thumbnail').getAttribute('src'), null);
  console.log('PASS: Metadata, portrait quality choices, highest-quality default, and title escaping.');

  fixture.metadata.title = 'Small moments, big memories.';
  await worker.evaluate(async (state) => {
    await chrome.runtime.sendMessage({ type: 'state', state }).catch(() => {});
  }, fixture);
  await page.waitForFunction(() => document.getElementById('video-title').textContent === 'Small moments, big memories.');
  await page.screenshot({ path: path.join(artifacts, 'extension-ready.png'), fullPage: true });

  await page.locator('#video-url').fill('https://www.tiktok.com/@creator/video/123');
  assert.equal(await page.locator('#video-card').isVisible(), false);
  console.log('PASS: Editing the link invalidates the old video selection.');

  await page.locator('#video-url').fill('https://www.youtube.com/shorts/123');
  await page.locator('#inspect').click();
  assert.match(await page.locator('#error').innerText(), /Facebook Reel, Instagram Reel, or TikTok/);
  console.log('PASS: Unsupported platforms are rejected before native extraction.');

  for (const url of ['https://facebook.com.evil.test/reel/123', 'https://user:pass@instagram.com/reel/Test/', 'http://tiktok.com/@user/video/123']) {
    assert.throws(() => parseVideoUrl(url));
  }
  assert.equal(parseVideoUrl('https://instagram.com/reel/Test/?igsh=secret').url, 'https://instagram.com/reel/Test/');
  console.log('PASS: JavaScript URL trust boundaries and tracking removal.');

  assert.deepEqual(errors, [], 'No uncaught popup errors');
  console.log('All browser checks passed. Screenshot: .test-artifacts/extension-ready.png');
} finally {
  await context.close();
  await fs.rm(runDir, { recursive: true, force: true });
}
