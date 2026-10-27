// Fetch the original model bytes from the existing, pinned public asset host.
export const siteRoot = new URL('../', import.meta.url);
export const sourceCommit = '24f4db5cb22791f4059dc74cfdc556778f7a4882';
const mediaRoot = new URL(`https://media.githubusercontent.com/media/Supra-3D/PhysAg3D/${sourceCommit}/website/`);
const binaryAsset = /\.(?:glb|obj|png|jpe?g|webp|mp4)$/i;

export function resourceURL(path, base = siteRoot) {
  if (typeof path !== 'string' || !path) throw new Error('The model resource path is missing.');
  const rooted = path.startsWith('/assets/');
  const url = new URL(rooted ? path.slice(1) : path, rooted ? siteRoot : base);
  if (url.origin === siteRoot.origin && url.pathname.startsWith(siteRoot.pathname + 'assets/')) {
    const assetPath = url.pathname.slice(siteRoot.pathname.length);
    if (binaryAsset.test(url.pathname)) return new URL(assetPath, mediaRoot).href;
    return url.href;
  }
  if (url.origin === mediaRoot.origin && url.pathname.startsWith(mediaRoot.pathname)) return url.href;
  throw new Error('The model resource is outside the published collection.');
}

export async function readResource(path, { base, signal, hash, onProgress = () => {} } = {}) {
  const url = resourceURL(path, base);
  let buffer;
  for (let attempt = 0; attempt < 3; attempt++) {
    signal?.throwIfAborted();
    const controller = new AbortController();
    const abort = () => controller.abort(signal.reason);
    signal?.addEventListener('abort', abort, { once: true });
    let timer;
    const armTimeout = () => {
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(new DOMException('Download timed out', 'TimeoutError')), 90000);
    };
    armTimeout();
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        const error = new Error(`Could not load the model resource (${response.status}).`);
        error.retryable = response.status === 429 || response.status >= 500;
        throw error;
      }
      const length = Number(response.headers.get('Content-Length'));
      if (!response.body) buffer = await response.arrayBuffer();
      else {
        const reader = response.body.getReader(), chunks = [];
        let received = 0, lastProgress = 0;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          armTimeout();
          chunks.push(value); received += value.byteLength;
          if (performance.now() - lastProgress > 250) {
            const mb = (received / 1048576).toFixed(1);
            onProgress(`Loading model data: ${mb} MB${length ? ' / ' + (length / 1048576).toFixed(1) + ' MB' : ''}`);
            lastProgress = performance.now();
          }
        }
        const bytes = new Uint8Array(received);
        let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
        buffer = bytes.buffer;
      }
      break;
    } catch (error) {
      if (signal?.aborted) throw signal.reason;
      if (attempt === 2 || error.retryable === false) throw error;
      onProgress('Reconnecting to the model download…');
      await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
    } finally {
      clearTimeout(timer); signal?.removeEventListener('abort', abort);
    }
  }
  if (typeof hash === 'string' && /^[a-f0-9]{64}$/i.test(hash)) {
    onProgress('Checking model integrity…');
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer)), x => x.toString(16).padStart(2, '0')).join('');
    if (digest !== hash.toLowerCase()) throw new Error('The model and its motion data do not match.');
  }
  signal?.throwIfAborted();
  return buffer;
}
