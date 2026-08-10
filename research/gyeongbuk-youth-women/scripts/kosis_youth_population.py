#!/usr/bin/env python3
"""KOSIS Open API 연동 스크립트 — 경북 18개 시군 x 5세 연령구간 x 성별 인구 조회

경북 청년여성 지역정주 연구 2-1절(인구구조와 성별 비교) 보완용.
사용법 및 사전 준비사항은 scripts/README.md 를 반드시 먼저 읽을 것.

이 스크립트는 통계표 ID(TBL_ID)와 분류코드(REGION_CODES 등)를 하드코딩하지
않는다. KOSIS 통계표마다 분류체계가 다르고, 잘못된 표 ID로 조회하면 결과가
"그럴듯하지만 틀린" 값이 되어 연구 데이터를 오염시키기 때문이다. 반드시
KOSIS_config.json 에 실제 값을 채운 뒤 실행한다.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
CONFIG_PATH = Path(__file__).parent / "kosis_config.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "gyeongbuk_youth_population_by_sex_age.csv"

# 5세 단위 청년 연령구간 (청년기본법 확장 정의, 19~39세 기준)
AGE_BRACKETS = ["19-24", "25-29", "30-34", "35-39"]

# 경북 18개 시군 (2025년 기준 행정구역명 — KOSIS 코드값은 kosis_config.json에서 매핑)
GYEONGBUK_DISTRICTS = [
    "포항시", "경주시", "김천시", "안동시", "구미시", "영주시", "영천시",
    "상주시", "문경시", "경산시",
    "군위군", "의성군", "청송군", "영양군", "영덕군", "청도군", "고령군",
    "성주군", "칠곡군", "예천군", "봉화군", "울진군", "울릉군",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"[오류] 설정 파일이 없습니다: {CONFIG_PATH}\n"
            "kosis_config.example.json 을 kosis_config.json 으로 복사한 뒤 "
            "실제 API 키와 통계표 코드를 채워 넣으세요. (scripts/README.md 참고)"
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    required = ["apiKey", "orgId", "tblId", "objL1_map", "objL2_sex_map", "objL3_age_map", "itmId"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        sys.exit(f"[오류] kosis_config.json에 다음 항목이 비어 있습니다: {missing}")
    return config


def fetch_one(config: dict, region_code: str, sex_code: str, age_code: str) -> list[dict]:
    params = {
        "method": "getList",
        "apiKey": config["apiKey"],
        "orgId": config["orgId"],
        "tblId": config["tblId"],
        "objL1": region_code,
        "objL2": sex_code,
        "objL3": age_code,
        "itmId": config["itmId"],
        "format": "json",
        "jsonVD": "Y",
        "prdSe": config.get("prdSe", "Y"),
        "startPrdDe": config.get("startPrdDe", ""),
        "endPrdDe": config.get("endPrdDe", ""),
    }
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"  [경고] 요청 실패 (region={region_code}, sex={sex_code}, age={age_code}): {e}", file=sys.stderr)
        return []

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  [경고] JSON 파싱 실패, 응답 원문: {body[:300]}", file=sys.stderr)
        return []

    if isinstance(data, dict) and "err" in data:
        print(f"  [경고] KOSIS API 오류: {data}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    config = load_config()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for district in GYEONGBUK_DISTRICTS:
        region_code = config["objL1_map"].get(district)
        if not region_code:
            print(f"  [경고] '{district}'의 KOSIS 지역코드가 kosis_config.json에 없습니다. 건너뜀.", file=sys.stderr)
            continue
        for sex_name, sex_code in config["objL2_sex_map"].items():
            for age_name, age_code in config["objL3_age_map"].items():
                if age_name not in AGE_BRACKETS:
                    continue
                result = fetch_one(config, region_code, sex_code, age_code)
                for item in result:
                    rows.append(
                        {
                            "시군": district,
                            "성별": sex_name,
                            "연령구간": age_name,
                            "시점": item.get("PRD_DE", ""),
                            "인구수": item.get("DT", ""),
                            "단위": item.get("UNIT_NM", ""),
                        }
                    )
                time.sleep(0.2)  # KOSIS API 호출 간격 제한 대응

    if not rows:
        sys.exit("[오류] 수집된 데이터가 없습니다. kosis_config.json의 코드값을 다시 확인하세요.")

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["시군", "성별", "연령구간", "시점", "인구수", "단위"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"완료: {len(rows)}건 저장 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
