import unittest
from unit_summary import failure_item,failure_origin,failure_key

class RetestTests(unittest.TestCase):
 def test_only_explicit_fail_all_stations(self):
  for station in ('WiFi','BOB','Throughput','Coupling','InformationWrite','InformationCheck'):
   with self.subTest(station=station):
    rows=[{'category':station,'item':'正常測項','result':'PASS','mode':'','freq_MHz':'','antenna':''},
          {'category':station,'item':'不良測項','result':'FAIL','mode':'','freq_MHz':'','antenna':''},
          {'category':station,'item':'規格差異但不宣稱FAIL','result':'規格差異','mode':'','freq_MHz':'','antenna':''}]
    self.assertEqual({k[0] for k in failure_origin(rows)},{'不良測項'})
 def test_missing_measure_not_a_failure(self):
  self.assertFalse(failure_item({'category':'ParserStatus','result':'FAIL'}))
  self.assertFalse(failure_item({'category':'WiFi','result':'待確認'}))
 def test_identity_contains_channel_antenna(self):
  a={'item':'EVM','mode':'HE20','freq_MHz':2422,'antenna':'ANT1'}
  b=dict(a,antenna='ANT2')
  self.assertNotEqual(failure_key(a),failure_key(b))
if __name__=='__main__':unittest.main()
