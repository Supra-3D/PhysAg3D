/* Curated local media snapshot. No remote credentials or runtime SSH dependency. */
(() => {
  'use strict';
  const root=document.getElementById('hero-stage');
  if(!root)return;
  const assets=[
  {
    "id": "hero-camera",
    "key": "camera",
    "name": "Camera",
    "category": "electronics",
    "line": "Lens · display · dials · shutter",
    "description": "Quick lens and display demonstrations, followed by parallel close-ups of both dials and the shutter.",
    "note": "Assisted refinement of an existing generated camera. Existing recorded joint trajectories are separated and retimed for the close-ups; this presentation is not a new coupled dynamics simulation. The final controls are presented as parallel recorded close-ups.",
    "beats": [
      [
        0,
        "Lens · display · dials · shutter"
      ],
      [
        1.0,
        "Rotating & telescoping lens"
      ],
      [
        3.6,
        "Fold-out display"
      ],
      [
        6.6,
        "Two dials + shutter"
      ]
    ],
    "mediaKey": "camera-studio-20261023"
  },
  {
    "id": "hero-trifold",
    "key": "trifold",
    "name": "Phone",
    "category": "electronics",
    "line": "Closed → open → closed",
    "description": "Two opposing folds shown in sequence, from fully closed to open and back.",
    "note": "Assisted refinement of an existing generated phone. Both hinges and the display seams retain synchronized recorded motion. Rear model lettering is softened for this presentation.",
    "beats": [
      [
        0,
        "Closed → open → closed"
      ],
      [
        0.6,
        "First hinge"
      ],
      [
        3.7,
        "Second hinge"
      ],
      [
        6.3,
        "Fold back to closed"
      ]
    ],
    "mediaKey": "trifold-studio-20261023"
  },
  {
    "id": "hero-globe",
    "key": "globe",
    "name": "Globe",
    "category": "personal",
    "line": "Polar-axis rotation · glass close-up",
    "description": "The globe turns within its fixed frame, followed by a close-up through the glass lens.",
    "note": "Original generated geometry, glass material and recorded globe rotation. The lens is fixed; its glass rendering is approximate and optical magnification is not calibrated. Presentation timing and viewpoints are adjusted.",
    "beats": [
      [
        0,
        "Polar-axis rotation · glass close-up"
      ],
      [
        0.6,
        "Polar-axis rotation"
      ],
      [
        4.4,
        "Glass lens close-up"
      ]
    ],
    "mediaKey": "globe-studio-20261023"
  },
  {
    "id": "hero-ladder",
    "key": "ladder",
    "name": "Ladder",
    "category": "tools",
    "line": "Side links · folding frames",
    "description": "Close-ups of the connected side linkages and top hinges as the ladder folds and reopens.",
    "note": "Assisted local repair of the generated ladder. The six coupled frame and linkage animation tracks remain synchronized. The motion assumes idealized support and is not a load-bearing test.",
    "beats": [
      [
        0,
        "Side links · folding frames"
      ],
      [
        0.6,
        "Side linkage"
      ],
      [
        4.5,
        "Hinge & frame opening"
      ]
    ],
    "mediaKey": "ladder-studio-20261023"
  },
  {
    "id": "hero-carousel",
    "key": "carousel",
    "name": "Carousel",
    "category": "leisure",
    "line": "Rotating platform · fixed base",
    "description": "The canopy, horses and platform rotate together above the fixed base.",
    "note": "Assisted refinement of an existing generated carousel. Recorded rotor motion is retained and retimed for two close-ups. The horses do not move independently.",
    "beats": [
      [
        0,
        "Rotating platform · fixed base"
      ],
      [
        0.6,
        "Rotating platform"
      ],
      [
        4.5,
        "Fixed base · moving assembly"
      ]
    ],
    "mediaKey": "carousel-studio-20261023"
  }
].map(x=>({...x,poster:window.PHYSAG3D_ASSET_URL(`assets/hero/${x.mediaKey}-poster.webp`),video:window.PHYSAG3D_ASSET_URL(`assets/hero/${x.mediaKey}.mp4`),heroVideo:window.PHYSAG3D_ASSET_URL(`assets/hero/${x.mediaKey}.mp4`),heroPoster:window.PHYSAG3D_ASSET_URL(`assets/hero/${x.mediaKey}-poster.webp`)}));
  const inputs=[
    'https://media.githubusercontent.com/media/Supra-3D/PhysAg3D/24f4db5cb22791f4059dc74cfdc556778f7a4882/website/assets/generated-latest/img_145/input.png',
    'assets/generated-latest/img_020/input.webp',
    'https://media.githubusercontent.com/media/Supra-3D/PhysAg3D/24f4db5cb22791f4059dc74cfdc556778f7a4882/website/assets/generated-latest/img_110/input/source.png',
    'assets/generated-latest/img_149/input.webp',
    'https://media.githubusercontent.com/media/Supra-3D/PhysAg3D/24f4db5cb22791f4059dc74cfdc556778f7a4882/website/assets/generated-latest/img_099/input.png'
  ];
  const galleryIds=['extra-img_145','studio-img_020','extra-img_110','extra-img_149','extra-img_099'];
  assets.forEach((asset,i)=>{asset.input=inputs[i];asset.videoLabel='Full interaction';});
  const overview={video:'assets/hero/overview-48s-20261028.mp4',poster:'assets/hero/camera-studio-20261023-poster.webp'};
  const chapters=[
  {
    "start": 0,
    "end": 11.1,
    "line": "Lens, display, dials & shutter"
  },
  {
    "start": 11.1,
    "end": 20.7,
    "line": "Two-hinge unfolding"
  },
  {
    "start": 20.7,
    "end": 29.9,
    "line": "Polar-axis rotation"
  },
  {
    "start": 29.9,
    "end": 39.1,
    "line": "Linked folding motion"
  },
  {
    "start": 39.1,
    "end": 48.3,
    "line": "Rotating platform"
  }
];
  const videos=[document.getElementById('hero-video-a'),document.getElementById('hero-video-b')];
  const tabs=[...root.querySelectorAll('[data-hero]')];
  const overviewButton=document.getElementById('hero-overview');
  const toggle=document.getElementById('hero-toggle');
  const detail=document.getElementById('hero-detail');
  const input=document.getElementById('hero-input-image');
  const description=document.getElementById('hero-description');
  const announcement=document.getElementById('hero-announcement');
  const film=document.getElementById('overview-video');
  const reduce=matchMedia('(prefers-reduced-motion: reduce)');
  let index=0,slot=0,sequence=0,mode='overview',paused=reduce.matches,inView=false;
  let cancelLoad=null;
  const current=()=>videos[slot];
  const canPlay=()=>!paused&&inView&&!document.hidden&&!document.querySelector('dialog[open]')&&film.paused;
  function paintPause(){
    toggle.setAttribute('aria-pressed',String(paused));
    toggle.setAttribute('aria-label',paused?'Play showcase':'Pause showcase');
    document.getElementById('hero-play-label').textContent=paused?'Play showcase':'Pause showcase';
  }
  function play(video=current()){
    if(!canPlay()){video.pause();return;}
    video.play().catch(error=>{
      if(error.name==='AbortError'||video!==current())return;
      paused=true;paintPause();
    });
  }
  function labels(){
    const asset=assets[index];
    root.dataset.asset=asset.key;root.dataset.mode=mode;
    document.getElementById('hero-name').textContent=asset.name;
    description.textContent=mode==='overview'?chapters[index].line:asset.line;
    if(input.getAttribute('src')!==asset.input){input.src=asset.input;input.alt='Input image for '+asset.name;}
    detail.setAttribute('aria-label','Interact in 3D with '+asset.name);
    overviewButton.setAttribute('aria-pressed',String(mode==='overview'));
    if(mode==='detail')overviewButton.style.setProperty('--shot-progress','0');
    tabs.forEach((tab,i)=>{
      tab.setAttribute('aria-pressed',String(mode==='detail'&&i===index));
      tab.classList.toggle('is-current',i===index);
      tab.style.setProperty('--shot-progress','0');
    });
  }
  function updateFrame(video){
    if(video!==current())return;
    if(mode==='overview'){
      const next=chapters.findIndex(c=>video.currentTime>=c.start&&video.currentTime<c.end);
      if(next>=0&&next!==index){index=next;labels();}
      overviewButton.style.setProperty('--shot-progress',String(video.currentTime/28));
      const chapter=chapters[index];
      tabs[index].style.setProperty('--shot-progress',String(Math.max(0,Math.min(1,(video.currentTime-chapter.start)/(chapter.end-chapter.start)))));
    }else if(Number.isFinite(video.duration)&&video.duration>0){
      tabs[index].style.setProperty('--shot-progress',String(video.currentTime/video.duration));
      const beat=[...assets[index].beats].reverse().find(b=>video.currentTime>=b[0]);
      if(beat&&description.textContent!==beat[1])description.textContent=beat[1];
    }
  }
  async function select(nextMode,next=0){
    const token=++sequence;
    if(cancelLoad)cancelLoad();
    const previous=current(),nextSlot=1-slot,video=videos[nextSlot];
    previous.pause();video.pause();
    const media=nextMode==='overview'?overview:{video:assets[next].heroVideo,poster:assets[next].heroPoster};
    root.setAttribute('aria-busy','true');
    video.poster=media.poster;
    const ready=new Promise(resolve=>{
      const finish=(ok)=>{clearTimeout(timer);video.removeEventListener('loadeddata',loaded);video.removeEventListener('error',failed);if(cancelLoad===cancel)cancelLoad=null;resolve(ok);};
      const loaded=()=>finish(true),failed=()=>finish(false),cancel=()=>finish(false);
      const timer=setTimeout(failed,10000);
      cancelLoad=cancel;
      video.addEventListener('loadeddata',loaded,{once:true});video.addEventListener('error',failed,{once:true});
    });
    video.src=media.video;video.load();
    const ok=await ready;
    if(token!==sequence)return;
    root.removeAttribute('aria-busy');
    if(!ok){announcement.textContent='The clip could not load. Please select it again.';play(previous);return;}
    mode=nextMode;index=next;slot=nextSlot;paused=false;
    film.pause();labels();paintPause();
    video.classList.add('is-active');previous.classList.remove('is-active');
    announcement.textContent=mode==='overview'?'48.3-second overview':assets[index].name+' — full interaction';
    play(video);
  }
  videos.forEach(video=>{
    video.muted=true;video.playsInline=true;video.loop=true;
    video.addEventListener('timeupdate',()=>updateFrame(video));
    if('requestVideoFrameCallback' in video){
      const frame=()=>{updateFrame(video);video.requestVideoFrameCallback(frame);};
      video.requestVideoFrameCallback(frame);
    }
  });
  tabs.forEach((tab,i)=>tab.addEventListener('click',()=>select('detail',i)));
  overviewButton.addEventListener('click',()=>select('overview'));
  toggle.addEventListener('click',()=>{
    paused=!paused;if(!paused)film.pause();paintPause();play();
  });
  detail.addEventListener('click',e=>{
    current().pause();
    document.dispatchEvent(new CustomEvent('physag:open-studio',{detail:{galleryId:galleryIds[index],trigger:e.currentTarget}}));
  });
  new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;play();},{threshold:.1}).observe(root);
  document.addEventListener('visibilitychange',()=>{videos.forEach(video=>video.pause());play();});
  document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(()=>play()).observe(dialog,{attributes:true,attributeFilter:['open']}));
  film.addEventListener('play',()=>current().pause());
  film.addEventListener('pause',()=>play());
  reduce.addEventListener('change',()=>{paused=reduce.matches;paintPause();play();});
  inputs.forEach(src=>{const image=new Image();image.src=src;});
  paintPause();labels();
})();
