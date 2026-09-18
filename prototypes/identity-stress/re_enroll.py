"""Check replacement after eligible evidence arrives, within remaining WP7 budget."""
import json,ssl
from run import Probe,Client,SCRATCH,OUT,audio,emit
p=Probe.__new__(Probe);p.client=Client('https://127.0.0.1:17867',ssl._create_unverified_context())
p.client._jar=json.loads((SCRATCH/'cookies.json').read_text());p.results=json.loads((OUT/'stress-results.json').read_text())
emit('bank_before_reenrollment',bank=p.bank())
def replace(p,ident,ids,elapsed,done):
    if ids and elapsed>=9 and not done:
        done.append(emit('eligible_replace',response=p.name(ident,ids[0],'WP7 renamed'),bank=p.bank()))
        done.append(emit('eligible_replace_again',response=p.name(ident,ids[0],'WP7 renamed'),bank=p.bank()))
p.meeting('confirmed_replacement',audio('interview_adam_frank_180s',49,61),[(0,12,'Adam')],actions=replace,expected_name='WP7 renamed')
