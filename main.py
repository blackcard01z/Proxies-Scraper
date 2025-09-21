#!/usr/bin/env python3
"""
Usage:
    python3 main.py --pages 1 2 3 4 5 6 7 8 9
    python3 main.py --pages 1-9 --verify --timeout 3 --workers 50
"""

import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import socket

BASE_URL = "https://www.freeproxy.world/"
USER_AGENT = "Mozilla/5.0 (compatible; ProxyScraper/1.0)"
DEFAULT_TIMEOUT = 5.0

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def fetch_page_html(page_num, proxy_type="socks4"):
    params = {
        "type": proxy_type,
        "page": page_num
    }
    resp = session.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_proxies_from_html(html, country_filter=None):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.layui-table tbody tr")
    results = []
    for tr in rows:
        ip_td = tr.select_one("td.show-ip-div")
        if not ip_td:
            continue
        ip = ip_td.get_text(strip=True)

        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        port_a = tds[1].find("a")
        port = port_a.get_text(strip=True) if port_a else tds[1].get_text(strip=True)

        speed_text = None
        speed_tag = tr.select_one("div.n-bar-wrapper p a")
        if speed_tag:
            speed_text = speed_tag.get_text(strip=True)
        else:
            m = re.search(r"(\d+)\s*ms", tr.get_text())
            if m:
                speed_text = m.group(0)
        speed_ms = int(re.search(r"(\d+)", speed_text).group(1)) if speed_text else None

        types_td = None
        for td in tds:
            if td.find("a") and any("type=" in (a.get("href","")) for a in td.find_all("a")):
                types_td = td
                break
        types = []
        if types_td:
            for a in types_td.find_all("a"):
                href = a.get("href", "")
                if "type=" in href:
                    types.append(a.get_text(strip=True).lower())
        else:
            txt = tr.get_text(" ", strip=True).lower()
            if "socks4" in txt: types.append("socks4")
            if "socks5" in txt: types.append("socks5")

        country_td = tds[2] if len(tds) >= 3 else None
        country = country_td.get_text(strip=True) if country_td else None
        if country_filter and country != country_filter:
            continue

        results.append({
            "ip": ip,
            "port": port,
            "speed_ms": speed_ms,
            "types": types,
            "country": country
        })
    return results

def filter_socks_and_speed(rows, max_ms=1000):
    out = []
    for r in rows:
        if not any(t in ("socks4", "socks5") for t in r["types"]):
            continue

        if r["speed_ms"] is not None and r["speed_ms"] > max_ms:
            continue
        out.append(r)
    return out


def measure_connect_time(ip, port, timeout=3.0):
    try:
        port = int(port)
    except Exception:
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    start = time.time()
    try:
        s.connect((ip, port))
        end = time.time()
        s.close()
        return int((end - start) * 1000)
    except Exception:
        try:
            s.close()
        except:
            pass
        return None


def verify_proxies(proxies, timeout=3.0, workers=50):
    verified = []
    tasks = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_to_proxy = {ex.submit(measure_connect_time, p["ip"], p["port"], timeout): p for p in proxies}
        for fut in as_completed(future_to_proxy):
            p = future_to_proxy[fut]
            try:
                ct = fut.result()
            except Exception:
                ct = None
            p2 = p.copy()
            p2["connect_ms"] = ct
            if ct is not None:
                verified.append(p2)
    return verified


def write_wordlist(proxies, out_path="proxies.txt"):

    lines = []
    seen = set()
    for p in proxies:
        line = f"{p['ip']}:{p['port']}"
        if line not in seen:
            seen.add(line)
            lines.append(line)

    lines = sorted(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(lines)


def expand_pages_arg(pages_arg):
    pages = set()
    for part in pages_arg:
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a); b = int(b)
            for i in range(a, b+1):
                pages.add(i)
        else:
            pages.add(int(part))
    return sorted(pages)


def main():
    parser = argparse.ArgumentParser(description="Scrape freeproxy.world socks4/socks5 and build ip:port wordlist")
    parser.add_argument("--pages", nargs="+", default=["1-9"],
                        help="pages to scrape (e.g. 1 3 5 or 1-9). Default 1-9")
    parser.add_argument("--type", choices=["socks4","socks5","both"], default="both",
                        help="which proxy type page to fetch. Default 'both' (will fetch socks4 then socks5)")
    parser.add_argument("--max-ms", type=int, default=1000, help="max reported speed (ms) to include")
    parser.add_argument("--verify", action="store_true", help="actually try to connect to each proxy and measure connect time")
    parser.add_argument("--timeout", type=float, default=3.0, help="connect timeout in seconds for verification")
    parser.add_argument("--workers", type=int, default=50, help="concurrent workers for verification")
    parser.add_argument("--out", default="proxies.txt", help="output wordlist file")
    args = parser.parse_args()

    pages = expand_pages_arg(args.pages)

    all_candidates = []

    types_to_fetch = []
    if args.type == "both":
        types_to_fetch = ["socks4", "socks5"]
    else:
        types_to_fetch = [args.type]

    for t in types_to_fetch:
        for pnum in pages:
            print(f"[+] Fetching {t} page {pnum} ...")
            try:
                html = fetch_page_html(pnum, proxy_type=t)
            except Exception as e:
                print(f"    ! fetch failed: {e}")
                continue
            parsed = parse_proxies_from_html(html)
            filtered = filter_socks_and_speed(parsed, max_ms=args.max_ms)
            print(f"    -> found {len(parsed)} entries, {len(filtered)} passed filter (<= {args.max_ms} ms & socks)")
            all_candidates.extend(filtered)

    # dedupe by ip+port
    unique = {}
    for p in all_candidates:
        key = f"{p['ip']}:{p['port']}"
        if key not in unique:
            unique[key] = p

    proxies_list = list(unique.values())
    print(f"[+] Total unique candidates after scraping/filter: {len(proxies_list)}")

    if args.verify:
        print("[+] Verifying connectivity (this may take a while)...")
        verified = verify_proxies(proxies_list, timeout=args.timeout, workers=args.workers)
        verified_ok = [p for p in verified if p.get("connect_ms") is not None]
        print(f"[+] Verified alive: {len(verified_ok)}")
        proxies_to_write = verified_ok
    else:
        proxies_to_write = proxies_list

    count = write_wordlist(proxies_to_write, out_path=args.out)
    print(f"[+] Wrote {count} proxies to {args.out}")


if __name__ == "__main__":
    main()
