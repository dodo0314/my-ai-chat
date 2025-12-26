import streamlit as st
from openai import OpenAI  # OpenRouter는 OpenAI 라이브러리를 사용함
import base64
from io import BytesIO
from PIL import Image

# 1. 페이지 설정
st.set_page_config(page_title="꼬질이 탐지기", page_icon="🐶", layout="centered")
st.title("🐶 꼬질이 탐지기 (via OpenRouter)")
st.write("AI가 분석하는 우리 강아지 미용 시급도!")

# 2. 이미지 처리 함수 (OpenRouter용 Base64 변환)
def encode_image(image):
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# 3. API 키 설정 (Streamlit Secrets 사용)
if "OPENROUTER_API_KEY" in st.secrets:
    api_key = st.secrets["OPENROUTER_API_KEY"]
else:
    api_key = st.text_input("OpenRouter API 키를 입력하세요", type="password")

if api_key:
    # OpenRouter 클라이언트 설정
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://ggojil-detect.streamlit.app", # 나중에 실제 앱 주소로 변경
            "X-Title": "Ggojil Detect App",
        }
    )

    uploaded_file = st.file_uploader("강아지 사진 업로드 📸", type=["jpg", "jpeg", "png"])

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='분석 대기 중...', use_container_width=True)

        if st.button("🔍 꼬질도 진단 시작"):
            with st.spinner("OpenRouter를 통해 분석 중..."):
                try:
                    # 이미지를 base64로 변환
                    base64_image = encode_image(image)

                    # 4. OpenRouter API 호출 (Chat Completion 방식)
                    response = client.chat.completions.create(
                        model="google/gemini-2.5-flash", # OpenRouter 모델명 확인 필요
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": """
                                        너는 20년 경력의 반려견 미용 전문가야. 
                                        이 사진을 보고 다음 형식으로 분석해줘:
                                        
                                        1. **꼬질 지수 (0~100점)**: 100점에 가까울수록 미용 시급.
                                        2. **상태 분석**: 눈 가림, 털 엉킴 등.
                                        3. **원장님의 한마디**: 재치 있는 독설 혹은 조언.
                                        
                                        출력은 마크다운 형식으로 해줘.
                                        """
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}"
                                        }
                                    }
                                ]
                            }
                        ]
                    )
                    
                    # 결과 출력
                    result_text = response.choices[0].message.content
                    st.markdown(result_text)

                except Exception as e:
                    st.error(f"오류 발생: {e}")
else:
    st.info("API 키를 설정해주세요.")

