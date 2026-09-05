"""
템플릿(guides/image-templates/*.html)에 spec.json 내용을 채워 넣어 이미지별
HTML을 만들고, Playwright로 한 번에 캡처 + 오버플로우(내용 잘림) 자동 검사까지
끝내는 스크립트.

사용법:
    python build_images.py <images_dir>

<images_dir>/spec.json 을 읽어 같은 폴더에 {id}.html / {id}.png 를 생성한다.
spec.json 스키마는 agents/image-make.md 참고.
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parent.parent / "guides" / "image-templates"

DEFAULT_SIZE = {
    "thumbnail": (1080, 1080),
    "step-diagram": (1200, 640),
    "comparison-table": (1200, 620),
    "key-points": (1200, 620),
    "quote-box": (1200, 460),
}

# 요일별 이미지 테마 — thumbnail + 본문 이미지 공통. image-make가 spec의 각
# 이미지 항목에 "theme": "<이름>" 을 넣는다. 없거나 모르는 이름이면 default(기존 톤).
# 레이아웃/폰트/크기는 그대로, 배경 그라데이션과 포인트 컬러만 바뀐다.
THEMES = {
    "default":      ("linear-gradient(155deg,#2f6f8f 0%,#358a72 55%,#3a9b73 100%)", "#4ade80", "#22c55e"),
    "epl-result":   ("linear-gradient(155deg,#2b1a45 0%,#341a52 55%,#3d195b 100%)", "#25e07d", "#00c766"),
    "epl-preview":  ("linear-gradient(155deg,#3d195b 0%,#5a2a8f 55%,#7c3ce0 100%)", "#3fe1f0", "#12b5c9"),
    "euro-result":  ("linear-gradient(155deg,#241f3a 0%,#3a2440 55%,#4a2545 100%)", "#f5c542", "#d99b1f"),
    "euro-preview": ("linear-gradient(155deg,#1e3a5f 0%,#255780 55%,#2f6f8f 100%)", "#ffd23f", "#e0a83c"),
    "kor-star":     ("linear-gradient(155deg,#0f2a47 0%,#153c5c 55%,#1b4a6b 100%)", "#ff5a5f", "#e63946"),
    "kor-youth":    ("linear-gradient(155deg,#14432f 0%,#216845 55%,#2f7d55 100%)", "#a3e635", "#79c015"),
}


def theme_root(name: str) -> str:
    bg, accent, strong = THEMES.get(name or "default", THEMES["default"])
    return f":root{{--bg:{bg};--accent:{accent};--accent-strong:{strong};}}"


FRAGMENT_FILES = {
    "step-diagram": {"cells": "step-diagram-cell.html", "steps": "step-diagram-step.html"},
    "comparison-table": {
        "left_rows": "comparison-table-row.html",
        "right_rows": "comparison-table-row.html",
    },
    "key-points": {"cards": "key-points-card.html"},
}


def fill(template: str, values: dict) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def render_block(frag_name: str, items: list, join_with: str = "") -> str:
    frag = (TEMPLATES_DIR / frag_name).read_text(encoding="utf-8")
    return join_with.join(fill(frag, item) for item in items)


def build_html(spec: dict) -> str:
    img_type = spec["type"]
    width, height = DEFAULT_SIZE.get(img_type, (1200, 620))
    width = spec.get("width", width)
    height = spec.get("height", height)

    template = (TEMPLATES_DIR / f"{img_type}.html").read_text(encoding="utf-8")
    values = {
        "WIDTH": width,
        "HEIGHT": height,
        "THEME": theme_root(spec.get("theme")),
        **spec.get("vars", {}),
    }

    if img_type == "step-diagram":
        values["CELLS"] = render_block(FRAGMENT_FILES[img_type]["cells"], spec.get("cells", []))
        values["STEPS"] = render_block(
            FRAGMENT_FILES[img_type]["steps"],
            spec.get("steps", []),
            join_with='      <div class="connector"></div>\n',
        )
    elif img_type == "comparison-table":
        row_frag = FRAGMENT_FILES[img_type]["left_rows"]
        values["LEFT_ROWS"] = render_block(row_frag, spec.get("left_rows", []))
        values["RIGHT_ROWS"] = render_block(row_frag, spec.get("right_rows", []))
    elif img_type == "key-points":
        values["CARDS"] = render_block(FRAGMENT_FILES[img_type]["cards"], spec.get("cards", []))

    return fill(template, values), height


async def capture_all(images_dir: Path, specs: list):
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        async def capture_one(spec):
            html, declared_height = build_html(spec)
            html_path = images_dir / f"{spec['id']}.html"
            html_path.write_text(html, encoding="utf-8")

            page = await browser.new_page()
            await page.goto(html_path.as_uri())
            root = page.locator("#capture-root")
            await root.screenshot(path=str(images_dir / f"{spec['id']}.png"))
            scroll_height = await root.evaluate("el => el.scrollHeight")
            await page.close()
            html_path.unlink()

            overflow = scroll_height > declared_height + 2
            return spec["id"], overflow, scroll_height, declared_height

        results = await asyncio.gather(*(capture_one(s) for s in specs))
        await browser.close()
        return results


def main():
    images_dir = Path(sys.argv[1]).resolve()
    spec_path = images_dir / "spec.json"
    specs = json.loads(spec_path.read_text(encoding="utf-8"))["images"]

    results = asyncio.run(capture_all(images_dir, specs))

    overflowed = [r for r in results if r[1]]
    print(f"완료: {len(results)}장 캡처")
    if overflowed:
        print("오버플로우(내용 잘림 가능) 감지 - 텍스트를 줄이거나 height를 늘려서 재실행 필요:")
        for image_id, _, scroll_h, declared_h in overflowed:
            print(f"  - {image_id}: 실제 {scroll_h}px > 지정 {declared_h}px")
    else:
        print("오버플로우 없음 - 전부 정상.")


if __name__ == "__main__":
    main()
