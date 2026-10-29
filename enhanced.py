"""V1.1 enhanced audit; content-based station identification and traceable logs."""
import argparse,collections,datetime,hashlib,json,pathlib,re,sys,traceback,zipfile
from inspector import decode,parse_wifi,checks,row,CONFIG
from shipping_validator import pass_rules,DEFAULTS
from report import make_report
VERSION='1.5.2'
DIR=pathlib.Path(__file__).resolve().parent

def entries(path):
 p=pathlib.Path(path)
 if p.suffix.lower()=='.zip':
  with zipfile.ZipFile(p) as z:
   for f in z.infolist():
    if f.is_dir() or not f.filename.lower().endswith(('.txt','.log')):continue
    if f.file_size>30_000_000 or '..' in pathlib.PurePosixPath(f.filename).parts:continue
    yield re.sub(r'#U([0-9A-Fa-f]{4})',lambda m:chr(int(m[1],16)),f.filename),decode(z.read(f))
 elif p.is_dir():
  for f in sorted(p.rglob('*')):
   if f.is_file() and f.suffix.lower() in ('.txt','.log'):yield str(f.relative_to(p)),decode(f.read_bytes())
 else:yield p.name,decode(p.read_bytes())

def category(path,txt):
 name=path.lower();head=txt[:12000].lower()
 if 'rf-log' in name or ('measurepower' in head and 'evm' in txt.lower() and 'ant1' in head):return 'WiFi'
 if 'bob' in name or 'lddla_1g' in head:return 'BOB'
 if '写信息' in name or '寫資訊' in name or 'nvram set wifissidsuffix' in head:return 'InformationWrite'
 if '信息核对' in name or '資訊核對' in name:return 'InformationCheck'
 if '流量' in name or 'iperf' in head:return 'Throughput'
 if '耦合' in name:return 'Coupling'
 return 'Other'

def writing(path,txt):
 from shipping_log_validator import check_log
 result=check_log(txt)
 out=[]
 evidence=result['evidence']
 for code,label in [('serial','SN工廠碼'),('ssid_set','SSID後綴'),('ssid_mes','MES SSID'),('key_mes','WPA Key'),('final','工站最終狀態')]:
  e=evidence.get(code,[])
  if not e:out.append(row(path,'Customization',label,'需要可追溯證據','未提供','缺少證據',0));continue
  value,line=e[-1]; masked='[已遮蔽；長度 '+str(len(value))+']' if code=='key_mes' else value
  issues=[i for i in result['issues'] if (i['field'] in ('WiFi WPA Key',) if code=='key_mes' else i['field'] in ('SSID',) if code in ('ssid_set','ssid_mes') else i['field'] in ('serial','Production test') )]
  status='不符合' if issues else 'PASS'
  out.append(row(path,'Customization',label,'R1.3／ShippingDataValidation V1.2.0',masked,status,line,'[secret redacted]' if code=='key_mes' else label,note='; '.join(i['code'] for i in issues)))
 hw=re.findall(r'nvram set HWver\s+([\d.]+)',txt,re.I)
 for m in re.finditer(r'nvram set HWver\s+([\d.]+)',txt,re.I):
  val=m.group(1);out.append(row(path,'Customization','HW Version','Micron=1.2',val,'PASS' if val=='1.2' else '不符合',txt.count('\n',0,m.start())+1,'HWver'))
 return out,result


def parse_bob_eye(path,txt):
 """Parse documented instrument eye-mask parameters, keep log decision and QA conclusion separate."""
 lines=txt.splitlines();start_rx=re.compile(r'Start\s+EYE\s+Mask\s+Margin\s+Test',re.I)
 starts=[i for i,l in enumerate(lines) if start_rx.search(l)];out=[]
 if not starts:
  if '调试' in path or '調試' in path:
   out.append(row(path,'BOB','Eye Mask Margin Test','30% mask, ≥300 wfms, Failed Samples=0, Success','未找到測試區塊','待確認',0,note='調試Log缺少EYE Mask測試區塊；須核對是否另有紀錄'))
  return out
 for run,idx in enumerate(starts):
  # Limit block to next test / next Mask start; avoid inheriting a success from another run.
  end=starts[run+1] if run+1<len(starts) else min(len(lines),idx+95)
  for k in range(idx+1,end):
   if re.search(r'^\s*(?:Start\s+(?!EYE)|\d+[.]\s*[^:]{5,}Test|End\s+EYE)',lines[k],re.I):end=k;break
  block=lines[idx:end];body='\n'.join(block)
  def find(pattern):
   m=re.search(pattern,body,re.I);return m.group(1) if m else None
  wf=find(r':ACQ:RUNTIL\s+WAVEFORMS\s*,\s*(\d+)')
  margin=find(r':MTEST:MMAR:PERC\s+(-?\d+(?:\.\d+)?)')
  failed=find(r'FailedSmpls\s*:\s*(-?\d+(?:\.\d+)?)')
  success=bool(re.search(r'Mask\s+Test\s+Success\s*!',body,re.I))
  failure=bool(re.search(r'Mask\s+Test\s+Fail(?:ed|ure)?\b',body,re.I))
  evidence=next((lines[k] for k in range(idx,end) if 'Mask Test' in lines[k] and 'Start' not in lines[k]),lines[idx]); evline=next((k+1 for k in range(idx,end) if 'Mask Test Success' in lines[k] or re.search(r'Mask\s+Test\s+Fail',lines[k],re.I)),idx+1)
  if failure or (failed is not None and float(failed)>0) or (wf is not None and int(wf)<300) or (margin is not None and abs(float(margin)-30)>1e-5):state='FAIL'
  elif wf is not None and margin is not None and failed is not None and success:state='PASS'
  else:state='待確認'
  actual=f'Margin={margin if margin is not None else "未記錄"}%; Waveforms設定={wf if wf is not None else "未記錄"}; FailedSmpls={failed if failed is not None else "未記錄"}; LogSuccess={success}'
  note='波形數為儀器擷取設定值，不等同於實際完成波形數的獨立回讀證據。'
  if state=='待確認':note+=' 不完整或未能判斷的證據不得判PASS。'
  out.append(row(path,'BOB','Eye Mask Margin Test','Margin=30%; Waveforms設定≥300; FailedSmpls=0; Mask Test Success!',actual,state,evline,evidence,note=note))
 return out

def parse_bob(path,txt):
 out=checks(path,txt,'BOB')
 # Legacy free-text Margin interpretation is not sufficiently tied to same Mask attempt.
 out=[r for r in out if r['item'] not in ('BOB Eye Margin','眼圖波形數')]
 out.extend(parse_bob_eye(path,txt))
 return out

def parse_coupling(path,txt):
 """Extract per-antenna compensated CW1600 power and the limit from the same test block."""
 lines=txt.splitlines(); starts=[i for i,l in enumerate(lines) if re.search(r'^\s*##\s*测试项：\s*(?:2\.4G|5G)\s*天线\s*\d+\s*功率',l)]
 out=[]
 for i,start in enumerate(starts):
  end=starts[i+1] if i+1<len(starts) else len(lines)
  # Stop at next (different) test section; don't consume status from elsewhere.
  for j in range(start+1,end):
   if re.search(r'^\s*##\s*测试项：',lines[j]):end=j;break
  head=lines[start]; band='2.4G' if '2.4G' in head else '5G'; antm=re.search(r'天线\s*(\d+)',head);ant='ANT'+str(int(antm.group(1))+1) if antm else ''
  block=lines[start:end]
  for j,l in enumerate(block):
   m=re.search(r'补偿后功率\s*[：:]\s*(-?\d+(?:\.\d+)?)\s*dBm',l,re.I)
   if not m:continue
   v=float(m.group(1));low=high=None;limit_line=0
   for k in range(j+1,min(j+13,len(block))):
    lm=re.search(r'标准范围\s*[：:]\s*(-?\d+(?:\.\d+)?)\s*[~～]\s*(-?\d+(?:\.\d+)?)\s*dBm',block[k],re.I)
    if lm: low,high=float(lm.group(1)),float(lm.group(2));limit_line=start+k+1;break
   if low is None:
    out.append(row(path,'Coupling',f'{band} {ant} NFT功率','愷安 V1.1: 17.5~25.5 dBm',v,'待確認',start+j+1,l,ant=ant,note='Log 未顯示可配對的標準範圍，無法核實實際程式 Limit'))
   else:
    # Kaian V1.1 NFT 2.4G/5G 54M CH3/CH40 both 17.5~25.5.
    actual_pass=17.5<=v<=25.5
    status='規格差異' if abs(low-17.5)>1e-6 or abs(high-25.5)>1e-6 else 'PASS' if actual_pass and low<=v<=high else 'FAIL'
    out.append(row(path,'Coupling',f'{band} {ant} NFT功率','17.5~25.5 dBm (愷安V1.1 NFT)',v,status,start+j+1,l,ant=ant,low=low,high=high,note=f'Log 標準範圍行號 {limit_line}；使用補償後功率，不使用儀表原始功率'))
 if not out:
  out.append(row(path,'Coupling','NFT 功率量測','須有逐天線補償後功率及Limit','未找到可配對量測','待確認',0,note='已辨識耦合站，但無法確認數值測試；非產品FAIL'))
 return out

def audit(input_path,outdir,progress=None):
 outdir=pathlib.Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
 def notify(message):
  if progress:progress(message)
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 execution=outdir/f'RUN_LOG_{stamp}.txt'; test=outdir/f'TEST_LOG_{stamp}.csv';debug=outdir/f'DEBUG_RECORD_{stamp}.txt';report=outdir/f'GRG4372_Audit_{stamp}.xlsx'
 rows=[];files=[];counts=collections.Counter();exception_count=0;sn_to_files=collections.defaultdict(set);write_count=0
 with execution.open('w',encoding='utf-8') as run,debug.open('w',encoding='utf-8') as dbg,test.open('w',encoding='utf-8') as tlog:
  def emit(msg):run.write(datetime.datetime.now().isoformat(timespec='seconds')+' '+msg+'\n');run.flush()
  tlog.write('file,category,status,item,line\n')
  emit(f'START version={VERSION} input_name={pathlib.Path(input_path).name} policy=FULL_AUDIT')
  notify('開始讀取並分類 Log')
  for path,txt in entries(input_path):
   c=category(path,txt);counts[c]+=1
   try:
    r=parse_wifi(path,txt) if c=='WiFi' else parse_bob(path,txt) if c=='BOB' else parse_coupling(path,txt) if c=='Coupling' else checks(path,txt,c)
    if c=='InformationWrite':
     r,extra=writing(path,txt);write_count+=1
     sn=extra['values'].get('SN');
     if sn:sn_to_files[sn].add(path)
    if c=='InformationCheck':r+=checks(path,txt,c)
    if not r:r=[row(path,'ParserStatus','解析覆蓋狀態','解析器需擴充','未取得可解析測項','待確認',0,note=f'來源工站={c}，非實際測試項目，不可計入測試項PASS/FAIL')]
    for a in r:
     tlog.write('"'+path.replace('"','')+'",'+c+','+a['result']+','+str(a['item']).replace(',',';')+','+str(a['line'])+'\n')
    rows.extend(r);files.append({'file':path,'category':c,'lines':len(txt.splitlines()),'findings':len(r)})
    dbg.write('FILE sha256='+hashlib.sha256(txt.encode('utf-8')).hexdigest()+' station='+c+' measures='+str(len(r))+' file='+path+'\n')
    if len(files)%10==0:notify(f'已解析 {len(files)} 份 Log：{c} / {pathlib.PurePosixPath(path).name}')
   except Exception as ex:
    exception_count+=1;dbg.write('ERROR '+path+': '+traceback.format_exc()+'\n');emit('ERROR file='+path+' error='+type(ex).__name__)
    rows.append(row(path,c,'解析例外','必須成功解析',type(ex).__name__,'待確認',0));files.append({'file':path,'category':c,'lines':len(txt.splitlines()),'findings':0})
  # rule: per-file zeros must never be confused with a passing RF measurement
  for expected in ['WiFi','BOB','InformationWrite','InformationCheck','Throughput','Coupling']:
   if not counts[expected]:rows.append(row('—','Coverage',expected,'必要工站','未發現','缺少證據',0))
  states=collections.Counter(r['result'] for r in rows if r['category']!='ParserStatus')
  emit('STATION_COUNTS '+json.dumps(counts,ensure_ascii=False))
  emit('RESULT_COUNTS '+json.dumps(states,ensure_ascii=False))
  emit(f'FILES={len(files)} WRITE_LOGS={write_count} EXCEPTIONS={exception_count}')
  notify('解析完成，正在產生總報告 Excel')
  make_report(rows,files,states,report,CONFIG)
  # One full workbook plus one independent workbook per station, preserving original findings.
  station_defs=[('RF','WiFi',('WiFi',)),('BOB','BOB',('BOB',)),
                ('Throughput','Throughput',('Throughput',)),('Coupling','Coupling',('Coupling',)),
                ('InformationWrite','InformationWrite',('InformationWrite',)),
                ('InformationCheck','InformationCheck',('InformationCheck',))]
  station_reports={};allocation={}
  for label,file_cat,cats in station_defs:
   subset_files=[f for f in files if f['category'] in cats]
   names={f['file'] for f in subset_files}
   subset=[r for r in rows if r['file'] in names]
   # Exclude missing-station markers from individual station reports; they remain in the full report.
   if not subset_files:continue
   target=outdir/f'GRG4372_{label}_{stamp}.xlsx'
   notify(f'正在輸出 {label} Excel（{len(subset_files)} 份 Log）')
   make_report(subset,subset_files,collections.Counter(r['result'] for r in subset if r['category']!='ParserStatus'),target,CONFIG)
   station_reports[label]=str(target)
   allocation[label]={'files':len(subset_files),'rows':len(subset)}
   emit('STATION_REPORT='+label+' files='+str(len(subset_files))+' rows='+str(len(subset))+' path='+str(target))
  from cpk_analysis import produce_cpk_reports
  notify('正在計算並輸出 RF／BOB 良品 Cpk')
  cpk_reports=produce_cpk_reports(rows,files,outdir,stamp,CONFIG)
  for key,value in cpk_reports.items():emit('CPK_REPORT='+key+' path='+value)
  emit('REPORT='+str(report));emit('STATION_REPORT_SUMMARY '+json.dumps(allocation,ensure_ascii=False));emit('END')
  notify('完成：全部 Excel 與 Run/Test/Debug Log 已輸出')
 return {'report':str(report),'run_log':str(execution),'test_log':str(test),'debug_log':str(debug),'files':len(files),'stations':dict(counts),'results':dict(states),'exceptions':exception_count,'station_reports':station_reports,'cpk_reports':cpk_reports,'report_allocation':allocation}

def gui(input_path,outdir):
 import tkinter as tk,threading,queue,os
 from tkinter import ttk,messagebox
 root=tk.Tk();root.title('GRG4372 LogInspector V1.5.2｜執行狀態');root.geometry('760x440');root.minsize(640,360)
 frame=ttk.Frame(root,padding=14);frame.pack(fill='both',expand=True)
 ttk.Label(frame,text='GRG-4372u 產測 Log 自動查核',font=('Microsoft JhengHei UI',15,'bold')).pack(anchor='w')
 ttk.Label(frame,text='來源：'+str(input_path),wraplength=710).pack(anchor='w',pady=(8,4))
 status=tk.StringVar(value='準備開始');ttk.Label(frame,textvariable=status).pack(anchor='w',pady=5)
 bar=ttk.Progressbar(frame,mode='indeterminate');bar.pack(fill='x',pady=6);bar.start(12)
 display=tk.Text(frame,height=13,wrap='word',state='disabled');display.pack(fill='both',expand=True)
 actions=ttk.Frame(frame);actions.pack(fill='x',pady=(8,0));open_btn=ttk.Button(actions,text='開啟報告資料夾',state='disabled',command=lambda:os.startfile(os.path.abspath(outdir)));open_btn.pack(side='right')
 q=queue.Queue();result_holder={}
 def worker():
  try:result_holder['result']=audit(input_path,outdir,progress=lambda msg:q.put(('progress',msg)));q.put(('done','完成'))
  except BaseException as ex:
   import traceback;result_holder['error']=traceback.format_exc();q.put(('error',str(ex)))
 def poll():
  try:
   while True:
    typ,msg=q.get_nowait()
    if typ=='progress':
     status.set(msg);display.configure(state='normal');display.insert('end',msg+'\n');display.see('end');display.configure(state='disabled')
    elif typ=='done':
     bar.stop();bar.configure(mode='determinate',value=100);status.set('✅ 執行完成：'+str(result_holder['result']['files'])+' 份 Log，報告已輸出');open_btn.configure(state='normal');messagebox.showinfo('查核完成','全部輸出完成。\n\n請點擊「開啟報告資料夾」查看 RF／BOB Excel 與執行紀錄。')
    else:
     bar.stop();status.set('❌ 執行失敗：'+msg);display.configure(state='normal');display.insert('end',result_holder.get('error','')+'\n');display.configure(state='disabled');messagebox.showerror('查核失敗',msg+'\n請檢查Debug記錄')
  except queue.Empty:pass
  if bar.cget('mode')=='indeterminate':root.after(120,poll)
 threading.Thread(target=worker,daemon=True).start();root.after(120,poll);root.mainloop()
 return 0 if 'result' in result_holder else 2

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('input',nargs='?');p.add_argument('-o','--output-dir',default='audit_output');args=p.parse_args(argv)
 if not args.input:
  import tkinter as tk
  from tkinter import filedialog
  root=tk.Tk();root.withdraw();args.input=filedialog.askopenfilename(title='選擇ZIP／LOG',filetypes=[('Log archives','*.zip *.log *.txt')]);root.destroy()
  if not args.input:return 1
  return gui(args.input,args.output_dir)
 try:
  result=audit(args.input,args.output_dir,progress=lambda msg:print(msg,flush=True));print(json.dumps(result,ensure_ascii=False,indent=2));return 0
 except Exception as e:print(type(e).__name__,str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
