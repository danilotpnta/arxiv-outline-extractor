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

def add_numbering_to_outline(outline):
    """
    Add numbering to the generated Markdown outline based on heading levels.
    Switch to alphabetical numbering after the Conclusion.
    """
    numbered_outline = []
    counters = {}  # To hold counters for each heading level
    appendices_started = False  # Flag to mark the start of the appendices
    letter_counter = ord('A')  # Start alphabetically with 'A'
    last_final_num = 6  # Track the last conclusion number

    for line in outline.split("\n"):
        # Identify the level of the heading by counting the number of '#' symbols
        heading_level = line.count('#')
        if heading_level == 0:
            numbered_outline.append(line)
            continue

        # If the heading is "Conclusion" or similar, switch to appendices
        if not appendices_started:
            conclusion_keywords = ["Conclusion", "Concluding", "Final Remarks", "Summary"]
            if any(keyword in line for keyword in conclusion_keywords):
                appendices_started = True
                # Keep the last numeric number for the conclusion section
                numbered_outline.append(f"# {last_final_num} {line.lstrip('#').strip()}")
                continue

        # Handle normal numbering (numeric) for main content
        if not appendices_started:
            if heading_level not in counters:
                counters[heading_level] = 0
            if heading_level > 1:
                # Reset sub-level counters when a new higher level heading appears
                for i in range(heading_level + 1, max(counters.keys()) + 1):
                    counters[i] = 0

            counters[heading_level] += 1
            numbering = '.'.join(str(counters[i]) for i in range(1, heading_level + 1))

            # Generate the numbered heading
            numbered_outline.append(f"{'#' * heading_level} {numbering} {line.lstrip('#').strip()}")

        # Handle alphabetical numbering for appendices
        else:
            # Alphabetical numbering: A, B, C, etc.
            appendix_prefix = chr(letter_counter)
            numbered_outline.append(f"# {appendix_prefix} {line.lstrip('#').strip()}")
            letter_counter += 1

            # Dynamically handle sub-levels (A.1, A.2, B.1, etc.)
            if heading_level > 1:
                numbering = f"{appendix_prefix}." + ".".join(str(counters[i]) for i in range(2, heading_level + 1))
                numbered_outline.append(f"{'#' * heading_level} {numbering} {line.lstrip('#').strip()}")
                counters[heading_level] += 1

    return "\n".join(numbered_outline)

def get_arxiv_id(url):
    """
    Extracts the arXv ID from a URL.
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
        st.error("Could not extract arXv ID. Please check your URL.")
    else:
        st.info(f"Extracted arXv ID: {arxiv_id}")

        # Fetch paper metadata using the arxiv package.
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

            # Download the PDF file.
            pdf_url = paper.pdf_url
            try:
                response = requests.get(pdf_url)
                response.raise_for_status()
                pdf_bytes = response.content
            except Exception as e:
                st.error(f"Error downloading PDF: {e}")
                pdf_bytes = None

            if pdf_bytes:

                # Try extracting the embedded TOC; if not available, use regex-based extraction.
                headings = extract_pdf_toc(pdf_bytes)
                if not headings:
                    st.info("Embedded TOC not found; attempting regex-based extraction of headings.")
                    headings = extract_headings_regex(pdf_bytes, max_pages=7)
                    if not headings:
                        st.info("No headings found via regex extraction.")

                if headings:
                    markdown_outline = generate_markdown_outline(headings)
                    numbered_outline = add_numbering_to_outline(markdown_outline)
                    st.subheader("Generated Markdown Outline")
                    
                    st.text_area("Markdown Outline (raw)", value=numbered_outline, height=400)
                    st.download_button(
                        label="Download Outline as Markdown",
                        data=numbered_outline,
                        file_name="OUTLINE.md",
                        mime="text/markdown"
                    )
                    # with col2:
                    #     # Apply custom CSS to the right panel to make text smaller
                    #     st.markdown(
                    #         """
                    #         <style>
                    #         #right-panel markdown {
                    #             font-size: 12px !important;
                    #         }
                    #         </style>
                    #         """, 
                    #         unsafe_allow_html=True
                    #     )
                    #     # Add custom id for the right panel
                    #     right_panel = st.markdown(numbered_outline, key="right-panel")