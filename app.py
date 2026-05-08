import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 통합 관리 시스템", page_icon="🌱", layout="wide")
st.title("🌱 유년부 통합 관리 시스템 v13.0 (Streamlit)")

# ★ 아까 만드신 Apps Script 징검다리 주소
GOOGLE_PROXY_URL = "여기에_복사해둔_웹앱_URL을_넣으세요"

# --- 2. 구글 시트 연결 (Streamlit Secrets 사용) ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    # GitHub에 비밀번호가 노출되지 않도록 Streamlit의 보안 기능(secrets)을 사용합니다.
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

try:
    client = init_connection()
    # 구글 시트 ID (기존과 동일)
    sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"
    worksheet = client.open_by_key(sheet_id).worksheet("교적부")
except Exception as e:
    st.error(f"구글 시트 연결 실패. Secrets 설정을 확인하세요! 에러: {e}")
    st.stop()

# --- 3. 화면 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📋 교적부 명단", "➕ 새 친구 등록", "📊 출석 통계 (준비중)"])

# [탭 1] 교적부 명단 보기
with tab1:
    st.subheader("현재 등록된 명단")
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("등록된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"데이터를 불러오는 중 에러가 발생했습니다: {e}")

# [탭 2] 새 친구 등록 및 사진 업로드 테스트
with tab2:
    st.subheader("새 친구 정보 및 사진 등록")
    with st.form("new_member_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("이름")
            grade = st.selectbox("소속 (반)", ["1-1", "1-2", "1-3", "2-1", "교사", "새친구"])
        with col2:
            phone = st.text_input("연락처")
            uploaded_file = st.file_uploader("사진 업로드", type=["jpg", "jpeg", "png"])
        
        submit_button = st.form_submit_button("등록하기")

    if submit_button:
        if not name:
            st.warning("이름을 입력해주세요!")
        else:
            photo_url = ""
            # 사진이 업로드 되었다면 구글 징검다리로 전송
            if uploaded_file is not None:
                with st.spinner("구글 드라이브에 사진 업로드 중..."):
                    file_bytes = uploaded_file.getvalue()
                    base64_encoded = base64.b64encode(file_bytes).decode("utf-8")
                    
                    payload = {
                        "fileName": uploaded_file.name,
                        "mimeType": uploaded_file.type,
                        "base64Data": base64_encoded
                    }
                    
                    response = requests.post(GOOGLE_PROXY_URL, json=payload)
                    res_data = response.json()
                    
                    if res_data.get("success"):
                        photo_url = res_data.get("fileUrl")
                        st.success("사진 업로드 성공!")
                    else:
                        st.error("사진 업로드 실패!")

            # 구글 시트에 데이터 저장 로직 (간단화)
            new_row = ["", grade, name, photo_url, "", "", "", phone]
            worksheet.append_row(new_row)
            st.success(f"{name} 등록 완료! 명단 탭을 확인하세요.")