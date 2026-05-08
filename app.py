import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 관리 v17.0", page_icon="🌱", layout="wide")

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 함수 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"

def get_data():
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("교적부")
        all_values = ws.get_all_values()
        if len(all_values) <= 1: return ws, pd.DataFrame(), []
            
        headers = all_values[0]
        df = pd.DataFrame(all_values[1:], columns=headers)
        df['sheet_row'] = range(2, len(df) + 2) # 시트 행 번호 유지
        
        # 컬럼명 매핑
        rename_dict = {'학년(담임)': '반', '부모(아빠/엄마)': '부모님', '비고': '등록일/기타'}
        df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns}, inplace=True)
        
        return ws, df, headers
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, pd.DataFrame(), []

ws, df, headers = get_data()

# --- 3. 공통 함수: 사진 업로드 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={
            "fileName": f"{name}_{file.name}", 
            "mimeType": file.type, 
            "base64Data": b64
        }).json()
        return res.get("fileUrl", "")
    except:
        return ""

# --- 4. 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["✅ 출석 체크", "📋 교적부 관리", "🏫 통계/기타"])

# ==========================================
# [탭 1] 출석 체크 (헤더 매칭 강화)
# ==========================================
with tab1:
    st.subheader("📅 주일 출석")
    
    # 주차/날짜 생성
    start_date = datetime.date(2026, 1, 4)
    weeks = [f"{i}주차" for i in range(1, 53)]
    week_map = {f"{i}주차": (start_date + datetime.timedelta(days=(i-1)*7)).strftime('%m/%d') for i in range(1, 53)}
    
    curr_week = datetime.date.today().isocalendar()[1] - 1
    sel_w = st.selectbox("주차 선택", weeks, index=max(0, min(51, curr_week)), 
                         format_func=lambda x: f"{x} ({week_map[x]})")

    # 시트 헤더에서 선택된 주차 컬럼 찾기 (공백/문자 무시 검색)
    target_col_idx = -1
    for i, h in enumerate(headers):
        if sel_w.strip() in h.strip():
            target_col_idx = i + 1
            break
    
    if target_col_idx == -1:
        st.error(f"⚠️ 구글 시트 첫 줄에서 '{sel_w}'을(를) 찾을 수 없습니다. 시트의 제목을 확인해 주세요!")
    else:
        classes = ["전체"] + sorted([c for c in df['반'].unique() if c])
        sel_class = st.selectbox("반 필터", classes)
        
        att_df = df[df['상태'] != '이사'].copy()
        if sel_class != "전체": att_df = att_df[att_df['반'] == sel_class]
        att_df['출석'] = att_df[headers[target_col_idx-1]].apply(lambda x: True if str(x).strip() == "1" else False)

        edited_att = st.data_editor(
            att_df[['반', '이름', '출석']],
            use_container_width=True, hide_index=True,
            column_config={"출석": st.column_config.CheckboxColumn("출석")}
        )
        
        if st.button("💾 출석 결과 저장", type="primary", use_container_width=True):
            with st.spinner("시트에 기록 중..."):
                for i in range(len(att_df)):
                    if att_df.iloc[i]['출석'] != edited_att.iloc[i]['출석']:
                        ws.update_cell(att_df.iloc[i]['sheet_row'], target_col_idx, "1" if edited_att.iloc[i]['출석'] else "")
                st.success("출석 저장 완료!")
                st.rerun()

# ==========================================
# [탭 2] 교적부 관리 (수정/저장/등록 완벽 연동)
# ==========================================
with tab2:
    st.subheader("📋 교적부 편집")
    st.info("💡 표 안의 내용을 수정(더블클릭)한 후 반드시 아래 [수정 내용 저장] 버튼을 누르세요.")
    
    # 에디터 표시용 컬럼 정리
    display_cols = [c for c in ['반', '이름', '상태', '연락처', '부모님', '주소', '등록일/기타', '사진'] if c in df.columns]
    
    # 1. 수정 에디터
    edited_data = st.data_editor(
        df[display_cols],
        use_container_width=True, hide_index=True,
        column_config={"사진": st.column_config.ImageColumn("사진"), "상태": st.column_config.SelectboxColumn("상태", options=["일반", "새친구", "이사", "교사"])}
    )
    
    if st.button("💾 수정 내용 저장", use_container_width=True):
        with st.spinner("시트 업데이트 중..."):
            # 바뀐 데이터프레임 전체를 시트에 덮어쓰기 (가장 확실한 방법)
            new_values = edited_data.values.tolist()
            # 헤더 제외한 영역 업데이트 (예: A2부터)
            ws.update(f"A2", new_values)
            st.success("전체 수정 사항이 시트에 반영되었습니다!")
            st.rerun()

    st.markdown("---")
    
    # 2. 신규 등록 (새친구 포함)
    with st.expander("➕ 신규 인원/새친구 등록", expanded=False):
        with st.form("new_friend_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                f_name = st.text_input("이름")
                f_class = st.text_input("반 (예: 1-1(홍길동))")
                f_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"], index=1)
            with c2:
                f_phone = st.text_input("연락처")
                f_birth = st.text_input("생년월일")
                f_photo = st.file_uploader("사진", type=["jpg", "png"])
            
            if st.form_submit_button("✨ 정보 등록하기", use_container_width=True):
                if not f_name: st.error("이름은 필수입니다."); st.stop()
                
                photo_url = upload_photo(f_photo, f_name)
                # 시트 헤더 순서대로 데이터 구성 (중요!)
                new_row = [""] * len(headers)
                h_map = {h: i for i, h in enumerate(headers)}
                
                # 시트 실제 제목에 맞춰 매칭
                if '이름' in h_map: new_row[h_map['이름']] = f_name
                if '반' in h_map: new_row[h_map['반']] = f_class
                elif '학년(담임)' in h_map: new_row[h_map['학년(담임)']] = f_class
                if '상태' in h_map: new_row[h_map['상태']] = f_status
                if '연락처' in h_map: new_row[h_map['연락처']] = f_phone
                if '생년월일' in h_map: new_row[h_map['생년월일']] = f_birth
                if '사진' in h_map: new_row[h_map['사진']] = photo_url
                
                ws.append_row(new_row)
                st.success(f"{f_name}님이 등록되었습니다!")
                st.rerun()

# ==========================================
# [탭 3] 통계/반편성
# ==========================================
with tab3:
    st.subheader("🏫 반별 인원")
    if not df.empty:
        grouped = df.groupby('반')
        for name, group in grouped:
            with st.expander(f"{name} ({len(group)}명)"):
                st.write(", ".join(group['이름'].tolist()))
