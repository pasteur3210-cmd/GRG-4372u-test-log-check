import unittest
from throughput_parser import parse_throughput
from inspector import decode
class ThroughputTests(unittest.TestCase):
 def setUp(self):
  self.log="""Total Result:PASS
The information of Port Statistics:
4(1,1,4) Speed_10G Full 1518 7.5 609557 609555 0 0 0.00000000% 0
12(1,2,4) Speed_10G Full 1518 1.5 121911 121912 0 0 0.00000000% 0
29(1,3,13) Speed_1000M Full 1518 15 121911 121912 0 0 0.00000000% 0
30(1,3,14) Speed_1000M Full 1518 15 121911 121911 0 0 0.00000000% 0
31(1,3,15) Speed_1000M Full 1518 15 121911 121911 0 0 0.00000000% 0
32(1,3,16) Speed_1000M Full 1518 15 121911 121911 0 0 0.00000000% 0
The information of Stream Statistics:
4(1,1,4)-12(1,2,4) 1.5 121912 121912 0 0% 0 0 --
4(1,1,4)-29(1,3,13) 1.5 121912 121912 0 0% 0 0 --
4(1,1,4)-30(1,3,14) 1.5 121911 121911 0 0% 0 0 --
4(1,1,4)-31(1,3,15) 1.5 121911 121911 0 0% 0 0 --
4(1,1,4)-32(1,3,16) 1.5 121911 121911 0 0% 0 0 --
12(1,2,4)-4(1,1,4) 1.5 121911 121911 0 0% 0 0 --
29(1,3,13)-4(1,1,4) 15 121911 121911 0 0% 0 0 --
30(1,3,14)-4(1,1,4) 15 121911 121911 0 0% 0 0 --
31(1,3,15)-4(1,1,4) 15 121911 121911 0 0% 0 0 --
32(1,3,16)-4(1,1,4) 15 121911 121911 0 0% 0 0 --"""
 def test_counts(self):
  rows=parse_throughput('log',self.log)
  self.assertEqual(sum(r['item'].startswith('Port ') for r in rows),6)
  self.assertEqual(sum(r['item'].startswith('Stream ') for r in rows),10)
 def test_result(self):
  rows=parse_throughput('log',self.log)
  self.assertEqual(sum(r['result']=='PASS' for r in rows),17)
  self.assertEqual(sum(r['result']=='待確認' for r in rows),0)
 def test_errors(self):
  log=self.log.replace('609555 0 0 0.00000000% 0','609555 2 0 0.00000000% 0',1)
  self.assertTrue(any(r['result']=='FAIL' for r in parse_throughput('log',log)))
 def test_no_fabricated_mbps(self):
  rows=parse_throughput('log',self.log)
  self.assertFalse(any(r['item']=='PON→LAN 實際吞吐量' for r in rows))
if __name__=='__main__': unittest.main()
