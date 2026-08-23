"""LsSec -- decrypt the WiFi credentials the camera hands out over BLE.

The camera puts its access-point SSID and password into BLE characteristic
0x2004, Blowfish-encrypted. This module reproduces the vendor scheme so the
credentials can be recovered from the ciphertext -- for any pairing, even when
the password rotates.

Verified 23.08.2026 against the vendor library (as an oracle) and two
plaintext/ciphertext pairs from real hardware. The scheme, all Blowfish words
big-endian:

  1. Fixed transform: Blowfish with key ffffaa5511223300 (the pairing key),
     CBC, IV L=0x01020304 R=0x05060708.
  2. field_a (8 bytes) = 0x01 | camera_timestamp[1:4] | own_timestamp[0:4],
     from the stage-2 and stage-1 handshake timestamps.
  3. Session key = the *last* CBC block (a CBC-MAC) of the fixed transform over
     stage4_payload | device_id | field_a.
  4. Decrypt: Blowfish-CBC with the session key and an all-zero IV.

The Blowfish tables are the standard pi-init constants, carried here as a
compressed blob so the module stays standard-library only -- no pycryptodome,
matching the rest of the client.

Nothing here touches the camera; it works on bytes captured during pairing.
"""
from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass

#: Standard Blowfish pi-init P-array and S-boxes (1042 words), verified byte for
#: byte against the ones in the vendor library.
_PI = struct.unpack(
    "<1042I", zlib.decompress(base64.b64decode(
    "eNoBSBC374hqPyTTCKOFLooZE0RzcAMiOAmk0DGfKZj6LgiJbE7s5iEoRXcT0DjPZlS+bAzpNLcprMDdUHzJtdWEPxcJR7XZ1RaSG/t5iaYLMdGstd+Y23L9L7ffGtDtr+G4ln4makWQfLqZfyzxR5mhJPdskbPi8gEIFvyOhdggaWNpTldxo/5YpH49k/SPdJUNWLaOcljNi3HuShWCHaRUe7VZWsI51TCcE2DyKiOw0cXwhWAoGHlByu8427iw3HmODhg6YIsOnmw+ih6wwXcV1ydLMb3aL694YFxgVfMlVeaUq1WqYphIV0AU6GNqOcpVthCrKjRczLTO6EERr4ZUoZPpcnwRFO6zKrxvY13FqSv2MRh0Fj5czh6Th5szutavXM8kbIFTMnp3hpUomEiPO6+5S2sb6L/EkyEoZswJ2GGRqSH7YKx8SDKA7F1dXYTvsXWF6QIjJtyIG2XrgT6JI8WsltPzb20POUL0g4JECy4EIISkSvDIaV6bH55CaMYhmmzp9mGcDGfwiNOr0qBRamgvVNgopw+WozNRq2wL727kO3oTUPA7upgq+34dZfGhdgGvOT5ZymaIDkOCGYbujLSfb0XDpYR9vl6LO9h1b+BzIMGFn0QaQKZqwVZiqtNOBnc/NnLf/hs9AptCJNfQN0gSCtDT6g/bm8DxSclyUwd7G5mA2HnUJffe6PYaUP7jO0x5tr3gbJe6BsAEtk+pwcRgn0DCnlxeYyRqGa9v+2i1U2w+67I5E2/sUjsfUfxtLJUwm0RFgcwJvV6vBNDjvv1KM94HKA9ms0suGVeoy8APdMhFOV8L0tv707m9wHlVCjJgGsYAodZ5cixA/iWfZ8yjH/v46aWO+CIy298WdTwVa2H9yB5QL6tSBa36tT0yYIcj/Uh7MVOC3wA+u1dcnqCMb8ouVoca22kX3/aoQtXD/34oxjJnrHNVT4ywJ1tpyFjKu12j/+GgEfC4mD36ELiDIf1stfxKW9PRLXnkU5plRfi2vEmO0pCX+0va8t3hM37LpEET+2LoxuTO2sog7wFMdzb+nn7QtB/xK03a25WYkZCucY6t6qDVk2vQ0Y7Q4CXHry9bPI63lHWO++L2j2QrEvISuIiIHPANkKBerU8cw49okfHP0a3BqLMYIi8vdxcOvv4tdeqhHwKLD8yg5eh0b7XW86wYmeKJzuBPqLS34BP9gTvEfNmordJmol8WBXeVgBRzzJN3FBohZSCt5ob6tXf1QlTHzzWd+wyvzeugiT570xtB1kl+Hq4tDiUAXrNxILsAaCKv4LhXmzZkJB65CfAdkWNVqqbfWYlDwXh/U1rZolt9IMW55QJ2AyaDqc+VYmgZyBFBSnNOyi1Hs0qpFHtSAFEbFSlTmj9XD9bkxpu8dqRgKwB05oG1b7oIH+kbV2vslvIV2Q0qIWVjtrb5uecuBTT/ZFaFxV0tsFOhj5+pmUe6CGoHhW7pcHpLRCmztS4JddsjJhnEsKZurX3fp0m4YO6cZrLtj3GMquz/F5ppbFJkVuGescKlAjYZKUwJdUATWaA+OhjkmphUP2WdQlvW5I9r1j/3mQec0qH1MOjv5jgtTcFdJfCGIN1MJutwhMbpgmNezB4CP2toCcnvuj4UGJc8oXBqa4Q1f2iG4qBSBVOctzcHUKochAc+XK7ef+xEfY648hZXN9o6sA0MUPAEHxzw/7MAAhr1DK6ydLU8WHqDJb0hCdz5E5HR9i+pfHNHMpQBR/UigeXlOtzawjc0drXIp93zmkZhRKkOA9APPsfI7EEedaSZzTjiLw7qO6G7gDIxsz4YOItUTgi5bU8DDUJvvwQK9pASuCx5fJckcrB5Vq+Jr7wfd5reEAiT2RKui7MuP8/cH3ISVSRxay7m3RpQh82EnxhHWHoX2gh0vJqfvIx9S+k67Hrs+h2F22ZDCWPSw2TERxgc7wjZFTI3O0PdFrrCJENNoRJRxGUqAgCUUN3kOhOe+N9xVU4xENZ3rIGbGRFf8VY1BGvHo9c7GBE8CaUkWe3mj/L6+/GXLL+6nm48FR5wReOGsW/p6gpeDoazKj5aHOcfd/oGPU653GUpDx3nmdaJPoAlyGZSeMlMLmqzEJy6DhXGeOrilFM8/KX0LQoep0738j0rHTYPJjkZYHnCGQinI1K2EhP3bv6t62Yfw+qVRbzjg8h7ptE3f7Eo/4wB790yw6VabL6FIVhlApiraA+lzu47lS/brX3vKoQvblsotiEVcGEHKXVH3ewQFZ9hMKjME5a9Yese/jQDz2MDqpBcc7U5onBMC56e1RTeqsu8hszupyxiYKtcq5xuhPOyrx6LZMrwvRm5aSOgULtaZTJaaECztCo81emeMfe4IcAZC1SbmaBfh36Z95WofT1imog3+Hct45dfk+0RgRJoFimINQ7WH+bHod/elpm6WHilhPVXY3IiG//Dg5uWRsIa6wqzzVQwLlPkSNmPKDG8be/y61jq/8Y0Ye0o/nM8fO7ZFEpd47dk6BRdEELgEz4gtuLuReqrqqMVT2zb0E/L+kL0Qse1u2rvHTtPZQUhzUGeeR7Yx02FhmpHS+RQYoE98qFiz0YmjVugg4j8o7bHwcMkFX+SdMtpC4qER4WyklYAv1sJnUgZrXSxYhQADoIjKo1CWOr1VQw+9K0dYXA/I5LwcjNBfpON8exf1ts7ImxZN958YHTuy6fyhUBuMnfOhIAHpp5Q+BlV2O/oNZfZYaqnaanCBgzF/KsEWtzKC4AuekSehDRFwwVn1f3Jnh4O09tz282IVRB52l9nQENn42U0xMXYOD5xnvgoPSD/bfHnIT4VSj2wjyuf4+b3rYPbaFo96fdAgZQcJkz2NClplPcgFUH31AJ2Lmv0vGgAotRxJAjUavQgM7fUt0OvYQBQLvY5HkZFJJd0TyEUQIiLvx38lU2vkbWW0930cEUvoGbsCby/hZe9A9BtrH8EhcsxsyfrlkE5/VXmRyXamgrKqyV4UCj0KQRT2oYsCvtttuliFNxoAGlI16TADmjujaEnov4/T4yth+gG4Iy1ttb0enwezqrsXzfTmaN4zkIqa0A1nv4guYXz2avXOe6LThI79/rJHVYYbUsxZqMmspfj6nT6bjoyQ1vd9+dBaPsgeMpO9Qr7l7P+2KxWQEUnlUi6OjpTVYeNgyC3qWv+S5WW0LxnqFVYmhWhYympzDPb4ZlWSiqm+SUxPxx+9F58MSmQAuj4/XAvJwRcFbuA4ywoBUgVwZUibcbkPxPBSNyGD8fuyfkHDx8EQaR5R0AXbohd61FfMtHAm9WPwbzyZDURQTR4eyVgnCpgo+j43xtsYx/CtBIOnjLhAtFPZq8VgdHK4JUja+GSPjNiCyQ7Irm+7g6isoWZDbrmjAxy3ij3oi1FeBLQ/ZS3lWIIfWTw9cznb6NJVPpIfYcn/Z3DHo0+80FjRwp0/y6Zq25vOjf9+PRg3BKo+N3roUzhG5kNa27bEFV7xjcsZ2071GUnBOjQ3McNKfGj/wDMkg85tQvtD2n7n3tmnH3bzgvPkaCjXhXZiC8TuyStW1G/eZR769Y7drMuOTd5WRHMl+ImgC0xLvSnrUJoOytqxsxMdRIc8S54N0ISaudRkrfmu6EGUGP7SxgQaxr67coR2L0lPcnD4eJZFkJEhhMSCm7sDNkq6qvVTmevZF+ohtqI6b++/sPkZFeAvJ2GwPfw+Ht4YE1gA2BGg/3RsB849gSuRXfM/DbXM2tCg3GrHvCHQYCwX14APL5XoHckrui9mUJGVWEuWL+P9FhOov3d8jjvdPTCvYmHw/lmU3SOs8hV8nW0udn8RmEm63qE3x2LeQ5qhOKVX5GOWW5GcFe0IJFV1YxM3gLJ4awLudAFgrtIYqgRnql0dbYZf7cJ3KngoQktZjNGMsQCH1rojL7wCSWgmUoQ/m4dHT25Gt+kpQsP8oahafFoKIPat9z+BjlXm87ioVJ/zU8BXhFQ+oMGp8S1AqAn0OYNJ4z4mkGGP3cGTGDDtQaoYSh6F/DghvXAqlhgAGJ93DDXnuYRY+o4I5TdwlM0FsLCVu7Lu962vJChffzrdh1ZzgnkBW+IAXxLPQpyOSR8knxfcuOGuZ1NcrRbwRr8uJ7TeFVU7bWl/AjTfD3YxA+tTV7vUB745mGx2RSFojwTUWznx9VvxE7hVs6/KjY3yMbdNDKa1xKCY5KO+g5n4ABgQDfOOTrP9frTN3fCqxstxVqeZ7BcQjejT0AngtO+m7yZnY4R1RVzD79+HC3We8QAx2sbjLdFkKEhvrFusrRuNmovq0hXeW6UvNJ2o8bIwkll7vgPU33ejUYdCnPVxk3QTNu7OSlQRrqp6CaVrATjXr7w1fqhmlEtauKM72Mi7oaauMKJwPYuJEOqAx6lpNDynLphwINNaumbUBXlj9ZbZLr5oiYo4To6p4aVqUvpYlXv0+8vx9r3UvdpbwQ/WQr6dxWp5IABhrCHreYJm5PlPjta/ZDpl9c0ntm38CxRiysCOqzVln2mfQHWPs/RKC19fM8lnx+buPKtcrTWWkz1iFpxrCng5qUZ4P2ssEeb+pPtjcTT6MxXOygpZtX4KC4TeZEBX3hVYHXtRA6W94xe0+PUbQUVum30iCVhoQO98GQFFZ7rw6JXkDzsGieXKgc6qZttPxv1IWMe+2ac9Rnz3CYo2TN19f1VsYI0VgO7PLqKEXdRKPjZCsJnUcyrX5KtzFEX6E2O3DA4YlidN5H5IJPCkHrqzns++2TOIVEyvk93fuO2qEY9KcNpU95IgOYTZBAIrqIksm3d/S2FaWYhBwkKRpqz3cBFZM/ebFiuyCAc3fe+W0CNWBt/AdLMu+O0a35qot1F/1k6RAo1PtXNtLyozupyu4Rk+q4SZo1Hbzy/Y+Sb0p5dL1Qbd8KucGNO9o0NDnRXE1vncRZy+F19U68Iy0BAzOK0TmpG0jSErxUBKASw4R06mJW0n7gGSKBuzoI7P2+CqyA1Sx0aAfgnciexYBVh3D+T5yt5Oru9JUU04TmIoEt5zlG3yTIvybofoH7IHOD20ce8wxEBz8eq6KFJh5Aamr1P1Mve2tA42grVKsM5A2c2kcZ8MfmNTyux4LdZnvc6u/VD/xnV8pxF2ScsIpe/KvzmFXH8kQ8lFZSbYZPl+uucts5ZZKjC0ai6El4HwbYMagXjZVDSEEKkA8sObuzgO9uYFr6gmExk6XgyMpUfn9+S0+ArNKDTHvJxiUF0ChuMNKNLIHG+xdgydsONnzXfLi+Zm0dvC+Yd8eMPVNpM5ZHY2h7PeWLOb34+zWaxGBYFHSz9xdKPhJki+/ZX8yP1I3YypjE1qJMCzcxWYoHwrLXrdVqXNhZuzHPSiJJilt7QSbmBG5BQTBRWxnG9x8bmChR6MgbQ4UWae/LD/VOqyQAPqGLivyW79tK9NQVpEnEiAgSyfM/Ltiucds3APhFT0+NAFmC9qzjwrUclnCA4unbORvfFoa93YGB1IE7+y4XYjeiKsPmqen6q+UxcwkgZjIr7AuRqwwH54evWafjUkKDeXKYtJQk/n+YIwjJhTrdb4nfO49+PV+Zywzr6CBRS"
)))
_PI_P = list(_PI[:18])
_PI_S = [list(_PI[18 + b * 256 : 18 + (b + 1) * 256]) for b in range(4)]

#: The key baked into the fixed transform -- the same one the handshake uses.
LSSEC_KEY = bytes.fromhex("ffffaa5511223300")
#: The fixed transform's CBC IV, as two big-endian words.
LSSEC_IV = struct.pack(">II", 0x01020304, 0x05060708)

_MASK = 0xFFFFFFFF


class _Blowfish:
    """Plain 16-round Blowfish; key schedule optional."""

    def __init__(self, key: bytes | None = None) -> None:
        self.P = list(_PI_P)
        self.S = [list(box) for box in _PI_S]
        if key:
            self._schedule(key)

    def _schedule(self, key: bytes) -> None:
        j = 0
        for i in range(18):
            k = 0
            for _ in range(4):
                k = ((k << 8) | key[j % len(key)]) & _MASK
                j += 1
            self.P[i] ^= k
        left = right = 0
        for i in range(0, 18, 2):
            left, right = self._encrypt(left, right)
            self.P[i], self.P[i + 1] = left, right
        for box in range(4):
            for i in range(0, 256, 2):
                left, right = self._encrypt(left, right)
                self.S[box][i], self.S[box][i + 1] = left, right

    def _f(self, x: int) -> int:
        a, b, c, d = (x >> 24) & 0xFF, (x >> 16) & 0xFF, (x >> 8) & 0xFF, x & 0xFF
        return ((((self.S[0][a] + self.S[1][b]) & _MASK) ^ self.S[2][c]) + self.S[3][d]) & _MASK

    def _encrypt(self, left: int, right: int) -> tuple[int, int]:
        for i in range(16):
            left ^= self.P[i]
            right ^= self._f(left)
            left, right = right, left
        left, right = right, left
        right ^= self.P[16]
        left ^= self.P[17]
        return left, right

    def _decrypt(self, left: int, right: int) -> tuple[int, int]:
        for i in range(17, 1, -1):
            left ^= self.P[i]
            right ^= self._f(left)
            left, right = right, left
        left, right = right, left
        right ^= self.P[1]
        left ^= self.P[0]
        return left, right

    def encrypt_cbc(self, data: bytes, iv: bytes) -> bytes:
        out = bytearray()
        prev = iv
        for i in range(0, len(data) - 7, 8):
            left, right = struct.unpack(">II", data[i : i + 8])
            pl, pr = struct.unpack(">II", prev)
            block = struct.pack(">II", *self._encrypt(left ^ pl, right ^ pr))
            out += block
            prev = block
        return bytes(out)

    def decrypt_cbc(self, data: bytes, iv: bytes) -> bytes:
        out = bytearray()
        prev = iv
        for i in range(0, len(data) - 7, 8):
            block = data[i : i + 8]
            dl, dr = self._decrypt(*struct.unpack(">II", block))
            pl, pr = struct.unpack(">II", prev)
            out += struct.pack(">II", dl ^ pl, dr ^ pr)
            prev = block
        return bytes(out)


#: The eight salt pairs the camera chooses from, as 8-byte big-endian blocks.
_SALTS = [
    struct.pack(">II", a, b)
    for a, b in (
        (0x704066E4, 0x0433D552), (0xED4B8FAC, 0x15F7E47B),
        (0x24471F11, 0x8B5EA1FC), (0x05960C31, 0x2B8C7F41),
        (0xFDA588C1, 0xEBA8B1F3), (0x99166056, 0x1BD3D550),
        (0xCD32687F, 0xA9E28A30), (0x2A8FE834, 0xDEC7EBF4),
    )
]


def _mac(blocks: bytes) -> bytes:
    """Last block of the fixed transform -- a Blowfish-CBC MAC."""
    return _Blowfish(LSSEC_KEY).encrypt_cbc(blocks, LSSEC_IV)[-8:]


def find_salt(own_ts: bytes, camera_ts: bytes, challenge: bytes) -> int:
    """Which of the eight salts reproduces the camera's stage-2 challenge.

    The camera picks one per session; the same search the pairing handshake
    does, reused here because field_a carries the salt index.
    """
    for index, salt in enumerate(_SALTS):
        if _mac(salt + camera_ts[:8] + own_ts[:8]) == challenge[:8]:
            return index
    raise ValueError("no salt reproduces the challenge -- wrong handshake values")


def field_a(salt_index: int, own_ts: bytes, camera_ts: bytes) -> bytes:
    """The 8-byte context value stage 3 builds: salt index, then two timestamps.

    Measured: byte 0 is the matched salt index (0-7), bytes 1-3 come from the
    camera timestamp, bytes 4-7 from our own.
    """
    return bytes([salt_index]) + camera_ts[1:4] + own_ts[0:4]


def session_key(
    stage4_payload: bytes, device_id: bytes, own_ts: bytes, camera_ts: bytes, challenge: bytes
) -> bytes:
    """Derive the 8-byte Blowfish session key for one pairing."""
    salt_index = find_salt(own_ts, camera_ts, challenge)
    fa = field_a(salt_index, own_ts, camera_ts)
    return _mac(stage4_payload[:8] + device_id[:8] + fa)


def _unpad(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


@dataclass(frozen=True)
class WifiCredentials:
    ssid: str
    password: str


def decrypt_config(config: bytes, key: bytes) -> WifiCredentials:
    """Recover SSID and password from the 0x2004 blob given the session key.

    Layout: 1 flag byte, 32 bytes SSID, 64 bytes password (both ciphertext),
    then the encryption mode. Decryption is Blowfish-CBC with an all-zero IV.
    """
    bf = _Blowfish(key)
    zero = bytes(8)
    ssid = bf.decrypt_cbc(config[1:33], zero)
    password = bf.decrypt_cbc(config[33:97], zero)
    return WifiCredentials(_unpad(ssid), _unpad(password))


#: Where each value sits inside a 17-byte handshake message:
#: stage byte, 8-byte timestamp, 4-byte device, 4-byte nonce.
def _timestamp(msg: bytes) -> bytes:
    return msg[1:9]


def _device_nonce(msg: bytes) -> bytes:
    return msg[9:17]


def decrypt_config_from_handshake(
    stage1: bytes, stage2: bytes, stage4: bytes, config: bytes
) -> WifiCredentials:
    """Recover the WiFi credentials straight from the pairing handshake.

    Takes the three handshake messages the client saw -- stage 1 (ours),
    stage 2 and stage 4 (the camera's) -- and the 0x2004 blob, and returns the
    access point's SSID and password. Everything the derivation needs is in
    those bytes:

      * own timestamp and device id from stage 1
      * camera timestamp and challenge from stage 2
      * the payload from stage 4

    This is the whole point of the module: the credentials fall out of what the
    client already captured while pairing, with no device secret and no matter
    how often the camera rotates the password.
    """
    key = session_key(
        stage4_payload=_device_nonce(stage4),
        device_id=_device_nonce(stage1),
        own_ts=_timestamp(stage1),
        camera_ts=_timestamp(stage2),
        challenge=_device_nonce(stage2),
    )
    return decrypt_config(config, key)
