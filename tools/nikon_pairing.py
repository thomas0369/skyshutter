"""The camera's BLE authentication handshake.

Four 17-byte messages on characteristic 0x2000. We send stages 1 and 3, the
camera answers with 2 and 4. Stage 2 is a challenge: the camera hashes its own
timestamp together with ours under one of eight fixed salts, and we have to
work out which salt it used before we can answer. Stage 4 hands back the
camera's serial as ASCII.

The hash is Blowfish in ECB with a fixed key, chained: each pair of input
words is XORed with the running state and encrypted, and the ciphertext
becomes the new state. Everything inside the hash is big-endian; everything on
the wire is little-endian, which is the detail that costs an afternoon if you
miss it.

Protocol facts (key, salts, field layout) were taken from published reverse
engineering -- github.com/hurui200320/nsg and the write-up at
skyblond.info/archives/1115.html -- and reimplemented here rather than copied.
They are verified against this camera: see the recorded exchange in
docs/FINDINGS.md, which this module reproduces exactly.

Needs pycryptodome, which is why it sits in tools/ and not in the package.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from Crypto.Cipher import Blowfish

#: Fixed Blowfish key. Not a secret, just a constant of the protocol.
KEY = bytes.fromhex("ffffaa5511223300")

#: Starting state of the chained hash.
INITIAL_LEFT = 0x01020304
INITIAL_RIGHT = 0x05060708

#: The camera picks one of these per session; we find it by trying all eight.
SALTS: tuple[tuple[int, int], ...] = (
    (0x704066E4, 0x0433D552),
    (0xED4B8FAC, 0x15F7E47B),
    (0x24471F11, 0x8B5EA1FC),
    (0x05960C31, 0x2B8C7F41),
    (0xFDA588C1, 0xEBA8B1F3),
    (0x99166056, 0x1BD3D550),
    (0xCD32687F, 0xA9E28A30),
    (0x2A8FE834, 0xDEC7EBF4),
)

MESSAGE_LENGTH = 17


class HandshakeError(Exception):
    """The exchange did not go as the protocol says it should."""


def blowfish_hash(words: list[int]) -> tuple[int, int]:
    """Chain an even number of 32-bit words through Blowfish."""
    if len(words) % 2:
        raise ValueError("need an even number of words")
    cipher = Blowfish.new(KEY, Blowfish.MODE_ECB)
    left, right = INITIAL_LEFT, INITIAL_RIGHT
    for i in range(0, len(words), 2):
        block = struct.pack(">II", words[i] ^ left, words[i + 1] ^ right)
        left, right = struct.unpack(">II", cipher.encrypt(block))
    return left, right


@dataclass(frozen=True)
class Message:
    """One handshake message, as it appears on the wire."""

    stage: int
    timestamp: bytes  # 8 bytes, kept verbatim -- we never need its value
    device: bytes  # 4 bytes
    nonce: bytes  # 4 bytes

    def encode(self) -> bytes:
        return bytes([self.stage]) + self.timestamp + self.device + self.nonce

    @classmethod
    def decode(cls, raw: bytes) -> Message:
        if len(raw) != MESSAGE_LENGTH:
            raise HandshakeError(f"expected {MESSAGE_LENGTH} bytes, got {len(raw)}")
        return cls(raw[0], raw[1:9], raw[9:13], raw[13:17])

    @property
    def halves(self) -> tuple[int, int]:
        """The timestamp's two words, as the hash wants them."""
        return struct.unpack(">II", self.timestamp)

    @property
    def serial(self) -> str:
        """Stage 4 carries the camera's serial in the device and nonce fields."""
        return (self.device + self.nonce).decode("ascii", "replace")


def stage_one(device: bytes | None = None, nonce: bytes | None = None) -> Message:
    """Open the handshake.

    The device id's first byte on the wire has to be 0x01. Passing a device and
    nonce back in reconnects as an already-known client instead of pairing as a
    new one.
    """
    return Message(
        stage=0x01,
        timestamp=os.urandom(8),
        device=device or (b"\x01" + os.urandom(3)),
        nonce=nonce or os.urandom(4),
    )


def find_salt(stage1: Message, stage2: Message) -> int:
    """Which salt did the camera use?

    Try each one on the camera's own challenge until the hash reproduces the
    device and nonce it sent back. Note the word order: the camera's timestamp
    comes first here and second in the reply. Getting that backwards fails
    silently -- no salt matches and nothing says why.
    """
    cam_lo, cam_hi = stage2.halves
    our_lo, our_hi = stage1.halves
    expected = struct.unpack(">II", stage2.device + stage2.nonce)

    for index, (salt_a, salt_b) in enumerate(SALTS):
        if blowfish_hash([salt_a, salt_b, cam_lo, cam_hi, our_lo, our_hi]) == expected:
            return index
    raise HandshakeError("no salt reproduces the camera's challenge")


def stage_three_for_salt(stage1: Message, stage2: Message, salt: int) -> Message:
    """Stage 3 when the salt is already known.

    The camera knows which salt it picked, so when we play the camera we skip
    the search. Same computation either way -- note the word order flips
    relative to find_salt: our timestamp leads here.
    """
    salt_a, salt_b = SALTS[salt]
    our_lo, our_hi = stage1.halves
    cam_lo, cam_hi = stage2.halves
    left, right = blowfish_hash([salt_a, salt_b, our_lo, our_hi, cam_lo, cam_hi])
    return Message(
        stage=0x03,
        timestamp=stage1.timestamp,
        device=struct.pack(">I", left),
        nonce=struct.pack(">I", right),
    )


def stage_three(stage1: Message, stage2: Message) -> Message:
    """Answer the challenge, keeping our original timestamp."""
    if stage1.stage != 0x01 or stage2.stage != 0x02:
        raise HandshakeError(f"expected stages 1 and 2, got {stage1.stage} and {stage2.stage}")
    salt_a, salt_b = SALTS[find_salt(stage1, stage2)]
    our_lo, our_hi = stage1.halves
    cam_lo, cam_hi = stage2.halves
    left, right = blowfish_hash([salt_a, salt_b, our_lo, our_hi, cam_lo, cam_hi])
    return Message(
        stage=0x03,
        timestamp=stage1.timestamp,
        device=struct.pack(">I", left),
        nonce=struct.pack(">I", right),
    )


def client_name(name: str) -> bytes:
    """The 32-byte name field written to 0x2002 after a successful handshake."""
    encoded = name.encode("ascii")
    if len(encoded) > 31:
        raise ValueError("name must be at most 31 characters; the last byte stays nul")
    return encoded.ljust(32, b"\x00")
