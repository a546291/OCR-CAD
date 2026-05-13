# 錯卷題庫系統 (Error Exam Question Bank System)

這是一個基於 Python Flask、PyMuPDF 與 Google Gemini AI 開發的智慧錯卷題庫系統。
旨在協助國中教師自動化處理 PDF 試卷，透過 AI 萃取並結構化題目與附圖，最後依據題型重新排版匯出成精美的 Word 試卷。

## ✨ 核心特色

- **📄 智慧 PDF 解析**：支援上傳原始電子檔 PDF，系統能自動循序讀取文字與圖片區塊。
- **🤖 Gemini AI 語意重構**：自動修正 OCR 辨識錯誤、錯字及排版問題，並將題目結構化（題幹、選項）。
- **🖼️ 完美圖文對應**：自動識別試卷中的附圖，並將其精準綁定在對應的題目段落中。
- **🌐 網址載入支援**：可直接貼上公開的 PDF 下載網址，系統會在背景自動下載並解析。
- **📝 專業 Word 匯出**：依據選擇題、填充題等「題型」自動分組，並保留原始邏輯順序匯出。

## 🛠️ 技術架構

- **後端 (Backend)**：Python 3.10+, Flask
- **資料庫 (Database)**：SQLite (輕量、免安裝)
- **AI 引擎**：Google Gemini 2.5 Flash API
- **PDF 處理**：PyMuPDF (fitz)
- **Word 產出**：python-docx
- **前端 (Frontend)**：Vanilla HTML, CSS, JavaScript

## 🚀 快速啟動

1. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```

2. **啟動伺服器**：
   ```bash
   python app.py
   ```

3. **瀏覽器訪問**：
   打開瀏覽器前往 `http://127.0.0.1:5000`

4. **設定 API Key**：
   在系統左側選單的「API 設定」中，輸入您的 Google Gemini API Key。

## ⚠️ 注意事項
- 請盡量使用「原始電子檔」（例如從 Word 直接另存新檔的 PDF），這能確保圖文分離精準。
- 「整頁掃描成大圖」的 PDF 無法將圖表獨立裁切，整個頁面將視為單一圖片。
