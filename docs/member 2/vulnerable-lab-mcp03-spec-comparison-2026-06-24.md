# Vulnerable Lab MCP03 Spec 전후 비교 보고서 - 2026-06-24

생성일: `2026-06-24`

## 비교 대상

- 기존 보고서: `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-24.md`
- Spec 보고서: `docs/member 2/vulnerable-lab-detected-mcp03-spec-2026-06-24.md`

기존 `vulnerable-lab-detected-mcp03-2026-06-24.md`는 같은 날짜에 생성된 spec 적용 전 최신 vulnerable-lab 보고서로 보고 비교했습니다. 새 보고서는 `_meta/meta`, raw 임의 필드, schema `default/examples/enum/required/type`을 기본 MCP03 판정에서 제외한 spec 경계 적용 결과입니다.

## 요약 변화

| 항목 | 기존 | Spec | 변화 |
|---|---:|---:|---:|
| 전체 사례 | 112 | 112 | +0 |
| 탐지 사례 | 48 | 45 | -3 |
| 무탐지 사례 | 64 | 67 | +3 |
| 전체 Finding | 136 | 126 | -10 |
| 오류 | 0 | 0 | +0 |

## 심각도 변화

| Severity | 기존 | Spec | 변화 |
|---|---:|---:|---:|
| `critical` | 39 | 37 | -2 |
| `high` | 62 | 57 | -5 |
| `medium` | 32 | 30 | -2 |
| `low` | 3 | 2 | -1 |
| `info` | 0 | 0 | +0 |

## Category 변화

| Category | 기존 | Spec | 변화 |
|---|---:|---:|---:|
| `hidden_instruction` | 43 | 41 | -2 |
| `obfuscation.base64` | 3 | 2 | -1 |
| `obfuscation.url_encoding` | 3 | 2 | -1 |
| `obfuscation.zero_width_unicode` | 8 | 7 | -1 |
| `semantic_similarity.hidden_instruction` | 22 | 19 | -3 |
| `tool_poisoning.obfuscated_hidden_instruction` | 28 | 26 | -2 |

## 탐지 사례 변화

- 기존에만 탐지된 사례: 3개
- Spec에서 새로 추가된 사례: 0개
- 공통 탐지 사례 중 finding 수가 변한 사례: 0개

### 기존에만 탐지된 사례

| 사례 | 경로 | 기존 finding 수 | 기존 finding 위치 | 해석 |
|---|---|---:|---|---|
| `LAB-034` / `LAB-034-meta-poisoning` | `vulnerable-lab/expanded-112/LAB-034-meta-poisoning/tools.json` | 1 | `meta.operator_note` | spec 경계 밖 필드 기반 finding 제거 |
| `LAB-077` / `LAB-077-unicode-tag-meta-instruction` | `vulnerable-lab/expanded-112/LAB-077-unicode-tag-meta-instruction/tools.json` | 6 | `_meta.operator_note, _meta.operator_note|normalized:unicode, meta.operator_note` | spec 경계 밖 필드 기반 finding 제거 |
| `LAB-081` / `LAB-081-nested-base64-meta-rug-pull-note` | `vulnerable-lab/expanded-112/LAB-081-nested-base64-meta-rug-pull-note/tools.json` | 3 | `_meta.operator_note, _meta.operator_note|decoded:base64|url_encoding` | spec 경계 밖 필드 기반 finding 제거 |

## 주의: fingerprint ID 비교 제외

일부 obfuscation finding ID는 fingerprint 기반이라 보고서를 다시 생성하면 같은 위치/같은 의미의 finding도 ID suffix가 달라질 수 있습니다. 그래서 이 비교 보고서는 개별 fingerprint ID의 추가/삭제를 핵심 지표로 보지 않고, 사례 수, finding 수, category/severity 분포, 그리고 spec 적용으로 완전히 빠진 사례를 중심으로 비교했습니다.

## 해석

- 탐지 사례는 48개에서 45개로 3개 줄었고, 전체 finding은 136개에서 126개로 10개 줄었습니다.
- 줄어든 3개 사례는 `LAB-034`, `LAB-077`, `LAB-081`이며 모두 `_meta/meta` 계열 위치에 의존하던 케이스입니다.
- category 감소도 `semantic_similarity.hidden_instruction`, `hidden_instruction`, `obfuscation.*`, `tool_poisoning.obfuscated_hidden_instruction`에서 발생했는데, 이는 `_meta/meta`와 그 안의 난독화/canonical text 재검사가 spec 경계에서 제외됐기 때문입니다.
- 공통 탐지 사례 45개는 finding 수가 유지됐습니다. 즉 `description`, `title`, `inputSchema/outputSchema`의 `description/title`, `annotations` 기반 핵심 MCP03 탐지는 유지됐습니다.
- 따라서 이번 변화는 탐지 엔진이 약해졌다기보다, MCP03의 설명 가능한 표준 공격면으로 판정 범위를 좁힌 개선으로 보는 것이 맞습니다.
