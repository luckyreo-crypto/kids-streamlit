import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
from datetime import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 통합 관리 시스템", page_icon="🌱", layout="wide")

# 시크릿에서 징검다리 주소 가져오기
if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 및 데이터 로드 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"

def get_data():
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("교적부")
        rows = ws.get_all_records()
        df = pd.DataFrame(rows)
        
        # ★ 구글 시트의 실제 제목을 파이썬 코드의 기준에 맞게 번역(이름 변경)합니다.
        df.rename(columns={
            '학년(담임)': '반',
            '부모(아빠/엄마)': '부모님',
            '비고': '등록일/기타'
        }, inplace=True)
        
        return ws, df
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return None, pd.DataFrame()
ws, df = get_data()

# --- 3. 헤더 영역 ---
st.title("🌱 유년부 통합 관리 시스템 v13.0")
st.markdown("---")

if df.empty:
    st.warning("구글 시트에 데이터가 없거나 불러오지 못했습니다.")
    st.stop()

# --- 4. 화면 탭 구성 ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "01. 출석 체크", "02. 교적부 관리", "03. 반편성 현황", "04. 월별 생일표", "05. 새친구 목록"
])

# ==========================================
# [탭 1] 출석 체크
# ==========================================
with tab1:
    st.subheader("📅 주일 출석 체크")
    
    # 주차 계산 (단순화: 1~52주차 선택)
    weeks = [f"{i}주차" for i in range(1, 53)]
    
    colA, colB, colC = st.columns(3)
    with colA:
        selected_week = st.selectbox("주차 선택", weeks)
    with colB:
        class_list = ["전체보기"] + sorted(list(df['반'].unique()))
        selected_class = st.selectbox("반 필터", class_list)
    with colC:
        search_name = st.text_input("이름 검색", "")

    # 필터링 적용
    view_df = df.copy()
    if selected_class != "전체보기":
        view_df = view_df[view_df['반'] == selected_class]
    if search_name:
        view_df = view_df[view_df['이름'].str.contains(search_name)]
    
    # 이사/퇴소자 제외
    if '상태' in view_df.columns:
        view_df = view_df[view_df['상태'] != '이사']

    st.write(f"조회 인원: **{len(view_df)}명**")
    
    # 출석 체크 리스트 (모바일 친화적인 형태로 출력)
    if not view_df.empty:
        for idx, row in view_df.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([1, 3, 2])
                c1.write(f"**{row['반']}**")
                
                # 새친구 표시
                name_display = f"🔴 {row['이름']}" if row.get('상태') == '새친구' else row['이름']
                c2.write(f"**{name_display}**")
                
                # 체크박스로 출석 여부 표시 (구글 시트 연동은 속도 문제로 일단 UI만 구현, 추후 버튼으로 업데이트 구현 필요)
                # 현재는 구글 시트에 "1주차", "2주차" 컬럼이 있다고 가정합니다.
                is_attended = False
                if selected_week in row and str(row[selected_week]).strip() == "1":
                    is_attended = True
                
                c3.checkbox("출석", value=is_attended, key=f"att_{idx}_{selected_week}", disabled=True)
                st.divider()
        st.info("💡 실시간 출석 체크 연동은 '수정' 기능과 함께 다음 단계에서 적용됩니다.")

# ==========================================
# [탭 2] 교적부 관리 (명단 + 추가)
# ==========================================
with tab2:
    st.subheader("📋 전체 교적부 명단")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "사진": st.column_config.ImageColumn("사진", help="학생 사진")
        }
    )
    
    with st.expander("✨ 새 친구 / 인원 정보 등록하기", expanded=False):
        with st.form("upload_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"])
                new_grade = st.selectbox("반", class_list[1:] if len(class_list)>1 else ["1-1", "1-2", "2-1"])
                new_name = st.text_input("이름")
                new_birth = st.text_input("생년월일 (예: 19.02.26)")
                new_phone = st.text_input("연락처")
            with col2:
                new_parents = st.text_input("부모님")
                new_address = st.text_input("주소")
                new_memo = st.text_input("등록일/비고")
                new_evangelist = st.text_input("전도자")
                uploaded_file = st.file_uploader("사진 선택", type=["jpg", "png", "jpeg"])
                
            submit = st.form_submit_button("저장하기")

            if submit:
                if not new_name:
                    st.warning("이름을 입력해주세요!")
                else:
                    photo_url = ""
                    if uploaded_file:
                        with st.spinner("구글 드라이브에 사진 저장 중..."):
                            b64 = base64.b64encode(uploaded_file.getvalue()).decode()
                            payload = {"fileName": f"{new_name}_{uploaded_file.name}", "mimeType": uploaded_file.type, "base64Data": b64}
                            try:
                                res = requests.post(GOOGLE_PROXY_URL, json=payload).json()
                                if res.get("success"):
                                    photo_url = res.get("fileUrl")
                                    st.success("사진 업로드 완료!")
                            except Exception as e:
                                st.error("사진 업로드 실패!")
                    
                    # 시트에 저장 (구글 시트 컬럼 순서에 맞게 배열해야 합니다. 현재는 임의 배치)
                    # 번호, 반, 이름, 사진, 생년월일, 주소, 부모, 연락처, 학교, 상태, 비고, 전도자
                    try:
                        new_row = ["", new_grade, new_name, photo_url, new_birth, new_address, new_parents, new_phone, "", new_status, new_memo, new_evangelist]
                        ws.append_row(new_row)
                        st.success(f"{new_name} 등록 성공! 새로고침(F5)을 눌러 확인하세요.")
                    except Exception as e:
                        st.error(f"시트 저장 에러: {e}")

# ==========================================
# [탭 3] 반편성 현황
# ==========================================
with tab3:
    st.subheader("🏫 반편성 현황")
    st.write("※ 🔴: 새친구, ̶취̶소̶선̶: 이사")
    
    if not df.empty:
        student_df = df[(df['반'] != '교사') & (~df['반'].str.contains('테스트', na=False))]
        st.metric("총 학생 인원", f"{len(student_df)}명")
        
        # 반별로 그룹화
        grouped = df.groupby('반')
        cols = st.columns(3)
        col_idx = 0
        
        for grade, group in grouped:
            if grade == "": continue
            with cols[col_idx % 3]:
                with st.container(border=True):
                    st.markdown(f"#### {grade} (총 {len(group)}명)")
                    names = []
                    for _, row in group.iterrows():
                        n = str(row['이름'])
                        if row.get('상태') == '새친구': n = f"🔴{n}"
                        elif row.get('상태') == '이사': n = f"~{n}~"
                        names.append(n)
                    st.write(", ".join(names))
            col_idx += 1

# ==========================================
# [탭 4] 월별 생일표
# ==========================================
with tab4:
    st.subheader("🎂 월별 생일표")
    if not df.empty and '생년월일' in df.columns:
        months_data = {str(i): [] for i in range(1, 13)}
        
        for _, row in df.iterrows():
            birth = str(row.get('생년월일', ''))
            name = str(row.get('이름', ''))
            grade = str(row.get('반', ''))
            
            if birth and len(birth.split('.')) >= 3:
                try:
                    month = str(int(birth.split('.')[1]))
                    day = int(birth.split('.')[2])
                    months_data[month].append(f"**{name}** ({grade}, {day}일)")
                except:
                    pass
        
        cols = st.columns(4)
        for i in range(1, 13):
            with cols[(i-1) % 4]:
                with st.container(border=True):
                    st.markdown(f"##### {i}월")
                    if months_data[str(i)]:
                        for person in months_data[str(i)]:
                            st.write(person)
                    else:
                        st.caption("없음")

# ==========================================
# [탭 5] 새친구 목록
# ==========================================
with tab5:
    st.subheader("🌱 최근 등록된 새친구 목록")
    if not df.empty and '상태' in df.columns:
        new_friends_df = df[df['상태'] == '새친구']
        if not new_friends_df.empty:
            st.dataframe(
                new_friends_df[['등록일/기타', '반', '이름', '생년월일', '전도자', '부모님', '연락처', '주소']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("등록된 새친구가 없습니다.")
