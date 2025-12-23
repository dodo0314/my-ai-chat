import streamlit as st
import json
import uuid
from datetime import datetime
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pdfplumber

# ==========================================
# [1] 설정 및 API 연결
# ==========================================
st.set_page_config(page_title="Cloud AI Lab", page_icon="☁️", layout="wide")

# API 키 및 구글 인증
try:
    API_KEY = st.secrets["MY_API_KEY"]
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client_gs = gspread.authorize(creds)
except Exception as e:
    st.error(f"Secret 설정 오류: {e}")
    st.stop()

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

MODEL_OPTIONS = {
    "GPT 5.2": "openai/gpt-5.2",
    "GPT 5-Mini": "openai/gpt-5-mini", 
    "DeepSeek V3.2": "deepseek/deepseek-v3.2",
}

# ==========================================
# [2] 구글 시트 함수
# ==========================================
def get_google_sheet():
    try:
        return client_gs.open("dodochat_db").sheet1
    except Exception as e:
        st.error(f"구글 시트 연동 실패: {e}")
        st.stop()

def load_all_chats_from_sheet():
    sheet = get_google_sheet()
    try:
        records = sheet.get_all_records()
        records.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return records
    except:
        return []

def save_chat_to_sheet(chat_id, title, history):
    try:
        sheet = get_google_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_json = json.dumps(history, ensure_ascii=False)
        cell = sheet.find(chat_id)
        if cell:
            row = cell.row
            sheet.update_cell(row, 2, title)
            sheet.update_cell(row, 3, history_json)
            sheet.update_cell(row, 4, timestamp)
        else:
            sheet.append_row([chat_id, title, history_json, timestamp])
    except Exception as e:
        st.warning(f"저장 실패(데이터 보존됨): {e}")

# ==========================================
# [3] UI 및 로직
# ==========================================
if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None
if "history" not in st.session_state:
    st.session_state["history"] = []
if "retry_trigger" not in st.session_state:
    st.session_state["retry_trigger"] = False
if "last_loaded_id" not in st.session_state:
    st.session_state["last_loaded_id"] = None

# --- 사이드바 ---
with st.sidebar:
    st.title("☁️ 클라우드 연구소")
    
    # [NEW] 보기 모드 설정 (PC vs 모바일)
    view_mode = st.radio("화면 모드", ["🖥️ 분할 (PC)", "📱 탭 (모바일)"], index=0)

    st.subheader("모델 설정")
    num_screens = st.number_input("비교할 모델 수", min_value=1, max_value=4, value=2)
    selected_models = []
    selected_model_names = [] # 탭 이름용
    
    model_names = list(MODEL_OPTIONS.keys())
    for i in range(num_screens):
        default_idx = i % len(model_names)
        m = st.selectbox(f"모델 {i+1}", model_names, index=default_idx, key=f"m_{i}")
        selected_models.append(MODEL_OPTIONS[m])
        selected_model_names.append(m)
    
    st.divider()
    
    # PDF 업로드
    st.subheader("📂 자료 업로드")
    uploaded_file = st.file_uploader("PDF/TXT 파일", type=["pdf", "txt"])
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
            st.error(f"읽기 실패: {e}")

    st.divider()

    # 채팅방 관리
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ 새 연구"):
            new_id = str(uuid.uuid4())[:8]
            st.session_state["current_chat_id"] = new_id
            st.session_state["history"] = []
            st.session_state["last_loaded_id"] = new_id
            save_chat_to_sheet(new_id, "새 연구", [])
            st.rerun()
    with col2:
        if st.button("🔄 재시도"):
            if st.session_state["history"]:
                st.session_state["retry_trigger"] = True
                st.rerun()

    # 목록 로드
    all_chats = load_all_chats_from_sheet()
    if all_chats:
        chat_options = {c['chat_id']: c['title'] for c in all_chats}
        if st.session_state["current_chat_id"] not in chat_options:
             if all_chats: st.session_state["current_chat_id"] = all_chats[0]['chat_id']
        
        sel_id = st.radio("기록", list(chat_options.keys()), 
                          format_func=lambda x: chat_options[x],
                          index=list(chat_options.keys()).index(st.session_state["current_chat_id"]) if st.session_state["current_chat_id"] else 0)
        
        if sel_id != st.session_state["last_loaded_id"]:
            st.session_state["current_chat_id"] = sel_id
            st.session_state["last_loaded_id"] = sel_id
            found = next((i for i in all_chats if i["chat_id"] == sel_id), None)
            if found:
                try: st.session_state["history"] = json.loads(found['history'])
                except: st.session_state["history"] = []
            st.rerun()

# --- 메인 화면 ---
current_title = "새 연구"
if all_chats and st.session_state["current_chat_id"]:
    found = next((c for c in all_chats if c['chat_id'] == st.session_state["current_chat_id"]), None)
    if found: current_title = found['title']

st.subheader(f"🧪 {current_title}")

history = st.session_state["history"]

# [NEW] 렌더링 함수: 모드에 따라 다르게 그리기
def render_responses(turn_data, is_streaming=False):
    # 탭 모드일 때
    if view_mode == "📱 탭 (모바일)":
        tabs = st.tabs(selected_model_names) # 모델 이름으로 탭 생성
        containers = []
        for i, tab in enumerate(tabs):
            with tab:
                if not is_streaming: # 과거 기록 출력
                    resp = turn_data["responses"].get(str(i))
                    if resp:
                        st.info(resp.get("text"))
                    else:
                        st.caption("응답 없음")
                containers.append(tab) # 스트리밍용 컨테이너 반환
        return containers

    # 분할 모드일 때 (PC)
    else:
        cols = st.columns(num_screens)
        containers = []
        for i, col in enumerate(cols):
            with col:
                st.caption(f"🤖 {selected_model_names[i]}")
                if not is_streaming:
                    resp = turn_data["responses"].get(str(i))
                    if resp:
                        st.info(resp.get("text"))
                containers.append(col)
        return containers

# 1. 과거 대화 출력
for turn in history:
    with st.chat_message("user"):
        st.write(turn["user"])
    render_responses(turn, is_streaming=False)

st.divider()

# --- 입력 처리 ---
prompt_process = None

if st.session_state["retry_trigger"] and history:
    last = history.pop()
    prompt_process = last["user"]
    st.session_state["history"] = history
    st.toast("재시도 중...")
    st.session_state["retry_trigger"] = False

with st.form("chat_form", clear_on_submit=True):
    txt_in = st.text_area("질문 입력 (Shift+Enter 줄바꿈)", height=100)
    if st.form_submit_button("전송 🚀") and txt_in:
        prompt_process = txt_in

# --- 응답 생성 ---
if prompt_process:
    final_prompt = prompt_process
    if context_text:
        final_prompt = f"문서 참고:\n{context_text}\n\n질문: {prompt_process}"
        st.info(f"📎 문서 포함됨 ({len(context_text)}자)")

    with st.chat_message("user"):
        st.write(prompt_process)

    # [NEW] 화면 모드에 맞는 컨테이너 가져오기
    # 빈 껍데기(turn_data)를 넘겨서 컨테이너 위치만 받아옴
    target_containers = render_responses({"responses": {}}, is_streaming=True)
    
    current_responses = {}
    recent_history = history[-10:]

    for i in range(num_screens):
        # 탭 모드든 분할 모드든, 위에서 받아온 컨테이너(target_containers)에 그리면 됨
        with target_containers[i]:
            model_id = selected_models[i]
            d_name = selected_model_names[i]
            
            # 탭 모드일 땐 캡션이 탭 이름에 있으니 생략 가능하지만, 명확성을 위해 표시
            if view_mode != "📱 탭 (모바일)": 
                pass # 이미 위에서 이름 출력함
            
            placeholder = st.empty()
            full_text = ""
            
            messages = [{"role": "system", "content": "전문적인 리서치 어시스턴트입니다."}]
            for t in recent_history:
                messages.append({"role": "user", "content": t["user"]})
                if str(i) in t["responses"]:
                    messages.append({"role": "assistant", "content": t["responses"][str(i)]["text"]})
            messages.append({"role": "user", "content": final_prompt})

            try:
                stream = client.chat.completions.create(model=model_id, messages=messages, stream=True)
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        full_text += chunk.choices[0].delta.content
                        placeholder.info(full_text + "▌")
                placeholder.info(full_text)
                current_responses[str(i)] = {"model_name": d_name, "text": full_text}
            except Exception as e:
                placeholder.error(f"Error: {e}")
                current_responses[str(i)] = {"model_name": d_name, "text": str(e)}

    # 저장
    if st.session_state["current_chat_id"]:
        new_turn = {"user": prompt_process, "responses": current_responses}
        st.session_state["history"].append(new_turn)
        save_title = current_title
        if len(st.session_state["history"]) == 1:
            save_title = prompt_process[:15] + "..."
        save_chat_to_sheet(st.session_state["current_chat_id"], save_title, st.session_state["history"])
        st.rerun()
