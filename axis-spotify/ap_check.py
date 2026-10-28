"""Point unreachable Spotify access points at a reachable one via /etc/hosts.

librespot always tries the first access point returned by apresolve and can
hang for minutes if the network blocks it. All access points speak the same
protocol on ports 4070/443/80, so redirecting a blocked hostname is safe.
"""

import json
import socket
import urllib.request

APRESOLVE = "https://apresolve.spotify.com/?type=accesspoint"


def log(msg):
    print(f"[axis-spotify] {msg}", flush=True)


def reachable(host, port, attempts=3):
    for _ in range(attempts):
        try:
            socket.create_connection((host, port), timeout=4).close()
            return True
        except OSError:
            pass
    return False


def main():
    aps = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(APRESOLVE, timeout=10) as resp:
                aps = json.load(resp)["accesspoint"]
            break
        except Exception as err:
            error = err
    if aps is None:
        log(f"access point check skipped: {error}")
        return

    hosts = {}
    for ap in aps:
        host, port = ap.rsplit(":", 1)
        hosts.setdefault(host, []).append(int(port))

    good_ip = None
    bad = []
    for host, ports in hosts.items():
        if any(reachable(host, port) for port in ports):
            good_ip = good_ip or socket.gethostbyname(host)
            log(f"access point {host}: reachable")
        else:
            bad.append(host)
            log(f"access point {host}: unreachable")

    if not bad or not good_ip:
        return
    with open("/etc/hosts", "a") as hosts_file:
        for host in bad:
            hosts_file.write(f"{good_ip} {host}\n")
            log(f"redirecting {host} to {good_ip}")


if __name__ == "__main__":
    main()
