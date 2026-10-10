import assert from 'node:assert/strict';
import test from 'node:test';
import { hasOverlappingRange, toCodePointOffset } from '../src/modules/automation/utils/offsets.js';

test('converts browser UTF-16 selections to source code-point offsets', () => {
  const text = 'A🙂éZ';

  assert.equal(toCodePointOffset(text, 3), 2);
  assert.equal(toCodePointOffset(text, 4), 3);
});

test('detects overlapping manual privacy ranges', () => {
  const ranges = [{ start: 2, end: 7 }];

  assert.equal(hasOverlappingRange(ranges, 6, 9), true);
  assert.equal(hasOverlappingRange(ranges, 7, 9), false);
});
