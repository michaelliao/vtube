# -*- coding: utf-8 -*-

'''
Start dev server:

python vtube_dev.py --serve --port 5000
python vtube_dev.py --build
'''

import traceback, argparse, mimetypes, shutil, webbrowser

from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from jinja2 import Environment, FileSystemLoader

# base directory path:
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = TEMPLATE_DIR / 'static'

# Init Jinja2
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    block_start_string="[%",
    block_end_string="%]",
    variable_start_string="[[",
    variable_end_string="]]"
)

def render_template(templ_path: Path):
    context = {}
    template = jinja_env.get_template(templ_path.as_posix())
    return template.render(context)

class DevHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        # "/help/about.html?v=1" => "help/about.html"
        req_path_str = self.path.split('?')[0].lstrip('/')
        if not req_path_str:
            # "/" => "index.html"
            req_path_str = 'index.html'
        match req_path_str:
            case 'index.html':
                self.render(Path('index.html'))
                return
            case 'video.html':
                self.render(Path('video.html'))
                return
            case 'config.html':
                self.render(Path('config.html'))
                return
            case _ if not req_path_str.endswith('.html'):
                # try static file under template dir:
                static_file_path = TEMPLATE_DIR / req_path_str
                if static_file_path.is_file():
                    self.serve_file(static_file_path)
                    return
        # 404 error:
        self.send_error(404, f"Page not found by path: {self.path}")

    def render(self, templ_path: Path):
        try:
            rendered_html = render_template(templ_path)
            self.send_content('text/html', rendered_html.encode('utf-8'))
        except Exception as e:
            print(f"[ERROR] Failed to render template: {templ_path}: {e}")
            traceback.print_exc()
            self.send_error(500, f'Render template error: {str(e)}')

    def serve_file(self, file_path: Path):
        mime_type, _ = mimetypes.guess_type(file_path)
        try:
            content = file_path.read_bytes()
            self.send_content(mime_type, content)
        except Exception as e:
            print(f"[ERROR] Failed to read file {file_path}: {e}")
            self.send_error(500, f"Read file error: {str(e)}")

    def send_content(self, mime_type: str, content: bytes):
        self.send_response(200)
        self.send_header('Content-Type', mime_type or 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

def open_browser(url: str):
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[WARN] Open {url} failed: {e}")

def run_dev_server(port: int):
    server_address = ('localhost', port)
    httpd = ThreadingHTTPServer(server_address, DevHTTPRequestHandler)
    print(f"[INFO] vtube dev server started at: http://localhost:{port}")
    print("Press Ctrl+C to exit...")
    open_browser(f"http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

# Build mode: generate static pages
def build_static_site():
    dist_dir = BASE_DIR / 'dist'
    print(f"[BUILD] Build and output to: {dist_dir} ...")
    filters = ['*.html', '.*']
    shutil.copytree('templates', dist_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*filters))
    # render templates:
    for templ in ['index.html', 'video.html', 'config.html']:
        html = render_template(Path(templ))
        html_file = dist_dir / templ
        html_file.write_text(html, encoding='utf-8')
    print("done.")

def main():
    parser = argparse.ArgumentParser(description="vtube site builder")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--build',
        action='store_true',
        help='Generate static files.'
    )
    mode_group.add_argument(
        '--serve',
        action='store_true',
        help='Start dev server for preview. Default port is 5000.'
    )
    parser.add_argument(
        '--port',
        nargs='?',
        type=int,
        default=5000,
        metavar='PORT',
        help='Specify port.'
    )

    args = parser.parse_args()

    if args.build:
        build_static_site()
    elif args.serve:
        run_dev_server(port=args.port)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
