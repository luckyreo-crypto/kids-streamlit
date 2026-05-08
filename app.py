import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 관리 시스템", page_icon="🌱", layout="wide")

# 시크릿에서 주소 가져오기
if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"

# --- 3. 데이터 불러오기 함수 ---
def get_data():
    try:
        sh = client.open_by_key(sheet_id)
        # '교적부' 시트 가져오기
        ws = sh.worksheet("교적부")
        # 데이터 가져오기 (헤더가 1행에 있다고 가정)
        rows = ws.get_all_records()
        return ws, rows
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return None, []

worksheet, data = get_data()

# --- 4. 화면 구성 ---
st.title("🌱 유년부 통합 관리 시스템")

tab1, tab2 = st.tabs(["📋 명단 보기", "➕ 사진 및 정보 등록"])

with tab1:
    if data:
        df = pd.DataFrame(data)
        # 불필요한 열 숨기기 또는 필터링 가능
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("데이터가 없습니다. 구글 시트의 '교적부' 탭에 내용이 있는지, 그리고 서비스 계정에 공유가 되었는지 확인해주세요.")
        if st.button("새로고침"):
            st.rerun()

with tab2:
    st.subheader("새 친구 등록 (사진 포함)")
    with st.form("upload_form"):
        name = st.text_input("이름")
        grade = st.selectbox("반", ["1-1", "1-2", "1-3", "2-1", "2-2", "2-3", "3-1", "3-2", "3-3", "교사"])
        uploaded_file = st.file_uploader("사진 선택", type=["jpg", "png", "jpeg"])
        submit = st.form_submit_button("등록")

        if submit:
            photo_url = ""
            if uploaded_file:
                with st.spinner("사진 업로드 중..."):
                    b64 = base64.b64encode(uploaded_file.getvalue()).decode()
                    payload = {"fileName": uploaded_file.name, "mimeType": uploaded_file.type, "base64Data": b64}
                    res = requests.post(GOOGLE_PROXY_URL, json=payload).json()
                    if res.get("success"):
                        photo_url = res.get("fileUrl")
                        st.success("사진 업로드 완료!")
            
            # 시트에 저장 (순서: 비고, 반, 이름, 사진URL 등 시트 구조에 맞게 수정 필요)
            worksheet.append_row(["", grade, name, photo_url])
            st.success(f"{name} 등록 성공!")
            st.rerun()
