/* Static release: open recorded demonstrations without starting the physics API. */
(() => {
  'use strict';
  const featured = {
    camera: ['extra-img_145', 'camera-studio-20261023'],
    phone: ['studio-img_020', 'trifold-studio-20261023'],
    globe: ['extra-img_110', 'globe-studio-20261023'],
    ladder: ['extra-img_149', 'ladder-studio-20261023'],
    carousel: ['extra-img_099', 'carousel-studio-20261023'],
  };
  function openDemo(id, trigger) {
    const original = (window.PHYSAG3D_GALLERY || []).find(item => item.id === id);
    if (!original) return;
    const feature = Object.entries(featured).find(([, value]) => value[0] === id);
    let item = original;
    if (feature) {
      const [key, [, clip]] = feature;
      item = {
        ...original,
        id: 'hero-' + key,
        video: window.PHYSAG3D_ASSET_URL(`assets/hero/${clip}.mp4`),
        poster: window.PHYSAG3D_ASSET_URL(`assets/hero/${clip}-poster.webp`),
        videoLabel: 'Recorded demonstration',
        defaultView: 'orbit',
        interaction: null,
      };
    }
    document.dispatchEvent(new CustomEvent('physag:open-feature', { detail: { item, trigger } }));
  }
  document.querySelectorAll('[data-case]').forEach(button => {
    button.addEventListener('click', () => openDemo(featured[button.dataset.case]?.[0], button));
  });
  document.addEventListener('physag:open-studio', event => {
    openDemo(event.detail?.galleryId, event.detail?.trigger);
  });
})();
