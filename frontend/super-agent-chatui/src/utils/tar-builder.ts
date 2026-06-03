/**
 * Minimal TAR archive builder for browser-side folder upload.
 *
 * Produces a valid ustar-format tar archive as a Uint8Array.
 * The resulting tar can be POSTed to the upload-directory API.
 */

const BLOCK_SIZE = 512;
const encoder = new TextEncoder();

function padBlock(data: Uint8Array): Uint8Array {
  const remainder = data.length % BLOCK_SIZE;
  if (remainder === 0) return data;
  const padded = new Uint8Array(data.length + (BLOCK_SIZE - remainder));
  padded.set(data);
  return padded;
}

function octal(n: number, width: number): Uint8Array {
  const s = n.toString(8).padStart(width - 1, "0") + "\0";
  return encoder.encode(s);
}

function ascii(s: string, width: number): Uint8Array {
  const buf = new Uint8Array(width);
  const encoded = encoder.encode(s);
  buf.set(encoded.slice(0, width - 1));
  return buf;
}

function checksum(header: Uint8Array): number {
  let sum = 0;
  for (let i = 0; i < BLOCK_SIZE; i++) {
    sum += header[i];
  }
  // The chksum field (bytes 148-155) is treated as spaces during calculation
  for (let i = 148; i < 156; i++) {
    sum += 32 - header[i]; // 32 = space char
  }
  return sum;
}

function buildHeader(
  name: string,
  size: number,
  typeflag: string,
): Uint8Array {
  const header = new Uint8Array(BLOCK_SIZE);

  header.set(ascii(name, 100), 0); // name
  header.set(octal(0o644, 8), 100); // mode
  header.set(octal(0, 8), 108); // uid
  header.set(octal(0, 8), 116); // gid
  header.set(octal(size, 12), 124); // size
  header.set(octal(Math.floor(Date.now() / 1000), 12), 136); // mtime
  // chksum placeholder (filled below)
  for (let i = 148; i < 156; i++) header[i] = 32; // spaces
  header[156] = typeflag.charCodeAt(0); // typeflag
  header.set(ascii("ustar", 6), 257); // magic
  header.set(ascii("00", 2), 263); // version
  header.set(ascii("root", 32), 265); // uname
  header.set(ascii("root", 32), 297); // gname

  const chk = checksum(header);
  header.set(octal(chk, 8), 148);

  return header;
}

export interface TarEntry {
  /** Relative path within the archive (e.g. "SKILL.md", "scripts/helper.py") */
  path: string;
  /** File content as bytes */
  data: Uint8Array;
}

export function buildTar(entries: TarEntry[]): Uint8Array {
  const blocks: Uint8Array[] = [];

  for (const entry of entries) {
    const header = buildHeader(entry.path, entry.data.length, "0");
    blocks.push(header);
    blocks.push(padBlock(entry.data));
  }

  // End-of-archive marker: two zero blocks
  blocks.push(new Uint8Array(BLOCK_SIZE));
  blocks.push(new Uint8Array(BLOCK_SIZE));

  const totalSize = blocks.reduce((sum, b) => sum + b.length, 0);
  const result = new Uint8Array(totalSize);
  let offset = 0;
  for (const block of blocks) {
    result.set(block, offset);
    offset += block.length;
  }

  return result;
}