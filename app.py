import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import io
import time
import random
import re
from pypdf import PdfReader

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="JLP x Google | Growth Engine",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. LUXURY RETAIL x GOOGLE CSS ---
st.markdown("""
<style>
    /* IMPORTS */
    @import url('https://fonts.googleapis.com/css2?family=Gill+Sans+MT&family=Google+Sans:wght@400;500;700&display=swap');

    /* BASE THEME */
    html, body, [class*="css"] {
        font-family: 'Google Sans', sans-serif;
        background-color: #f9f9f9; /* Soft grey background for contrast */
        color: #1c1c1c;
    }

    /* REMOVE CLUTTER */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}

    /* PREMIUM CHAT CARDS */
    .stChatInput {
        border-radius: 30px !important;
        border: 1px solid #e0e0e0 !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        background-color: white;
    }
    
    /* The Chat Bubble itself - Now a "Card" */
    .stChatMessage {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 25px;
        font-size: 15px;
        line-height: 1.7;
        box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        margin-bottom: 15px;
    }
    
    /* LINK BUTTONS (The Star of the Show) */
    .file-link {
        display: inline-block;
        background-color: #1c1c1c; /* JLP Black */
        color: #ffffff !important;
        padding: 10px 20px;
        border-radius: 0px; 
        text-decoration: none;
        font-weight: 600;
        font-size: 13px;
        letter-spacing: 1px;
        margin-top: 15px;
        margin-right: 10px;
        transition: all 0.2s ease;
        text-transform: uppercase;
        border: 1px solid #1c1c1c;
    }
    .file-link:hover {
        background-color: #ffffff;
        color: #1c1c1c !important;
        cursor: pointer;
    }

    /* SIDEBAR CARD */
    .tip-card {
        background-color: #ffffff;
        padding: 20px;
        border-left: 4px solid #4285F4;
        margin-bottom: 20px;
        border-radius: 0 8px 8px 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    /* JLP LOGO RECREATION (CSS) */
    .jlp-logo-box {
        font-family: 'Gill Sans', 'Gill Sans MT', Calibri, sans-serif;
        color: #000;
        text-align: right;
        line-height: 1;
        text-transform: uppercase;
    }
    .jlp-main {
        font-size: 32px;
        font-weight: 600;
        letter-spacing: 2px;
        display: block;
    }
    .jlp-sub {
        font-size: 14px;
        font-weight: 400;
        letter-spacing: 3px;
        margin-top: 5px;
        display: block;
    }
    
    /* VERTICAL ALIGNMENT HELPER */
    div[data-testid="column"] {
        display: flex;
        align-items: center; 
        justify-content: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. CREDENTIALS ---
FOLDER_ID = "1km4pPoH4Gqa47Aug0tW1DR4ElkRvh72k" 
GEMINI_API_KEY = "AIzaSyB4ZO0yEI2ApKb4XBKN1idyUEjav8FuFCI"
CLIENT_PASSWORD = "Google2025!" 

# --- 4. BACKEND LOGIC ---
@st.cache_resource
def get_drive_service():
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    if os.path.exists("service_account.json"):
        creds = service_account.Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    elif "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    else: return None
    return build('drive', 'v3', credentials=creds)

def get_working_model():
    """Auto-discovers the best available model to prevent 404 Errors."""
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priorities = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        for p in priorities:
            for m in available_models:
                if p in m: return genai.GenerativeModel(m)
        if available_models: return genai.GenerativeModel(available_models[0])
        return genai.GenerativeModel('gemini-1.5-flash')
    except:
        return genai.GenerativeModel('gemini-1.5-flash')

def list_files(service, folder_id):
    try:
        results = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name, mimeType, webViewLink)").execute()
        return results.get('files', [])
    except: return []

def read_file(service, file_id, mime_type):
    try:
        content = None
        if "spreadsheet" in mime_type or mime_type.endswith("sheet"):
            if "application/vnd.google-apps.spreadsheet" in mime_type:
                request = service.files().export_media(fileId=file_id, mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else: request = service.files().get_media(fileId=file_id)
            data = request.execute()
            df = pd.read_excel(io.BytesIO(data))
            content = df.head(50).to_string()
        elif "presentation" in mime_type or "pdf" in mime_type:
            if "presentation" in mime_type: request = service.files().export_media(fileId=file_id, mimeType="application/pdf")
            else: request = service.files().get_media(fileId=file_id)
            data = request.execute()
            reader = PdfReader(io.BytesIO(data))
            content = "".join([page.extract_text() + "\n" for page in reader.pages])
        return content
    except: return None

# --- KNOWLEDGE BASE BUILDER ---
@st.cache_data(ttl=600) 
def build_knowledge_base(_service, folder_id):
    all_files = list_files(_service, folder_id)
    supported = [f for f in all_files if any(x in f['mimeType'] for x in ['spreadsheet', 'presentation', 'pdf', 'sheet'])]
    
    global_context = ""
    file_map = {} 
    
    progress_bar = st.progress(0, text="Syncing secure documents...")
    
    for i, f in enumerate(supported):
        progress_bar.progress((i + 1) / len(supported), text=f"Reading: {f['name']}...")
        content = read_file(_service, f['id'], f['mimeType'])
        if content:
            # We explicitly label the LINK here so the AI sees it
            global_context += f"\n\n=== DOCUMENT START: {f['name']} ===\n"
            global_context += f"FILE_LINK: {f.get('webViewLink', '#')}\n" 
            global_context += f"CONTENT:\n{content}\n"
            global_context += "=== DOCUMENT END ===\n"
            file_map[f['name']] = f.get('webViewLink', '#')
            
    progress_bar.empty()
    return global_context, file_map

def generate_with_backoff(model, prompt):
    for attempt in range(4): 
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                wait_time = (attempt + 1) * 6
                with st.spinner(f"⚡ High Traffic: Waiting {wait_time}s..."):
                    time.sleep(wait_time)
            elif "404" in error_msg:
                return "⚠️ System Config Error: The selected AI model is not available. Please refresh."
            else: return f"Error: {str(e)}"
    return "⚠️ Server busy. Please wait 1 min."

def extract_and_render_links(text):
    """
    Scans text for Markdown links [Title](URL) and extracts them 
    to render as Premium Buttons.
    """
    # Regex to find [Title](URL)
    links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', text)
    
    # Render Text first (we clean the links from the text if needed, or leave them)
    # Ideally, we leave the text as is, and append buttons below.
    st.markdown(text)
    
    if links:
        st.write("") # Spacer
        cols = st.columns(len(links) + 2) # Create columns for buttons
        for i, (title, url) in enumerate(links):
            # Render specific button
            # We clean the title to be short "VIEW SOURCE" if it's too long
            btn_label = "VIEW SOURCE FILE" if len(title) > 20 else title.upper()
            
            # Use columns to place buttons side by side if multiple
            with cols[i]:
                st.markdown(f"<a href='{url}' target='_blank' class='file-link'>{btn_label} &rarr;</a>", unsafe_allow_html=True)

# --- 5. THE EXPERIENCE (UI) ---
def main():
    if "authenticated" not in st.session_state: st.session_state.authenticated = False
    google_logo = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Google_2015_logo.svg/368px-Google_2015_logo.svg.png"

    # --- LOGIN SCREEN ---
    if not st.session_state.authenticated:
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            lc1, lc2, lc3 = st.columns([4, 1, 3])
            with lc1:
                st.markdown("""<div class="jlp-logo-box"><span class="jlp-main">JOHN LEWIS</span><span class="jlp-sub">& PARTNERS</span></div>""", unsafe_allow_html=True)
            with lc2: st.markdown("<h1 style='text-align: center; color: #ccc; margin:0;'>&times;</h1>", unsafe_allow_html=True)
            with lc3: st.image(google_logo, width=140)
            st.markdown("<br><p style='text-align: center; color: #666; letter-spacing: 2px; font-size: 12px; text-transform: uppercase;'>Strategic Growth Portal</p><br>", unsafe_allow_html=True)
            pwd = st.text_input("Enter Access Key", type="password", placeholder="••••••••")
            if pwd == CLIENT_PASSWORD: st.session_state.authenticated = True; st.rerun()
        return

    # --- MAIN DASHBOARD ---
    service = get_drive_service()
    if "model" not in st.session_state: st.session_state.model = get_working_model()

    # SIDEBAR
    with st.sidebar:
        st.markdown("### 📈 Growth Academy")
        tips = ["**Did you know?**\nCampaigns limited by budget miss out on 20% of converting traffic on average.", "**Pro Tip:**\nUse 'Target ROAS' with uncapped budgets to capture all profitable demand.", "**Holiday Insight:**\nSearch demand spikes 48h before a sale."]
        st.markdown(f"""<div class="tip-card">{random.choice(tips)}</div>""", unsafe_allow_html=True)
        st.divider()
        
        # Admin Diagnostics
        with st.expander("🔧 Admin Diagnostics"):
            if service:
                debug_files = list_files(service, FOLDER_ID)
                if debug_files: st.success(f"✅ Connected: {len(debug_files)} files found.")
                else: st.error("❌ No files found. Check Permissions.")
        
        if st.button("🔒 Logout"): st.session_state.authenticated = False; st.rerun()

    # HERO HEADER
    h1, h2, h3, h4 = st.columns([3, 0.5, 1.5, 4]) 
    with h1: st.markdown("""<div class="jlp-logo-box"><span class="jlp-main">JOHN LEWIS</span><span class="jlp-sub">& PARTNERS</span></div>""", unsafe_allow_html=True)
    with h2: st.markdown("<h2 style='text-align: center; color: #ccc; margin:0;'>&times;</h2>", unsafe_allow_html=True)
    with h3: st.image(google_logo, width=130)
    
    st.markdown("## Welcome to your Growth Command Center")
    st.markdown("Ask questions about your media spend, missed opportunities, and demand trends.")
    st.divider()
    
    # --- LOAD ALL DATA ---
    if "knowledge_base" not in st.session_state:
        with st.spinner("Initializing Secure Data Environment..."):
            kb_text, file_map = build_knowledge_base(service, FOLDER_ID)
            st.session_state.knowledge_base = kb_text
            st.session_state.file_map = file_map
            if not kb_text:
                st.error("❌ No readable files found in the Drive Folder.")

    # CHAT HISTORY
    if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "Welcome. I have read all your secure reports. How can we drive growth today?"}]
    
    for msg in st.session_state.messages: 
        with st.chat_message(msg["role"]):
            # Use the new renderer for history too
            if msg["role"] == "assistant":
                extract_and_render_links(msg["content"])
            else:
                st.markdown(msg["content"])

    # INPUT
    if query := st.chat_input("E.g., Summarize the missed opportunities across all reports"):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"): st.markdown(query)

        with st.chat_message("assistant"):
            step_box = st.status("⚡ Analyzing Global Data...", expanded=True)
            step_box.write("🧠 Scanning all documents...")
            
            final_prompt = f"""
            You are a Strategic Growth Partner for John Lewis & Google.
            USER STATUS: Verified Admin.
            
            GLOBAL DATA CONTEXT:
            {st.session_state.knowledge_base}
            
            USER QUESTION: {query}
            
            INSTRUCTIONS:
            1. Search across ALL the documents provided above to find the answer.
            2. CRITICAL: When referencing a specific document, YOU MUST PROVIDE THE LINK using this EXACT Markdown format: [📄 Open Source File](FILE_LINK).
            3. Do not just say "click the link", actually generate the markdown link syntax.
            4. Tone: Premium, Strategic, Encouraging.
            """
            
            ans_text = generate_with_backoff(st.session_state.model, final_prompt)
            
            step_box.update(label="Analysis Complete", state="complete", expanded=False)
            
            # Use the Smart Renderer to show buttons
            extract_and_render_links(ans_text)
            
            st.session_state.messages.append({"role": "assistant", "content": ans_text})

if __name__ == "__main__": main()