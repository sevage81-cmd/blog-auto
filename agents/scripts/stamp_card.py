"""
user-faces/<구단>/<선수>.png 에 사용자가 만들어 둔 **베이스 선수 카드**에
경기별 스탯 문구와 평가 톤(밝게/어둡게)을 얹어 완성 카드를 만드는 스크립트.

베이스 카드는 이미 (흰 테두리 + 초록 프레임 + 선수 얼굴 + 이름 배너 + 등번호
+ 구단 뱃지) 구성이다. 여기서 하단 초록 패널을 경기 스탯 패널로 덮어씌운다.

사용법:
    python stamp_card.py <base.png> <out.png>
        --stat "1골 1도움" --sub "vs 에버턴 · 프리미어리그"
        [--mood good|bad|neutral] [--theme epl-result] [--number 8]

스탯·하단문구는 image-make 가 research.md 기준 사실만 넣는다.
mood: good=밝고 따뜻 / bad=어둡고 차갑게 / neutral=그대로.
"""
import asyncio
import base64
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_images import THEMES

MOOD = {
    "good": ("brightness(1.05) saturate(1.1) contrast(1.02)",
             "radial-gradient(circle at 50% 30%, rgba(255,214,140,0.22), rgba(255,170,80,0) 65%)"),
    "bad": ("grayscale(0.42) brightness(0.8) contrast(1.06)",
            "linear-gradient(180deg, rgba(18,32,66,0.28) 0%, rgba(8,12,26,0.5) 100%)"),
    "neutral": ("none", "transparent"),
}


def _theme(name: str):
    bg, accent, strong = THEMES.get(name or "epl-result", THEMES["epl-result"])
    return bg, accent, strong


def build_html(data_uri: str, w: int, h: int, *, stat: str, sub: str,
               number: str, mood: str, theme: str) -> str:
    bg, accent, strong = _theme(theme)
    filt, tint = MOOD.get(mood, MOOD["neutral"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; }}
  .frame {{
    position:relative; width:{w}px; height:{h}px; overflow:hidden;
    font-family:'Pretendard','Malgun Gothic','Apple SD Gothic Neo',sans-serif;
  }}
  .base {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
           filter:{filt}; }}
  .tint {{ position:absolute; inset:0; background:{tint}; }}

  /* 하단 초록 패널을 스탯 패널로 덮어씌운다 (카드 안쪽에 맞춰 인셋).
     베이스 카드 흰 테두리 안쪽에 딱 맞도록 — AI 생성 편차가 있어 살짝 보수적. */
  .stat {{
    position:absolute;
    left:24%; right:24%; bottom:9%;
    top:72%;
    background:{bg};
    border-radius:4px 4px 30px 30px;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    text-align:center; padding:0 22px; overflow:hidden;
  }}
  .stat .num {{
    position:absolute; right:18px; bottom:10px;
    font-size:30px; font-weight:900; color:rgba(255,255,255,0.55);
  }}
  .stat .headline {{
    color:#fff; font-size:52px; font-weight:900; letter-spacing:-1px; line-height:1.08;
  }}
  .stat .sub {{
    margin-top:10px; color:#e7efe9; font-size:23px; font-weight:600; line-height:1.3;
  }}
</style></head><body>
  <div class="frame">
    <img class="base" src="{data_uri}">
    <div class="tint"></div>
    <div class="stat">
      <div class="headline">{stat}</div>
      <div class="sub">{sub}</div>
      <div class="num">{number}</div>
    </div>
  </div>
</body></html>"""


async def stamp(base: Path, out: Path, *, stat: str, sub: str, number: str,
                mood: str, theme: str) -> None:
    raw = base.read_bytes()
    # PNG 크기 읽기 (16..24 바이트가 width,height big-endian)
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        w = int.from_bytes(raw[16:20], "big")
        h = int.from_bytes(raw[20:24], "big")
    else:
        w = h = 1024
    data_uri = "data:image/png;base64," + base64.b64encode(raw).decode()
    html = build_html(data_uri, w, h, stat=stat, sub=sub, number=number,
                      mood=mood, theme=theme)

    tmp = out.with_name(out.stem + ".stamp-tmp.html")
    tmp.write_text(html, encoding="utf-8")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": w, "height": h})
            await page.goto(tmp.as_uri())
            await page.locator(".frame").screenshot(path=str(out))
            await browser.close()
    finally:
        tmp.unlink(missing_ok=True)


def _opt(name: str, default: str = "") -> str:
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def main() -> None:
    if "--selftest" in sys.argv:
        html = build_html("data:image/png;base64,AA==", 1024, 1024,
                          stat="1골 1도움", sub="vs 에버턴", number="8",
                          mood="bad", theme="epl-result")
        assert "grayscale(0.42)" in html and "1골 1도움" in html
        print("selftest ok")
        return
    if len(sys.argv) < 3:
        print("usage: stamp_card.py <base.png> <out.png> --stat \"...\" --sub \"...\" [--mood good] [--theme epl-result] [--number 8]")
        sys.exit(1)
    base, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    asyncio.run(stamp(
        base, out,
        stat=_opt("--stat"), sub=_opt("--sub"), number=_opt("--number"),
        mood=(_opt("--mood", "neutral") or "neutral").lower(),
        theme=_opt("--theme", "epl-result"),
    ))
    print(f"완료: {out}")


if __name__ == "__main__":
    main()
