import unittest
from inspector import parse_wifi, checks

class RuleTests(unittest.TestCase):
 def test_freq_limit_diff(self):
  x='[12:00][频偏校准][2437.00][11G_OFDM][54Mbps][ANT1]\nFreqError :[ -2 ]<[ 0.2 ]<[ 2 ]ppm PASS'
  a=parse_wifi('WiFi.LOG',x)
  self.assertEqual(a[0]['result'],'規格差異')
 def test_evm_uses_only_approved_high(self):
  x='[12:00][2G TX Verify][2437.00][11AX_HE20][MCS0][ANT1]\nEVM :[ -55 ]<[ -20 ]<[ -5 ]dB PASS'
  a=parse_wifi('WiFi.LOG',x)
  self.assertEqual(a[0]['result'],'PASS')
 def test_per_units_not_equal(self):
  x='[12:00][RX Verify][5180.00][11AX_HE20][MCS0][ANT1]\nPER :[ 0 ]<[ 0 ]<[ 10 ]% PASS'
  a=parse_wifi('WiFi.LOG',x)
  self.assertEqual(a[0]['result'],'待確認')
 def test_factory_and_hw(self):
  a=checks('a.log','nvram set SerialNum 26B4372UXXF-CF000016\nnvram set HWver 1.1','InformationWrite')
  self.assertEqual([x['result'] for x in a],['不符合','不符合'])
 def test_ssid_excluded(self):
  a=checks('a.log','WiFiSSIDSuffix=rhh0','InformationWrite')
  self.assertEqual(a[0]['result'],'不符合')
if __name__=='__main__':unittest.main()
