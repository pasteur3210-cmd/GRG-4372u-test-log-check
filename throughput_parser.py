"""TeleATT port/stream statistics parser with explicit throughput evidence separation."""
import re
from inspector import row

_PORT_RE=re.compile(r'^\s*(\d+\([\d,]+\))\s+(Speed_(?:10G|\d+M))\s+(Full|Half)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s*$',re.I)
_STREAM_RE=re.compile(r'^\s*(\d+\([\d,]+\)-\d+\([\d,]+\))\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s+(\d+)\s+(?:--|[\d.]+)\s*$',re.I)

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
            actual=f'Speed={speed}; Duplex={duplex}; Frame={frame}; Rate欄={rate}; TX={tx}; RX={rx}; FCS={fcs}; IPv4Check={iperr}; LostRate={loss}%; UDPCheck={udperr}'
            out.append(row(path,'Throughput',f'Port {port} 封包錯誤／遺失','FCS=0; IPv4/UDP Checksum=0; LostRate=0%',actual,state,n,line,note='只判封包計數/錯誤；Rate欄數值的單位未明，不能視為 Mbps。'))
        elif section=='stream':
            m=_STREAM_RE.match(line)
            if not m:continue
            stream,rate,tx,rx,lost,lostpct,seq,payload=m.groups();streams+=1
            state='PASS' if int(lost)==0 and float(lostpct)==0 and int(seq)==0 and int(payload)==0 else 'FAIL'
            actual=f'StreamRate={rate}(單位待確認); TX={tx}; RX={rx}; LostPacket={lost}; LostRate={lostpct}%; SeqError={seq}; PayloadError={payload}'
            out.append(row(path,'Throughput',f'Stream {stream} 丟包／封包錯誤','LostPacket=0; LostRate=0%; SeqError=0; PayloadError=0',actual,state,n,line,note='零丟包驗證；非吞吐量Mbps實測；若收發數差異需由設備定義確認。'))
    if total_match:
        logstate=total_match.group(1).upper()
        n=txt.count('\n',0,total_match.start())+1
        out.append(row(path,'Throughput','TeleATT 測站總結果','設備需輸出正式 PASS；並保留實際測試證據',logstate,'PASS' if logstate=='PASS' else 'FAIL',n,lines[n-1],note=f'Port={ports}, Stream={streams}；站別 PASS 不等於 ≥800 Mbps。'))
    if not ports and not streams:
        out.append(row(path,'Throughput','Port／Stream 解析狀態','需有逐埠/逐流可追溯資料','無可解析 Port/Stream 數值','待確認',0,note='Log格式未支援；不是設備不良判定。'))
    out.append(row(path,'Throughput','PON→LAN 實際吞吐量','愷安V1.1網口流量測試 ≥800 Mbps','Log 未提供明確 Mbps 實測及 DUT PON→LAN 埠映射','待確認',0,note='測試儀顯示封包量、Rate/StreamRate，但不能從無單位欄位推定 ≥800 Mbps；需 TE 確認實際端口映射、流量速率定義及測試規格。'))
    return out
