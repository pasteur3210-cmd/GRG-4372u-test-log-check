"""V1.1 enhanced audit; content-based station identification and traceable logs."""
import argparse,collections,datetime,hashlib,json,pathlib,re,sys,traceback,zipfile
from inspector import decode,parse_wifi,checks,row,CONFIG
from shipping_validator import pass_rules,DEFAULTS
from report import make_report
from throughput_parser import parse_throughput
VERSION='1.5.10'
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
 """Parse actual compensated power, logged limits and CW1600 frequency per antenna.

 No PASS is inferred from a station filename, and no neighboring block's limits
 may be borrowed. Missing/ambiguous readings remain explicit review items.
 """
 lines=txt.splitlines()
 start_rx=re.compile(r'^\s*##\s*测试项\s*[：:]\s*(2\.4G|5G)\s*天线\s*(\d+)\s*功率')
 starts=[(i,m) for i,line in enumerate(lines) if (m:=start_rx.search(line))]
 out=[]
 for idx,(start,m) in enumerate(starts):
  end=starts[idx+1][0] if idx+1<len(starts) else len(lines)
  # Never cross into unrelated test item, even when antenna count differs.
  for k in range(start+1,end):
   if re.search(r'^\s*##\s*测试项\s*[：:]',lines[k]):end=k;break
  block=lines[start:end]
  band=m.group(1);ant=f'ANT{int(m.group(2))+1}'
  freqs=[(float(mm.group(1)),start+j+1) for j,line in enumerate(block)
         if (mm:=re.search(r'信道频点\s*[：:]\s*(\d+(?:\.\d+)?)\s*MHz',line,re.I))]
  freq=freqs[-1][0] if freqs else ''
  expected_freq=2422.0 if band=='2.4G' else 5200.0 # NFT V1.1 CH3 / CH40
  for j,line in enumerate(block):
   pm=re.search(r'补偿后功率\s*[：:]\s*(-?\d+(?:\.\d+)?)\s*dBm',line,re.I)
   if not pm:continue
   val=float(pm.group(1)); low=high=None;limit_line=0
   # The next limit belongs to this reading only if no subsequent reading intervenes.
   for k in range(j+1,min(j+14,len(block))):
    if re.search(r'补偿后功率\s*[：:]',block[k],re.I):break
    lm=re.search(r'标准范围\s*[：:]\s*(-?\d+(?:\.\d+)?)\s*[~～]\s*(-?\d+(?:\.\d+)?)\s*dBm',block[k],re.I)
    if lm:
     low,high=float(lm.group(1)),float(lm.group(2));limit_line=start+k+1;break
   item=f'{band} {ant} NFT 補償後功率'
   standard=f'{band} NFT CH{3 if band=="2.4G" else 40} ({expected_freq:g} MHz): 17.5~25.5 dBm'
   if low is None:
    state='待確認';note='未取得同一測試段的Log Low/High，不可判定PASS'
   elif len(set(x[0] for x in freqs))>1 or not freqs:
    state='待確認';note='缺少或存在不一致的量測頻率；須確認 Channel'
   elif abs(freq-expected_freq)>1e-6:
    state='規格差異';note=f'測試頻率{freq:g}MHz不同於核准NFT {expected_freq:g}MHz'
   elif abs(low-17.5)>1e-6 or abs(high-25.5)>1e-6:
    state='規格差異';note='Log Limit不同於愷安NFT核准17.5~25.5 dBm'
   else:
    state='PASS' if low<=val<=high else 'FAIL'
    note='補償後功率與Log Limit及愷安NFT標準逐項核對'
   out.append(row(path,'Coupling',item,standard,val,state,start+j+1,line,
                  mode='NFT CW1600',freq=freq,ant=ant,
                  low='' if low is None else low,high='' if high is None else high,
                  note=f'{note}；Limit行號={limit_line or "缺少"}；原始量測不等於補償後功率'))
 if not out:
  out.append(row(path,'Coupling','NFT 功率量測','需逐天線補償後功率及Log Limit','未找到可配對量測','待確認',0,
   note='未辨識到NFT測項；非產品FAIL，須更新解析或提供完整Log'))
 return out

def audit(input_path,outdir,progress=None,unit_ids=None):
 outdir=pathlib.Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
 def notify(message):
  if progress:progress(message)
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 execution=outdir/f'RUN_LOG_{stamp}.txt'; test=outdir/f'TEST_LOG_{stamp}.csv';debug=outdir/f'DEBUG_RECORD_{stamp}.txt';report=outdir/f'GRG4372_Audit_{stamp}.xlsx'
 rows=[];files=[];counts=collections.Counter();exception_count=0;sn_to_files=collections.defaultdict(set);write_count=0
 with execution.open('w',encoding='utf-8') as run,debug.open('w',encoding='utf-8') as dbg,test.open('w',encoding='utf-8-sig') as tlog:
  def emit(msg):run.write(datetime.datetime.now().isoformat(timespec='seconds')+' '+msg+'\n');run.flush()
  tlog.write('file,category,status,item,line\n')
  emit(f'START version={VERSION} input_name={pathlib.Path(input_path).name} policy=FULL_AUDIT')
  notify('開始讀取並分類 Log')
  for path,txt in entries(input_path):
   c=category(path,txt);counts[c]+=1
   try:
    r=parse_wifi(path,txt) if c=='WiFi' else parse_bob(path,txt) if c=='BOB' else parse_coupling(path,txt) if c=='Coupling' else parse_throughput(path,txt) if c=='Throughput' else checks(path,txt,c)
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
   make_report(subset,subset_files,collections.Counter(r['result'] for r in subset if r['category']!='ParserStatus'),target,CONFIG,station=label)
   station_reports[label]=str(target)
   allocation[label]={'files':len(subset_files),'rows':len(subset)}
   emit('STATION_REPORT='+label+' files='+str(len(subset_files))+' rows='+str(len(subset))+' path='+str(target))
  from cpk_analysis import produce_cpk_reports
  notify('正在計算並輸出 RF／BOB 良品 Cpk')
  cpk_reports=produce_cpk_reports(rows,files,outdir,stamp,CONFIG)
  for key,value in cpk_reports.items():emit('CPK_REPORT='+key+' path='+value)
  if unit_ids:
   from unit_summary import build_unit_summaries
   summaries=build_unit_summaries(input_path,rows,unit_ids,outdir/'Unit_Summary',progress=notify)
   emit('UNIT_SUMMARIES '+json.dumps(summaries,ensure_ascii=False))
  else:summaries=None
  emit('REPORT='+str(report));emit('STATION_REPORT_SUMMARY '+json.dumps(allocation,ensure_ascii=False));emit('END')
  notify('完成：全部 Excel 與 Run/Test/Debug Log 已輸出')
 return {'report':str(report),'run_log':str(execution),'test_log':str(test),'debug_log':str(debug),'files':len(files),'stations':dict(counts),'results':dict(states),'exceptions':exception_count,'station_reports':station_reports,'cpk_reports':cpk_reports,'report_allocation':allocation,'unit_summaries':summaries}

def gui(input_path,outdir,unit_ids=None):
 """Persistent Tk GUI: audit once, then query more units from the in-memory rows.
    All Excel/file work is on a worker, all Tk calls stay on the main thread.
 """
 import tkinter as tk, threading, queue, os, time
 from tkinter import ttk, messagebox
 from unit_summary import build_unit_summaries
 root=tk.Tk();root.title('GRG4372 LogInspector '+VERSION+'｜查核與單機查詢')
 root.geometry('930x670');root.minsize(770,550)
 frame=ttk.Frame(root,padding=12);frame.pack(fill='both',expand=True)
 ttk.Label(frame,text='GRG-4372u 產測 Log 自動查核',font=('Microsoft JhengHei UI',15,'bold')).pack(anchor='w')
 source=tk.StringVar(value=str(input_path));status=tk.StringVar(value='可開始分析')
 source_frame=ttk.Frame(frame);source_frame.pack(fill='x',pady=5)
 ttk.Label(source_frame,text='Log來源：').pack(side='left')
 ttk.Entry(source_frame,textvariable=source).pack(side='left',fill='x',expand=True)
 state={'busy':False,'ready':False,'rows':None,'input':None,'last':None,'raw':None};q=queue.Queue()
 bar=ttk.Progressbar(frame,mode='indeterminate');bar.pack(fill='x',pady=(4,3))
 ttk.Label(frame,textvariable=status).pack(anchor='w',pady=2)
 actions=ttk.Frame(frame);actions.pack(fill='x',pady=5)
 unit_frame=ttk.LabelFrame(frame,text='單機／多機 Summary 查詢（每行一個 MAC／SN）',padding=8);unit_frame.pack(fill='x',pady=4)
 ids=tk.Text(unit_frame,height=5,wrap='word');ids.pack(fill='both',expand=True)
 if unit_ids:ids.insert('1.0',unit_ids)
 unit_actions=ttk.Frame(unit_frame);unit_actions.pack(fill='x',pady=4)
 display=tk.Text(frame,height=15,wrap='word',state='disabled');display.pack(fill='both',expand=True)
 footer=ttk.Frame(frame);footer.pack(fill='x',pady=5)
 def append(msg):
  display.configure(state='normal');display.insert('end',str(msg)+'\n');display.see('end');display.configure(state='disabled')
 def buttons():
  audit_btn.configure(state='disabled' if state['busy'] else 'normal')
  query_btn.configure(state='normal' if state['ready'] and not state['busy'] else 'disabled')
  browse_btn.configure(state='disabled' if state['busy'] else 'normal')
 def launch(task):
  if state['busy']:return
  state['busy']=True;buttons();bar.start(15)
  def worker():
   try:q.put(('done',task(),None))
   except BaseException as ex:q.put(('error',str(ex),__import__('traceback').format_exc()))
  threading.Thread(target=worker,daemon=True).start()
 def do_audit():
  path=source.get().strip()
  if not path or not pathlib.Path(path).is_file():messagebox.showerror('來源錯誤','請選擇有效的 ZIP／Log 檔');return
  state['ready']=False;state['rows']=None;state['input']=None;state['raw']=None
  def task():
   result=audit(path,outdir,progress=lambda msg:q.put(('progress',msg)))
   # Cache the parsed rows once for repeated independent unit queries.
   row_cache=[];raw_cache=list(entries(path))
   for name,txt in raw_cache:
    c=category(name,txt)
    try:
     rr=parse_wifi(name,txt) if c=='WiFi' else parse_bob(name,txt) if c=='BOB' else parse_coupling(name,txt) if c=='Coupling' else parse_throughput(name,txt) if c=='Throughput' else checks(name,txt,c)
     if c=='InformationWrite':rr,_=writing(name,txt)
     if c=='InformationCheck':rr+=checks(name,txt,c)
     row_cache.extend(rr)
    except Exception as ex:q.put(('progress','單機索引解析警示：'+name+' '+str(ex)))
   return ('audit',result,row_cache,path,raw_cache)
  status.set('正在分析整批 Log');launch(task)
 def do_query():
  values=ids.get('1.0','end').strip()
  if not values:messagebox.showwarning('輸入資料','請輸入至少一組 MAC 或 SN');return
  if not state['ready']:messagebox.showwarning('請先分析','請先執行整批 Log 分析');return
  path=state['input'];rows=state['rows'];raw_cache=state['raw']
  def task():
   output=pathlib.Path(outdir)/'Unit_Summary'
   res=build_unit_summaries(path,rows,values,output,progress=lambda msg:q.put(('progress',msg)),raw_entries=raw_cache)
   return ('query',res)
  status.set('正在產生單機 Summary');launch(task)
 def browse():
  from tkinter import filedialog
  new=filedialog.askopenfilename(title='選擇 Log ZIP',filetypes=[('Log','*.zip *.log *.txt')])
  if new and new!=source.get():
   source.set(new);state['ready']=False;state['rows']=None;state['input']=None;state['raw']=None;append('來源已更新，需重新分析新 Log');buttons()
 browse_btn=ttk.Button(actions,text='更換 Log來源',command=browse);browse_btn.pack(side='left',padx=3)
 audit_btn=ttk.Button(actions,text='① 整批 Log 分析',command=do_audit);audit_btn.pack(side='left',padx=4)
 query_btn=ttk.Button(unit_actions,text='② 產生選定 MAC／SN Summary',command=do_query);query_btn.pack(side='right')
 ttk.Button(footer,text='開啟報告資料夾',command=lambda:os.startfile(os.path.abspath(outdir)) if hasattr(os,'startfile') else None).pack(side='right',padx=3)
 ttk.Button(footer,text='結束',command=root.destroy).pack(side='right',padx=3)
 buttons()
 def poll():
  try:
   while True:
    event=q.get_nowait()
    kind,payload=event[:2];extra=event[2] if len(event)>2 else None
    if kind=='progress':status.set(payload);append(payload)
    elif kind=='error':
     state['busy']=False;bar.stop();status.set('執行失敗：'+payload);append(extra);buttons();messagebox.showerror('執行失敗',payload)
    elif kind=='done':
     state['busy']=False;bar.stop()
     if payload[0]=='audit':
      _,result,row_cache,path,raw_cache=payload
      state.update(ready=True,rows=row_cache,input=path,last=result,raw=raw_cache)
      status.set('整批分析完成，已建立單機索引，可以繼續輸入 MAC／SN 查詢')
      append('整批完成：'+str(result['files'])+' 份 Log；單機索引 '+str(len(row_cache))+' 筆')
      if ids.get('1.0','end').strip():root.after(150,do_query)
     else:
      res=payload[1];status.set('完成：'+str(res['generated'])+' 份單機報告')
      append('單機報告 '+str(res['generated'])+' 份，找不到 '+str(res['missing'])+' 筆，查詢清單：'+res['index'])
     buttons()
  except queue.Empty:pass
  if root.winfo_exists():root.after(120,poll)
 root.after(120,poll);root.after(250,do_audit);root.mainloop()
 return 0

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('input',nargs='?');p.add_argument('-o','--output-dir',default='audit_output');p.add_argument('--unit-ids',default='',help='MAC/SN清單，逗號、空白或換行分隔');args=p.parse_args(argv)
 if not args.input:
  import tkinter as tk
  from tkinter import filedialog
  root=tk.Tk();root.withdraw();args.input=filedialog.askopenfilename(title='選擇ZIP／LOG',filetypes=[('Log archives','*.zip *.log *.txt')]);root.destroy()
  if not args.input:return 1
  return gui(args.input,args.output_dir,args.unit_ids)
 try:
  result=audit(args.input,args.output_dir,progress=lambda msg:print(msg,flush=True),unit_ids=args.unit_ids);print(json.dumps(result,ensure_ascii=False,indent=2));return 0
 except Exception as e:print(type(e).__name__,str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
