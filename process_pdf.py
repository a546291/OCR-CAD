import fitz  # PyMuPDF
import os
import sys

def extract_pdf(pdf_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    doc = fitz.open(pdf_path)
    md_content = f"# PDF Extraction: {os.path.basename(pdf_path)}\n\n"
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        md_content += f"## Page {page_num + 1}\n\n"
        
        # 1. Extract text (PyMuPDF retains order generally top-to-bottom)
        text = page.get_text("text")
        if text.strip():
            md_content += f"{text}\n\n"
        else:
            md_content += "*[No text found on this page or it's a scanned image]*\n\n"
            
        # 2. Extract images
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list, start=1):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            image_filename = f"page_{page_num+1}_img_{img_index}.{image_ext}"
            image_filepath = os.path.join(output_dir, image_filename)
            
            with open(image_filepath, "wb") as f:
                f.write(image_bytes)
                
            md_content += f"![Image {img_index}](./{os.path.basename(output_dir)}/{image_filename})\n\n"
            
    # Save markdown
    md_filepath = os.path.join(output_dir, "output.md")
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"Extraction complete! Saved to {md_filepath}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_pdf.py <pdf_path>")
    else:
        target_pdf = sys.argv[1]
        out_folder = target_pdf.replace('.pdf', '_extracted')
        extract_pdf(target_pdf, out_folder)
