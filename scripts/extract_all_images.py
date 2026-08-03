import fitz
import os

def main():
    pdf_path = "data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf"
    output_dir = "data/outputs/images"
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    
    # Extract images from the first 3 pages
    for page_num in range(min(3, doc.page_count)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        
        print(f"\n--- Processing Page {page_num + 1} ---")
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            filename = f"page{page_num+1}_img{img_index+1}.{image_ext}"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            print(f"Saved: {filepath}")
            
    doc.close()
    print("\n✅ Image extraction complete!")

if __name__ == "__main__":
    main()
