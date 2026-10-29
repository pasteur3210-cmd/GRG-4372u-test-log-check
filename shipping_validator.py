"""Shipping Data Validation Tool V1.1.1. Python 3.11."""
from __future__ import annotations
import collections, datetime, json, logging, re, secrets
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

VERSION='1.2.0'
DEFAULTS={
 'sn_start':'26A4372UXXF-CF000001','sn_end':'26A4372UXXF-CF031000',
 'mac_start':'A01842F8D4B7','mac_end':'A01842FD8FA6',
 'ssid_24_prefix':'DIGIFIBRA-','ssid_5_prefix':'DIGIFIBRA-PLUS-',
 'ssid_suffix_length':4,'ssid_suffix_regex':'[A-Za-z0-9]{4}',
 'require_ssid_suffix_match':True,'require_wifi_key_match':True,
 'allowed_special':'!%*+,.:=[]^_{}#@<>','password_length':12,
 'banned':'0oO1lIi9gq2zZDQ6b8B',
 'check_other_password_fields':False,
 'check_gpon_relation':True,
 'allow_duplicate_ssid':True,
 'mac_per_device':10,
 'check_mac_sn_mapping':True,
 'check_mac_block_overlap':True,
 'check_fixed_value_embedded':True,
}
MANDATORY=['CT S/N','MAC','WiFi 2.4G SSID','WiFi 5G SSID','WiFi 2.4G Key','WiFi 5G Key']
PASSWORD_FIELDS=['WiFi 2.4G Key','WiFi 5G Key']
EXTRA_PASSWORD_FIELDS=['Admin PSW','User account PSW']

def clean(v):
 return '' if v is None else str(v).strip()

def pass_rules(value, cfg):
 errors=[]; value=clean(value)
 if len(value)!=int(cfg['password_length']):errors.append('KEY_LENGTH')
 if not value.isascii():errors.append('KEY_NON_ASCII')
 if any(c in cfg['banned'] for c in value):errors.append('KEY_BANNED_CHARACTER')
 allowed=set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'+cfg['allowed_special'])
 if any(c not in allowed for c in value):errors.append('KEY_INVALID_CHARACTER')
 if not any('A'<=c<='Z' for c in value):errors.append('KEY_NO_UPPERCASE')
 if not any('a'<=c<='z' for c in value):errors.append('KEY_NO_LOWERCASE')
 if not any('0'<=c<='9' for c in value):errors.append('KEY_NO_DIGIT')
 if not any(c in cfg['allowed_special'] for c in value):errors.append('KEY_NO_SPECIAL')
 return errors

def validate_config(cfg):
 if not re.fullmatch(r'[0-9A-Fa-f]{12}',cfg['mac_start']) or not re.fullmatch(r'[0-9A-Fa-f]{12}',cfg['mac_end']):raise ValueError('MAC boundary must be 12 hex characters')
 if int(cfg['mac_start'],16)>int(cfg['mac_end'],16):raise ValueError('MAC start > end')
 pattern=r'^(.*?)(\d+)$'; a=re.match(pattern,cfg['sn_start']); b=re.match(pattern,cfg['sn_end'])
 if not a or not b or a.group(1)!=b.group(1) or len(a.group(2))!=len(b.group(2)) or int(a.group(2))>int(b.group(2)):raise ValueError('SN boundaries must share prefix/width and increase')
 if isinstance(cfg['mac_per_device'],bool) or not str(cfg['mac_per_device']).isdigit() or int(cfg['mac_per_device'])<1:raise ValueError('mac_per_device must be a positive integer')
 if int(cfg['password_length'])<1:raise ValueError('password_length invalid')
 if int(cfg['ssid_suffix_length'])<1:raise ValueError('ssid_suffix_length invalid')
 re.compile('^(?:'+cfg['ssid_suffix_regex']+')$')
 if set(cfg['allowed_special']) & set(cfg['banned']):raise ValueError('special and banned characters overlap')
 return a,b

def analyze(input_path, output_dir, config=None, progress=None):
 cfg={**DEFAULTS,**(config or {})}; a,b=validate_config(cfg)
 output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
 run=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(3)
 debug_path=output_dir/f'DEBUG_{run}.log'; execution_path=output_dir/f'EXECUTION_{run}.log'
 logger=logging.getLogger('ship_'+run);logger.setLevel(logging.DEBUG); logger.propagate=False
 f=logging.FileHandler(debug_path,encoding='utf-8');f.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));logger.addHandler(f)
 log=open(execution_path,'w',encoding='utf-8')
 input_wb=None
 report_wb=None
 def emit(message):log.write(datetime.datetime.now().isoformat(timespec='seconds')+' '+message+'\n');log.flush();logger.info(message)
 try:
  emit('START version='+VERSION+' input='+str(input_path));logger.debug('CONFIG='+json.dumps(cfg,ensure_ascii=False))
  input_wb=load_workbook(input_path,read_only=True,data_only=True)
  ws=input_wb.active
  itr=ws.iter_rows(values_only=True)
  headers=[clean(v) for v in next(itr)]
  if len(headers)!=len(set(headers)):raise ValueError('Duplicate column headers')
  missing=[h for h in MANDATORY if h not in headers]
  if missing:raise ValueError('Missing required columns: '+', '.join(missing))
  positions={name:i for i,name in enumerate(headers)}
  items=[]; seen_sn={};seen_mac={};seen_keys={};seen_ssid={}; mac_blocks=[]
  base_mac=int(cfg['mac_start'],16); max_mac=int(cfg['mac_end'],16); mac_count=int(cfg['mac_per_device'])
  for rownum,row in enumerate(itr,2):
   if not any(v is not None and clean(v) for v in row):continue
   vals={name:clean(row[i] if i<len(row) else None) for name,i in positions.items()}
   problems=[]
   def fail(field,code,detail):problems.append((field,code,detail))
   sn=vals['CT S/N'];mac=vals['MAC'].upper()
   match=re.fullmatch(re.escape(a.group(1))+r'(\d{'+str(len(a.group(2)))+r'})',sn)
   if not match:fail('CT S/N','SN_FORMAT','Expected '+a.group(1)+' + '+str(len(a.group(2)))+' digits')
   elif not int(a.group(2))<=int(match.group(1))<=int(b.group(2)):fail('CT S/N','SN_OUT_OF_RANGE',sn)
   if sn in seen_sn:fail('CT S/N','SN_DUPLICATE','First row '+str(seen_sn[sn]))
   else:seen_sn[sn]=rownum
   if not re.fullmatch('[0-9A-F]{12}',mac):fail('MAC','MAC_FORMAT','Expected exactly 12 hexadecimal characters')
   elif not int(cfg['mac_start'],16)<=int(mac,16)<=int(cfg['mac_end'],16):fail('MAC','MAC_OUT_OF_RANGE',mac)
   if mac in seen_mac:fail('MAC','MAC_DUPLICATE','First row '+str(seen_mac[mac]))
   else:seen_mac[mac]=rownum
   if re.fullmatch('[0-9A-F]{12}',mac):
    mac_num=int(mac,16); end_mac=mac_num+mac_count-1
    if end_mac>max_mac or mac_num<base_mac:
     fail('MAC','MAC_BLOCK_OUT_OF_RANGE',f'Occupied MAC block {mac}-{end_mac:012X} exceeds {cfg["mac_start"]}-{cfg["mac_end"]}')
    if (mac_num-base_mac)%mac_count:
     fail('MAC','MAC_STEP_ALIGNMENT',f'Base {cfg["mac_start"]}, allocation {mac_count}; start MAC is not block aligned')
    if cfg['check_mac_sn_mapping'] and match:
     expected=base_mac+(int(match.group(1))-int(a.group(2)))*mac_count
     if mac_num!=expected:
      fail('MAC','MAC_SN_MAPPING',f'SN {sn} should start at {expected:012X} for {mac_count} MAC/device, actual {mac}')
    mac_blocks.append((mac_num,end_mac,rownum,problems,mac))
   s24=vals['WiFi 2.4G SSID'];s5=vals['WiFi 5G SSID'];suffixes=[]
   for field,prefix,v in [('WiFi 2.4G SSID',cfg['ssid_24_prefix'],s24),('WiFi 5G SSID',cfg['ssid_5_prefix'],s5)]:
    suffix=v[len(prefix):] if v.startswith(prefix) else None
    if suffix is None or len(suffix)!=int(cfg['ssid_suffix_length']) or not re.fullmatch(cfg['ssid_suffix_regex'],suffix,flags=re.ASCII):fail(field,'SSID_FORMAT','Expected prefix '+prefix+' and '+str(cfg['ssid_suffix_length'])+' character suffix')
    suffixes.append(suffix)
    if not cfg['allow_duplicate_ssid'] and v in seen_ssid:fail(field,'SSID_DUPLICATE','First row '+str(seen_ssid[v]))
    else:seen_ssid[v]=rownum
   if cfg['require_ssid_suffix_match'] and suffixes[0]!=suffixes[1]:fail('SSID','SSID_SUFFIX_MISMATCH','2.4G/5G suffixes differ')
   fieldset=PASSWORD_FIELDS+(EXTRA_PASSWORD_FIELDS if cfg['check_other_password_fields'] else [])
   for field in fieldset:
    if field not in vals:fail(field,'KEY_COLUMN_MISSING','Missing password column');continue
    key=vals[field]
    for code in pass_rules(key,cfg):fail(field,code,'Value violates '+code)
    # Wi-Fi bands for a single device may share one key; cross-device uniqueness is enforced below.
    if key:
     origin=seen_keys.get((field if field in EXTRA_PASSWORD_FIELDS else 'wifi',key))
     if origin and origin!=rownum:fail(field,'KEY_DUPLICATE','First row '+str(origin))
     else:seen_keys[(field if field in EXTRA_PASSWORD_FIELDS else 'wifi',key)]=rownum
     if cfg['check_fixed_value_embedded'] and (key.casefold() in (sn.casefold(),mac.casefold()) or (len(key)>=6 and any(key.casefold() in x.casefold() for x in (sn,mac,s24,s5)))):
      fail(field,'KEY_FIXED_VALUE_SUSPECT','Password appears as fixed identifier substring')
   if cfg['require_wifi_key_match'] and vals[PASSWORD_FIELDS[0]]!=vals[PASSWORD_FIELDS[1]]:fail('WiFi Keys','WIFI_KEYS_MISMATCH','2.4G and 5G values differ')
   if cfg['check_gpon_relation']:
    if 'GPON SN' in vals:
     expected='CMTD'+mac[4:] if re.fullmatch('[0-9A-F]{12}',mac) else None
     if expected and vals['GPON SN'].upper()!=expected:fail('GPON SN','GPON_SN_MISMATCH','Expected '+expected)
    if 'GPON SN1' in vals and 'GPON SN' in vals:
     gp=vals['GPON SN'];expected=(gp[:4].encode('ascii').hex().upper()+gp[4:]) if len(gp)==12 and gp[:4].isascii() and re.fullmatch('[0-9A-Fa-f]{8}',gp[4:]) else None
     if expected and vals['GPON SN1'].upper()!=expected:fail('GPON SN1','GPON_SN1_MISMATCH','Expected '+expected)
   items.append((rownum,vals,problems))
   if rownum%1000==0:
    emit('CHECKED '+str(rownum-1)+' rows');
    if progress:progress(rownum-1)
  if cfg['check_mac_block_overlap']:
   mac_blocks.sort(key=lambda x:x[0])
   previous=None
   for block in mac_blocks:
    if previous is not None and block[0]<=previous[1]:
     block[3].append(('MAC','MAC_BLOCK_OVERLAP',f'Block {block[4]} overlaps row {previous[2]} ({previous[4]})'))
     previous[3].append(('MAC','MAC_BLOCK_OVERLAP',f'Block {previous[4]} overlaps row {block[2]} ({block[4]})'))
    if previous is None or block[1]>previous[1]:previous=block
  counts=collections.Counter(code for _,_,p in items for _,code,_ in p)
  failed=sum(bool(p) for _,_,p in items);total=len(items)
  report_path=output_dir/f'Shipping_Validation_{run}.xlsx'
  wb=Workbook();report_wb=wb;summary=wb.active;summary.title='Summary'
  for r in [('Shipping Data Validation','V'+VERSION),('Source file',Path(input_path).name),('Date',datetime.datetime.now().isoformat(timespec='seconds')),('Rows checked',total),('PASS',total-failed),('FAIL',failed),('Overall','PASS' if failed==0 else 'FAIL'),('Important','Random generation cannot be proven from Excel values alone.'),('Wi-Fi keys','Same key on 2.4G/5G of one device permitted; reuse across devices is FAIL.'),('MAC allocation',f'{mac_count} MAC/device; verify interval, alignment, SN mapping, and overlap'),('SSID duplicate','Allowed' if cfg['allow_duplicate_ssid'] else 'Not allowed')]:summary.append(r)
  summary.append([]);summary.append(['Error code','Count'])
  for code,n in sorted(counts.items()):summary.append([code,n])
  details=wb.create_sheet('Detail');details.append(['Excel row','Result','Error count','Error codes','Error messages']+headers)
  failures=wb.create_sheet('Failures');failures.append(['Excel row','Field','Error code','Message','SN','MAC'])
  for rownum,vals,p in items:
   details.append([rownum,'FAIL' if p else 'PASS',len(p),'; '.join(dict.fromkeys(code for _,code,_ in p)),' | '.join(f'{field}: {detail}' for field,_,detail in p)]+[vals.get(h,'') for h in headers])
   for field,code,msg in p:failures.append([rownum,field,code,msg,vals['CT S/N'],vals['MAC']])
  settings=wb.create_sheet('Rule Settings');settings.append(['Setting','Value'])
  for k,v in cfg.items():settings.append([k,str(v)])
  for sheet in wb:
   sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
   for c in sheet[1]:c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True);c.alignment=Alignment(wrap_text=True)
   for idx,col in enumerate(sheet.columns,1):
    if idx>35:break
    samples=[str(c.value or '') for c in list(col)[:50]]
    sheet.column_dimensions[get_column_letter(idx)].width=min(52,max(12,max(map(len,samples),default=12)+2))
  wb.save(report_path)
  wb.close()
  report_wb=None
  emit(f'FINISH total={total} pass={total-failed} fail={failed} report={report_path.name}')
  return {'report':str(report_path),'execution_log':str(execution_path),'debug_log':str(debug_path),'total':total,'pass':total-failed,'fail':failed,'errors':dict(counts)}
 except Exception:
  logger.exception('VALIDATION_FAILED');emit('ERROR: check debug log');raise
 finally:
  # On Windows an openpyxl read-only workbook retains the source ZIP handle.
  # TemporaryDirectory cleanup fails with WinError 32 unless it is closed.
  if input_wb is not None:input_wb.close()
  if report_wb is not None:report_wb.close()
  log.close();f.close();logger.removeHandler(f)
