/* Each link resolves to one complete, prebuilt case ZIP from the verified manifest. */
(() => {
  'use strict';
  const manifest = window.PHYSAG3D_DOWNLOAD_MANIFEST;
  const byGalleryId = new Map();
  for (const [caseId, asset] of Object.entries(manifest.assets)) {
    if (!/^img_\d{3}$/.test(caseId) || asset.file !== caseId + '.zip' ||
        !asset.galleryId.endsWith('-' + caseId) || byGalleryId.has(asset.galleryId)) {
      throw new Error('Invalid asset download identity: ' + caseId);
    }
    byGalleryId.set(asset.galleryId, { ...asset, caseId });
  }
  function bind(link, galleryId, expectedCaseId) {
    const asset = byGalleryId.get(galleryId);
    if (!asset || (expectedCaseId && asset.caseId !== expectedCaseId)) {
      link.removeAttribute('href');
      link.removeAttribute('download');
      delete link.dataset.caseId;
      link.setAttribute('aria-disabled', 'true');
      link.tabIndex = -1;
      link.title = 'This asset download is unavailable.';
      return false;
    }
    link.href = manifest.baseUrl + encodeURIComponent(asset.file) + '?download=true';
    link.download = asset.file;
    link.dataset.caseId = asset.caseId;
    link.dataset.galleryId = galleryId;
    link.removeAttribute('aria-disabled');
    link.removeAttribute('tabindex');
    link.setAttribute('aria-label', 'Download complete ' + asset.name + ' ZIP (' + asset.caseId + ')');
    link.title = asset.caseId + ' · Complete ZIP · ' + (asset.bytes / 1024 / 1024).toFixed(1) + ' MB';
    return true;
  }
  window.PHYSAG3D_DOWNLOADS = Object.freeze({ bind });
})();
