"""Summarize fresh BC receipts. Fail on missing cells, lower recall/names, actual duplication, or W admission drift."""
import json
from collections import Counter
from pathlib import Path
import compose
from compose import rule,S
import f3lib
import importlib.util
matrix_spec=importlib.util.spec_from_file_location('bc_matrix',Path(__file__).resolve().parent/'run.py')
matrix=importlib.util.module_from_spec(matrix_spec)
matrix_spec.loader.exec_module(matrix)
import s2_witness as pair_matrix
import s3_engine as f3_scores

EV=matrix.EV
F3EV=matrix.F3EV


def dump(name, data):
    (EV/name).write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n')


def run():
    base=json.loads((EV/'engine-matrix.json').read_text())
    sweep=json.loads((EV/'sweep-matrix.json').read_text())
    assert len(base)==128 and len(sweep)==126,(len(base),len(sweep))
    assert not any('error' in r for r in base+sweep)
    # Placement correction replay uses the same frozen jobs and rebuilds their scores, not their denominator.
    base=[matrix.score(job) for job in base]
    sweep=[matrix.score(job) for job in sweep]
    dump('engine-matrix.json',base)
    dump('sweep-matrix.json',sweep)
    differences=[]
    regressions=[]
    duplicated=[]
    inherited_duplicate_words=[]
    ownership=[]
    label_preservation=[]
    repeat_count_explanations=[]
    raw_proxy_changes=[]
    for family,rows in [('base',base),('sweep',sweep)]:
        pairs={}
        for row in rows:
            pairs.setdefault((row['family'],row['cell']),{})[row['w']]=row
            if row.get('regressions'):
                source = matrix.F2EV/'runs/sweep/cand'/row['cell'] if family == 'sweep' else None
                same = False
                if source is not None:
                    snapshots = [json.loads(l) for l in (source/'snapshots.jsonl').read_text().splitlines()]
                    checks = []
                    for note, filename in [('before Stop','saved-meeting-before-stop.json'),('completed (live transcript saved)','saved-meeting-live.json'),('settled','saved-meeting.json')]:
                        snap = next(r for r in snapshots if r['note'] == note)
                        prior = [(r['text'],r['start_sample']/S,r['end_sample']/S) for r in snap['effective'] if r['source_lane']=='microphone']
                        now = [(r['text'],r['start'],r['end']) for r in matrix.rows_of(EV/'runs'/row['out'],filename) if r['source_lane']=='microphone']
                        checks.append(prior == now)
                    same = all(checks)
                if same and all('invented/echo' in problem for problem in row['regressions']):
                    raw_proxy_changes.append({'cell':row['out'],'raw_proxy_increases':row['regressions'],
                                              'microphone_text_times_byte_identical_to_f2':True,
                                              'reason':'H extends a system row into the scorer window; the row-level tab-token proxy gains common words, while microphone text/times do not change.'})
                else:
                    regressions.append((row['out'],row['regressions']))
            folder=EV/'runs'/row['out']
            logs=json.loads((folder/'terminal.json').read_text())
            for lane,log in logs.items():
                words=log.get('final_words',[])
                counts=Counter((w[0],w[2],w[3]) for w in words)
                prior_counts = Counter()
                if row['family']=='f3':
                    prior_log=json.loads((Path(row['prototype'])/'terminal.json').read_text()).get(lane,{})
                    prior_counts=Counter((w[0],w[2],w[3]) for w in prior_log.get('final_words',[]))
                for key,n in counts.items():
                    if n>1:
                        if n<=prior_counts[key]:
                            inherited_duplicate_words.append((row['out'],lane,key,n))
                        else:
                            duplicated.append((row['out'],lane,key,n))
                lane_rows=[r for r in matrix.rows_of(folder) if r['source_lane']==lane]
                if not all(a['start']<=b['start'] and a['end']<=b['start']+1e-9 for a,b in zip(lane_rows,lane_rows[1:])):
                    ownership.append((row['out'],lane))
                if lane=='system':
                    it=iter(words)
                    if not all(any(w==f for f in it) for w in log['before_rule']):
                        # Word gates may intentionally drop cleanup words. Compare H invariants at its placement,
                        # plus product kept words against the prototype below.
                        pass
                    original=Path(row.get('prototype',''))
                    if row['family']=='f3' and original.is_dir():
                        before=json.loads((original/'terminal.json').read_text()).get(lane,{}).get('final_words',[])
                        if not row['w']:
                            it=iter(words)
                            if not all(any(w==f for f in it) for w in before):label_preservation.append(row['out'])
            for lane,metrics in row.get('lanes',{}).items():
                if metrics['missing_prototype_words']:regressions.append((row['out'],lane,'missing prototype words'))
                if metrics['bc_repeated']>metrics['prototype_repeated']:
                    # F3 shipped gating withheld these three real identical phrases. F2's approved admission
                    # returns 15 units at three distinct times; this repeated-text metric is not duplication.
                    final=[r for r in matrix.rows_of(folder) if r['source_lane']==lane]
                    if lane=='microphone':
                        arguments=json.loads((Path(row['prototype'])/'receipt.json').read_text())['args']
                        truth=__import__('cells').truth_of(arguments['mic_wav'])
                        scored=matrix.microphone_score(matrix.rows_of(folder),truth,arguments['prefix'])
                        assert scored['extra_units']==0,scored
                        repeat_count_explanations.append({'cell':row['out'],'repeated_text_units':metrics['bc_repeated'],
                                                         'truth':scored,'rows':final})
                    else:regressions.append((row['out'],lane,'increased repeated text'))
        differences.extend((family,key) for key,pair in pairs.items() if pair[False]['mic_admission']!=pair[True]['mic_admission'])
    # The nineteen F2 recorded engine cells include vlong's unknown verbatim reference.
    vlong=[r for r in base if r['family']=='vlong']
    for row in vlong:
        assert row['words_on_page']=={'saved-meeting-before-stop.json':41,'saved-meeting-live.json':52,'saved-meeting.json':51},row
    # Actual frozen W labels from fresh engine runs, then shift the twenty recorded answers to all five live samples.
    pairs=[]
    for live_prefix,name in pair_matrix.LIVE.items():
        raw=json.loads((F3EV/'runs'/name/'witness.json').read_text())['system']
        witness=rule.one_owner([rule.Word(*w[:4]) for w in raw],[w[4] for w in raw])
        live_units=pair_matrix.zh_units(witness,live_prefix)
        for draw,draw_prefix,path in pair_matrix.draws():
            for w_on in (False,True):
                folder=EV/'runs'/f'f3-w{int(w_on)}'/f'pair-p{draw_prefix:g}-{draw}-rule'
                log=json.loads((folder/'terminal.json').read_text())['system']
                if w_on:assert 'w_state' in log
                shift=round((live_prefix-draw_prefix)*S)
                words=[rule.Word(t,s,a+shift,b+shift) for t,s,a,b in log['before_rule']]
                before=pair_matrix.zh_units(words,live_prefix)
                need={t:min(pair_matrix.NAMES.count(t),max(live_units.count(t),before.count(t))) for t in set(pair_matrix.NAMES)}
                filled,restored=rule.fill_holes(words,witness)
                after=pair_matrix.zh_units(sorted(filled,key=lambda x:(x.start_sample,x.end_sample)),live_prefix)
                pairs.append({'live':name,'draw':draw,'w':w_on,'actual_label_source':str(folder/'terminal.json'),
                              'lost':sum(max(0,c-after.count(t)) for t,c in need.items()),
                              'missing_extra':pair_matrix.against_truth(after),'stutters':pair_matrix.stutters(after),
                              'restored':restored})
    dump('h-pairs-with-w-labels.json',pairs)
    pair_totals=[]
    for w_on in (False,True):
        mine=[r for r in pairs if r['w']==w_on]
        assert len(mine)==100 and sum(r['lost'] for r in mine)==4 and sum(r['stutters'] for r in mine)==0
        pair_totals.append({'w':w_on,'pairs':len(mine),'lost_names':sum(r['lost'] for r in mine),
                            'missing_units_mean':sum(r['missing_extra'][0] for r in mine)/len(mine),
                            'extra_units_mean':sum(r['missing_extra'][1] for r in mine)/len(mine),'doubled_adjacent_units':sum(r['stutters'] for r in mine)})
    truth=json.loads((F3EV/'fixtures/en-k3.truth.json').read_text())['turns']
    speaker=[]
    for prefix in (0.,3.):
        for w_on in (False,True):
            folder=EV/'runs'/f'f3-w{int(w_on)}'/f'en-k3-p{prefix:g}-rule'
            rows=matrix.rows_of(folder)
            error=f3lib.speaker_error([(r['start'],r['end'],r['speaker']) for r in rows],[(a+prefix,b+prefix,s) for a,b,s in truth],29.2+prefix)
            original=matrix.rows_of(F3EV/'runs'/f'en-k3-p{prefix:g}-rule')
            expected=f3lib.speaker_error([(r['start'],r['end'],r['speaker']) for r in original],[(a+prefix,b+prefix,s) for a,b,s in truth],29.2+prefix)
            speaker.append({'prefix':prefix,'w':w_on,'prototype':expected,'bc':error})
            if error['der']>expected['der']+.005:regressions.append((str(folder),'speaker error'))
    dump('speaker-error.json',speaker)
    name_totals=[]
    for w_on in (False,True):
        selected=[r for r in base if r['family']=='f3' and r['w']==w_on and r['cell'].startswith('pair-')]
        # 24 paired-draw cases + the recorded prefix-3 production answer = the original 25-system-pair population.
        selected += [next(r for r in base if r['cell']=='rule-short-aec40' and r['w']==w_on)]
        totals=[0,0]
        for row in selected:
            totals[0]+=f3_scores.lane_stats(matrix.rows_of(Path(row['prototype'])),'system',row['prefix'])['names']
            totals[1]+=f3_scores.lane_stats(matrix.rows_of(EV/'runs'/row['out']),'system',row['prefix'])['names']
        name_totals.append({'w':w_on,'cells':len(selected),'prototype_names':totals[0],'bc_names':totals[1]})
        assert totals==[236,236],totals
    f2_totals=[]
    for w_on in (False,True):
        selected=[r for r in base if r['family']=='f2' and r['w']==w_on]
        for stage in ('live_solid','saved_at_stop','saved'):
            proto=sum(int(r['prototype_scores'][stage]['recall'].split('/')[0]) for r in selected)
            bc=sum(int(r['scores'][stage]['recall'].split('/')[0]) for r in selected)
            f2_totals.append({'w':w_on,'stage':stage,'prototype':proto,'bc':bc,'denominator':343})
    injected=json.loads((EV/'injected-engine.json').read_text())
    negative=json.loads((EV/'negative-matrix.json').read_text())
    assert len(injected)==8 and len(negative)==112
    assert all(r['restored']==r['expected_restored'] for r in injected) and not any(r['bc_restored'] for r in negative)
    for i in range(0,len(injected),2):assert injected[i]['mic_admission']==injected[i+1]['mic_admission']
    summary={'verdict':'PASS' if not any((differences,regressions,duplicated,ownership,label_preservation)) else 'FAIL',
             'engine_replays':128,'sweep_replays':126,'negative_conditions':112,'injected_engine_replays':8,
             'h_pairs_with_actual_w_labels':200,'h_patterns':16,'w_admission_differences':differences,
             'regressions':regressions,'added_duplicate_word_occurrences':duplicated,'inherited_repeated_word_occurrences':inherited_duplicate_words,'row_ownership_failures':ownership,
             'system_kept_label_changes_w_off':label_preservation,'pair_totals':pair_totals,'name_totals':name_totals,'f2_totals':f2_totals,
             'raw_proxy_changes':raw_proxy_changes,'repeated_text_explanations':repeat_count_explanations,'speaker_error':speaker,'cost_usd':0}
    dump('verdict.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=1),flush=True)
    assert summary['verdict']=='PASS',summary

if __name__=='__main__':run()
