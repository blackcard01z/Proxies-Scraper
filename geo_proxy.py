import requests
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

lock = Lock()

API_URL = "http://ip-api.com/json/{}"  

def get_country(proxy_line):
    proxy = proxy_line.split(":")[0] 
    try:
        res = requests.get(API_URL.format(proxy), timeout=5)
        data = res.json()
        if data.get("status") == "success":
            country = data.get("country", "Unknown")
        else:
            country = "Unknown"
    except Exception as e:
        country = "Unknown"
    
    result_line = f"{proxy_line} {country}"
    print(result_line)
    
    with lock:
        with open("geo_proxy.txt", "a") as f:
            f.write(result_line + "\n")

def main():
    with open("ok_proxies.txt", "r") as f:
        proxies = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=30) as executor:
        executor.map(get_country, proxies)

if __name__ == "__main__":
    main()
