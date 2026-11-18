"""Talent Pool shared intranet launcher, following ksikkk/people serve --share-edit.

Use python app.py. Never sends internal data outside this PC.
Company firewall and networking still determine who can connect.
"""
import os
import socket
import subprocess
import sys
from ipaddress import IPv4Address

PORT = 8090


def network_addresses():
    """Discover locally bound IPv4 candidates; never query external IP services."""
    try:
        records = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return []
    found = set()
    for record in records:
        try:
            address = IPv4Address(record[4][0])
        except ValueError:
            continue
        if address.is_loopback or address.is_unspecified or address.is_multicast or address == IPv4Address("255.255.255.255"):
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((str(address), 0))
        except OSError:
            continue
        found.add(str(address))
    return sorted(found, key=lambda x: int(IPv4Address(x)))


def main():
    print("=" * 58, flush=True)
    print("Talent Pool | Intranet Shared Management", flush=True)
    print("=" * 58, flush=True)
    os.environ["TALENTPOOL_SHARE_EDIT"] = "1"
    print(f"\nMy PC: http://127.0.0.1:{PORT}", flush=True)
    addresses = network_addresses()
    for address in addresses:
        print(f"Other PC: http://{address}:{PORT}", flush=True)
    if not addresses:
        print(f"Other PC: http://<this PC's IPv4 address>:{PORT}", flush=True)
        print("Network IP auto-discovery unavailable. Server will still start.", flush=True)
        print("Use ipconfig to check IPv4 address if needed.", flush=True)
    print("\nShare the correct address only inside your approved intranet.", flush=True)
    print("Any device that can reach this port can read, edit, and delete data.", flush=True)
    print("Windows/company firewalls must permit port 8090. No firewall changes are made.", flush=True)
    print("Keep this console window open. Stop with Ctrl+C.", flush=True)
    print("Production use requires company-approved authentication and HTTPS.\n", flush=True)
    try:
        return subprocess.call([
            sys.executable, "-m", "uvicorn", "viewer:app",
            "--host", "0.0.0.0", "--port", str(PORT),
            "--no-proxy-headers"
        ])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
