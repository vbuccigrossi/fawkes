"""
TLS/SSL Support for Fawkes

Provides encrypted communication for controller-worker connections.
"""

import ssl
import socket
import os
import logging
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger("fawkes.auth.tls")


def generate_self_signed_cert(cert_file: str, key_file: str,
                              days_valid: int = 365,
                              common_name: str = "fawkes-controller") -> bool:
    """
    Generate a self-signed certificate for TLS

    Args:
        cert_file: Path to save certificate
        key_file: Path to save private key
        days_valid: Number of days certificate is valid
        common_name: Common name for certificate

    Returns:
        True if successful
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Fawkes"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("*.local"),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        # Write private key
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Write certificate
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # Set restrictive permissions on key file
        os.chmod(key_file, 0o600)
        os.chmod(cert_file, 0o644)

        logger.info(f"Generated self-signed certificate: {cert_file}")
        logger.info(f"Generated private key: {key_file}")
        return True

    except ImportError:
        logger.error("cryptography library not installed. Run: pip install cryptography")
        return False
    except Exception as e:
        logger.error(f"Failed to generate certificate: {e}", exc_info=True)
        return False


def create_ssl_context(cert_file: Optional[str] = None,
                       key_file: Optional[str] = None,
                       ca_file: Optional[str] = None,
                       is_server: bool = True,
                       require_client_cert: bool = False) -> ssl.SSLContext:
    """
    Create an SSL context for TLS connections

    Args:
        cert_file: Path to certificate file
        key_file: Path to private key file
        ca_file: Path to CA certificate file (for client verification)
        is_server: True for server context, False for client
        require_client_cert: Whether to require client certificates

    Returns:
        SSL context
    """
    # Create context with secure defaults
    if is_server:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    # Set minimum TLS version
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    # Disable insecure protocols
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    context.options |= ssl.OP_NO_TLSv1
    context.options |= ssl.OP_NO_TLSv1_1

    # Use strong ciphers only
    context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')

    if is_server:
        # Server context
        if cert_file and key_file:
            if not os.path.exists(cert_file):
                raise FileNotFoundError(f"Certificate file not found: {cert_file}")
            if not os.path.exists(key_file):
                raise FileNotFoundError(f"Key file not found: {key_file}")

            context.load_cert_chain(cert_file, key_file)
            logger.debug(f"Loaded server certificate: {cert_file}")

        if require_client_cert and ca_file:
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(ca_file)
            logger.debug("Enabled client certificate verification")
        else:
            context.verify_mode = ssl.CERT_NONE

    else:
        # Client context
        if ca_file:
            context.load_verify_locations(ca_file)
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = False  # Allow self-signed certs
            logger.debug(f"Loaded CA certificate: {ca_file}")
        else:
            # For self-signed certificates, don't verify
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            logger.warning("Client SSL verification disabled (using self-signed cert)")

        if cert_file and key_file:
            context.load_cert_chain(cert_file, key_file)
            logger.debug(f"Loaded client certificate: {cert_file}")

    return context


def wrap_socket_tls(sock: socket.socket, context: ssl.SSLContext,
                    is_server: bool = True,
                    server_hostname: Optional[str] = None) -> ssl.SSLSocket:
    """
    Wrap a socket with TLS

    Args:
        sock: Socket to wrap
        context: SSL context
        is_server: True for server socket, False for client
        server_hostname: Server hostname for client connections

    Returns:
        TLS-wrapped socket
    """
    try:
        if is_server:
            tls_sock = context.wrap_socket(sock, server_side=True)
            logger.debug("Wrapped socket as TLS server")
        else:
            tls_sock = context.wrap_socket(sock, server_side=False,
                                          server_hostname=server_hostname)
            logger.debug(f"Wrapped socket as TLS client (server: {server_hostname})")

        return tls_sock

    except ssl.SSLError as e:
        logger.error(f"TLS handshake failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to wrap socket with TLS: {e}", exc_info=True)
        raise


def verify_certificate(cert_file: str, ca_file: Optional[str] = None) -> bool:
    """
    Verify a certificate

    Args:
        cert_file: Path to certificate to verify
        ca_file: Optional CA certificate to verify against

    Returns:
        True if certificate is valid
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        with open(cert_file, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        # Check if certificate is expired
        now = datetime.utcnow()
        if now < cert.not_valid_before:
            logger.error("Certificate not yet valid")
            return False
        if now > cert.not_valid_after:
            logger.error("Certificate expired")
            return False

        logger.info(f"Certificate valid: {cert.subject}")
        return True

    except ImportError:
        logger.error("cryptography library not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to verify certificate: {e}", exc_info=True)
        return False


def get_default_cert_paths() -> Tuple[str, str]:
    """
    Get default paths for certificate and key files

    Returns:
        Tuple of (cert_file, key_file)
    """
    config_dir = Path.home() / ".fawkes" / "certs"
    config_dir.mkdir(parents=True, exist_ok=True)

    cert_file = str(config_dir / "fawkes.crt")
    key_file = str(config_dir / "fawkes.key")

    return cert_file, key_file


def ensure_certificates(cert_file: Optional[str] = None,
                       key_file: Optional[str] = None) -> Tuple[str, str]:
    """
    Ensure certificates exist, generating them if necessary

    Args:
        cert_file: Optional certificate file path
        key_file: Optional key file path

    Returns:
        Tuple of (cert_file, key_file)
    """
    if cert_file is None or key_file is None:
        cert_file, key_file = get_default_cert_paths()

    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        logger.info("Certificates not found, generating self-signed certificate...")
        if not generate_self_signed_cert(cert_file, key_file):
            raise RuntimeError("Failed to generate certificates")

    return cert_file, key_file
