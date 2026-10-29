/* Shared Studio entry for the five featured assets and the full Gallery. */
(() => {
  'use strict';
  const dialog = document.getElementById('asset-dialog');
  const host = document.getElementById('explore-frame-host');
  const loading = document.getElementById('explore-loading');
  const label = document.getElementById('explore-loading-text');
  const retry = document.getElementById('explore-retry');
  const assets = new Set(['camera', 'phone', 'globe', 'ladder', 'carousel']);
  const nativeGallery = new Map([
    ['extra-img_145', 'camera'], ['studio-img_020', 'phone'],
    ['extra-img_110', 'globe'], ['extra-img_149', 'ladder'], ['extra-img_099', 'carousel'],
  ]);
  let frame = null, trigger = null, currentAsset = 'camera', timeout;
  let mode = 'native', galleryItem = null;
  let savedOverflow = '';
  function showLoadError(message) {
    clearTimeout(timeout);
    loading.hidden = false;
    loading.classList.add('has-error');
    label.textContent = message;
    retry.hidden = false;
    host.setAttribute('aria-busy', 'false');
  }
  function launch() {
    clearTimeout(timeout);
    frame?.remove();
    host.replaceChildren(loading);
    loading.hidden = false;
    loading.classList.remove('has-error');
    retry.hidden = true;
    label.textContent = 'Preparing the 3D viewer…';
    host.setAttribute('aria-busy', 'true');
    frame = document.createElement('iframe');
    frame.title = galleryItem ? `${galleryItem.name} — 3D Studio` : 'PhysAg3D live 3D asset viewer';
    frame.src = `viewer/?embed=1&${mode === 'gallery' ? 'gallery' : 'asset'}=${encodeURIComponent(currentAsset)}&direct=1&v=soft-contact-20261030`;
    frame.allow = 'fullscreen';
    // Loading the document is earlier than initializing the viewer and its model.
    // Keep it measurable but concealed until the first model frame is ready.
    frame.dataset.ready = 'false';
    frame.style.visibility = 'hidden';
    frame.setAttribute('aria-hidden', 'true');
    frame.tabIndex = -1;
    frame.addEventListener('error', event => {
      if (event.currentTarget === frame) showLoadError('The viewer could not open. Please retry.');
    }, {once:true});
    host.append(frame);
    timeout = setTimeout(() => {
      if (!dialog.open || !frame) return;
      if (!loading.hidden) {
        showLoadError('The viewer is taking longer to open. Please retry.');
      }
    }, 20000);
  }
  function open(asset, button, item = null) {
    if (!item && !assets.has(asset)) return;
    currentAsset = asset;
    galleryItem = item;
    mode = item && !assets.has(asset) ? 'gallery' : 'native';
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
    button.addEventListener('click', () => open(button.dataset.case, button));
  });
  document.addEventListener('physag:open-studio', event => {
    const id = event.detail?.galleryId;
    const item = (window.PHYSAG3D_GALLERY || []).find(entry => entry.id === id);
    if (!item) return;
    open(nativeGallery.get(id) || id, event.detail.trigger, item);
  });
  retry.addEventListener('click', launch);
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || !frame || event.source !== frame.contentWindow) return;
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'physag-viewer-close') dialog.close();
    if (data.type === 'physag-viewer-error' && frame.dataset.ready !== 'true') {
      showLoadError('This asset could not be loaded. Please retry.');
    }
    if (data.type === 'physag-viewer-ready') {
      clearTimeout(timeout);
      frame.dataset.ready = 'true';
      frame.style.visibility = 'visible';
      frame.removeAttribute('aria-hidden');
      frame.removeAttribute('tabindex');
      loading.hidden = true;
      host.setAttribute('aria-busy', 'false');
      if (assets.has(data.assetId)) {
        currentAsset = data.assetId;
        mode = 'native';
        if (galleryItem) {
          const match = [...nativeGallery].find(([, id]) => id === data.assetId);
          galleryItem = (window.PHYSAG3D_GALLERY || []).find(item => item.id === match?.[0]) || galleryItem;
        }
      } else {
        const item = (window.PHYSAG3D_GALLERY || []).find(entry => entry.id === data.assetId);
        if (item) { currentAsset = item.id; galleryItem = item; mode = 'gallery'; }
      }
    }
  });
  dialog.addEventListener('close', () => {
    clearTimeout(timeout);
    // The embedded page deletes its simulation session on pagehide.
    frame?.remove();
    frame = null;
    host.replaceChildren(loading);
    host.setAttribute('aria-busy', 'false');
    loading.hidden = true;
    document.body.style.overflow = savedOverflow;
    if (trigger?.isConnected) trigger.focus({preventScroll:true});
  });
})();
