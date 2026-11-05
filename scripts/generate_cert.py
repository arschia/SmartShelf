"""Generate self-signed SSL certificate with Subject Alternative Names (SAN)."""
import os
import ipaddress
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_ROOT / "certs"
CERTS_DIR.mkdir(parents=True, exist_ok=True)

CERT_FILE = CERTS_DIR / "cert.pem"
KEY_FILE = CERTS_DIR / "key.pem"


def generate_self_signed_cert():
    print("[1/3] Generating RSA 2048 private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Collect SAN IPs and domains
    hostname = socket.gethostname()
    san_list = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]

    try:
        _, _, ips = socket.gethostbyname_ex(hostname)
        for ip in ips:
            if not ip.startswith("127."):
                san_list.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
                print(f"  Added SAN IP: {ip}")
    except Exception as e:
        print(f"  Warning detecting local IPs: {e}")

    print("[2/3] Generating self-signed X.509 certificate...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SMARTSHELF Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    print("[3/3] Saving certificate and key...")
    with open(KEY_FILE, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"\nCertificate generated successfully at:\n  - {CERT_FILE}\n  - {KEY_FILE}")


if __name__ == "__main__":
    generate_self_signed_cert()
