import streamlit as st
import pandas as pd
from PIL import Image
from io import BytesIO
import google.generativeai as genai
import anthropic
import base64
from streamlit_paste_button import paste_image_button
import os
import signal
import time

# ==========================================
# 1. 초기 세팅
# ==========================================
def init_app():
    st.set_page_config(page_title="기획/QA 초안 생성기 v2", layout="wide")
    st.title("⚡ 디스크립션 & TC 초안 생성기 v2")
    st.caption("기존 초안 생성 기능과, Claude 3.5 기반 실무 딥다이브 TC 추출 기능이 통합되었습니다.")

    # 세션 초기화 (탭1: 기존)
    if 'tab1_images' not in st.session_state:
        st.session_state['tab1_images'] = []
    if 'tab1_spec' not in st.session_state:
        st.session_state['tab1_spec'] = None
    if 'tab1_tc' not in st.session_state:
        st.session_state['tab1_tc'] = None

    # 세션 초기화 (탭2: 신규 실무용)
    if 'tab2_image' not in st.session_state:
        st.session_state['tab2_image'] = None
    if 'tab2_tc' not in st.session_state:
        st.session_state['tab2_tc'] = None

# ==========================================
# 2. AI 호출 로직 (Gemini & Claude)
# ==========================================
def run_gemini(api_key, prompt, images=[]):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')
    response = model.generate_content([prompt] + images)
    return response.text

def run_claude(api_key, prompt, image):
    client = anthropic.Anthropic(api_key=api_key)
    
    # 이미지를 Base64로 인코딩 (Claude 요구사항)
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    )
    return response.content[0].text

# ==========================================
# 3. 메인 UI (2개의 탭 분리)
# ==========================================
def main():
    init_app()
    
    with st.sidebar:
        st.header("🔑 API 키 설정")
        gemini_key = st.text_input("Gemini API Key", type="password")
        claude_key = st.text_input("Claude API Key (탭2 전용)", type="password")
        
        st.markdown("---")
        if st.button("❌ 프로그램 종료", use_container_width=True):
            st.warning("프로그램을 종료합니다...")
            time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)

    # 거대한 2개의 탭 생성
    tab1, tab2 = st.tabs(["⚡ 1. 빠른 초안 모드 (기존)", "🔬 2. 실무 딥다이브 TC 추출 (신규)"])

    # ------------------------------------------
    # TAB 1: 기존 빠른 초안 모드
    # ------------------------------------------
    with tab1:
        st.subheader("화면 캡처만으로 기획서와 TC 초안을 빠르게 잡습니다.")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            # ▼ 수정됨: key="btn1" 추가
            paste_res1 = paste_image_button(label="📋 화면 붙여넣기", background_color="#FF4B4B", key="btn1")
        with col2:
            if st.button("🗑️ 이미지 비우기"):
                st.session_state['tab1_images'] = []
                st.rerun()

        if paste_res1.image_data is not None:
            st.session_state['tab1_images'].append(paste_res1.image_data)
            
        if st.session_state['tab1_images']:
            st.image(st.session_state['tab1_images'][-1], width=300, caption="최근 추가된 이미지")
            
            c1, c2 = st.columns(2)
            if c1.button("📄 기능 명세서 생성 (Gemini)", use_container_width=True):
                if not gemini_key:
                    st.error("Gemini API 키를 입력하세요.")
                else:
                    prompt = "이 UI 이미지들을 분석해서 기능 명세서를 Markdown 표(No, 화면명, UI요소, 타입, 기능상세, 정책)로 작성해."
                    with st.spinner("명세서 작성 중..."):
                        st.session_state['tab1_spec'] = run_gemini(gemini_key, prompt, st.session_state['tab1_images'])
            
            if c2.button("🧪 테스트 케이스 생성 (Gemini)", use_container_width=True):
                if not gemini_key:
                    st.error("Gemini API 키를 입력하세요.")
                else:
                    prompt = "이 UI 이미지들의 흐름을 보고 TC를 Markdown 표(ID, 화면, 테스트항목, 사전조건, 단계, 기대결과)로 작성해."
                    with st.spinner("TC 작성 중..."):
                        st.session_state['tab1_tc'] = run_gemini(gemini_key, prompt, st.session_state['tab1_images'])

        if st.session_state['tab1_spec']:
            st.markdown("### 📄 기획 명세서 결과")
            st.markdown(st.session_state['tab1_spec'])
        if st.session_state['tab1_tc']:
            st.markdown("### 🧪 테스트 케이스 결과")
            st.markdown(st.session_state['tab1_tc'])

    # ------------------------------------------
    # TAB 2: 실무 딥다이브 TC 추출 모드
    # ------------------------------------------
    with tab2:
        st.subheader("작성된 [기획 정책]과 [피그마 디자인]을 교차 검증하여 결점 없는 TC를 뽑습니다.")
        
        col_req, col_img = st.columns(2)
        
        with col_req:
            st.markdown("**1. 기획 명세서 / 정책 입력**")
            req_text = st.text_area("엑셀이나 노션에 작성한 정책을 그대로 복붙하세요.", height=300)
            
        with col_img:
            st.markdown("**2. 피그마 최종 디자인 캡처 (Win+Shift+S)**")
            # ▼ 수정됨: key="btn2" 추가
            paste_res2 = paste_image_button(label="📋 디자인 화면 붙여넣기", background_color="#2E86C1", key="btn2")
            
            if paste_res2.image_data is not None:
                st.session_state['tab2_image'] = paste_res2.image_data
                
            if st.session_state['tab2_image']:
                st.image(st.session_state['tab2_image'], use_container_width=True)
                if st.button("🗑️ 디자인 지우기"):
                    st.session_state['tab2_image'] = None
                    st.rerun()

        st.divider()
        
        # 모델 선택 및 실행
        st.markdown("**3. AI 모델 선택 및 추출**")
        model_choice = st.radio("TC 추출에 사용할 뇌를 선택하세요:", ["🧠 Claude 3.5 Sonnet (논리력 최강, 추천)", "🚀 Gemini 1.5 Pro (속도/가성비)"], horizontal=True)
        
        if st.button("🔥 무자비한 TC 추출 시작", type="primary", use_container_width=True):
            if not req_text or not st.session_state['tab2_image']:
                st.warning("기획 정책 텍스트와 피그마 캡처 이미지를 모두 넣어주세요.")
            else:
                prompt = f"""
                당신은 10년 차 악마 같은 QA 리드입니다.
                다음 제공되는 [기획 명세서 정책]과 첨부된 [피그마 UI 디자인]을 교차 검증하세요.
                
                [기획 명세서 정책]
                {req_text}
                
                [작성 지침]
                1. 명세서에 적힌 정책이 화면에서 어떻게 동작해야 하는지 파악하여 테스트 케이스(TC)를 작성하세요.
                2. 정상 동작(Happy Path)은 물론이고, 에지 케이스(예외 처리, 통신 지연, 빈 화면, 극단적 입력값 등)를 집요하게 파고드세요.
                3. 마크다운 표 형식으로 깔끔하게 출력하세요. (ID, 구분, 테스트 항목, 사전 조건, 테스트 스텝, 기대 결과)
                """
                
                with st.spinner(f"{model_choice.split(' ')[1]}가 정책과 화면을 뜯어보는 중..."):
                    try:
                        if "Claude" in model_choice:
                            if not claude_key: st.error("왼쪽에 Claude API 키를 입력하세요.")
                            else: st.session_state['tab2_tc'] = run_claude(claude_key, prompt, st.session_state['tab2_image'])
                        else:
                            if not gemini_key: st.error("왼쪽에 Gemini API 키를 입력하세요.")
                            else: st.session_state['tab2_tc'] = run_gemini(gemini_key, prompt, [st.session_state['tab2_image']])
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

        # 결과 출력
        if st.session_state['tab2_tc']:
            st.success("✅ 교차 검증 TC 추출 완료!")
            st.markdown(st.session_state['tab2_tc'])

if __name__ == "__main__":
    main()