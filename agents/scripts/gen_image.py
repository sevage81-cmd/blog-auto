"""
AI 이미지 생성 스크립트 (분위기 컷 전용).

저작권 걱정 없는 "실사에 최대한 유사한" 이미지를 프롬프트로 생성해서 저장한다.
Wikimedia Commons에 쓸 만한 실사진이 없을 때(경기장 내부, 관중석, 조명 아래
피치, 골 세리머니 분위기 등) image-make 에이전트가 이 스크립트로 "분위기 컷"을
만든다. fetch_photo.py(Commons 실사진)를 대체하는 게 아니라 보완한다.

백엔드 2개:
- pollinations  — 무료, 키 불필요(Flux 기반). 기본값.
- gemini        — Google Gemini 이미지 모델. GEMINI_API_KEY + 결제 크레딧 필요.
                  키가 있으면 먼저 시도하고, 쿼터/결제 오류(429/402)면 자동으로
                  pollinations 로 폴백한다.

안전 규칙 (프롬프트에 자동으로 덧붙는다):
- 실존 인물의 식별 가능한 얼굴을 특정해 생성하지 않는다(딥페이크 방지).
  얼굴이 필요하면 뒷모습·실루엣·원거리·군중 수준으로.
- 로고·엠블럼·유니폼 스폰서·텍스트 오버레이·워터마크 없이.
- image-make 에이전트는 이 이미지 캡션에 반드시 "AI 생성 이미지"를 밝힌다.

사용법:
    python gen_image.py "<영문 프롬프트>" <저장경로(.jpg|.png)> [--aspect 16:9]

환경변수:
    GEMINI_API_KEY       (선택) 있으면 gemini 백엔드를 먼저 시도.
    GEMINI_IMAGE_MODEL   (선택) 기본 "gemini-3-pro-image".
    IMAGE_BACKEND        (선택) "pollinations" 로 고정하면 gemini 를 건너뛴다.

성공: stdout 에 JSON 한 줄  {"path", "model", "prompt"}
실패: stdout 에 {"error": "..."} 찍고 exit 1
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image").strip()
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BACKEND = os.environ.get("IMAGE_BACKEND", "").strip().lower()

SAFETY_SUFFIX = (
    " Photorealistic editorial sports photography, natural stadium lighting, "
    "shallow depth of field, sharp focus, high detail, wide cinematic shot. "
    "Do NOT depict any real, identifiable person's face — crowds, silhouettes, "
    "distant or back views only. No club logos, no emblems, no kit sponsors, "
    "no text, no scoreboard graphics, no watermark."
)

# 16:9 등 aspect 문자열 -> (width, height). 목록에 없으면 비율로 계산.
ASPECT_SIZES = {
    "16:9": (1280, 720), "3:2": (1200, 800), "4:3": (1024, 768),
    "1:1": (1024, 1024), "9:16": (720, 1280), "2:3": (800, 1200),
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


def gen_pollinations(full_prompt: str, out_path: str, aspect: str, seed: int | None) -> None:
    w, h = dims_for(aspect)
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(full_prompt, safe="")
        + f"?width={w}&height={h}&nologo=true&model=flux&enhance=true"
    )
    if seed is not None:
        url += f"&seed={seed}"
    req = urllib.request.Request(url, headers={"User-Agent": "blog-pipeline/1"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        die(f"pollinations HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:  # noqa: BLE001
        die(f"pollinations {type(e).__name__}: {e}")
    if len(raw) < 1000 or not raw[:3] == b"\xff\xd8\xff" and b"PNG" not in raw[:8]:
        die(f"pollinations 응답이 이미지가 아님 ({len(raw)} bytes)")
    with open(out_path, "wb") as f:
        f.write(raw)
    print(json.dumps(
        {"path": out_path, "model": "pollinations/flux", "prompt": full_prompt.split(". Aspect")[0]},
        ensure_ascii=False,
    ))


def gen_gemini(full_prompt: str, out_path: str) -> bool:
    """성공하면 저장 후 True. 쿼터/결제 오류면 False(폴백 신호). 그 외 오류는 die()."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in (402, 429):
            sys.stderr.write(f"[gen_image] gemini {e.code}, pollinations 로 폴백: {detail[:120]}\n")
            return False
        die(f"gemini HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        die(f"gemini {type(e).__name__}: {e}")

    cands = data.get("candidates") or []
    parts = cands[0].get("content", {}).get("parts", []) if cands else []
    b64 = next(
        (p["inlineData"]["data"] for p in parts
         if isinstance(p, dict) and "inlineData" in p and p["inlineData"].get("data")),
        None,
    )
    if not b64:
        die(f"gemini 응답에 이미지 없음: {json.dumps(data, ensure_ascii=False)[:400]}")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(json.dumps({"path": out_path, "model": MODEL, "prompt": full_prompt.split(". Aspect")[0]},
                     ensure_ascii=False))
    return True


def main() -> None:
    args = list(sys.argv[1:])
    aspect = "16:9"
    seed: int | None = None
    for flag, cast in (("--aspect", str), ("--seed", int)):
        if flag in args:
            i = args.index(flag)
            try:
                val = cast(args[i + 1])
            except (IndexError, ValueError):
                die(f"{flag} needs a value")
            del args[i:i + 2]
            if flag == "--aspect":
                aspect = val
            else:
                seed = val

    if len(args) < 2:
        die('usage: gen_image.py "<prompt>" <out.jpg> [--aspect 16:9] [--seed N]')
    prompt, out_path = args[0], args[1]
    full_prompt = f"{prompt}. Aspect ratio {aspect}.{SAFETY_SUFFIX}"

    if KEY and BACKEND != "pollinations":
        if gen_gemini(full_prompt, out_path):
            return
    gen_pollinations(full_prompt, out_path, aspect, seed)


if __name__ == "__main__":
    main()
