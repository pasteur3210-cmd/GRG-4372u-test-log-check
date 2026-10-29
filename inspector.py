"""GRG-4372u production log checker. Standard: Kaian V1.1 and DIG R1.3."""
from __future__ import annotations
import argparse, json, re, zipfile, pathlib, io, sys
from collections import Counter
from datetime import datetime

ROOT=pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
CONFIG=json.loads((ROOT/'rules.json').read_text(encoding='utf-8'))
MEASURE=re.compile(r'(?P<name>MeasurePower|TestPower|FreqError|FrequencyError|EVM|SpectrumMask|Spectrum Mask|PER|RxPER|RxPackets|PacketCount|PowerIndex)\s*:\s*\[\s*(?P<low>-?\d+(?:\.\d+)?)\s*\]\s*<\s*\[\s*(?P<value>-?\d+(?:\.\d+)?)\s*\]\s*<\s*\[\s*(?P<high>-?\d+(?:\.\d+)?)\s*\]\s*(?P<unit>\w+|%)?\s*(?P<status>PASS|FAIL)?',re.I)
CONTEXT=re.compile(r'\[(?P<station>[^\[\]]{2,35}?)\]\[(?P<freq>\d{4}\.\d+)\]\[(?P<mode>[^\]]+)\]\[(?P<rate>[^\]]+)\]\[(?P<ant>ANT\d+)\]',re.I)
MODEMAP={'11G_OFDM':'OFDM54','11A_OFDM':'OFDM54','11AX_HE20':'HE20-MCS0','11AX_HE40':'HE40-MCS11','11AX_HE80':'HE80-MCS11','11AX_HE160':'HE160-MCS11','11BE_EHT40':'EHT40-MCS13','11BE_EHT160':'EHT160-MCS13'}
EXCLUDED=set(CONFIG['customization']['excluded_chars'])

def decode(b):
 for encoding in ('utf-8-sig','gb18030','big5'):
  try:return b.decode(encoding)
  except UnicodeDecodeError:continue
 return b.decode('utf-8',errors='replace')

def iter_files(path):
 path=pathlib.Path(path)
 if path.is_dir():
  for f in sorted(path.rglob('*')):
   if f.is_file() and f.suffix.lower() in ('.log','.txt'):
    yield f.name,decode(f.read_bytes())
 elif path.suffix.lower()=='.zip':
  with zipfile.ZipFile(path) as z:
   for item in z.infolist():
    if item.is_dir() or not item.filename.lower().endswith(('.log','.txt')):continue
    if '..' in pathlib.PurePosixPath(item.filename).parts or item.file_size>30_000_000:continue
    name=re.sub(r'#U([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),item.filename)
    yield pathlib.PurePosixPath(name).name,decode(z.read(item))
 else:yield path.name,decode(path.read_bytes())

def classify(name):
 n=name.lower()
 if 'wifi' in n:return 'WiFi'
 if 'bob' in n:return 'BOB'
 if '写入' in n or '寫入' in n:return 'InformationWrite'
 if '网页' in n or '網頁' in n or 'telnet' in n:return 'InformationCheck'
 if '流量' in n:return 'Throughput'
 if '耦合' in n:return 'Coupling'
 return 'Other'

def row(file,category,item,standard,actual,status,line,evidence='',mode='',freq='',ant='',low='',high='',note=''):
 return {'file':file,'category':category,'item':item,'mode':mode,'freq_MHz':freq,'antenna':ant,'standard':standard,'low_in_log':low,'high_in_log':high,'actual':actual,'result':status,'line':line,'evidence':evidence[:220],'note':note}

def wifi_spec(category,band,mode,param):
 if '校准' in category or '校準' in category:
  if param=='MeasurePower':return (20,21,'Calibration TX Power')
  if param=='FreqError':return (-3,3,'Calibration frequency')
  return None
 p={'TestPower':'power','MeasurePower':'power','EVM':'evm','FreqError':'frequency','SpectrumMask':'mask','PER':'per','RxPER':'per'}.get(param)
 if not p:return None
 v=CONFIG['wifi_verification'].get(f'{band}|{mode}',{})
 return (*v[p], f'{band} {mode} {p}') if p in v else None

def parse_wifi(name,s):
 rows=[];context='';freq='';mode='';ant='';band='';category=''; station=''
 for i,line in enumerate(s.splitlines(),1):
  c=CONTEXT.search(line)
  if c:
   station=c['station'];freq=float(c['freq']);ant=c['ant']; band='2.4G' if freq<3000 else '5G'
   r=c['rate'].upper();m=c['mode'].upper()
   if 'EHT160' in m or 'EHT160' in r:mode='EHT160-MCS13'
   elif 'EHT40' in m or 'EHT40' in r:mode='EHT40-MCS13'
   elif 'HE160' in m or 'HE160' in r:mode='HE160-MCS11'
   elif 'HE80' in m or 'HE80' in r:mode='HE80-MCS11'
   elif 'HE40' in m or 'HE40' in r:mode='HE40-MCS11'
   elif 'HE20' in m or 'HE20' in r:mode='HE20-MCS0'
   elif '11AX' in m:mode='HE20-MCS0' if 'MCS0' in r else 'HE80-MCS11' if 'MCS11' in r else 'Unknown AX'
   elif '11BE' in m:mode='EHT160-MCS13' if '160' in m else 'EHT40-MCS13'
   elif 'OFDM' in m:mode='OFDM54'
   else:mode=m+' '+r
  mt=MEASURE.search(line)
  if not mt:continue
  p=mt['name'].replace(' ','');p={'TestPower':'TestPower','MeasurePower':'MeasurePower','FrequencyError':'FreqError','SpectrumMask':'SpectrumMask','RxPER':'RxPER','PacketCount':'PacketCount'}.get(p,p)
  low=float(mt['low']);val=float(mt['value']);high=float(mt['high']);log_status=(mt['status'] or '').upper()
  if not log_status:log_status='PASS' if low<=val<=high else 'FAIL'
  is_cal='校准' in station or '校準' in station
  k='校准' if is_cal else 'TXRX驗證'
  spec=wifi_spec(k,band,mode,p)
  if spec:
   lo,hi,desc=spec
   if p in ('PER','RxPER') and mt['unit']=='%':
    status='待確認';standard=f'{lo:g}~{hi:g} packets ({desc})'
    note='Log記錄PER百分比，核准標準用封包數；不可直接比較，需確認測試定義與轉換'
   elif p=='EVM':
    # Kaian V1.1 EVM has only a high (negative dB) limit; no approved lower bound.
    delta='一致' if abs(hi-high)<1e-5 else '差異'
    status='規格差異' if delta=='差異' else ('PASS' if val<=hi and log_status=='PASS' else 'FAIL')
    standard=f'≤ {hi:g} dB ({desc}; 文件未定義Low)';note=f'Log判定={log_status}; EVM High Limit {delta}; Log Low不作核准比較'
   else:
    delta='一致' if abs(lo-low)<1e-5 and abs(hi-high)<1e-5 else '差異'
    status='規格差異' if delta=='差異' else ('PASS' if lo<=val<=hi and log_status=='PASS' else 'FAIL')
    standard=f'{lo:g} ~ {hi:g} ({desc})';note=f'Log判定={log_status}; Limit {delta}'
  else:status='待確認';standard='未建立對應核准規格';note='需確認 Mode/測項；不以 Log PASS 取代核准規格'
  rows.append(row(name,'WiFi',f'{band} {p}',standard,val,status,i,line,mode,freq,ant,low,high,note))
 return rows

def checks(name,s,category):
 result=[];lines=s.splitlines(); joined='\n'.join(lines)
 def scan(pattern,label,expected,validator,scope='Customization'):
  found=False
  for i,l in enumerate(lines,1):
   m=re.search(pattern,l,re.I)
   if not m:continue
   found=True;value=m.group(1).strip(); status='PASS' if validator(value) else '不符合'
   result.append(row(name,scope,label,expected,value,status,i,l))
  return found
 if category in ('InformationWrite','InformationCheck'):
  scan(r'(?:nvram set SerialNum|SerialNum\s*[:=]|(?:Device\s*)?SN\s*[:=])\s*([0-9A-Za-z-]{15,24})','SN工廠碼','20字元；第13-14碼 CH',lambda v: len(v)==20 and v[12:14]=='CH')
  scan(r'(?:nvram set HWver|HWver\s*[:=]|HW\s*version\s*[:=:])\s*([\d.]+)','HW Version','Micron Flash -> 1.2',lambda v:v=='1.2')
  scan(r'WiFiSSIDSuffix\s*[:=]\s*([a-zA-Z0-9]{4})','SSID後綴','4碼英數，排除易混淆字元',lambda v:len(v)==4 and not any(c in EXCLUDED for c in v))
  scan(r'\b(?:DIGIFIBRA(?:-PLUS)?)-([A-Za-z0-9]{4})\b','SSID後綴','4碼英數，排除易混淆字元',lambda v:len(v)==4 and not any(c in EXCLUDED for c in v))
  scan(r'(?:nvram set (?:ssid_suffix|ssidSuffix)|SSID_suffix\s*[:=])\s*([A-Za-z0-9]{4})','SSID後綴','4碼英數，排除易混淆字元',lambda v:len(v)==4 and not any(c in EXCLUDED for c in v))
  scan(r'(?:Firmware version|Firmware Version|FirmwareVer|FW\s*Version)\s*[:=]\s*([A-Za-z0-9.-]+)','FW版本','出貨 DIG-1.0.6；生產 FTY-1.0.0b5',lambda v:v in ('DIG-1.0.6','FTY-1.0.0b5'))
  # Do not export real password values.
  for i,l in enumerate(lines,1):
   if re.search(r'(?i)(?:Wifi\s*Key|WPA\s*Key|UserPassword|RootPassword)\s*[:=]',l):
    result.append(row(name,'Customization','Password','12字元；大小寫/數字/合法特殊字元且唯一','[不輸出密碼]','待確認',i,'[Sensitive data redacted]',note='需解析可信欄位及跨設備查重，不可僅以文字找到密碼即放行'))
 if category=='Throughput':
  for i,l in enumerate(lines,1):
   if re.search(r'Total Result\s*:\s*(PASS|FAIL)',l,re.I):
    result.append(row(name,'Throughput','網口流量','標準 >=800；需每port實測值','Test summary '+re.search(r'(PASS|FAIL)',l,re.I)[1].upper(),'待確認',i,l,note='總體PASS無法證明每port >=800；須逐port證據'))
 if category=='BOB':
  for pat,label,lo,hi in [(r'APC_Target=\d+,The Power=\s*(-?\d+\.\d+)','BOB TX校準功率',2.3,2.7),(r'Target_ER=\s*\d+[^\n]*?(?:=|：)\s*(-?\d+\.\d+)\s*dB','BOB 消光比校準',12,13),(r'Margin(?:余量百分比)?\s*[:=]\s*(\d+(?:\.\d+)?)','BOB Eye Margin',30,100)]:
   for i,l in enumerate(lines,1):
    m=re.search(pat,l,re.I)
    if m:
     v=float(m[1]);result.append(row(name,'BOB',label,f'{lo:g}~{hi:g}',v,'PASS' if lo<=v<=hi else '不符合',i,l))
  if any('Margin' in l for l in lines) and not re.search(r'(?i)(?:wfms|waveforms)\s*[:=]\s*[3-9]\d\d',joined):
   result.append(row(name,'BOB','眼圖波形數','>=300 wfms','未見可確認數量','待確認',0,'',note='沒有波形數不代表一定未測'))
 return result

def inspect(inputpath,pass_only=False):
 rows=[];file_rows=[];types=set()
 for name,s in iter_files(inputpath):
  typ=classify(name);types.add(typ)
  r=parse_wifi(name,s) if typ=='WiFi' else []
  r+=checks(name,s,typ)
  file_rows.append({'file':name,'category':typ,'lines':len(s.splitlines()),'findings':len(r)})
  rows+=r
 # PASS-only: keep only positive measurements, but retain critical customization violations and evidence gaps.
 if pass_only: rows=[r for r in rows if r['category'] in ('Customization',) or r['result'] in ('PASS','規格差異','待確認','不符合')]
 for needed in ('WiFi','BOB','InformationWrite','InformationCheck','Throughput','Coupling'):
  if needed not in types:rows.append(row('—','Coverage',needed,'應確認測站是否需要','未提供對應LOG','缺少證據',0))
 stats=dict(Counter(r['result'] for r in rows))
 return rows,file_rows,stats

def main(argv=None):
 ap=argparse.ArgumentParser(description='GRG-4372u QA log inspector')
 ap.add_argument('input',nargs='?',help='ZIP, log, or folder');ap.add_argument('-o','--output',default='GRG4372_Audit.xlsx');ap.add_argument('--pass-only',action='store_true');args=ap.parse_args(argv)
 if not args.input:
  from tkinter import Tk,filedialog,messagebox
  root=Tk();root.withdraw();path=filedialog.askopenfilename(title='選擇測試 Log ZIP / LOG',filetypes=[('Logs','*.zip *.LOG *.log *.txt'),('All','*.*')]);root.destroy()
  if not path:return 1
  args.input=path
 rows,files,stats=inspect(args.input,args.pass_only)
 from report import make_report
 make_report(rows,files,stats,args.output,CONFIG)
 print('Saved:',args.output,'|',stats)
 return 0
if __name__=='__main__':sys.exit(main())
