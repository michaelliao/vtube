# -*- coding: utf-8 -*-

'''
generate videos.js used for vtube website.
'''

import json, hashlib
from pathlib import Path
from urllib.parse import quote

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import hstack
import numpy as np
import jieba

from util import DotDict, load_json, get_video_meta, scan_videos

def dump_counters(counters: dict):
    cs = []
    for cat, num in counters.items():
        cs.append((cat, num))
    return sorted(cs, key=lambda x: (-x[1], x[0]))

# tag: "Hello World" => "hello_world":
def clean_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_").lower()

def gen_suggestions(videos: list):
    print('generate suggestions...')
    all_videos = [DotDict(id=v.id, name=v.name, category=v.category, tags=v.tags[:]) for v in videos]
    id_to_index = { v.id: idx for idx, v in enumerate(all_videos) }
    if len(id_to_index) != len(all_videos):
        raise ValueError("Duplicate video ID!")
    # tag + category matrix:
    tags_corpus = [" ".join([clean_tag(t) for t in v.tags] + [clean_tag(v.category)]) for v in all_videos]
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

    def recommend(video_id: str, top_n = 12):
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
        suggestions[v.id] = recommend(v.id)
    return suggestions

def gen_video_json(videos_dir:str|Path):
    input_dir = Path(videos_dir)
    print(f'process video source dir: {input_dir}...')

    # global data:
    data = DotDict()

    # try load config:
    cfg_file = input_dir / 'config.json'
    print(f'load config {cfg_file}...')
    cfg_data = load_json(cfg_file)
    data.cdn = cfg_data.cdn

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

    data.categories = dump_counters(categories)
    data.tags = dump_counters(tags)
    data.suggestions = gen_suggestions(videos)
    data.videos = videos

    return json.dumps(data, ensure_ascii=False, indent=2)
