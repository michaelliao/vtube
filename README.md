# vTube

[vTube](https://vtube.puppylab.org/) is a static video site but can connect to any video source.

## Configure video source

The site fetches `videos.json` from `<remote_url>/videos.json`. Open [config](https://vtube.puppylab.org/config.html) to add or select a `remote_url`; it is saved in localStorage (keeping a history of used URLs).

## Architecture

**vTube is only static pages, yet it can connect to any video source.**

The site is pure static HTML + JavaScript with no backend of its own. It holds no video data — instead it fetches everything (`videos.json` plus the media assets: video / poster / thumbnails) at runtime from a CDN, whose base URL (`remote_url`) is stored in the browser's localStorage.

Because the pages carry no data, the video source is fully decoupled from the site. **Point `remote_url` at a different CDN and the very same deployed pages become a completely fresh catalog of videos** — a brand-new site to browse and watch, with no rebuild and no redeploy. Just switch the video source (on the config page) and refresh.

Try another video source by [config new video source](https://vtube.puppylab.org/config.html?remote_url=https://cdn.vtube.puppylab.org/featured-videos/).

## Privacy

**All your data stays on your device — nothing is ever shared.** Since vTube has no backend, there is nowhere to send it. Your watch history and favorites live only in the browser's localStorage; they are never uploaded, tracked, or shared with any server (not even the CDN, which only serves videos). Clear your browser storage and it is gone for good.

## How to Build Video Source

Create a Python venv and install the packages by `pip install -r requirements.txt`.

Here is the package list:

```
$ pip list
Package       Version
------------- -------
jieba         0.42.1
Jinja2        3.1.6
joblib        1.5.3
MarkupSafe    3.0.3
narwhals      2.24.0
numpy         2.5.1
scikit-learn  1.9.0
scipy         1.18.0
threadpoolctl 3.6.0
```

vTube provides a dev server to preview web pages:

- `/`: index page, mapping to `index.html`;
- `/video.html?id=[id]`: video playing page, mapping to `video.html`;
- `/config.html`: config page to set the video source (`remote_url`), mapping to `config.html`.

All templates are stored under `templates`, and the dev server renders a template to HTML by jinja2.

NOTE: the block and variable start/end symbol is changed to `[% %]` and `[[ ]]` to avoid conflict of Vue3.

Check the sample site: [https://vtube.puppylab.org](https://vtube.puppylab.org)

### Prepare Video Source

Organize all videos under a directory. For example:

```
videos/
├─ a-herd-of-lions-walking/
│  └─ vid-12345.mp4
├─ a-private-jet-taking-off/
│  └─ video.mp4
├─ african-elephants-walking-on-a-dusty-ground/
│  └─ video(2).mp4
├─ airplane-landing-rear-view/
│  └─ unnamed.mp4
└─ ...
```

Run `python vtube.py --prepare videos` to generate `info.json`, `poster.jpg`, `thumb.jpg` and `thumbs.jpg` under each sub-directory and a global `videos.json`:

```
videos/
├─ a-herd-of-lions-walking/
│  ├─ info.json
│  ├─ poster.jpg
│  ├─ thumb.jpg
│  ├─ thumbs.jpg
│  └─ video.mp4
├─ a-private-jet-taking-off/
│  ├─ info.json
│  ├─ poster.jpg
│  ├─ thumb.jpg
│  ├─ thumbs.jpg
│  └─ video.mp4
├─ african-elephants-walking-on-a-dusty-ground/
│  ├─ info.json
│  ├─ poster.jpg
│  ├─ thumb.jpg
│  ├─ thumbs.jpg
│  └─ v12345.mp4
├─ airplane-landing-rear-view/
│  ├─ info.json
│  ├─ poster.jpg
│  ├─ thumb.jpg
│  ├─ thumbs.jpg
│  └─ unnamed.mp4
├─ ...
└─ videos.json
```

### Serve video source (local CDN)

The prepared directory is served by a CDN. For local testing, vTube includes a simple CDN server with CORS and HTTP range support (needed for video seeking):

Use `python vtube.py --source videos` to serve the directory (default port `5001`, override with `--port`). It exposes `videos.json` and the media assets, e.g. `http://localhost:5001/videos.json`.

To test your local CDN, visit [https://vtube.puppylab.org/config.html?remote_url=http://localhost:5001/](https://vtube.puppylab.org/config.html?remote_url=http://localhost:5001/) to add local CDN as a video source.

### Upload to CDN

Use `rclone` to upload video source to cloud storage. Here is an example to upload video source to CloudFlare R2:

```
$ rclone sync ./videos r2:vtube-sample/videos --progress
```

The video source url is `https://your-cdn/videos/`.

## Development

You can build your own static site based on the templates of vTube.

### Dev mode

Use `python vtube.py --serve` to start the dev server (default port `5000`, override with `--port`). It renders `index.html`, `video.html` and `config.html`, and serves the other static files (`store.js`, `favicon.ico`, ...) from `templates`.

## Build mode

Use `python vtube.py --build` to generate static site.

What you get:

```
dist/
├─ config.html
├─ index.html
├─ video.html
├─ store.js
└─ favicon.ico
```
