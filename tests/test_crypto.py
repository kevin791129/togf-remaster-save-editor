import pytest

from togf_save import crypto


@pytest.mark.parametrize("n", [0, 1, 15, 16, 17, 1000])
def test_roundtrip(n):
    data = (bytes(range(256)) * 4)[:n]
    assert crypto.decrypt(crypto.encrypt(data)) == data


def test_fixed_iv_is_deterministic():
    assert crypto.encrypt(b"same plaintext") == crypto.encrypt(b"same plaintext")


def test_key_and_iv_lengths():
    assert len(crypto.KEY) == 16 and len(crypto.IV) == 16


@pytest.mark.parametrize("data", [b"", b"x" * 15, b"x" * 17])
def test_bad_length(data):
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(data)


def test_bad_padding():
    ct = bytearray(crypto.encrypt(b"hello"))
    ct[-1] ^= 0xFF  # corrupts the last plaintext block, including the padding
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(bytes(ct))
