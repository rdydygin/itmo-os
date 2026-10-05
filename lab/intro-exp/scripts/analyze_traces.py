#!/usr/bin/env python3
"""Analyze xctrace XML with document-wide id/ref resolution; main thread only."""
from collections import Counter,defaultdict
import csv,json,re
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'results/system-trace'
NAMES=['graph_traverse-read','graph_traverse-write','graph_traverse_mmap-read','graph_traverse_mmap-write']

def analyze(name):
    toc=ET.parse(FOLDER/f'{name}-toc.xml').getroot()
    root=ET.parse(FOLDER/f'{name}-data.xml').getroot()
    ids={el.attrib['id']:el for el in root.iter() if 'id' in el.attrib}
    def resolve(el):
        seen=set()
        while el is not None and 'ref' in el.attrib:
            ref=el.attrib['ref']
            if ref in seen:raise ValueError('reference cycle')
            seen.add(ref);el=ids[ref]
        return el
    def val(el):
        el=resolve(el)
        return el.text if el is not None else None
    def fmt(el):
        el=resolve(el)
        return el.attrib.get('fmt','') if el is not None else ''
    def main(el):return fmt(el).startswith('Main Thread')
    tables=toc.find('run/data').findall('table')
    nodes={tables[int(re.search(r'table\[(\d+)\]',n.attrib['xpath']).group(1))-1].attrib['schema']:n for n in root.findall('node')}
    event_counts=Counter(); switches=[]
    for row in nodes['context-switch'].findall('row'):
        cells=list(row)
        if main(cells[1]):
            event=val(cells[2]);event_counts[event]+=1
            switches.append((int(val(cells[0])),event,fmt(cells[4])))
    # Ignore the synthetic Blocked interval starting at trace time zero,
    # before the first scheduling event for the launched main thread.
    start=min(time for time,event,core in switches)
    durations=Counter();cores=Counter();intervals=[]
    for row in nodes['thread-state'].findall('row'):
        c=list(row)
        if not main(c[1]):continue
        a=int(val(c[0]));b=a+int(val(c[3]))
        if b<=start:continue
        duration=b-max(a,start)
        state=val(c[2]);durations[state]+=duration
        core=fmt(c[5])
        if state=='Running':cores[core]+=duration
        intervals.append((max(a,start),b,state,core))
    end=max(b for a,b,state,core in intervals)
    running=[(a,core) for a,b,state,core in intervals if state=='Running' and core]
    migrations=sum(a[1]!=b[1] for a,b in zip(running,running[1:]))
    frames=Counter();samples=0;sample_cores=Counter()
    for row in nodes['time-profile'].findall('row'):
        c=list(row)
        if not main(c[1]):continue
        weight=int(val(c[5]));bt=resolve(c[6])
        if bt is None or not len(bt):continue
        frame=resolve(bt[0]);frames[frame.attrib.get('name','unknown')]+=weight
        samples+=1;sample_cores[fmt(c[3])]+=weight
    target=toc.find('run/info/target/process')
    args=target.attrib['arguments'].split()
    iters=int(next(x for x in args if x.isdigit()))
    observed=(end-start)/1e9
    assert sum(durations.values())==end-start,'overlapping/gapped main-thread intervals'
    result={'trace':name,'iterations':iters,'pid':target.attrib['pid'],'return_exit_status':target.attrib.get('return-exit-status'),'recording_duration_s':float(toc.findtext('run/info/summary/duration')),'observed_start_s':start/1e9,'observed_end_s':end/1e9,'observed_window_s':observed,'observed_s_per_iteration':observed/iters,'states_s':{k:v/1e9 for k,v in durations.items()},'running_percent':durations['Running']/(end-start)*100,'cores_running_s':{k:v/1e9 for k,v in cores.items()},'core_changes':migrations,'scheduling_events':dict(event_counts),'sample_count':samples,'sample_weight_s':sum(frames.values())/1e9,'top_sample_frames':[{'frame':key,'weight_s':weight/1e9,'percent':weight/sum(frames.values())*100} for key,weight in frames.most_common(12)]}
    return result

if __name__=='__main__':
    results=[analyze(name) for name in NAMES]
    (FOLDER/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    for result in results:
        print(json.dumps(result,ensure_ascii=False,indent=2))
