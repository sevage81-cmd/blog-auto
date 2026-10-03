"""
AI 이미지 생성 스크립트. 두 가지 용도.

1) 분위기 컷 (기본) — 저작권 걱정 없는 실사 유사 이미지를 프롬프트로 생성.
   경기장 내부·관중석·조명 아래 피치 등 Commons에 없는 무드 컷.
   실존 인물 얼굴은 넣지 않는다(실루엣·군중·원경).

2) 선수 카드 (--card) — 득점자·주요 선수를 트레이딩 카드 형태로 생성.
   `guides/image-templates/player-card-ref.png` 스타일을 그대로 따르며,
   선수 얼굴·구단 최신 유니폼·성적 스탯·표정(호평/혹평)을 반영한다.
   팬/에디토리얼 목적의 그래픽이고, 표시하는 스탯은 research.md 기준 사실만
   넣는다. 표정은 경기력 반영이지 조롱이 아니다. 카드에는 "AI 생성" 표기를
   남긴다(image-make 에이전트 캡션 규칙).

백엔드:
- pollinations  — 분위기 컷 기본값. POLLINATIONS_API_KEY 있으면 gen.pollinations.ai
                  (기본 모델 zimage, POLLINATIONS_MODEL 로 변경), 실패/키 없음이면
                  키 없는 구 엔드포인트(Flux, 워터마크·저해상도)로 폴백.
- gemini        — GEMINI_API_KEY + 결제 크레딧 필요. 분위기 컷은 429/402 시
                  pollinations 폴백. **선수 카드는 gemini 전용**(Flux는 텍스트·
                  얼굴·레이아웃을 못 맞춤) — 키 없거나 크레딧 없으면 에러.

사용법:
    python gen_image.py "<영문 프롬프트>" <out.jpg> [--aspect 16:9] [--seed N]
    python gen_image.py --card <out.png> --player "브루누 페르난드스"
        --player-en "Bruno Fernandes" --club "맨체스터 유나이티드" --number 8
        --stat "1골 1도움" --sub "vs 에버턴 · 프리미어리그" --mood good

환경변수:
    GEMINI_API_KEY, GEMINI_IMAGE_MODEL(기본 gemini-3-pro-image),
    IMAGE_BACKEND(pollinations 로 고정 시 gemini 건너뜀 — 카드에는 무시)

성공: stdout 에 JSON 한 줄  {"path", "model", ...}
실패: stdout 에 {"error": "..."} 찍고 exit 1
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Windows 기본 stdout(cp949)은 —·ü 등을 못 써서 JSON 출력이 죽는다 → UTF-8 고정.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image").strip()
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BACKEND = os.environ.get("IMAGE_BACKEND", "").strip().lower()
PKEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()
PMODEL = os.environ.get("POLLINATIONS_MODEL", "zimage").strip()

CARD_REF = Path(__file__).resolve().parents[2] / "guides" / "image-templates" / "player-card-ref.png"

SAFETY_SUFFIX = (
    " Photorealistic editorial sports photography, natural stadium lighting, "
    "shallow depth of field, sharp focus, high detail, wide cinematic shot. "
    "Do NOT depict any real, identifiable person's face — crowds, silhouettes, "
    "distant or back views only. No club logos, no emblems, no kit sponsors, "
    "no text, no scoreboard graphics, no watermark."
)

MOOD_FACE = {
    "good": "bright, confident, proud — a genuine smile, chin up, energised",
    "bad": "subdued and disappointed — no smile, downcast or thousand-yard gaze, tired",
    "neutral": "calm and focused, neutral expression, no strong emotion",
}

ASPECT_SIZES = {
    "16:9": (1280, 720), "3:2": (1200, 800), "4:3": (1024, 768),
    "1:1": (1024, 1024), "9:16": (720, 1280), "2:3": (800, 1200), "3:4": (900, 1200),
}


def die(msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def dims_for(aspect: str) -> tuple[int, int]:
    if aspect in ASPECT_SIZES:
        return ASPECT_SIZES[aspect]
    try:
        w, h = (float(x) for x in aspect.split(":"))
        if w >= h:
            return 1280, max(256, round(1280 * h / w))
        return max(256, round(1280 * w / h)), 1280
    except Exception:  # noqa: BLE001
        return 1280, 720


def _gemini_call(parts: list) -> bytes:
    """parts(list of {"text":...} / {"inlineData":...}) 로 gemini 이미지 생성. 실패 시 die()."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in (402, 429):
            die(f"gemini {e.code} — 결제 크레딧 없음/쿼터 초과. AI Studio에서 크레딧 충전 필요: {detail[:160]}")
        die(f"gemini HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        die(f"gemini {type(e).__name__}: {e}")
    cands = data.get("candidates") or []
    ps = cands[0].get("content", {}).get("parts", []) if cands else []
    b64 = next((p["inlineData"]["data"] for p in ps
                if isinstance(p, dict) and p.get("inlineData", {}).get("data")), None)
    if not b64:
        die(f"gemini 응답에 이미지 없음: {json.dumps(data, ensure_ascii=False)[:400]}")
    return base64.b64decode(b64)


# ---------- 1) 분위기 컷 ----------

def gen_pollinations(full_prompt: str, out_path: str, aspect: str, seed: int | None) -> None:
    w, h = dims_for(aspect)
    q = urllib.parse.quote(full_prompt, safe="")
    seed_q = f"&seed={seed}" if seed is not None else ""
    # 1순위: 키 있는 gen.pollinations.ai (워터마크 없음, 모델 선택). 실패하면 키 없는 구 엔드포인트.
    attempts = []
    if PKEY:
        attempts.append((f"https://gen.pollinations.ai/image/{q}?width={w}&height={h}&model={PMODEL}{seed_q}",
                         {"Authorization": f"Bearer {PKEY}"}, PMODEL))
    attempts.append((f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&nologo=true&model=flux&enhance=true{seed_q}",
                     {}, "flux"))
    raw, used, err = b"", "", ""
    for url, hdrs, used in attempts:
        req = urllib.request.Request(url, headers={"User-Agent": "blog-pipeline/1", **hdrs})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        else:
            if len(raw) >= 1000 and (raw[:3] == b"\xff\xd8\xff" or b"PNG" in raw[:8]):
                break
            err = f"응답이 이미지가 아님 ({len(raw)} bytes)"
        raw = b""
        sys.stderr.write(f"[gen_image] pollinations/{used} 실패 ({err})\n")
    if not raw:
        die(f"pollinations {err}")
    with open(out_path, "wb") as f:
        f.write(raw)
    print(json.dumps({"path": out_path, "model": f"pollinations/{used}",
                      "prompt": full_prompt.split(". Aspect")[0]}, ensure_ascii=False))


def gen_gemini_mood(full_prompt: str, out_path: str) -> bool:
    """429/402면 False(폴백). 성공 시 저장 후 True."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in (402, 429):
            sys.stderr.write(f"[gen_image] gemini {e.code}, pollinations 로 폴백\n")
            return False
        die(f"gemini HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        die(f"gemini {type(e).__name__}: {e}")
    cands = data.get("candidates") or []
    ps = cands[0].get("content", {}).get("parts", []) if cands else []
    b64 = next((p["inlineData"]["data"] for p in ps
                if isinstance(p, dict) and p.get("inlineData", {}).get("data")), None)
    if not b64:
        die(f"gemini 응답에 이미지 없음: {json.dumps(data, ensure_ascii=False)[:400]}")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(json.dumps({"path": out_path, "model": MODEL,
                      "prompt": full_prompt.split(". Aspect")[0]}, ensure_ascii=False))
    return True


# ---------- 2) 선수 카드 ----------

def gen_card(fields: dict, out_path: str) -> None:
    if not KEY:
        die("선수 카드는 gemini 전용인데 GEMINI_API_KEY 가 없다 (secrets.env 확인).")
    if not CARD_REF.exists():
        die(f"카드 레퍼런스 이미지 없음: {CARD_REF}")

    face = MOOD_FACE.get(fields.get("mood", "neutral"), MOOD_FACE["neutral"])
    player = fields["player"]
    player_en = fields.get("player_en") or player
    club = fields.get("club", "")
    number = str(fields.get("number", "")).strip()
    stat = fields.get("stat", "")
    sub = fields.get("sub", "")

    prompt = (
        "Recreate the EXACT design, framing and layout of the attached reference "
        "trading card, but for a different player and stats.\n"
        f"- Player: {player_en} ({player}) of {club}.\n"
        "- Portrait: photorealistic head-and-shoulders studio-style portrait, "
        "accurate likeness, wearing the club's CURRENT 2025-26 season home kit "
        "(latest design, correct sponsor and badge).\n"
        f"- Facial expression: {face}.\n"
        f"- Top name banner text: {player_en.upper()}.\n"
        f"- Large headline stat text in the lower panel: \"{stat}\".\n"
        f"- Smaller sub text lines below it: \"{sub}\".\n"
        f"- Jersey number bottom-right corner: {number}.\n"
        "- Keep: white rounded card outline, green inner frame with corner "
        "brackets, soft grey blurred background, club crest badge on the divider, "
        "faint club-crest watermark low in the background.\n"
        "- Korean text must render cleanly and correctly, no gibberish.\n"
        "- Vertical card, 3:4 aspect.\n"
        "This is fan / editorial sports content; depict the player respectfully — "
        "the expression reflects match performance, not mockery. Stats shown are factual."
    )

    ref_b64 = base64.b64encode(CARD_REF.read_bytes()).decode()
    raw = _gemini_call([
        {"text": prompt},
        {"inlineData": {"mimeType": "image/png", "data": ref_b64}},
    ])
    with open(out_path, "wb") as f:
        f.write(raw)
    print(json.dumps({"path": out_path, "model": MODEL, "kind": "player-card",
                      "player": player, "mood": fields.get("mood", "neutral")},
                     ensure_ascii=False))


# ---------- CLI ----------

def _take(args: list, flag: str, default=None):
    if flag in args:
        i = args.index(flag)
        try:
            v = args[i + 1]
        except IndexError:
            die(f"{flag} needs a value")
        del args[i:i + 2]
        return v
    return default


def main() -> None:
    args = list(sys.argv[1:])

    if "--card" in args:
        args.remove("--card")
        fields = {
            "player": _take(args, "--player"),
            "player_en": _take(args, "--player-en"),
            "club": _take(args, "--club", ""),
            "number": _take(args, "--number", ""),
            "stat": _take(args, "--stat", ""),
            "sub": _take(args, "--sub", ""),
            "mood": (_take(args, "--mood", "neutral") or "neutral").lower(),
        }
        if not args:
            die('card usage: gen_image.py --card <out.png> --player "이름" --stat "1골" --mood good')
        out_path = args[0]
        if not fields["player"]:
            die("--player 는 필수")
        gen_card(fields, out_path)
        return

    aspect = _take(args, "--aspect", "16:9")
    seed_raw = _take(args, "--seed")
    seed = int(seed_raw) if seed_raw is not None else None

    if len(args) < 2:
        die('usage: gen_image.py "<prompt>" <out.jpg> [--aspect 16:9] [--seed N]  |  --card <out.png> ...')
    prompt, out_path = args[0], args[1]
    full_prompt = f"{prompt}. Aspect ratio {aspect}.{SAFETY_SUFFIX}"

    if KEY and BACKEND != "pollinations":
        if gen_gemini_mood(full_prompt, out_path):
            return
    gen_pollinations(full_prompt, out_path, aspect, seed)


if __name__ == "__main__":
    main()
