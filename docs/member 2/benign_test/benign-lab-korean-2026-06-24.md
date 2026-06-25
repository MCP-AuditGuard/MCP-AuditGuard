# Benign Lab Korean 재검증 보고서 - 2026-06-24

생성일: `2026-06-24`

한국어 사용자용 `title`과 `recommendation` 문구를 적용한 뒤 benign-lab 전체를 스캔하여 오탐 후보를 확인한 결과입니다.

## 스캔 범위

- 대상: `vulnerable-lab/benign-lab/mcp03-benign-100`
- 대상: `vulnerable-lab/benign-lab/general-benign-100`
- 모드: 현재 기본 Detector Registry
- 목적: 한국어 사용자용 `title`/`recommendation` 문구 반영 확인
- 비고: `id`, `category`, `severity`, `confidence`, `location`, `evidence`는 기존 기계 판정 값을 유지

## 요약

- 전체 사례: 200
- 탐지 사례: 1
- 미탐/무탐지 사례: 199
- finding 수: 1
- 오류 사례: 0

## Severity 분포

- `critical`: 0
- `high`: 0
- `medium`: 1
- `low`: 0
- `info`: 0

## Category 상위 분포

- `obfuscation.url_encoding`: 1

## Rule/Finding ID 상위 분포

- `mcp03-url_encoding-ca5868d8b9c6`: 1

## 탐지 사례 목록

| 사례 | 경로 | finding 수 | 주요 severity | 주요 category |
|---|---|---:|---|---|
| `BENIGN-032` / `BENIGN-032-url-encoding-doc` | `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json` | 1 | medium:1 | obfuscation.url_encoding:1 |

## 탐지 상세

### BENIGN-032 - BENIGN-032-url-encoding-doc

- 경로: `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json`
- 라벨/그룹: `MCP03 benign false-positive control`
- 난이도: `-`
- 기대/설명: No finding from default MCP03/obfuscation detectors.

| ID | Title | Category | Severity | Confidence | Location | Evidence 요약 | Recommendation |
|---|---|---|---|---|---|---|---|
| `mcp03-url_encoding-ca5868d8b9c6` | 도구 메타데이터의 URL_ENCODING 인코딩 페이로드 | `obfuscation.url_encoding` | `medium` | `medium` | `description` | {"decoded_excerpt": "hello world.", "encoding": "url_encoding", "original_excerpt": "hello%20world.", "transformation_chain": ["url_encoding"]} | MCP 도구 메타데이터는 사람이 읽을 수 있는 기능 설명을 제공하는 용도입니다. 인코딩된 문자열 안에 실제 설명과 다른 지시문이 숨겨져 있는지 복호화해 확인하세요. 실제 기능 설명과 무관한 숨겨진 내용이라면 제거하거나 평문 설명으로 수정하세요. |
