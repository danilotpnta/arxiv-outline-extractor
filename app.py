import streamlit as st
import re
import arxiv
import requests
import fitz
from io import BytesIO

def extract_pdf_toc(pdf_bytes):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        toc = doc.get_toc()
        return toc if toc else None
    except Exception as e:
        st.error(f"Error extracting TOC: {e}")
        return None

def extract_headings_regex(pdf_bytes, max_pages=5):
    headings = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
        return headings

    heading_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)(?:\s+)(.+)$', re.MULTILINE)
    
    for page_num in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_num)
        text = page.get_text()
        for match in heading_pattern.finditer(text):
            numbering = match.group(1)
            title = match.group(2).strip()
            level = numbering.count('.') + 1
            headings.append((level, f"{numbering} {title}", page_num + 1))
    
    return headings

def generate_markdown_outline(headings):
    markdown_lines = []
    for level, heading, _ in headings:
        header_line = f"{'#' * level} {heading}"
        markdown_lines.append(header_line)
    return "\n".join(markdown_lines)

def add_numbering_to_outline(outline):
    numbered_outline = []
    counters = {}
    appendices_started = False
    letter_counter = ord('A')
    last_final_num = 6

    for line in outline.split("\n"):
        heading_level = line.count('#')
        if heading_level == 0:
            numbered_outline.append(line)
            continue

        if not appendices_started:
            conclusion_keywords = ["Conclusion", "Concluding", "Final Remarks", "Summary"]
            if any(keyword in line for keyword in conclusion_keywords):
                appendices_started = True
                numbered_outline.append(f"# {last_final_num} {line.lstrip('#').strip()}")
                continue

        if not appendices_started:
            if heading_level not in counters:
                counters[heading_level] = 0
            if heading_level > 1:
                for i in range(heading_level + 1, max(counters.keys()) + 1):
                    counters[i] = 0

            counters[heading_level] += 1
            numbering = '.'.join(str(counters[i]) for i in range(1, heading_level + 1))
            numbered_outline.append(f"{'#' * heading_level} {numbering} {line.lstrip('#').strip()}")

        else:
            appendix_prefix = chr(letter_counter)
            numbered_outline.append(f"# {appendix_prefix} {line.lstrip('#').strip()}")
            letter_counter += 1

            if heading_level > 1:
                numbering = f"{appendix_prefix}." + ".".join(str(counters[i]) for i in range(2, heading_level + 1))
                numbered_outline.append(f"{'#' * heading_level} {numbering} {line.lstrip('#').strip()}")
                counters[heading_level] += 1

    return "\n".join(numbered_outline)

def get_arxiv_id(url):
    match = re.search(r'arxiv\.org/(abs|pdf)/([^\?/]+)', url)
    if match:
        return match.group(2)
    return None

def main():
    st.title("Arxiv Paper Outline Extractor")

    url_input = st.text_input("Enter the arXiv paper URL:")

    if url_input:
        arxiv_id = get_arxiv_id(url_input)
        if not arxiv_id:
            st.error("Could not extract arXv ID. Please check your URL.")
        else:
            st.info(f"Extracted arXv ID: {arxiv_id}")

            try:
                search = arxiv.Search(id_list=[arxiv_id])
                paper = next(search.results())
            except StopIteration:
                st.error("No results found for this arXv ID.")
            except Exception as e:
                st.error(f"Error fetching metadata: {e}")
            else:
                st.header(paper.title)
                st.subheader("Abstract")
                st.write(paper.summary)

                try:
                    response = requests.get(paper.pdf_url)
                    response.raise_for_status()
                    pdf_bytes = response.content
                except Exception as e:
                    st.error(f"Error downloading PDF: {e}")
                    pdf_bytes = None

                if pdf_bytes:
                    headings = extract_pdf_toc(pdf_bytes)
                    if not headings:
                        st.info("Embedded TOC not found; attempting regex-based extraction.")
                        headings = extract_headings_regex(pdf_bytes, max_pages=7)
                        if not headings:
                            st.info("No headings found via regex extraction.")

                    if headings:
                        markdown_outline = generate_markdown_outline(headings)
                        numbered_outline = add_numbering_to_outline(markdown_outline)
                        
                        st.subheader("Paper Outline")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.text_area("Raw Markdown", value=numbered_outline, height=400)
                            st.download_button(
                                label="Download Outline",
                                data=numbered_outline,
                                file_name="OUTLINE.md",
                                mime="text/markdown"
                            )
                        
                        with col2:
                            st.markdown("""
                                <style>
                                    .h1-style { font-size: 24px !important; }
                                    .h2-style { font-size: 20px !important; margin-left: 20px; }
                                    .h3-style { font-size: 16px !important; margin-left: 40px; }
                                </style>
                            """, unsafe_allow_html=True)
                            
                            # Convert markdown headings to styled HTML
                            html_output = []
                            for line in numbered_outline.split('\n'):
                                if line.startswith('### '):
                                    html_output.append(f'<p class="h3-style">{line[4:]}</p>')
                                elif line.startswith('## '):
                                    html_output.append(f'<p class="h2-style">{line[3:]}</p>')
                                elif line.startswith('# '):
                                    html_output.append(f'<p class="h1-style">{line[2:]}</p>')
                                else:
                                    html_output.append(line)
                            
                            st.markdown('<div style="border:1px solid #ddd; padding:10px; border-radius:5px; height:400px; overflow:auto; background-color:white;">' + 
                                      '\n'.join(html_output) + '</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()