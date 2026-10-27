"""Package an animated native-preserving GLB and factual evidence. No geometry generation."""
from pathlib import Path
import json,shutil,argparse
ROOT=Path(__file__).resolve().parent
HTML='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PhysAg3D · 交互资产</title>
<style>*{box-sizing:border-box}body{margin:0;font:15px system-ui;background:#eef1f4;color:#202d37}header{padding:20px 28px;background:#fff;border-bottom:1px solid #d8dee4}h1{margin:8px 0;font-size:25px}a{color:#25619a}.grid{display:grid;grid-template-columns:1fr 310px;gap:16px;padding:20px}#stage{height:70vh;min-height:440px;background:#e2e7ec;position:relative;border-radius:12px;overflow:hidden}canvas{display:block;width:100%;height:100%}aside{background:white;padding:20px;border-radius:12px}img{width:100%;object-fit:contain;background:white}button,select{padding:9px;margin:5px 4px 5px 0;border:1px solid #abbcc8;border-radius:6px;background:white;font:inherit}input{width:100%}.note{color:#55636d;line-height:1.7;font-size:13px}#status{position:absolute;bottom:12px;left:12px;background:#ffffffdc;padding:10px;border-radius:7px}video{width:100%;max-height:500px;background:#222}section{padding:0 20px 20px}pre{white-space:pre-wrap;word-break:break-word;font-size:12px}#compare{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0;background:white;padding:10px}figcaption{padding:8px}@media(max-width:800px){.grid{grid-template-columns:1fr}#stage{height:58vh;min-height:350px}#compare{grid-template-columns:1fr}}</style>
<script type="importmap">{"imports":{"three":"./vendor/three.module.js","three/addons/utils/BufferGeometryUtils.js":"./vendor/BufferGeometryUtils.js"}}</script>
<header><span>单例交互回放</span><h1 id="title">加载资产</h1><div class="note">PhysAg3D · Native generation → Blender refinement</div></header>
<div class="grid"><div id="stage"><div id="status">加载真实模型与动画…</div></div><aside><img id="source" alt="原始输入"><h3>交互回放</h3><select id="clips"></select><div><button id="play">暂停</button><button id="home">重置视角</button></div><label>当前动作进度<input id="scrub" type="range" min="0" max="1" step="0.001" value="0"></label><p id="type" class="note"></p><p id="limitations" class="note"></p><a id="download">下载资产 GLB</a><p class="note">拖动旋转视角，滚轮缩放。滑块驱动资产中已有的动作；此页面不是在线物理求解器。</p></aside></div>
<section id="compare"></section><section><h2>动作视频</h2><video id="video" controls loop muted playsinline preload="metadata"></video></section><section><details><summary>生成与验证记录</summary><pre id="evidence"></pre></details></section><script type="module" src="./viewer.js"></script></html>'''
def make(case):
 case=Path(case).resolve();meta=json.loads((case/'delivery.json').read_text(encoding='utf-8'));out=case/'presentation';out.mkdir(exist_ok=True)
 shutil.copytree(ROOT/'vendor',out/'vendor',dirs_exist_ok=True)
 shutil.copy2(ROOT/'viewer.js',out/'viewer.js');(out/'index.html').write_text(HTML,encoding='utf-8')
 # Relative URLs, no output duplication or giant base64 HTML.
 def relative(k):
  p=meta.get(k)
  if not p:return None
  p=Path(p);p=p if p.is_absolute() else case/p
  if not p.is_file():return None
  return '../'+p.relative_to(case).as_posix()
 payload={'title':meta.get('title',case.name),'model':relative('model'),'source':relative('input'),'video':relative('video'),'native_render':relative('native_render'),'refined_render':relative('refined_render'),'motion_kind':meta.get('motion_kind','unverified'),'physics_status':meta.get('physics_status','not_verified'),'limitations':meta.get('limitations',[]),'evidence':meta}
 (out/'presentation.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 return out/'index.html'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('case');a=p.parse_args();print(make(a.case))
