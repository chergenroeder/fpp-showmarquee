#!/usr/bin/env python3
"""Check that this player can hear a WeatherFlow Tempest hub on the local network.

Run it ON the FPP player (no root needed):

    python3 tempest_listen.py              # listens 75 s, long enough for one full observation
    python3 tempest_listen.py --seconds 180

The hub broadcasts JSON over UDP port 50222:
  rapid_wind  about every 3 s   ob = [time, wind m/s, direction deg]
  obs_st      about every 60 s  obs[0] = [time, lull, avg, gust (m/s), direction, interval,
                                          pressure mb, air temp C, humidity %, ...]
It prints each reading as it arrives, in F and mph, then a report to paste back.
Other programs listening on the same port (Home Assistant, WeeWX) are not affected.
"""

import argparse
import json
import socket
import time
from collections import Counter

PORT = 50222
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def c_to_f(c):
    return c * 9 / 5 + 32


def ms_to_mph(ms):
    return ms * 2.236936


def compass(deg):
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def wind_text(ms, deg):
    if ms is None:
        return "wind ?"
    s = f"wind {ms_to_mph(ms):.0f} mph"
    return s + (f" {compass(deg)} ({deg:.0f}°)" if deg is not None and ms > 0 else "")


def open_socket(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):     # share the port with other listeners
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    s.bind(("", port))
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seconds", type=float, default=75)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--raw", action="store_true", help="also print every packet as received")
    a = p.parse_args()

    try:
        sock = open_socket(a.port)
    except OSError as e:
        raise SystemExit(f"Could not listen on UDP port {a.port}: {e}")
    sock.settimeout(1.0)
    print(f"Listening on UDP port {a.port} for {a.seconds:.0f} s ... (Ctrl+C to stop early)")

    counts = Counter()
    senders, hubs, stations = set(), set(), set()
    last_obs = last_wind = None
    first_at = None
    bad = 0
    end = time.monotonic() + a.seconds
    try:
        while time.monotonic() < end:
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except ValueError:
                bad += 1
                continue
            if not isinstance(msg, dict):
                bad += 1
                continue
            kind = str(msg.get("type", "?"))
            counts[kind] += 1
            senders.add(ip)
            if msg.get("hub_sn"):
                hubs.add(msg["hub_sn"])
            if first_at is None:
                first_at = time.monotonic()
            if a.raw:
                print(f"  {ip} {json.dumps(msg)[:200]}")
            stamp = time.strftime("%H:%M:%S")
            if kind == "obs_st" and msg.get("obs"):
                ob = msg["obs"][0]
                stations.add(msg.get("serial_number"))
                last_obs = ob
                temp = ob[7] if len(ob) > 7 else None
                print(f"{stamp} obs_st     from {msg.get('serial_number')}: "
                      + (f"{c_to_f(temp):.1f}°F" if temp is not None else "temp ?")
                      + f", {wind_text(ob[2] if len(ob) > 2 else None, ob[4] if len(ob) > 4 else None)}"
                      + (f", gust {ms_to_mph(ob[3]):.0f} mph" if len(ob) > 3 and ob[3] is not None else "")
                      + (f", humidity {ob[8]:.0f}%" if len(ob) > 8 and ob[8] is not None else ""))
            elif kind == "rapid_wind" and msg.get("ob"):
                ob = msg["ob"]
                last_wind = ob
                stations.add(msg.get("serial_number"))
                print(f"{stamp} rapid_wind from {msg.get('serial_number')}: {wind_text(ob[1], ob[2])}")
    except KeyboardInterrupt:
        print("Stopped")

    print("\n==== Tempest check (paste this back) ====")
    if not counts:
        print("Heard NOTHING on UDP port %d." % a.port)
        print("This player is probably on a different network from the Tempest hub (e.g. FPP's own")
        print("Wi-Fi or a separate show network), or a firewall blocks UDP broadcasts.")
        print(f"This player's addresses: {', '.join(addresses()) or 'unknown'}")
        return
    print(f"heard from: {', '.join(sorted(senders))}  hub(s): {', '.join(sorted(hubs)) or '?'}  "
          f"device(s): {', '.join(sorted(s for s in stations if s)) or '?'}")
    print("packets: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + (f", unreadable={bad}" if bad else ""))
    if last_obs:
        print(f"last obs_st: {c_to_f(last_obs[7]):.1f}°F, {wind_text(last_obs[2], last_obs[4])}, "
              f"gust {ms_to_mph(last_obs[3]):.0f} mph")
    else:
        print("no obs_st yet (it comes about once a minute: run longer with --seconds 180)")
    if last_wind:
        print(f"last rapid_wind: {wind_text(last_wind[1], last_wind[2])}")
    else:
        print("no rapid_wind (expected every ~3 s)")


def addresses():
    try:
        out = set()
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            out.add(info[4][0])
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))   # no packet is sent; picks the default interface
            out.add(s.getsockname()[0])
        finally:
            s.close()
        return sorted(a for a in out if not a.startswith("127."))
    except OSError:
        return []


if __name__ == "__main__":
    main()
