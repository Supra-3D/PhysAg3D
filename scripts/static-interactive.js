/* Shared browser-only Studio for featured examples and every Gallery asset. */
(() => {
  'use strict';
  const dialog = document.getElementById('asset-dialog');
  const host = document.getElementById('explore-frame-host');
  const loading = document.getElementById('explore-loading');
  const label = document.getElementById('explore-loading-text');
  const retry = document.getElementById('explore-retry');
  const featured = {
    camera: 'extra-img_145',
    phone: 'studio-img_020',
    globe: 'extra-img_110',
    ladder: 'extra-img_149',
    carousel: 'extra-img_099',
  };
  let frame = null, trigger = null, galleryItem = null, timeout;
  let savedOverflow = '';
  const findItem = id => (window.PHYSAG3D_GALLERY || []).find(item => item.id === id);

  function removeFrame() {
    frame?.contentWindow?.postMessage({type: 'physag-viewer-dispose'}, location.origin);
    frame?.remove();
    frame = null;
  }
  function showLoadError(message) {
    clearTimeout(timeout);
    loading.hidden = false;
    loading.classList.add('has-error');
    label.textContent = message;
    retry.hidden = false;
    host.setAttribute('aria-busy', 'false');
  }
  function waitForProgress() {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      if (dialog.open && frame && !loading.hidden) {
        showLoadError('The model is taking longer to load. You can keep waiting or retry.');
      }
    }, 90000);
  }
  function launch() {
    if (!galleryItem || !dialog.open) return;
    clearTimeout(timeout);
    removeFrame();
    host.replaceChildren(loading);
    loading.hidden = false;
    loading.classList.remove('has-error');
    retry.hidden = true;
    label.textContent = 'Loading the 3D model and its controls…';
    host.setAttribute('aria-busy', 'true');
    frame = document.createElement('iframe');
    frame.title = `${galleryItem.name} — 3D Studio`;
    frame.src = `viewer/?gallery=${encodeURIComponent(galleryItem.id)}&direct=1&embed=1`;
    frame.allow = 'fullscreen';
    // Keep the frame measurable while the model loads, then reveal its first frame.
    frame.dataset.ready = 'false';
    frame.style.visibility = 'hidden';
    frame.setAttribute('aria-hidden', 'true');
    frame.tabIndex = -1;
    frame.addEventListener('error', event => {
      if (event.currentTarget === frame) showLoadError('The viewer could not open. Please retry.');
    }, {once: true});
    host.append(frame);
    waitForProgress();
  }
  function open(id, button) {
    const item = findItem(id);
    if (!item) return;
    galleryItem = item;
    trigger = button;
    if (!dialog.open) {
      savedOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      dialog.showModal();
    }
    dialog.scrollTop = 0;
    launch();
  }
  document.querySelectorAll('[data-case]').forEach(button => {
    button.addEventListener('click', () => open(featured[button.dataset.case], button));
  });
  document.addEventListener('physag:open-studio', event => {
    open(event.detail?.galleryId, event.detail?.trigger);
  });
  retry.addEventListener('click', launch);
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || !frame || event.source !== frame.contentWindow) return;
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'physag-viewer-close') {
      dialog.close();
      return;
    }
    if (data.type === 'physag-viewer-error' && frame.dataset.ready !== 'true') {
      showLoadError('This model could not be loaded. Please retry.');
    }
    if (data.type === 'physag-viewer-progress' && frame.dataset.ready !== 'true' && dialog.open) {
      if (typeof data.message === 'string' && data.message.trim()) label.textContent = data.message.slice(0, 300);
      loading.hidden = false;
      loading.classList.remove('has-error');
      retry.hidden = true;
      host.setAttribute('aria-busy', 'true');
      waitForProgress();
    }
    if (data.type === 'physag-viewer-ready') {
      clearTimeout(timeout);
      frame.dataset.ready = 'true';
      frame.style.visibility = 'visible';
      frame.removeAttribute('aria-hidden');
      frame.removeAttribute('tabindex');
      loading.hidden = true;
      host.setAttribute('aria-busy', 'false');
      const item = findItem(featured[data.assetId] || data.assetId);
      if (item) {
        galleryItem = item;
        frame.title = `${item.name} — 3D Studio`;
      }
    }
  });
  dialog.addEventListener('close', () => {
    clearTimeout(timeout);
    removeFrame();
    host.replaceChildren(loading);
    host.setAttribute('aria-busy', 'false');
    loading.hidden = true;
    document.body.style.overflow = savedOverflow;
    if (trigger?.isConnected) trigger.focus({preventScroll: true});
  });
})();
