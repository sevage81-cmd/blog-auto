"""
선수 사진처럼 인물이 나온 실사진을, 요일별 테마 컬러의 듀오톤 필터로 살짝
가공해서 원본 그대로 붙여넣지 않고 블로그 그래픽 톤에 맞는 느낌으로 바꾸는
스크립트. 원본은 Wikimedia Commons의 자유 라이선스 사진이라 2차적 저작물
작성이 라이선스로 이미 허용돼 있다(CC BY/BY-SA/CC0 전부 가공 허용) — 다만
캡션에 원저작자/라이선스 표기는 그대로 남기고 "편집됨"만 덧붙이면 된다.

사용법:
    python stylize_photo.py <입력.jpg> <출력.jpg> --theme <테마이름>

입력과 출력 경로가 같아도 된다(제자리 변형). 테마 이름은
build_images.py의 THEMES 키를 그대로 쓴다(예: epl-preview, kor-star).
없거나 모르는 이름이면 default 톤이 적용된다.
"""
import asyncio
import base64
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_images import THEMES  # 요일별 (배경, 포인트, 강조) 컬러 재사용

FRAME_W, FRAME_H = 1200, 800


def theme_colors(name: str) -> tuple[str, str]:
    _, accent, strong = THEMES.get(name or "default", THEMES["default"])
    return accent, strong


def build_html(data_uri: str, accent: str, strong: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body {{ margin:0; padding:0; background:#000; }}
.frame {{ position:relative; width:{FRAME_W}px; height:{FRAME_H}px; overflow:hidden; }}
img {{
  width:100%; height:100%; object-fit:cover; display:block;
  filter: grayscale(70%) contrast(1.15) brightness(0.92) saturate(1.1);
}}
.tint {{
  position:absolute; inset:0;
  background: linear-gradient(155deg, {accent}55 0%, {strong}66 100%);
  mix-blend-mode: color;
}}
.vignette {{
  position:absolute; inset:0;
  box-shadow: inset 0 0 140px 40px rgba(0,0,0,0.35);
}}
</style></head><body>
<div class="frame">
  <img src="{data_uri}">
  <div class="tint"></div>
  <div class="vignette"></div>
</div>
</body></html>"""


async def stylize(in_path: Path, out_path: Path, theme: str) -> None:
    accent, strong = theme_colors(theme)
    raw = in_path.read_bytes()
    ext = in_path.suffix.lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    data_uri = f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"
    html = build_html(data_uri, accent, strong)

    tmp_html = out_path.with_name(out_path.stem + ".stylize-tmp.html")
    tmp_html.write_text(html, encoding="utf-8")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": FRAME_W, "height": FRAME_H})
            await page.goto(tmp_html.as_uri())
            await page.locator(".frame").screenshot(path=str(out_path), type="jpeg", quality=88)
            await browser.close()
    finally:
        tmp_html.unlink(missing_ok=True)


def main():
    if "--selftest" in sys.argv:
        return _selftest()

    if len(sys.argv) < 3:
        print("usage: stylize_photo.py <입력.jpg> <출력.jpg> [--theme <이름>]")
        sys.exit(1)

    in_path, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    theme = None
    if "--theme" in sys.argv:
        theme = sys.argv[sys.argv.index("--theme") + 1]

    asyncio.run(stylize(in_path, out_path, theme))
    print(f"완료: {out_path}")


def _selftest():
    accent, strong = theme_colors("epl-preview")
    assert accent == "#3fe1f0" and strong == "#12b5c9"
    accent, strong = theme_colors("no-such-theme")
    assert accent == THEMES["default"][1]
    html = build_html("data:image/jpeg;base64,AA==", "#111111", "#222222")
    assert "linear-gradient(155deg, #111111" in html
    assert "mix-blend-mode: color" in html
    print("selftest ok")


if __name__ == "__main__":
    main()
