import unittest
from enhanced import parse_bob_eye

HEAD='Start EYE Mask Margin Test...\n:ACQ:RUNTIL WAVEFORMS,300\n:MTEST:MMAR:PERC 30\nMargin余量百分比=30.000000 %\nFailedSmpls: 0.00\n'
class EyeTests(unittest.TestCase):
 def case(self,tail):return parse_bob_eye('unit-BOB调试.txt',HEAD+tail)[0]['result']
 def test_pass(self):self.assertEqual(self.case('Mask Test Success!'),'PASS')
 def test_missing_success(self):self.assertEqual(self.case(''), '待確認')
 def test_missing_section(self):self.assertEqual(parse_bob_eye('unit-BOB调试.txt','foo')[0]['result'],'待確認')
 def test_fail_samples(self):self.assertEqual(self.case('FailedSmpls: 3\nMask Test Success!'),'PASS') if False else self.assertEqual(parse_bob_eye('x',HEAD.replace('FailedSmpls: 0.00','FailedSmpls: 3.00')+'Mask Test Success!')[0]['result'],'FAIL')
 def test_wrong_margin(self):self.assertEqual(parse_bob_eye('x',HEAD.replace('MMAR:PERC 30','MMAR:PERC 20')+'Mask Test Success!')[0]['result'],'FAIL')
 def test_waveforms_short(self):self.assertEqual(parse_bob_eye('x',HEAD.replace('WAVEFORMS,300','WAVEFORMS,200')+'Mask Test Success!')[0]['result'],'FAIL')
 def test_explicit_fail(self):self.assertEqual(self.case('Mask Test Failed!'),'FAIL')
if __name__=='__main__':unittest.main()
