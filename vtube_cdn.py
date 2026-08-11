# -*- coding: utf-8 -*-

'''
Start CDN server:

python vtube_cdn.py --source <path> --port 5001
'''

import re, argparse, mimetypes

from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

cdn_web_root = Path('.')

class CdnHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        # "/help/about.html?v=1" => "help/about.html"
        req_path_str = self.path.split('?')[0].lstrip('/')
        cdn_file = cdn_web_root / req_path_str
        print(f'try cdn file: {cdn_file}')
        if not cdn_file.is_file():
            self.send_error(404, 'File not found.')
        else:
            range_header = self.headers.get('Range')
            if not range_header:
                self.serve_file(cdn_file)
            else:
                self.serve_file_by_range(cdn_file, range_header)

    def serve_file(self, file_path: Path):
        mime_type, _ = mimetypes.guess_type(file_path)
        try:
            content = file_path.read_bytes()
            self.send_content(mime_type, content)
        except Exception as e:
            print(f"[ERROR] Failed to read file {file_path}: {e}")
            self.send_error(500, f"Read file error: {str(e)}")

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Max-Age', '86400')

    def send_content(self, mime_type: str, content: bytes):
        self.send_response(200)
        self.send_cors_headers()
        self.send_header('Content-Type', mime_type or 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_file_by_range(self, file_path: Path, range_header: str):
        # Parse Range header: "bytes=1000-2000" or "bytes=1000-":
        match = re.match(r'bytes=(\d+)-(\d+)?', range_header)
        if not match:
            self.send_error(416, "Requested Range Not Satisfiable")
            return

        file_size = file_path.stat().st_size
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1

        if start >= file_size or end >= file_size or start > end:
            self.send_error(416, f"Requested Range Not Satisfiable (File size: {file_size})")
            return

        length = end - start + 1
        self.send_response(206)
        mime_type, _ = mimetypes.guess_type(file_path)
        self.send_cors_headers()
        self.send_header("Content-Type", mime_type or 'application/octet-stream')
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        try:
            with open(file_path, 'rb') as f:
                f.seek(start)
                buffer_size = 64 * 1024
                remaining = length
                while remaining > 0:
                    chunk_size = min(buffer_size, remaining)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"[ERROR] Failed during range streaming {file_path}: {e}")

def run_cdn_server(source_dir: str, port: int):
    global cdn_web_root
    cdn_web_root = Path(source_dir)
    if not cdn_web_root.is_dir():
        print(f'Error: source dir is not exist: {cdn_web_root}')
        return
    server_address = ('localhost', port)
    httpd = ThreadingHTTPServer(server_address, CdnHTTPRequestHandler)
    print(f"[INFO] vtube cdn server started at: http://localhost:{port}")
    print("Press Ctrl+C to exit...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

def main():
    parser = argparse.ArgumentParser(description="vtube cdn server")
    parser.add_argument(
        '--source',
        default=None,
        metavar='DIR',
        help='Start local CDN server for video source. Default port is 5001.'
    )
    parser.add_argument(
        '--port',
        nargs='?',
        type=int,
        default=5001,
        metavar='PORT',
        help='Specify port.'
    )

    args = parser.parse_args()

    if args.source:
        run_cdn_server(args.source, args.port)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
