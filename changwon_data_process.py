# -*- coding: utf-8 -*-
"""
창원 실거래가 원본 CSV 2개 → 리포트용 경량 데이터 4개 생성 스크립트 (Claude 세션 내부용)

사용 상황: 사용자가 changwon_all_apt_trade.csv / changwon_all_apt_rent.csv 를 대화에 업로드하고
"프로젝트 데이터 갱신"을 요청하면, Claude가 이 스크립트를 실행한 뒤
생성된 4개 파일을 project_write(local_path)로 프로젝트 문서에 덮어쓴다.

실행: python3 changwon_data_process.py <trade_csv경로> <rent_csv경로> <기준일 YYYY-MM-DD> <출력폴더>

저장 대상 프로젝트 문서 경로 (덮어쓰기):
  claude/data/changwon_주요단지_매매.csv
  claude/data/changwon_주요단지_전월세.csv
  claude/data/changwon_구별_월별집계.csv
  claude/data/changwon_성산구_동별_월별집계.csv

변경 이력: 2026-09-20 — 주요단지 필터에 '창원 센트럴 아이파크'(성산구 신월동, 신월2구역 재건축,
1,509세대, 2026-09 입주) 추가(사용자 요청). 국토부 aptNm 표기 확정 전이라 정규식
"센트럴\\s*아이파크"로 매칭 — 실거래 등록 후 표기 확인 요망.
"""
import sys
import pandas as pd, numpy as np

trade_path, rent_path, BASIS, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].rstrip("/") + "/"

t = pd.read_csv(trade_path, dtype=str)
r = pd.read_csv(rent_path, dtype=str)

ym_min, ym_max = t["DEAL_YMD"].min(), t["DEAL_YMD"].max()

# 해제거래 제외
n_cancel = (t["cdealType"] == "O").sum()
t = t[t["cdealType"] != "O"].copy()

def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")

t["amt"] = num(t["dealAmount"])          # 만원
t["ar"] = num(t["excluUseAr"])
t["py"] = t["amt"] / (t["ar"] / 3.3058)  # 만원/평
r["dep"] = num(r["deposit"]); r["mrent"] = num(r["monthlyRent"]); r["ar"] = num(r["excluUseAr"])
r["py_jeonse"] = np.where(r["mrent"] == 0, r["dep"] / (r["ar"] / 3.3058), np.nan)

TARGETS = ["용지더샵레이크파크", "용지아이파크", "유니시티", "창원자이시그니처", r"센트럴\s*아이파크"]
def is_target(s):
    return s.str.contains("|".join(TARGETS), na=False, regex=True)

hdr = lambda desc: f"# {desc} | 기준일: {BASIS} | 기간: {ym_min}~{ym_max} | 해제거래 {n_cancel}건 제외(매매) | 금액단위: 만원\n"

cols_t = ["aptNm","dealYear","dealMonth","dealDay","dealAmount","excluUseAr","floor","umdNm","buildYear","dealingGbn","구","DEAL_YMD"]
with open(OUT + "changwon_주요단지_매매.csv", "w", encoding="utf-8") as f:
    f.write(hdr("창원 주요단지(용지더샵레이크파크·용지아이파크·유니시티1~4·창원자이시그니처·센트럴아이파크) 아파트 매매 실거래 원자료"))
    t[is_target(t["aptNm"])][cols_t].to_csv(f, index=False)

cols_r = ["aptNm","dealYear","dealMonth","dealDay","deposit","monthlyRent","excluUseAr","floor","umdNm","contractType","구","DEAL_YMD"]
with open(OUT + "changwon_주요단지_전월세.csv", "w", encoding="utf-8") as f:
    f.write(hdr("창원 주요단지 아파트 전월세 실거래 원자료"))
    r[is_target(r["aptNm"])][cols_r].to_csv(f, index=False)

g = t.groupby(["구","DEAL_YMD"]).agg(매매건수=("amt","size"), 중위매매가_만원=("amt","median"), 중위평당가_만원=("py","median"), 평균평당가_만원=("py","mean")).round(1).reset_index()
je = r[r["mrent"]==0].groupby(["구","DEAL_YMD"]).agg(전세건수=("dep","size"), 중위전세보증금_만원=("dep","median"), 중위전세평당가_만원=("py_jeonse","median")).round(1).reset_index()
wo = r[r["mrent"]>0].groupby(["구","DEAL_YMD"]).agg(월세건수=("dep","size"), 중위월세보증금_만원=("dep","median"), 중위월세_만원=("mrent","median")).round(1).reset_index()
gu = g.merge(je, on=["구","DEAL_YMD"], how="outer").merge(wo, on=["구","DEAL_YMD"], how="outer")
with open(OUT + "changwon_구별_월별집계.csv", "w", encoding="utf-8") as f:
    f.write(hdr("창원 5개구 구별×월별 매매/전세/월세 집계"))
    gu.to_csv(f, index=False)

s = t[t["구"]=="성산구"]
sd = s.groupby(["umdNm","DEAL_YMD"]).agg(매매건수=("amt","size"), 중위매매가_만원=("amt","median"), 중위평당가_만원=("py","median")).round(1).reset_index()
sj = r[(r["구"]=="성산구")&(r["mrent"]==0)].groupby(["umdNm","DEAL_YMD"]).agg(전세건수=("dep","size"), 중위전세보증금_만원=("dep","median")).round(1).reset_index()
sg = sd.merge(sj, on=["umdNm","DEAL_YMD"], how="outer")
with open(OUT + "changwon_성산구_동별_월별집계.csv", "w", encoding="utf-8") as f:
    f.write(hdr("창원 성산구 동별×월별 매매/전세 집계"))
    sg.to_csv(f, index=False)

print("완료. 4개 파일 생성:", OUT)
