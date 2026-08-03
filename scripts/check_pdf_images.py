import fitz

def main():
    pdf_path = "data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf"
    doc = fitz.open(pdf_path)
    
    print(f"Total pages: {doc.page_count}\n")
    
    for i in range(min(3, doc.page_count)):
        page = doc[i]
        images = page.get_images(full=True)
        print(f"--- Page {i + 1} ---")
        print(f"Number of images: {len(images)}")
        
        for img in images:
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            print(f"  -> Image dimensions: {pix.width}x{pix.height} pixels")
        print()

if __name__ == "__main__":
    main()
