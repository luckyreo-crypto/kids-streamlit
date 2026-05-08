import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v23.0", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .attendance-box {
        border: 1px solid #ddd;
        padding: 10px;
        border-radius: 8px;
        background-color: #f9f9f9;
        margin-bottom: 10px;
        text-align: center;
    }
    .stCheckbox { transform: scale(1.2); }
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
        # 1. 교적부 로드
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        headers = vals[0]
        df_m = pd.DataFrame(vals[1:], columns=headers) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        # 2. 활동간식 로드 (명칭 변경 반영)
        try:
            ws_a = sh.worksheet("활동간식")
        except:
            ws_a = sh.add_worksheet(title="활동간식", rows="500", cols="10")
            ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
        
        a_vals = ws_a.get_all_values()
        df_a = pd.DataFrame(a_vals[1:], columns=a_vals[0]) if len(a_vals) > 1 else pd.DataFrame()
        
        return ws_m, df_m, headers, ws_a, df_a
    except Exception as e:
        st.error(f"데이터 연동 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame()

ws, df, headers, ws_act, df_act = get_all_data()

# --- 3. 공통 함수 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except: return ""

# 컬럼명 자동 매칭 (학년(담임) -> 반 등으로 유연하게 처리)
class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')

# --- 4. 주차 및 날짜 생성 (2026년 기준) ---
start_date = datetime.date(2026, 1, 4)
weeks_list = []
week_display_map = {}
for i in range(1, 53):
    w_name = f"{i}주"
    w_disp = f"{w_name} ({start_date.strftime('%m/%d')})"
    weeks_list.append(w_name)
    week_display_map[w_name] = w_disp
    start_date += datetime.timedelta(days=7)

# --- 5. 탭 구성 ---
tabs = st.tabs(["✅ 출석체크", "📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사&간식"])

if df.empty:
    st.warning("교적부 데이터를 불러오지 못했습니다. 구글 시트 이름을 확인해주세요.")
    st.stop()

# ==========================================
# [탭 1] 출석체크 (3열 배치 & 연간 통계 수정)
# ==========================================
with tabs[0]:
    st.subheader("📅 주차별 출석 관리")
    
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    sel_w = st.selectbox("주차(날짜) 선택", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    
    classes = ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()])
    sel_class = st.selectbox("반 필터", classes)

    att_df = df[df['상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    att_df = att_df.sort_values(by=[class_col, '이름'])

    # 1. 3열 카드형 출석체크
    with st.form("quick_att_form"):
        st.write(f"### {week_display_map[sel_w]} - {sel_class}")
        cols = st.columns(3) # ★ 3열 배치
        new_att_values = {}
        
        for i, (idx, row) in enumerate(att_df.iterrows()):
            with cols[i % 3]:
                is_checked = True if str(row.get(sel_w, "")).strip() == "1" else False
                label = f"{row['이름']}({row[class_col]})"
                if row.get('상태') == '새친구': label = "🔴" + label
                new_att_values[row['sheet_row']] = st.checkbox(label, value=is_checked, key=f"q_{row['sheet_row']}")
        
        if st.form_submit_button("💾 선택 주차 출석 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                col_idx = headers.index(sel_w) + 1
                for r_idx, val in new_att_values.items():
                    ws.update_cell(r_idx, col_idx, "1" if val else "")
                st.success("출석이 저장되었습니다!")
                st.rerun()

    st.markdown("---")
    
    # 2. 연간 통계 및 일괄 수정
    with st.expander("📊 연간 전체 출석 통계 및 일괄 수정", expanded=False):
        st.write("표에서 직접 '1'(출석) 또는 공백(결석)을 입력하여 대규모 수정이 가능합니다.")
        week_cols = [w for w in weeks_list if w in df.columns]
        stat_df = df[df['상태'] != '이사'][[class_col, '이름'] + week_cols + ['sheet_row']].copy()
        
        # 출석률 계산
        def get_rate(row):
            count = sum([1 for w in week_cols if str(row[w]).strip() == "1"])
            return f"{int(count/52*100)}%" if len(week_cols)>0 else "0%"
        stat_df['출석률'] = stat_df.apply(get_rate, axis=1)
        
        edited_stat = st.data_editor(
            stat_df.drop(columns=['sheet_row']),
            use_container_width=True,
            hide_index=True
        )
        if st.button("📝 연간 통계 수정사항 저장"):
            st.info("데이터 에디터를 통한 대량 수정은 '교적부 관리' 탭의 일괄 저장 방식을 권장합니다.")

# ==========================================
# [탭 2] 교적부 관리 (데이터 가시화)
# ==========================================
with tabs[1]:
    st.subheader("📋 교적부 상세 관리")
    # 보여줄 컬럼 필터링
    core_cols = [class_col, '이름', '상태', '연락처', '부모(아빠/엄마)', '주소', '비고']
    valid_cols = [c for c in core_cols if c in df.columns]
    
    edited_members = st.data_editor(
        df[valid_cols],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic"
    )
    
    if st.button("💾 교적부 변경사항 저장"):
        with st.spinner("구글 시트 업데이트 중..."):
            for r in range(len(edited_members)):
                for c in valid_cols:
                    if str(df.iloc[r][c]) != str(edited_members.iloc[r][c]):
                        ws.update_cell(df.iloc[r]['sheet_row'], headers.index(c)+1, str(edited_members.iloc[r][c]))
            st.success("수정되었습니다!")
            st.rerun()

# ==========================================
# [탭 3] 반편성 현황 (데이터 복구)
# ==========================================
with tabs[2]:
    st.subheader("🏫 반별 명단 현황")
    if not df.empty:
        grouped = df[df['상태'] != '이사'].groupby(class_col)
        cols = st.columns(3)
        for i, (name, group) in enumerate(grouped):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{name}** ({len(group)}명)")
                    names = [f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['상태'])]
                    st.write(", ".join(names))

# ==========================================
# [탭 4] 월별 생일표 (이름|반|생일)
# ==========================================
with tabs[3]:
    st.subheader("🎂 월별 생일 명단")
    if '생년월일' in df.columns:
        b_map = {str(i): [] for i in range(1, 13)}
        for _, r in df.iterrows():
            b = str(r['생년월일'])
            if len(b.split('.')) >= 3:
                m = str(int(b.split('.')[1]))
                d = str(int(b.split('.')[2]))
                b_map[m].append(f"**{r['이름']}** ({r[class_col]}) - {d}일")
        
        cols = st.columns(4)
        for i in range(1, 13):
            with cols[(i-1)%4]:
                with st.container(border=True):
                    st.write(f"📅 **{i}월**")
                    for p in b_map[str(i)]: st.write(p)
                    if not b_map[str(i)]: st.caption("없음")

# ==========================================
# [탭 5] 새친구 목록
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    if '상태' in df.columns:
        news = df[df['상태'] == '새친구']
        st.dataframe(news[valid_cols], use_container_width=True, hide_index=True)

# ==========================================
# [탭 6] 행사&간식 (기존 "활동기록" 대체)
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 간식 활동 기록")
    
    with st.expander("➕ 신규 활동 기록 추가", expanded=False):
        with st.form("act_form"):
            d = st.date_input("날짜", datetime.date.today())
            t = st.text_input("활동명")
            desc = st.text_area("세부내용")
            note = st.text_area("공지사항")
            files = st.file_uploader("사진(최대 4장)", accept_multiple_files=True)
            if st.form_submit_button("기록 저장"):
                urls = ["", "", "", ""]
                for i, f in enumerate(files[:4]):
                    urls[i] = upload_photo(f, f"act_{t}_{i}")
                ws_act.append_row([str(d), t, desc, note, urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                st.success("저장되었습니다!")
                st.rerun()

    st.markdown("---")
    st.write("📂 **과거 활동 및 간식 내역**")
    if not df_act.empty:
        for _, row in df_act[::-1].iterrows():
            with st.container(border=True):
                st.info(f"**{row['날짜']}** - {row['활동명']}")
                st.write(row['세부내용'])
                if row['공지사항']: st.warning(f"공지: {row['공지사항']}")
                p_cols = st.columns(4)
                for i in range(1, 5):
                    url = row.get(f'사진{i}', "")
                    if url: p_cols[i-1].image(url, use_container_width=True)
    else:
        st.info("기록된 내역이 없습니다. '활동간식' 시트를 확인해주세요.")
