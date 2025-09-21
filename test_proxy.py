import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

lock = Lock()

def check_socks5_proxy(proxy):
    proxies = {
        "http": f"socks5h://{proxy}",
        "https": f"socks5h://{proxy}"
    }
    try:
        response = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10, verify=False)
        if response.status_code == 200:
            print(f"[OK] {proxy} -> {response.text.strip()}")
            with lock:
                with open("ok_proxies.txt", "a") as f:
                    f.write(proxy + "\n")
            return True
        else:
            print(f"[FAILED] {proxy} -> Status {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAILED] {proxy} -> {e}")
        return False

def main():
    with open("proxies.txt", "r") as f:
        proxies = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=30) as executor:
        executor.map(check_socks5_proxy, proxies)

if __name__ == "__main__":
    main()
