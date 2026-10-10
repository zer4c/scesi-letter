export function toCodePointOffset(value, utf16Offset) {
  return Array.from(value.slice(0, utf16Offset)).length;
}

export function hasOverlappingRange(ranges, start, end) {
  return ranges.some((range) => start < range.end && end > range.start);
}
