# -*- coding: utf-8 -*-

import argparse

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
        action='store_true',
        help='Start dev server for preview. Default port is 5000.'
    )
    mode_group.add_argument(
        '--source',
        default=None,
        metavar='DIR',
        help='Start local CDN server for video source. Default port is 5001.'
    )
    parser.add_argument(
        '--port',
        nargs='?',
        type=int,
        default=0,
        metavar='PORT',
        help='Specify port.'
    )

    args = parser.parse_args()

    if args.prepare:
        from vtube_prepare import prepare_videos
        prepare_videos(args.prepare)
    elif args.build:
        from vtube_dev import build_static_site
        build_static_site()
    elif args.serve:
        port = args.port
        if port == 0:
            port = 5000
        from vtube_dev import run_dev_server
        run_dev_server(port=port)
    elif args.source:
        port = args.port
        if port == 0:
            port = 5001
        from vtube_cdn import run_cdn_server
        run_cdn_server(args.source, port)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
