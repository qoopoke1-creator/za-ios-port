#!/usr/bin/env python3
"""Read-only ONEPACK/Trinity inventory. Outputs must remain outside the source tree.

Format references (schemas only; implementation written independently):
kwsch/pkNX, FlatBuffers/ZA/Trinity/Schemas/{TrinityFileDescriptors,
TrinityFileSystemMetadata,TrinityPak}.fbs at d191cd0e5c05f2af81d9a41c1f1d82e6621b351a.
No Oodle decompressor is bundled; optional pyooz is loaded only when requested.
Signature hits alone do not establish runtime correctness.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import mmap
from pathlib import Path
import struct
import zlib


class FB:
    def __init__(self, data):
        self.data = data

    def read(self, pos, fmt):
        size = struct.calcsize('<' + fmt)
        if pos < 0 or pos + size > len(self.data):
            raise ValueError(f'Out-of-bounds scalar at {pos:#x}')
        return struct.unpack_from('<' + fmt, self.data, pos)[0]

    def indirect(self, pos):
        target = pos + self.read(pos, 'I')
        if target < 0 or target + 4 > len(self.data):
            raise ValueError('Out-of-bounds relative offset')
        return target

    def field(self, table, index):
        vt = table - self.read(table, 'i')
        entry = 4 + index * 2
        if entry + 2 > self.read(vt, 'H'):
            return None
        off = self.read(vt + entry, 'H')
        return table + off if off else None

    def scalar(self, table, index, fmt, default=0):
        pos = self.field(table, index)
        return self.read(pos, fmt) if pos is not None else default

    def vector(self, table, index, width):
        pos = self.field(table, index)
        if pos is None:
            raise ValueError(f'Missing required vector {index}')
        start = self.indirect(pos)
        count = self.read(start, 'I')
        limit = 512 * 2**20 if width == 1 else 2_000_000
        if count > limit or start + 4 + count * width > len(self.data):
            raise ValueError('Invalid vector range')
        return start + 4, count

    def tables(self, table, index):
        start, count = self.vector(table, index, 4)
        return [self.indirect(start + i * 4) for i in range(count)]

    def numbers(self, table, index):
        start, count = self.vector(table, index, 8)
        return [self.read(start + i * 8, 'Q') for i in range(count)]

    def strings(self, table, index):
        result = []
        for pos in self.tables(table, index):
            length = self.read(pos, 'I')
            if length > 16384 or pos + 4 + length >= len(self.data):
                raise ValueError('Invalid string range')
            if self.data[pos + 4 + length] != 0:
                raise ValueError('Unterminated string')
            result.append(bytes(self.data[pos + 4:pos + 4 + length]).decode('utf-8'))
        return result


def fnv(name):
    # Trinity uses a nonstandard offset basis, not the usual FNV-1a basis.
    h = 0xcbf29ce484222645
    for byte in name.encode('utf-8'):
        h = ((h ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return h


def inspect_bnsh(data):
    """Validate stage ranges using the layout documented in shader_split.py."""
    inventory = Counter()
    containers = 0
    pos = data.find(b'BNSH\0\0\0\0')
    while pos >= 0:
        view = FB(data[pos:])
        if view.data[0x60:0x64] != b'grsc':
            raise ValueError('BNSH candidate has no grsc block')
        count = view.read(0x7c, 'I')
        table = view.read(0x80, 'Q')
        if count > 1_000_000 or table + count * 0x40 > len(view.data):
            raise ValueError('Invalid BNSH variation range')
        for i in range(count):
            program = view.read(table + i * 0x40 + 0x10, 'Q')
            if not program:
                continue
            for slot, stage in enumerate(('vs', 'hs', 'ds', 'gs', 'ps', 'cs')):
                desc = view.read(program + 8 + slot * 8, 'Q')
                if not desc:
                    continue
                ctl, code = view.read(desc + 8, 'Q'), view.read(desc + 16, 'Q')
                nc, nt = view.read(desc + 24, 'I'), view.read(desc + 28, 'I')
                if nt < 0x760 or ctl + nt > len(view.data) or code + nc > len(view.data):
                    raise ValueError('Invalid BNSH stage range')
                if view.read(ctl, 'I') != 0x98761234 or view.read(ctl + 0x704, 'I') != nc:
                    raise ValueError('Invalid BNSH stage control or code length')
                if stage != 'cs' and view.read(code, 'I') != 0x12345678:
                    raise ValueError('Invalid graphics code magic')
                inventory[stage] += 1
        containers += 1
        pos = data.find(b'BNSH\0\0\0\0', pos + 8)
    return containers, inventory


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('arc', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--decode-limit-mib', type=int, default=32)
    ap.add_argument('--oodle-candidates', action='store_true', help='use optional pyooz for shader-named packs only')
    ap.add_argument('--extract-candidates', action='store_true', help='save decoded shader-named entries outside the repository')
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        ap.error('Output must be outside the source repository')
    if not 1 <= args.decode_limit_mib <= 256:
        ap.error('decode limit must be between 1 and 256 MiB')
    out.mkdir(parents=True, exist_ok=True)
    index = (args.arc / 'data.trpfd').read_bytes()
    fd = FB(index)
    root = fd.indirect(0)
    names = fd.strings(root, 1)
    infos = fd.tables(root, 3)
    if len(names) != len(infos):
        raise ValueError('Descriptor count mismatch')
    compression, signatures = Counter(), Counter()
    stages, bnsh_containers = Counter(), 0
    candidates, total_files, skipped = [], 0, 0
    with (args.arc / 'data.trpfs').open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as archive:
        fs = FB(archive)
        if archive[:8] != b'ONEPACK\0':
            raise ValueError('Invalid ONEPACK magic')
        meta = fs.indirect(fs.read(8, 'Q'))
        hashes, offsets = fs.numbers(meta, 0), fs.numbers(meta, 1)
        if len(hashes) != len(offsets) or len(hashes) != len(names) or len(set(hashes)) != len(hashes):
            raise ValueError('Metadata count or duplicate hash mismatch')
        offset_by_hash = dict(zip(hashes, offsets))
        with (out / 'packs.tsv').open('w', encoding='utf-8', newline='') as pf, (out / 'files.tsv').open('w', encoding='utf-8', newline='') as ff:
            packs = csv.writer(pf, delimiter='\t')
            files = csv.writer(ff, delimiter='\t')
            packs.writerow(['pack', 'offset', 'size', 'files'])
            files.writerow(['pack', 'hash', 'compression', 'raw_size', 'stored_size', 'signature_hits'])
            for name, info in zip(names, infos):
                named = any(s in name.lower() for s in ('shader', '.trsh', '.bnsh', '.bfsha'))
                size = fd.scalar(info, 0, 'Q')
                expected = fd.scalar(info, 1, 'Q')
                offset = offset_by_hash[fnv(name)]
                if size > 512 * 2**20 or offset < 16 or offset + size > len(archive):
                    raise ValueError(f'Invalid pack range: {name}')
                pack = FB(archive[offset:offset + size])
                pr = pack.indirect(0)
                fhashes, entries = pack.numbers(pr, 0), pack.tables(pr, 1)
                if len(entries) != expected or len(entries) != len(fhashes):
                    raise ValueError(f'Pack file count mismatch: {name}')
                packs.writerow([name, offset, size, expected])
                for h, entry in zip(fhashes, entries):
                    kind = pack.scalar(entry, 1, 'b')
                    raw_size = pack.scalar(entry, 3, 'Q')
                    start, stored = pack.vector(entry, 4, 1)
                    compression[kind] += 1
                    total_files += 1
                    decoded = None
                    if raw_size <= args.decode_limit_mib * 2**20:
                        payload = pack.data[start:start + stored]
                        if kind == -1:
                            decoded = payload
                        elif kind == 1:
                            decoder = zlib.decompressobj()
                            decoded = decoder.decompress(payload, raw_size + 1)
                            if not decoder.eof or decoder.unconsumed_tail:
                                raise ValueError('Invalid or oversized zlib stream')
                        elif kind == 2:
                            import lz4.block
                            decoded = lz4.block.decompress(payload, uncompressed_size=raw_size)
                        elif kind == 3 and args.oodle_candidates and named:
                            import ooz
                            decoded = ooz.decompress(payload, raw_size)
                    if decoded is not None and len(decoded) != raw_size:
                        raise ValueError('Decompressed size mismatch')
                    hits = []
                    if decoded is None:
                        skipped += 1
                    else:
                        nbnsh, stage_counts = inspect_bnsh(decoded)
                        bnsh_containers += nbnsh
                        stages.update(stage_counts)
                        for magic, label in ((b'BNSH', 'BNSH'), (b'BAHS', 'BAHS'), (b'\x91\x68\x86\x19', 'GLSLC'), (b'\x03\x02\x23\x07', 'SPIR-V')):
                            n = decoded.count(magic)
                            if n:
                                signatures[label] += n
                                hits.append(f'{label}:{n}')
                    if hits or named:
                        candidates.append({'pack': name, 'hash': f'{h:016x}', 'compression': kind,
                                           'raw_size': raw_size, 'hits': hits,
                                           'sha256': hashlib.sha256(decoded).hexdigest() if decoded is not None else None})
                        if args.extract_candidates and decoded is not None:
                            target = out / 'decoded' / f'{fnv(name):016x}'
                            target.mkdir(parents=True, exist_ok=True)
                            (target / f'{h:016x}.bin').write_bytes(decoded)
                    files.writerow([name, f'{h:016x}', kind, raw_size, stored, ','.join(hits)])
    summary = {'packs': len(names), 'files': total_files, 'compression_counts': dict(compression),
               'decoded_files': total_files - skipped, 'skipped_files': skipped,
               'signature_counts': dict(signatures), 'candidate_files': len(candidates),
               'validated_bnsh_containers': bnsh_containers, 'stage_records': dict(stages),
               'index_sha256': hashlib.sha256(index).hexdigest(),
               'limitations': 'Signatures are heuristic; only optional shader-named Oodle candidates are decoded; oversized entries are skipped.'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (out / 'candidates.json').write_text(json.dumps(candidates, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
