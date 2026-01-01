import os
import time
import json
import requests
from config import TARGET_DELAY, MAX_RUNTIME_SECONDS
from notifier import send_telegram

TARGET_FILE = "targets.txt"
SUBS_DIR = "subs"
STATE_FILE = "state.json"

CHAOS_KEY = os.environ.get("CHAOS_KEY")

os.makedirs(SUBS_DIR, exist_ok=True)
START_TIME = time.time()

# ---------------- helpers ----------------

def load_targets():
    return [t.strip() for t in open(TARGET_FILE)
            if t.strip() and not t.startswith("#")]

def subs_path(domain):
    return f"{SUBS_DIR}/{domain}.txt"

def is_first_run(domain):
    return not os.path.exists(subs_path(domain))

def load_old(domain):
    if not os.path.exists(subs_path(domain)):
        return set()
    return set(open(subs_path(domain)).read().splitlines())

def save_all(domain, subs):
    with open(subs_path(domain), "w") as f:
        for s in sorted(subs):
            f.write(s + "\n")

def runtime_guard():
    if time.time() - START_TIME > MAX_RUNTIME_SECONDS:
        print("[!] Max runtime reached, exiting safely")
        exit(0)

# ---------------- sources ----------------

def fetch_crtsh(domain):
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    r = requests.get(url, timeout=30)

    subs = set()
    try:
        for e in r.json():
            for s in e.get("name_value", "").split("\n"):
                if "*" not in s:
                    subs.add(s.strip())
    except Exception:
        pass

    return subs

def fetch_chaos(domain):
    headers = {"Authorization": f"Bearer {CHAOS_KEY}"}
    url = f"https://dns.projectdiscovery.io/dns/{domain}/subdomains"

    r = requests.get(url, headers=headers, timeout=30)

    subs = set()
    if r.status_code == 200:
        for s in r.json().get("subdomains", []):
            subs.add(f"{s}.{domain}")

    return subs

# ---------------- main ----------------

def main():
    targets = load_targets()
    any_new_found = False

    for domain in targets:
        runtime_guard()

        old = load_old(domain)
        subs = set()

        subs |= fetch_crtsh(domain)
        subs |= fetch_chaos(domain)

        # 🔥 First time → baseline only
        if is_first_run(domain):
            save_all(domain, subs)
            time.sleep(TARGET_DELAY)
            continue

        diff = subs - old
        if diff:
            any_new_found = True
            msg = f"🚨 New Subdomains Found ({domain})\n\n"
            msg += "\n".join(sorted(diff))
            send_telegram(msg)

        save_all(domain, old | subs)
        time.sleep(TARGET_DELAY)

    if not any_new_found:
        send_telegram("👎 No subdomains Found from any targets.")

if __name__ == "__main__":
    main()
