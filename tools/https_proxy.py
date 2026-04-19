#!/usr/bin/env python3
"""HTTPS reverse proxy using self-signed cert - terminates SSL, forwards to Vite"""
import ssl
import socket
import threading
import os

HOST = "0.0.0.0"
PORT = 10443
VITE_HOST = "127.0.0.1"
VITE_PORT = 5173

def handle(client_sock, addr):
    print(f"[proxy] conn from {addr}")
    vite_sock = None
    try:
        # Read request
        data = b""
        while True:
            chunk = client_sock.recv(8192)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data:
                header_end = data.index(b"\r\n\r\n") + 4
                headers = data[:header_end].decode('ascii', errors='replace')
                for line in headers.split('\r\n'):
                    if line.lower().startswith('content-length:'):
                        cl = int(line.split(':')[1].strip())
                        if len(data) >= header_end + cl:
                            print(f"[proxy] got full request {len(data)}b")
                            data = data[:header_end + cl]
                            break
                else:
                    print(f"[proxy] got request {len(data)}b")
                break
            if len(data) > 1024 * 1024:
                break

        if not data:
            client_sock.close()
            return

        # Connect to Vite
        try:
            vite_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            vite_sock.settimeout(20)
            vite_sock.connect((VITE_HOST, VITE_PORT))
        except Exception as e:
            print(f"[proxy] Vite connect error: {e}")
            client_sock.close()
            return

        vite_sock.sendall(data)
        print(f"[proxy] forwarded {len(data)}b")

        # Read full response from Vite
        response_parts = []
        while True:
            try:
                chunk = vite_sock.recv(32768)
                if not chunk:
                    break
                response_parts.append(chunk)
            except socket.timeout:
                break
            except Exception:
                break

        if response_parts:
            full_response = b"".join(response_parts)
            client_sock.sendall(full_response)
            print(f"[proxy] sent {len(full_response)}b back")

    except Exception as e:
        print(f"[proxy] error: {e}")
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
        try:
            if vite_sock:
                vite_sock.close()
        except Exception:
            pass
    print(f"[proxy] done")

def main():
    # Generate certs if missing
    cert_file = os.path.join(os.path.dirname(__file__), 'localhost.pem')
    key_file = os.path.join(os.path.dirname(__file__), 'localhost-key.pem')
    if not (os.path.exists(cert_file) and os.path.exists(key_file)):
        print("[proxy] generating self-signed cert...")
        os.system(f'openssl req -x509 -newkey rsa:2048 -keyout "{key_file}" -out "{cert_file}" '
                  f'-days 365 -nodes -subj "//CN=localhost" 2>nul')
        print("[proxy] cert generated")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(50)

    server_ssl = context.wrap_socket(server, server_side=True)
    print(f"[proxy] HTTPS proxy {HOST}:{PORT} -> {VITE_HOST}:{VITE_PORT}", flush=True)

    while True:
        try:
            client, addr = server_ssl.accept()
            t = threading.Thread(target=handle, args=(client, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            print("\n[proxy] bye")
            break
        except Exception as e:
            print(f"[proxy] accept error: {e}")

if __name__ == "__main__":
    main()
