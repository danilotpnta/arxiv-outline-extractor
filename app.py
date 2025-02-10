import streamlit as st
import re
import arxiv
import requests
import fitz  # PyMuPDF
from io import BytesIO

def extract_pdf_toc(pdf_bytes):
    """
    Try to extract the embedded table of contents (TOC) from the PDF.
    Returns a list of entries: (level, title, page number)
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        toc = doc.get_toc()  # Format: [ [level, title, page], ... ]
        return toc if toc else None
    except Exception as e:
        st.error(f"Error extracting TOC: {e}")
        return None

def extract_headings_regex(pdf_bytes, max_pages=5):
    """
    Fallback: Extract headings from the first few pages of the PDF using regex.
    Looks for lines starting with a number pattern (e.g., '3.' or '3.1').

    Returns a list of tuples: (level, heading text, page number)
    """
    headings = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
        return headings

    # This regex matches patterns like "1. Introduction" or "3.1 Query PubMed"
    heading_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)(?:\s+)(.+)$', re.MULTILINE)
    
    for page_num in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_num)
        text = page.get_text()
        for match in heading_pattern.finditer(text):
            numbering = match.group(1)
            title = match.group(2).strip()
            # Determine the heading level (e.g., "3" -> level 1, "3.1" -> level 2)
            level = numbering.count('.') + 1
            headings.append((level, f"{numbering} {title}", page_num + 1))
    
    return headings

def generate_markdown_outline(headings):
    """
    Given a list of headings (level, heading text, page number), generate a Markdown
    outline string. For example, a level-1 heading becomes '# 1. Introduction'
    and a level-2 heading becomes '## 3.1 Query PubMed'.
    """
    markdown_lines = []
    for level, heading, _ in headings:
        header_line = f"{'#' * level} {heading}"
        markdown_lines.append(header_line)
    return "\n".join(markdown_lines)

def get_arxiv_id(url):
    """
    Extracts the arXiv ID from a URL.
    Supports URLs like:
      - https://arxiv.org/abs/2102.00001
      - https://arxiv.org/pdf/2102.00001.pdf
    """
    match = re.search(r'arxiv\.org/(abs|pdf)/([^\?/]+)', url)
    if match:
        return match.group(2)
    return None

st.title("Arxiv Paper Outline Extractor")

url_input = st.text_input("Enter the arXiv paper URL:")

if url_input:
    arxiv_id = get_arxiv_id(url_input)
    if not arxiv_id:
        st.error("Could not extract arXiv ID. Please check your URL.")
    else:
        st.info(f"Extracted arXiv ID: {arxiv_id}")

        # Fetch paper metadata using the arxiv package.
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(search.results())
        except StopIteration:
            st.error("No results found for this arXiv ID.")
        except Exception as e:
            st.error(f"Error fetching metadata: {e}")
        else:
            st.header(paper.title)
            st.subheader("Abstract")
            st.write(paper.summary)

            # Download the PDF file.
            pdf_url = paper.pdf_url
            st.write("Downloading PDF...")
            try:
                response = requests.get(pdf_url)
                response.raise_for_status()
                pdf_bytes = response.content
            except Exception as e:
                st.error(f"Error downloading PDF: {e}")
                pdf_bytes = None

            if pdf_bytes:
                st.write("Extracting paper outline...")

                # Try extracting the embedded TOC; if not available, use regex-based extraction.
                headings = extract_pdf_toc(pdf_bytes)
                if not headings:
                    st.info("Embedded TOC not found; attempting regex-based extraction of headings.")
                    headings = extract_headings_regex(pdf_bytes, max_pages=7)
                    if not headings:
                        st.info("No headings found via regex extraction.")

                if headings:
                    markdown_outline = generate_markdown_outline(headings)
                    st.subheader("Generated Markdown Outline")
                    
                    # Create a two-column layout: left for raw Markdown, right for rendered Markdown.
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_area("Markdown Outline (raw)", value=markdown_outline, height=400)
                        st.download_button(
                            label="Download Outline as Markdown",
                            data=markdown_outline,
                            file_name="OUTLINE.md",
                            mime="text/markdown"
                        )
                    with col2:
                        st.markdown(markdown_outline)