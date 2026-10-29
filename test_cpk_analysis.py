import unittest
from cpk_analysis import capability,measure_info
class CpkTests(unittest.TestCase):
 def test_two_sided(self):
  a,s,c,k=capability([2.3,2.5,2.7],(2.0,3.0));self.assertAlmostEqual(a,2.5);self.assertAlmostEqual(c,0.8333333333,places=5);self.assertIn("雙側",k)
 def test_upper_only(self):
  a,s,c,k=capability([-40.,-42.,-44.],(None,-38.));self.assertAlmostEqual(c,2/3,places=5);self.assertIn('單側',k)
 def test_missing(self):self.assertIsNone(capability([1.,2.],(None,None))[2])
 def test_small(self):self.assertIsNone(capability([2.5],(2.3,2.7))[2])
 def test_log_limit_provenance(self):
  r=dict(category='BOB',item='BOB TX校準功率',result='PASS',actual=2.55,low_in_log='',high_in_log='',evidence='APC_Target=1234,The Power=2.55 dBm(2.30 dBm,2.70 dBm)')
  got=measure_info(r,{})
  self.assertEqual(got[6],(2.3,2.7))
  r['evidence']='Power=2.55 dBm';self.assertEqual(measure_info(r,{})[6],(None,None))
if __name__=='__main__':unittest.main()
