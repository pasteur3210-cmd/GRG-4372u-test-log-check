"""Separate RF/BOB PASS-only capability workbook; Kaian limits and actual log limits.

Metrics use the overall sample standard deviation. Consequently reported figures
are Ppk-type estimates, NOT subgroup-within Cpk, and PASS-only filtering creates
selection bias. Only the upper EVM bound is an approved limit.
"""
from collections import defaultdict
from statistics import mean, stdev
from math import isfinite
from pathlib import Path
import re
from excel_compat import Workbook, SpreadsheetFile

VALID={'PASS'}
BOB_STANDARDS={'BOB TX校準功率':(2.3,2.7),'BOB 消光比校準':(12.0,13.0)}
PARAMS={'MeasurePower':'power','TestPower':'power','EVM':'evm','FreqError':'frequency','SpectrumMask':'mask'}

def measure_info(r,rules):
    c=r['category']; item=str(r['item']); actual=r['actual']
    if c not in ('WiFi','BOB') or r['result'] not in VALID or isinstance(actual,bool) or not isinstance(actual,(int,float)) or not isfinite(actual):return None
    try:
        ll=float(r['low_in_log']) if r['low_in_log']!='' else None
        ul=float(r['high_in_log']) if r['high_in_log']!='' else None
    except (TypeError,ValueError):ll=ul=None
    if c=='BOB':
        if item not in BOB_STANDARDS:return None
        kaian=BOB_STANDARDS[item]
        # Parse actual limits from the SAME source Log line, never assume Kaian limits.
        raw=str(r.get('evidence',''))
        pairs=re.findall(r'(-?\d+(?:\.\d+)?)\s*dB[m]?\s*[,，~～-]\s*(-?\d+(?:\.\d+)?)\s*dB[m]?',raw,re.I)
        log=tuple(map(float,pairs[-1])) if pairs else ((ll,ul) if ll is not None and ul is not None else (None,None))
        return ('BOB',item,'','', '',kaian,log,float(actual),r)
    if c=='WiFi':
        band=item.split(' ',1)[0]; param=item.split(' ',1)[-1];mode=str(r['mode']);freq=r['freq_MHz'];ant=r['antenna']
        if param not in PARAMS:return None
        if '校准' in r['standard'] or 'Calibration' in r['standard']:
            kaian=(20.,21.) if param=='MeasurePower' else (-3.,3.) if param=='FreqError' else None
        else:
            spec=rules['wifi_verification'].get(band+'|'+mode,{}).get(PARAMS[param]); kaian=tuple(map(float,spec)) if spec else None
        if not kaian:return None
        if param=='EVM':kaian=(None,kaian[1]);log=(None,ul)
        else:log=(ll,ul)
        return ('RF',item,mode,str(freq),str(ant),kaian,log,float(actual),r)
    return None

def capability(values,limit):
    n=len(values);lo,hi=limit
    if n<2:return (None,None,None,'樣本數<2')
    avg=mean(values);sd=stdev(values)
    if sd<=1e-12:return (avg,sd,None,'σ=0；無法可靠計算')
    if lo is not None and hi is not None:
        val=min((hi-avg)/(3*sd),(avg-lo)/(3*sd));kind='雙側 Ppk估計（PASS-only）'
    elif hi is not None:val=(hi-avg)/(3*sd);kind='單側 Ppu估計（PASS-only）'
    elif lo is not None:val=(avg-lo)/(3*sd);kind='單側 Ppl估計（PASS-only）'
    else:return (avg,sd,None,'缺少核准規格')
    return (avg,sd,val,kind + ('；N<30僅參考' if n<30 else ''))

def collect(rows,rules):
    grouped=defaultdict(list)
    for r in rows:
        info=measure_info(r,rules)
        if info:
            station,item,mode,freq,ant,approved,log,val,orig=info
            grouped[(station,item,mode,freq,ant)].append((approved,log,val,orig))
    return grouped

def build(station,grouped,out):
    wb=Workbook.create();summary=wb.worksheets.add(station+'_CPK比較')
    headers=['測項','Mode','頻率 MHz','天線','採用標準','LSL','USL','PASS候選筆數','排除超規','納入N','Ppk／單側能力指標（整體σ）','指標類型與限制']
    summary.get_range_by_indexes(0,0,1,len(headers)).values=[headers]
    records=[];details=[]
    dhead=['測項','Mode','頻率 MHz','天線','來源Log','行號','實測值','採用標準','LSL','USL','是否納入','排除原因']
    for key,v in sorted(grouped.items()):
        st,item,mode,freq,ant=key
        if st!=station:continue
        for typ,idx in [('愷安 V1.1',0),('達天 Log 設定',1)]:
            limits=v[0][idx]
            if any(z is None for z in limits) and not (item.endswith('EVM') and limits[1] is not None):
                # Log limits missing: no fabricated limit or Cpk.
                limits=(None,None)
            sample=[];excluded=0
            for ka,log,val,r in v:
                low,high=limits
                admissible=(low is not None or high is not None) and (low is None or val>=low) and (high is None or val<=high)
                if admissible:sample.append(val)
                else:excluded+=1
                details.append([item,mode,freq,ant,str(r['file']),r['line'],val,typ,low,high,'納入' if admissible else '排除','' if admissible else '超出本規格／Limit缺失'])
            avg,sd,cpk,kind=capability(sample,limits)
            records.append([item,mode,freq,ant,typ,limits[0],limits[1],len(v),excluded,len(sample),cpk,kind if limits!=(None,None) else 'Log未記載有效上下限'])
    if records:
        for at in range(0,len(records),250):summary.get_range_by_indexes(at+1,0,len(records[at:at+250]),len(headers)).values=records[at:at+250]
    summary.get_range('A1:L1').format={'fill':'#173A59','font':{'color':'#FFFFFF','bold':True},'row_height':30}
    for col,width in {'A':27,'B':20,'C':17,'D':11,'E':20,'F':12,'G':12,'H':17,'I':13,'J':12,'K':26,'L':47}.items():summary.get_range(col+':'+col).format.column_width=width
    summary.freeze_panes.freeze_rows(1)
    det=wb.worksheets.add(station+'_樣本追溯');det.get_range_by_indexes(0,0,1,len(dhead)).values=[dhead]
    for at in range(0,len(details),300):det.get_range_by_indexes(at+1,0,len(details[at:at+300]),len(dhead)).values=details[at:at+300]
    det.get_range('A1:L1').format={'fill':'#173A59','font':{'color':'#FFFFFF','bold':True}}
    det.get_range('A:A').format.column_width=27;det.get_range('E:E').format.column_width=65
    det.get_range('B:D').format.column_width=16;det.get_range('F:L').format.column_width=20;det.freeze_panes.freeze_rows(1)
    note=wb.worksheets.add('統計說明');instructions=[
        ['項目','說明'],['計算範圍','僅使用程式判定 PASS 的量測；FAIL／不符合／待確認／規格差異均不納入'],
        ['兩套規格','同一 PASS 候選資料各自按愷安 V1.1、達天 Log Limit 過濾；超規筆數獨立紀錄'],
        ['雙側公式','min((USL-平均)/(3×樣本σ),(平均-LSL)/(3×樣本σ))'],
        ['單側公式','只有 USL 時為 (USL-平均)/(3×樣本σ)，稱 Ppu；只有 LSL 時為 Ppl'],
        ['重要統計限制','使用整體樣本標準差，故近似 Ppk/Ppu/Ppl 而非真正的組內σ Cpk；PASS-only會產生選擇偏差。平均與樣本σ用於內部運算，依V1.5.6需求不在主報表顯示'],
        ['分組','RF 依 Band／Mode／MHz／ANT／測項分組；BOB 依測項分組'],
        ['不計算','Eye Mask Success 等定性結果、未取得數值、PER單位歧義、未提供有效Limit、N<2'],
        ['BOB 規格','TX校準功率 2.3~2.7 dBm；ER校準 12~13 dB；均為雙側指標'],
        ['N<30','顯示數值供參考，樣本量不足不應視為正式製程能力驗收'],
        ['一致性','RF/BOB 獨立Cpk檔由 LogInspector 同一次執行產生，資料來自該次原始Log解析'],
        ['安全','不輸出 WPA 密碼明文'],]
    note.get_range_by_indexes(0,0,len(instructions),2).values=instructions
    note.get_range('A1:B1').format={'fill':'#173A59','font':{'bold':True,'color':'#FFFFFF'}}
    note.get_range('A:A').format.column_width=30;note.get_range('B:B').format.column_width=115
    SpreadsheetFile.export_xlsx(wb).save(str(out))
    return len(records),len(details)

def produce_cpk_reports(rows,files,outdir,stamp,rules):
    grouped=collect(rows,rules);output={}
    for station in ('RF','BOB'):
        target=Path(outdir)/('GRG4372_'+station+'_CPK_'+stamp+'.xlsx')
        build(station,grouped,target);output[station]=str(target)
    return output
