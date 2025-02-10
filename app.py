import streamlit as st
import re
import arxiv
import requests
import fitz 
from io import BytesIO


def extract_pdf_toc(pdf_bytes):
    """
    Opens a PDF from bytes and extracts its table of contents (if available).
    Returns a list of TOC entries in the format: (level, title, page number).
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        toc = doc.get_toc()  # returns list: [ [level, title, page], ... ]
        return toc
    except Exception as e:
        st.error(f"Error extracting TOC: {e}")
        return None


def get_arxiv_id(url):
    """
    Extracts the arXiv ID from a URL.
    Supports URLs like:
      - https://arxiv.org/abs/2102.00001
      - https://arxiv.org/pdf/2102.00001.pdf
    """
    # Try to find a pattern like /abs/<id> or /pdf/<id>
    match = re.search(r"arxiv\.org/(abs|pdf)/([^\?/]+)", url)
    if match:
        return match.group(2)
    else:
        return None


st.title("ArXiv Paper Outline Extractor")

# Input box for the user to provide an arXiv paper URL.
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
                st.write("Extracting paper outline (if available)...")
                toc = extract_pdf_toc(pdf_bytes)
                if toc:
                    st.subheader("Paper Outline (Table of Contents)")
                    for entry in toc:
                        level, title, page = entry
                        indent = "    " * (level - 1)
                        st.write(f"{indent}- {title} (Page {page})")
                else:
                    st.info("No table of contents found in the PDF.")
