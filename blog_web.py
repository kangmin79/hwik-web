# -*- coding: utf-8 -*-
"""
블로그 원고 생성 웹 인터페이스
- hwik_engine.py run_pipeline() 을 웹에서 실행
- 실시간 진행 로그 스트리밍 (SSE)
- 완료 후 이미지 미리보기 + 파일 다운로드

실행:
  pip install flask
  python blog_web.py

접속: http://localhost:5050
"""

from config import load_env, SUPABASE_URL, SUPABASE_KEY

import os, sys, json, time, uuid, threading, queue, io, zipfile
import hashlib, secrets, urllib.parse
from pathlib import Path
from functools import wraps
import requests as _req

# ── Flask ─────────────────────────────────────────────────
try:
    from flask import Flask, request, jsonify, Response, send_file, session, redirect
except ImportError:
    print("❌ Flask 미설치 → pip install flask --break-system-packages")
    sys.exit(1)

# ── hwik_engine.py import (같은 폴더에 있어야 함) ─────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "hwik_engine", os.path.join(SCRIPT_DIR, "hwik_engine.py")
    )
    _engine = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_engine)
    run_pipeline = _engine.run_pipeline
    print("✅ hwik_engine.py 로드 완료")
except Exception as e:
    print(f"❌ hwik_engine.py 로드 실패: {e}")
    print("   blog_web.py 와 hwik_engine.py 를 같은 폴더에 두세요")
    sys.exit(1)

# ── Flask 앱 ──────────────────────────────────────────────
app = Flask(__name__)
jobs: dict = {}   # job_id → Job

# ── 인증 설정 ──────────────────────────────────────────────
_raw_secret = os.environ.get("ANTHROPIC_API_KEY", "hwik-blog-2026")
app.secret_key = hashlib.sha256(_raw_secret.encode()).hexdigest()[:32]

MIN_CARDS        = 3                                  # 원고 생성 최소 매물 수
KAKAO_REDIRECT   = "http://localhost:5050/kakao-callback"

DEFAULT_OUTPUT = os.path.join(Path.home(), "Desktop", "원고")

# ── Supabase (.env에서 로드 — config.py가 이미 load_env 실행) ──
SB_URL      = os.environ.get("SUPABASE_URL", "https://api.hwik.kr")       # REST API
SB_AUTH_URL = os.environ.get("SUPABASE_AUTH_URL", "https://jqaxejgzkchxbfzgzyzi.supabase.co")  # Auth API

def _sb_key():
    return os.environ.get("SUPABASE_KEY", "")

def _sb_hdr():
    k = _sb_key()
    return {"apikey": k, "Authorization": f"Bearer {k}"}

# 하위 호환용 (기존 코드에서 SB_KEY/SB_HDR 직접 쓰는 곳)
SB_KEY = _sb_key()
SB_HDR = _sb_hdr()

# PKCE verifier 임시 저장 (세션 대신 메모리 사용)
_pkce_store: dict = {}   # state → code_verifier


# ========================================================
# Job 클래스
# ========================================================
class Job:
    def __init__(self, job_id: str, apt_name: str, output_base: str):
        self.job_id      = job_id
        self.apt_name    = apt_name
        self.output_base = output_base
        self.status      = "running"   # running | done | error
        self.output_dir  = None
        self.error_msg   = ""
        self.log_queue   = queue.Queue()
        self.all_logs: list[str] = []


class _LogCapture(io.StringIO):
    """sys.stdout 을 가로채 SSE 큐에 실시간 전송"""
    def __init__(self, job: Job, orig_stdout):
        super().__init__()
        self.job   = job
        self._orig = orig_stdout

    def write(self, text: str):
        stripped = text.rstrip()
        if stripped:
            self.job.log_queue.put({"type": "log", "text": stripped})
            self.job.all_logs.append(stripped)
        self._orig.write(text)

    def flush(self):
        self._orig.flush()


# ========================================================
# HTML 페이지
# ========================================================
HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>휙 블로그 원고 생성</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --green:       #0F6E56;
  --green-light: #1a9c7a;
  --green-pale:  #e8f5f0;
  --green-glow:  rgba(15,110,86,.12);
  --bg:          #f4f5f7;
  --surface:     #ffffff;
  --border:      #e2e4e8;
  --text:        #1a1d23;
  --muted:       #6b7280;
  --log-bg:      #0e1117;
  --log-text:    #b8c4ce;
  --log-green:   #4ade80;
  --log-yellow:  #fbbf24;
  --log-red:     #f87171;
  --radius:      12px;
  --shadow:      0 2px 12px rgba(0,0,0,.07);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Noto Sans KR', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

/* ── 헤더 ── */
header {
  background: var(--green);
  padding: 0 32px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 12px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 16px rgba(0,0,0,.15);
}

.logo {
  font-size: 22px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.5px;
}

.logo-sub {
  font-size: 13px;
  color: rgba(255,255,255,.65);
  font-weight: 400;
  margin-left: 4px;
}

.nav-user-info {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-user-name {
  font-size: 13px;
  color: rgba(255,255,255,.85);
  font-weight: 500;
}

.btn-logout {
  padding: 5px 12px;
  background: rgba(255,255,255,.15);
  color: #fff;
  border: 1px solid rgba(255,255,255,.25);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  transition: background .15s;
}

.btn-logout:hover { background: rgba(255,255,255,.25); }

/* 매물 부족 경고 배너 */
.card-gate-banner {
  display: none;
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 10px;
  padding: 14px 18px;
  font-size: 13px;
  color: #92400e;
  line-height: 1.7;
  margin-bottom: 0;
}

.card-gate-banner strong { color: #d97706; }

/* ── 레이아웃 ── */
.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 64px;
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  align-items: start;
}

/* ── 카드 ── */
.card {
  background: var(--surface);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  padding: 28px;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title::before {
  content: '';
  width: 3px;
  height: 18px;
  background: var(--green);
  border-radius: 2px;
  display: block;
}

/* ── 입력 폼 ── */
.form-group {
  margin-bottom: 18px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 14px;
  color: var(--text);
  background: #fafafa;
  transition: border-color .2s, box-shadow .2s;
  outline: none;
}

.form-input:focus {
  border-color: var(--green);
  box-shadow: 0 0 0 3px var(--green-glow);
  background: #fff;
}

.form-input.big {
  font-size: 16px;
  padding: 13px 16px;
  font-weight: 500;
}

.form-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 5px;
}

/* ── 버튼 ── */
.btn-generate {
  width: 100%;
  padding: 13px;
  background: var(--green);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: background .2s, transform .1s, box-shadow .2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
}

.btn-generate:hover:not(:disabled) {
  background: var(--green-light);
  box-shadow: 0 4px 16px rgba(15,110,86,.3);
}

.btn-generate:active:not(:disabled) {
  transform: scale(.98);
}

.btn-generate:disabled {
  opacity: .6;
  cursor: not-allowed;
}

/* ── 스피너 ── */
.spinner {
  width: 16px;
  height: 16px;
  border: 2.5px solid rgba(255,255,255,.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .7s linear infinite;
  display: none;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 배치 힌트 ── */
.batch-hint {
  background: var(--green-pale);
  border: 1px solid rgba(15,110,86,.2);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  color: var(--green);
  margin-top: 16px;
  line-height: 1.7;
}

/* ── 히스토리 ── */
.history-list {
  list-style: none;
  margin-top: 0;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .15s;
  font-size: 13px;
}

.history-item:hover {
  background: var(--bg);
}

.history-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-done  { background: #22c55e; }
.dot-error { background: #ef4444; }
.dot-run   { background: var(--green-light); animation: pulse 1s infinite; }

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

/* ── 오른쪽 패널 ── */
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── 로그 터미널 ── */
.terminal {
  background: var(--log-bg);
  border-radius: var(--radius);
  border: 1px solid #1e2635;
  overflow: hidden;
  box-shadow: 0 4px 24px rgba(0,0,0,.2);
}

.terminal-header {
  background: #161b26;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.terminal-dots {
  display: flex;
  gap: 5px;
}

.terminal-dots span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.terminal-dots span:nth-child(1) { background: #ff5f57; }
.terminal-dots span:nth-child(2) { background: #febc2e; }
.terminal-dots span:nth-child(3) { background: #28c840; }

.terminal-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #4a5568;
  margin-left: 6px;
}

.log-body {
  height: 420px;
  overflow-y: auto;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--log-text);
}

.log-body::-webkit-scrollbar { width: 4px; }
.log-body::-webkit-scrollbar-track { background: transparent; }
.log-body::-webkit-scrollbar-thumb { background: #2d3748; border-radius: 2px; }

.log-line { display: block; word-break: break-all; }
.log-line.ok     { color: var(--log-green); }
.log-line.warn   { color: var(--log-yellow); }
.log-line.err    { color: var(--log-red); }
.log-line.head   { color: #93c5fd; font-weight: 500; }
.log-line.muted  { color: #4a5568; }

.log-placeholder {
  color: #2d3748;
  font-style: italic;
  padding: 20px 0;
}

/* ── 완료 패널 ── */
.result-panel {
  display: none;
}

.result-panel.show {
  display: block;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.image-thumb {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  aspect-ratio: 16/9;
  background: var(--bg);
  cursor: pointer;
  transition: transform .2s, box-shadow .2s;
}

.image-thumb:hover {
  transform: scale(1.02);
  box-shadow: 0 6px 20px rgba(0,0,0,.1);
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-label {
  font-size: 11px;
  color: var(--muted);
  text-align: center;
  margin-top: 4px;
}

.file-list {
  list-style: none;
}

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-radius: 6px;
  transition: background .15s;
  font-size: 13px;
  gap: 10px;
}

.file-item:hover {
  background: var(--bg);
}

.file-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.file-name {
  flex: 1;
  color: var(--text);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

.btn-dl {
  padding: 4px 10px;
  background: var(--green-pale);
  color: var(--green);
  border: 1px solid rgba(15,110,86,.2);
  border-radius: 5px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  transition: background .15s;
}

.btn-dl:hover {
  background: rgba(15,110,86,.15);
}

.btn-zip {
  width: 100%;
  padding: 10px;
  background: var(--green);
  color: #fff;
  border: none;
  border-radius: 7px;
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 12px;
  transition: background .2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-decoration: none;
}

.btn-zip:hover {
  background: var(--green-light);
}

/* ── 상태 배지 ── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.badge-running {
  background: #fef3c7;
  color: #d97706;
}

.badge-done {
  background: #dcfce7;
  color: #16a34a;
}

.badge-error {
  background: #fee2e2;
  color: #dc2626;
}

/* ── 빈 상태 ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  color: var(--muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: .4;
}

.empty-text {
  font-size: 14px;
  line-height: 1.6;
}

/* ── 라이트박스 ── */
.lightbox {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.85);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.lightbox.show {
  display: flex;
}

.lightbox img {
  max-width: 100%;
  max-height: 90vh;
  border-radius: 8px;
  object-fit: contain;
}

.lightbox-close {
  position: absolute;
  top: 16px;
  right: 20px;
  color: #fff;
  font-size: 28px;
  cursor: pointer;
  opacity: .7;
  transition: opacity .15s;
}

.lightbox-close:hover { opacity: 1; }

/* ── 자동완성 ── */
.ac-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background .12s;
}

.ac-item:last-child { border-bottom: none; }

.ac-item:hover, .ac-item.active {
  background: var(--green-pale);
}

.ac-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  flex-shrink: 0;
}

.badge-apt  { background: #dbeafe; color: #1d4ed8; }
.badge-offi { background: #fef9c3; color: #92400e; }

.ac-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ac-name em {
  color: var(--green);
  font-style: normal;
  font-weight: 700;
}

.ac-addr {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

.ac-empty {
  padding: 14px;
  text-align: center;
  font-size: 13px;
  color: var(--muted);
}

@media (max-width: 768px) {
  .container {
    grid-template-columns: 1fr;
    padding: 16px;
    gap: 16px;
  }
}
</style>
</head>
<body>

<header>
  <span class="logo">휙</span>
  <span class="logo-sub">블로그 원고 자동 생성</span>
  <div class="nav-user-info">
    <span class="nav-user-name" id="navUserName"></span>
    <a class="btn-logout" href="/logout">로그아웃</a>
  </div>
</header>

<div class="container">

  <!-- ── 왼쪽: 입력 + 히스토리 ── -->
  <div style="display:flex;flex-direction:column;gap:20px;">

    <div class="card">
      <div class="card-title">단지 입력</div>

      <div class="form-group" style="position:relative">
        <label class="form-label">단지명 <span style="color:#ef4444">*</span></label>
        <input id="apt-input" class="form-input big" type="text"
               placeholder="예) 동성4차  /  래미안블레스티지"
               autocomplete="off"
               oninput="onAptInput(this.value)"
               onkeydown="onAptKeydown(event)">
        <div class="form-hint">단지명 입력 시 DB에서 자동 검색됩니다</div>

        <!-- 자동완성 드롭다운 -->
        <div id="autocomplete-box" style="
          display:none;
          position:absolute;
          top:100%;
          left:0; right:0;
          margin-top:4px;
          background:#fff;
          border:1.5px solid var(--green);
          border-radius:10px;
          box-shadow:0 8px 32px rgba(0,0,0,.12);
          z-index:200;
          overflow:hidden;
          max-height:300px;
          overflow-y:auto;
        ">
          <div id="autocomplete-list"></div>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">출력 폴더 (선택)</label>
        <input id="output-input" class="form-input" type="text"
               placeholder="기본: 바탕화면/원고">
        <div class="form-hint">비워두면 바탕화면 원고 폴더에 저장됩니다</div>
      </div>

      <div class="form-group">
        <label class="form-label">매물 사진 (선택)</label>
        <label id="photo-label" style="
          display:flex;align-items:center;gap:8px;
          border:2px dashed #ccc;border-radius:10px;
          padding:12px 16px;cursor:pointer;
          color:#888;font-size:14px;
          transition:border-color .2s,color .2s;
        " onmouseover="this.style.borderColor='#1D9E75';this.style.color='#1D9E75'"
           onmouseout="this.style.borderColor='#ccc';this.style.color='#888'">
          <span style="font-size:20px">📷</span>
          <span id="photo-label-text">사진 선택 (여러 장 가능)</span>
          <input id="photo-input" type="file" multiple accept="image/*"
                 style="display:none" onchange="onPhotoChange(this)">
        </label>
        <div class="form-hint">선택한 사진은 Vision AI가 분석해 원고에 자동 삽입됩니다</div>
        <div id="photo-preview" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;"></div>
      </div>

      <button class="btn-generate" id="btn-gen" onclick="generate()">
        <span class="spinner" id="spinner"></span>
        <span id="btn-text">📄 원고 생성 시작</span>
      </button>

      <div class="batch-hint">
        💡 <strong>배치 입력</strong> 가능<br>
        여러 단지를 줄바꿈으로 구분하면 순차 처리됩니다<br>
        예) 신내동성4차↵신내우남푸르미아
      </div>

      <div class="card-gate-banner" id="cardGateBanner">
        ⚠️ 원고 생성은 휙에 <strong>매물 <span id="minCardsNum">3</span>개 이상</strong> 등록 시 사용 가능합니다.<br>
        현재 <strong><span id="currentCardCount">0</span>개</strong> 등록됨 —
        <a href="https://hwik.kr" target="_blank" style="color:#d97706;font-weight:600">hwik.kr에서 매물 추가 →</a>
      </div>
    </div>

    <div class="card" id="history-card" style="display:none">
      <div class="card-title">작업 히스토리</div>
      <ul class="history-list" id="history-list"></ul>
    </div>

  </div>

  <!-- ── 오른쪽: 로그 + 결과 ── -->
  <div class="right-panel">

    <!-- 터미널 로그 -->
    <div class="terminal" id="terminal-wrap">
      <div class="terminal-header">
        <div class="terminal-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="terminal-title">pipeline log</span>
        <span id="status-badge" style="margin-left:auto"></span>
      </div>
      <div class="log-body" id="log-body">
        <span class="log-placeholder">단지명을 입력하고 원고 생성을 시작하세요</span>
      </div>
    </div>

    <!-- 완료 결과 -->
    <div class="card result-panel" id="result-panel">
      <div class="card-title">생성 완료</div>

      <div id="image-grid-wrap" class="image-grid" style="display:none"></div>

      <div style="font-size:13px;font-weight:600;color:var(--muted);margin-bottom:8px;" id="file-list-title"></div>
      <ul class="file-list" id="file-list"></ul>

      <a class="btn-zip" id="btn-zip" href="#" download>
        ⬇ 전체 ZIP 다운로드
      </a>
    </div>

  </div>
</div>

<!-- 라이트박스 -->
<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <span class="lightbox-close">✕</span>
  <img id="lightbox-img" src="">
</div>

<script>
let currentJobId = null;
let currentEs    = null;
let jobHistory   = [];

// ── 유저 상태 초기화 ────────────────────────────────
async function initUserStatus() {
  try {
    const res  = await fetch('/user-status');
    if (res.status === 401) { location.href = '/'; return; }
    const data = await res.json();

    // 헤더 이름 표시
    const nameEl = document.getElementById('navUserName');
    if (nameEl) nameEl.textContent = data.user_name + ' 님';

    // 매물 부족 배너 + 버튼 잠금
    const banner   = document.getElementById('cardGateBanner');
    const btnGen   = document.getElementById('btn-gen');
    const countEl  = document.getElementById('currentCardCount');
    const minEl    = document.getElementById('minCardsNum');
    if (countEl) countEl.textContent = data.card_count;
    if (minEl)   minEl.textContent   = data.min_cards;

    // TODO: 매물 수 게이팅 — 테스트 완료 후 아래 주석 해제
    // if (!data.can_generate) {
    //   if (banner) banner.style.display = 'block';
    //   if (btnGen) { btnGen.disabled = true;
    //     btnGen.title = '매물 ' + data.min_cards + '개 이상 등록 후 사용 가능'; }
    // } else {
      if (banner) banner.style.display = 'none';
      if (btnGen) btnGen.disabled = false;
    // }

  } catch(e) {
    console.warn('유저 상태 조회 실패:', e);
  }
}

document.addEventListener('DOMContentLoaded', initUserStatus);

function formatSize(bytes) {
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1048576) return (bytes/1024).toFixed(0) + 'KB';
  return (bytes/1048576).toFixed(1) + 'MB';
}

function colorLine(text) {
  if (/✅|완료|성공|found/.test(text)) return 'ok';
  if (/⚠️|warn|주의/.test(text)) return 'warn';
  if (/❌|오류|실패|error/i.test(text)) return 'err';
  if (/={3,}|#{3,}|={3,}/.test(text)) return 'head';
  if (/^\s*$/.test(text)) return 'muted';
  return '';
}

function appendLog(text) {
  const lb = document.getElementById('log-body');
  // 처음 placeholder 제거
  const ph = lb.querySelector('.log-placeholder');
  if (ph) ph.remove();

  const span = document.createElement('span');
  span.className = 'log-line ' + colorLine(text);
  span.textContent = text;
  lb.appendChild(span);
  lb.appendChild(document.createElement('br'));
  lb.scrollTop = lb.scrollHeight;
}

function setStatus(type) {
  const badge = document.getElementById('status-badge');
  const map = {
    running: ['⏳ 실행 중', 'badge-running'],
    done:    ['✅ 완료',    'badge-done'],
    error:   ['❌ 오류',    'badge-error'],
  };
  const [label, cls] = map[type] || ['', ''];
  badge.innerHTML = `<span class="status-badge ${cls}">${label}</span>`;
}

// 사진 처리
function onPhotoChange(input) {
  const files = Array.from(input.files);
  const label = document.getElementById('photo-label-text');
  const preview = document.getElementById('photo-preview');
  preview.innerHTML = '';
  if (files.length === 0) {
    label.textContent = '사진 선택 (여러 장 가능)';
    return;
  }
  label.textContent = `📷 ${files.length}장 선택됨`;
  files.forEach(f => {
    const url = URL.createObjectURL(f);
    const img = document.createElement('img');
    img.src = url;
    img.style.cssText = 'width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid #ddd;';
    preview.appendChild(img);
  });
}

async function generate() {
  const aptRaw = document.getElementById('apt-input').value.trim();
  if (!aptRaw) {
    alert('단지명을 입력하세요');
    return;
  }

  // 줄바꿈 배치 처리
  const apts = aptRaw.split('\n').map(s => s.trim()).filter(Boolean);

  // UI 초기화
  document.getElementById('log-body').innerHTML =
    '<span class="log-placeholder">초기화 중...</span>';
  document.getElementById('result-panel').classList.remove('show');
  document.getElementById('btn-gen').disabled = true;
  document.getElementById('spinner').style.display = 'block';
  document.getElementById('btn-text').textContent = '생성 중...';
  if (currentEs) { currentEs.close(); currentEs = null; }

  const outputBase = document.getElementById('output-input').value.trim() || null;

  // 사진 업로드
  const photoInput = document.getElementById('photo-input');
  let photoJobId = null;
  if (photoInput.files.length > 0) {
    const fd = new FormData();
    Array.from(photoInput.files).forEach(f => fd.append('photos', f));
    try {
      const r = await fetch('/upload_photos', {method:'POST', body:fd});
      const j = await r.json();
      photoJobId = j.photo_job_id || null;
      appendLog(`📷 사진 ${photoInput.files.length}장 업로드 완료`);
    } catch(e) {
      appendLog(`⚠️ 사진 업로드 실패: ${e}`);
    }
  }

  // 배치: 순차 처리
  for (let i = 0; i < apts.length; i++) {
    const apt = apts[i];
    if (apts.length > 1) {
      appendLog(`\n${'#'.repeat(40)}`);
      appendLog(`# [${i+1}/${apts.length}] ${apt}`);
      appendLog('#'.repeat(40));
    }
    await runOne(apt, outputBase, photoJobId);
  }

  // 버튼 복구
  document.getElementById('btn-gen').disabled = false;
  document.getElementById('spinner').style.display = 'none';
  document.getElementById('btn-text').textContent = '📄 원고 생성 시작';
}

function runOne(aptName, outputBase, photoJobId) {
  return new Promise(async (resolve) => {
    const payload = { apt_name: aptName, output_base: outputBase, photo_job_id: photoJobId || null };
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const { job_id, error } = await res.json();
    if (error) { appendLog('❌ ' + error); resolve(); return; }

    currentJobId = job_id;
    setStatus('running');

    // 히스토리 추가
    addHistory(job_id, aptName, 'running');

    // SSE 스트림 연결
    const es = new EventSource(`/stream/${job_id}`);
    currentEs = es;

    es.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);

      if (msg.type === 'log') {
        appendLog(msg.text);

      } else if (msg.type === 'done') {
        setStatus('done');
        updateHistory(job_id, 'done');
        appendLog('\n✅ 원고 생성 완료!');
        await loadFiles(job_id);
        es.close();
        resolve();

      } else if (msg.type === 'error') {
        setStatus('error');
        updateHistory(job_id, 'error');
        appendLog('❌ 오류: ' + msg.text);
        es.close();
        resolve();

      } else if (msg.type === 'end') {
        es.close();
        resolve();
      }
    };

    es.onerror = () => { es.close(); resolve(); };
  });
}

async function loadFiles(jobId) {
  const res  = await fetch(`/files/${jobId}`);
  const files = await res.json();
  if (!files.length) return;

  document.getElementById('result-panel').classList.add('show');

  // 이미지 그리드
  const imgs = files.filter(f => f.type === 'image');
  const imgGrid = document.getElementById('image-grid-wrap');
  if (imgs.length) {
    imgGrid.style.display = 'grid';
    imgGrid.innerHTML = imgs.map(f => `
      <div>
        <div class="image-thumb" onclick="openLightbox('${f.url}')">
          <img src="${f.url}" alt="${f.name}" loading="lazy">
        </div>
        <div class="image-label">${f.name}</div>
      </div>
    `).join('');
  } else {
    imgGrid.style.display = 'none';
  }

  // 문서 목록
  const docs = files.filter(f => f.type === 'doc');
  document.getElementById('file-list-title').textContent =
    `📄 문서 ${docs.length}개`;
  document.getElementById('file-list').innerHTML = docs.map(f => `
    <li class="file-item">
      <span class="file-icon">📝</span>
      <span class="file-name" title="${f.name}">${f.name}</span>
      <span class="file-size">${formatSize(f.size)}</span>
      <a class="btn-dl" href="${f.url}" download="${f.name}">다운</a>
    </li>
  `).join('');

  // ZIP 버튼
  document.getElementById('btn-zip').href = `/download_zip/${jobId}`;
}

// 히스토리
function addHistory(jobId, aptName, status) {
  jobHistory.unshift({ jobId, aptName, status });
  renderHistory();
}

function updateHistory(jobId, status) {
  const job = jobHistory.find(j => j.jobId === jobId);
  if (job) { job.status = status; renderHistory(); }
}

function renderHistory() {
  const card = document.getElementById('history-card');
  const list = document.getElementById('history-list');
  if (!jobHistory.length) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  list.innerHTML = jobHistory.map(j => `
    <li class="history-item" onclick="switchJob('${j.jobId}')">
      <span class="history-dot dot-${j.status === 'running' ? 'run' : j.status}"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${j.aptName}</span>
    </li>
  `).join('');
}

async function switchJob(jobId) {
  currentJobId = jobId;
  // 히스토리 클릭 시 파일만 다시 로드
  document.getElementById('log-body').innerHTML =
    '<span class="log-placeholder">이전 작업 결과를 불러오는 중...</span>';
  await loadFiles(jobId);
}

// 라이트박스
function openLightbox(url) {
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox').classList.add('show');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('show');
}

// ── 자동완성 ────────────────────────────────────────────
let acTimer     = null;
let acResults   = [];
let acIndex     = -1;
let selectedFromAc = false;  // 드롭다운에서 선택했으면 바로 생성 가능

function onAptInput(val) {
  selectedFromAc = false;
  clearTimeout(acTimer);
  const q = val.trim();
  if (q.length < 1) { hideAc(); return; }
  // 줄바꿈 배치 모드면 자동완성 숨김
  if (q.includes('\n')) { hideAc(); return; }
  acTimer = setTimeout(() => fetchAc(q), 200);
}

async function fetchAc(q) {
  try {
    const res  = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const rows = await res.json();
    acResults = rows;
    acIndex   = -1;
    renderAc(q, rows);
  } catch(e) { hideAc(); }
}

function renderAc(q, rows) {
  const box  = document.getElementById('autocomplete-box');
  const list = document.getElementById('autocomplete-list');

  if (!rows.length) {
    list.innerHTML = `<div class="ac-empty">검색 결과 없음 — 그대로 입력해도 됩니다</div>`;
    box.style.display = 'block';
    return;
  }

  // 검색어 하이라이트
  function hl(name) {
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`, 'gi');
    return name.replace(re, '<em>$1</em>');
  }

  list.innerHTML = rows.map((r, i) => {
    const isOffi = r.property_type === 'offi';
    const badge  = isOffi
      ? '<span class="ac-badge badge-offi">오피스텔</span>'
      : '<span class="ac-badge badge-apt">아파트</span>';
    const addr   = r.doro_juso
      ? r.doro_juso.replace(/^서울특별시\s*/, '').replace(/^경기도\s*/, '')
      : (r.sgg || '');
    return `
      <div class="ac-item" data-idx="${i}"
           onmousedown="selectAc(${i})"
           onmouseover="setAcIndex(${i})">
        ${badge}
        <span class="ac-name">${hl(r.kapt_name)}</span>
        <span class="ac-addr">${addr}</span>
      </div>`;
  }).join('');

  box.style.display = 'block';
}

function selectAc(idx) {
  const row = acResults[idx];
  if (!row) return;
  document.getElementById('apt-input').value = row.kapt_name;
  selectedFromAc = true;
  hideAc();
}

function setAcIndex(idx) {
  acIndex = idx;
  document.querySelectorAll('.ac-item').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
}

function hideAc() {
  document.getElementById('autocomplete-box').style.display = 'none';
  acResults = [];
  acIndex   = -1;
}

function onAptKeydown(e) {
  const box = document.getElementById('autocomplete-box');
  if (box.style.display === 'none') {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); generate(); }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    acIndex = Math.min(acIndex + 1, acResults.length - 1);
    setAcIndex(acIndex);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    acIndex = Math.max(acIndex - 1, 0);
    setAcIndex(acIndex);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (acIndex >= 0) {
      selectAc(acIndex);
    } else {
      hideAc();
      generate();
    }
  } else if (e.key === 'Escape') {
    hideAc();
  }
}

// 드롭다운 밖 클릭 시 닫기
document.addEventListener('click', (e) => {
  if (!e.target.closest('#apt-input') && !e.target.closest('#autocomplete-box')) {
    hideAc();
  }
});

</script>
</body>
</html>
"""


# ========================================================
# 로그인 페이지 HTML
# ========================================================
LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>휙 로그인</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Noto Sans KR',sans-serif;background:#f4f5f7;min-height:100vh;display:flex;flex-direction:column;}
header{background:#0F6E56;padding:0 32px;height:56px;display:flex;align-items:center;}
.logo{font-size:22px;font-weight:700;color:#fff;}
.logo-sub{font-size:13px;color:rgba(255,255,255,.65);margin-left:8px;}
.center{flex:1;display:flex;align-items:center;justify-content:center;}
.card{background:#fff;border-radius:16px;border:1px solid #e2e4e8;box-shadow:0 4px 24px rgba(0,0,0,.08);padding:48px 40px;width:100%;max-width:420px;text-align:center;}
.icon{font-size:52px;margin-bottom:16px;}
h1{font-size:22px;font-weight:700;color:#1a1d23;margin-bottom:8px;}
.desc{font-size:14px;color:#6b7280;line-height:1.7;margin-bottom:32px;}
.btn-kakao{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:14px;background:#FEE500;border:none;border-radius:10px;font-family:'Noto Sans KR',sans-serif;font-size:15px;font-weight:700;color:#191919;cursor:pointer;transition:background .2s,transform .1s;}
.btn-kakao:hover{background:#F0D900;}
.btn-kakao:active{transform:scale(.98);}
.kakao-icon{width:22px;height:22px;}
.notice{margin-top:20px;font-size:12px;color:#9ca3af;line-height:1.6;}
</style>
</head>
<body>
<header>
  <span class="logo">휙</span>
  <span class="logo-sub">블로그 원고 자동 생성</span>
</header>
<div class="center">
  <div class="card">
    <div class="icon">📝</div>
    <h1>휙 원고 생성 도구</h1>
    <p class="desc">
      휙(Hwik) 회원만 사용할 수 있습니다.<br>
      카카오 계정으로 로그인해주세요.
    </p>
    <button class="btn-kakao" onclick="location.href='/kakao-login'">
      <svg class="kakao-icon" viewBox="0 0 24 24" fill="#191919">
        <path d="M12 3C6.477 3 2 6.477 2 10.8c0 2.755 1.676 5.17 4.2 6.6L5.1 21l5.1-2.1c.6.1 1.2.1 1.8.1 5.523 0 10-3.477 10-7.8S17.523 3 12 3z"/>
      </svg>
      카카오로 로그인
    </button>
    <p class="notice">휙 미가입자는 hwik.kr에서 먼저 가입해주세요.</p>
  </div>
</div>
</body>
</html>"""


# ========================================================
# 인증 헬퍼 함수
# ========================================================
def login_required(f):
    """로그인 필요 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            accept = request.headers.get("Accept", "")
            if "text/event-stream" in accept:
                def _err():
                    yield 'data: {"type":"error","text":"로그인이 필요합니다"}\n\n'
                return Response(_err(), mimetype="text/event-stream")
            if request.is_json or request.method == "POST":
                return jsonify({"error": "로그인이 필요합니다"}), 401
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def _build_agent_info(profile: dict) -> dict:
    """Supabase profiles → naver_blog_post AGENT_INFO 형식으로 변환"""
    return {
        "name":          profile.get("agent_name") or "",
        "office":        profile.get("business_name") or "",
        "phone":         profile.get("phone") or "",
        "address":       profile.get("address") or "",
        "naver_map_url": profile.get("naver_map_url") or "",
        "lat":           float(profile.get("office_lat") or 0),
        "lon":           float(profile.get("office_lon") or 0),
    }


def _get_card_count(user_id: str) -> int:
    """Supabase에서 해당 유저 매물(카드) 수 조회"""
    try:
        res = _req.get(
            f"{SB_URL}/rest/v1/cards",
            headers={**_sb_hdr(), "Prefer": "count=exact", "Range": "0-0"},
            params={"user_id": f"eq.{user_id}", "select": "id"},
            timeout=5,
        )
        cr = res.headers.get("Content-Range", "")
        # Content-Range: 0-0/42 → 42
        if "/" in cr:
            return int(cr.split("/")[1])
    except Exception:
        pass
    return 0


def _get_profile(user_id: str) -> dict:
    """Supabase profiles 테이블에서 중개사 정보 조회"""
    try:
        # 전체 컬럼 조회 (컬럼명 파악용)
        res = _req.get(
            f"{SB_URL}/rest/v1/profiles",
            headers=_sb_hdr(),
            params={
                "id": f"eq.{user_id}",
                "select": "*",
                "limit": "1",
            },
            timeout=5,
        )
        key = _sb_key()
        print(f'  [_get_profile] SB_KEY={key[:8] if key else "빈값"}, status={res.status_code}')
        if res.status_code != 200:
            print(f"  [_get_profile] error body: {res.text[:200]}")
            return {}
        rows = res.json()
        print(f"  [_get_profile] rows={len(rows)}, keys={list(rows[0].keys()) if rows else []}")
        return rows[0] if rows else {}
    except Exception as e:
        print(f"  [_get_profile] exception: {e}")
        return {}


# ========================================================
# 라우트
# ========================================================
@app.route("/")
def index():
    if not session.get("user_id"):
        return LOGIN_HTML
    return HTML


@app.route("/user-status")
@login_required
def user_status():
    """현재 로그인 유저 상태 — 매물 수 실시간 조회"""
    user_id    = session["user_id"]
    card_count = _get_card_count(user_id)
    return jsonify({
        "user_name":   session.get("user_name", ""),
        "card_count":  card_count,
        "min_cards":   MIN_CARDS,
        "can_generate": card_count >= MIN_CARDS,
    })


@app.route("/kakao-login")
def kakao_login():
    """Supabase OAuth — 카카오 로그인 시작 (Supabase가 PKCE 내부 관리)"""
    params = urllib.parse.urlencode({
        "provider":    "kakao",
        "redirect_to": KAKAO_REDIRECT,
    })
    url = f"{SB_AUTH_URL}/auth/v1/authorize?{params}"
    print(f"  [kakao_login] redirect → {url}")
    return redirect(url)


@app.route("/kakao-callback")
def kakao_callback():
    """Supabase OAuth 콜백 — 토큰은 URL fragment(#)에 담겨옴"""
    error = request.args.get("error")
    if error:
        desc = request.args.get("error_description", "")
        print(f"  [callback] error={error}, desc={desc}")
        return f"<p>로그인 오류: {error}<br>{desc}</p><a href='/'>다시 시도</a>"

    # Supabase는 access_token을 URL fragment(#access_token=...)로 전달
    # fragment는 서버에서 못 읽으므로 JS로 처리
    return """<!DOCTYPE html>
<html><head><meta charset=utf-8>
<style>body{font-family:sans-serif;text-align:center;margin-top:80px;color:#555;}</style>
</head><body>
<p>🔐 로그인 처리 중...</p>
<script>
const hash = location.hash.substring(1);
const params = new URLSearchParams(hash);
const access_token  = params.get('access_token');
const refresh_token = params.get('refresh_token');
const error         = params.get('error');
const error_desc    = params.get('error_description');

if (error) {
  document.body.innerHTML = '<p>❌ 오류: ' + error_desc + '</p><a href=\'/\'>다시 시도</a>';
} else if (access_token) {
  fetch('/kakao-token', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({access_token, refresh_token})
  })
  .then(r => r.json())
  .then(d => { location.href = d.ok ? '/' : '/?login_error=1'; })
  .catch(() => { location.href = '/'; });
} else {
  // fragment 없으면 code 방식 시도
  const code = new URLSearchParams(location.search).get('code');
  if (code) {
    fetch('/kakao-token', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code})
    })
    .then(r => r.json())
    .then(d => { location.href = d.ok ? '/' : '/?login_error=1'; })
    .catch(() => { location.href = '/'; });
  } else {
    location.href = '/';
  }
}
</script>
</body></html>"""


@app.route("/kakao-token", methods=["POST"])
def kakao_token():
    """Fragment 토큰 또는 code → 유저 확인 → 세션 저장"""
    body         = request.get_json() or {}
    access_token = body.get("access_token")
    code         = body.get("code")

    # ── access_token 직접 받은 경우 (fragment flow) ──
    if access_token:
        # JWT payload 디코딩으로 user_id 추출 (API 호출 없이)
        try:
            import base64 as _b64
            payload_b64 = access_token.split(".")[1]
            # base64 패딩 보정
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(_b64.urlsafe_b64decode(payload_b64).decode())
            user_id = payload.get("sub", "")
            print(f"  [kakao-token/fragment] JWT decoded, user_id={user_id[:8]}...")
        except Exception as e:
            print(f"  [kakao-token/fragment] JWT decode 실패: {e}")
            return jsonify({"error": "토큰 파싱 실패"}), 401

        if not user_id:
            return jsonify({"error": "user_id 없음"}), 401

        # 프로필 조회 (service key로 직접)
        profile = _get_profile(user_id)
        print(f"  [kakao-token/fragment] profile={'있음' if profile else '없음'}")

        # 프로필 없어도 Supabase 인증 유저면 일단 허용 (개발/테스트용)
        # TODO: 정식 배포 시 아래 주석 해제 → 휙 가입자만 허용
        # if not profile:
        #     return jsonify({"error": "휙 미가입 계정"}), 401

        agent_name = profile.get("agent_name") or profile.get("name") or "중개사"
        session.permanent = True
        session["user_id"]      = user_id
        session["user_name"]    = agent_name
        session["access_token"] = access_token
        session["profile"]      = profile or {}
        print(f"  ✅ 로그인 성공: {agent_name} ({user_id[:8]}...)")
        return jsonify({"ok": True})

    # ── code 받은 경우 (PKCE code flow) ──
    if code:
        try:
            res = _req.post(
                f"{SB_AUTH_URL}/auth/v1/token?grant_type=pkce",
                headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                json={"auth_code": code, "code_verifier": ""},
                timeout=10,
            )
            print(f"  [kakao-token/code] status={res.status_code}, body={res.text[:200]}")
            if res.status_code != 200:
                return jsonify({"error": f"토큰 교환 실패({res.status_code})"}), 401
            data = res.json()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        _finalize_login(data)
        return jsonify({"ok": True})

    return jsonify({"error": "토큰/코드 없음"}), 400


def _finalize_login(data: dict):
    """액세스 토큰 + 유저 정보 → 프로필 확인 → 세션 저장"""
    user         = data.get("user") or {}
    user_id      = user.get("id", "")
    access_token = data.get("access_token", "")

    if not user_id:
        return "<p>유저 정보를 가져올 수 없습니다.</p><a href='/'>다시 시도</a>"

    # 프로필 확인 — 휙 가입자만 허용
    profile = _get_profile(user_id)
    if not profile:
        return (
            "<p style='font-family:sans-serif;text-align:center;margin-top:60px'>'"
            "<strong>휙(Hwik) 미가입 계정입니다.</strong><br>'"
            "<a href='https://hwik.kr' target='_blank'>hwik.kr</a>에서 먼저 가입해주세요.'"
            "</p><p style='text-align:center;margin-top:16px'><a href='/'>돌아가기</a></p>"
        )

    # 세션 저장
    session.permanent = True
    session["user_id"]      = user_id
    session["user_name"]    = profile.get("agent_name") or profile.get("name") or user.get("email", "중개사")
    session["access_token"] = access_token
    session["profile"]      = profile
    print(f"✅ 로그인 성공: {session['user_name']} ({user_id[:8]}...)")

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/search")
@login_required
def search_apt():
    """
    Supabase apartments DB 실시간 검색
    ?q=검색어 → [{kapt_name, doro_juso, property_type, sido, sgg}, ...]
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 1:
        return jsonify([])
    try:
        # ilike 검색 (대소문자 무시)
        res = _req.get(
            f"{SB_URL}/rest/v1/apartments",
            headers=SB_HDR,
            params={
                "select": "kapt_name,doro_juso,property_type,sido,sgg,slug",
                "kapt_name": f"ilike.*{q}*",
                "order": "trade_count.desc.nullslast",
                "limit": "10",
            },
            timeout=5,
        )
        rows = res.json() if res.status_code == 200 else []
        if not isinstance(rows, list):
            rows = []
        return jsonify(rows)
    except Exception as e:
        return jsonify([])


photo_jobs: dict = {}  # photo_job_id → [파일 경로 목록]

@app.route("/upload_photos", methods=["POST"])
@login_required
def upload_photos():
    files = request.files.getlist("photos")
    if not files:
        return jsonify({"error": "사진 없음"}), 400

    photo_job_id = str(uuid.uuid4())[:8]
    save_dir = os.path.join(DEFAULT_OUTPUT, "_photos_" + photo_job_id)
    os.makedirs(save_dir, exist_ok=True)

    paths = []
    for f in files:
        fname = f.filename or f"photo_{len(paths)}.jpg"
        fpath = os.path.join(save_dir, fname)
        f.save(fpath)
        paths.append(fpath)

    photo_jobs[photo_job_id] = paths
    print(f"📷 사진 {len(paths)}장 저장: {save_dir}")
    return jsonify({"photo_job_id": photo_job_id, "count": len(paths)})


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    data     = request.get_json() or {}
    apt_name = (data.get("apt_name") or "").strip()
    if not apt_name:
        return jsonify({"error": "단지명을 입력하세요"}), 400

    output_base  = (data.get("output_base") or "").strip() or DEFAULT_OUTPUT
    photo_job_id = data.get("photo_job_id") or None
    photo_paths  = photo_jobs.get(photo_job_id, []) if photo_job_id else []

    job_id = str(uuid.uuid4())[:8]
    job    = Job(job_id, apt_name, output_base)
    jobs[job_id] = job

    # 스레드 시작 전에 session에서 미리 캡처
    _captured_profile = dict(session.get("profile") or {})

    def _run():
        orig_stdout = sys.stdout
        cap = _LogCapture(job, orig_stdout)
        sys.stdout = cap
        try:
            # ── AGENT_INFO 자동 주입 (naver_blog_post 모듈에 주입) ──
            _profile = _captured_profile
            if _profile:
                try:
                    import importlib.util as _ilu
                    _spec_nbp = _ilu.spec_from_file_location(
                        "naver_blog_post", os.path.join(SCRIPT_DIR, "naver_blog_post.py")
                    )
                    _nbp_mod = _ilu.module_from_spec(_spec_nbp)
                    _spec_nbp.loader.exec_module(_nbp_mod)
                    _nbp_mod.AGENT_INFO = _build_agent_info(_profile)
                    print(f"  ✅ AGENT_INFO 주입: {_nbp_mod.AGENT_INFO['name']} / {_nbp_mod.AGENT_INFO['office']}")
                except Exception as _e:
                    print(f"  ⚠️ AGENT_INFO 주입 실패: {_e}")

            result = run_pipeline(apt_name, output_base=output_base, auto_mode=True,
                                  photo_paths=photo_paths if photo_paths else None)
            job.output_dir = result
            job.status     = "done"
            job.log_queue.put({"type": "done", "output_dir": str(result or "")})
        except Exception as e:
            import traceback
            job.status    = "error"
            job.error_msg = str(e)
            job.log_queue.put({"type": "error", "text": str(e)})
            job.log_queue.put({"type": "log",   "text": traceback.format_exc()})
        finally:
            sys.stdout = orig_stdout
            job.log_queue.put(None)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
@login_required
def stream(job_id):
    job = jobs.get(job_id)
    if not job:
        return "not found", 404

    def _sse():
        while True:
            try:
                msg = job.log_queue.get(timeout=60)
            except queue.Empty:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"
                continue
            if msg is None:
                yield f"data: {json.dumps({'type':'end'})}\n\n"
                break
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return Response(
        _sse(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


@app.route("/files/<job_id>")
@login_required
def files(job_id):
    job = jobs.get(job_id)
    if not job or not job.output_dir:
        return jsonify([])
    output_dir = str(job.output_dir)
    if not os.path.exists(output_dir):
        return jsonify([])

    items = []
    for f in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, f)
        if not os.path.isfile(fpath):
            continue
        ext  = f.rsplit(".", 1)[-1].lower()
        ftype = "image" if ext in ("jpg", "jpeg", "png", "gif") else "doc"
        items.append({
            "name": f,
            "size": os.path.getsize(fpath),
            "type": ftype,
            "url":  f"/download/{job_id}/{f}",
        })
    return jsonify(items)


@app.route("/download/<job_id>/<path:filename>")
@login_required
def download(job_id, filename):
    job = jobs.get(job_id)
    if not job or not job.output_dir:
        return "not found", 404
    fpath = os.path.join(str(job.output_dir), filename)
    if not os.path.isfile(fpath):
        return "not found", 404
    return send_file(fpath, as_attachment=True)


@app.route("/download_zip/<job_id>")
@login_required
def download_zip(job_id):
    job = jobs.get(job_id)
    if not job or not job.output_dir:
        return "not found", 404
    output_dir = str(job.output_dir)
    if not os.path.exists(output_dir):
        return "not found", 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, f)
            if os.path.isfile(fpath):
                zf.write(fpath, f)
    buf.seek(0)

    apt_clean = job.apt_name.replace(" ", "")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{apt_clean}_원고.zip",
    )


@app.route("/vision_test")
def vision_test():
    return """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vision 사진 테스트</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'맑은 고딕',sans-serif;background:#f5f5f5;padding:20px;}
.wrap{max-width:860px;margin:0 auto;}
h1{font-size:20px;font-weight:600;color:#1a1a1a;margin-bottom:20px;}
.card{background:#fff;border-radius:12px;border:1px solid #e5e7eb;padding:24px;margin-bottom:16px;}
.label{font-size:13px;font-weight:500;color:#555;margin-bottom:8px;}
.upload-area{border:2px dashed #ccc;border-radius:10px;padding:20px;text-align:center;cursor:pointer;color:#888;font-size:14px;transition:border-color .2s;}
.upload-area:hover{border-color:#1D9E75;color:#1D9E75;}
.preview-grid{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
.preview-grid img{width:80px;height:80px;object-fit:cover;border-radius:6px;border:1px solid #ddd;}
.btn{background:#1D9E75;color:#fff;border:none;border-radius:8px;padding:12px 28px;font-size:15px;font-weight:600;cursor:pointer;width:100%;}
.btn:disabled{opacity:.5;cursor:not-allowed;}
.result-wrap{margin-top:16px;}
.result-item{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;display:flex;gap:16px;align-items:flex-start;}
.result-img{width:120px;height:90px;object-fit:cover;border-radius:6px;flex-shrink:0;}
.result-body{flex:1;}
.space-badge{display:inline-block;background:#E1F5EE;color:#0F6E56;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;margin-bottom:8px;}
.caption{font-size:14px;color:#333;line-height:1.7;}
.log{font-size:13px;color:#666;padding:12px;background:#f1f5f9;border-radius:8px;margin-top:8px;}
</style></head>
<body>
<div class="wrap">
<h1>📷 Vision 사진 원고 테스트</h1>

<div class="card">
  <div class="label">매물 사진 선택</div>
  <label class="upload-area" id="upload-label">
    사진을 선택하세요 (여러 장 가능)
    <input type="file" id="photo-input" multiple accept="image/*" style="display:none" onchange="onSelect(this)">
  </label>
  <div class="preview-grid" id="preview"></div>
</div>

<div class="card">
  <div class="label">단지명 (테스트용)</div>
  <input type="text" id="apt-name" value="테스트단지" style="width:100%;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px;">
</div>

<button class="btn" id="btn" onclick="analyze()">사진 분석 시작</button>

<div id="log" class="log" style="display:none;margin-top:12px;"></div>
<div class="result-wrap" id="results"></div>
</div>

<script>
let files = [];

function onSelect(input) {
  files = Array.from(input.files);
  const prev = document.getElementById('preview');
  const label = document.getElementById('upload-label');
  prev.innerHTML = '';
  label.childNodes[0].textContent = `${files.length}장 선택됨 — `;
  files.forEach(f => {
    const img = document.createElement('img');
    img.src = URL.createObjectURL(f);
    prev.appendChild(img);
  });
}

function log(msg) {
  const el = document.getElementById('log');
  el.style.display = 'block';
  el.innerHTML += msg + '<br>';
}

async function analyze() {
  if (!files.length) { alert('사진을 먼저 선택하세요'); return; }
  const btn = document.getElementById('btn');
  btn.disabled = true; btn.textContent = '분석 중...';
  document.getElementById('results').innerHTML = '';
  document.getElementById('log').innerHTML = '';
  document.getElementById('log').style.display = 'block';

  const aptName = document.getElementById('apt-name').value.trim() || '테스트단지';
  log(`📷 ${files.length}장 분석 시작 (단지명: ${aptName})`);

  const fd = new FormData();
  files.forEach(f => fd.append('photos', f));
  fd.append('apt_name', aptName);

  try {
    const res = await fetch('/vision_analyze', {method:'POST', body:fd});
    const data = await res.json();
    if (data.error) { log('❌ 오류: ' + data.error); return; }

    log(`✅ 분석 완료 (${data.results.length}장)`);
    const wrap = document.getElementById('results');
    data.results.forEach((r, i) => {
      const div = document.createElement('div');
      div.className = 'result-item';
      div.innerHTML = `
        <img class="result-img" src="${r.preview_url}">
        <div class="result-body">
          <span class="space-badge">${r.space}</span>
          <div class="caption">${r.caption || '(원고 없음)'}</div>
        </div>`;
      wrap.appendChild(div);
    });
  } catch(e) {
    log('❌ 오류: ' + e);
  } finally {
    btn.disabled = false; btn.textContent = '사진 분석 시작';
  }
}
</script>
</body></html>"""


@app.route("/vision_analyze", methods=["POST"])
@login_required
def vision_analyze():
    files = request.files.getlist("photos")
    apt_name = request.form.get("apt_name", "테스트단지").strip()
    if not files:
        return jsonify({"error": "사진 없음"}), 400

    # 임시 저장
    save_dir = os.path.join(DEFAULT_OUTPUT, "_vision_test")
    os.makedirs(save_dir, exist_ok=True)
    paths = []
    for f in files:
        fname = f.filename or f"photo_{len(paths)}.jpg"
        fpath = os.path.join(save_dir, fname)
        f.save(fpath)
        paths.append(fpath)

    # Vision 분석
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "naver_blog_post",
            os.path.join(SCRIPT_DIR, "naver_blog_post.py")
        )
        _nbp = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_nbp)
        results_raw = _nbp.analyze_photos_with_vision(paths, apt_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # 이미지 base64 → 브라우저 미리보기용
    results = []
    for r in results_raw:
        import base64
        try:
            with open(r["path"], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(r["path"])[1].lower()
            mime = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png"
            preview = f"data:{mime};base64,{b64}"
        except:
            preview = ""
        results.append({"space": r["space"], "caption": r["caption"], "preview_url": preview})

    return jsonify({"results": results})


# ========================================================
# 실행
# ========================================================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀  블로그 원고 생성 서버 시작")
    print(f"    접속: http://localhost:5050")
    print(f"    hwik_engine.py 경로: {os.path.join(SCRIPT_DIR, 'hwik_engine.py')}")
    print(f"    기본 출력 폴더: {DEFAULT_OUTPUT}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)