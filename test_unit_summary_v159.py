import unittest
from unit_summary import identify,station_for,status_for,MAC_RE

class UnitSummaryTests(unittest.TestCase):
 def test_mes_pair_and_sn(self):
  txt='''[MES] 获取重复值请求：{"fieldName":"lanmac","fieldValue":"3447630641BC"}\n[MES] 过站检查请求：{"pcbSeq":"MO26100236-00016"}\n[MES] 字段读取请求：{"pcbSeq":"MO26100236-00016","fieldName":"ksn"}\n  MES 字段“ksn”读取成功，值：26B4372UXXF-CH000016。\n  字段读取响应：{"isSuccess":true,"fieldValue":"26B4372UXXF-CH000016"}\n'''
  mp,sm,c=identify([('D/3447630641BC-写信息.log',txt)])
  self.assertEqual(mp['3447630641BC']['seq'],'MO26100236-00016')
  self.assertEqual(sm['26B4372UXXF-CH000016'],'3447630641BC')
  self.assertEqual(c,[])
 def test_conflict(self):
  one='{"pcbSeq":"MO26100236-00016"}'
  two='{"pcbSeq":"MO26100236-00017"}'
  m,s,c=identify([('D/3447630641BC-写信息.log',one),('D/3447630641BC-信息核对.log',two)])
  self.assertEqual(len(c),1)
 def test_station(self):
  self.assertEqual(station_for('D/RF-log/MO26100236-00016_20261020_142235_PASS.LOG'),'RF')
  self.assertEqual(station_for('D/3447630641BC-BOB测试.txt'),'BOB測試')
  self.assertEqual(station_for('D/3447630641BC-流量.log'),'Throughput')
 def test_status(self):
  self.assertEqual(status_for({'rows':[{'result':'PASS'}]}),'PASS')
  self.assertEqual(status_for({'rows':[{'result':'PASS'},{'result':'FAIL'}]}),'FAIL')
  self.assertEqual(status_for({'rows':[] }),'NO EVIDENCE')
if __name__=='__main__':unittest.main()
