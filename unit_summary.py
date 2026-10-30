"""Individual unit manufacturing evidence reports. Exact MES keys; no guessed joins."""
from __future__ import annotations
import collections,datetime,pathlib,re,json
from inspector import decode
from excel_compat import Workbook,SpreadsheetFile
from enhanced import entries,category

MAC_RE=re.compile(r'^[0-9A-F]{12}$')
SEQ_RE=re.compile(r'MO\d{8}-\d{5}',re.I)
ID_SPLIT=re.compile(r'[\s,;，；]+')
STATIONS=('RF','BOB調試','BOB測試','資訊寫入','資訊核對','Throughput','Coupling')

def identify(raw):
    """One exact pcbSeq and LAN MAC per unit from MES evidence; detect conflicts."""
    by_mac={};sn_to_mac={};conflicts=[]
    for path,txt in raw:
        if category(path,txt) not in ('InformationWrite','InformationCheck'):continue
        basename=pathlib.PurePosixPath(path).name
        mm=re.match(r'([0-9A-Fa-f]{12})-',basename)
        if not mm:continue
        mac=mm.group(1).upper()
        seqs=set(re.findall(r'"pcbSeq"\s*:\s*"(MO\d{8}-\d{5})"',txt,re.I))
        # MES ksn requests paired with the following response, not a free adjacent field.
        sms=re.findall(r'"fieldName"\s*:\s*"ksn"[^\n]*(?:\n[^\n]*){0,4}?字段读取响应：\s*\{[^\n]*?"fieldValue"\s*:\s*"([^"]+)"',txt,re.I)
        sns=set(sms)
        if len(seqs)>1 or len(sns)>1:
            conflicts.append((mac,path,'同一來源多個PCB Seq或SN'));continue
        d=by_mac.setdefault(mac,{'mac':mac,'seq':'','sn':'','sources':[]})
        d['sources'].append(path)
        for typ,values in [('seq',seqs),('sn',sns)]:
            if values:
                value=next(iter(values))
                if d[typ] and d[typ]!=value:conflicts.append((mac,path,f'{typ}衝突 {d[typ]} / {value}'))
                else:d[typ]=value
    seq_map=collections.defaultdict(set)
    for mac,d in by_mac.items():
        if d['seq']:seq_map[d['seq']].add(mac)
        if d['sn']:
            if d['sn'] in sn_to_mac and sn_to_mac[d['sn']]!=mac:conflicts.append((mac,'',f'SN重複 {d["sn"]}'))
            else:sn_to_mac[d['sn']]=mac
    for seq,macs in seq_map.items():
        if len(macs)>1:conflicts.append((','.join(sorted(macs)),'',f'PCB Seq重複 {seq}'))
    return by_mac,sn_to_mac,conflicts

def station_for(path):
    c=category(path,'')
    if c=='WiFi':return 'RF'
    if c=='BOB':
        if '调试' in path or '調試' in path:return 'BOB調試'
        return 'BOB測試'
    return {'InformationWrite':'資訊寫入','InformationCheck':'資訊核對','Throughput':'Throughput','Coupling':'Coupling'}.get(c,'')

def declared_for(event):
    m=re.search(r'_(PASS|FAIL)(?:_Debug)?\.LOG$',pathlib.PurePosixPath(event['path']).name,re.I)
    if m:return m.group(1).upper()
    for r in event['rows']:
        if r['item'] in ('TeleATT 測站總結果','工站最終狀態') and str(r['actual']).upper() in ('PASS','FAIL'):
            return str(r['actual']).upper()
    return '未明確標示'

def status_for(event):
    vals=[r['result'] for r in event['rows'] if r['result']]
    if not vals:return 'NO EVIDENCE'
    if 'FAIL' in vals or '不符合' in vals:return 'FAIL'
    if '規格差異' in vals:return 'SPEC DIFF'
    if '待確認' in vals or '缺少證據' in vals:return 'REVIEW'
    return 'PASS' if 'PASS' in vals else 'REVIEW'

def _data(ws,headers,rows,widths=None):
    cols=len(headers);ws.get_range_by_indexes(0,0,1,cols).values=[headers]
    for start in range(0,len(rows),250):
        block=rows[start:start+250]
        ws.get_range_by_indexes(start+1,0,len(block),cols).values=block
    ws.get_range_by_indexes(0,0,1,cols).format={'fill':'#173851','font':{'bold':True,'color':'#FFFFFF'},'row_height':30}
    for idx,w in enumerate(widths or [24]*cols):
        ws.get_range_by_indexes(0,idx,1,1).format.column_width=w
    ws.freeze_panes.freeze_rows(1)

def failure_item(row):
    """Confirmed item-level failures only; no inferred failure from station retry."""
    if row.get('category') == 'ParserStatus':
        return False
    return str(row.get('result','')).upper() in ('FAIL','不符合')


def failure_key(row):
    return (str(row.get('item','')),str(row.get('mode','')),
            str(row.get('freq_MHz','')),str(row.get('antenna','')))


def failure_origin(rows):
    """Only explicit failed measures count as defect origin."""
    return {failure_key(r) for r in rows if failure_item(r)}


def _write_unit(dest,unit,station_events,conflicts):
    wb=Workbook.create();mac=unit['mac'];seq=unit['seq'];sn=unit['sn']
    summary=[];attempt_rows=[];detail_rows=[];history=[]; unresolved=[]
    all_events=[]
    for station in STATIONS:
        ev=sorted(station_events.get(station,[]),key=lambda x:x['sort_key'])
        all_events.extend(ev)
        statuses=[status_for(e) for e in ev]
        attempts=len(ev);retry=max(0,attempts-1)
        defects=set().union(*(failure_origin(e['rows']) for e in ev)) if ev else set()
        names=', '.join(sorted({k[0] for k in defects})) if defects else ('FAIL原因未解析' if any(declared_for(e)=='FAIL' for e in ev) else '無已證實FAIL測項')
        summary.append([station,attempts,retry,declared_for(ev[0]) if ev else 'NO EVIDENCE',declared_for(ev[-1]) if ev else 'NO EVIDENCE',statuses[-1] if statuses else 'NO EVIDENCE',names,'; '.join(pathlib.PurePosixPath(e['path']).name for e in ev)])
        for n,e in enumerate(ev,1):
            if declared_for(e)=='FAIL' and not failure_origin(e['rows']):
                unresolved.append([station,n,e['path'],'整站FAIL，但沒有可確認的FAIL測項；不可推定全部測項FAIL'])
        for n,e in enumerate(ev,1):
            history.append([station,n,e['time'],declared_for(e),status_for(e),e['path'],len(e['rows'])])
            for r in e['rows']:
                detail_rows.append([station,n,e['time'],r['item'],r['standard'],str(r['actual']),r['result'],r['mode'],r['freq_MHz'],r['antenna'],r['file'],r['line']])
        if retry:
            # Group repeated measures by (item/mode/frequency/antenna); keep ordinal duplicates in same attempt.
            keys=collections.OrderedDict()
            for e in ev:
                per=collections.Counter()
                for r in e['rows']:
                    if r['category']=='ParserStatus':continue
                    key=(r['item'],r['mode'],str(r['freq_MHz']),r['antenna'])
                    per[key]+=1
                    key=key+(per[key],)
                    keys.setdefault(key,[])
            defect_keys=set().union(*(failure_origin(e['rows']) for e in ev))
            for key in keys:
                if key[:4] not in defect_keys:continue
                vals=[]
                for e in ev:
                    relevant=[r for r in e['rows'] if (r['item'],r['mode'],str(r['freq_MHz']),r['antenna'])==key[:4]]
                    r=relevant[key[4]-1] if len(relevant)>=key[4] else None
                    vals.append(r)
                attempt_rows.append((station,key,vals))
    retested=sum(x[2]>0 for x in summary)
    total_retry=sum(x[2] for x in summary)
    observed=sum(x[1]>0 for x in summary)
    ws=wb.worksheets.add('01_單機Summary')
    meta=[['項目','結果'],['Model','GRG-4372u'],['MAC',mac],['SN',sn or 'NO EVIDENCE'],['PCB Seq',seq or 'NO EVIDENCE'],['有效測站數',observed],['有複測測站數',retested],['站別複測率',f'{retested}/{observed} ({retested/observed:.1%})' if observed else 'N/A'],['總複測次數',total_retry],['識別衝突', '有' if any(mac in c[0] for c in conflicts) else '無'],['說明','複測=同測站超過一份不同來源 Log；不等於單份 Log 中多個量測點。']]
    _data(ws,['設備資訊','數值'],meta[1:],[27,70])
    issues=wb.worksheets.add('06_FAIL原因未解析')
    _data(issues,['測站','第幾次','來源Log','原因'],unresolved or [['無','','','']], [21,14,90,72])
    st=wb.worksheets.add('02_各站結果')
    _data(st,['測站','測試次數','複測次數','初測Log結果','最終Log結果','QA查核結果','已證實FAIL測項','來源Log'],summary,[19,15,15,17,17,18,54,85])
    ret=wb.worksheets.add('03_複測履歷對照')
    max_attempt=max((len(x[2]) for x in attempt_rows),default=0)
    headers=['測站','測項','Mode','MHz','天線','同測項序次']
    for n in range(1,max_attempt+1):
        ordinal=('1st' if n==1 else '2nd' if n==2 else '3rd' if n==3 else f'{n}th')
        headers += [ordinal+' 標準',ordinal+' 實測值',ordinal+' 結果',ordinal+' 來源檔']
    matrix=[]
    for station,key,vals in attempt_rows:
        r=[station,*key[:4],key[4]]
        for v in vals:r.extend([v['standard'],str(v['actual']),v['result'],pathlib.PurePosixPath(v['file']).name] if v else ['','','',''])
        r+=['']*(len(headers)-len(r));matrix.append(r)
    if not matrix:matrix=[['無已證實FAIL測項的複測對照；可於測試次數頁查看重測事件']]+['']*(len(headers)-1)
    _data(ret,headers,matrix,[18,30,18,12,12,13]+[34,22,14,47]*max_attempt)
    hist=wb.worksheets.add('04_測試次數與來源')
    _data(hist,['測站','第幾次','來源時間','原始Log結果','QA查核結果','原始路徑','測項數'],history,[18,12,24,19,19,90,13])
    det=wb.worksheets.add('05_逐筆測項')
    _data(det,['測站','第幾次','時間','測試項目','標準','數值','判定','Mode','MHz','ANT','來源Log','行號'],detail_rows,[18,12,22,31,49,37,15,21,15,12,85,12])
    SpreadsheetFile.export_xlsx(wb).save(str(dest))
    return {'mac':mac,'sn':sn,'pcb_seq':seq,'file':str(dest),'retry_stations':retested,'retests':total_retry,'stations_observed':observed}

def build_unit_summaries(input_path,rows,ids,outdir,progress=None,raw_entries=None):
    outdir=pathlib.Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    requested=[i.strip().upper().replace(':','').replace('-','') if re.fullmatch(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}',i) else i.strip().upper() for i in ID_SPLIT.split(ids or '') if i.strip()]
    raw=list(entries(input_path)) if raw_entries is None else raw_entries
    by_mac,sn_to_mac,conflicts=identify(raw)
    row_map=collections.defaultdict(list)
    for r in rows:row_map[r['file']].append(r)
    # Build exact RF MES identity mapping from the full path basename. No fuzzy sequence guessing.
    rf_map={}
    for m,d in by_mac.items():
        if d['seq']:
            if d['seq'] not in rf_map:rf_map[d['seq']]=m
            elif rf_map[d['seq']]!=m:rf_map[d['seq']]=None
    events=collections.defaultdict(lambda:collections.defaultdict(list))
    unmatched=[]
    for path,txt in raw:
        station=station_for(path)
        if not station:continue
        base=pathlib.PurePosixPath(path).name
        mac=None
        if station=='RF':
            if '/Debug/' in path or '/debug/' in path:continue
            mt=re.match(r'^(MO\d{8}-\d{5})_',base,re.I)
            if mt:mac=rf_map.get(mt.group(1).upper())
            if not mac:unmatched.append(path);continue
        else:
            mt=re.match(r'^([0-9A-Fa-f]{12})-',base)
            if mt:mac=mt.group(1).upper()
        if not mac or mac not in by_mac:unmatched.append(path);continue
        tm=re.search(r'(20\d{6})[_-](\d{6})',base)
        sort_key=(tm.group(1)+tm.group(2) if tm else '00000000000000',base)
        events[mac][station].append({'path':path,'time':tm.group(1)+' '+tm.group(2) if tm else 'Log未提供檔名時間','sort_key':sort_key,'rows':row_map.get(path,[])})
    # Exact PCB Seq index; ambiguous identifiers must never resolve to an arbitrary unit.
    seq_to_macs=collections.defaultdict(set)
    sn_to_macs=collections.defaultdict(set)
    for mapped_mac, mapped_unit in by_mac.items():
        if mapped_unit['seq']:
            seq_to_macs[mapped_unit['seq'].upper()].add(mapped_mac)
        if mapped_unit['sn']:
            sn_to_macs[mapped_unit['sn'].upper()].add(mapped_mac)
    query_rows=[]; results=[];seen=set()
    for identifier in requested:
        if identifier in by_mac:
            candidates={identifier}
        elif identifier in seq_to_macs:
            candidates=seq_to_macs[identifier]
        elif identifier in sn_to_macs:
            candidates=sn_to_macs[identifier]
        else:
            candidates=set()
        if len(candidates)>1:
            query_rows.append([identifier,'TRACEABILITY CONFLICT',', '.join(sorted(candidates)),identifier if SEQ_RE.fullmatch(identifier) else '',identifier if identifier in sn_to_macs else '']);continue
        if not candidates:
            query_rows.append([identifier,'NOT FOUND','','','']);continue
        mac=next(iter(candidates))
        if mac in seen:
            query_rows.append([identifier,'DUPLICATE',mac,'','']);continue
        seen.add(mac)
        d=by_mac[mac]
        if any(mac in c[0] for c in conflicts):
            query_rows.append([identifier,'TRACEABILITY CONFLICT',mac,d['seq'],d['sn']]);continue
        if progress:progress('單機報告 '+mac)
        path=outdir/f'GRG4372_{mac}_Summary.xlsx'
        result=_write_unit(path,d,events.get(mac,{}),conflicts)
        results.append(result)
        query_rows.append([identifier,'GENERATED',mac,d['seq'],d['sn']])
    summary=Workbook.create();ws=summary.worksheets.add('查詢清單')
    _data(ws,['輸入識別碼','結果','MAC','PCB Seq','SN'],query_rows,[35,25,23,31,35])
    ws=summary.worksheets.add('複測總覽')
    _data(ws,['MAC','SN','PCB Seq','有複測的測站數','總複測次數','實際有Log測站數','報告檔案'],[[r['mac'],r['sn'],r['pcb_seq'],r['retry_stations'],r['retests'],r['stations_observed'],r['file']] for r in results],[21,35,28,21,17,21,76])
    ws=summary.worksheets.add('未配對與限制')
    _data(ws,['類別','來源','說明'],[['RF未精確配對',p,'RF識別碼未符合MES正確PCB Seq，不強制綁定'] for p in unmatched[:1000]]+[['MES衝突',p,reason] for m,p,reason in conflicts],[25,90,70])
    report=outdir/'GRG4372_Unit_Query_Index.xlsx'
    SpreadsheetFile.export_xlsx(summary).save(str(report))
    return {'generated':len(results),'missing':sum(x[1]=='NOT FOUND' for x in query_rows),'duplicate':sum(x[1]=='DUPLICATE' for x in query_rows),'conflicts':len(conflicts),'unmatched_sources':len(unmatched),'index':str(report),'reports':results}
