# vTube

vTube is a video site generator.

vTube provides a dev server to preview web pages:

- `/`: index page, mapping to `index.html`;
- `/video.html?id=[id]`: video playing page, mapping to `video.html`.

All templates are stored under `templates`, and the dev server renders a template to HTML by jinja2.

NOTE: the block and variable start/end symbol is changed to `[% %]` and `[[ ]]` to avoid conflict of Vue3.

# Environment

Create a Python venv and install the following packages:

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
pip           25.2
scikit-learn  1.9.0
scipy         1.18.0
threadpoolctl 3.6.0
```

# Prepare Video Source

Organize all videos under a directory. For example: `free-videos`:

```
free-videos
├─ A Herd of Elephants/
│  └─ elephants.mp4
├─ Fox hunting/
│  └─ f0001.mp4
├─ Grizzly-bear/
│  └─ gb.mp4
├─ Piano under a tree/
│  └─ piano.mp4
├─ Smiling dog/
│  └─ dog.mp4
├─ Three Funny Santa Clauses/
│  └─ t003.mp4
└─ Traveling on the highway/
   └─ traveling.mp4
```

Run `python3 vtube.py --prepare free-videos` to generate `info.json`, `poster.jpg`, `thumb.jpg` and `thumbs.jpg` under each sub-directory.

This script also generates `config.json` and `videos.js`. You can modify the CDN config in these two files.

## Dev mode

Use `python3 vtube.py --serve` to start dev mode.

## Build mode

Use `python3 vtube.py --build free-videos` to generate static site.
