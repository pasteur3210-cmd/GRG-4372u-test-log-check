import tempfile,unittest,pathlib
from enhanced import audit
class StationReportTests(unittest.TestCase):
 def test_station_outputs(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'logs';p.mkdir()
   (p/'RF-LOG.txt').write_text('[TX][5180.00][11AX_HE20][MCS0][ANT1]\nEVM :[ -55.0 ]<[ -25.0 ]<[ -5.0 ]dB PASS',encoding='utf8')
   (p/'BOB.txt').write_text('APC_Target=1274,The Power=2.65 dBm(2.30 dBm,2.70 dBm)',encoding='utf8')
   x=audit(p,pathlib.Path(d)/'out')
   self.assertEqual(x['exceptions'],0)
   self.assertEqual(set(x['station_reports']),{'RF','BOB'})
   for f in [x['report'],*x['station_reports'].values()]:self.assertTrue(pathlib.Path(f).is_file())
   self.assertEqual(sum(v['files'] for v in x['report_allocation'].values()),2)
if __name__=='__main__':unittest.main()
