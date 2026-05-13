import os
import json
import threading
import urllib.request
import urllib.parse
import uuid
from flask import Flask, request, jsonify, send_file, send_from_directory
from database import init_db, get_db, SUBJECTS, QUESTION_TYPES
from pipeline import process_pdf_pipeline
from exporter import export_to_word

app = Flask(__name__, static_folder="static", static_url_path="")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── 處理任務狀態追蹤 ────────────────────────────────────────────────────────────
jobs: dict[str, dict] = {}  # job_id -> {status, result, error}


def run_pipeline(job_id: str, pdf_path: str, api_key: str):
    try:
        jobs[job_id]["status"] = "processing"
        result = process_pdf_pipeline(pdf_path, api_key)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


# ── 前端頁面 ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/images/<q_id>/<filename>")
def serve_image(q_id, filename):
    img_dir = os.path.join(UPLOAD_DIR, "images", q_id)
    return send_from_directory(img_dir, filename)

# ── API: 上傳 PDF ───────────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload():
    auth_header = request.headers.get("Authorization", "")
    api_key = auth_header.replace("Bearer ", "").strip()
    if not api_key:
        return jsonify({"error": "未提供 API Key"}), 401

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "未選擇任何檔案"}), 400

    started_jobs = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            continue
        safe_name = f.filename
        pdf_path = os.path.join(UPLOAD_DIR, safe_name)
        f.save(pdf_path)

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        jobs[job_id] = {"status": "queued"}
        threading.Thread(target=run_pipeline, args=(job_id, pdf_path, api_key)).start()
        started_jobs.append({"job_id": job_id, "filename": safe_name})

    return jsonify({"jobs": started_jobs})

# ── API: 從 URL 載入 PDF ───────────────────────────────────────────────────────
@app.route("/api/upload-url", methods=["POST"])
def upload_url():
    auth_header = request.headers.get("Authorization", "")
    api_key = auth_header.replace("Bearer ", "").strip()
    if not api_key:
        return jsonify({"error": "未提供 API Key"}), 401

    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "網址不得為空"}), 400

    try:
        # 簡單判斷檔名
        parsed = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename or not filename.lower().endswith(".pdf"):
            filename = f"url_download_{uuid.uuid4().hex[:6]}.pdf"

        pdf_path = os.path.join(UPLOAD_DIR, filename)

        # 下載檔案
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get_content_type()
            
            # 若不是 PDF，阻擋並提示
            if content_type != 'application/pdf' and not url.lower().endswith('.pdf'):
                return jsonify({"error": f"此連結指向網頁 ({content_type}) 而非原始 PDF 檔案，請提供「直接下載連結」。"}), 400

            with open(pdf_path, 'wb') as out_file:
                out_file.write(response.read())

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        jobs[job_id] = {"status": "queued"}
        threading.Thread(target=run_pipeline, args=(job_id, pdf_path, api_key)).start()

        return jsonify({"jobs": [{"job_id": job_id, "filename": filename}]})
    except Exception as e:
        return jsonify({"error": f"下載失敗: {str(e)}"}), 500


# ── API: 查詢處理進度 ───────────────────────────────────────────────────────────
@app.route("/api/status/<job_id>")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ── API: 取得題庫列表 ───────────────────────────────────────────────────────────
@app.route("/api/questions")
def get_questions():
    subject = request.args.get("subject", "")
    q_type = request.args.get("type", "")
    keyword = request.args.get("keyword", "")
    source_file = request.args.get("source_file", "")

    conn = get_db()
    query = "SELECT id, source_file, created_at, exported_at, subject, type, stem, options FROM questions WHERE 1=1"
    params = []

    if subject:
        query += " AND subject = ?"
        params.append(subject)
    if q_type:
        query += " AND type = ?"
        params.append(q_type)
    if source_file:
        query += " AND source_file = ?"
        params.append(source_file)
    if keyword:
        query += " AND stem LIKE ?"
        params.append(f"%{keyword}%")

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "source_file": r["source_file"],
            "created_at": r["created_at"],
            "exported_at": r["exported_at"],
            "subject": r["subject"],
            "type": r["type"],
            "stem": r["stem"][:120] + ("..." if len(r["stem"]) > 120 else ""),
            "options": json.loads(r["options"])
        })

    return jsonify({"questions": result, "total": len(result)})


# ── API: 取得科目 / 題型清單（供 UI 篩選器）──────────────────────────────────────
@app.route("/api/meta")
def get_meta():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT source_file FROM questions").fetchall()
    source_files = [r["source_file"] for r in rows]
    conn.close()
    return jsonify({"subjects": SUBJECTS, "types": QUESTION_TYPES, "source_files": source_files})


# ── API: 匯出選取題目為 Word ────────────────────────────────────────────────────
@app.route("/api/export", methods=["POST"])
def export():
    data = request.get_json()
    question_ids = data.get("question_ids", [])
    title = data.get("title", "試卷")

    if not question_ids:
        return jsonify({"error": "未選取任何題目"}), 400

    conn = get_db()
    try:
        placeholders = ",".join(["?"] * len(question_ids))
        conn.execute(f"UPDATE questions SET exported_at = datetime('now','localtime') WHERE id IN ({placeholders})", question_ids)
        conn.commit()
    finally:
        conn.close()

    docx_path = export_to_word(question_ids, title)
    return send_file(docx_path, as_attachment=True,
                     download_name=f"{title}.docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ── API: 批次刪除選取題目 ────────────────────────────────────────────────────────
@app.route("/api/questions/batch", methods=["DELETE"])
def delete_questions_batch():
    data = request.get_json()
    question_ids = data.get("question_ids", [])
    if not question_ids:
        return jsonify({"error": "未選取任何題目"}), 400

    conn = get_db()
    try:
        placeholders = ",".join(["?"] * len(question_ids))
        
        # 刪除圖片檔案
        img_rows = conn.execute(f"SELECT image_path FROM question_images WHERE question_id IN ({placeholders})", question_ids).fetchall()
        for row in img_rows:
            if os.path.exists(row["image_path"]):
                os.remove(row["image_path"])
                
        conn.execute(f"DELETE FROM question_images WHERE question_id IN ({placeholders})", question_ids)
        conn.execute(f"DELETE FROM questions WHERE id IN ({placeholders})", question_ids)
        conn.commit()
    finally:
        conn.close()
        
    return jsonify({"success": True})



# ── API: 刪除題目 ───────────────────────────────────────────────────────────────
@app.route("/api/questions/<q_id>", methods=["DELETE"])
def delete_question(q_id: str):
    conn = get_db()
    conn.execute("DELETE FROM questions WHERE id = ?", (q_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "已刪除"})


if __name__ == "__main__":

    init_db()
    print("[OK] System started: http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
