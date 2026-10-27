from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parent
sys.path.insert(0,str(Path(r'C:\HISTORICAL_REFERENCE_NOT_EXECUTABLE\Documents\华为\server_skill_physxverse10_20260909\presentation\_plot_deps')))
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from PIL import Image
font=FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc')
items=[('输入原图','input/source.png'),('新 TRELLIS.2 原始候选','renders/native.png'),('Blender 精修后','renders/refined.png')]
fig,axes=plt.subplots(1,3,figsize=(15,5.7),dpi=160,facecolor='#131821')
for ax,(title,rel) in zip(axes,items):
 ax.imshow(Image.open(R/rel));ax.set_axis_off();ax.set_title(title,fontproperties=font,color='white',fontsize=14);ax.set_facecolor('#131821')
fig.text(.5,.025,'原图保持原样；候选与精修共用参考相机、灯光。单图物理值为推断，测试通过不等于完整高保真验收。',ha='center',fontproperties=font,color='#c4cedc',fontsize=10)
plt.subplots_adjust(left=.012,right=.988,top=.94,bottom=.075,wspace=.025);fig.savefig(R/'comparison.png',facecolor=fig.get_facecolor());plt.close(fig)
(R/'comparison_provenance.json').write_text(json.dumps({'files':{rel:hashlib.sha256((R/rel).read_bytes()).hexdigest() for _,rel in items},'operation':'static comparative figure of unchanged input and actual Blender renders; no image enhancement'},indent=2))
print('Saved',R/'comparison.png')
