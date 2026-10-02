from pathlib import Path
import json, os
os.environ['MPLCONFIGDIR']='/tmp/cii_mpl'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch
ROOT=Path(__file__).resolve().parents[1]
D=json.loads((ROOT/'outputs/revision/diagnostics.json').read_text())
B,F=D['scenarios'][0],D['scenarios'][3]
OUT=ROOT/'outputs/revision_figures'
plt.rcParams.update({'font.family':'Arial','font.size':10,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
ids=[f'F-{i:02}' for i in range(1,9)]
colors=['#1c6578','#e49a37','#6f8394']
def save(fig,name,kind='Main'):
 for ext in ['pdf','png','svg','eps']:
  folder=OUT/kind if ext in ['pdf','png'] else OUT/ext.upper()/kind
  folder.mkdir(parents=True,exist_ok=True)
  fig.savefig(folder/(name+'.'+ext),dpi=300,bbox_inches=None if name=='Graphical_Abstract' else 'tight',facecolor='white')
 plt.close(fig)
def compare(name,a,b,labels):
 fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
 va=np.array([a[k]*100 for k in ids]);vb=np.array([b[k]*100 for k in ids])
 for ax,v,title,color in zip(axes,[va,vb,vb-va],labels,colors):
  ax.bar(ids,v,color=color,width=.65)
  ax.set_title(title,loc='left',fontweight='bold',fontsize=11)
  ax.tick_params(axis='x',rotation=45)
  ax.set_ylabel('Normalized score (%)' if ax is not axes[2] else 'Score change (percentage points)')
  ax.axhline(0,color='#89949e',lw=.6)
  for j,x in enumerate(v):ax.text(j,x+(0.5 if x>=0 else -.8),f'{x:.1f}',ha='center',va='bottom' if x>=0 else 'top',fontsize=8)
  ax.margins(y=.2)
 fig.supxlabel('Fixed nominal EKLM reference • prescribed inputs • uncalibrated scores',fontsize=10)
 save(fig,name)
compare('Figure_4',B['process_only'],F['process_only'],['(a) Nominal efficiency 0.845','(b) Efficiency 0.815','(c) Perturbed − nominal'])
compare('Figure_5',F['design_margin'],F['margin_10'],['(a) Prescribed surge margin 15%','(b) Prescribed surge margin 10%','(c) Assumed − design margin'])
fig,ax=plt.subplots(figsize=(8,4.4),layout='constrained');x=np.arange(8)
for off,key,label,color in [(-.18,B['process_only'],'Nominal / specified priors',colors[0]),(.18,F['process_only'],'Efficiency 0.815',colors[1])]:
 ax.bar(x+off,[key[k]*100 for k in ids],width=.35,label=label,color=color)
ax.set_xticks(x,ids);ax.set_ylabel('Normalized score (%)');ax.legend(frameon=False)
ax.set_title('Fixed-reference hypothesis scores; surge observation omitted',loc='left',fontsize=11)
save(fig,'Figure_S2','SI')
def box(ax,x,y,w,h,title,body):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.015,rounding_size=0.015',fc='#f3f7f8',ec='#91a8b0',lw=1.1))
 ax.text(x+.025,y+h-.055,title,color='#17495c',weight='bold',fontsize=13,va='top')
 ax.text(x+.025,y+h-.13,body,color='#243540',fontsize=11,va='top',linespacing=1.65)
fig,ax=plt.subplots(figsize=(11,6));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
box(ax,.025,.56,.95,.39,'(a) Populate the current graph','EKLM process outputs → runtime observations\nMechanical outputs → equipment-linked properties\nCombustor combined-life fraction: 0.625 at 10,000 hours')
box(ax,.025,.08,.45,.38,'(b) Execute Q1','P1 priority + combined-life fraction > 0.5\nRecorded result: COMB-001, 0.625\nThe cutoff is an explicit query literal.')
box(ax,.525,.08,.45,.38,'(c) Verify evidence lifecycle','PARTIAL → NONE → PARTIAL → invalid binding\nDeactivate → remove → restore → clear/reject\n24 activation / binding checks\n17 additional failure scenarios')
ax.annotate('',xy=(.25,.475),xytext=(.25,.545),arrowprops={'arrowstyle':'->','color':'#426b7b','lw':1.5})
ax.annotate('',xy=(.75,.475),xytext=(.75,.545),arrowprops={'arrowstyle':'->','color':'#426b7b','lw':1.5})
save(fig,'Figure_7')
fig,ax=plt.subplots(figsize=(12.5,5));fig.subplots_adjust(left=.02,right=.98,bottom=.03,top=.98);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
ax.text(.025,.95,'From conceptual model to runtime governance',fontsize=19,weight='bold',color='#17495c')
box(ax,.025,.36,.29,.48,'Declare','OWL/RDF equipment context\nFULL / PARTIAL / NONE\nParameters and provenance\nEngineering contract')
box(ax,.355,.36,.29,.48,'Execute','EKLM process simulation\nMechanical estimates\nDiagnostic hypothesis scores\nInvalidate stale evidence')
box(ax,.685,.36,.29,.48,'Inspect','72 routing / 104 contract cases\n36 lifecycle / 17 failure checks\n8 indicator-extension cases\nMatched conventional results')
for x in [.33,.66]:ax.annotate('',xy=(x+.018,.60),xytext=(x-.012,.60),arrowprops={'arrowstyle':'->','color':'#17495c','lw':2})
ax.text(.025,.20,'GTCC digital-twin framework • simulation-based evaluation',fontsize=13,weight='bold',color='#17495c')
ax.text(.025,.105,'Shared numerical models and policies: RDF and JSON give equivalent tested outcomes.\nPublic design-point comparison is separate from configuration and execution verification.',fontsize=11,linespacing=1.5)
save(fig,'Graphical_Abstract')
print('Figures 4, 5, 7, S2 and graphical abstract regenerated in PDF, PNG, SVG and EPS.')
