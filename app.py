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
        ws = sh.worksheet("교적부")
        rows = ws.get_all_records()
        return ws, rows
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return None, []

worksheet, data = get_data()

# --- 4. 화면 구성 ---
st.title("🌱 유년부 통합 관리 시스템")

tab1, tab2 = st.tabs(["📋 교적부 명단", "➕ 새 친구 등록"])

with tab1:
    st.subheader("현재 등록된 명단")
    if data:
        df = pd.DataFrame(data)
        
        # ★ 파이썬에게 '사진' 열을 이미지로 보여달라고 명령하는 부분!
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True, # 쓸데없는 맨 앞 번호(0,1,2...) 숨기기
            column_config={
                "사진": st.column_config.ImageColumn(
                    "사진 (프로필)", help="학생 사진입니다."
                )
            }
        )
    else:
        st.warning("데이터가 없습니다.")
        if st.button("새로고침"):
            st.rerun()

with tab2:
    st.subheader("새 친구 등록 (사진 포함)")
    with st.form("upload_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("이름")
            grade = st.selectbox("반", ["1-1", "1-2", "1-3", "2-1", "2-2", "2-3", "3-1", "3-2", "3-3", "교사", "새친구"])
        with col2:
            uploaded_file = st.file_uploader("사진 선택", type=["jpg", "png", "jpeg"])
            submit = st.form_submit_button("등록 완료")

        if submit:
            if not name:
                st.warning("이름을 입력해주세요!")
            else:
                photo_url = ""
                if uploaded_file:
                    with st.spinner("구글 드라이브에 사진 저장 중..."):
                        b64 = base64.b64encode(uploaded_file.getvalue()).decode()
                        payload = {"fileName": uploaded_file.name, "mimeType": uploaded_file.type, "base64Data": b64}
                        try:
                            res = requests.post(GOOGLE_PROXY_URL, json=payload).json()
                            if res.get("success"):
                                photo_url = res.get("fileUrl")
                                st.success("사진 업로드 완료!")
                            else:
                                st.error("사진 업로드 실패!")
                        except Exception as e:
                            st.error(f"통신 에러: {e}")
                
                # 구글 시트에 저장
                try:
                    # 빈칸들은 엑셀 표 순서에 맞춰야 합니다. (번호, 학년(담임), 이름, 사진, 생년월일, 주소...)
                    worksheet.append_row(["", grade, name, photo_url])
                    st.success(f"{name} 학생 정보가 등록되었습니다! 명단 탭을 확인하세요.")
                except Exception as e:
                    st.error(f"시트 저장 에러: {e}")
