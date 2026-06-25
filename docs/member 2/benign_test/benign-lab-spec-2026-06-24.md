# Benign Lab Spec 재검증 보고서 - 2026-06-24

생성일: `2026-06-24`

현재 spec 모드 정리 이후 benign-lab 전체를 스캔하여 오탐 후보를 확인한 결과입니다.

## 스캔 범위

- 대상: `vulnerable-lab/benign-lab/mcp03-benign-100`
- 대상: `vulnerable-lab/benign-lab/general-benign-100`
- 모드: `spec` 경계 적용 현재 기본 Detector Registry
- 기준: `_meta/meta`, raw 임의 필드, schema `default/examples/enum/required/type`은 기본 MCP03 판정에서 제외

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

- `mcp03-url_encoding-0cc001c83faf`: 1

## 탐지 사례 목록

| 사례 | 경로 | finding 수 | 주요 severity | 주요 category |
|---|---|---:|---|---|
| `BENIGN-032` / `BENIGN-032-url-encoding-doc` | `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json` | 1 | medium:1 | obfuscation.url_encoding:1 |

## 탐지 상세

### BENIGN-032 - BENIGN-032-url-encoding-doc

- 경로: `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json`
- 라벨/그룹: `MCP03 benign false-positive control`
- 기대/설명: No finding from default MCP03/obfuscation detectors.

| ID | Category | Severity | Confidence | Location | Evidence |
|---|---|---|---|---|---|
| `mcp03-url_encoding-0cc001c83faf` | `obfuscation.url_encoding` | `medium` | `medium` | `description` | {"decoded_excerpt": "hello world.", "encoding": "url_encoding", "original_excerpt": "hello%20world.", "transformation_chain": ["url_encoding"]} |
