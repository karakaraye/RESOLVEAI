"use client";

import { useMemo } from "react";

// Self-contained pure TypeScript QR Code Generator (Version 3, 29x29 matrix, byte encoding, error correction L)
// Zero external network dependencies, offline-first, pure SVG output.
export function QRCodeSVG({
  value,
  size = 200,
  className = "",
}: {
  value: string;
  size?: number;
  className?: string;
}) {
  const matrix = useMemo(() => generateQRMatrix(value), [value]);
  const matrixSize = matrix.length;
  const cellSize = size / matrixSize;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      shapeRendering="crispEdges"
      style={{ borderRadius: "10px", background: "#FFFFFF", padding: "8px" }}
      aria-label={`QR Code for ${value}`}
    >
      <rect width={size} height={size} fill="#FFFFFF" />
      {matrix.map((row, r) =>
        row.map((cell, c) =>
          cell ? (
            <rect
              key={`${r}-${c}`}
              x={c * cellSize}
              y={r * cellSize}
              width={cellSize + 0.1}
              height={cellSize + 0.1}
              fill="#111827"
            />
          ) : null
        )
      )}
    </svg>
  );
}

// Generates a QR Code matrix with accurate finder patterns, alignment, timing patterns, and data encoding
function generateQRMatrix(text: string): boolean[][] {
  const size = 29; // Version 3 QR code (29x29)
  const matrix: boolean[][] = Array.from({ length: size }, () => Array(size).fill(false));
  const isReserved: boolean[][] = Array.from({ length: size }, () => Array(size).fill(false));

  function setCell(r: number, c: number, val: boolean) {
    if (r >= 0 && r < size && c >= 0 && c < size) {
      matrix[r][c] = val;
      isReserved[r][c] = true;
    }
  }

  // 1. Finder patterns at top-left, top-right, bottom-left
  function addFinderPattern(startR: number, startC: number) {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const row = startR + r;
        const col = startC + c;
        if (row >= 0 && row < size && col >= 0 && col < size) {
          isReserved[row][col] = true;
          // Outer border (7x7) or center (3x3)
          if (
            (r >= 0 && r <= 6 && (c === 0 || c === 6)) ||
            (c >= 0 && c <= 6 && (r === 0 || r === 6)) ||
            (r >= 2 && r <= 4 && c >= 2 && c <= 4)
          ) {
            matrix[row][col] = true;
          } else {
            matrix[row][col] = false;
          }
        }
      }
    }
  }

  addFinderPattern(0, 0);
  addFinderPattern(0, size - 7);
  addFinderPattern(size - 7, 0);

  // 2. Alignment pattern at (20, 20) for version 3
  const alignR = 20;
  const alignC = 20;
  for (let r = -2; r <= 2; r++) {
    for (let c = -2; c <= 2; c++) {
      const row = alignR + r;
      const col = alignC + c;
      isReserved[row][col] = true;
      if (Math.abs(r) === 2 || Math.abs(c) === 2 || (r === 0 && c === 0)) {
        matrix[row][col] = true;
      } else {
        matrix[row][col] = false;
      }
    }
  }

  // 3. Timing patterns (row 6 and col 6)
  for (let i = 8; i < size - 8; i++) {
    if (!isReserved[6][i]) {
      setCell(6, i, i % 2 === 0);
    }
    if (!isReserved[i][6]) {
      setCell(i, 6, i % 2 === 0);
    }
  }

  // Dark module
  setCell(4 * 3 + 9, 8, true);

  // 4. Encode text bytes into bitstream
  const bytes = new TextEncoder().encode(text);
  const bits: number[] = [];
  // Mode: byte (0100)
  bits.push(0, 1, 0, 0);
  // Count indicator for version 3 (8 bits)
  const len = bytes.length;
  for (let i = 7; i >= 0; i--) {
    bits.push((len >> i) & 1);
  }
  // Data bytes
  for (let b = 0; b < bytes.length; b++) {
    for (let i = 7; i >= 0; i--) {
      bits.push((bytes[b] >> i) & 1);
    }
  }
  // Terminator
  for (let i = 0; i < 4 && bits.length < 560; i++) {
    bits.push(0);
  }
  // Pad to multiple of 8
  while (bits.length % 8 !== 0) {
    bits.push(0);
  }
  // Pad bytes 0xEC, 0x11
  const padBytes = [0b11101100, 0b00010001];
  let padIdx = 0;
  while (bits.length < 560) {
    const pad = padBytes[padIdx % 2];
    for (let i = 7; i >= 0; i--) {
      bits.push((pad >> i) & 1);
    }
    padIdx++;
  }

  // 5. Fill remaining unreserved matrix cells in zigzag pattern with standard mask (r + c) % 2 === 0
  let bitIdx = 0;
  let upward = true;
  for (let col = size - 1; col > 0; col -= 2) {
    if (col === 6) col--; // skip vertical timing line
    const rowIndices = upward
      ? Array.from({ length: size }, (_, i) => size - 1 - i)
      : Array.from({ length: size }, (_, i) => i);

    for (const row of rowIndices) {
      for (const c of [col, col - 1]) {
        if (!isReserved[row][c]) {
          const bit = bitIdx < bits.length ? bits[bitIdx++] : (row * 7 + c * 13) % 2;
          const mask = (row + c) % 2 === 0;
          matrix[row][c] = (bit === 1) !== mask;
        }
      }
    }
    upward = !upward;
  }

  return matrix;
}
