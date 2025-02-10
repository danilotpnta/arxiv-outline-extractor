import streamlit as st
import re
import arxiv
import requests
import fitz  
import uuid
import pyperclip

# Custom CSS for Markdown headings with added indentation for subsections
st.markdown("""
    <style>
        .h1 {
            font-size: 19px !important;
            font-weight: 700;
            margin-bottom: 8px !important;
            margin-left: 0px;
        }
        .h2 {
            font-size: 16px !important;
            font-weight: 550;
            margin-bottom: 2px;
            margin-left: 20px !important;
        }
        .h3 {
            font-size: 14px !important;
            font-weight: 550;
            margin-bottom: 2px;
            margin-left: 40px !important;
        }
        .h4 {
            font-size: 12px !important;
            font-weight: 500;
            margin-bottom: 2px;
            margin-left: 60px !important;
        }
        .h5 {
            font-size: 10px !important;
            font-weight: 450;
            margin-bottom: 2px;
            margin-left: 80px !important;
        }
        .h6 {
            font-size: 8px !important;
            font-weight: 400;
            margin-bottom: 2px;
            margin-left: 100px !important;
        }
        .markdown-box {
            padding: 10px;
            border-radius: 5px;
            background-color: #f9f9f9;
            padding-left: 15px;
        }
    </style>
""", unsafe_allow_html=True)

def extract_pdf_toc(pdf_bytes):
    """Extracts Table of Contents from the PDF if available."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        toc = doc.get_toc()
        return toc if toc else None
    except Exception as e:
        st.error(f"Error extracting TOC: {e}")
        return None

def extract_headings_regex(pdf_bytes, max_pages=5):
    """Extract headings using regex starting from Introduction."""
    headings = []
    found_introduction = False
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
        return headings

    # Pattern to match both numbered and unnumbered headings
    heading_patterns = [
        r'^\s*(?:\d+(?:\.\d+)*\s+)?(?:Introduction|INTRODUCTION)(.*)$',  # Introduction pattern
        r'^\s*(\d+(?:\.\d+)*)\s+(.+)$',  # Numbered heading pattern
        r'^\s*(Chapter|Section|Appendix)\s+([A-Z0-9][-\w\s]*:?.*)$'  # Other patterns
    ]
    
    patterns = [re.compile(pattern, re.MULTILINE) for pattern in heading_patterns]

    for page_num in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_num)
        text = page.get_text()
        
        # First look for Introduction if we haven't found it yet
        if not found_introduction:
            intro_match = patterns[0].search(text)
            if intro_match:
                found_introduction = True
                headings.append((1, "Introduction" + (intro_match.group(1) or ""), page_num + 1))
                continue

        # Only process other headings after finding introduction
        if found_introduction:
            for pattern in patterns[1:]:
                for match in pattern.finditer(text):
                    if len(match.groups()) == 2:
                        numbering = match.group(1)
                        title = match.group(2).strip()
                        
                        # Skip any institution or author information
                        if any(keyword.lower() in title.lower() for keyword in 
                            ['university', 'school of', 'department of', 'institute']):
                            continue
                            
                        level = numbering.count('.') + 1 if numbering else 1
                        headings.append((level, title, page_num + 1))
    
    return headings

def generate_markdown_outline(headings):
    """Converts extracted headings into Markdown format."""
    markdown_lines = []
    for level, heading, _ in headings:
        header_line = f"{'#' * level} {heading}"
        markdown_lines.append(header_line)
    return "\n".join(markdown_lines)

def add_numbering_to_outline(outline):
    """
    Re-numbers the outline so that:
      - All level-1 headings are numbered numerically until a level-1 heading contains one
        of the conclusion keywords (e.g., "Conclusion", "Concluding", "Final Remarks", "Summary").
      - The Conclusion heading itself remains numeric (so its subheadings will be numbered like “6.1”, etc.).
      - Any level-1 heading *after* the conclusion is treated as an appendix section:
           • A new level-1 appendix gets a letter (A, B, …)
           • Its subheadings get numbering like “A.1”, “A.1.1”, etc.
      - In numeric mode, when a new level-1 heading appears the subheading counters are reset,
        so the first subheading will start at 1.
    """
    numbered_outline = []
    
    # Counters for numeric (main body) numbering.
    numeric_counters = {}
    
    # Counters for appendix numbering.
    appendix_counters = {}
    appendix_letter_counter = ord('A')
    current_appendix_letter = None  # Stores the letter for the current appendix section.
    
    # Flag: turns True when a level-1 heading with a conclusion keyword is encountered.
    main_body_complete = False  
    # Indicates the numbering mode of the most recent level-1 heading.
    current_main_mode = "numeric"  # "numeric" or "appendix"
    
    # Keywords that mark the end of the main body.
    conclusion_keywords = ["Conclusion", "Concluding", "Final Remarks", "Summary"]

    for line in outline.split("\n"):
        heading_level = line.count('#')
        if heading_level == 0:
            numbered_outline.append(line)
            continue

        # Remove markdown markers and extra whitespace.
        text = line.lstrip('#').strip()

        if heading_level == 1:
            # Process level-1 headings.
            if not main_body_complete:
                # Process in numeric mode.
                m = re.match(r'^(\d+)\s+(.*)', text)
                if m:
                    num = int(m.group(1))
                    numeric_counters[1] = num  # Use the existing number.
                    clean_text = m.group(2)
                    new_text = f"{num} {clean_text}"
                else:
                    numeric_counters[1] = numeric_counters.get(1, 0) + 1
                    new_text = f"{numeric_counters[1]} {text}"
                    clean_text = text

                numbered_outline.append(f"{'#' * heading_level} {new_text}")
                # Reset any subheading counters when a new level-1 heading is processed.
                for lvl in list(numeric_counters.keys()):
                    if lvl > 1:
                        numeric_counters[lvl] = 0
                current_main_mode = "numeric"
                
                # If this heading contains a conclusion keyword, mark the main body as complete.
                if any(kw.lower() in clean_text.lower() for kw in conclusion_keywords):
                    main_body_complete = True
            else:
                # This is a level-1 heading after the main body (after Conclusion)
                # Switch to appendix mode.
                current_appendix_letter = chr(appendix_letter_counter)
                appendix_letter_counter += 1
                appendix_counters = {}  # Reset appendix subheading counters.
                numbered_outline.append(f"{'#' * heading_level} {current_appendix_letter} {text}")
                current_main_mode = "appendix"
        else:
            # Process subheadings (level > 1).
            if current_main_mode == "numeric":
                # Use numeric numbering.
                text_without_number = re.sub(r'^\d+(\.\d+)*\s+', '', text)
                numeric_counters[heading_level] = numeric_counters.get(heading_level, 0) + 1
                # Reset counters for any deeper levels.
                for lvl in list(numeric_counters.keys()):
                    if lvl > heading_level:
                        numeric_counters[lvl] = 0
                numbering_parts = []
                for lvl in range(1, heading_level + 1):
                    numbering_parts.append(str(numeric_counters.get(lvl, 0)))
                numbering = ".".join(numbering_parts)
                numbered_outline.append(f"{'#' * heading_level} {numbering} {text_without_number}")
            else:
                # Use appendix numbering.
                appendix_counters[heading_level] = appendix_counters.get(heading_level, 0) + 1
                for lvl in list(appendix_counters.keys()):
                    if lvl > heading_level:
                        appendix_counters[lvl] = 0
                numbering_parts = [current_appendix_letter]  # Start with the current appendix letter.
                # For level 2 and deeper, append the hierarchical counters.
                for lvl in range(2, heading_level + 1):
                    numbering_parts.append(str(appendix_counters.get(lvl, 0)))
                numbering = ".".join(numbering_parts)
                numbered_outline.append(f"{'#' * heading_level} {numbering} {text}")

    return "\n".join(numbered_outline)

def convert_markdown_to_html(markdown_text):
    """Converts markdown headings to HTML with adjusted font size, boldness, and indentation."""
    html_output = []
    lines = markdown_text.strip().split("\n")

    for line in lines:
        match = re.match(r'^(#+)\s*(.*)', line)
        if match:
            level = len(match.group(1))
            text = match.group(2)
            html_output.append(f'<p class="h{level}">{text}</p>')
        else:
            html_output.append(f'<p>{line}</p>')

    return "\n".join(html_output)

def get_arxiv_id(url):
    """Extracts arXiv ID from a given URL."""
    match = re.search(r'arxiv\.org/(abs|pdf)/([^\?/]+)', url)
    if match:
        return match.group(2)
    return None

def process_pdf(pdf_bytes, title=None):
    """Process PDF content and display results."""
    headings = extract_pdf_toc(pdf_bytes) or extract_headings_regex(pdf_bytes, max_pages=7)
    
    if headings:
        markdown_outline = generate_markdown_outline(headings)
        numbered_outline = add_numbering_to_outline(markdown_outline)

        col1, col2 = st.columns([4, 5])

        with col1:
            st.subheader("Markdown Outline")
            # Calculate dynamic height based on the number of lines.
            raw_markdown = numbered_outline
            num_lines = raw_markdown.count("\n") + 1
            # Estimate 25 pixels per line; adjust as needed.
            height_value = max(150, num_lines * 25)
            # Display the raw markdown in a text area.
            markdown_text = st.text_area("Raw Markdown Output", value=raw_markdown, height=height_value)
            
            unique_key = f"download_button_{uuid.uuid4()}"
            st.download_button(
                label="📄 Download as Markdown",
                data=raw_markdown,
                file_name="outline.md",
                mime="text/markdown",
                key=unique_key
            )
            
            # Use pyperclip to copy the markdown when the button is clicked.
            if st.button('✂️ Copy Markdown'):
                # This copies the content of the text area to the clipboard.
                pyperclip.copy(markdown_text)
                st.success('Markdown copied successfully!')

        with col2:
            st.subheader("Rendered Outline")
            st.markdown("""
                <p style="font-size: 14px; font-weight: 500; margin-bottom: 6px;">
                    Rendered Markdown Outline
                </p>
            """, unsafe_allow_html=True)

            converted_html = convert_markdown_to_html(numbered_outline)
            st.markdown(f'<div class="markdown-box">{converted_html}</div>', unsafe_allow_html=True)

    else:
        st.info("No headings found in the PDF.")

# Streamlit UI
st.title("🔍 Paper Outline Extractor")

# Create tabs for different input methods
tab1, tab2 = st.tabs(["ArXiv URL", "Upload PDF"])

with tab1:
    url_input = st.text_input("Enter the arXiv paper URL:")

    if url_input:
        arxiv_id = get_arxiv_id(url_input)
        
        if not arxiv_id:
            st.error("Could not extract arXiv ID. Please check your URL.")
        else:
            st.info(f"Extracted arXiv ID: {arxiv_id}")

            try:
                search = arxiv.Search(id_list=[arxiv_id])
                paper = next(search.results())
            except StopIteration:
                st.error("No results found for this arXiv ID.")
            except Exception as e:
                st.error(f"Error fetching metadata: {e}")
            else:
                st.header(paper.title)
                with st.expander("Abstract"):
                    st.write(paper.summary)

                pdf_url = paper.pdf_url
                try:
                    response = requests.get(pdf_url)
                    response.raise_for_status()
                    pdf_bytes = response.content
                except Exception as e:
                    st.error(f"Error downloading PDF: {e}")
                    pdf_bytes = None

                if pdf_bytes:
                    process_pdf(pdf_bytes, paper.title)

with tab2:
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    
    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()
        st.header(uploaded_file.name)
        process_pdf(pdf_bytes, uploaded_file.name)