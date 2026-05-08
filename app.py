import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v26.1", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .class-header {
        background-color: #f1f8ff;
        padding: 12px 15px;
        border-radius: 8px;
        color: #0366d6;
        font-weight: 800;
        font-size: 1.1rem;
        margin-top: 20px;
        margin-bottom: 15px;
        border-left: 5px solid #0366d6;
    }
    .att-card {
        border: 2px solid #e0e0e0;
        padding: 15px;
        border-radius: 12px;
        background-color: #ffffff;
        margin-bottom: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .stCheckbox label {
        font-size: 1.2rem !important;
        font-weight: bold !important;
        color: #2c3e50 !important;
    }
    .month-container { 
        min-height: 200px; border: 1px solid #eee; padding: 10px; 
        border-radius: 10px; background: white; margin-bottom: 15px; 
    }
    .event-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
        background-color: #fafafa;
    }
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
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        df_m = pd.DataFrame(vals[1:], columns=vals[0]) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        if '상태' in df_m.columns and '학교상태' not in df_m.columns:
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            
        try:
            ws_a = sh.worksheet("활동간식")
        except:
            ws_a = sh.add_worksheet(title="활동간식", rows="500", cols="10")
            ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
        
        a_vals = ws_a.get_all_values()
        df_a = pd.DataFrame(a_vals[1:], columns=a_vals[0]) if len(a_vals) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        
        try:
            ws_s = sh.worksheet("주차별통계")
        except:
            ws_s = sh.add_worksheet(title="주차별통계", rows="100", cols="10")
            ws_s.append_row(["주차", "대상인원", "출석", "결석", "기타인원", "총합계", "출석률", "업데이트일시"])
        
        s_vals = ws_s.get_all_values()
        df_s = pd.DataFrame(s_vals[1:], columns=s_vals[0]) if len(s_vals) > 1 else pd.DataFrame()
        
        return ws_m, df_m, vals[0], ws_a, df_a, ws_s, df_s
    except Exception as e:
        st.error(f"데이터 로딩 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat = get_all_data()

# --- 3. 공통 함수 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except: return ""

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
start_date = datetime.date(2026, 1, 4)
weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": f"{i}주 ({ (start_date + datetime.timedelta(days=(i-1)*7)).strftime('%m/%d') })" for i in range(1, 53)}

# --- 4. 탭 구성 ---
tabs = st.tabs(["✅ 출석체크", "📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사"])

# ==========================================
# [탭 1] 출석체크 (v26.0 최신 기능 유지)
# ==========================================
with tabs[0]:
    st.subheader("📅 주간 출석 & 통계 관리")
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    c1, c2 = st.columns(2)
    with c1: sel_w = st.selectbox("기록 주차", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    with c2: sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()]))
    
    att_df = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    
    total_reg = len(att_df)
    present_count = len(att_df[att_df[sel_w].astype(str).str.strip() == "1"])
    saved_guest = 0
    if not df_stat.empty:
        match_stat = df_stat[df_stat['주차'] == sel_w]
        if not match_stat.empty:
            try: saved_guest = int(match_stat.iloc[0]['기타인원'])
            except: pass

    st.markdown("---")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("대상", f"{total_reg}명")
    cs2.metric("출석", f"{present_count}명")
    guest_input = cs3.number_input("기타 인원", min_value=0, value=saved_guest, step=1)
    cs4.metric("총 합계", f"{present_count + guest_input}명")

    with st.form("att_toggle_form"):
        new_att_status = {}
        grouped = att_df.sort_values(by=['이름']).groupby(class_col)
        for c_name, group in sorted(grouped):
            st.markdown(f"<div class='class-header'>🏷️ {c_name} ({len(group)}명)</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            for i, (idx, row) in enumerate(group.iterrows()):
                with cols[i % 3]:
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    new_att_status[row['sheet_row']] = st.toggle(row['이름'], value=is_on, key=f"tgl_{row['sheet_row']}")
        if st.form_submit_button("💾 출석 및 통계 저장", type="primary", use_container_width=True):
            target_col_idx = headers.index(sel_w) + 1
            final_p = 0
            for r_idx, val in new_att_status.items():
                ws.update_cell(r_idx, target_col_idx, "1" if val else "")
                if val: final_p += 1
            rate = int((final_p / total_reg) * 100) if total_reg > 0 else 0
            stat_row = [sel_w, total_reg, final_p, total_reg - final_p, guest_input, final_p + guest_input, f"{rate}%", str(datetime.datetime.now())]
            ws_stat.append_row(stat_row) # 통계 추가
            st.success("저장 완료!"); st.rerun()

# ==========================================
# [탭 6] 행사 (🔥 사진 보기 및 수정 기능 강화)
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 활동 관리")
    
    # 1. 모드 선택
    event_mode = st.radio("작업 선택", ["📂 과거 내역 보기", "📝 내역 수정하기", "➕ 신규 행사 등록"], horizontal=True)
    
    st.markdown("---")
    
    if event_mode == "📂 과거 내역 보기":
        if not df_act.empty:
            # 최신순으로 정렬하여 표시
            for _, row in df_act[::-1].iterrows():
                with st.container():
                    st.markdown(f"""
                    <div class='event-card'>
                        <h3 style='margin-top:0;'>📅 {row['날짜']} | {row['활동명']}</h3>
                        <p><b>내용:</b> {row['세부내용']}</p>
                        <p style='color: #d32f2f;'><b>공지:</b> {row['공지사항']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 사진 4장 배치
                    p_cols = st.columns(4)
                    for i in range(1, 5):
                        p_url = row.get(f'사진{i}', "")
                        if p_url and str(p_url).startswith('http'):
                            p_cols[i-1].image(p_url, use_container_width=True, caption=f"사진 {i}")
                    st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.info("기록된 행사 내역이 없습니다.")

    elif event_mode == "📝 내역 수정하기":
        st.info("💡 표에서 직접 내용을 수정하거나 사진 주소를 변경할 수 있습니다. (사진은 썸네일로 보입니다)")
        if not df_act.empty:
            act_headers = ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"]
            v_act_cols = [c for c in act_headers if c in df_act.columns]
            
            # ★ 사진 컬럼을 ImageColumn으로 설정하여 텍스트 대신 이미지가 보이게 함
            edited_events = st.data_editor(
                df_act[v_act_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "사진1": st.column_config.ImageColumn("사진1"),
                    "사진2": st.column_config.ImageColumn("사진2"),
                    "사진3": st.column_config.ImageColumn("사진3"),
                    "사진4": st.column_config.ImageColumn("사진4"),
                },
                key="events_editor_v26"
            )
            
            if st.button("💾 행사 수정사항 저장하기", use_container_width=True):
                with st.spinner("구글 시트 업데이트 중..."):
                    changed_count = 0
                    act_sh_headers = ws_act.row_values(1)
                    for r in range(len(edited_events)):
                        for c in v_act_cols:
                            old_v = str(df_act.iloc[r][c]).strip()
                            new_v = str(edited_events.iloc[r][c]).strip()
                            if old_v != new_v:
                                row_idx = df_act.iloc[r]['sheet_row']
                                col_idx = act_sh_headers.index(c) + 1
                                ws_act.update_cell(row_idx, col_idx, new_v)
                                changed_count += 1
                    st.success(f"{changed_count}건의 정보가 수정되었습니다!"); st.rerun()
        else:
            st.info("기록된 행사가 없습니다.")

    elif event_mode == "➕ 신규 행사 등록":
        with st.form("new_act_form_v26", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                a_date = st.date_input("행사 날짜", datetime.date.today())
                a_title = st.text_input("행사/활동명", placeholder="예: 여름성경학교, 간식 파티")
            with col2:
                a_desc = st.text_area("세부 활동 내용", placeholder="행사 내용을 간단히 적어주세요.")
            
            a_notice = st.text_input("공지 및 기타사항", placeholder="전달사항이 있다면 적어주세요.")
            
            st.write("📸 **행사 사진 첨부 (최대 4장)**")
            files = st.file_uploader("사진을 선택하세요", accept_multiple_files=True, type=['jpg', 'png', 'jpeg'])
            
            if st.form_submit_button("🚀 행사 기록 저장하기", use_container_width=True):
                if not a_title:
                    st.error("행사명을 입력해주세요!")
                else:
                    with st.spinner("사진 업로드 및 시트 저장 중..."):
                        urls = ["", "", "", ""]
                        for i, f in enumerate(files[:4]):
                            urls[i] = upload_photo(f, f"event_{a_title}_{i}")
                        
                        # 시트에 한 줄 추가
                        ws_act.append_row([str(a_date), a_title, a_desc, a_notice, urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                        st.success("새로운 행사가 등록되었습니다!"); st.rerun()

# --- 나머지 탭(교적부, 반편성, 생일, 새친구)은 v26.0과 동일 유지 ---
with tabs[1]: # 교적부
    st.subheader("📋 교적부 통합 관리")
    m_mode = st.radio("작업", ["👀 보기", "📝 수정/삭제", "➕ 추가"], horizontal=True)
    if m_mode == "👀 보기":
        st.dataframe(df[['학년(담임)', '이름', '생년월일', '연락처', '학교상태', '비고']], use_container_width=True, hide_index=True)
    elif m_mode == "📝 수정/삭제":
        st.info("개별 상세 수정 모드를 이용하세요.")
    elif m_mode == "➕ 추가":
        with st.form("add"):
            n_name = st.text_input("이름")
            n_class = st.text_input("학년(담임)")
            if st.form_submit_button("등록"):
                ws.append_row([n_class, n_name, "", "", "", "", "일반", ""]); st.rerun()

with tabs[2]: # 반편성
    st.subheader("🏫 반별 명단 현황")
    grouped = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'].groupby(class_col)
    cols = st.columns(3)
    for i, (name, group) in enumerate(grouped):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{name}** ({len(group)}명)")
                st.write(", ".join([f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['학교상태'])]))

with tabs[3]: # 생일 (수정된 가로 정렬 로직)
    st.subheader("🎂 월별 생일 명단")
    b_map = {i: [] for i in range(1, 13)}
    for _, r in df.iterrows():
        b = str(r.get('생년월일', ''))
        if len(b.split('.')) >= 3:
            try: m=int(b.split('.')[1]); d=int(b.split('.')[2]); b_map[m].append({"name": r['이름'], "class": r.get(class_col,''), "day":d})
            except: pass
    for row_idx in range(4):
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"<b>📅 {m}월</b>", unsafe_allow_html=True); st.divider()
                    sorted_b = sorted(b_map[m], key=lambda x: x["day"])
                    if sorted_b:
                        for p in sorted_b: st.write(f"🎈 {p['name']} ({p['class']}) - {p['day']}일")
                    else: st.caption("없음")

with tabs[4]: # 새친구
    st.subheader("🌱 최근 등록 새친구")
    news = df[df['학교상태' if '학교상태' in df.columns else '상태'] == '새친구']
    st.dataframe(news[['학년(담임)', '이름', '생년월일', '연락처', '비고']], use_container_width=True, hide_index=True)
