"""AES layer of the save records (Noble.Encryption).

Rfc2898DeriveBytes(PASSWORD, SALT, 1000, SHA1) -> key = bytes 0-15, IV = bytes 16-31;
AES-128-CBC with PKCS7 padding. The IV is fixed, so unchanged plaintext re-encrypts
byte-identically.
"""
import hashlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .errors import SaveError

PASSWORD = b"1123581321345589"
SALT = b"saltString"
ITERATIONS = 1000

_derived = hashlib.pbkdf2_hmac("sha1", PASSWORD, SALT, ITERATIONS, 32)
KEY, IV = _derived[:16], _derived[16:]


class CryptoError(SaveError):
    """A record body could not be decrypted."""


def decrypt(data: bytes) -> bytes:
    if not data or len(data) % AES.block_size:
        raise CryptoError(f"ciphertext length {len(data)} is not a positive multiple of 16")
    try:
        return unpad(AES.new(KEY, AES.MODE_CBC, IV).decrypt(data), AES.block_size)
    except ValueError as e:
        raise CryptoError(f"bad PKCS7 padding after decrypt ({e})") from None


def encrypt(data: bytes) -> bytes:
    return AES.new(KEY, AES.MODE_CBC, IV).encrypt(pad(data, AES.block_size))
