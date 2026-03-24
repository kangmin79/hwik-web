# -*- coding: utf-8 -*-
"""
기존 매물 전체에 임베딩 생성
- embedding이 없는 카드만 대상
- OpenAI text-embedding-3-small 사용
- 배치 처리 (50개씩)
"""
import os, sys, json, time, requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = "https://api.hwik.kr"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not SUPABASE_SERVICE_KEY:
    print("SUPABASE_SERVICE_ROLE_KEY missing"); sys.exit(1)
if not OPENAI_API_KEY:
    print("OPENAI_API_KEY missing - .env에 추가해주세요"); sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def get_embedding(texts):
    """OpenAI 임베딩 배치 생성"""
    resp = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": "text-embedding-3-small", "input": texts}
    )
    if resp.status_code != 200:
        print(f"  OpenAI 에러: {resp.status_code} {resp.text[:200]}")
        return None
    data = resp.json()
    return [item["embedding"] for item in data["data"]]

def card_to_text(card):
    """매물 정보를 임베딩용 텍스트로 변환"""
    p = card.get("property", {}) or {}
    parts = [
        p.get("type", ""),
        p.get("price", ""),
        p.get("location", ""),
        p.get("complex", ""),
        p.get("area", ""),
        p.get("floor", ""),
        p.get("room", ""),
        p.get("category", ""),
        " ".join(p.get("features", []) or []),
        p.get("moveIn", ""),
        card.get("agent_comment", ""),
    ]
    text = " ".join(filter(None, parts)).strip()
    return text if text else "매물"

def main():
    print("=" * 60)
    print("EMBED ALL CARDS")
    print("=" * 60)

    # 1. 임베딩 없는 카드 조회
    print("\n임베딩 없는 카드 조회 중...")
    all_cards = []
    offset = 0
    batch = 1000

    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/cards?select=id,property,agent_comment,embedding&embedding=is.null&offset={offset}&limit={batch}",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
        )
        if resp.status_code != 200:
            print(f"  조회 에러: {resp.status_code}")
            break
        data = resp.json()
        if not data:
            break
        all_cards.extend(data)
        offset += len(data)
        print(f"  로드: {len(all_cards)}개")
        if len(data) < batch:
            break

    print(f"\n총 {len(all_cards)}개 카드에 임베딩 생성 필요")

    if not all_cards:
        print("모든 카드에 이미 임베딩이 있어요!")
        return

    # 2. 배치 임베딩 생성 + DB 업데이트
    batch_size = 50
    success = 0
    fail = 0

    for i in range(0, len(all_cards), batch_size):
        batch_cards = all_cards[i:i+batch_size]
        texts = [card_to_text(c) for c in batch_cards]

        # OpenAI 임베딩 생성
        embeddings = get_embedding(texts)
        if not embeddings:
            fail += len(batch_cards)
            time.sleep(1)
            continue

        # DB 업데이트 (개별)
        for j, card in enumerate(batch_cards):
            card_id = card["id"]
            text = texts[j]
            embedding = embeddings[j]

            resp = requests.patch(
                f"{SUPABASE_URL}/rest/v1/cards?id=eq.{card_id}",
                headers=HEADERS,
                json={
                    "embedding": embedding,
                    "search_text": text
                }
            )
            if resp.status_code in (200, 204):
                success += 1
            else:
                fail += 1

        print(f"  진행: {min(i+batch_size, len(all_cards))}/{len(all_cards)} (성공: {success}, 실패: {fail})")

        # Rate limit 방지
        time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"DONE! 성공: {success}, 실패: {fail}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
