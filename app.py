import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 통합 관리 시스템", page_icon="🌱", layout="wide")

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

def get_all_sheets():
    try:
        sh = client.open_by_key(sheet_id)
        # 교적부 시트
        ws_members = sh.worksheet("교적부")
        vals = ws_members.get_all_values()
        df_members = pd.DataFrame(vals[1:], columns=vals[0]) if len(vals) > 1 else pd.DataFrame()
        df_members['sheet_row'] = range(2, len(df_members) + 2)
        
        # 활동기록 시트 (없으면 생성 시도)
        try:
            ws_act = sh.worksheet("활동기록")
        except:
            ws_act = sh.add_worksheet(title="활동기록", rows="100", cols="20")
            ws_act.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
            
        act_vals = ws_act.get_all_values()
        df_act = pd.DataFrame(act_vals[1:], columns=act_vals[0]) if len(act_vals) > 1 else pd.DataFrame()

        return ws_members, df_members, vals[0], ws_act, df_act
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame()

ws, df, headers, ws_act, df_act = get_all_sheets()

# --- 3. 공통 함수: 사진 업로드 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except:
        return ""

# --- 4. 주차 세팅 (관리자님 요청: "1주", "2주" 형식) ---
weeks_list = [f"{i}주" for i in range(1, 53)]

# --- 5. 화면 구성 및 탭 (총 6개 완벽 복구) ---
st.title("🌱 유년부 통합 관리 v21.0")
tabs = st.tabs(["✅ 출석체크", "📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사&관리"])

# ==========================================
# [탭 1] 출석체크 (모바일 최적화 카드 UI)
# ==========================================
with tabs[0]:
    st.subheader("📱 모바일 출석 체크")
    
    # 주차 선택
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    sel_w = st.selectbox("기록할 주차 선택", weeks_list, index=max(0, min(51, curr_week_idx)))

    # 반 필터
    classes = ["전체보기"] + sorted([str(c) for c in df['학년(담임)'].unique() if str(c).strip()]) if '학년(담임)' in df.columns else ["전체보기"]
    sel_class = st.selectbox("반 선택", classes)

    # 시트 헤더 매칭
    target_col_idx = -1
    for i, h in enumerate(headers):
        if str(h).strip() == sel_w:
            target_col_idx = i + 1
            break
    
    if target_col_idx == -1:
        st.warning(f"⚠️ 시트에 '{sel_w}' 열이 없습니다. 관리 탭에서 컬럼을 확인하세요.")
    else:
        # 필터링
        att_df = df[df['상태'] != '이사'].copy()
        if sel_class != "전체보기": att_df = att_df[att_df['학년(담임)'] == sel_class]
        
        st.write(f"--- **{sel_w} 명단 ({len(att_df)}명)** ---")
        
        # 일괄 저장을 위한 폼
        with st.form("att_mobile_form"):
            new_status = {}
            for idx, row in att_df.iterrows():
                # 모바일에서 누르기 좋게 큼직한 체크박스 레이아웃
                is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                label = f"[{row.get('학년(담임)','-')}] {row['이름']}"
                if row.get('상태') == '새친구': label = "🔴 " + label
                
                new_status[row['sheet_row']] = st.checkbox(label, value=is_on, key=f"att_{row['sheet_row']}")
            
            save_att = st.form_submit_button("💾 출석 정보 저장하기", use_container_width=True)
            
            if save_att:
                with st.spinner("구글 시트에 기록 중..."):
                    for r_idx, val in new_status.items():
                        ws.update_cell(r_idx, target_col_idx, "1" if val else "")
                    st.success("출석 저장이 완료되었습니다!")
                    st.rerun()

# ==========================================
# [탭 2] 교적부 관리 (수정 및 상세)
# ==========================================
with tabs[1]:
    st.subheader("📋 교적부 데이터 관리")
    # 기존 에디터 유지
    view_cols = ['학년(담임)', '이름', '상태', '연락처', '부모(아빠/엄마)', '주소', '비고']
    view_df = df[[c for c in view_cols if c in df.columns]].copy()
    
    edited_df = st.data_editor(view_df, use_container_width=True, hide_index=True)
    
    if st.button("💾 교적부 수정 내용 저장"):
        with st.spinner("반영 중..."):
            for r in range(len(view_df)):
                for c_name in view_df.columns:
                    if view_df.iloc[r][c_name] != edited_df.iloc[r][c_name]:
                        row_num = df.iloc[r]['sheet_row']
                        col_num = headers.index(c_name) + 1
                        ws.update_cell(row_num, col_num, str(edited_df.iloc[r][c_name]))
            st.success("교적부 정보가 업데이트되었습니다!")
            st.rerun()

# ==========================================
# [탭 3] 반편성 현황
# ==========================================
with tabs[2]:
    st.subheader("🏫 반별 명단")
    if not df.empty:
        grouped = df[df['상태'] != '이사'].groupby('학년(담임)')
        cols = st.columns(3)
        for i, (name, group) in enumerate(grouped):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{name}** ({len(group)}명)")
                    names = [f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['상태'])]
                    st.write(", ".join(names))

# ==========================================
# [탭 4] 월별 생일표
# ==========================================
with tabs[3]:
    st.subheader("🎂 월별 생일 명단")
    if '생년월일' in df.columns:
        birth_map = {str(i): [] for i in range(1, 13)}
        for _, r in df.iterrows():
            b = str(r['생년월일'])
            if len(b.split('.')) >= 2:
                m = str(int(b.split('.')[1]))
                birth_map[m].append(f"{r['이름']}({r.get('학년(담임)','-')})")
        
        cols = st.columns(4)
        for i in range(1, 13):
            with cols[(i-1)%4]:
                st.write(f"**{i}월**")
                for p in birth_map[str(i)]: st.caption(p)

# ==========================================
# [탭 5] 새친구 목록
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    if '상태' in df.columns:
        news = df[df['상태'] == '새친구']
        st.dataframe(news[['학년(담임)', '이름', '생년월일', '연락처', '비고']], use_container_width=True, hide_index=True)

# ==========================================
# [탭 6] 행사 & 관리 (복구 완료)
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 활동 기록")
    
    with st.expander("➕ 새 활동 기록 추가하기", expanded=True):
        with st.form("activity_form", clear_on_submit=True):
            a_date = st.date_input("날짜", datetime.date.today())
            a_title = st.text_input("활동명 (예: 여름성경학교, 달란트잔치)")
            a_desc = st.text_area("세부내용")
            a_notice = st.text_area("공지사항")
            
            st.write("📸 사진 첨부 (최대 4장)")
            up_files = st.file_uploader("사진을 선택하세요", accept_multiple_files=True, type=['jpg', 'png', 'jpeg'])
            
            if st.form_submit_button("🚀 활동 기록 저장"):
                if not a_title:
                    st.error("활동명은 필수입니다.")
                else:
                    with st.spinner("사진 업로드 및 시트 저장 중..."):
                        p_urls = ["", "", "", ""]
                        for idx, f in enumerate(up_files[:4]):
                            p_urls[idx] = upload_photo(f, f"act_{a_title}_{idx}")
                        
                        new_act = [str(a_date), a_title, a_desc, a_notice, p_urls[0], p_urls[1], p_urls[2], p_urls[3], str(datetime.datetime.now())]
                        ws_act.append_row(new_act)
                        st.success("활동 기록이 저장되었습니다!")
                        st.rerun()
    
    st.markdown("---")
    st.write("📂 **과거 활동 내역**")
    if not df_act.empty:
        for idx, row in df_act[::-1].iterrows():
            with st.expander(f"[{row['날짜']}] {row['활동명']}"):
                st.write(f"**내용:** {row['세부내용']}")
                st.write(f"**공지:** {row['공지사항']}")
                cols = st.columns(4)
                for i in range(1, 5):
                    p_url = row.get(f'사진{i}', "")
                    if p_url: cols[i-1].image(p_url, use_container_width=True)
