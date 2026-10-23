import { parseVideoUrl, PLATFORMS } from './platforms.js';

const $ = (id) => document.getElementById(id);
let state;
let dirty = false;
let metadataKey = '';
let operatingSystem = 'mac';
let deviceName = 'your Mac';

function configurePlatform(os, extensionId) {
  operatingSystem = os;
  deviceName = os === 'win' ? 'your PC' : os === 'mac' ? 'your Mac' : 'your computer';
  $('device-name').textContent = deviceName;
  $('setup-title').textContent = `First time? Connect ${deviceName}`;
  $('companion-icon').textContent = os === 'mac' ? '⌘' : 'PC';
  $('open-folder').textContent = os === 'win' ? 'Show in Explorer' : os === 'mac' ? 'Show in Finder' : 'Open folder';
  $('playback').options[1].textContent = os === 'win' ? 'Media Player · H.264 + AAC' : os === 'mac' ? 'QuickTime / Finder · H.264 + AAC' : 'Compatible player · H.264 + AAC';
  $('prerequisite-command').textContent = os === 'win'
    ? 'winget install --id Python.Python.3.12 --exact --source winget\nwinget install --id Gyan.FFmpeg --exact --source winget'
    : os === 'mac' ? 'brew install python ffmpeg' : 'Install Python 3.11+, FFmpeg and FFprobe with your system package manager.';
  const python = os === 'win' ? 'py -3' : 'python3';
  $('install-command').textContent = `${python} scripts/install_companion.py --extension-id ${extensionId}`;
  $('setup-help').textContent = os === 'win'
    ? 'You can also run Install-Windows.bat in the project folder. Keep that folder in place. See WINDOWS.md for the full Windows guide.'
    : 'The companion runs only on your computer. Keep the project folder in place. See README.md for complete instructions.';
}

async function send(type, data = {}) {
  const response = await chrome.runtime.sendMessage({ type, ...data });
  if (response?.error) throw new Error(response.error);
  return response;
}

function showError(error) {
  $('error').textContent = error.message;
  $('error').hidden = false;
}

function displayBytes(bytes) {
  if (!Number.isFinite(bytes)) return '';
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
}

function render(next) {
  state = next;
  const working = ['inspecting', 'downloading'].includes(state.status);
  if (working) $('playback').value = state.outputMode || 'original';
  $('playback').disabled = working;
  document.body.classList.toggle('has-video', !!state.metadata && !dirty);
  if (!dirty && state.url) $('video-url').value = state.url;
  $('use-login').checked = state.useLogin;
  $('use-login').disabled = working;
  $('video-url').disabled = working;
  $('current-tab').disabled = working;
  $('inspect').disabled = working;
  $('inspect').firstElementChild.textContent = state.status === 'inspecting' ? 'Finding the original…' : 'Find video';
  $('video-card').hidden = !state.metadata || dirty;
  if (state.metadata) {
    const metadata = state.metadata;
    $('video-title').textContent = metadata.title;
    $('video-platform').textContent = PLATFORMS[metadata.platform]?.label || metadata.platform;
    const duration = Number.isFinite(metadata.duration) ? ` · ${Math.floor(metadata.duration / 60)}:${String(Math.floor(metadata.duration % 60)).padStart(2, '0')}` : '';
    $('video-creator').textContent = metadata.creator + duration;
    const quicktime = $('playback').value === 'quicktime';
    const choices = quicktime ? metadata.quicktime?.qualities || [] : metadata.qualities || [];
    const unavailable = quicktime && !metadata.quicktime?.available;
    $('max-quality').textContent = choices.length ? choices[0].label : 'SOURCE QUALITY';
    $('playback-note').textContent = !quicktime
      ? 'Original codecs preserved. Use VLC if your video player cannot show the picture.'
      : !metadata.quicktime ? 'Update the companion files, reload Instant, and inspect again to see QuickTime sources.'
        : unavailable ? 'No H.264/AAC source is offered. Use Original quality with VLC.'
        : 'Best H.264/AAC source. Resolution may be lower than Original quality. No re-encoding.';
    const key = `${state.url}|${quicktime}|${JSON.stringify(choices)}`;
    if (key !== metadataKey) {
      metadataKey = key;
      $('quality').replaceChildren(new Option(quicktime ? 'Best compatible H.264 / AAC source' : 'Highest available · recommended', 'best'));
      for (const quality of choices) $('quality').add(new Option(`Up to ${quality.label}`, quality.value));
      $('thumbnail-wrap').classList.remove('has-image');
      $('thumbnail').removeAttribute('src');
      if (metadata.thumbnail) $('thumbnail').src = metadata.thumbnail;
    }
    $('quality').disabled = working || unavailable;
    $('download').disabled = working || dirty || unavailable;
  }
  $('activity').hidden = !working;
  if (working) {
    const progress = state.progress || {};
    $('activity-text').textContent = progress.stage === 'verifying' ? 'Verifying video and audio tracks…' : progress.stage === 'processing' ? 'Finishing original streams…' : progress.stage === 'downloading' ? 'Downloading original media…' : 'Finding available streams…';
    if (Number.isFinite(progress.percent)) $('progress').value = progress.percent;
    else $('progress').removeAttribute('value');
    const details = [];
    if (progress.downloaded) details.push(`${displayBytes(progress.downloaded)}${progress.total ? ` / ${displayBytes(progress.total)}` : ''}`);
    if (progress.speed) details.push(`${displayBytes(progress.speed)}/s`);
    if (Number.isFinite(progress.eta)) details.push(`${Math.ceil(progress.eta)}s left`);
    $('progress-detail').textContent = details.join(' · ') || 'Processing locally on your machine';
  }
  $('success').hidden = state.status !== 'complete' || dirty;
  if (state.result) {
    $('filename').textContent = state.result.filename;
    const media = state.result.media;
    $('media-details').textContent = media ? `${media.width} × ${media.height} · ${media.videoCodec?.toUpperCase()}${media.audioCodec ? ` + ${media.audioCodec.toUpperCase()}` : ' · no audio track'}` : '';
    $('compatibility-warning').hidden = !media || media.quicktimeCompatible;
    $('compatibility-warning').textContent = media && !media.quicktimeCompatible
      ? operatingSystem === 'mac' ? 'QuickTime may play only audio with these source codecs. Open in VLC/IINA or select QuickTime playback above.'
        : 'Your video player may need a video codec for this source. Open in VLC or select compatible H.264/AAC playback above.' : '';
  }
  $('error').hidden = !state.error;
  $('error').textContent = state.error || '';
  $('companion').classList.toggle('connected', !!state.helper);
  $('companion-title').textContent = state.helper ? 'Local companion connected' : 'Local companion needed';
  $('companion-detail').textContent = state.helper ? `FFmpeg ready · companion ${state.helper.version || 'older version'}` : `One quick setup. Everything stays on ${deviceName}.`;
  highlightPlatform();
}

function highlightPlatform() {
  let platform;
  try { platform = parseVideoUrl($('video-url').value).platform; } catch { /* Incomplete input. */ }
  for (const element of document.querySelectorAll('[data-platform]')) element.classList.toggle('active', element.dataset.platform === platform);
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    const parsed = parseVideoUrl(tab?.url || '');
    $('video-url').value = parsed.url;
    dirty = state?.url !== parsed.url;
    if (state) render(state);
  } catch { throw new Error('Open a Facebook Reel, Instagram Reel, or TikTok video in the current tab.'); }
}

async function reconnect() {
  $('reconnect').disabled = true;
  $('companion-title').textContent = `Connecting to ${deviceName}…`;
  try {
    await send('connect');
    $('setup').open = false;
  } catch (error) {
    $('companion-title').textContent = 'Local companion needed';
    $('companion-detail').textContent = error.message;
    $('setup').open = true;
  } finally { $('reconnect').disabled = false; }
}

$('thumbnail').addEventListener('load', () => $('thumbnail-wrap').classList.add('has-image'));
$('thumbnail').addEventListener('error', () => $('thumbnail-wrap').classList.remove('has-image'));
$('video-url').addEventListener('input', () => {
  dirty = true;
  document.body.classList.remove('has-video');
  $('download').disabled = true;
  $('video-card').hidden = true;
  $('success').hidden = true;
  $('error').hidden = true;
  highlightPlatform();
});
$('source-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const parsed = parseVideoUrl($('video-url').value);
    dirty = false;
    await send('inspect', { url: parsed.url, useLogin: $('use-login').checked });
  } catch (error) { showError(error); }
});
$('download').addEventListener('click', async () => {
  try { await send('download', { url: $('video-url').value, quality: $('quality').value, useLogin: $('use-login').checked, outputMode: $('playback').value }); }
  catch (error) { showError(error); }
});
$('playback').addEventListener('change', () => { if (state) render(state); });
$('current-tab').addEventListener('click', () => currentTab().catch(showError));
$('reconnect').addEventListener('click', reconnect);
$('cancel').addEventListener('click', async () => {
  try {
    await send('cancel');
    $('activity-text').textContent = 'Cancelling after the current operation…';
  } catch (error) { showError(error); }
});
$('open-folder').addEventListener('click', () => send('openFolder').catch(showError));
$('copy-command').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('install-command').textContent);
    $('copy-command').textContent = 'Copied';
  } catch { $('copy-command').textContent = 'Select and copy the command above'; }
});
chrome.runtime.onMessage.addListener((message) => { if (message.type === 'state') render(message.state); });

try {
  const initial = await send('getState');
  const platform = await chrome.runtime.getPlatformInfo();
  configurePlatform(platform.os, initial.extensionId);
  $('playback').value = initial.state.outputMode || 'original';
  render(initial.state);
  if (!initial.state.url) await currentTab().catch(() => {});
  await reconnect();
} catch (error) { showError(error); }
