import fitz
import os

def main():
    pdf_path = "data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf"
    output_dir = "data/outputs/pages"
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    
    print(f"Rendering {doc.page_count} pages at 300 DPI...\n")
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        
        # Render page to an image at 300 DPI (high quality for math formulas)
        pix = page.get_pixmap(dpi=300)
        
        filename = f"page_{page_num + 1:02d}.png"
        filepath = os.path.join(output_dir, filename)
        
        pix.save(filepath)
        print(f"Saved: {filepath} ({pix.width}x{pix.height} pixels)")
        
    doc.close()
    print("\n✅ Page rendering complete!")

if __name__ == "__main__":
    main()
