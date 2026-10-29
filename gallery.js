/* Preview original clips on hover; open each asset in the shared 3D Studio. */
(() => {
  'use strict';
  const items = (window.PHYSAG3D_GALLERY || []).filter(item => !["img_020", "img_099", "img_110", "img_145", "img_149"].includes(item.caseId));
  const labels = {"furniture":"Furniture & bedding","fixtures":"Doors & fixtures","appliances":"Appliances & lighting","electronics":"Electronics","kitchen":"Kitchenware","tools":"Tools & stationery","vehicles":"Vehicles & robotics","leisure":"Sports & leisure","personal":"Personal & household"};
  const categoryText = item => labels[item.category];
  const grid = document.getElementById('asset-grid');
  const search = document.getElementById('asset-search');
  const onlyNew = document.getElementById('gallery-new-only');
  const more = document.getElementById('gallery-more');
  const dialog = document.getElementById('gallery-dialog');
  const player = document.getElementById('gallery-video');
  const interact = document.getElementById('gallery-interact');
  const featureIds = {'hero-camera':'extra-img_145','hero-trifold':'studio-img_020','hero-globe':'extra-img_110','hero-ladder':'extra-img_149','hero-carousel':'extra-img_099'};
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let category='all', limit=12, selected=null, lastFocus=null, hoverVideo=null;
  const button = (text, className) => { const b=document.createElement('button'); b.type='button'; b.textContent=text; if(className)b.className=className; return b; };
  function stopPreviews(){grid.querySelectorAll('video').forEach(v=>v.pause());hoverVideo=null;}
  function preview(v){
    if(reducedMotion.matches || dialog.open || document.getElementById('asset-dialog').open)return;
    if(hoverVideo && hoverVideo!==v)hoverVideo.pause();
    hoverVideo=v;
    if(!v.getAttribute('src'))v.src=v.dataset.src;
    v.play().catch(()=>{});
  }
  const observer = new IntersectionObserver(entries=>entries.forEach(e=>{if(!e.isIntersecting)e.target.pause();}),{threshold:0.05});
  function card(item){
    const article=document.createElement('article');article.className='gallery-card';
    const previewFrame=document.createElement('div');previewFrame.className='gallery-card-preview';
    const media=document.createElement('div');media.className='gallery-card-media';
    const video=document.createElement('video');video.poster=item.previewPoster||item.poster;video.dataset.src=item.defaultView==='interaction'?item.interaction:item.video;video.muted=true;video.loop=true;video.playsInline=true;video.preload='none';video.setAttribute('aria-hidden','true');video.tabIndex=-1;
    if(item.previewFit==='contain'){video.style.objectFit='contain';media.style.background='#172830';}
    const launch=button('Interact ↗', 'gallery-interact');
    launch.dataset.galleryId=item.id;
    launch.setAttribute('aria-label','Interact in 3D with '+item.name);
    launch.setAttribute('aria-haspopup','dialog');launch.setAttribute('aria-controls','asset-dialog');
    const download=button('Download ↓', 'gallery-download');download.disabled=true;
    download.dataset.galleryId=item.id;
    download.setAttribute('aria-label','Download '+item.name);
    const actions=document.createElement('div');actions.className='gallery-card-actions';actions.append(launch,download);
    const copy=document.createElement('div');copy.className='gallery-card-copy';
    const info=document.createElement('div');info.className='gallery-card-info';
    const name=document.createElement('strong');name.textContent=item.name;
    const detail=document.createElement('span');detail.textContent=categoryText(item);
    copy.append(name,detail);info.append(copy,actions);media.append(video);previewFrame.append(media,info);article.append(previewFrame);
    article.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')preview(video);});
    article.addEventListener('pointerleave',()=>video.pause());
    launch.addEventListener('focus',()=>preview(video));launch.addEventListener('blur',()=>video.pause());
    launch.addEventListener('click',()=>{
      stopPreviews();
      document.dispatchEvent(new CustomEvent('physag:open-studio',{detail:{galleryId:item.id,trigger:launch}}));
    });observer.observe(video);
    return article;
  }
  function render(resetFocus=false){
    stopPreviews();observer.disconnect();
    const query=search.value.trim().toLowerCase();
    const matches=items.filter(x=>(category==='all'||x.category===category)&&(!onlyNew.checked||x.newInGallery)&&(!query||([x.name,x.nameZh,x.caseId,x.id,x.description,categoryText(x),...(x.tags||[])].filter(Boolean).join(' ')).toLowerCase().includes(query)));
    grid.replaceChildren(...matches.slice(0,limit).map(card));
    document.getElementById('gallery-count').textContent=`Showing ${Math.min(limit,matches.length)} of ${matches.length} assets`;
    document.getElementById('gallery-empty').hidden=matches.length!==0;
    more.hidden=limit>=matches.length;
    if(resetFocus){const first=grid.querySelectorAll('.gallery-interact')[Math.max(0,limit-12)];if(first)first.focus({preventScroll:true});}
  }
  document.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=b.dataset.category;limit=12;document.querySelectorAll('[data-category]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));render();}));
  search.addEventListener('input',()=>{limit=12;render();});
  onlyNew.addEventListener('change',()=>{limit=12;render();});
  more.addEventListener('click',()=>{limit+=12;render(true);});
  document.getElementById('gallery-reset').addEventListener('click',()=>{search.value='';onlyNew.checked=false;document.querySelector('[data-category="all"]').click();search.focus();});
  function setView(view,autoplay=true){
    const src=view==='interaction'?selected.interaction:selected.video;
    player.pause();player.poster=view==='interaction'?(selected.previewPoster||selected.poster):selected.poster;player.src=src;player.load();
    document.querySelectorAll('[data-video-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.videoView===view)));
    const download=document.getElementById('gallery-download');download.href=src;download.download=selected.name.toLowerCase().replace(/[^a-z0-9]+/g,'-')+'-'+view+'.mp4';
    if(autoplay)player.play().catch(()=>{});
  }
  function openAsset(item,trigger){
    selected=item;lastFocus=trigger;stopPreviews();
    interact.dataset.galleryId=featureIds[item.id]||item.id;
    interact.hidden=!(window.PHYSAG3D_GALLERY||[]).some(asset=>asset.id===interact.dataset.galleryId);
    document.getElementById('gallery-asset-download').hidden=interact.hidden;
    interact.setAttribute('aria-label','Interact in 3D with '+item.name);
    const featured=Boolean(item.id && item.id.startsWith('hero-'));dialog.classList.toggle('focus-film',featured);document.querySelector('[data-video-view=orbit]').textContent=item.videoLabel||(featured?'Mechanism close-ups':'Studio orbit');
    document.getElementById('gallery-dialog-title').textContent=item.name;
    document.getElementById('gallery-dialog-category').textContent=categoryText(item);
    document.getElementById('gallery-dialog-description').textContent=item.description;
    document.getElementById('gallery-dialog-note').textContent=item.note;
    const inputPanel=document.getElementById('gallery-input-panel');inputPanel.hidden=!item.input;
    const input=document.getElementById('gallery-input');if(item.input){input.src=item.input;input.alt='Input image for '+item.name;}else input.removeAttribute('src');
    dialog.classList.toggle('with-input',Boolean(item.input));
    const interactionButton=document.querySelector('[data-video-view="interaction"]');
    interactionButton.hidden=!item.interaction;interactionButton.textContent=item.interactionLabel||'Interaction clip';
    dialog.showModal();setView(item.defaultView||'orbit',!reducedMotion.matches);
  }
  interact.addEventListener('click',()=>{
    const galleryId=interact.dataset.galleryId, trigger=lastFocus;
    dialog.close();
    document.dispatchEvent(new CustomEvent('physag:open-studio',{detail:{galleryId,trigger}}));
  });
  document.querySelectorAll('[data-video-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.videoView)));
  document.querySelector('.gallery-dialog-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>{player.pause();player.removeAttribute('src');player.load();if(lastFocus?.isConnected&&!document.getElementById('asset-dialog').open)lastFocus.focus({preventScroll:true});});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stopPreviews();player.pause();}});
  document.getElementById('overview-video').addEventListener('play',stopPreviews);
  document.addEventListener('physag:open-studio',stopPreviews);
  document.addEventListener('physag:open-feature',e=>{if(e.detail?.item)openAsset(e.detail.item,e.detail.trigger);});
  render();
})();

 document.getElementById('gallery-dialog').addEventListener('close',()=>document.getElementById('gallery-dialog').classList.remove('focus-film'));
