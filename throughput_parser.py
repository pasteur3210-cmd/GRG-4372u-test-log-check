"""TeleATT port/stream statistics parser with explicit throughput evidence separation."""
import re
from inspector import row

_PORT_RE=re.compile(r'^\s*(\d+\([\d,]+\))\s+(Speed_(?:10G|\d+M))\s+(Full|Half)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s*$',re.I)
_STREAM_RE=re.compile(r'^\s*(\d+\([\d,]+\)-\d+\([\d,]+\))\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s+(\d+)\s+(?:--|[\d.]+)\s*$',re.I)

def _mbps(speed, rate):
    """Convert tester configured rate-percent of link speed into nominal Mbps."""
    m=re.fullmatch(r'Speed_(10G|\d+M)', speed, re.I)
    if not m: return None
    link=10000.0 if m.group(1).upper()=='10G' else float(m.group(1)[:-1])
    return round(link*float(rate)/100.0, 6)

def parse_throughput(path,txt):
    lines=txt.splitlines(); out=[]; section=None; ports=streams=0
    total_match=re.search(r'^\s*Total Result\s*:\s*(PASS|FAIL)\s*$',txt,re.M|re.I)
    for n,line in enumerate(lines,1):
        if 'The information of Port Statistics' in line: section='port';continue
        if 'The information of Stream Statistics' in line:section='stream';continue
        if section=='port':
            m=_PORT_RE.match(line)
            if not m:continue
            port,speed,duplex,frame,rate,tx,rx,fcs,iperr,loss,udperr=m.groups()
            ports+=1
            errs=[int(fcs),int(iperr),int(udperr)]
            lossval=float(loss)
            state='PASS' if not any(errs) and lossval==0 else 'FAIL'
            actual=f'Speed={speed}; Rate={rate}%; 設定頻寬={_mbps(speed,rate):g} Mbps; Duplex={duplex}; Frame={frame}; TX={tx}; RX={rx}; FCS={fcs}; IPv4Check={iperr}; LostRate={loss}%; UDPCheck={udperr}'
            out.append(row(path,'Throughput',f'Port {port} 封包錯誤／遺失','FCS=0; IPv4/UDP Checksum=0; LostRate=0%',actual,state,n,line,note='Rate按鏈路Speed百分比換算為測試儀設定頻寬；不是實際PON→LAN有效吞吐量。'))
        elif section=='stream':
            m=_STREAM_RE.match(line)
            if not m:continue
            stream,rate,tx,rx,lost,lostpct,seq,payload=m.groups();streams+=1
            state='PASS' if int(lost)==0 and float(lostpct)==0 and int(seq)==0 and int(payload)==0 else 'FAIL'
            actual=f'StreamRate={rate}%; 基準Speed=1G(依工站規則); 設定頻寬={float(rate)*10:g} Mbps; TX={tx}; RX={rx}; LostPacket={lost}; LostRate={lostpct}%; SeqError={seq}; PayloadError={payload}'
            out.append(row(path,'Throughput',f'Stream {stream} 丟包／封包錯誤','LostPacket=0; LostRate=0%; SeqError=0; PayloadError=0',actual,state,n,line,note='StreamRate按工站確認的1G基準換算設定頻寬；零丟包核對；不是PON→LAN實際吞吐量。'))
    if total_match:
        logstate=total_match.group(1).upper()
        n=txt.count('\n',0,total_match.start())+1
        out.append(row(path,'Throughput','TeleATT 測站總結果','設備需輸出正式 PASS；並保留實際測試證據',logstate,'PASS' if logstate=='PASS' else 'FAIL',n,lines[n-1],note=f'Port={ports}, Stream={streams}；站別 PASS 不等於 ≥800 Mbps。'))
    if not ports and not streams:
        out.append(row(path,'Throughput','Port／Stream 解析狀態','需有逐埠/逐流可追溯資料','無可解析 Port/Stream 數值','待確認',0,note='Log格式未支援；不是設備不良判定。'))
    # V1.5.8: The station-confirmed Port/Stream evidence is reported above.
    # Do not create a synthetic unverified PON→LAN record for every unit.
    # Port/Stream configured bandwidth is NOT a measured PON→LAN goodput certification.
    return out
