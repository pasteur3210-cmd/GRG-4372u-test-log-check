import unittest
from enhanced import category
from inspector import parse_wifi
from shipping_validator import pass_rules,DEFAULTS
class V11Tests(unittest.TestCase):
 def test_rf_path(self):self.assertEqual(category('RF-log/xxx_PASS.LOG',''), 'WiFi')
 def test_rf_content(self):self.assertEqual(category('data.LOG','[2G TX Verify][2442.00][11AX_HE20][MCS0][ANT1]\nEVM :[ -55 ]<[ -20 ]<[ -5 ]dB PASS\nMeasurePower'), 'WiFi')
 def test_evm_limit(self):
  rows=parse_wifi('rf.LOG','[2G TX Verify][2442.00][11AX_HE20][MCS0][ANT1]\nEVM :[ -55 ]<[ -36 ]<[ -35 ]dB PASS')
  self.assertEqual(rows[0]['result'],'規格差異')
 def test_key_reject(self):self.assertIn('KEY_BANNED_CHARACTER',pass_rules('Av!T4MnpQw0Y',DEFAULTS))
if __name__=='__main__':unittest.main()
