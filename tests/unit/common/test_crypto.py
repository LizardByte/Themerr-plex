"""Certificates are generated and reused in a temporary directory."""

# local imports
from common import crypto


def test_certificate_lifecycle(tmp_path, monkeypatch):
    cert = tmp_path / 'cert.pem'
    key = tmp_path / 'key.pem'
    monkeypatch.setattr(crypto, 'CERT_FILE', str(cert))
    monkeypatch.setattr(crypto, 'KEY_FILE', str(key))
    assert crypto.initialize_certificate() == (str(cert), str(key))
    assert cert.exists()
    assert key.exists()
    assert crypto.check_expiration(str(cert)) > 300
    before = cert.read_bytes()
    assert crypto.initialize_certificate() == (str(cert), str(key))
    assert cert.read_bytes() == before
    monkeypatch.setattr(crypto, 'check_expiration', lambda _: 0)
    crypto.initialize_certificate()
    assert cert.read_bytes() != before
