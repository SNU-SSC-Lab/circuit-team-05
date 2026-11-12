import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from model import decode, expected, packet, signed


class ModelTest(unittest.TestCase):
    def test_hand_calculated_vectors(self):
        self.assertEqual(expected([1,0,2,1,2,0,1,2],[10,-20,30,40,-50,60,70,-80]),220)
        self.assertEqual(expected([2]*8,[-128]*8),1024)
        self.assertEqual(signed(expected([1]*8,[-128]*8),12),-1024)
        self.assertEqual(expected([3]*8,[127]*8),4096)
        self.assertEqual(expected([1]+[0]*7,[-1]+[0]*7),4095)

    def test_wire_order(self):
        self.assertEqual(packet([1,2,0,0,0,0,0,0],[3,5,0,0,0,0,0,0])[:8], [9,0,0,0,3,0,5,0])
        self.assertEqual(decode([14,15,15,0]),4094)

    def test_invalid_domain(self):
        for codes,inputs in [([0]*7,[0]*8),([4]*8,[0]*8),([1]*8,[128]*8)]:
            with self.assertRaises(ValueError): expected(codes,inputs)


if __name__=='__main__': unittest.main()
