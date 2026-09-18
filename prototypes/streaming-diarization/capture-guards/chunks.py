"""Attack candidate on production-sized 0.5 s mixer chunks; counts only."""
import json
from prototype import *
s=read('interview_bill_ackman_60s');n=read('interview_keyu_jin_60s');rows=[]
for name,x,near in cases(s,n):
    for start in range(0,len(s),8000):
        mic=np.frombuffer(pcm(x[start:start+8000]),dtype='<i2').astype(float)/32768
        row=dict(name=name,start_sample=start,near=near,**statistic(s[start:start+8000],mic));rows.append(row)
print(json.dumps(dict(spans=len(rows),near_spans=sum(r['near'] for r in rows),false_suppress=sum(r['near'] and r['decision']=='leak-suspect' for r in rows),echo_suspect=sum(not r['near'] and r['decision']=='leak-suspect' for r in rows))))
(ROOT/'evidence/mvpfix/wp3/chunks.json').write_text(json.dumps(rows))
