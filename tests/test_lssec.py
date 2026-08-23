"""LsSec: the WiFi-credential decryption, checked without any device data.

Two kinds of test. First the Blowfish core against the published Eric-Young
vectors, so the cipher itself is proven standard. Then the full chain -- salt
search, field_a, session key, decrypt -- against a synthetic pairing built here
from made-up numbers. The synthetic vector never touches a real camera, so no
serial, SSID or password lives in the repository, but it still exercises every
step end to end.

The scheme itself was verified separately against the vendor library and two
real plaintext/ciphertext pairs; that verification stays out of the tree.
"""

from __future__ import annotations

import struct

from skyshutter import lssec


def test_blowfish_matches_the_published_vectors() -> None:
    """Eric Young's Blowfish test vectors -- the cipher is standard."""
    bf = lssec._Blowfish(bytes(8))
    assert struct.pack(">II", *bf._encrypt(0, 0)).hex() == "4ef997456198dd78"

    bf = lssec._Blowfish(bytes.fromhex("ffffffffffffffff"))
    left, right = struct.unpack(">II", bytes.fromhex("ffffffffffffffff"))
    assert struct.pack(">II", *bf._encrypt(left, right)).hex() == "51866fd5b85ecb8a"


def test_blowfish_cbc_round_trips() -> None:
    bf = lssec._Blowfish(bytes.fromhex("0123456789abcdef"))
    iv = bytes(8)
    plain = b"skyshutter carves the night sky."  # 32 bytes
    assert bf.decrypt_cbc(bf.encrypt_cbc(plain, iv), iv) == plain


def _synthetic_pairing():
    """Build a self-consistent pairing from made-up numbers.

    Picks a salt, invents the two timestamps and the device id, then derives
    the challenge the camera would have sent (so the salt search finds it) and
    the session key. Encrypts a fake SSID and password the way the camera
    would. Returns everything a caller needs plus the expected plaintext.
    """
    own_ts = bytes.fromhex("1122334455667788")
    camera_ts = bytes.fromhex("99aabbccddeeff00")
    device_id = bytes.fromhex("0102030405060708")
    stage4 = bytes.fromhex("4142434445464748")
    salt_index = 5

    # The challenge the camera would send for that salt -- so find_salt lands
    # on salt_index rather than an earlier collision.
    challenge = lssec._mac(lssec._SALTS[salt_index] + camera_ts + own_ts)

    key = lssec.session_key(stage4, device_id, own_ts, camera_ts, challenge)
    bf = lssec._Blowfish(key)
    zero = bytes(8)
    ssid = b"NIGHTCAM_TEST".ljust(32, b"\x00")
    password = b"hunter2secret".ljust(64, b"\x00")
    config = (
        bytes([0x03])
        + bf.encrypt_cbc(ssid, zero)
        + bf.encrypt_cbc(password, zero)
        + bytes([0x03])
    )
    return {
        "own_ts": own_ts, "camera_ts": camera_ts, "device_id": device_id,
        "stage4": stage4, "challenge": challenge, "salt_index": salt_index,
        "config": config,
    }


def test_find_salt_lands_on_the_right_index() -> None:
    p = _synthetic_pairing()
    assert lssec.find_salt(p["own_ts"], p["camera_ts"], p["challenge"]) == p["salt_index"]


def test_field_a_carries_the_salt_index_then_the_timestamps() -> None:
    fa = lssec.field_a(5, bytes.fromhex("1122334455667788"), bytes.fromhex("99aabbccddeeff00"))
    assert fa[0] == 5
    assert fa[1:4] == bytes.fromhex("aabbcc")  # camera_ts[1:4]
    assert fa[4:8] == bytes.fromhex("11223344")  # own_ts[0:4]


def test_the_full_chain_recovers_ssid_and_password() -> None:
    p = _synthetic_pairing()
    key = lssec.session_key(
        p["stage4"], p["device_id"], p["own_ts"], p["camera_ts"], p["challenge"]
    )
    cred = lssec.decrypt_config(p["config"], key)
    assert cred.ssid == "NIGHTCAM_TEST"
    assert cred.password == "hunter2secret"


def test_a_wrong_challenge_is_reported_not_guessed() -> None:
    import pytest

    with pytest.raises(ValueError, match="no salt"):
        lssec.session_key(bytes(8), bytes(8), bytes(8), bytes(8), b"\xff" * 8)
