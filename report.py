from excel_compat import Workbook,SpreadsheetFile
from pathlib import Path

def make_report(rows,files,stats,out,rules,station=None):
 wb=Workbook.create()
 s=wb.worksheets.add('查核總覽')
 s.get_range('A1:D1').values=[['GRG-4372u Log 自動查核 V1.5.7','','','']]
 s.get_range('A3:B7').values=[['產品',rules['metadata']['model']],['測試依據',rules['metadata']['test_standard']],['客製化依據',rules['metadata']['production_notice']],['判定原則','測試標準與Log Limit分別核對；缺證據不判PASS'],['安全原則','報告不輸出密碼明文']]
 s.get_range('A9:B9').values=[['判定','筆數']]
 states=['PASS','不符合','規格差異','FAIL','待確認','缺少證據']
 s.get_range('A10:B15').values=[[x,stats.get(x,0)] for x in states]
 s.get_range('A17:B17').values=[['審查結論','存在「不符合／規格差異／FAIL」時，不建議直接放行；PASS Only 不能證明全流程良率']]
 s.get_range('A1:D1').format={'fill':'#13324D','font':{'bold':True,'color':'#FFFFFF','size':15},'row_height':30}
 s.get_range('A9:B9').format={'fill':'#225579','font':{'bold':True,'color':'#FFFFFF'}}
 s.get_range('A:A').format.column_width=28;s.get_range('B:B').format.column_width=70
 s.freeze_panes.freeze_rows(1)
 t=wb.worksheets.add('逐筆比對')
 # Per-station report: remove entirely blank columns, preserving audit essentials.
 # Aggregate report retains the full column set for cross-station filtering.
 cols=[('file','原始檔',42),('category','類別',16),('item','測試項目',31),
       ('mode','測試模式',22),('freq_MHz','頻率 MHz',15),('antenna','天線',13),
       ('standard','核准測試標準',40),('low_in_log','Log Low',15),
       ('high_in_log','Log High',15),('actual','實際測試值',22),
       ('result','判定',16),('line','原始行號',14),
       ('evidence','原始證據（截斷）',65),('note','備註',60)]
 data=[r for r in rows if r['category']!='ParserStatus']
 # No material evidence is deleted: drop a column only if it is blank in every record.
 if station:
  mandatory={'file','item','result','actual'}
  cols=[c for c in cols if c[0] in mandatory or any(r.get(c[0]) not in (None,'') for r in data)]
 headers=[h for k,h,w in cols]
 t.get_range_by_indexes(0,0,1,len(headers)).values=[headers]
 for offset in range(0,len(data),400):
  block=[[r.get(k,'') for k,h,w in cols] for r in data[offset:offset+400]]
  t.get_range_by_indexes(1+offset,0,len(block),len(headers)).values=block
 lastcol=chr(64+len(headers))
 t.get_range('A1:'+lastcol+'1').format={'fill':'#13324D','font':{'bold':True,'color':'#FFFFFF'},'row_height':32}
 for i,(k,h,width) in enumerate(cols):
  letter=chr(65+i)
  t.get_range(letter+':'+letter).format.column_width=width
 t.freeze_panes.freeze_rows(1)
 parser=wb.worksheets.add('程式解析紀錄')
 parser.get_range('A1:F1').values=[['原始檔','程式狀態','描述','原因','原始行號','說明']]
 prow=[[r['file'],r['category'],r['item'],r['actual'],r['line'],r['note']] for r in rows if r['category']=='ParserStatus']
 if prow:parser.get_range_by_indexes(1,0,len(prow),6).values=prow
 parser.get_range('A1:F1').format={'fill':'#225579','font':{'bold':True,'color':'#FFFFFF'}}
 parser.get_range('A:A').format.column_width=68
 parser.get_range('B:C').format.column_width=25
 parser.get_range('D:D').format.column_width=38
 parser.get_range('F:F').format.column_width=74
 parser.freeze_panes.freeze_rows(1)
 f=wb.worksheets.add('Log檔案索引');f.get_range('A1:D1').values=[['原始檔','類別','行數','已解析項目']]
 if files:f.get_range_by_indexes(1,0,len(files),4).values=[[r[k] for k in ['file','category','lines','findings']] for r in files]
 f.get_range('A1:D1').format={'fill':'#13324D','font':{'bold':True,'color':'#FFFFFF'}}
 f.get_range('A:A').format.column_width=45;f.get_range('B:D').format.column_width=18
 d=wb.worksheets.add('使用說明')
 notes=[['查核方式','說明'],['標準來源','愷安 V1.1 (PDF)；DIG 生產注意事項 R1.3 (Word)'],['PASS判定','只有能對應標準且數值/Limit滿足時PASS'],['規格差異','Log設定上下限與核准標準不一致'],['待確認','規則尚未支援、欄位證據不足或測試條件不一致'],['原始行號','回到 Log 指定行核對原文'],['密碼','不輸出密碼；格式與全量唯一性須另外驗證'],['已知限制','不同測試程式的 EVM / Spectrum Mask / PER 定義或量測格式可能不同，未能解讀者不判PASS'],['校準與驗證','校準不等於成品 RF 驗證；兩者分開查核'],['生產/出貨 FW','應由站別與出貨階段確認版本；不能因生產測試看到 FTY 而判出貨違規'],['非完整放行工具','需 RD/QA 審核規格、MES/設備追溯、重測與實機驗證'],['ParserStatus','只列於程式解析紀錄，不列入測試明細及產品結果統計']]
 d.get_range_by_indexes(0,0,len(notes),2).values=notes
 d.get_range('A1:B1').format={'fill':'#13324D','font':{'bold':True,'color':'#FFFFFF'}}
 d.get_range('A:A').format.column_width=24;d.get_range('B:B').format.column_width=110
 SpreadsheetFile.export_xlsx(wb).save(str(out))
