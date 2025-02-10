import streamlit as st
import re
import arxiv
import requests
import fitz  

# Custom CSS for Markdown headings
st.markdown("""
    <style>
        .h1 { font-size: 19px !important; font-weight: 700; margin-bottom: 8px !important; }  /* Large & Bold */
        .h2 { font-size: 16px !important; font-weight: 550; margin-bottom: 2px; }  /* Slightly Smaller & Less Bold */
        .h3 { font-size: 14px !important; font-weight: 550; margin-bottom: 2px; }  /* Medium Size & Weight */
        .h4 { font-size: 12px !important; font-weight: 500; margin-bottom: 2px; }  /* Getting Smaller */
        .h5 { font-size: 10px !important; font-weight: 450; margin-bottom: 2px; }  /* Even Less Bold */
        .h6 { font-size: 8px !important; font-weight: 400; margin-bottom: 2px; }  /* Smallest & Normal Weight */
        .markdown-box {
            # border: 1px solid #ddd;
            padding: 10px;
            border-radius: 5px;
            background-color: #f9f9f9;
            overflow-y: auto;
            max-height: 500px;
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
    """Extract headings using regex if TOC is not available."""
    headings = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
        return headings

    heading_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)\s+(.+)$', re.MULTILINE)

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
    """Converts extracted headings into Markdown format."""
    markdown_lines = []
    for level, heading, _ in headings:
        header_line = f"{'#' * level} {heading}"
        markdown_lines.append(header_line)
    return "\n".join(markdown_lines)

def add_numbering_to_outline(outline):
    """Adds numbering to the generated Markdown outline based on heading levels."""
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

    return "\n".join(numbered_outline)

def convert_markdown_to_html(markdown_text):
    """Converts markdown headings to HTML with adjusted font size & boldness."""
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

# Streamlit UI
st.title("🔍 ArXiv Paper Outline Extractor")

url_input = st.text_input("Enter the arXiv paper URL:")

if url_input:
    arxiv_id = get_arxiv_id(url_input)
    
    if not arxiv_id:
        st.error("Could not extract arXiv ID. Please check your URL.")
    else:
        st.info(f"Extracted arXiv ID: {arxiv_id}")

        # Fetch paper metadata
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(search.results())
        except StopIteration:
            st.error("No results found for this arXiv ID.")
        except Exception as e:
            st.error(f"Error fetching metadata: {e}")
        else:
            st.header(paper.title)
            # st.subheader("Abstract")
            with st.expander("Abstract"):
                st.write(paper.summary)

            # Download the PDF
            pdf_url = paper.pdf_url
            try:
                response = requests.get(pdf_url)
                response.raise_for_status()
                pdf_bytes = response.content
            except Exception as e:
                st.error(f"Error downloading PDF: {e}")
                pdf_bytes = None

            if pdf_bytes:
                headings = extract_pdf_toc(pdf_bytes) or extract_headings_regex(pdf_bytes, max_pages=7)
                
                if headings:
                    markdown_outline = generate_markdown_outline(headings)
                    numbered_outline = add_numbering_to_outline(markdown_outline)

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        st.subheader("Markdown Outline")
                        markdown_text = st.text_area("Raw Markdown Output", value=numbered_outline, height=400)
                        st.download_button(
                            label="Download as Markdown",
                            data=numbered_outline,
                            file_name="outline.md",
                            mime="text/markdown"
                        )

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