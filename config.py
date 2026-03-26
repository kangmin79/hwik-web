# -*- coding: utf-8 -*-
"""
휙 공통 설정 — 환경변수, API 키, 공통 유틸리티
모든 Python 파일에서 import해서 사용
"""

import os
import sys

# Windows CMD UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", buffering=1)


def load_env():
    """프로젝트 루트의 .env 또는 env 파일에서 환경변수 로드"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in (".env", "env"):
        env_path = os.path.join(script_dir, fname)
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())
            return env_path
    return None


# 자동 로드
_loaded = load_env()

# ── API 키 ──
GOV_SERVICE_KEY = os.environ.get("GOV_SERVICE_KEY", "")
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "")
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NAVER_BLOG_ACCESS_TOKEN = os.environ.get("NAVER_BLOG_ACCESS_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# ── Anthropic API 설정 ──
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL_HAIKU = "claude-3-5-haiku-20241022"
ANTHROPIC_MODEL_SONNET = "claude-sonnet-4-20250514"

def anthropic_headers():
    """Anthropic API 공통 헤더"""
    return {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION
    }
