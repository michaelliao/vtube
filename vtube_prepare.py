# -*- coding: utf-8 -*-

'''
Process video source.

python vtube_prepare.py --prepare <path>
'''

import re, json, hashlib, argparse, shlex, subprocess, unicodedata
from pathlib import Path
from urllib.parse import quote

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import hstack
import numpy as np
import jieba

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

def _dump_counters(counters: dict):
    cs = []
    for cat, num in counters.items():
        cs.append((cat, num))
    return sorted(cs, key=lambda x: (-x[1], x[0]))

# tag: "Hello World" => "hello_world":
def _clean_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_").lower()

def _gen_suggestions(videos: list):
    print('generate suggestions...')
    all_videos = [DotDict(id=v.id, name=v.name, category=v.category, tags=v.tags[:]) for v in videos]
    id_to_index = { v.id: idx for idx, v in enumerate(all_videos) }
    if len(id_to_index) != len(all_videos):
        raise ValueError("Duplicate video ID!")
    # tag + category matrix:
    tags_corpus = [" ".join([_clean_tag(t) for t in v.tags] + [_clean_tag(v.category)]) for v in all_videos]
    tags_tfidf = TfidfVectorizer()
    tags_matrix = tags_tfidf.fit_transform(tags_corpus)
    # name matrix:
    name_corpus = [" ".join(jieba.lcut(v.name)) for v in all_videos]
    name_tfidf = TfidfVectorizer()
    name_matrix = name_tfidf.fit_transform(name_corpus)
    # merge:
    tags_matrix_weighted = tags_matrix * 1.0
    name_matrix_weighted = name_matrix * 0.2
    combined_matrix = hstack([tags_matrix_weighted, name_matrix_weighted]).tocsr()
    similarity_matrix = cosine_similarity(combined_matrix, combined_matrix)

    def _recommend(video_id: str, top_n = 12):
        target_idx = id_to_index[video_id]
        scores = similarity_matrix[target_idx]
        sorted_indices = np.argsort(scores)[::-1]
        recommended_videos = []
        for idx in sorted_indices:
            if idx == target_idx:
                continue
            recommended_videos.append(all_videos[idx].id)
            if len(recommended_videos) == top_n:
                break
        return recommended_videos

    suggestions = DotDict()
    for v in all_videos:
        suggestions[v.id] = _recommend(v.id)
    return suggestions

def gen_video_json(videos_dir:str|Path):
    input_dir = Path(videos_dir)
    print(f'process video source dir: {input_dir}...')

    # global data:
    data = DotDict()

    # scan video dir:
    print(f'scan videos under {input_dir}')
    v_files = scan_videos(input_dir)

    video_name_set = set()
    videos = []
    for v_file in v_files:
        print(f'process: {v_file}')
        f_info = v_file.with_name('info.json')
        v_info = load_json(f_info) if f_info.is_file() else DotDict(name='', category='Default', tags=[])
        v_name = v_info.name.strip() or v_file.parent.name
        if v_name in video_name_set:
            print(f'WARNING: duplidate video name: {v_name}')
            continue
        video_name_set.add(v_name)
        vmeta = get_video_meta(v_file)
        # video relative path as url:
        v_rel_file = v_file.relative_to(input_dir)
        videos.append(DotDict(
            id=hashlib.sha256(v_name.encode('utf-8')).hexdigest()[:8],
            name=v_name,
            category=v_info.category,
            tags=v_info.tags,
            duration=int(vmeta.duration),
            url=quote(v_rel_file.as_posix(), safe='/'),
            poster=quote(v_rel_file.with_name('poster.jpg').as_posix(), safe='/'),
            thumb=quote(v_rel_file.with_name('thumb.jpg').as_posix(), safe='/'),
            thumbs=quote(v_rel_file.with_name('thumbs.jpg').as_posix(), safe='/')
        ))

    print(f"loaded {len(videos)} videos.")

    # generate category and tags:
    categories = DotDict()
    tags = DotDict()

    for v in videos:
        cat = v.category
        if not cat in categories:
            categories[cat] = 0
        categories[cat] += 1
        for t in v.tags:
            if not t in tags:
                tags[t] = 0
            tags[t] += 1

    print(f'categories: {', '.join(categories)}')
    print(f'tags: {', '.join(tags)}')

    data.categories = _dump_counters(categories)
    data.tags = _dump_counters(tags)
    data.suggestions = _gen_suggestions(videos)
    data.videos = videos

    return json.dumps(data, ensure_ascii=False)

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
    parser = argparse.ArgumentParser(description="vtube video source builder")
    parser.add_argument(
        '--prepare',
        default=None,
        metavar='DIR',
        help='Prepare videos by auto-generate videos.json and metadata of each video.'
    )

    args = parser.parse_args()

    if args.prepare:
        prepare_videos(args.prepare)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
