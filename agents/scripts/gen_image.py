"""
Google Gemini(Nano Banana) 이미지 생성 스크립트.

저작권 걱정 없는 "실사에 최대한 유사한" 이미지를 프롬프트로 생성해서 저장한다.
Wikimedia Commons에 쓸 만한 실사진이 없을 때(경기장 내부, 관중석, 조명 아래
피치, 골 세리머니 분위기 등) image-make 에이전트가 이 스크립트로 "분위기 컷"을
만든다. fetch_photo.py(Commons 실사진)를 대체하는 게 아니라 보완한다.

안전 규칙 (프롬프트에 자동으로 덧붙는다):
- 실존 인물의 식별 가능한 얼굴을 특정해 생성하지 않는다(딥페이크 방지).
  얼굴이 필요하면 뒷모습·실루엣·원거리·군중 수준으로.
- 로고·엠블럼·유니폼 스폰서·텍스트 오버레이·워터마크 없이.
- image-make 에이전트는 이 이미지 캡션에 반드시 "AI 생성 이미지"를 밝힌다.

사용법:
    python gen_image.py "<영문 프롬프트>" <저장경로(.jpg|.png)> [--aspect 16:9]

환경변수:
    GEMINI_API_KEY       (필수) Google AI Studio 발급 키
    GEMINI_IMAGE_MODEL   (선택) 기본 "gemini-2.5-flash-image-preview".
                         모델 ID가 바뀌면 이 값만 덮어쓰면 된다.

성공: stdout 에 JSON 한 줄  {"path", "model", "prompt"}
실패: stdout 에 {"error": "..."} 찍고 exit 1
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image-preview").strip()
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

SAFETY_SUFFIX = (
    " Photorealistic editorial sports photography, natural stadium lighting, "
    "shallow depth of field, sharp focus, high detail. "
    "Do NOT depict any real, identifiable person's face — crowds, silhouettes, "
    "distant or back views only. No club logos, no emblems, no kit sponsors, "
    "no text, no scoreboard graphics, no watermark."
)


def die(msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def main() -> None:
    args = list(sys.argv[1:])
    aspect = "16:9"
    if "--aspect" in args:
        i = args.index("--aspect")
        try:
            aspect = args[i + 1]
            del args[i:i + 2]
        except IndexError:
            die("--aspect needs a value like 16:9")

    if len(args) < 2:
        die('usage: gen_image.py "<prompt>" <out.jpg> [--aspect 16:9]')
    prompt, out_path = args[0], args[1]

    if not KEY:
        die("GEMINI_API_KEY not set (repo 루트 secrets.env 또는 사용자 환경변수)")

    full_prompt = f"{prompt}. Aspect ratio {aspect}.{SAFETY_SUFFIX}"
    body = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        # 이미지 모델은 TEXT+IMAGE 를 함께 요구한다(IMAGE 단독은 거부되는 버전이 있음).
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        die(f"HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001 - 원인만 보고하면 됨
        die(f"{type(e).__name__}: {e}")

    cands = data.get("candidates") or []
    parts = cands[0].get("content", {}).get("parts", []) if cands else []
    b64 = next(
        (p["inlineData"]["data"] for p in parts
         if isinstance(p, dict) and "inlineData" in p and p["inlineData"].get("data")),
        None,
    )
    if not b64:
        die(f"응답에 이미지 없음: {json.dumps(data, ensure_ascii=False)[:600]}")

    try:
        raw = base64.b64decode(b64)
    except Exception as e:  # noqa: BLE001
        die(f"base64 decode 실패: {e}")

    with open(out_path, "wb") as f:
        f.write(raw)

    print(json.dumps(
        {"path": out_path, "model": MODEL, "prompt": prompt},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
