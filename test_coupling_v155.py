import unittest
from enhanced import parse_coupling

class CouplingTest(unittest.TestCase):
 def sample(self, freq='5200',value='25.060569',limit='17.5\t~\t25.5',part='5G',ant=0):
  return f"## 测试项：{part} 天线 {ant} 功率\n### 步骤：读取 {part} 天线 {ant} 功率\n[CW1600]\n  信道频点：{freq} MHz\n[判定脚本] 补偿后功率：\t{value}\tdBm\n[判定脚本] 标准范围：\t{limit}\tdBm\n"
 def test_example_pass(self):
  r=parse_coupling('3447630641BC-耦合.log',self.sample())
  self.assertEqual(len(r),1);self.assertEqual(r[0]['result'],'PASS');self.assertEqual(r[0]['freq_MHz'],5200)
  self.assertEqual(r[0]['actual'],25.060569);self.assertEqual(r[0]['high_in_log'],25.5)
 def test_above_high_is_fail(self):self.assertEqual(parse_coupling('x',self.sample(value='25.6'))[0]['result'],'FAIL')
 def test_missing_limit(self):self.assertEqual(parse_coupling('x',self.sample().replace('标准范围','不明范围'))[0]['result'],'待確認')
 def test_wrong_freq(self):self.assertEqual(parse_coupling('x',self.sample(freq='5220'))[0]['result'],'規格差異')
 def test_wrong_limit(self):self.assertEqual(parse_coupling('x',self.sample(limit='17.5~26.0'))[0]['result'],'規格差異')
 def test_24g(self):self.assertEqual(parse_coupling('x',self.sample(part='2.4G',freq='2422'))[0]['result'],'PASS')
 def test_empty(self):self.assertEqual(parse_coupling('x','Log empty')[0]['result'],'待確認')
