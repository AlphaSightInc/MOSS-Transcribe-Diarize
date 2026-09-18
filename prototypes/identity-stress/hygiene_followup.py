"""Finish the short-clip action after decoder response; same WP7 workspace and budget."""
import json,ssl
from run import Probe,Client,SCRATCH,OUT,audio,emit
p=Probe.__new__(Probe);p.client=Client('https://127.0.0.1:17867',ssl._create_unverified_context())
p.client._jar=json.loads((SCRATCH/'cookies.json').read_text());p.results=json.loads((OUT/'stress-results.json').read_text())
def enroll(p,ident,ids,elapsed,done):
    if ids and not done:done.append(emit('short_enrollment_attempt',response=p.name(ident,ids[0],'WP7 short')))
p.meeting('three_seconds_waited',audio('interview_adam_frank_180s',61,64),[(0,3,'Adam')],actions=enroll)
def replace(p,ident,ids,elapsed,done):
    if ids and elapsed>=4 and not done:
        done.append(emit('replace_profile',response=p.name(ident,ids[0],'WP7 replacement'),bank=p.bank()))
        done.append(emit('replace_same_sample',response=p.name(ident,ids[0],'WP7 replacement'),bank=p.bank()))
p.meeting('replacement',audio('interview_adam_frank_180s',67,73),[(0,6,'Adam')],actions=replace,expected_name='WP7 short')
