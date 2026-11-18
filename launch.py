"""One-click LAN launcher for the existing FastAPI dashboard.
No internet calls, external telemetry, or third-party packages beyond the project.
"""
import ipaddress
import os
import socket
import subprocess
import sys

PORT = 8090

def private_ipv4(value):
    try:
        ip = ipaddress.ip_address(value)
        return ip.version == 4 and any(ip in n for n in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        ))
    except ValueError:
        return False

def choose_ip():
    candidates = []
    # No actual datagram is sent. The operating system selects the outbound interface.
    for destination in ("10.255.255.255", "192.168.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((destination, 1))
                candidates.append(sock.getsockname()[0])
        except OSError:
            pass
    try:
        candidates += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return next((a for a in candidates if private_ipv4(a)), None)

def main():
    print("=" * 54)
    print("   Talent Pool - Easy LAN Start")
    print("=" * 54)
    local_ip = choose_ip()
    if not local_ip:
        print("Could not automatically identify a private LAN IPv4 address.")
        print("You may have a corporate-managed/non-private IP.")
        print("Please ask IT for the approved LAN address/network settings.")
        return 1
    os.environ["TALENTPOOL_LAN_SHARE"] = "1"
    print(f"\nServer:   http://127.0.0.1:{PORT}")
    print(f"Share:    http://{local_ip}:{PORT}")
    print("\nShare the second address with coworkers on the approved intranet.")
    print("Keep this window open while the server is in use.")
    print("The Windows firewall/corporate policy must allow TCP 8090.")
    print("WARNING: reachable internal-network users can view/edit/delete.")
    print("For real personnel data, use IT-approved SSO and HTTPS.\n")
    cmd = [sys.executable, "-m", "uvicorn", "viewer:app",
           "--host", "0.0.0.0", "--port", str(PORT), "--no-proxy-headers"]
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    sys.exit(main())
