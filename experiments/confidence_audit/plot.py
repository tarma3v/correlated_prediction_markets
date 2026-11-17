"""Draw the thesis figure from the result table. Optional dependency: matplotlib."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

folder = Path(__file__).resolve().parent
rows = json.loads((folder/'results.json').read_text())['thresholds']
labels = [f"{r['cutoff']:.2f}".replace('.', ',') for r in rows]
fig, ax = plt.subplots(figsize=(8, 3.0))
safe = [r['calls']-r['errors'] for r in rows]
bad = [r['errors'] for r in rows]
abstain = [r['pairs']-r['calls'] for r in rows]
y = list(range(len(rows)))
ax.barh(y,bad,color='#9c422d',label='Есть контрпример')
ax.barh(y,safe,left=bad,color='#33756f',label='Запрет выдержал проверку')
ax.barh(y,abstain,left=[r['calls'] for r in rows],color='#e2e7ea',label='Отказ')
for i,r in enumerate(rows):
    ax.text(852,i,f"{r['errors']}/{r['calls']}",va='center',ha='left',fontsize=9)
ax.text(852,-0.58,'Ошибки / ответы',fontsize=8,color='#394654')
ax.set_xlim(0,1010)
ax.set_yticks(y,labels)
ax.set_ylabel('Порог')
ax.invert_yaxis()
ax.set_xticks([0,200,400,600,839])
ax.set_xlabel('Число пар')
ax.spines[['top','right','left']].set_visible(False)
ax.tick_params(length=0)
ax.legend(loc='upper center',bbox_to_anchor=(0.5,-0.25),ncol=3,frameon=False,fontsize=8)
fig.subplots_adjust(left=.12,right=.98,top=.91,bottom=.30)
fig.savefig(folder/'confidence.png',dpi=155,facecolor='white')
