# -*- coding: utf-8 -*-
"""
창원시 5개구(의창구·성산구·마산합포구·마산회원구·진해구) 전체
아파트 매매/전월세 실거래가 수집 스크립트
국토교통부 공공데이터포털 Open API 사용

버전: v1.2 | 수정일: 2026-11-02
(v1.2 변경: END_YM을 실행일 기준 "이번 달"로 자동 계산(매달 수정 불필요),
 인증키를 스크립트 옆 service_key.txt 또는 환경변수 CHANGWON_API_KEY에서 읽음(스크립트 본문에 키 보관 불필요),
 CSV를 스크립트와 같은 폴더에 저장)
(v1.1 변경: 타임아웃 15초→40초 연장, 타임아웃 시 5초 간격 최대 3회 재시도 추가,
 END_YM 202607→202608 갱신, 종료 시 오류 발생 건 요약 출력)

사용 전 준비:
  pip install requests pandas

사용 방법:
  1. 스크립트와 같은 폴더에 service_key.txt 파일을 만들고 공공데이터포털 "일반 인증키(Encoding)"를
     한 줄로 넣으세요. (또는 환경변수 CHANGWON_API_KEY, 또는 아래 SERVICE_KEY 상수에 직접 입력)
  2. END_YM은 실행하는 달로 자동 설정됩니다. 기간을 바꾸려면 START_YM / END_YM_OVERRIDE만 수정.
  3. 실행: python changwon_all_collect_v1.2.py
  4. 완성된 CSV 두 개 (매매/전월세, 5개구 전체 + "구" 컬럼 포함)를 Claude에게 업로드하면
     구별 비교까지 포함한 창원시 전체 리포트를 만들어줍니다.

※ 창원시 5개구 x 개월 수 x 2종 API를 순차 호출하므로, 2년치 기준으로 몇 분 정도 걸릴 수 있습니다.
"""

import requests
import xml.etree.ElementTree as ET
import pandas as pd
import time
import os
from datetime import datetime

# ====== 설정 ======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_KEY = "여기에_발급받은_인증키_붙여넣기"  # (선택) 직접 입력. service_key.txt / 환경변수가 있으면 그쪽을 우선 사용
START_YM = "202401"       # 조회 시작월 (YYYYMM)
END_YM_OVERRIDE = ""      # 비워 두면 실행일이 속한 달(이번 달)로 자동 설정. 특정 달까지만 원하면 "202610"처럼 지정


def load_service_key():
    """우선순위: 환경변수 CHANGWON_API_KEY > 스크립트 옆 service_key.txt > SERVICE_KEY 상수"""
    env = os.environ.get("CHANGWON_API_KEY", "").strip()
    if env:
        return env
    key_path = os.path.join(BASE_DIR, "service_key.txt")
    if os.path.exists(key_path):
        with open(key_path, encoding="utf-8") as f:
            k = f.read().strip()
            if k:
                return k
    return SERVICE_KEY


SERVICE_KEY = load_service_key()
END_YM = END_YM_OVERRIDE or datetime.now().strftime("%Y%m")  # v1.2: 이번 달 자동

# 창원시 5개구 법정동코드(시군구코드)
GU_LIST = {
    "의창구": "48121",
    "성산구": "48123",
    "마산합포구": "48125",
    "마산회원구": "48127",
    "진해구": "48129",
}

TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
RENT_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

# 오류 발생 건 기록용 (구, 연월, 종류)
FAILED = []


def month_range(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    months = []
    while (y, m) <= (ey, em):
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def fetch_xml(url, lawd_cd, deal_ymd, page_no=1, num_of_rows=1000):
    params = {
        "serviceKey": SERVICE_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    for attempt in range(3):  # 최대 3회 시도
        try:
            resp = requests.get(url, params=params, timeout=40)  # v1.1: 15초 → 40초
            resp.raise_for_status()
            return resp.text
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 2:
                print(f"    [재시도 {attempt + 1}/2] {deal_ymd} 응답 지연, 5초 후 재시도")
                time.sleep(5)
            else:
                raise


def parse_items(xml_text):
    root = ET.fromstring(xml_text)
    header = root.find("./header")
    result_code = header.findtext("resultCode") if header is not None else None
    if result_code not in (None, "00", "000"):
        result_msg = header.findtext("resultMsg")
        print(f"    [경고] API 응답 코드 {result_code}: {result_msg}")
        return []
    items = root.findall("./body/items/item")
    rows = []
    for item in items:
        row = {child.tag: (child.text or "").strip() for child in item}
        rows.append(row)
    return rows


def collect(url, months, label):
    all_rows = []
    for gu_name, lawd_cd in GU_LIST.items():
        print(f"[{label}] {gu_name}({lawd_cd}) 수집 시작")
        for ym in months:
            try:
                xml_text = fetch_xml(url, lawd_cd, ym)
                rows = parse_items(xml_text)
                for r in rows:
                    r["DEAL_YMD"] = ym
                    r["구"] = gu_name
                    r["LAWD_CD"] = lawd_cd
                all_rows.extend(rows)
                print(f"  {ym} -> {len(rows)}건")
            except Exception as e:
                print(f"  [오류] {gu_name} {ym} 조회 실패: {e}")
                FAILED.append((label, gu_name, ym))
            time.sleep(0.25)  # 과도한 호출 방지
    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    if SERVICE_KEY.startswith("여기에"):
        print("!! 인증키가 없습니다. 스크립트 옆 service_key.txt에 키를 넣거나 환경변수 CHANGWON_API_KEY를 설정하세요 !!")
        exit(1)
    print(f"조회 기간: {START_YM} ~ {END_YM} (END_YM 자동 설정)")

    months = month_range(START_YM, END_YM)

    print("=== 창원시 5개구 아파트 매매 실거래가 수집 시작 ===")
    df_trade = collect(TRADE_URL, months, "매매")
    trade_path = os.path.join(BASE_DIR, "changwon_all_apt_trade.csv")
    df_trade.to_csv(trade_path, index=False, encoding="utf-8-sig")
    print(f"매매 데이터 저장 완료: {trade_path} ({len(df_trade)}행)\n")

    print("=== 창원시 5개구 아파트 전월세 실거래가 수집 시작 ===")
    df_rent = collect(RENT_URL, months, "전월세")
    rent_path = os.path.join(BASE_DIR, "changwon_all_apt_rent.csv")
    df_rent.to_csv(rent_path, index=False, encoding="utf-8-sig")
    print(f"전월세 데이터 저장 완료: {rent_path} ({len(df_rent)}행)\n")

    # v1.1: 오류 요약 — 여기 뜨는 달은 CSV에서 빠져 있으므로 재실행 필요
    if FAILED:
        print(f"!! 주의: 3회 재시도에도 실패한 조회 {len(FAILED)}건 — 아래 달은 CSV에 빠져 있음 !!")
        for label, gu, ym in FAILED:
            print(f"  - [{label}] {gu} {ym}")
        print("시간대를 바꿔 전체 재실행을 권장합니다.")
    else:
        print("모든 달 수집 성공 (누락 없음).")

    print("\n완료! 아래 두 파일을 Claude에게 업로드해주세요:")
    print(f"  - {trade_path}")
    print(f"  - {rent_path}")
