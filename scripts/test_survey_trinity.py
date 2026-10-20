"""Synthetic malformed-input checks for the bounded archive reader."""
import struct
import unittest

from survey_trinity import FB, inspect_bnsh


class ReaderTests(unittest.TestCase):
    def test_scalar_and_relative_offset_reject_truncation(self):
        with self.assertRaises(ValueError):
            FB(b'\x00').read(0, 'I')
        with self.assertRaises(ValueError):
            FB(struct.pack('<I', 0xfffffff0)).indirect(0)

    def test_vector_rejects_oversized_range(self):
        # root table at 12, vtable at 4, vector at 20 with absent payload.
        data = struct.pack('<IHHHHiII', 12, 6, 8, 4, 0, 8, 4, 1000)
        with self.assertRaises(ValueError):
            FB(data).vector(12, 0, 8)

    def test_bnsh_rejects_unbounded_variation_table(self):
        data = bytearray(0x90)
        data[:8] = b'BNSH\0\0\0\0'
        data[0x60:0x64] = b'grsc'
        struct.pack_into('<IQ', data, 0x7c, 2, 0x1000)
        with self.assertRaises(ValueError):
            inspect_bnsh(data)

    def test_no_signature_is_not_a_shader(self):
        self.assertEqual(inspect_bnsh(b'ordinary bytes')[0], 0)


if __name__ == '__main__':
    unittest.main()
