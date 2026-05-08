import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 CSS 주입 (모바일 최적화) ---
st.set_page_config(page_title="유년부 통합 관리 시스템", page_icon="🌱", layout="wide")

# 모바일 UI 개선을 위한 커스텀 스타일
st.markdown("""
    <style>
    .stCheckbox { transform: scale(1.5); margin-bottom: 10px; }
    .attendance-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #ddd;
        margin-bottom: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .stat-text { font-size: 0.8rem; color: #666; }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"

def get_all_data():
    try:
        sh = client.open_by_key(sheet_id)
        # 교적부 데이터
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        df_m = pd.DataFrame(vals[1:], columns=vals[0]) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        # 활동기록 데이터
        try:
            ws_a = sh.worksheet("활동기록")
        except:
            ws_a = sh.add_worksheet(title="활동기록", rows="500", cols="10")
            ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
        
        a_vals = ws_a.get_all_values()
        df_a = pd.DataFrame(a_vals[1:], columns=a_vals[0]) if len(a_vals) > 1 else pd.DataFrame()
        
        return ws_m, df_m, vals[0], ws_a, df_a
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame()

ws, df, headers, ws_act, df_act = get_all_data()

# --- 3. 함수: 사진 업로드 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except: return ""

# --- 4. 주차 설정 ---
weeks_list = [f"{i}주" for i in range(1, 53)]

# --- 5. 탭 구성 ---
tabs = st.tabs(["✅ 출석체크", "📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사관리"])

# ==========================================
# [탭 1] 출석체크 (개인별 52주 통계 포함)
# ==========================================
with tabs[0]:
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    sel_w = st.selectbox("📅 주차 선택", weeks_list, index=max(0, min(51, curr_week_idx)))
    
    # 반 필터링
    class_col = '학년(담임)' if '학년(담임)' in df.columns else '반'
    classes = ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()])
    sel_class = st.selectbox("🏫 반 선택", classes)

    target_df = df[df['상태'] != '이사'].copy()
    if sel_class != "전체보기": target_df = target_df[target_df[class_col] == sel_class]

    # 통계 계산 (52주 출석률)
    def calc_stats(row):
        att_values = [row.get(f"{i}주", "") for i in range(1, 53)]
        present_count = att_values.count("1")
        rate = int((present_count / 52) * 100)
        return present_count, rate

    st.write(f"### {sel_w} 명단 ({len(target_df)}명)")
    
    with st.form("attendance_form"):
        new_att = {}
        # 화면에 약 6명 정도가 큼직하게 보이도록 구성
        for _, row in target_df.iterrows():
            count, rate = calc_stats(row)
            is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
            
            # 카드형 UI
            with st.container():
                col1, col2 = st.columns([3, 1])
                name_tag = "🔴 " if row.get('상태') == '새친구' else ""
                col1.markdown(f"**{name_tag}{row['이름']}** ({row[class_col]})")
                col1.markdown(f"<p class='stat-text'>누적: {count}회 / 출석률: {rate}%</p>", unsafe_allow_html=True)
                new_att[row['sheet_row']] = col2.checkbox("출석", value=is_on, key=f"att_{row['sheet_row']}")
                st.markdown("---")
        
        if st.form_submit_button("💾 출석 정보 일괄 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                col_idx = headers.index(sel_w) + 1
                for r_idx, val in new_att.items():
                    ws.update_cell(r_idx, col_idx, "1" if val else "")
                st.success(f"{sel_w} 저장 완료!")
                st.rerun()

# ==========================================
# [탭 3] 생일표 (이름, 반, 생일 표시)
# ==========================================
with tabs[3]:
    st.subheader("🎂 월별 생일 명단")
    if '생년월일' in df.columns:
        # 월별로 데이터 분류
        months = {str(i): [] for i in range(1, 13)}
        for _, r in df.iterrows():
            b = str(r['생년월일'])
            if len(b.split('.')) >= 3:
                m = str(int(b.split('.')[1]))
                d = str(int(b.split('.')[2]))
                months[m].append({"이름": r['이름'], "반": r.get(class_col, "-"), "날짜": f"{d}일"})
        
        cols = st.columns(3)
        for i in range(1, 13):
            with cols[(i-1)%3]:
                with st.container(border=True):
                    st.markdown(f"#### 📅 {i}월")
                    if months[str(i)]:
                        for p in months[str(i)]:
                            st.write(f"**{p['이름']}** ({p['반']}) - {p['날짜']}")
                    else:
                        st.caption("생일자 없음")

# ==========================================
# [탭 6] 행사관리 (기존 정보 가시화)
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 활동 기록")
    
    # 1. 새 활동 입력
    with st.expander("➕ 새 활동 기록 추가", expanded=False):
        with st.form("act_add"):
            a_date = st.date_input("날짜", datetime.date.today())
            a_title = st.text_input("활동명")
            a_desc = st.text_area("세부내용")
            a_note = st.text_area("공지사항")
            a_files = st.file_uploader("사진 (최대 4장)", accept_multiple_files=True)
            if st.form_submit_button("저장"):
                urls = ["", "", "", ""]
                for i, f in enumerate(a_files[:4]):
                    urls[i] = upload_photo(f, f"event_{a_title}_{i}")
                ws_act.append_row([str(a_date), a_title, a_desc, a_note, urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                st.success("기록 완료!")
                st.rerun()

    st.markdown("---")
    
    # 2. 기존 정보 출력 (이 부분 보강)
    st.write("📂 **과거 활동 기록 내역**")
    if not df_act.empty:
        # 최신순 정렬
        for _, row in df_act[::-1].iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                c1.info(f"**{row['날짜']}**")
                with c2:
                    st.markdown(f"### {row['활동명']}")
                    st.write(f"**상세:** {row['세부내용']}")
                    if row['공지사항']:
                        st.warning(f"**공지:** {row['공지사항']}")
                    
                    # 사진 표시
                    p_cols = st.columns(4)
                    for i in range(1, 5):
                        p_url = row.get(f"사진{i}", "")
                        if p_url and p_url.startswith("http"):
                            p_cols[i-1].image(p_url, use_container_width=True)
    else:
        st.info("아직 저장된 행사 기록이 없습니다.")

# 나머지 탭(교적부, 반편성, 새친구)은 기존의 안정적인 코드를 유지합니다.
