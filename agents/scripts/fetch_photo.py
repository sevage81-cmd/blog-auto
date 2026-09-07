"""
Wikimedia Commons에서 저작권 걱정 없는(전부 자유 라이선스) 실사진을 검색해
다운로드하고, 캡션에 쓸 저작자/라이선스 정보를 함께 돌려주는 스크립트.

Commons에 올라간 파일은 정책상 전부 CC/PD 등 자유 라이선스이므로, 여기서만
사진을 가져오면 출처 캡션 한 줄만 붙여도 그대로 쓸 수 있다. 구글 이미지·뉴스
기사·공식 SNS 캡처는 저작권이 확인되지 않으므로 절대 쓰지 않는다.

사용법:
    python fetch_photo.py "<검색어(영문 고유명사 권장)>" <저장경로.jpg> [--width 1400]

성공하면 stdout에 JSON 한 줄:
    {"title", "query", "path", "author", "license", "source_url"}
실패하면 {"error": "..."} 를 찍고 exit code 1.
image-make 에이전트는 author/license/source_url로 사진 아래 캡션 문단을 만들고,
path의 사진을 Read로 한 번 확인해 마커 설명과 실제로 맞는지 검증한다.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

# Windows 기본 stdout 인코딩(cp949)은 Commons 저작자명의 ü·é 같은 문자를 못 써서
# json.dumps(ensure_ascii=False) 출력이 UnicodeEncodeError로 죽는다 → UTF-8 고정.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # py<3.7
    pass

API = "https://commons.wikimedia.org/w/api.php"
UA = "blog-pipeline/1.0 (personal blog image sourcing; contact: n/a)"
PHOTO_EXT = (".jpg", ".jpeg", ".png")


def api_get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def search_photo_titles(query: str, limit: int = 8) -> list[str]:
    data = api_get({"action": "query", "list": "search", "srsearch": query,
                     "srnamespace": 6, "srlimit": limit})
    titles = [item["title"] for item in data.get("query", {}).get("search", [])]
    # ponytail: 파일명 확장자만 보고 사진/비사진을 가른다 — 로고·다이어그램(svg)·
    # 문서(pdf)를 걸러내는 정도의 단순 휴리스틱. 내용까지 판별하려면 이미지 인식이
    # 필요한데, 그건 image-make가 다운로드 후 Read로 눈으로 확인하는 단계가 대신한다.
    return [t for t in titles if t.lower().endswith(PHOTO_EXT)]


def strip_tags(html_fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", html_fragment or "").strip()


def image_info(title: str, width: int) -> dict | None:
    data = api_get({"action": "query", "titles": title, "prop": "imageinfo",
                     "iiprop": "url|user|extmetadata", "iiurlwidth": width})
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    infos = page.get("imageinfo") or [None]
    return infos[0]


def download(url: str, out_path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r, open(out_path, "wb") as f:
        f.write(r.read())


def main():
    if "--selftest" in sys.argv:
        return _selftest()

    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: fetch_photo.py <query> <out_path> [--width N]"}))
        sys.exit(1)

    query, out_path = sys.argv[1], sys.argv[2]
    width = 1400
    if "--width" in sys.argv:
        width = int(sys.argv[sys.argv.index("--width") + 1])

    titles = search_photo_titles(query)
    if not titles:
        print(json.dumps({"error": "no photo found", "query": query}, ensure_ascii=False))
        sys.exit(1)

    for title in titles[:5]:
        info = image_info(title, width)
        if not info:
            continue
        img_url = info.get("thumburl") or info.get("url")
        if not img_url:
            continue
        meta = info.get("extmetadata", {})
        artist = strip_tags(meta.get("Artist", {}).get("value", "")) or info.get("user") or "작자 미상"
        license_name = meta.get("LicenseShortName", {}).get("value") or "라이선스 미상"

        try:
            download(img_url, out_path)
        except Exception:
            continue  # 이 후보가 실패하면 다음 후보로

        print(json.dumps({
            "title": title,
            "query": query,
            "path": out_path,
            "author": artist,
            "license": license_name,
            "source_url": info.get("descriptionurl"),
        }, ensure_ascii=False))
        return

    print(json.dumps({"error": "no downloadable photo", "query": query}, ensure_ascii=False))
    sys.exit(1)


def _selftest():
    titles = ["File:A.jpg", "File:B.svg", "File:C.PNG", "File:D.pdf"]
    photos = [t for t in titles if t.lower().endswith(PHOTO_EXT)]
    assert photos == ["File:A.jpg", "File:C.PNG"], photos
    assert strip_tags('<a href="x">dom fellowes</a> from UK') == "dom fellowes from UK"
    assert strip_tags("") == ""
    print("selftest ok")


if __name__ == "__main__":
    main()
