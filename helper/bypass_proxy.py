#!/usr/bin/env python3
"""
VPN Disconnector helper (macOS).

A tiny local HTTP/HTTPS proxy that sends every connection out through the
physical network interface (Wi-Fi / Ethernet) instead of the VPN tunnel.
It does this with the IP_BOUND_IF socket option, which pins a socket to an
interface and makes macOS use that interface's own (scoped) default route.

The Chrome extension routes only the sites you choose through this proxy;
everything else keeps going through NordVPN as usual.

Usage:  python3 bypass_proxy.py [--port 8899] [--interface en0]
"""
import argparse
import asyncio
import json
import logging
import os
import random
import re
import socket
import struct
import subprocess
import time

IP_BOUND_IF = 25      # <netinet/in.h>
IPV6_BOUND_IF = 125   # <netinet6/in6.h>
VPN_IFACE_PREFIXES = ("utun", "ipsec", "ppp", "tun", "tap", "wg", "gif", "stf", "lo")

log = logging.getLogger("vpn-bypass")


# --------------------------------------------------------------------------- #
# Interface / DNS detection
# --------------------------------------------------------------------------- #
class Network:
    """Finds the physical interface and its DNS servers (cached briefly)."""

    def __init__(self, forced_iface=None, ttl=15):
        self.forced = forced_iface
        self.ttl = ttl
        self._stamp = 0.0
        self.iface = None
        self.dns = []

    def refresh(self):
        if time.monotonic() - self._stamp < self.ttl and self.iface:
            return
        self.iface = self.forced or self._detect_iface()
        self.dns = self._detect_dns(self.iface) if self.iface else []
        self._stamp = time.monotonic()

    @staticmethod
    def _detect_iface():
        try:
            out = subprocess.run(["netstat", "-rn", "-f", "inet"],
                                 capture_output=True, text=True, timeout=3).stdout
        except Exception:
            return None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "default":
                gw, netif = parts[1], parts[3]
                if gw.startswith("link#") or netif.startswith(VPN_IFACE_PREFIXES):
                    continue
                return netif
        return None

    @staticmethod
    def _detect_dns(iface):
        try:
            out = subprocess.run(["ipconfig", "getoption", iface, "domain_name_server"],
                                 capture_output=True, text=True, timeout=3).stdout.strip()
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", out):
                return [out]
        except Exception:
            pass
        return []


def bound_socket(family, iface):
    sock = socket.socket(family, socket.SOCK_STREAM)
    idx = socket.if_nametoindex(iface)
    if family == socket.AF_INET:
        sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, idx)
    else:
        sock.setsockopt(socket.IPPROTO_IPV6, IPV6_BOUND_IF, idx)
    sock.setblocking(False)
    return sock


# --------------------------------------------------------------------------- #
# Minimal DNS resolver bound to the physical interface, so lookups for bypassed
# sites also skip the VPN (and you get the "local" answer for CDNs).
# Falls back to the system resolver on any problem.
# --------------------------------------------------------------------------- #
def _build_query(host, qid):
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode("idna") for p in host.rstrip(".").split(".")) + b"\0"
    return header + qname + struct.pack(">HH", 1, 1)  # A, IN


def _skip_name(data, off):
    while True:
        n = data[off]
        if n == 0:
            return off + 1
        if n & 0xC0 == 0xC0:
            return off + 2
        off += n + 1


def _parse_a_records(data, qid):
    rid, flags, qd, an, _, _ = struct.unpack(">HHHHHH", data[:12])
    if rid != qid or flags & 0x000F:
        return []
    off = 12
    for _ in range(qd):
        off = _skip_name(data, off) + 4
    ips = []
    for _ in range(an):
        off = _skip_name(data, off)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[off:off + 10])
        off += 10
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(data[off:off + 4]))
        off += rdlen
    return ips


async def resolve(host, net):
    try:
        socket.inet_pton(socket.AF_INET, host)
        return [(socket.AF_INET, host)]
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host.strip("[]"))
        return [(socket.AF_INET6, host.strip("[]"))]
    except OSError:
        pass

    loop = asyncio.get_running_loop()
    for server in net.dns:
        try:
            qid = random.randint(0, 0xFFFF)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, socket.if_nametoindex(net.iface))
            s.setblocking(False)
            try:
                await loop.sock_connect(s, (server, 53))
                await loop.sock_sendall(s, _build_query(host, qid))
                data = await asyncio.wait_for(loop.sock_recv(s, 4096), 2)
            finally:
                s.close()
            ips = _parse_a_records(data, qid)
            if ips:
                return [(socket.AF_INET, ip) for ip in ips]
        except Exception as e:
            log.debug("local DNS failed for %s via %s: %s", host, server, e)

    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    infos.sort(key=lambda i: i[0] != socket.AF_INET)  # prefer IPv4
    return [(fam, addr[0]) for fam, _, _, _, addr in infos]


async def open_bypass_connection(host, port, net):
    net.refresh()
    if not net.iface:
        raise OSError("no physical network interface found")
    loop = asyncio.get_running_loop()
    last_err = None
    for family, ip in await resolve(host, net):
        sock = bound_socket(family, net.iface)
        try:
            await asyncio.wait_for(loop.sock_connect(sock, (ip, port)), 10)
            return await asyncio.open_connection(sock=sock)
        except Exception as e:
            sock.close()
            last_err = e
    raise last_err or OSError(f"could not resolve {host}")


# --------------------------------------------------------------------------- #
# Proxy
# --------------------------------------------------------------------------- #
async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def split_host_port(hostport, default_port):
    if hostport.startswith("["):
        host, _, rest = hostport[1:].partition("]")
        return host, int(rest[1:]) if rest.startswith(":") else default_port
    host, sep, port = hostport.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return hostport, default_port


async def respond(writer, status, body, ctype="text/plain"):
    body = body.encode()
    writer.write(
        f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
        f"Access-Control-Allow-Origin: *\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n".encode()
        + body)
    await writer.drain()
    writer.close()


async def handle(client_r, client_w, net):
    try:
        head = await asyncio.wait_for(client_r.readuntil(b"\r\n\r\n"), 30)
    except Exception:
        client_w.close()
        return

    lines = head.decode("latin-1").split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        client_w.close()
        return

    # Health check used by the extension popup.
    if target.startswith("/"):
        net.refresh()
        await respond(client_w, "200 OK",
                      json.dumps({"ok": True, "interface": net.iface, "dns": net.dns}),
                      "application/json")
        return

    try:
        if method == "CONNECT":  # HTTPS (and anything else tunnelled)
            host, port = split_host_port(target, 443)
            up_r, up_w = await open_bypass_connection(host, port, net)
            client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_w.drain()
        else:  # plain HTTP with absolute URL
            m = re.match(r"http://([^/]+)(.*)", target, re.I)
            if not m:
                await respond(client_w, "400 Bad Request", "bad request")
                return
            host, port = split_host_port(m.group(1), 80)
            path = m.group(2) or "/"
            headers = [h for h in lines[1:] if h and not h.lower().startswith(
                ("proxy-connection:", "connection:", "keep-alive:"))]
            new_head = "\r\n".join([f"{method} {path} {version}", *headers,
                                    "Connection: close", "", ""]).encode("latin-1")
            up_r, up_w = await open_bypass_connection(host, port, net)
            up_w.write(new_head)
            await up_w.drain()
        log.info("%s %s:%s via %s", method, host, port, net.iface)
    except Exception as e:
        log.warning("failed %s %s: %s", method, target, e)
        await respond(client_w, "502 Bad Gateway", f"VPN bypass failed: {e}")
        return

    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("VPN_BYPASS_PORT", 8899)))
    ap.add_argument("--interface", help="physical interface to use (auto-detected if omitted)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    net = Network(args.interface)
    net.refresh()
    log.info("physical interface: %s, DNS: %s", net.iface or "NOT FOUND", net.dns or "system")

    server = await asyncio.start_server(lambda r, w: handle(r, w, net), "127.0.0.1", args.port)
    log.info("listening on 127.0.0.1:%d", args.port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
