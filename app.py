import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v29.0", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .class-header {
        background-color: #f1f8ff; padding: 12px 15px; border-radius: 8px;
        color: #0366d6; font-weight: 800; font-size: 1.1rem;
        margin-top: 20px; margin-bottom: 15px; border-left: 5px solid #0366d6;
    }
    div[data-testid="stToggle"] {
        border: 2px solid #eef2f6; padding: 12px 18px; border-radius: 16px;
        background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        transition: all 0.2s ease-in-out; margin-bottom: 10px;
    }
    div[data-testid="stToggle"]:hover {
        border-color: #0366d6; background-color: #f8fbff; box-shadow: 0 4px 8px rgba(3,102,214,0.1);
    }
    div[data-testid="stToggle"] label p {
        font-size: 1.15rem !important; font-weight: 800 !important; color: #2c3e50 !important;
    }
    .month-container { min-height: 180px; border: 1px solid #eee; padding: 10px; border-radius: 10px; background: white; margin-bottom: 15px; }
    .event-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #fafafa; }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 (초고속 캐싱 엔진 도입) ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

@st.cache_resource
def get_worksheets():
    client = init_connection()
    sh = client.open_by_key("1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q")
    ws_m = sh.worksheet("교적부")
    
    try: ws_a = sh.worksheet("활동간식")
    except:
        ws_a = sh.add_worksheet(title="활동간식", rows="500", cols="10")
        ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
        
    try: ws_s = sh.worksheet("주차별통계")
    except:
        ws_s = sh.add_worksheet(title="주차별통계", rows="100", cols="10")
        ws_s.append_row(["주차", "대상인원", "출석", "결석", "기타인원", "총합계", "출석률", "업데이트일시"])
        
    return ws_m, ws_a, ws_s

# API 429 에러(한도 초과)를 막기 위한 데이터 캐싱 (10분 유지)
@st.cache_data(ttl=600)
def fetch_sheet_data():
    ws_m, ws_a, ws_s = get_worksheets()
    return ws_m.get_all_values(), ws_a.get_all_values(), ws_s.get_all_values()

def get_all_data():
    try:
        ws_m, ws_a, ws_s = get_worksheets()
        vals_m, vals_a, vals_s = fetch_sheet_data()
        
        df_m = pd.DataFrame(vals_m[1:], columns=vals_m[0]) if len(vals_m) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        if '상태' in df_m.columns and '학교상태' not in df_m.columns:
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            
        df_a = pd.DataFrame(vals_a[1:], columns=vals_a[0]) if len(vals_a) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        
        df_s = pd.DataFrame(vals_s[1:], columns=vals_s[0]) if len(vals_s) > 1 else pd.DataFrame()
        
        return ws_m, df_m, vals_m[0], ws_a, df_a, ws_s, df_s
    except Exception as e:
        st.error(f"데이터 로딩 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat = get_all_data()

# ★ 안전 장치 복구: 구글 API 에러나 빈 데이터일 경우 시스템 정지하여 에러(AttributeError) 차단
if df is None or df.empty:
    st.warning("⚠️ 구글 시트 요청 한도(API Quota)를 초과했거나 데이터가 비어있습니다. 약 1분 후 새로고침 해주세요.")
    st.stop()

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
tabs = st.tabs(["📋 교적부", "✅ 출석체크", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사"])

# ==========================================
# [탭 1] 교적부 관리
# ==========================================
with tabs[0]:
    st.subheader("📋 교적부 통합 관리")
    manage_mode = st.radio("작업 모드", ["👀 전체보기", "📝 수정/삭제", "➕ 인원추가"], horizontal=True)
    req_cols = ['학년(담임)', '이름', '사진', '생년월일', '학교', '주소', '부모(아빠/엄마)', '연락처', '상태', '비고', '전도자']
    
    available_cols = []
    for c in req_cols:
        if c in df.columns: available_cols.append(c)
        elif c == '상태' and '학교상태' in df.columns: available_cols.append('학교상태')

    if manage_mode == "👀 전체보기":
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config={"사진": st.column_config.ImageColumn("사진")})
        
    elif manage_mode == "📝 수정/삭제":
        search_list = ["학생 선택"] + df.apply(lambda r: f"{r['이름']} | {r.get(class_col,'')}", axis=1).tolist()
        sel_idx = st.selectbox("학생 선택", range(len(search_list)), format_func=lambda x: search_list[x])
        if sel_idx > 0:
            target = df.iloc[sel_idx - 1]
            with st.form("edit_form_final"):
                col_i, col_f = st.columns([1, 2])
                if target.get('사진') and str(target['사진']).startswith('http'): 
                    col_i.image(target['사진'], use_container_width=True)
                
                c1, c2 = col_f.columns(2)
                e_name = c1.text_input("이름", value=target.get('이름', ''))
                e_class = c2.text_input("학년(담임)", value=target.get(class_col, ''))
                e_birth = c1.text_input("생년월일", value=target.get('생년월일', ''))
                e_school = c2.text_input("학교", value=target.get('학교', ''))
                e_phone = c1.text_input("연락처", value=target.get('연락처', ''))
                e_parents = c2.text_input("부모(아빠/엄마)", value=target.get('부모(아빠/엄마)', ''))
                
                current_status = target.get('상태', target.get('학교상태', '일반'))
                e_status = col_f.selectbox("상태", ["일반", "새친구", "이사", "교사"], index=["일반", "새친구", "이사", "교사"].index(current_status) if current_status in ["일반", "새친구", "이사", "교사"] else 0)
                e_addr = col_f.text_input("주소", value=target.get('주소', ''))
                e_memo = col_f.text_input("비고", value=target.get('비고', ''))
                e_evangelist = col_f.text_input("전도자", value=target.get('전도자', ''))
                e_photo = col_f.file_uploader("사진변경 (선택)")
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.form_submit_button("💾 정보 수정 저장", use_container_width=True):
                    with st.spinner("저장 중..."):
                        p_url = upload_photo(e_photo, e_name) if e_photo else target.get('사진','')
                        actual_headers = ws.row_values(1)
                        r_idx = target['sheet_row']
                        
                        update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '학교': e_school, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '전도자': e_evangelist, '사진': p_url}
                        for k, v in update_map.items():
                            if k in actual_headers: ws.update_cell(r_idx, actual_headers.index(k)+1, str(v))
                        
                        if '상태' in actual_headers: ws.update_cell(r_idx, actual_headers.index('상태')+1, e_status)
                        elif '학교상태' in actual_headers: ws.update_cell(r_idx, actual_headers.index('학교상태')+1, e_status)
                        
                        fetch_sheet_data.clear() # 캐시 초기화
                        st.success("수정 완료!"); st.rerun()

                if col_btn2.form_submit_button("🚨 완전 삭제", use_container_width=True):
                    with st.spinner("삭제 중..."):
                        ws.delete_rows(int(target['sheet_row']))
                        fetch_sheet_data.clear() # 캐시 초기화
                        st.success("삭제되었습니다!"); st.rerun()
                        
    elif manage_mode == "➕ 인원추가":
        st.markdown("#### ✨ 새로운 인원 등록")
        with st.form("add_member_form_final", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                n_class = st.text_input("학년(담임) (필수)", placeholder="예: 1-1(권은주)")
                n_name = st.text_input("이름 (필수)")
                n_birth = st.text_input("생년월일", placeholder="예: 19.02.26")
                n_school = st.text_input("학교")
                n_phone = st.text_input("연락처", placeholder="010-1234-5678")
            with col2:
                n_parents = st.text_input("부모(아빠/엄마)")
                n_addr = st.text_input("주소")
                n_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"], index=1)
                n_memo = st.text_input("비고")
                n_evangelist = st.text_input("전도자")
            n_photo = st.file_uploader("학생 사진 첨부", type=["jpg", "png", "jpeg"])
                
            if st.form_submit_button("✨ 등록하기", use_container_width=True):
                if not n_name or not n_class:
                    st.error("이름과 학년(담임)은 필수입니다.")
                else:
                    with st.spinner("등록 중..."):
                        photo_url = upload_photo(n_photo, n_name)
                        actual_headers = ws.row_values(1)
                        new_row = [""] * len(actual_headers)
                        h_map = {str(h).strip(): i for i, h in enumerate(actual_headers)}
                        
                        if '학년(담임)' in h_map: new_row[h_map['학년(담임)']] = n_class
                        if '이름' in h_map: new_row[h_map['이름']] = n_name
                        if '생년월일' in h_map: new_row[h_map['생년월일']] = n_birth
                        if '학교' in h_map: new_row[h_map['학교']] = n_school
                        if '주소' in h_map: new_row[h_map['주소']] = n_addr
                        if '부모(아빠/엄마)' in h_map: new_row[h_map['부모(아빠/엄마)']] = n_parents
                        if '연락처' in h_map: new_row[h_map['연락처']] = n_phone
                        if '상태' in h_map: new_row[h_map['상태']] = n_status
                        elif '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                        if '비고' in h_map: new_row[h_map['비고']] = n_memo
                        if '전도자' in h_map: new_row[h_map['전도자']] = n_evangelist
                        if '사진' in h_map: new_row[h_map['사진']] = photo_url
                        
                        ws.append_row(new_row)
                        fetch_sheet_data.clear() # 캐시 초기화
                        st.success("등록 완료!"); st.rerun()

# ==========================================
# [탭 2] 출석체크
# ==========================================
with tabs[1]:
    st.subheader("📅 주간 출석 및 통계 관리")
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    c1, c2 = st.columns(2)
    with c1: sel_w = st.selectbox("기록 주차", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    with c2: sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()]))
    
    att_df = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    
    st.markdown("---")
    total_reg = len(att_df)
    present_cnt = len(att_df[att_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest = 0
    if not df_stat.empty:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(match.iloc[0]['기타인원'])
            except: pass

    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("대상", f"{total_reg}명")
    cs2.metric("출석", f"{present_cnt}명")
    guest_in = cs3.number_input("기타 인원", min_value=0, value=saved_guest)
    cs4.metric("총 합계", f"{present_cnt + guest_in}명")

    with st.form("att_form_v29"):
        grouped = att_df.sort_values(by=['이름']).groupby(class_col)
        new_att = {}
        for c_name, group in sorted(grouped):
            st.markdown(f"<div class='class-header'>🏷️ {c_name} ({len(group)}명)</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            for i, (idx, row) in enumerate(group.iterrows()):
                with cols[i % 3]:
                    status_val = row.get('상태', row.get('학교상태', ''))
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    label = f"🌱 {row['이름']}" if status_val == '새친구' else row['이름']
                    new_att[row['sheet_row']] = st.toggle(label, value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 출석 및 주간 통계 저장", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: ws.update_cell(1, target_c, sel_w)
                
                final_p = 0
                for r, v in new_att.items():
                    ws.update_cell(r, target_c, "1" if v else "")
                    if v: final_p += 1
                
                rate = int((final_p/total_reg)*100) if total_reg > 0 else 0
                target_stat_row = -1
                if not df_stat.empty and '주차' in df_stat.columns:
                    match_stat = df_stat[df_stat['주차'] == sel_w]
                    if not match_stat.empty: target_stat_row = match_stat.index[0] + 2
                
                stat_data = [sel_w, total_reg, final_p, total_reg-final_p, guest_in, final_p+guest_in, f"{rate}%", str(datetime.datetime.now())]
                if target_stat_row != -1: ws_stat.update(f"A{target_stat_row}:H{target_stat_row}", [stat_data])
                else: ws_stat.append_row(stat_data)
                
                fetch_sheet_data.clear() # 캐시 초기화
                st.success("저장되었습니다!"); st.rerun()

    with st.expander("📊 연간 전체 출석 현황 및 일괄 수정"):
        week_cols = [f"{i}주" for i in range(1, 53) if f"{i}주" in df.columns]
        annual_df = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'][[class_col, '이름', 'sheet_row'] + week_cols].copy()
        for w in week_cols: annual_df[w] = annual_df[w].apply(lambda x: True if str(x).strip() == "1" else False)
        
        edited_annual = st.data_editor(annual_df, hide_index=True, use_container_width=True, 
                                       column_config={w: st.column_config.CheckboxColumn(w) for w in week_cols})
        if st.button("📝 연간 데이터 수정사항 반영"):
            with st.spinner("수정 중..."):
                for r in range(len(annual_df)):
                    for w in week_cols:
                        if annual_df.iloc[r][w] != edited_annual.iloc[r][w]:
                            ws.update_cell(annual_df.iloc[r]['sheet_row'], headers.index(w)+1, "1" if edited_annual.iloc[r][w] else "")
                fetch_sheet_data.clear() # 캐시 초기화
                st.success("업데이트 완료!"); st.rerun()

# ==========================================
# [탭 3] 반편성 현황
# ==========================================
with tabs[2]:
    st.subheader("🏫 반별 명단 현황")
    grouped = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'].groupby(class_col)
    cols = st.columns(3)
    for i, (name, group) in enumerate(grouped):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{name}** ({len(group)}명)")
                st.write(", ".join([f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['학교상태' if '학교상태' in df.columns else '상태'])]))

# ==========================================
# [탭 4] 월별 생일표
# ==========================================
with tabs[3]:
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
                    else: st.caption("생일자 없음")

# ==========================================
# [탭 5] 새친구 목록
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df['학교상태' if '학교상태' in df.columns else '상태'] == '새친구']
    if not news.empty:
        st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else: st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 6] 행사 관리
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 활동 관리")
    e_mode = st.radio("행사 작업", ["📂 보기", "📝 수정", "🚨 삭제", "➕ 등록"], horizontal=True)
    
    if e_mode == "📂 보기" and not df_act.empty:
        for _, row in df_act[::-1].iterrows():
            with st.container():
                st.markdown(f"<div class='event-card'><b>📅 {row['날짜']} | {row['활동명']}</b><br>{row['세부내용']}</div>", unsafe_allow_html=True)
                p_cols = st.columns(4)
                for i in range(1, 5):
                    url = row.get(f'사진{i}', "")
                    if url and str(url).startswith('http'): p_cols[i-1].image(url, use_container_width=True)
                    
    elif e_mode == "📝 수정" and not df_act.empty:
        act_headers = ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"]
        v_act_cols = [c for c in act_headers if c in df_act.columns]
        edited_events = st.data_editor(df_act, use_container_width=True, hide_index=True, column_config={f"사진{i}": st.column_config.ImageColumn() for i in range(1, 5)})
        if st.button("📝 행사 저장"):
            with st.spinner("저장 중..."):
                act_sh_headers = ws_act.row_values(1)
                for r in range(len(edited_events)):
                    for c in v_act_cols:
                        if str(df_act.iloc[r][c]) != str(edited_events.iloc[r][c]):
                            col_idx = act_sh_headers.index(c) + 1
                            ws_act.update_cell(df_act.iloc[r]['sheet_row'], col_idx, str(edited_events.iloc[r][c]))
                fetch_sheet_data.clear() # 캐시 초기화
                st.success("업데이트 완료!"); st.rerun()

    elif e_mode == "🚨 삭제" and not df_act.empty:
        search_list = ["행사 선택"] + df_act.apply(lambda r: f"[{r['날짜']}] {r['활동명']}", axis=1).tolist()
        sel_idx = st.selectbox("삭제할 행사 선택", range(len(search_list)), format_func=lambda x: search_list[x])
        if sel_idx > 0:
            target_act = df_act.iloc[sel_idx - 1]
            if st.button("🚨 완전히 삭제하기", type="primary"):
                with st.spinner("삭제 중..."):
                    ws_act.delete_rows(int(target_act['sheet_row']))
                    fetch_sheet_data.clear() # 캐시 초기화
                    st.success("삭제되었습니다!"); st.rerun()
                    
    elif e_mode == "➕ 등록":
        with st.form("new_event"):
            a_date = st.date_input("날짜"); a_title = st.text_input("행사명"); a_desc = st.text_area("내용"); a_files = st.file_uploader("사진", accept_multiple_files=True)
            if st.form_submit_button("등록"):
                with st.spinner("저장 중..."):
                    urls = ["", "", "", ""]
                    for i, f in enumerate(a_files[:4]): urls[i] = upload_photo(f, a_title)
                    ws_act.append_row([str(a_date), a_title, a_desc, "", urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                    fetch_sheet_data.clear() # 캐시 초기화
                    st.success("등록완료!"); st.rerun()
