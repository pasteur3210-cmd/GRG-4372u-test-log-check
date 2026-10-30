import unittest
from throughput_parser import parse_throughput
from test_throughput import ThroughputTests

class V157Tests(unittest.TestCase):
    def setUp(self):
        self.rows=parse_throughput('log',(lambda t: (t.setUp(), t.log)[1])(ThroughputTests()))
    def test_10g_7_5(self):
        self.assertIn('設定頻寬=750 Mbps',next(r['actual'] for r in self.rows if r['item'].startswith('Port 4(')))
    def test_1g_15(self):
        self.assertIn('設定頻寬=150 Mbps',next(r['actual'] for r in self.rows if r['item'].startswith('Port 29(')))
    def test_stream_1g(self):
        self.assertIn('設定頻寬=15 Mbps',next(r['actual'] for r in self.rows if r['item'].startswith('Stream 4(')))
    def test_no_unverified_units(self):
        self.assertFalse(any('單位待確認' in str(r['actual']) for r in self.rows))
    def test_no_synthetic_pon_review_row(self):
        self.assertFalse(any(r['item']=='PON→LAN 實際吞吐量' for r in self.rows))
    def test_station_evidence_remains(self):
        self.assertEqual(sum(r['item'].startswith('Port ') for r in self.rows), 6)
        self.assertEqual(sum(r['item'].startswith('Stream ') for r in self.rows), 10)
        self.assertEqual(sum(r['item']=='TeleATT 測站總結果' for r in self.rows), 1)
