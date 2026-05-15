import os
import sys
import json
import time
import random
import requests
import socket
import uuid
import argparse
from cryptography.fernet import Fernet

CONFIG_FILE = "login_config_autologin_ctk.json"
KEY_FILE = "secret_autologin_ctk.key"
EPORTAL_LOGIN_URL_BASE = "http://10.2.5.251:801/eportal/"

try:
    from win10toast import ToastNotifier
    _toast = ToastNotifier()
except Exception:
    _toast = None

def generate_key():
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        return generate_key()

def encrypt_data(data_str, key):
    f = Fernet(key)
    return f.encrypt(data_str.encode("utf-8"))

def decrypt_data(encrypted_data_bytes, key):
    f = Fernet(key)
    try:
        return f.decrypt(encrypted_data_bytes).decode("utf-8")
    except Exception:
        return None

def get_local_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        return ip
    except Exception:
        try:
            hostname = socket.gethostname()
            all_ips = socket.gethostbyname_ex(hostname)[2]
            for item_ip in all_ips:
                if not item_ip.startswith("127.") and (
                    item_ip.startswith("10.") or item_ip.startswith("192.168.") or (
                        item_ip.startswith("172.") and 16 <= int(item_ip.split('.')[1]) <= 31
                    )
                ):
                    return item_ip
            for item_ip in all_ips:
                if not item_ip.startswith("127."):
                    return item_ip
            if all_ips:
                return all_ips[0]
            return "10.0.0.1"
        except Exception:
            return "10.0.0.1"
    finally:
        if s:
            s.close()

def get_mac_address_formatted():
    try:
        mac_num = uuid.getnode()
        mac = format(mac_num, "012x")
        if len(mac) == 12:
            return mac.upper()
        return "000000000000"
    except Exception:
        return "000000000000"

def check_connectivity():
    try:
        requests.head("https://www.baidu.com", timeout=3)
        return True
    except requests.RequestException:
        return False

def notify(title, message):
    try:
        if _toast:
            _toast.show_toast(title, message, duration=3, threaded=True)
    except Exception:
        pass

def perform_login(username_base, password, isp_display_name):
    account_suffix_map = {
        "校园网": "",
        "中国电信": "@telecom",
        "中国移动": "@cmcc",
        "中国联通": "@unicom",
    }
    account_suffix = account_suffix_map.get(isp_display_name, "")
    user_account = f"{username_base}{account_suffix}"
    callback = f"dr{int(time.time() * 1000)}{random.randint(100,999)}"
    params = {
        "c": "ACSetting",
        "a": "Login",
        "DDDDD": user_account,
        "upass": password,
        "callback": callback,
        "login_method": "1",
        "wlan_user_ip": get_local_ip(),
        "wlan_user_mac": get_mac_address_formatted(),
        "wlan_ac_ip": "",
        "wlan_ac_name": "",
        "jsVersion": "3.0",
        "_": str(int(time.time() * 1000)),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        s = requests.Session()
        s.get(EPORTAL_LOGIN_URL_BASE, params=params, headers=headers, timeout=10)
        time.sleep(2)
        if check_connectivity():
            notify("校园网登录", "登录成功，网络已连接")
            return True
        else:
            notify("校园网登录", "登录失败，网络未连接")
            return False
    except requests.exceptions.Timeout:
        notify("校园网登录", "登录请求超时")
        return False
    except requests.exceptions.RequestException as e:
        notify("校园网登录", f"网络错误: {type(e).__name__}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default=None)
    parser.add_argument("--silent", action="store_true")
    args = parser.parse_args()
    key = load_key()
    if not os.path.exists(CONFIG_FILE):
        sys.exit(0)
    with open(CONFIG_FILE, "rb") as f:
        enc = f.read()
    dec = decrypt_data(enc, key)
    if not dec:
        sys.exit(0)
    cfg = json.loads(dec)
    accounts = cfg.get("accounts")
    if not accounts:
        acc = {
            "name": "默认",
            "username": cfg.get("username", ""),
            "password": cfg.get("password", ""),
            "isp_display_name": cfg.get("isp_display_name", "校园网"),
        }
        accounts = [acc]
    name = args.account or cfg.get("active_account") or accounts[0].get("name")
    sel = next((a for a in accounts if a.get("name") == name), accounts[0])
    if not sel.get("username") or not sel.get("password"):
        sys.exit(0)
    ok = perform_login(sel.get("username"), sel.get("password"), sel.get("isp_display_name"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
