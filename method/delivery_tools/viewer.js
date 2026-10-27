import * as THREE from 'three';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {OrbitControls} from './vendor/OrbitControls.js';
import {RoomEnvironment} from './vendor/RoomEnvironment.js';
const $=s=>document.querySelector(s),D=await fetch('./presentation.json').then(r=>r.json());
$('#title').textContent=D.title;$('#source').src=D.source;$('#download').href=D.model;$('#download').download='asset.glb';
$('#type').textContent=`动作来源：${D.motion_kind} · 物理状态：${D.physics_status}`;
$('#limitations').textContent=(D.limitations||[]).join('；');$('#evidence').textContent=JSON.stringify(D.evidence,null,2);
if(D.video)$('#video').src=D.video;else $('#video').replaceWith(Object.assign(document.createElement('p'),{textContent:'视频尚未交付。'}));
for(const [label,url] of [['输入',D.source],['原生候选',D.native_render],['细化资产',D.refined_render]]){if(!url)continue;const f=document.createElement('figure'),im=document.createElement('img'),cap=document.createElement('figcaption');im.src=url;cap.textContent=label;f.append(im,cap);$('#compare').append(f);}
const stage=$('#stage'),scene=new THREE.Scene(),renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1;
stage.prepend(renderer.domElement);const pm=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();scene.environment=pm.fromScene(room,.04).texture;room.dispose();pm.dispose();scene.environmentIntensity=.75;
scene.add(new THREE.HemisphereLight(0xffffff,0x7d8790,1.8));const light=new THREE.DirectionalLight(0xffffff,2.5);light.position.set(2,5,4);scene.add(light);
const camera=new THREE.PerspectiveCamera(36,1,.001,1000),orbit=new OrbitControls(camera,renderer.domElement);orbit.enableDamping=true;
let model,mixer,actions=[],clips=[],current=0,playing=true,elapsed=0,old=performance.now();
function home(){if(!model)return;const b=new THREE.Box3().setFromObject(model),c=b.getCenter(new THREE.Vector3()),s=b.getSize(new THREE.Vector3()).length()||1;camera.near=s/10000;camera.far=s*100;camera.position.copy(c).add(new THREE.Vector3(1,.6,1.3).normalize().multiplyScalar(s*1.6));orbit.target.copy(c);camera.updateProjectionMatrix();orbit.update();}
function select(i){actions.forEach(a=>a.stop());current=i;elapsed=0;const a=actions[i];if(a){a.reset();a.setLoop(THREE.LoopOnce,1);a.clampWhenFinished=true;a.play();mixer.setTime(0);}$('#clips').value=String(i);$('#scrub').value=0;}
function apply(t){const a=actions[current];if(!a)return;a.paused=false;a.time=Math.max(0,Math.min(t,clips[current].duration));mixer.update(0);a.paused=true;$('#scrub').value=a.time/clips[current].duration;}
$('#play').onclick=()=>{playing=!playing;$('#play').textContent=playing?'暂停':'播放';};$('#home').onclick=home;
$('#clips').onchange=e=>select(Number(e.target.value));$('#scrub').oninput=e=>{playing=false;$('#play').textContent='播放';elapsed=Number(e.target.value)*clips[current].duration;apply(elapsed);};
new ResizeObserver(()=>{renderer.setSize(stage.clientWidth,stage.clientHeight);camera.aspect=stage.clientWidth/stage.clientHeight;camera.updateProjectionMatrix();}).observe(stage);
try{const g=await new GLTFLoader().loadAsync(D.model);model=g.scene;scene.add(model);mixer=new THREE.AnimationMixer(model);clips=g.animations.filter(c=>c.duration>0);actions=clips.map(c=>mixer.clipAction(c));clips.forEach((c,i)=>$('#clips').add(new Option(c.name||`动作 ${i+1}`,i)));if(clips.length)select(0);else{$('#play').disabled=$('#scrub').disabled=$('#clips').disabled=true;}home();$('#status').textContent=clips.length?`${clips.length} 组资产动作 · 自动依次播放`:'静态候选：未包含可播放动作';window.__assetCheck={loaded:true,clips:clips.map(c=>({name:c.name,duration:c.duration,tracks:c.tracks.length})),meshCount:0};model.traverse(o=>{if(o.isMesh)window.__assetCheck.meshCount++;});}
catch(e){$('#status').textContent='加载失败：'+e.message;window.__assetCheck={loaded:false,error:e.message};}
renderer.setAnimationLoop(()=>{const now=performance.now(),dt=Math.min(.1,(now-old)/1000);old=now;if(mixer&&clips.length&&playing){elapsed+=dt;if(elapsed>clips[current].duration+.6)select((current+1)%clips.length);apply(Math.min(elapsed,clips[current].duration));}orbit.update();renderer.render(scene,camera);});
