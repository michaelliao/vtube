# -*- coding: utf-8 -*-

'''
util for other script.
'''

import re, sys, json, shlex, subprocess, unicodedata

from pathlib import Path

NOISE_PATTERNS = [
    r'1080p', r'720p', r'4k', r'x264', r'x265', r'mp4', r'mkv', r'dsc_\d+', r'vid_\d+', r'new folder', r'untitled', r'unnamed', r'新建文件夹'
]

class DotDict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def _clean_text(text: str) -> str:
    '''
    >>> _clean_text("a-couple-of-cats-in-the-snow.mp4")
    'a couple of cats in the snow'
    >>> _clean_text("上古卷轴5-1.17版本MOD整合包更新.mp4")
    '上古卷轴5 1.17版本MOD整合包更新'
    >>> _clean_text("DSC_0001.mp4")
    'DSC 0001'
    '''
    if text.endswith('.mp4'):
        text = text[:-4]
    text = re.sub(r'[-_]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _calculate_noise_penalty(text: str) -> float:
    penalty = 0.0
    text_lower = text.lower()
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, text_lower):
            penalty += 0.5
    words = text_lower.split()
    if not words:
        return 1.0
    meaningless_words = sum(1 for w in words if re.match(r'^[a-f0-9]{8,}$', w) or w.isdigit())
    penalty += (meaningless_words / len(words))
    return min(penalty, 1.0)

def _get_score(text: str) -> float:
    '''
    >>> _get_score("001")
    0.0
    >>> round(_get_score("A Couple Of Cats In The Snow"), 2)
    1.0
    >>> round(_get_score("Two Cats"), 2)
    0.8
    >>> round(_get_score("上古卷轴5 MOD整合包更新"), 2)
    0.96
    >>> round(_get_score("上古卷轴5 MOD"), 2)
    0.94
    '''
    if not text:
        return 0.0

    lang_chars = [c for c in text if unicodedata.category(c).startswith('L')]
    lang_char_count = len(lang_chars)
    if lang_char_count == 0:
        return 0.0

    no_space_len = len(text.replace(" ", ""))
    char_ratio = lang_char_count / no_space_len

    latin_words = len(re.findall(r'[a-zA-Z]+', text))
    non_latin_chars = sum(1 for c in lang_chars if not ('a' <= c.lower() <= 'z'))
    total_semantic_units = latin_words + non_latin_chars

    if 4 <= total_semantic_units <= 15:
        length_score = 1.0
    elif total_semantic_units < 4:
        length_score = 1.0 - (4 - total_semantic_units) * 0.2
    else:
        length_score = 1.0 - (total_semantic_units - 15) * 0.05
    length_score = max(0.1, min(1.0, length_score))

    noise_penalty = _calculate_noise_penalty(text)

    final_score = (char_ratio * 0.5) + (length_score * 0.5) - noise_penalty
    return max(0.0, final_score)

def select_best_title(filename: str, dirname: str) -> str:
    '''
    >>> select_best_title("a-couple-of-cats-in-the-snow", "Two Cats")
    'A Couple Of Cats In The Snow'
    >>> select_best_title("上古卷轴5 MOD整合包更新", "上古卷轴5 MOD")
    '上古卷轴5 Mod整合包更新'
    '''
    cleaned_fn = _clean_text(filename)
    cleaned_dn = _clean_text(dirname)

    score_fn = _get_score(cleaned_fn)
    score_dn = _get_score(cleaned_dn)

    best_raw = cleaned_fn if score_fn >= score_dn else cleaned_dn
    return best_raw.title()

def load_json(p: str|Path):
    return json.loads(Path(p).read_text(encoding='utf-8'), object_hook=DotDict)

def write_json(p: str|Path, obj: object):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=4), encoding='utf-8')

def path_by_symbol_link(symbol_link: Path) -> Path:
    if sys.platform == "win32":
        return Path(symbol_link.read_text(encoding='utf-8'))
    else:
        return symbol_link.resolve()

def create_symbol_link(target: Path, symbol_link: Path):
    if not target.exists():
        raise FileNotFoundError(f"Target path does not exist: {target}")

    # remove exist symbol_link:
    if symbol_link.exists() or symbol_link.is_symlink():
        symbol_link.unlink()

    if sys.platform == "win32":
        target_path = str(target.resolve())
        symbol_link.write_text(target_path, encoding='utf-8')
        print(f"created fake symbol link: {symbol_link} -> {target}")
    else:
        symbol_link.symlink_to(target)
        print(f"created symbol link: {symbol_link} -> {target}")

def run_cmd(cmd: str):
    result = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True
    )
    return result.stdout

def get_video_meta(fpath: str|Path) -> DotDict:
    result = run_cmd(f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height:format=duration -of json "{fpath.as_posix()}"')
    data = json.loads(result, object_hook=DotDict)
    return DotDict(
        width=data.streams[0].width,
        height=data.streams[0].height,
        duration=float(data.format.duration)
    )

def gen_video_images(fpath: str|Path, genPoster: bool=True, genThumb: bool=True, genThumbs: bool=True, override: bool=False):
    v = Path(fpath)
    meta = get_video_meta(v)
    snapTime = '00:00:00'
    if meta.duration > 100:
        snapTime = '00:00:30'
    elif meta.duration > 10:
        snapTime = '00:00:03'
    if genPoster:
        f = v.with_name('poster.jpg')
        if override or not f.is_file():
            print(f'  generate poster: {f}')
            run_cmd(f'ffmpeg -y -i "{v.as_posix()}" -ss {snapTime} -frames:v 1 -q:v 2 "{f.as_posix()}"')
    if genThumb:
        f = v.with_name('thumb.jpg')
        if override or not f.is_file():
            print(f'  generate thumb: {f}')
            run_cmd(f'ffmpeg -y -i "{v.as_posix()}" -ss {snapTime} -vf scale=-2:240 -frames:v 1 -q:v 2 "{f.as_posix()}"')
    if genThumbs:
        f = v.with_name('thumbs.jpg')
        if override or not f.is_file():
            print(f'  generate thumbs: {f}')
            run_cmd(f'ffmpeg -y -i "{v.as_posix()}" -vf fps=100/{int(meta.duration)},crop=ih*16/9:ih,scale=160:90,tile=100x1 -frames:v 1 "{f.as_posix()}"')

def scan_videos(pdir: str|Path):
    scan_dir = Path(pdir)
    found = []
    for d in scan_dir.iterdir():
        if d.is_dir():
            mp4_files = [f for f in d.iterdir() if f.is_file() and f.suffix == '.mp4']
            if len(mp4_files) == 0:
                continue
            if len(mp4_files) > 1:
                print(f'WARN: multiple mp4 found under {d}. will only pick the first one.')
                mp4_files.sort()
            found.append(mp4_files[0])
    return found

if __name__ == "__main__":
    import doctest
    doctest.testmod()
