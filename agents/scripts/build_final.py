"""
draft.md(이미지 마커가 실제 경로로 치환된 최종 초안)를 final.md/final.html로
조립하는 스크립트. LLM이 이미 완성된 글을 통째로 다시 쓰지 않도록, 그대로
옮기기만 하면 되는 이 단계는 스크립트로 처리한다.

사용법:
    python build_final.py "output/[주제]"

<output_dir>/draft.md 를 읽어 같은 폴더에 final.md / final.html 을 만든다.
draft.md 포맷 전제 (write.md/image-make.md 산출물 기준):
    # 제목
    (빈 줄로 구분된 문단들, "## 소제목", "---" 구분선, "![alt](경로)" 이미지)
    마지막 줄: #해시태그 #해시태그 ...
"""
import html
import re
import sys
from pathlib import Path

STYLE = """\
  body {
    font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", sans-serif;
    background-color: #f7f7f7;
    color: #333333;
    margin: 0;
    padding: 40px 16px;
    line-height: 1.8;
    word-break: keep-all;
  }
  .container {
    max-width: 700px;
    margin: 0 auto;
    background-color: #ffffff;
    padding: 48px 32px;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  }
  h1 {
    font-size: 26px;
    font-weight: 700;
    color: #1a1a1a;
    line-height: 1.4;
    margin: 0 0 28px 0;
  }
  h2 {
    font-size: 20px;
    font-weight: 700;
    color: #1a1a1a;
    margin: 44px 0 20px 0;
    padding-top: 8px;
    border-top: 2px solid #1a1a1a;
  }
  h3 {
    font-size: 17px;
    font-weight: 700;
    color: #1a1a1a;
    margin: 28px 0 14px 0;
  }
  p {
    font-size: 16px;
    margin: 0 0 18px 0;
    color: #333333;
  }
  img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 24px auto;
    border-radius: 4px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 28px;
    font-size: 14px;
  }
  ul {
    margin: 0 0 18px 0;
    padding-left: 20px;
    font-size: 16px;
    color: #333333;
  }
  li {
    margin-bottom: 6px;
  }
  th, td {
    border: 1px solid #e5e5e5;
    padding: 10px 12px;
    text-align: left;
  }
  th {
    background: #f7f7f8;
    font-weight: 700;
    color: #111111;
  }
  td {
    color: #333333;
  }
  .tags {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #eaeaea;
    font-size: 14px;
    color: #4a90d9;
    line-height: 1.9;
  }
  .caption {
    font-size: 13px;
    color: #888888;
    text-align: center;
    margin: -12px 0 24px 0;
  }
"""

IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.*?)\)$")


def inline_html(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text


def render_table(block: str) -> str:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in block.splitlines()
        if line.strip()
    ]
    header, _separator, *body = rows
    thead = "<tr>" + "".join(f"<th>{inline_html(c)}</th>" for c in header) + "</tr>"
    tbody = "\n      ".join(
        "<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in row) + "</tr>" for row in body
    )
    return f"<table>\n    <thead>\n      {thead}\n    </thead>\n    <tbody>\n      {tbody}\n    </tbody>\n  </table>"


def render_list(block: str) -> str:
    items = "\n      ".join(
        f"<li>{inline_html(line.strip()[2:].strip())}</li>" for line in block.splitlines() if line.strip()
    )
    return f"<ul>\n      {items}\n    </ul>"


def build_html(title: str, blocks: list[str]) -> str:
    body_parts = [f"<h1>{inline_html(title)}</h1>"]

    for block in blocks:
        if block == "---":
            continue
        if block.strip() == "&nbsp;":
            continue
        if block.startswith("## "):
            body_parts.append(f"<h2>{inline_html(block[3:].strip())}</h2>")
            continue
        if block.startswith("### "):
            body_parts.append(f"<h3>{inline_html(block[4:].strip())}</h3>")
            continue
        if block.startswith("|"):
            body_parts.append(render_table(block))
            continue
        if all(line.strip().startswith("- ") for line in block.splitlines() if line.strip()):
            body_parts.append(render_list(block))
            continue
        block_lines = block.splitlines()
        m = IMAGE_RE.match(block_lines[0])
        if m:
            alt, src = m.groups()
            body_parts.append(f'<img src="{html.escape(src)}" alt="{html.escape(alt)}">')
            caption = " ".join(line.strip() for line in block_lines[1:] if line.strip())
            if caption:
                body_parts.append(f'<p class="caption">{inline_html(caption)}</p>')
            continue
        if block.startswith("#") and not block.startswith("# "):
            body_parts.append(f'<p class="tags">{html.escape(block, quote=False)}</p>')
            continue
        # 이미지와 빈 줄로 떨어진 캡션("사진: ...", "이미지: AI 생성 ...")도
        # .caption 으로. (이미지 바로 다음 줄이면 위 IMAGE_RE 블록에서 처리됨)
        if re.match(r"^(사진|이미지)\s*[:·]", block) and "\n" not in block:
            body_parts.append(f'<p class="caption">{inline_html(block)}</p>')
            continue
        body_parts.append(f"<p>{inline_html(block)}</p>")

    body_html = "\n\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
{STYLE}</style>
</head>
<body>
<div class="container">

{body_html}

</div>
</body>
</html>
"""


def _selftest():
    html_out = build_html("제목", [
        "문단", "- 항목1\n- 항목2", "## 소제목", "### 더작은제목",
        "![alt](./x.png)", "![사진alt](./p.jpg)\n사진: 저작자 · CC BY · Wikimedia Commons (출처: https://x)",
        "![loose](./l.jpg)", "이미지: AI 생성 이미지 (Pollinations) · 특정 경기·인물이 아닌 연출 이미지",
        "&nbsp;", "#태그1 #태그2",
    ])
    assert '<p class="caption">이미지: AI 생성 이미지 (Pollinations) · 특정 경기·인물이 아닌 연출 이미지</p>' in html_out
    assert "<ul>" in html_out and "<li>항목1</li>" in html_out and "<li>항목2</li>" in html_out
    assert "<h2>소제목</h2>" in html_out
    assert "<h3>더작은제목</h3>" in html_out
    assert '<img src="./x.png" alt="alt">' in html_out
    assert '<img src="./p.jpg" alt="사진alt">' in html_out
    assert '<p class="caption">사진: 저작자 · CC BY · Wikimedia Commons (출처: https://x)</p>' in html_out
    assert "&amp;nbsp;" not in html_out
    assert '<p class="tags">#태그1 #태그2</p>' in html_out
    print("selftest ok")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
        return

    output_dir = Path(sys.argv[1]).resolve()
    draft = (output_dir / "draft.md").read_text(encoding="utf-8")

    (output_dir / "final.md").write_text(draft.strip() + "\n", encoding="utf-8", newline="\n")

    lines = draft.strip().splitlines()
    if not lines[0].startswith("# "):
        raise ValueError("draft.md 첫 줄이 '# 제목' 형식이 아닙니다.")
    title = lines[0][2:].strip()

    blocks = [b.strip() for b in "\n".join(lines[1:]).split("\n\n") if b.strip()]

    final_html = build_html(title, blocks)
    (output_dir / "final.html").write_text(final_html, encoding="utf-8", newline="\n")

    print(f"완료: {output_dir / 'final.md'}")
    print(f"완료: {output_dir / 'final.html'}")


if __name__ == "__main__":
    main()
