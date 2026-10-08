"""ROM-free tests of guarded allocation decoding and stored message boundaries."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import text_buffer_check as checker


def allocation(capacity):
    # Recorded Thumb call instruction at the investigated bag allocation site.
    return bytes([capacity]) + bytes.fromhex('20062128f6c7ff')


class TextBufferTests(unittest.TestCase):
    def test_actual_code_and_capacity_patch(self):
        self.assertEqual(checker.capacity_from_code(allocation(114), checker.SITE), 114)
        self.assertEqual(checker.capacity_from_code(allocation(128), checker.SITE), 128)
    def test_reject_unrecognized_register_heap_and_call(self):
        for index in (1,2,3,4,6):
            data=bytearray(allocation(114));data[index]^=1
            with self.assertRaises(ValueError): checker.capacity_from_code(data, checker.SITE)
    def test_actual_boundary_includes_terminator(self):
        strings=[[1]*113+[0xffff], [1]*114+[0xffff], [1]*119+[0xffff]]
        findings=checker.check_lengths(strings,114)
        self.assertEqual([f['id'] for f in findings],[1,2])
        self.assertEqual(findings[1]['excess_units'],6)
        self.assertEqual(checker.check_lengths(strings,128),[])
    def test_invalid_and_compressed_inputs_incomplete(self):
        for units in ([],[1],[0xf100,1,0xffff]):
            with self.assertRaises(ValueError): checker.check_lengths([units],114)


def thumb_bl(address, target):
    delta = (target-address-4) & 0x7fffff
    return (0xf000 | (delta >> 12)).to_bytes(2,'little') + (0xf800 | ((delta >> 1) & 0x7ff)).to_bytes(2,'little')


def consumer_fixture(spec, immediate):
    base=spec['site']
    data=bytearray(spec['description_call']-base+4)
    prefix=bytes([immediate])+bytes.fromhex(spec['suffix'])
    data[:len(prefix)]=prefix
    off=spec['call_offset']
    data[off:off+4]=thumb_bl(base+off,checker.STRING_NEW)
    if spec['overlay']==16: data[10:14]=bytes.fromhex('616b8862')
    off=spec['description_call']-base
    data[off:off+4]=thumb_bl(base+off,0x020763EC)
    return data,base


class ConsumerGuardTests(unittest.TestCase):
    def test_all_consumers_and_capacity_changes(self):
        for spec in checker.CONSUMERS:
            for immediate in (1 if spec['shift'] else 114,2 if spec['shift'] else 128):
                with self.subTest(overlay=spec['overlay'],immediate=immediate):
                    data,base=consumer_fixture(spec,immediate)
                    self.assertEqual(checker.consumer_capacity(data,base,spec),immediate << spec['shift'])
    def test_unsupported_sequences_and_description_links(self):
        for spec in checker.CONSUMERS:
            for index in (1,spec['call_offset'],spec['description_call']-spec['site']):
                data,base=consumer_fixture(spec,1 if spec['shift'] else 114)
                data[index]^=1
                with self.assertRaises(ValueError): checker.consumer_capacity(data,base,spec)
    def test_pc_assignment_and_zero_capacity_rejected(self):
        spec=checker.CONSUMERS[-1];data,base=consumer_fixture(spec,1);data[12]^=1
        with self.assertRaises(ValueError): checker.consumer_capacity(data,base,spec)
        for spec in checker.CONSUMERS:
            data,base=consumer_fixture(spec,0)
            with self.assertRaises(ValueError): checker.consumer_capacity(data,base,spec)


if __name__ == '__main__': unittest.main()
