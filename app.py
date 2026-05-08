import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v31.1", page_icon="🌱", layout="wide")

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
        border-color: #0366d6; background-color: #f8fbff;
    }
    .total-summary { background-color: #e6f2ff; padding: 15px; border-radius: 10px; text-align: center; color: #005bb5; font-size: 1.2rem; font-weight: bold; margin-bottom: 20px; }
    .month-container { min-height: 180px; border: 1px solid #eee; padding: 10px; border-radius: 10px; background: white; margin-bottom: 15px; }
    .event-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #fafafa; }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 (캐싱 엔진) ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

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
        ws_s = sh.add_worksheet(title="주차별통계", rows="200", cols="10")
        ws_s.append_row(["주차", "대상인원", "출석", "결석", "기타인원", "총합계", "출석률", "업데이트일시"])
    return ws_m, ws_a, ws_s

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

if df is None or df.empty:
    st.warning("⚠️ 구글 시트 데이터가 비어있습니다. 약 1분 후 새로고침 해주세요.")
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
tabs = st.tabs(["📋 교적부", "✅ 출석체크", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사", "📊 통합통계"])

# ==========================================
# [탭 1] 교적부 관리 (🔥 일괄 업데이트 로직 유지)
# ==========================================
with tabs[0]:
    st.subheader("📋 교적부 통합 관리")
    manage_mode = st.radio("작업 모드", ["👀 전체보기", "📝 수정/삭제", "➕ 인원추가"], horizontal=True)
    req_cols = ['학년(담임)', '이름', '사진', '생년월일', '학교', '주소', '부모(아빠/엄마)', '연락처', '학교상태', '비고', '전도자']
    available_cols = [c for c in req_cols if c in df.columns]
    
    if manage_mode == "👀 전체보기":
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config={"사진": st.column_config.ImageColumn("사진")})
    elif manage_mode == "📝 수정/삭제":
        search_list = ["학생 선택"] + df.apply(lambda r: f"{r['이름']} | {r.get(class_col,'')}", axis=1).tolist()
        sel_idx = st.selectbox("수정할 인원 선택", range(len(search_list)), format_func=lambda x: search_list[x])
        if sel_idx > 0:
            target = df.iloc[sel_idx - 1]
            with st.form("edit_form_v31"):
                col_i, col_f = st.columns([1, 2])
                if target.get('사진') and str(target['사진']).startswith('http'): col_i.image(target['사진'], use_container_width=True)
                c1, c2 = col_f.columns(2)
                e_name = c1.text_input("이름", value=target.get('이름',''))
                e_class = c2.text_input("학년(담임)", value=target.get(class_col,''))
                e_birth = c1.text_input("생년월일", value=target.get('생년월일',''))
                e_school = c2.text_input("학교", value=target.get('학교',''))
                e_phone = c1.text_input("연락처", value=target.get('연락처',''))
                e_parents = c2.text_input("부모", value=target.get('부모(아빠/엄마)',''))
                status_opts = ["일반", "새친구", "이사", "교사"]
                curr_s = target.get('학교상태', '일반')
                e_status = col_f.selectbox("구분", status_opts, index=status_opts.index(curr_s) if curr_s in status_opts else 0)
                e_addr = col_f.text_input("주소", value=target.get('주소',''))
                e_memo = col_f.text_input("비고", value=target.get('비고',''))
                e_evangelist = col_f.text_input("전도자", value=target.get('전도자',''))
                e_photo = col_f.file_uploader("사진변경")
                
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.form_submit_button("💾 정보 수정 저장"):
                    with st.spinner("서버에 일괄 저장 중..."):
                        p_url = upload_photo(e_photo, e_name) if e_photo else target.get('사진','')
                        actual_headers = ws.row_values(1)
                        r_idx = int(target['sheet_row'])
                        
                        update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '학교': e_school, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '전도자': e_evangelist, '사진': p_url}
                        
                        cells_to_update = []
                        for k, v in update_map.items():
                            if k in actual_headers:
                                cells_to_update.append(gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)))
                        if '상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('상태')+1, e_status))
                        elif '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                        
                        if cells_to_update: ws.update_cells(cells_to_update)
                        fetch_sheet_data.clear()
                        st.success("수정 완료!"); st.rerun()
                        
                if c_btn2.form_submit_button("🚨 완전 삭제"):
                    ws.delete_rows(int(target['sheet_row']))
                    fetch_sheet_data.clear(); st.success("삭제되었습니다!"); st.rerun()
                    
    elif manage_mode == "➕ 인원추가":
        with st.form("add_new"):
            col1, col2 = st.columns(2)
            n_name = col1.text_input("이름 (필수)")
            n_class = col1.text_input("학년(담임) (필수)")
            n_status = col2.selectbox("구분", ["일반", "새친구", "교사"], index=1)
            n_photo = st.file_uploader("사진 첨부")
            if st.form_submit_button("✨ 등록하기"):
                if n_name and n_class:
                    p_url = upload_photo(n_photo, n_name)
                    new_row = [""] * len(headers)
                    h_map = {str(h): i for i, h in enumerate(headers)}
                    if '이름' in h_map: new_row[h_map['이름']] = n_name
                    if class_col in h_map: new_row[h_map[class_col]] = n_class
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                    elif '상태' in h_map: new_row[h_map['상태']] = n_status
                    if '사진' in h_map: new_row[h_map['사진']] = p_url
                    ws.append_row(new_row)
                    fetch_sheet_data.clear(); st.success("등록 완료!"); st.rerun()

# ==========================================
# [탭 2] 출석체크 (🔥 API 에러 원천 차단 일괄 저장)
# ==========================================
with tabs[1]:
    st.subheader("📅 주간 출석 & 통계")
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    c1, c2 = st.columns(2)
    with c1: sel_w = st.selectbox("출석 주차", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    with c2: sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()]))
    
    status_col = '학교상태'
    att_df = df[df[status_col] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    
    # 통계 계산
    s_df = att_df[att_df[status_col] != '교사']
    t_df = att_df[att_df[status_col] == '교사']
    s_p = len(s_df[s_df[sel_w].astype(str).str.strip() == "1"])
    t_p = len(t_df[t_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest = 0
    if not df_stat.empty and '주차' in df_stat.columns:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(match.iloc[0]['기타인원'])
            except: pass

    st.markdown("#### 📊 이번 주 현황")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("학생 출석", f"{s_p}명", f"재적 {len(s_df)}명")
    cs2.metric("교사 출석", f"{t_p}명", f"재적 {len(t_df)}명")
    cs3.metric("전체 출석", f"{s_p + t_p}명")
    guest_in = cs4.number_input("기타 방문", min_value=0, value=saved_guest)
    st.markdown(f"<div class='total-summary'>✅ 최종 합계: {s_p + t_p + guest_in}명</div>", unsafe_allow_html=True)

    # 모바일 주간 출석체크
    with st.form("att_toggle_form_v31"):
        new_att = {}
        grouped = att_df.sort_values(by=['이름']).groupby(class_col)
        for c_name, group in sorted(grouped):
            st.markdown(f"<div class='class-header'>🏷️ {c_name} ({len(group)}명)</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            for i, (idx, row) in enumerate(group.iterrows()):
                is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                label = f"🌱 {row['이름']}" if row[status_col] == '새친구' else row['이름']
                new_att[row['sheet_row']] = cols[i%3].toggle(label, value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 출석 정보 일괄 저장", type="primary", use_container_width=True):
            with st.spinner("구글 서버에 한 번에 저장 중... (에러 없음)"):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: ws.update_cell(1, target_c, sel_w)
                
                cells_to_update = []
                final_p = 0
                for r, v in new_att.items():
                    cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                    if v: final_p += 1
                
                if cells_to_update: ws.update_cells(cells_to_update)
                
                rate = int((final_p/len(att_df))*100) if len(att_df)>0 else 0
                stat_data = [sel_w, len(att_df), final_p, len(att_df)-final_p, guest_in, final_p+guest_in, f"{rate}%", str(datetime.datetime.now())]
                match_stat = df_stat[df_stat['주차'] == sel_w] if not df_stat.empty else pd.DataFrame()
                if not match_stat.empty: ws_stat.update(f"A{match_stat.index[0]+2}:H{match_stat.index[0]+2}", [stat_data])
                else: ws_stat.append_row(stat_data)
                
                fetch_sheet_data.clear(); st.success("안전하게 일괄 저장되었습니다!"); st.rerun()

    # 연간 통계 에디터
    with st.expander("📊 연간 전체 출석 현황 및 일괄 수정"):
        week_cols = [f"{i}주" for i in range(1, 53) if f"{i}주" in df.columns]
        annual_df = df[df[status_col] != '이사'][[class_col, '이름', 'sheet_row'] + week_cols].copy()
        for w in week_cols: annual_df[w] = annual_df[w].apply(lambda x: True if str(x).strip() == "1" else False)
        
        edited_annual = st.data_editor(annual_df, hide_index=True, use_container_width=True, 
                                       column_config={w: st.column_config.CheckboxColumn(w) for w in week_cols})
        if st.button("📝 연간 데이터 수정사항 한 번에 반영"):
            with st.spinner("초고속 일괄 동기화 중..."):
                cells_to_update = []
                for r in range(len(annual_df)):
                    for w in week_cols:
                        if annual_df.iloc[r][w] != edited_annual.iloc[r][w]:
                            row_idx = int(annual_df.iloc[r]['sheet_row'])
                            col_idx = headers.index(w) + 1
                            val = "1" if edited_annual.iloc[r][w] else ""
                            cells_to_update.append(gspread.Cell(row_idx, col_idx, val))
                
                if cells_to_update: ws.update_cells(cells_to_update)
                fetch_sheet_data.clear(); st.success("에러 없이 완벽하게 업데이트 되었습니다!"); st.rerun()

# ==========================================
# [탭 7] 통합 통계 & 다운로드 (🔥CSV 모듈로 변경)
# ==========================================
with tabs[6]:
    st.subheader("📊 사역 통합 통계 및 다운로드")
    
    week_cols = [f"{i}주" for i in range(1, 53) if f"{i}주" in df.columns]
    report_df = df[df[status_col] != '이사'][[class_col, '이름', '학교상태'] + week_cols].copy()
    report_df['출석수'] = report_df[week_cols].apply(lambda x: x.astype(str).str.strip().eq('1').sum(), axis=1)
    report_df['출석률'] = report_df['출석수'].apply(lambda x: f"{int(x/len(week_cols)*100)}%" if len(week_cols)>0 else "0%")
    
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.write("👤 **개인별 누적 출석 현황**")
        st.dataframe(report_df[[class_col, '이름', '학교상태', '출석수', '출석률']], use_container_width=True, hide_index=True)
    with col_dl2:
        st.write("📅 **주차별 인원 흐름**")
        st.dataframe(df_stat, use_container_width=True, hide_index=True)

    st.divider()
    st.write("📥 **통계 데이터 엑셀/CSV 다운로드** (에러 없이 안전하게 받아보세요)")
    
    c_csv1, c_csv2 = st.columns(2)
    with c_csv1:
        # 개인별 통계 CSV 변환 (한글 깨짐 방지 utf-8-sig)
        csv_personal = report_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📊 개인별 통계 다운로드", data=csv_personal, file_name=f"개인별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
    with c_csv2:
        # 주차별 통계 CSV 변환
        csv_weekly = df_stat.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📅 주차별 통계 다운로드", data=csv_weekly, file_name=f"주차별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)

# ==========================================
# 나머지 탭 (반편성, 생일표, 새친구, 행사)
# ==========================================
with tabs[2]: # 반편성
    st.subheader("🏫 반별 명단 현황")
    grouped = df[df[status_col] != '이사'].groupby(class_col)
    cols = st.columns(3)
    for i, (name, group) in enumerate(grouped):
        with cols[i%3]:
            with st.container(border=True):
                st.markdown(f"**{name}** ({len(group)}명)")
                st.write(", ".join([f"🔴{n}" if s=='새친구' else n for n,s in zip(group['이름'], group[status_col])]))

with tabs[3]: # 생일
    st.subheader("🎂 월별 생일 명단")
    b_map = {i: [] for i in range(1, 13)}
    for _, r in df.iterrows():
        b = str(r.get('생년월일', ''))
        if len(b.split('.')) >= 3:
            try: m, d = int(b.split('.')[1]), int(b.split('.')[2]); b_map[m].append({"name": r['이름'], "class": r.get(class_col,''), "day": d})
            except: pass
    for row_idx in range(4):
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"<h4 style='color:#0366d6; margin-bottom:0px;'>📅 {m}월</h4>", unsafe_allow_html=True); st.divider()
                    for p in sorted(b_map[m], key=lambda x: x["day"]):
                        st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'>"
                                    f"<span>🎈 <b>{p['name']}</b> <span style='font-size:0.8rem; color:gray;'>({p['class']})</span></span>"
                                    f"<strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)

with tabs[4]: # 새친구
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구']
    if not news.empty: st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else: st.info("새친구가 없습니다.")

with tabs[5]: # 행사 (🔥 행사 뷰 레이아웃 복구)
    st.subheader("⚙️ 행사 관리")
    e_mode = st.radio("행사", ["📂 보기", "📝 수정", "🚨 삭제", "➕ 등록"], horizontal=True)
    
    if e_mode == "📂 보기" and not df_act.empty:
        for _, row in df_act[::-1].iterrows():
            with st.container():
                st.markdown(f"""
                <div class='event-card'>
                    <h3 style='margin-top:0;'>📅 {row.get('날짜', '')} | {row.get('활동명', '')}</h3>
                    <p><b>내용:</b> {row.get('세부내용', '')}</p>
                    <p style='color: #d32f2f;'><b>공지:</b> {row.get('공지사항', '')}</p>
                </div>
                """, unsafe_allow_html=True)
                p_cols = st.columns(4)
                for i in range(1, 5):
                    url = row.get(f'사진{i}', "")
                    if url and str(url).startswith('http'): p_cols[i-1].image(url, use_container_width=True)
                    
    elif e_mode == "📝 수정" and not df_act.empty:
        act_sh_headers = ws_act.row_values(1)
        v_act_cols = [c for c in ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"] if c in df_act.columns]
        edited_events = st.data_editor(df_act, use_container_width=True, hide_index=True, column_config={f"사진{i}": st.column_config.ImageColumn() for i in range(1, 5)})
        if st.button("📝 행사 저장"):
            with st.spinner("일괄 업데이트 중..."):
                cells_to_update = []
                for r in range(len(edited_events)):
                    for c in v_act_cols:
                        if str(df_act.iloc[r][c]) != str(edited_events.iloc[r][c]):
                            cells_to_update.append(gspread.Cell(int(df_act.iloc[r]['sheet_row']), act_sh_headers.index(c)+1, str(edited_events.iloc[r][c])))
                if cells_to_update: ws_act.update_cells(cells_to_update)
                fetch_sheet_data.clear(); st.success("저장완료"); st.rerun()
                
    elif e_mode == "🚨 삭제" and not df_act.empty:
        sel_del = st.selectbox("삭제할 행사", df_act['활동명'].tolist())
        if st.button("🚨 삭제 실행"):
            ws_act.delete_rows(int(df_act[df_act['활동명']==sel_del].iloc[0]['sheet_row']))
            fetch_sheet_data.clear(); st.success("삭제됨"); st.rerun()
            
    elif e_mode == "➕ 등록":
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명"); a_c = st.text_area("내용"); a_f = st.file_uploader("사진", accept_multiple_files=True)
            if st.form_submit_button("저장"):
                urls = ["", "", "", ""]; [urls.__setitem__(i, upload_photo(f, a_t)) for i, f in enumerate(a_f[:4])]
                ws_act.append_row([str(a_d), a_t, a_c, "", urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                fetch_sheet_data.clear(); st.success("저장완료"); st.rerun()
