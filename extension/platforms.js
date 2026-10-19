export const PLATFORMS = {
  facebook: { domain: 'facebook.com', label: 'Facebook Reels' },
  instagram: { domain: 'instagram.com', label: 'Instagram Reels' },
  tiktok: { domain: 'tiktok.com', label: 'TikTok' },
};

export function parseVideoUrl(value) {
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error('Paste a valid video link to get started.'); }
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) {
    throw new Error('Use an HTTPS video link from Facebook, Instagram, or TikTok.');
  }
  const platform = Object.keys(PLATFORMS).find((key) => {
    const domain = PLATFORMS[key].domain;
    return url.hostname === domain || url.hostname.endsWith(`.${domain}`);
  });
  if (!platform) throw new Error('Choose a Facebook Reel, Instagram Reel, or TikTok video.');
  const path = url.pathname;
  const videoId = url.searchParams.get('v');
  let query = '';
  if (platform === 'facebook') {
    if (/^\/watch\/?$/.test(path) && /^\d+$/.test(videoId || '')) query = `?v=${videoId}`;
    else if (!/^\/(?:reels?\/\d+|share\/r\/[A-Za-z0-9_-]+)\/?$/.test(path)) {
      throw new Error('Open the Facebook Reel itself and copy its link.');
    }
  } else if (platform === 'instagram') {
    if (!/^\/(?:reels?|p)\/[A-Za-z0-9_-]+\/?$/.test(path)) throw new Error('Copy an individual Instagram Reel link.');
  } else if (!(
    /^\/@[A-Za-z0-9_.-]+\/video\/\d+\/?$/.test(path)
    || (['vm.tiktok.com', 'vt.tiktok.com'].includes(url.hostname) && /^\/[A-Za-z0-9]+\/?$/.test(path))
    || /^\/t\/[A-Za-z0-9]+\/?$/.test(path)
  )) throw new Error('Copy an individual TikTok video link.');
  return { platform, url: `https://${url.hostname}${path}${query}` };
}
