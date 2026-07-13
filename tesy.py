#!/usr/bin/env python3
"""pgprobe.py - layered Postgres connectivity tester.

Usage:
    python3 pgprobe.py "postgresql://user:pass@host:5432/dbname?sslmode=require"
or:
    DATABASE_URL="postgresql://..." python3 pgprobe.py

Layers:
  [1] DNS resolution        (does the name resolve from THIS machine?)
  [2] TCP connect           (do packets to port 5432 get through?)
  [3] Postgres handshake    (is the thing answering actually Postgres?)
  [4] Login + list tables   (real query; needs: pip install pg8000)

Layers 1-3 need nothing but Python itself.
"""
import os
import socket
import ssl
import struct
import sys
from urllib.parse import urlsplit, unquote


def fail(msg, verdict):
    print(f"  FAIL  {msg}")
    print(f"\nVERDICT: {verdict}")
    sys.exit(1)


url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", "")
if not url:
    url = input("Connection string: ").strip()

u = urlsplit(url)
host = u.hostname
port = u.port or 5432
user = unquote(u.username or "")
password = unquote(u.password or "")
dbname = (u.path or "").lstrip("/") or "postgres"

if not host:
    sys.exit("Could not parse a hostname out of that string. Expected postgresql://user:pass@host:5432/db")

print(f"Target: {host}:{port}   db={dbname}   user={user or '(none)'}")

# ---------------------------------------------------------------- layer 1
print("\n[1] DNS resolution")
try:
    ip = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)[0][4][0]
    print(f"  OK    {host} -> {ip}")
except socket.gaierror as e:
    fail(
        f"cannot resolve {host} ({e})",
        "The name does not resolve from this machine. On Azure this usually means the "
        "server is deployed private/VNet-only. No firewall rule can fix this from here; "
        "run migrations from inside the network (Cloud Shell) or let the deployed "
        "container self-migrate.",
    )

# ---------------------------------------------------------------- layer 2
print("\n[2] TCP connect")
try:
    s = socket.create_connection((host, port), timeout=8)
    print(f"  OK    port {port} is open from this machine")
except socket.timeout:
    egress = ""
    try:
        import urllib.request

        egress = (
            urllib.request.urlopen("https://ifconfig.me", timeout=5)
            .read()
            .decode()
            .strip()
        )
    except Exception:
        pass
    hint = f" This machine's public egress IP is {egress}." if egress else ""
    fail(
        f"timeout - packets to port {port} are being silently dropped",
        "Blocked below the application layer. No driver (prisma, python, psql, anything) "
        f"can get past this.{hint} Either that IP is missing from the Azure server's "
        "firewall rules, or this network blocks outbound 5432 entirely (web traffic on "
        "443 working while 5432 times out is the classic corporate-egress signature).",
    )
except ConnectionRefusedError:
    fail(
        "connection refused",
        "A machine answered but nothing is listening on that port. Double-check host and "
        "port - this is not a firewall drop, it is the wrong door.",
    )
except OSError as e:
    fail(f"socket error: {e}", "Low-level network error before reaching Postgres.")

# ---------------------------------------------------------------- layer 3
print("\n[3] Postgres protocol handshake")
try:
    s.sendall(struct.pack("!II", 8, 80877103))  # Postgres SSLRequest packet
    reply = s.recv(1)
except (socket.timeout, OSError) as e:
    s.close()
    fail(
        f"port open but no protocol reply ({e})",
        "TCP opened but the far end never answered the Postgres handshake - that smells "
        "like a proxy or TLS-inspection middlebox accepting the connection and sitting "
        "on it, not a real Postgres server.",
    )

if reply == b"S":
    print("  OK    the server speaks Postgres and offers SSL")
elif reply == b"N":
    print("  WARN  Postgres answered but refuses SSL (unexpected for Azure)")
else:
    s.close()
    fail(
        f"unexpected reply {reply!r}",
        "Something answered TCP but it is not behaving like Postgres - likely a "
        "middlebox intercepting the connection.",
    )

# ---------------------------------------------------------------- layer 4
print("\n[4] Login + query")
try:
    import pg8000.native as pg
except ImportError:
    s.close()
    print("  SKIP  pg8000 not installed. Layers 1-3 PASSED; to also run a real query:")
    print("        pip install pg8000    then rerun this script")
    print(
        "\nVERDICT: the network path to Postgres is GOOD from this machine. If prisma "
        "still fails from here, the problem is prisma-side (TLS certificate "
        "verification, or blocked engine downloads), not the network."
    )
    sys.exit(0)

s.close()
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE  # mirrors psql's sslmode=require: encrypt, don't verify

try:
    con = pg.Connection(
        user,
        host=host,
        port=port,
        database=dbname,
        password=password,
        ssl_context=ctx,
        timeout=10,
    )
except Exception as e:
    fail(
        f"login failed: {e}",
        "Network path is fine - this is a credentials or database-name problem. Check "
        "percent-encoding of special characters in the password (@ -> %40 etc) and the "
        "database name at the end of the URL path.",
    )

ver = con.run("select version()")[0][0]
print(f"  OK    logged in - {ver.split(',')[0]}")
rows = con.run("select tablename from pg_tables where schemaname='public' order by 1")
names = [r[0] for r in rows]
if names:
    shown = ", ".join(names[:12]) + (" ..." if len(names) > 12 else "")
    print(f"  OK    {len(names)} tables in schema public: {shown}")
else:
    print("  OK    query ran - schema public has no tables yet (empty database)")
con.close()

print(
    "\nVERDICT: FULL Postgres connectivity from this machine works, including a real "
    "query. Anything prisma does differently is prisma-specific - usually TLS cert "
    "verification (append &sslaccept=accept_invalid_certs to both URLs) or blocked "
    "engine downloads (run the migration through the docker image instead)."
)
