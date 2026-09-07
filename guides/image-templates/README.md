# 이미지 템플릿

`agents/scripts/build_images.py`가 읽는 HTML 템플릿 모음. 디자인은
`image-guide.md` 규격에 맞춰 이미 확정돼 있다 — image-make 에이전트는 이
파일들을 고치지 않고, `spec.json`에 내용만 채워서 넘긴다.

`player-card-ref.png` 은 HTML 템플릿이 아니라 **선수 카드 디자인 레퍼런스**다.
기본 선수 카드는 `player-card.html` 템플릿(무료·자동)으로 만들고, 이 PNG는
그 디자인의 기준이다. `GEMINI_API_KEY` + 크레딧이 있으면 `gen_image.py --card`
가 이 이미지를 Gemini에 함께 넘겨 AI 생성 카드(진짜 표정·최신 유니폼)도 만든다.

모든 텍스트 필드는 그대로 HTML에 삽입된다. 줄바꿈이 필요하면 `<br>`을
직접 넣는다 (예: `"부임일 · 계약<br>5년 계약"`).

## spec.json 형식

```json
{ "images": [ { "id": "...", "type": "...", "height": 620, "vars": {...}, ... }, ... ] }
```

- `id` — 파일명이 된다 (`thumbnail`, `body-1`, `body-2`, `card-1`, ...)
- `type` — 아래 종류 중 하나 (thumbnail / step-diagram / comparison-table /
  key-points / quote-box / player-card)
- `theme` — 생략 가능. 요일별 색 테마 이름 (`epl-result`, `epl-preview`,
  `euro-result`, `euro-preview`, `kor-star`, `kor-youth`). 생략하면 `default`.
  값 정의는 `agents/scripts/build_images.py`의 `THEMES`, 용도는
  `guides/image-guide.md`의 "1-2. 요일별 테마" 참고.
- `height` — 생략 가능(타입별 기본값 있음). 텍스트가 많으면 미리 넉넉히 준다.
- `width` — 생략 가능. 대표 이미지 1080, 본문 이미지 1200이 기본.

### thumbnail (기본 1080×1080)

```json
{ "id": "thumbnail", "type": "thumbnail",
  "vars": { "BADGE_TEXT": "...", "TITLE_LINE1": "...", "TITLE_LINE2": "...", "SUBTITLE": "..." } }
```

### step-diagram — 단계/타임라인 (기본 1200×640)

```json
{ "id": "body-1", "type": "step-diagram", "height": 720,
  "vars": { "EYEBROW": "...", "TITLE": "...", "FOOTER": "..." },
  "cells": [ { "NUM": "17위", "LABEL": "최종 순위" } ],
  "steps": [ { "INDEX": "1", "NAME": "...", "CARD_CLASS": "out|in",
               "STATUS_CLASS": "fired|short|appointed", "STATUS_TEXT": "..." } ] }
```

- `cells`는 상단 요약 수치 박스(0개 이상, 보통 2~3개).
- `steps`는 타임라인 카드(2개 이상). `CARD_CLASS`/`STATUS_CLASS`는 위 값 중
  내용에 맞는 걸 고르거나, 필요하면 새 클래스명을 만들고 같은 이름으로
  CSS도 함께 추가해도 된다(템플릿 파일의 `.status.*`, `.card.*` 규칙 참고).

### comparison-table — 두 그룹 비교 (기본 1200×620)

```json
{ "id": "body-2", "type": "comparison-table",
  "vars": { "TITLE_PREFIX": "...", "TITLE_ACCENT": "...",
            "LEFT_TAG": "IN 영입", "LEFT_SUB": "...", "RIGHT_TAG": "OUT 방출", "RIGHT_SUB": "...",
            "SCORE_LEFT_LABEL": "...", "SCORE_LEFT_VALUE": "...",
            "SCORE_RIGHT_LABEL": "...", "SCORE_RIGHT_VALUE": "..." },
  "left_rows": [ { "PLAYER": "...", "FROM": "...", "FEE": "..." } ],
  "right_rows": [ { "PLAYER": "...", "FROM": "...", "FEE": "..." } ] }
```

- 양쪽 행 개수는 보통 3~5개, 꼭 같은 개수일 필요는 없다.
- "선수 이적"이 아닌 다른 비교(예: 제품 스펙)에도 `PLAYER`/`FROM`/`FEE`
  필드를 그 용도에 맞는 텍스트로 채워서 그대로 쓴다.

### key-points — 핵심 포인트 카드 3~5개 (기본 1200×620)

```json
{ "id": "body-3", "type": "key-points",
  "vars": { "HEAD_NAME": "...", "HEAD_ROLE": "..." },
  "cards": [ { "LABEL": "...", "VALUE": "...", "DESC": "..." } ] }
```

### quote-box — 한 문장 인용/강조 (기본 1200×460)

```json
{ "id": "body-4", "type": "quote-box",
  "vars": { "EYEBROW": "...", "QUOTE_TEXT": "...", "QUOTE_AUTHOR": "..." } }
```

- `EYEBROW`는 상단 작은 라벨(날짜, 섹션명 등). 없으면 빈 문자열 `""`.

### player-card — 선수 카드 (기본 900×1200, 세로)

```json
{ "id": "card-1", "type": "player-card", "theme": "epl-result", "mood": "good",
  "face": "face-1.jpg",
  "vars": { "NAME": "BRUNO FERNANDES", "STAT": "1골 1도움",
            "SUB": "vs 에버턴 · 프리미어리그", "NUMBER": "8", "CLUB_SHORT": "맨유" } }
```

- `face` — 같은 `images/` 폴더의 얼굴 사진 파일명. `face-*` 로 시작하면
  캡처 후 자동 삭제된다(중간 산출물). image-make 가 user-faces/ 또는
  Commons에서 확보해 둔다.
- `mood` — `good`(밝고 따뜻) / `bad`(어둡고 차갑게) / `neutral`. 얼굴 사진에
  CSS 필터로 적용된다. 매핑은 `build_images.py`의 `CARD_MOOD`.
- `NAME` 영문 대문자, `CLUB_SHORT` 짧은 구단 약칭, `NUMBER` 등번호.
- 디자인 레퍼런스: `player-card-ref.png`.

## 오버플로우(내용 잘림) 처리

`build_images.py`는 캡처 후 실제 렌더링 높이가 지정한 `height`를 넘으면
경고를 출력한다. 그러면:

1. 텍스트를 줄이거나
2. 해당 이미지의 `height`를 늘려서

`spec.json`을 고치고 스크립트를 다시 실행한다 (전체가 아니라 그 실행
자체가 이미 모든 이미지를 다시 캡처하지만, 수정은 문제된 이미지만 하면 됨).
