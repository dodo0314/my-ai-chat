import streamlit as st
import json
import uuid
from datetime import datetime
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pdfplumber  # PDF 읽기용

# ==========================================
# [1] 설정 및 API 연결
# ==========================================
st.set_page_config(page_title="Cloud AI Research Lab", page_icon="☁️", layout="wide")

# API 키 및 구글 인증 (Secrets에서 가져오기)
try:
    API_KEY = st.secrets["MY_API_KEY"]
    
    # 구글 시트 인증
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"]) # secrets를 dict로 변환
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client_gs = gspread.authorize(creds)
    
except Exception as e:
    st.error(f"Secret 키 설정 오류: {e}")
    st.stop()

# OpenRouter 클라이언트
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

# 모델 라인업
MODEL_OPTIONS = {
    "Claude 3.5 Sonnet": "anthropic/claude-3.5-sonnet",
    "GPT-4o": "openai/gpt-4o",
    "Gemini 1.5 Pro": "google/gemini-pro-1.5", 
    "DeepSeek V3": "deepseek/deepseek-chat",
}

# ==========================================
# [2] 구글 시트 함수 (안전성 강화)
# ==========================================
def get_google_sheet():
    try:
        return client_gs.open("dodochat_db").sheet1
    except Exception as e:
        st.error(f"구글 시트 'dodochat_db'를 찾을 수 없습니다. 이름과 공유설정을 확인하세요. ({e})")
        st.stop()

def load_all_chats_from_sheet():
    sheet = get_google_sheet()
    try:
        records = sheet.get_all_records()
        # 최신순 정렬 (last_updated 기준)
        records.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return records
    except:
        return []

def save_chat_to_sheet(chat_id, title, history):
    try:
        sheet = get_google_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_json = json.dumps(history, ensure_ascii=False)
        
        # gspread 6.0.0 대응: find 사용
        cell = sheet.find(chat_id)
        
        if cell:
            row = cell.row
            sheet.update_cell(row, 2, title)
            sheet.update_cell(row, 3, history_json)
            sheet.update_cell(row, 4, timestamp)
        else:
            sheet.append_row([chat_id, title, history_json, timestamp])
            
    except Exception as e:
        st.warning(f"저장 중 일시적 오류 (데이터는 안전합니다): {e}")

# ==========================================
# [3] UI 및 로직
# ==========================================

# 세션 초기화
if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None
if "history" not in st.session_state:
    st.session_state["history"] = []
if "retry_trigger" not in st.session_state:
    st.session_state["retry_trigger"] = False
if "last_loaded_id" not in st.session_state:
    st.session_state["last_loaded_id"] = None

# ----------------- [사이드바] -----------------
with st.sidebar:
    st.title("☁️ 클라우드 연구소")
    
    # 1. 화면/모델 설정
    num_screens = st.radio("화면 분할", [1, 2, 3], horizontal=True)
    selected_models = []
    model_names = list(MODEL_OPTIONS.keys())
    for i in range(num_screens):
        default_idx = i % len(model_names)
        m = st.selectbox(f"화면 {i+1}", model_names, index=default_idx, key=f"m_{i}")
        selected_models.append(MODEL_OPTIONS[m])
    
    st.divider()
    
    # 2. PDF/파일 업로드 (새로운 기능!)
    st.subheader("📂 자료 업로드")
    uploaded_file = st.file_uploader("PDF/TXT 파일을 드래그하세요", type=["pdf", "txt"])
    context_text = ""
    if uploaded_file:
        try:
            if uploaded_file.type == "application/pdf":
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        txt = page.extract_text()
                        if txt: context_text += txt + "\n"
            else:
                context_text = uploaded_file.read().decode("utf-8")
            st.success(f"문서 로드됨 ({len(context_text)}자)")
        except Exception as e:
            st.error(f"파일 읽기 실패: {e}")

    st.divider()

    # 3. 채팅방 관리 & 재시도
    col_new, col_retry = st.columns(2)
    with col_new:
        if st.button("➕ 새 연구", use_container_width=True):
            new_id = str(uuid.uuid4())[:8]
            st.session_state["current_chat_id"] = new_id
            st.session_state["history"] = []
            st.session_state["last_loaded_id"] = new_id
            # 시트에 미리 생성
            save_chat_to_sheet(new_id, "새 연구 시작", [])
            st.rerun()
            
    with col_retry:
        if st.button("🔄 재시도", use_container_width=True):
            if st.session_state["history"]:
                st.session_state["retry_trigger"] = True
                st.rerun()

    # 4. 목록 불러오기 (구글 시트)
    all_chats = load_all_chats_from_sheet()
    if all_chats:
        chat_options = {chat['chat_id']: chat['title'] for chat in all_chats}
        
        # 현재 ID 유효성 체크
        if st.session_state["current_chat_id"] not in chat_options:
             if all_chats: st.session_state["current_chat_id"] = all_chats[0]['chat_id']
        
        selected_id = st.radio(
            "기록 목록", list(chat_options.keys()),
            format_func=lambda x: chat_options[x],
            index=list(chat_options.keys()).index(st.session_state["current_chat_id"]) if st.session_state["current_chat_id"] else 0
        )
        
        # 목록 클릭 시 로딩 (DB -> Session)
        if selected_id != st.session_state["last_loaded_id"]:
            st.session_state["current_chat_id"] = selected_id
            st.session_state["last_loaded_id"] = selected_id
            
            chat_data = next((item for item in all_chats if item["chat_id"] == selected_id), None)
            if chat_data:
                try:
                    st.session_state["history"] = json.loads(chat_data['history'])
                except:
                    st.session_state["history"] = []
            st.rerun()

# ----------------- [메인 화면] -----------------
current_title = "새 연구"
if all_chats and st.session_state["current_chat_id"]:
    found = next((c for c in all_chats if c['chat_id'] == st.session_state["current_chat_id"]), None)
    if found: current_title = found['title']

st.subheader(f"🧪 {current_title}")

history = st.session_state["history"]

# 과거 대화 출력
for turn in history:
    with st.chat_message("user"):
        st.write(turn["user"])
    cols = st.columns(num_screens)
    for i in range(num_screens):
        with cols[i]:
            resp = turn["responses"].get(str(i))
            if resp:
                st.caption(f"🤖 {resp.get('model_name')}")
                st.info(resp.get("text"))

st.divider()

# ----------------- [입력 및 처리] -----------------
prompt_to_process = None

# 1. 재시도 트리거 확인
if st.session_state["retry_trigger"]:
    if history:
        last_turn = history.pop() # 마지막 턴 제거
        prompt_to_process = last_turn["user"] # 질문 복구
        
        # (중요) 만약 질문에 문서 내용이 포함되어 있었다면, 너무 기니까 
        # 원본 파일이 있으면 다시 붙이고, 아니면 그냥 텍스트만 씀.
        # 여기선 단순화를 위해 그대로 사용합니다.
        
        st.session_state["history"] = history
        st.toast("🔄 재시도 중...")
    st.session_state["retry_trigger"] = False

# 2. 신규 입력 (Form 사용 - 줄바꿈 지원)
with st.form(key="chat_form", clear_on_submit=True):
    col_in, col_btn = st.columns([8, 1])
    with col_in:
        user_input = st.text_area("질문/지시사항 (Shift+Enter 줄바꿈)", height=100, key="input_text")
    with col_btn:
        st.write("")
        st.write("")
        submit_btn = st.form_submit_button("전송 🚀")

if submit_btn and user_input:
    prompt_to_process = user_input

# ----------------- [AI 응답 생성] -----------------
if prompt_to_process:
    
    # PDF 내용이 있으면 질문과 합치기 (보이지 않게 내부적으로만 처리할 수도 있지만, 확인을 위해 표시 추천)
    final_prompt = prompt_to_process
    if context_text:
        final_prompt = f"다음 문서를 참고하여 답변해:\n[문서 시작]\n{context_text}\n[문서 끝]\n\n질문: {prompt_to_process}"
        st.info(f"📎 문서({len(context_text)}자)가 프롬프트에 포함되었습니다.")
    
    # 화면 표시
    with st.chat_message("user"):
        st.write(prompt_to_process) # 화면엔 깔끔하게 질문만
    
    current_turn_responses = {}
    cols = st.columns(num_screens)
    
    # 최근 N개 대화만 기억 (토큰 절약)
    recent_history = history[-10:]
    
    for i in range(num_screens):
        with cols[i]:
            model_id = selected_models[i]
            d_name = [k for k, v in MODEL_OPTIONS.items() if v == model_id][0]
            
            st.caption(f"🏃 {d_name}...")
            placeholder = st.empty()
            full_text = ""
            
            # 메시지 조립
            messages = [{"role": "system", "content": "전문적인 리서치 어시스턴트입니다."}]
            for turn in recent_history:
                messages.append({"role": "user", "content": turn["user"]}) # 여기선 문서 내용은 생략하고 질문만 넣음 (절약)
                if str(i) in turn["responses"]:
                    messages.append({"role": "assistant", "content": turn["responses"][str(i)]["text"]})
            
            messages.append({"role": "user", "content": final_prompt})
            
            try:
                stream = client.chat.completions.create(
                    model=model_id, messages=messages, stream=True
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_text += content
                        placeholder.info(full_text + "▌")
                placeholder.info(full_text)
                
                current_turn_responses[str(i)] = {
                    "model_name": d_name, "text": full_text
                }
            except Exception as e:
                placeholder.error(f"에러: {e}")
                current_turn_responses[str(i)] = {"model_name": d_name, "text": f"Error: {e}"}

    # 저장 (메모리 + 구글 시트)
    if st.session_state["current_chat_id"]:
        # 저장할 땐 '문서 내용이 포함된 긴 프롬프트' 대신 '사용자가 입력한 질문'만 저장할지 선택
        # 여기선 가독성을 위해 '사용자 입력 질문(prompt_to_process)'만 저장합니다.
        # (문서는 매번 새로 올리거나, 필요하면 final_prompt를 저장해도 됨)
        new_turn = {"user": prompt_to_process, "responses": current_turn_responses}
        
        st.session_state["history"].append(new_turn)
        
        # 제목 자동 설정 (첫 턴일 때)
        save_title = current_title
        if len(st.session_state["history"]) == 1:
            save_title = prompt_to_process[:20] + "..."
            
        save_chat_to_sheet(st.session_state["current_chat_id"], save_title, st.session_state["history"])
        st.rerun()
