# -*- coding: utf-8 -*-
# ===================================================================
# Campus Login App - Advanced Version with Statistics & Monitoring
#
# Required libraries: customtkinter, requests, cryptography, psutil
# For tray icon functionality, you also need: pystray, Pillow
# Install them using pip:
# pip install customtkinter requests cryptography psutil pystray Pillow
# ===================================================================

import customtkinter as ctk
import json
import os
import threading
import time
import requests
import random
import socket
import uuid
import datetime
import psutil
import subprocess
import sys
from collections import deque
from cryptography.fernet import Fernet
from tkinter import messagebox, filedialog

# --- Attempt to import tray icon libraries ---
try:
    from PIL import Image
    import pystray
except ImportError:
    messagebox.showerror(
        "Missing Libraries",
        "The 'pystray' and 'Pillow' libraries are required for the system tray icon feature.\n\n"
        "Please install them by running:\n"
        "pip install pystray Pillow"
    )
    exit()

try:
    from win10toast import ToastNotifier
    _toast = ToastNotifier()
except Exception:
    _toast = None


# --- Configuration Constants ---
CONFIG_FILE = "login_config_autologin_ctk.json"
KEY_FILE = "secret_autologin_ctk.key"
EPORTAL_LOGIN_URL_BASE = "http://10.2.5.251:801/eportal/"
STATS_FILE = "network_stats.json"
HISTORY_FILE = "login_history.json"

ISP_ACCOUNT_SUFFIX_MAP = {
    "校园网": "",
    "中国电信": "@telecom",
    "中国移动": "@cmcc",
    "中国联通": "@unicom"
}
ISP_DISPLAY_LIST = list(ISP_ACCOUNT_SUFFIX_MAP.keys())


# ===================================================================
# Network Statistics and Login History Classes
# ===================================================================

class NetworkStats:
    def __init__(self):
        self.stats_file = STATS_FILE
        self.stats = self.load_stats()
        self.session_start_time = time.time()
        self.total_bytes_sent = 0
        self.total_bytes_recv = 0
        self.last_network_check = time.time()
        
    def load_stats(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self.get_default_stats()
        return self.get_default_stats()
    
    def get_default_stats(self):
        return {
            "total_connections": 0,
            "successful_connections": 0,
            "failed_connections": 0,
            "total_uptime": 0,
            "total_downtime": 0,
            "last_connection": None,
            "last_disconnection": None,
            "current_session_start": None,
            "session_count": 0
        }
    
    def save_stats(self):
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def record_connection(self):
        self.stats["total_connections"] += 1
        self.stats["last_connection"] = datetime.datetime.now().isoformat()
        self.stats["current_session_start"] = datetime.datetime.now().isoformat()
        self.stats["session_count"] += 1
        self.session_start_time = time.time()
        self.save_stats()
    
    def record_disconnection(self):
        if self.stats["current_session_start"]:
            start_time = datetime.datetime.fromisoformat(self.stats["current_session_start"])
            session_duration = (datetime.datetime.now() - start_time).total_seconds()
            self.stats["total_uptime"] += session_duration
            self.stats["last_disconnection"] = datetime.datetime.now().isoformat()
            self.stats["current_session_start"] = None
            self.save_stats()
    
    def record_successful_login(self):
        self.stats["successful_connections"] += 1
        self.save_stats()
    
    def record_failed_login(self):
        self.stats["failed_connections"] += 1
        self.save_stats()
    
    def get_current_session_duration(self):
        if self.stats["current_session_start"]:
            start_time = datetime.datetime.fromisoformat(self.stats["current_session_start"])
            return (datetime.datetime.now() - start_time).total_seconds()
        return 0
    
    def get_uptime_percentage(self):
        total_time = self.stats["total_uptime"] + self.stats["total_downtime"]
        if total_time > 0:
            return (self.stats["total_uptime"] / total_time) * 100
        return 0
    
    def update_network_usage(self):
        try:
            current_time = time.time()
            time_diff = current_time - self.last_network_check
            
            if time_diff >= 1.0:  # Update every second
                net_io = psutil.net_io_counters()
                self.total_bytes_sent = net_io.bytes_sent
                self.total_bytes_recv = net_io.bytes_recv
                self.last_network_check = current_time
        except:
            pass

class LoginHistory:
    def __init__(self):
        self.history_file = HISTORY_FILE
        self.history = self.load_history()
    
    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_history(self):
        try:
            # Keep only last 1000 entries
            if len(self.history) > 1000:
                self.history = self.history[-1000:]
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def add_login_attempt(self, username, isp, success, error_message=None):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "username": username,
            "isp": isp,
            "success": success,
            "error_message": error_message,
            "session_duration": 0  # Will be updated on disconnect
        }
        self.history.append(entry)
        self.save_history()
        return len(self.history) - 1  # Return index for later update
    
    def update_session_duration(self, index, duration):
        if 0 <= index < len(self.history):
            self.history[index]["session_duration"] = duration
            self.save_history()
    
    def get_recent_history(self, limit=20):
        return self.history[-limit:]
    
    def get_success_rate(self):
        if not self.history:
            return 0
        successful = sum(1 for entry in self.history if entry["success"])
        return (successful / len(self.history)) * 100


# ===================================================================
# Core algorithm and helper functions (Unchanged + New)
# ===================================================================

# --- Encryption Functions ---
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
    return f.encrypt(data_str.encode('utf-8'))

def decrypt_data(encrypted_data_bytes, key):
    f = Fernet(key)
    try:
        return f.decrypt(encrypted_data_bytes).decode('utf-8')
    except Exception:
        return None

# --- Network Helper Functions ---
def run_command(command):
    """
    Executes a shell command without opening a console window.
    """
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        stdout, stderr = process.communicate()
        try:
            output = stdout.decode('gbk')
        except UnicodeDecodeError:
            output = stdout.decode('utf-8', errors='ignore')
        return output
    except FileNotFoundError:
        return "命令未找到"

def get_local_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        return ip
    except Exception:
        # Fallback mechanism
        try:
            hostname = socket.gethostname()
            all_ips = socket.gethostbyname_ex(hostname)[2]
            for item_ip in all_ips:
                if not item_ip.startswith("127.") and \
                   (item_ip.startswith("10.") or \
                    item_ip.startswith("192.168.") or \
                    (item_ip.startswith("172.") and 16 <= int(item_ip.split('.')[1]) <= 31)):
                    return item_ip
            for item_ip in all_ips:
                if not item_ip.startswith("127."): return item_ip
            if all_ips: return all_ips[0]
            return "10.0.0.1" # Final fallback
        except Exception:
            return "10.0.0.1"
    finally:
        if s:
            s.close()

def get_mac_address_formatted():
    try:
        mac_num = uuid.getnode()
        mac = format(mac_num, '012x')
        if len(mac) == 12:
            return mac.upper()
        return "000000000000"
    except Exception:
        return "000000000000"

# --- Main Application Class (UI and Logic Integration) ---
class CampusLoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Campus Login - Advanced")
        self.geometry("480x780")
        self.resizable(False, False)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # --- Core Logic Variables ---
        self.key = load_key()
        self.session = requests.Session()
        self.keep_alive_thread = None
        self.is_logging_in = threading.Lock()
        self.stop_keep_alive = threading.Event() # Event to gracefully stop the thread
        self.tray_icon = None # To hold the tray icon object
        
        # --- Advanced Features State ---
        self.night_mode_failures = []
        self.is_night_mode_suspended = False

        # --- Statistics and History ---
        self.network_stats = NetworkStats()
        self.login_history = LoginHistory()
        self.current_login_index = None
        self.last_connection_status = False
        self.bandwidth_thread = None
        self.stop_bandwidth = threading.Event()
        self.latency_samples = deque(maxlen=120)
        self.stop_quality = threading.Event()

        self.accounts = []
        self.active_account = None

        # --- UI Components ---
        self.create_widgets()
        
        # --- System Tray Icon Setup ---
        self.setup_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.hide_window) # Override close button

        # --- Load Config and Auto-Login ---
        self.load_credentials_and_settings()
        self.on_remember_change()
        
        # --- Start Bandwidth Monitoring ---
        self.start_bandwidth_monitoring()
        self.start_quality_monitoring()
        self.update_stats_display()
        
        # --- Setup tab change event ---
        self.notebook.configure(command=self.on_tab_change)
    
    def on_tab_change(self):
        """Handle tab change events."""
        current_tab = self.notebook.get()
        if current_tab == "历史":
            self.update_history_display()

    def create_widgets(self):
        # Create notebook for tabs
        self.notebook = ctk.CTkTabview(self)
        self.notebook.pack(padx=20, pady=20, fill="both", expand=True)
        
        # Create tabs
        self.login_tab = self.notebook.add("登录")
        self.stats_tab = self.notebook.add("统计")
        self.history_tab = self.notebook.add("历史")
        
        # Setup Login Tab
        self.create_login_tab()
        
        # Setup Stats Tab
        self.create_stats_tab()
        
        # Setup History Tab
        self.create_history_tab()
        
        # Start with login tab
        self.notebook.set("登录")
    
    def create_login_tab(self):
        main_frame = ctk.CTkFrame(self.login_tab)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)

        title_label = ctk.CTkLabel(main_frame, text="校园网登录", font=ctk.CTkFont(size=28, weight="bold"))
        title_label.pack(pady=(10, 20))

        account_row = ctk.CTkFrame(main_frame)
        account_row.pack(pady=8, fill="x")
        self.account_var = ctk.StringVar(value="默认")
        self.account_menu = ctk.CTkOptionMenu(account_row, variable=self.account_var, values=["默认"], width=180, height=36, command=self.switch_account)
        self.account_menu.grid(row=0, column=0, padx=(0,10))
        add_btn = ctk.CTkButton(account_row, text="添加账号", width=90, height=36, command=self.add_account)
        add_btn.grid(row=0, column=1, padx=5)
        del_btn = ctk.CTkButton(account_row, text="删除账号", width=90, height=36, command=self.remove_account)
        del_btn.grid(row=0, column=2, padx=5)

        self.username_entry = ctk.CTkEntry(main_frame, placeholder_text="登录账号", width=280, height=42)
        self.username_entry.pack(pady=8)

        self.password_entry = ctk.CTkEntry(main_frame, placeholder_text="登录密码", show="*", width=280, height=42)
        self.password_entry.pack(pady=8)

        self.isp_var = ctk.StringVar(value=ISP_DISPLAY_LIST[0] if ISP_DISPLAY_LIST else "")
        self.isp_combobox = ctk.CTkOptionMenu(main_frame, variable=self.isp_var, values=ISP_DISPLAY_LIST, width=280, height=42)
        self.isp_combobox.pack(pady=10)
        
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.pack(pady=10, fill="x", padx=20)
        options_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.remember_var = ctk.BooleanVar()
        self.remember_check = ctk.CTkCheckBox(options_frame, text="记住密码", variable=self.remember_var, command=self.on_remember_change)
        self.remember_check.grid(row=0, column=0, sticky="w")

        self.autologin_var = ctk.BooleanVar()
        self.autologin_check = ctk.CTkCheckBox(options_frame, text="自动登录", variable=self.autologin_var, command=self.on_autologin_change)
        self.autologin_check.grid(row=0, column=1)

        self.keep_alive_var = ctk.BooleanVar(value=False)
        self.keep_alive_check = ctk.CTkCheckBox(options_frame, text="保持联网", variable=self.keep_alive_var, command=self.on_keep_alive_change)
        self.keep_alive_check.grid(row=0, column=2, sticky="e")
        
        # --- Advanced Options ---
        adv_frame = ctk.CTkFrame(main_frame)
        adv_frame.pack(pady=10, fill="x", padx=20)
        adv_frame.grid_columnconfigure((0, 1), weight=1)

        self.auto_connect_wifi_var = ctk.BooleanVar(value=False)
        self.auto_connect_wifi_check = ctk.CTkCheckBox(adv_frame, text="掉线自动连接校园网", variable=self.auto_connect_wifi_var)
        self.auto_connect_wifi_check.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.night_mode_var = ctk.BooleanVar(value=False)
        self.night_mode_check = ctk.CTkCheckBox(adv_frame, text="夜间算力节省", variable=self.night_mode_var)
        self.night_mode_check.grid(row=0, column=1, padx=10, pady=5, sticky="e")

        import_btn = ctk.CTkButton(adv_frame, text="导入配置", width=130, height=35, command=self.import_config)
        import_btn.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        export_btn = ctk.CTkButton(adv_frame, text="导出配置", width=130, height=35, command=self.export_config)
        export_btn.grid(row=1, column=1, padx=10, pady=5, sticky="e")

        self.autostart_var = ctk.BooleanVar(value=False)
        autostart_check = ctk.CTkCheckBox(adv_frame, text="开机自启", variable=self.autostart_var, command=self.on_autostart_change)
        autostart_check.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        self.login_button = ctk.CTkButton(main_frame, text="登 录", command=self.trigger_login_manual, width=280, height=48, font=ctk.CTkFont(size=18, weight="bold"))
        self.login_button.pack(pady=20)

        # --- Dynamic Status Display ---
        self.status_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=60)
        self.status_frame.pack(pady=(10, 0), fill="x", expand=True)
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_rowconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.status_frame, text="欢迎使用", wraplength=350, font=ctk.CTkFont(size=14))
        self.status_label.grid(row=0, column=0, sticky="ew")

        # Canvas for animations
        self.status_canvas = ctk.CTkCanvas(self.status_frame, width=24, height=24, bg="#2B2B2B", highlightthickness=0)
        self.status_animation_id = None
        
        # Bandwidth display
        self.bandwidth_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.bandwidth_frame.pack(pady=(10, 0), fill="x", padx=20)
        
        self.bandwidth_label = ctk.CTkLabel(self.bandwidth_frame, text="↑ 0 KB/s | ↓ 0 KB/s", font=ctk.CTkFont(size=11))
        self.bandwidth_label.pack()
    
    def create_stats_tab(self):
        stats_frame = ctk.CTkFrame(self.stats_tab)
        stats_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Title
        title_label = ctk.CTkLabel(stats_frame, text="网络统计", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.pack(pady=(10, 20))
        
        # Stats display
        self.stats_text = ctk.CTkTextbox(stats_frame, width=400, height=280, wrap="word")
        self.stats_text.pack(pady=10, padx=10, fill="both", expand=True)
        self.stats_text.configure(state="disabled")
        self.quality_canvas = ctk.CTkCanvas(stats_frame, width=400, height=120, bg="#2B2B2B", highlightthickness=0)
        self.quality_canvas.pack(pady=6)
    
    def create_history_tab(self):
        history_frame = ctk.CTkFrame(self.history_tab)
        history_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Title
        title_label = ctk.CTkLabel(history_frame, text="登录历史", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.pack(pady=(10, 20))
        
        # History display
        self.history_text = ctk.CTkTextbox(history_frame, width=400, height=400, wrap="word")
        self.history_text.pack(pady=10, padx=10, fill="both", expand=True)
        self.history_text.configure(state="disabled")
        
        # Clear history button
        clear_button = ctk.CTkButton(history_frame, text="清空历史", command=self.clear_history, width=150, height=35)
        clear_button.pack(pady=10)


    def set_status(self, message, color_name="blue", animation=None):
        """Thread-safe method to update the status bar with optional animation."""
        colors = {
            "blue": ("#3B8ED0", "#1F6AA5"), "green": ("#2CC985", "#2FA572"),
            "red": ("#E54E4E", "#C13C3C"), "orange": ("#F9992A", "#D37D1A"),
            "darkgreen": ("#27956B", "#27956B")
        }
        text_color = colors.get(color_name, colors["blue"])

        def _update():
            # Stop any previous animation
            if self.status_animation_id:
                self.status_canvas.after_cancel(self.status_animation_id)
                self.status_animation_id = None
            self.status_canvas.delete("all")
            self.status_canvas.grid_forget()
            
            self.status_label.configure(text=message, text_color=text_color)
            self.status_label.grid(row=0, column=0, sticky="ew", padx=(0,0))

            if animation:
                self.status_canvas.grid(row=0, column=1, padx=(10, 0), sticky="w")
                self.status_label.grid(row=0, column=0, sticky="ew", padx=(30,0)) # Make space for canvas
                if animation == "checking":
                    self._animate_checking(0)
                elif animation == "connected":
                    self.status_canvas.create_oval(5, 5, 15, 15, fill="#2CC985", outline="#2CC985", tags="dot")
                elif animation == "reconnecting":
                    self._animate_reconnecting(True)

        self.after(0, _update)

    def _animate_checking(self, angle):
        self.status_canvas.delete("arc")
        self.status_canvas.create_arc(5, 5, 15, 15, start=angle, extent=120,
                                      outline="#3B8ED0", style=ctk.ARC, width=2, tags="arc")
        self.status_animation_id = self.status_canvas.after(15, self._animate_checking, (angle + 10) % 360)

    def _animate_reconnecting(self, is_visible):
        self.status_canvas.delete("dot")
        if is_visible:
            self.status_canvas.create_oval(5, 5, 15, 15, fill="#F9992A", outline="#F9992A", tags="dot")
        self.status_animation_id = self.status_canvas.after(500, self._animate_reconnecting, not is_visible)
    
    def start_bandwidth_monitoring(self):
        """Start bandwidth monitoring in background thread."""
        if self.bandwidth_thread is None or not self.bandwidth_thread.is_alive():
            self.stop_bandwidth.clear()
            self.bandwidth_thread = threading.Thread(target=self._bandwidth_worker, daemon=True)
            self.bandwidth_thread.start()
    
    def _bandwidth_worker(self):
        """Background worker for bandwidth monitoring."""
        last_bytes_sent = 0
        last_bytes_recv = 0
        last_time = time.time()
        
        while not self.stop_bandwidth.is_set():
            try:
                current_time = time.time()
                time_diff = current_time - last_time
                
                if time_diff >= 1.0:  # Update every second
                    net_io = psutil.net_io_counters()
                    
                    if last_bytes_sent > 0 and last_bytes_recv > 0:
                        upload_speed = (net_io.bytes_sent - last_bytes_sent) / time_diff
                        download_speed = (net_io.bytes_recv - last_bytes_recv) / time_diff
                        
                        # Update display
                        upload_str = self.format_speed(upload_speed)
                        download_str = self.format_speed(download_speed)
                        
                        self.after(0, lambda: self.bandwidth_label.configure(
                            text=f"↑ {upload_str} | ↓ {download_str}"
                        ))
                    
                    last_bytes_sent = net_io.bytes_sent
                    last_bytes_recv = net_io.bytes_recv
                    last_time = current_time
                    
                    # Update network stats
                    self.network_stats.update_network_usage()
                
                time.sleep(0.1)
            except:
                time.sleep(1)
    
    def format_speed(self, bytes_per_second):
        """Format speed in appropriate units."""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.0f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    
    def update_stats_display(self):
        """Update statistics display."""
        try:
            stats = self.network_stats.stats
            current_duration = self.network_stats.get_current_session_duration()
            success_rate = self.network_stats.get_uptime_percentage()
            
            stats_text = f"""连接统计
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

总连接次数: {stats['total_connections']}
成功连接: {stats['successful_connections']}
失败连接: {stats['failed_connections']}
连接成功率: {success_rate:.1f}%

当前会话时长: {self.format_duration(current_duration)}
总在线时长: {self.format_duration(stats['total_uptime'])}
会话次数: {stats['session_count']}

最近连接: {self.format_datetime(stats['last_connection'])}
最近断开: {self.format_datetime(stats['last_disconnection'])}

网络使用量
↑ 上传: {self.format_bytes(self.network_stats.total_bytes_sent)}
↓ 下载: {self.format_bytes(self.network_stats.total_bytes_recv)}
总计: {self.format_bytes(self.network_stats.total_bytes_sent + self.network_stats.total_bytes_recv)}
"""
            
            self.stats_text.configure(state="normal")
            self.stats_text.delete("1.0", "end")
            self.stats_text.insert("1.0", stats_text)
            self.stats_text.configure(state="disabled")
        except:
            pass
        
        # Schedule next update
        self.after(2000, self.update_stats_display)
    
    def update_history_display(self):
        """Update history display."""
        try:
            recent_history = self.login_history.get_recent_history(50)
            
            if not recent_history:
                history_text = "暂无登录历史记录"
            else:
                history_text = "最近登录历史\n" + "="*50 + "\n\n"
                
                for entry in reversed(recent_history):
                    timestamp = self.format_datetime(entry['timestamp'])
                    status = "✓ 成功" if entry['success'] else "✗ 失败"
                    duration = self.format_duration(entry['session_duration'])
                    
                    history_text += f"{timestamp}\n"
                    history_text += f"账号: {entry['username']} | 运营商: {entry['isp']}\n"
                    history_text += f"状态: {status} | 时长: {duration}\n"
                    
                    if entry['error_message']:
                        history_text += f"错误: {entry['error_message']}\n"
                    
                    history_text += "-" * 50 + "\n"
            
            self.history_text.configure(state="normal")
            self.history_text.delete("1.0", "end")
            self.history_text.insert("1.0", history_text)
            self.history_text.configure(state="disabled")
        except:
            pass
    
    def format_duration(self, seconds):
        """Format duration in human readable format."""
        if seconds < 60:
            return f"{seconds:.0f} 秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f} 分钟"
        else:
            return f"{seconds/3600:.1f} 小时"
    
    def format_datetime(self, dt_str):
        """Format datetime string."""
        if not dt_str:
            return "无"
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "无效时间"
    
    def format_bytes(self, bytes_count):
        """Format bytes in human readable format."""
        if bytes_count < 1024:
            return f"{bytes_count:.0f} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.1f} GB"
    
    def clear_history(self):
        """Clear login history."""
        if messagebox.askyesno("确认", "确定要清空所有登录历史记录吗？"):
            self.login_history.history = []
            self.login_history.save_history()
            self.update_history_display()
            self.set_status("历史记录已清空", "green")

    def notify(self, title, message):
        try:
            if _toast:
                _toast.show_toast(title, message, duration=3, threaded=True)
            else:
                pass
        except Exception:
            pass

    def update_account_menu(self):
        try:
            names = [a.get("name", "默认") for a in self.accounts] or ["默认"]
            self.account_menu.configure(values=names)
            if self.active_account and self.active_account in names:
                self.account_var.set(self.active_account)
            else:
                self.account_var.set(names[0])
        except Exception:
            pass

    def switch_account(self, name):
        try:
            self.active_account = name
            for a in self.accounts:
                if a.get("name") == name:
                    self.username_entry.delete(0, "end")
                    self.username_entry.insert(0, a.get("username", ""))
                    self.password_entry.delete(0, "end")
                    self.password_entry.insert(0, a.get("password", ""))
                    isp_name = a.get("isp_display_name", ISP_DISPLAY_LIST[0])
                    if isp_name in ISP_DISPLAY_LIST:
                        self.isp_var.set(isp_name)
                    break
        except Exception:
            pass

    def add_account(self):
        try:
            name = f"账号{len(self.accounts)+1}"
            acc = {
                "name": name,
                "username": self.username_entry.get(),
                "password": self.password_entry.get(),
                "isp_display_name": self.isp_var.get()
            }
            self.accounts.append(acc)
            self.active_account = name
            self.update_account_menu()
        except Exception:
            pass

    def remove_account(self):
        try:
            name = self.account_var.get()
            self.accounts = [a for a in self.accounts if a.get("name") != name]
            if not self.accounts:
                self.accounts = [{"name": "默认", "username": "", "password": "", "isp_display_name": ISP_DISPLAY_LIST[0]}]
            self.active_account = self.accounts[0].get("name")
            self.update_account_menu()
        except Exception:
            pass

    def import_config(self):
        try:
            path = filedialog.askopenfilename(title="选择配置文件", filetypes=[("JSON", "*.json"), ("All", "*.*")])
            if not path:
                return
            with open(path, "rb") as f:
                data = f.read()
            dec_json = decrypt_data(data, self.key)
            if not dec_json:
                messagebox.showerror("错误", "配置文件无法解密")
                return
            cfg = json.loads(dec_json)
            self._apply_config(cfg)
            self.save_credentials_and_settings()
            self.set_status("配置已导入", "green")
        except Exception:
            self.set_status("导入失败", "red")

    def export_config(self):
        try:
            cfg = self._collect_config()
            enc = encrypt_data(json.dumps(cfg), self.key)
            path = filedialog.asksaveasfilename(title="保存配置", defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            with open(path, "wb") as f:
                f.write(enc)
            self.set_status("配置已导出", "green")
        except Exception:
            self.set_status("导出失败", "red")

    def start_quality_monitoring(self):
        if not hasattr(self, "quality_thread") or not getattr(self, "quality_thread").is_alive():
            self.stop_quality.clear()
            self.quality_thread = threading.Thread(target=self._quality_worker, daemon=True)
            self.quality_thread.start()

    def _quality_worker(self):
        last_time = time.time()
        while not self.stop_quality.is_set():
            try:
                if time.time() - last_time >= 1.0:
                    latency = self._ping_latency("www.baidu.com")
                    self.latency_samples.append(latency if latency is not None else 500)
                    self.after(0, self._draw_quality_chart)
                    last_time = time.time()
                time.sleep(0.1)
            except Exception:
                time.sleep(1)

    def _ping_latency(self, host):
        try:
            out = run_command(f'ping {host} -n 1 -w 800')
            if "TTL" in out:
                for part in out.split():
                    if part.startswith("time=") or part.startswith("时间="):
                        val = ''.join(ch for ch in part if ch.isdigit())
                        if val:
                            return float(val)
            return None
        except Exception:
            return None

    def _draw_quality_chart(self):
        try:
            self.quality_canvas.delete("all")
            values = list(self.latency_samples)
            if not values:
                return
            w = int(self.quality_canvas["width"]) if isinstance(self.quality_canvas["width"], int) else 400
            h = int(self.quality_canvas["height"]) if isinstance(self.quality_canvas["height"], int) else 120
            max_v = max(values) if max(values) > 0 else 1
            step_x = w / max(1, len(values)-1)
            pts = []
            for i, v in enumerate(values):
                x = i * step_x
                y = h - (v / max_v) * (h - 10)
                pts.append((x, y))
            for i in range(1, len(pts)):
                x1, y1 = pts[i-1]
                x2, y2 = pts[i]
                self.quality_canvas.create_line(x1, y1, x2, y2, fill="#3B8ED0", width=2)
        except Exception:
            pass
    
    def on_autologin_change(self):
        if self.autologin_var.get():
            self.remember_var.set(True)
        self.on_remember_change()

    def on_remember_change(self):
        is_remembered = self.remember_var.get()
        state = ctk.NORMAL if is_remembered else ctk.DISABLED
        self.autologin_check.configure(state=state)
        self.keep_alive_check.configure(state=state)
        # Also control advanced options
        self.auto_connect_wifi_check.configure(state=state)
        self.night_mode_check.configure(state=state)

        if not is_remembered:
            self.autologin_var.set(False)
            self.auto_connect_wifi_var.set(False)
            self.night_mode_var.set(False)
            if self.keep_alive_var.get():
                self.keep_alive_var.set(False)
                self.on_keep_alive_change() # Stop the worker

    def on_keep_alive_change(self):
        if self.keep_alive_var.get():
            if not self.remember_var.get():
                messagebox.showerror("错误", "必须先“记住密码”才能使用保持联网功能。")
                self.keep_alive_var.set(False)
                return
            
            if self.keep_alive_thread is None or not self.keep_alive_thread.is_alive():
                self.stop_keep_alive.clear()
                self.set_status("“保持联网”功能已开启。", "darkgreen")
                self.keep_alive_thread = threading.Thread(target=self._keep_alive_worker, daemon=True)
                self.keep_alive_thread.start()
        else:
            self.stop_keep_alive.set()
            self.set_status("“保持联网”功能已关闭。", "blue")

    def _apply_config(self, config):
        try:
            self.remember_var.set(config.get("remember", False))
            self.autologin_var.set(config.get("autologin", False))
            self.keep_alive_var.set(config.get("keep_alive", False))
            self.auto_connect_wifi_var.set(config.get("auto_connect_wifi", False))
            self.night_mode_var.set(config.get("night_mode", False))
            self.autostart_var.set(config.get("autostart", False))
            self.accounts = config.get("accounts", [])
            if not self.accounts:
                acc = {
                    "name": "默认",
                    "username": config.get("username", ""),
                    "password": config.get("password", ""),
                    "isp_display_name": config.get("isp_display_name", ISP_DISPLAY_LIST[0])
                }
                self.accounts = [acc]
            self.active_account = config.get("active_account") or self.accounts[0].get("name")
            self.update_account_menu()
            self.switch_account(self.active_account)
            self.on_remember_change()
        except Exception:
            pass

    def _collect_config(self):
        try:
            if not self.accounts:
                self.accounts = [{
                    "name": "默认",
                    "username": self.username_entry.get(),
                    "password": self.password_entry.get(),
                    "isp_display_name": self.isp_var.get()
                }]
            cfg = {
                "remember": self.remember_var.get(),
                "autologin": self.autologin_var.get(),
                "keep_alive": self.keep_alive_var.get(),
                "auto_connect_wifi": self.auto_connect_wifi_var.get(),
                "night_mode": self.night_mode_var.get(),
                "accounts": self.accounts,
                "active_account": self.account_var.get(),
                "autostart": self.autostart_var.get()
            }
            return cfg
        except Exception:
            return {}

    def on_autostart_change(self):
        try:
            if self.autostart_var.get():
                self.register_autostart()
                self.set_status("已注册开机自启", "green")
            else:
                self.unregister_autostart()
                self.set_status("已取消开机自启", "blue")
        except Exception:
            self.set_status("开机自启设置失败", "red")

    def register_autostart(self):
        exe_path = sys.executable
        cmd = f'schtasks /Create /SC ONLOGON /DELAY 0000:30 /TN "CampusLoginAuto" /TR "\"{exe_path}\" --silent" /RL HIGHEST /F'
        run_command(cmd)

    def unregister_autostart(self):
        cmd = 'schtasks /Delete /TN "CampusLoginAuto" /F'
        run_command(cmd)

    def load_credentials_and_settings(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, "rb") as f: enc_data = f.read()
            if not enc_data: return
            dec_json = decrypt_data(enc_data, self.key)
            if not dec_json: return
            config = json.loads(dec_json)
            self._apply_config(config)
            if self.remember_var.get() and self.keep_alive_var.get():
                self.on_keep_alive_change()
            if self.autologin_var.get():
                acc = next((a for a in self.accounts if a.get("name") == self.active_account), self.accounts[0])
                if acc.get("username") and acc.get("password"):
                    self.set_status("检测到自动登录...", "blue", animation="checking")
                    self.after(500, lambda: self.trigger_login_auto(
                        acc.get("username"), acc.get("password"), acc.get("isp_display_name")
                    ))
        except Exception as e:
            self.set_status(f"加载配置失败: {e}", "red")
            if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)

    def save_credentials_and_settings(self):
        cfg = self._collect_config()
        if cfg["remember"]:
            try:
                encrypted_config = encrypt_data(json.dumps(cfg), self.key)
                with open(CONFIG_FILE, "wb") as f: f.write(encrypted_config)
            except Exception as e: self.set_status(f"保存配置失败: {e}", "red")
        elif os.path.exists(CONFIG_FILE):
            try:
                os.remove(CONFIG_FILE)
                self.set_status("配置已清除。", "green")
            except Exception as e: self.set_status(f"清除配置失败: {e}", "red")

    def trigger_login_manual(self):
        u, p, i_name = self.username_entry.get(), self.password_entry.get(), self.isp_var.get()
        if not u or not p: messagebox.showerror("错误", "账号和密码不能为空！"); return
        if not i_name: messagebox.showerror("错误", "请选择运营商！"); return
        self.save_credentials_and_settings()
        threading.Thread(target=self._perform_login, args=(u, p, i_name, "manual"), daemon=True).start()

    def trigger_login_auto(self, username, password, isp_display_name):
        threading.Thread(target=self._perform_login, args=(username, password, isp_display_name, "auto"), daemon=True).start()
    
    def _check_connectivity(self):
        try:
            requests.head('https://www.baidu.com', timeout=3)
            return True
        except requests.RequestException:
            return False

    def _connect_to_campus_wifi(self):
        """Attempts to connect to CUMT_Stu WiFi and returns success status."""
        command = 'netsh wlan connect name="CUMT_Stu"'
        result = run_command(command)
        if "已成功完成连接" in result or "Connection request was completed successfully" in result:
            return True
        return False

    def _record_night_mode_failure(self):
        """Records a login failure if night mode is active."""
        if not self.night_mode_var.get():
            return
        
        now = datetime.datetime.now().time()
        is_night_time = (now >= datetime.time(23, 30)) or (now < datetime.time(6, 0))
        
        if is_night_time:
            self.night_mode_failures.append(time.time())

    def _handle_night_mode(self):
        """Manages the night mode suspension logic. Returns False if suspended."""
        now = datetime.datetime.now()
        
        # If suspended, check if it's time to unsuspend
        if self.is_night_mode_suspended:
            if now.hour >= 6:
                self.is_night_mode_suspended = False
                self.night_mode_failures = []
                self.set_status("夜间模式结束，恢复网络检测。", "green")
                return True # Can continue
            else:
                return False # Still suspended
        
        # If not suspended, check if night mode is enabled
        if not self.night_mode_var.get():
            return True # Not enabled, can continue
            
        is_night_time = (now.time() >= datetime.time(23, 30)) or (now.time() < datetime.time(6, 0))
        if not is_night_time:
            return True # Not in time window, can continue
        
        # We are in the night window, check for failures
        current_time = time.time()
        # Filter failures to only include those in the last minute
        self.night_mode_failures = [t for t in self.night_mode_failures if current_time - t <= 60]
        
        if len(self.night_mode_failures) >= 3:
            self.is_night_mode_suspended = True
            self.set_status("校园网日常断网，将于6:00恢复检测。", "orange")
            return False # Suspend now
            
        return True # All checks passed, can continue

    def _keep_alive_worker(self):
        last_status_is_ok = False
        while not self.stop_keep_alive.is_set():
            # Handle night mode logic first
            if not self._handle_night_mode():
                time.sleep(30) # Sleep for a bit while suspended
                continue

            if self._check_connectivity():
                if not last_status_is_ok:
                    # Connection restored
                    self.set_status("网络连接正常。", "green", animation="connected")
                    last_status_is_ok = True
                    self.network_stats.record_connection()
            else:
                if last_status_is_ok:
                    # Connection lost
                    self.set_status("检测到网络断开，尝试重连...", "orange", animation="reconnecting")
                    last_status_is_ok = False
                    self.network_stats.record_disconnection()
                    
                    # Update current login session duration
                    if self.current_login_index is not None:
                        duration = self.network_stats.get_current_session_duration()
                        self.login_history.update_session_duration(self.current_login_index, duration)
                
                # --- NEW: Auto connect WiFi logic ---
                if self.auto_connect_wifi_var.get():
                    self.set_status("尝试连接校园网 WiFi...", "orange")
                    if self._connect_to_campus_wifi():
                        self.set_status("WiFi 连接成功，准备登录...", "blue")
                        time.sleep(3) # Give adapter time to get IP
                    else:
                        self.set_status("WiFi 连接失败，10秒后重试。", "red")
                        time.sleep(10)
                        continue # Skip login attempt

                u, p, i_name = self.username_entry.get(), self.password_entry.get(), self.isp_var.get()
                if u and p and i_name:
                    self._perform_login(u, p, i_name, "keep-alive")
                    time.sleep(0.5) # Wait after a reconnect attempt
                else:
                    self.set_status("保持联网失败：无账号信息。", "red")
                    self.after(0, lambda: self.keep_alive_var.set(False))
                    return
            time.sleep(0.5)

    def _perform_login(self, username_base, password, selected_isp, trigger_source):
        if not self.is_logging_in.acquire(blocking=False): return
        
        try:
            if trigger_source in ["manual", "auto"]:
                self.after(0, lambda: self.login_button.configure(state=ctk.DISABLED))
            
            self.set_status(f"正在登录 ({username_base})...", "blue", animation="checking")
            
            account_suffix = ISP_ACCOUNT_SUFFIX_MAP.get(selected_isp, "")
            user_account = f"{username_base}{account_suffix}"
            callback = f"dr{int(time.time() * 1000)}{random.randint(100,999)}"
            
            params = {
                "c": "ACSetting", "a": "Login", "DDDDD": user_account,
                "upass": password, "callback": callback, "login_method": "1",
                "wlan_user_ip": get_local_ip(), "wlan_user_mac": get_mac_address_formatted(),
                "wlan_ac_ip": "", "wlan_ac_name": "", "jsVersion": "3.0", 
                "_": str(int(time.time() * 1000))
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            # 发送登录请求，但不关心其具体返回值
            self.session.get(EPORTAL_LOGIN_URL_BASE, params=params, headers=headers, timeout=10)
            
            # --- 新的登录成功判断逻辑 ---
            self.set_status("请求已发送，2秒后检测连接...", "blue")
            time.sleep(2)

            if self._check_connectivity():
                # 登录成功
                self.set_status(f"登录成功！网络已连接。", "green", animation="connected")
                self.notify("校园网登录", "登录成功，网络已连接")
                
                # 记录统计和历史
                self.network_stats.record_successful_login()
                self.network_stats.record_connection()
                
                # 添加到登录历史
                self.current_login_index = self.login_history.add_login_attempt(
                    username_base, selected_isp, True, "检测到网络连接"
                )
                
                # 更新显示
                self.after(100, self.update_history_display)
                
            else:
                # 登录失败
                self.set_status("登录失败，2秒后未检测到网络。", "red")
                self.notify("校园网登录", "登录失败，网络未连接")
                self.network_stats.record_failed_login()
                self.current_login_index = self.login_history.add_login_attempt(
                    username_base, selected_isp, False, "2秒后网络未连接"
                )
                self._record_night_mode_failure() # 为夜间模式记录失败
                self.after(100, self.update_history_display)
        except requests.exceptions.Timeout:
            self.set_status("登录请求超时。", "red")
            self.notify("校园网登录", "登录请求超时")
            self.network_stats.record_failed_login()
            self.current_login_index = self.login_history.add_login_attempt(
                username_base, selected_isp, False, "登录请求超时"
            )
            self._record_night_mode_failure()
            self.after(100, self.update_history_display)
        except requests.exceptions.RequestException as e:
            self.set_status(f"网络错误: {type(e).__name__}", "red")
            self.notify("校园网登录", f"网络错误: {type(e).__name__}")
            self.network_stats.record_failed_login()
            self.current_login_index = self.login_history.add_login_attempt(
                username_base, selected_isp, False, f"网络错误: {type(e).__name__}"
            )
            self._record_night_mode_failure()
            self.after(100, self.update_history_display)
        finally:
            if trigger_source in ["manual", "auto"]:
                self.after(0, lambda: self.login_button.configure(state=ctk.NORMAL))
            self.is_logging_in.release()

    # --- System Tray Methods ---
    def setup_tray_icon(self):
        """Sets up and runs the system tray icon in a separate thread."""
        try:
            # Download and create icon image
            icon_url = "https://bkimg.cdn.bcebos.com/pic/3b87e950352ac65c1038cfd950a7a5119313b07e1c59?x-bce-process=image/format,f_auto/resize,m_lfit,limit_1,h_504"
            image_response = requests.get(icon_url, timeout=10)
            image = Image.open(image_response.raw).resize((64, 64))
        except Exception:
            # Fallback to a simple generated image if download fails
            image = Image.new('RGB', (64, 64), color = 'blue')

        menu = (
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Login', self.tray_login),
            pystray.MenuItem('Keep Alive', self.tray_toggle_keep_alive),
            pystray.MenuItem('Quit', self.quit_application)
        )
        
        self.tray_icon = pystray.Icon("CampusLoginApp", image, "Campus Login App", menu)
        
        # Run the icon in a non-blocking thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def tray_login(self, icon=None, item=None):
        try:
            u, p, i_name = self.username_entry.get(), self.password_entry.get(), self.isp_var.get()
            if u and p and i_name:
                threading.Thread(target=self._perform_login, args=(u, p, i_name, "tray"), daemon=True).start()
        except Exception:
            pass

    def tray_toggle_keep_alive(self, icon=None, item=None):
        try:
            self.keep_alive_var.set(not self.keep_alive_var.get())
            self.on_keep_alive_change()
        except Exception:
            pass

    def hide_window(self):
        """Hide the main window."""
        self.withdraw()

    def show_window(self):
        """Show the main window."""
        self.deiconify()

    def quit_application(self):
        """Gracefully quit the application."""
        # Stop all threads
        self.stop_keep_alive.set()  # Signal the keep-alive thread to stop
        self.stop_bandwidth.set()   # Signal the bandwidth monitoring thread to stop
        self.stop_quality.set()
        
        # Update final statistics
        if self.network_stats.stats.get("current_session_start"):
            self.network_stats.record_disconnection()
        
        # Stop tray icon
        if self.tray_icon:
            self.tray_icon.stop()
        
        # Destroy window and exit
        self.destroy()
        os._exit(0)  # Force exit to ensure all threads are terminated

if __name__ == "__main__":
    if "--silent" in sys.argv:
        try:
            key = load_key()
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "rb") as f:
                    enc = f.read()
                dec = decrypt_data(enc, key)
                if dec:
                    cfg = json.loads(dec)
                    accounts = cfg.get("accounts")
                    if not accounts:
                        accounts = [{
                            "name": "默认",
                            "username": cfg.get("username", ""),
                            "password": cfg.get("password", ""),
                            "isp_display_name": cfg.get("isp_display_name", ISP_DISPLAY_LIST[0])
                        }]
                    name = cfg.get("active_account") or accounts[0].get("name")
                    acc = next((a for a in accounts if a.get("name") == name), accounts[0])
                    if acc.get("username") and acc.get("password"):
                        s = requests.Session()
                        callback = f"dr{int(time.time() * 1000)}{random.randint(100,999)}"
                        params = {
                            "c": "ACSetting", "a": "Login", "DDDDD": f"{acc.get('username')}{ISP_ACCOUNT_SUFFIX_MAP.get(acc.get('isp_display_name'), '')}",
                            "upass": acc.get("password"), "callback": callback, "login_method": "1",
                            "wlan_user_ip": get_local_ip(), "wlan_user_mac": get_mac_address_formatted(),
                            "wlan_ac_ip": "", "wlan_ac_name": "", "jsVersion": "3.0",
                            "_": str(int(time.time() * 1000))
                        }
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                        try:
                            s.get(EPORTAL_LOGIN_URL_BASE, params=params, headers=headers, timeout=10)
                            time.sleep(2)
                            try:
                                requests.head('https://www.baidu.com', timeout=3)
                                if _toast:
                                    _toast.show_toast("校园网登录", "登录成功，网络已连接", duration=3, threaded=True)
                            except requests.RequestException:
                                if _toast:
                                    _toast.show_toast("校园网登录", "登录失败，网络未连接", duration=3, threaded=True)
                        except Exception:
                            pass
        except Exception:
            pass
    else:
        app = CampusLoginApp()
        app.mainloop()
