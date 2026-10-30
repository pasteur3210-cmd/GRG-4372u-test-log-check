import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from unit_summary import build_unit_summaries
import openpyxl

MAC1='3447630641BC'
MAC2='3447630641C6'
SEQ1='MO26100236-00014'
SEQ2='MO26100236-00015'

def log(mac,seq,sn=None):
    txt=f'[MES] 过站检查请求：{{"pcbSeq":"{seq}"}}\n'
    if sn:
        txt+=f'[MES] 字段读取请求：{{"pcbSeq":"{seq}","fieldName":"ksn"}}\n字段读取响应：{{"fieldValue":"{sn}"}}\n'
    return (f'InformationWrite/{mac}-写信息.log',txt)

class PCBSeqSearchTests(unittest.TestCase):
    def run_query(self,raw,ids):
        with TemporaryDirectory() as d:
            with patch('unit_summary._write_unit',return_value={'mac':MAC1,'sn':'','pcb_seq':SEQ1,'file':'mock','retry_stations':0,'retests':0,'stations_observed':0}):
                result=build_unit_summaries('unused',[],ids,d,raw_entries=raw)
            wb=openpyxl.load_workbook(str(Path(d)/'GRG4372_Unit_Query_Index.xlsx'),read_only=True)
            ws=wb['查詢清單']
            vals=[list(row) for row in ws.iter_rows(min_row=2,max_row=1+len(ids.splitlines()),max_col=5,values_only=True)]
            wb.close()
            return result,vals
    def test_pcb_seq_query(self):
        r,rows=self.run_query([log(MAC1,SEQ1)],SEQ1)
        self.assertEqual(r['generated'],1)
        self.assertEqual(rows[0][:4],[SEQ1,'GENERATED',MAC1,SEQ1])
    def test_mac_query_still_works(self):
        r,rows=self.run_query([log(MAC1,SEQ1)],MAC1)
        self.assertEqual(rows[0][1],'GENERATED')
    def test_sn_query_still_works(self):
        sn='26B4372UXXF-CF000014'
        r,rows=self.run_query([log(MAC1,SEQ1,sn)],sn)
        self.assertEqual(rows[0][1],'GENERATED')
    def test_unknown_seq(self):
        r,rows=self.run_query([log(MAC1,SEQ1)],'MO26100236-99999')
        self.assertEqual(rows[0][1],'NOT FOUND')
    def test_conflicting_seq(self):
        r,rows=self.run_query([log(MAC1,SEQ1),log(MAC2,SEQ1)],SEQ1)
        self.assertEqual(rows[0][1],'TRACEABILITY CONFLICT')
        self.assertEqual(r['generated'],0)
    def test_duplicate_aliases(self):
        r,rows=self.run_query([log(MAC1,SEQ1)],SEQ1+'\n'+MAC1)
        self.assertEqual(rows[1][1],'DUPLICATE')

if __name__=='__main__': unittest.main()
