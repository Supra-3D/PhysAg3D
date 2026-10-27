/* The Film's embedded instrumental soundtrack. Overview remains silent. */
(() => {
  'use strict';
  const film=document.getElementById('overview-video');
  const filmButton=document.getElementById('film-music-toggle');
  const filmVolume=document.getElementById('film-music-volume');
  if(!film||!filmButton||!filmVolume)return;
  film.volume=1;


  function paintFilm(){
    const audible=!film.muted&&film.volume>0;
    filmButton.setAttribute('aria-pressed',String(audible));
    filmButton.setAttribute('aria-label',audible?'Mute film music':'Unmute film music');
    filmButton.querySelector('.music-label').textContent=audible?'Music on':'Music off';
    filmVolume.value=String(Math.round(film.volume*100));
    filmVolume.setAttribute('aria-valuetext',filmVolume.value+' percent');
  }
  filmButton.addEventListener('click',()=>{
    if(film.muted||film.volume===0){film.volume=film.volume||1;film.muted=false;}
    else film.muted=true;
    paintFilm();
  });
  filmVolume.addEventListener('input',()=>{
    film.volume=Number(filmVolume.value)/100;
    film.muted=film.volume===0;
    paintFilm();
  });
  film.addEventListener('volumechange',paintFilm);
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden)film.pause();
  });
  document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(()=>{
    if(dialog.open)film.pause();
  }).observe(dialog,{attributes:true,attributeFilter:['open']}));
  paintFilm();
})();
