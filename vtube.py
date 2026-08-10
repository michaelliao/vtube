# -*- coding: utf-8 -*-

import traceback, argparse, mimetypes, shutil, webbrowser

from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from jinja2 import Environment, FileSystemLoader

from util import write_json, scan_videos, gen_video_images, select_best_title, gen_video_json

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
        print(f'GET: {self.path}')
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
    httpd = HTTPServer(server_address, DevHTTPRequestHandler)
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
    for templ in ['index.html', 'video.html']:
        html = render_template(Path(templ))
        html_file = dist_dir / templ
        html_file.write_text(html, encoding='utf-8')
    print("done.")

# Prepare videos: generate missing info.json, poster.jpg, thumb.jpg, thumbs.jpg:
def prepare_videos(video_root_dir: str):
    v_files = scan_videos(video_root_dir)
    for v_file in v_files:
        print(f'check video: {v_file}')
        i_file = v_file.with_name('info.json')
        if not i_file.is_file():
            print(f'  generate info: {i_file}')
            v_name = v_file.name
            d_name = v_file.parent.name
            info = dict(
                name = select_best_title(v_name, d_name),
                category = 'Default',
                tags = ['Sample']
            )
            write_json(i_file, info)
        gen_video_images(v_file)
  
    json_file = Path(video_root_dir) / 'videos.json'
    print(f'generate json: {json_file}')
    json_file.write_text(gen_video_json(video_root_dir))

def main():
    parser = argparse.ArgumentParser(description="vtube site builder")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--prepare',
        default=None,
        metavar='DIR',
        help='Prepare videos by auto-generate videos.json and metadata of each video.'
    )
    mode_group.add_argument(
        '--build',
        action='store_true',
        help='Generate static files.'
    )
    mode_group.add_argument(
        '--serve',
        nargs='?',
        type=int,
        const=5000,
        default=None,
        metavar='PORT',
        help='Start dev server for preview. Default port is 5000.'
    )

    args = parser.parse_args()

    if args.prepare:
        prepare_videos(args.prepare)
    elif args.build:
        build_static_site()
    elif args.serve:
        run_dev_server(port=args.serve)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
