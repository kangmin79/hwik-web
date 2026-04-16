#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_slug_index.py — 404 fuzzy redirect용 slug 인덱스 생성

gu/, dong/, ranking/ 폴더의 html 파일명을 JSON 배열로 내보낸다.
404.html이 이 파일을 fetch 해서 잘못된 URL → 가장 가까운 slug로 추측 리다이렉트.

산출물:
  gu-index.json       (~8 KB, 232개)
  dong-index.json     (~50 KB, 1,533개)
  ranking-index.json  (~3 KB, 73개)

GitHub Actions 매일 빌드에서 실행하면 새 단지 추가 시 자동 갱신.

사용법:
  python build_slug_index.py
"""

import json
import os
from pathlib import Path

BASE = Path(__file__).parent.resolve()


def build(folder_name: str) -> int:
    folder = BASE / folder_name
    if not folder.is_dir():
        return 0

    slugs = sorted(
        f.stem
        for f in folder.iterdir()
        if f.suffix == ".html" and f.stem != "index"
    )

    out_path = BASE / f"{folder_name}-index.json"
    out_path.write_text(
        json.dumps(slugs, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return len(slugs)


if __name__ == "__main__":
    for name in ("gu", "dong", "ranking"):
        n = build(name)
        print(f"  {name}-index.json: {n}개")
