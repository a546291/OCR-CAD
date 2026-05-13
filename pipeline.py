import fitz  # PyMuPDF
import re
import os
import json
import uuid
import shutil
from datetime import datetime
from google import genai
from google.genai import types
from database import get_db, SUBJECTS, IMAGES_DIR

# ── Gemini API 設定 ────────────────────────────────────────────────────────────
# API Key 現在由前端傳遞，不再從伺服器全域變數讀取

SYSTEM_PROMPT = """你是一位台灣國中階段的試卷辨識與整理助理。
請依照以下規則處理輸入的試卷原始文字：

1. 判斷此份試卷的科目，只能從以下九科中選擇一科：
   國文、英文、數學、理化、生物、地球科學、歷史、地理、公民
2. 識別每一道獨立題目，判斷題型（選擇題 / 填充題 / 問答題 / 閱讀測驗 / 寫作題 / 其他）
3. 修正 OCR 辨識錯誤、錯字及排版問題，根據原意重新整理語句使其通順
4. 閱讀測驗的文章段落屬於題幹，應包含在對應題目中
5. 請忽略題目中原有的空白答案欄、填答底線、作答說明等非題目本身的內容
6. ⚠️ 嚴格禁止將考題中的「注音」翻譯或替換為「國字」！若題目中包含注音符號（如「ㄞˋ」或「ㄆㄧㄥˊ」），這是國文科寫國字的考題，請絕對「保留原始注音符號與原句結構」。例如：若原卷為「方興未ㄞˋ」，輸出必須保留「方興未ㄞˋ」，絕對不可擅自解答並輸出為「方興未艾」。
7. ⚠️ 若原始文字中包含圖片標記（如 `[IMAGE: xxx.jpeg]`），這代表該處有一張附圖。請務必判斷該圖片屬於哪一道題目（通常緊跟在某題題幹或選項旁），並將該圖片標記完整保留於該題的 `stem` (題幹) 或選項之中！絕對不要省略圖片標記。

請以 JSON 陣列格式回傳，每道題目一個物件，格式如下：
[
  {
    "subject": "英文",
    "type": "選擇題",
    "stem": "題幹文字（含閱讀文章）",
    "options": ["(A) ...", "(B) ...", "(C) ...", "(D) ..."]
  }
]

注意：
- options 若為填充題或問答題，請給空陣列 []
- 只回傳 JSON，不要有任何額外說明文字
"""

# ── 清理填答空白 ────────────────────────────────────────────────────────────────
BLANK_PATTERNS = [
    r'[（(]\s*[）)]',               # 空括號 （） ()
    r'_{2,}',                        # 底線填空 ___
    r'＿{2,}',                       # 全型底線
    r'【\s*】',                      # 空方框
    r'□+',                           # 方格
    r'^(姓名|座號|班級|姓|名|號)\s*[:：]?\s*$',  # 個人資料欄位
    r'^\s*ERA\s*\(.*?\)\s*$',        # 亂碼/頁首尾殘留
]
BLANK_RE = [re.compile(p, re.MULTILINE) for p in BLANK_PATTERNS]


def clean_raw_text(text: str) -> str:
    """去除填答空白與無意義字元"""
    for pattern in BLANK_RE:
        text = pattern.sub('', text)
    # 壓縮多餘空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── PDF 提取 ────────────────────────────────────────────────────────────────────
def extract_pdf(pdf_path: str) -> dict:
    """從 PDF 提取文字與圖片，回傳 {text, image_paths}"""
    doc = fitz.open(pdf_path)
    full_text = ""
    image_paths = []

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    img_tmp_dir = os.path.join(IMAGES_DIR, "_tmp", base_name)
    os.makedirs(img_tmp_dir, exist_ok=True)

    img_index = 1
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        blocks = page.get_text("dict")["blocks"]
        
        for block in blocks:
            if block["type"] == 0:  # text
                for line in block["lines"]:
                    for span in line["spans"]:
                        full_text += span["text"]
                full_text += "\n"
            elif block["type"] == 1:  # image
                try:
                    base_image = block["image"]
                    ext = block["ext"]
                    img_filename = f"page_{page_num+1}_img_{img_index}.{ext}"
                    img_path = os.path.join(img_tmp_dir, img_filename)
                    with open(img_path, "wb") as f:
                        f.write(base_image)
                    image_paths.append(img_path)
                    
                    # 插入圖片標記
                    full_text += f"\n[IMAGE: {img_filename}]\n"
                    img_index += 1
                except Exception as e:
                    print(f"Error extracting image block: {e}")

    cleaned_text = clean_raw_text(full_text)
    return {"text": cleaned_text, "image_paths": image_paths, "source": base_name}


# ── Gemini 語意修正 ─────────────────────────────────────────────────────────────
def parse_with_gemini(raw_text: str, api_key: str) -> list[dict]:
    """Call Gemini API to parse the exam, return structured question list"""
    if not api_key:
        raise ValueError("Please provide a valid GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)
    prompt = SYSTEM_PROMPT + "\n\n---試卷原始文字---\n" + raw_text

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw_json = response.text.strip()

    # Remove markdown code block if Gemini wraps with ```json
    raw_json = re.sub(r'^```json\s*', '', raw_json)
    raw_json = re.sub(r'\s*```$', '', raw_json)

    questions = json.loads(raw_json)
    return questions


# ── 儲存至資料庫 ────────────────────────────────────────────────────────────────
def save_questions(questions: list[dict], source_file: str, image_paths: list[str]) -> list[str]:
    """將題目存入 SQLite，並分配圖片，回傳新增的 question id 列表"""
    conn = get_db()
    cur = conn.cursor()
    saved_ids = []

    for index, q in enumerate(questions, start=1):
        q_id = f"q_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        subject = q.get("subject", "其他")
        q_type = q.get("type", "其他")
        stem = q.get("stem", "")
        options_str = json.dumps(q.get("options", []), ensure_ascii=False)

        # 尋找並提取 [IMAGE: xxx] 標記
        img_pattern = re.compile(r"\[IMAGE:\s*(.+?)\]")
        stem_images = img_pattern.findall(stem)
        options_images = img_pattern.findall(options_str)
        q_images = list(set(stem_images + options_images))
        
        # ⚠️ 注意：不要將標記移除，保留在字串中以便匯出和 UI 知道精確插入點

        # 驗證科目
        if subject not in SUBJECTS:
            subject = "其他"

        cur.execute("""
            INSERT INTO questions (id, source_file, order_index, subject, type, stem, options)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (q_id, source_file, index, subject, q_type, stem, options_str))

        # 處理此題的圖片
        if q_images:
            q_img_dir = os.path.join(IMAGES_DIR, q_id)
            os.makedirs(q_img_dir, exist_ok=True)
            for img_name in q_images:
                # 尋找原始路徑
                src_path = next((p for p in image_paths if os.path.basename(p) == img_name), None)
                if src_path and os.path.exists(src_path):
                    dst_path = os.path.join(q_img_dir, img_name)
                    shutil.copy2(src_path, dst_path)
                    cur.execute("""
                        INSERT INTO question_images (question_id, image_path)
                        VALUES (?, ?)
                    """, (q_id, dst_path))

        saved_ids.append(q_id)

    conn.commit()
    conn.close()
    return saved_ids


# ── 主流程（供 Flask 呼叫）──────────────────────────────────────────────────────
def process_pdf_pipeline(pdf_path: str, api_key: str) -> dict:
    """完整處理一個 PDF，回傳結果摘要"""
    source_file = os.path.basename(pdf_path)

    # 1. 提取
    extracted = extract_pdf(pdf_path)

    # 2. Gemini 解析
    questions = parse_with_gemini(extracted["text"], api_key)

    # 3. 存入資料庫
    saved_ids = save_questions(questions, source_file, extracted["image_paths"])

    return {
        "source_file": source_file,
        "total_questions": len(saved_ids),
        "question_ids": saved_ids
    }
