import sys
import os
import re
import urllib.parse
import PyPDF2
from concurrent.futures import ProcessPoolExecutor
import subprocess

from colorama import init
from termcolor import cprint 
from pyfiglet import figlet_format

# --- ANSI Color Codes ---
COLOR_MAP = {
    '.html': '32',  # Green
    '.htm': '32',   # Green
    '.css': '34',   # Blue
    '.js': '31',    # Yellow
    '.py': '36',    # Cyan
    '.md': '35',    # Magenta
    '.txt': '37',   # White
    '.xml': '31',   # Red
    '.json': '31',  # Red
    '.log': '33',   # Yellow
    '.csv': '37',   # White
    '.sh': '36',    # Cyan
    '.yml': '35',   # Magenta
    '.yaml': '35',  # Magenta
    '.conf': '34',  # Blue
    '.pdf': '33',   # Red for PDF files
    # Add more extensions and colors as needed
}
RESET_COLOR = '\033[0m' # Resets terminal color to default
# ------------------------

print()
cprint(figlet_format('Asteroth text finder', font='slant', width=110),
       'red', attrs=['bold'])

def search_text_files(folder_path, search_sentence, file_extensions_to_search):
    """
    Searches through specified text files in a given folder for a specific sentence.
    Includes a progress bar in the terminal.

    Args:
        folder_path (str): The absolute path to the folder containing files.
        search_sentence (str): The exact sentence to search for.
        file_extensions_to_search (list): A list of file extensions (e.g., ['.txt', '.css', '.js'])
                                           to include in the search. Extensions should include the dot.

    Returns:
        list: A list of dictionaries, each containing 'file_path', 'line_number', and 'line_content'.
    """
    found_occurrences = []
    escaped_sentence = re.escape(search_sentence)
    pattern = re.compile(escaped_sentence, re.IGNORECASE)

    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found at '{folder_path}'")
        return []

    print(f"Searching for '{search_sentence}' in files with extensions {file_extensions_to_search} under '{folder_path}'...")

    # --- First pass: Count total relevant files for the progress bar ---
    total_files_to_process = 0
    print("Counting files... This might take a moment for large directories.")
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            _, file_extension = os.path.splitext(file_name)
            if file_extension.lower() in file_extensions_to_search:
                total_files_to_process += 1
    print(f"Found {total_files_to_process} files to search.")

    if total_files_to_process == 0:
        print("No files matching the specified extensions found. Exiting.")
        return []

    # --- Second pass: Perform the actual search with a progress bar ---
    processed_files_count = 0
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            _, file_extension = os.path.splitext(file_name)
            if file_extension.lower() in file_extensions_to_search:
                processed_files_count += 1
                file_path = os.path.join(root, file_name)

                # Update progress bar
                progress_percent = (processed_files_count / total_files_to_process) * 100
                sys.stdout.write(f"\r[{processed_files_count}/{total_files_to_process}] {progress_percent:.1f}% - Processing: {file_name[:50]}...")
                sys.stdout.flush()

                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                found_occurrences.append({'file_path': file_path, 'line_number': line_num, 'line_content': line.strip()})
                except Exception as e:
                    # Print error on a new line to not interfere with progress bar
                    sys.stdout.write(f"\nError reading {file_path}: {e}\n")
                    sys.stdout.flush()
    sys.stdout.write("\n") # Move to a new line after progress bar is complete
    sys.stdout.flush()

    return found_occurrences

def _search_single_pdf(filepath, search_term):
    """
    Helper function to search a single PDF file for a term using pdftotext.
    Returns a list of occurrences found in this file.
    """
    file_occurrences = []
    escaped_term = re.escape(search_term)
    pattern = re.compile(escaped_term, re.IGNORECASE)

    try:
        # Call pdftotext to extract text
        process = subprocess.run(['pdftotext', '-enc', 'UTF-8', filepath, '-'], capture_output=True, text=True, check=True)
        text = process.stdout

        if text:
            lines = text.splitlines()
            for line_idx, line in enumerate(lines, 1):
                if pattern.search(line):
                    file_occurrences.append({'file_path': filepath, 'page_number': 0, 'line_number': line_idx, 'line_content': line.strip()})
                    # pdftotext doesn't easily give page numbers per line, so we'll use 0 or a placeholder
    except FileNotFoundError:
        sys.stdout.write(f"\n  Warning: 'pdftotext' not found. Please install poppler-utils (e.g., 'sudo apt-get install poppler-utils' on Debian/Ubuntu, 'brew install poppler' on macOS) for faster PDF processing. Falling back to PyPDF2 for '{filepath}'.\n")
        sys.stdout.flush()
        # Fallback to PyPDF2 if pdftotext is not found
        try:
            with open(filepath, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text = page.extract_text() if page.extract_text() else ""
                    if text:
                        lines = text.splitlines()
                        for line_idx, line in enumerate(lines, 1):
                            if pattern.search(line):
                                file_occurrences.append({'file_path': filepath, 'page_number': page_num + 1, 'line_number': line_idx, 'line_content': line.strip()})
        except PyPDF2.errors.PdfReadError:
            sys.stdout.write(f"\n  Warning: Could not read PDF file '{filepath}' with PyPDF2. It might be corrupted or encrypted.\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(f"\n  An unexpected error occurred with PyPDF2 while processing '{filepath}': {e}\n")
            sys.stdout.flush()
    except subprocess.CalledProcessError as e:
        sys.stdout.write(f"\n  Error processing PDF '{filepath}' with pdftotext: {e}\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(f"\n  An unexpected error occurred while processing '{filepath}': {e}\n")
        sys.stdout.flush()
    return file_occurrences

def search_pdfs(folder_path, search_term):
    """
    Searches for a specific term within PDF files in a given folder and its subfolders using multiprocessing.
    Prioritizes 'pdftotext' for speed, falls back to PyPDF2 if not available.

    Args:
        folder_path (str): The absolute path to the folder containing PDF files.
        search_term (str): The word or sentence to search for.

    Returns:
        list: A list of dictionaries, each containing 'file_path', 'page_number', 'line_number', and 'line_content'.
    """
    all_found_occurrences = []

    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found at '{folder_path}'")
        return all_found_occurrences

    print(f"Searching for '{search_term}' in PDF files within '{folder_path}' and its subfolders (using multiprocessing and pdftotext/PyPDF2)...")

    pdf_files_to_process = []
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            if file_name.lower().endswith(".pdf"):
                pdf_files_to_process.append(os.path.join(root, file_name))

    if not pdf_files_to_process:
        print("No PDF files found. Exiting PDF search.")
        return []

    print(f"Found {len(pdf_files_to_process)} PDF files to search. Processing in parallel...")

    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(_search_single_pdf, filepath, search_term) for filepath in pdf_files_to_process]
        
        for i, future in enumerate(futures):
            try:
                occurrences = future.result()
                all_found_occurrences.extend(occurrences)
                sys.stdout.write(f"\rProcessed {i+1}/{len(pdf_files_to_process)} PDF files.")
                sys.stdout.flush()
            except Exception as e:
                sys.stdout.write(f"\n  Error processing one PDF file: {e}\n")
                sys.stdout.flush()
    sys.stdout.write("\n") # Move to a new line after progress bar is complete
    sys.stdout.flush()

    return all_found_occurrences


if __name__ == "__main__":
    # Prompt user for the sentence to search
    sentence_to_find = input("Write the word/sentence you want to look for: ")

    # Prompt user for the directory path
    folder_to_search = input("Enter the absolute path to the directory where the files are located: ")

    # --- Configure the file extensions to search ---
    extensions = ['.html', '.htm', '.txt', '.css', '.js', '.py', '.md', '.xml', '.json', '.log', '.csv', '.sh', '.yml', '.yaml', '.conf', '.pdf']
    # ---------------------------------------------

    if not sentence_to_find.strip():
        print("Error: Search sentence cannot be empty.")
    elif not folder_to_search.strip():
        print("Error: Directory path cannot be empty.")
    else:
        # Search text files
        text_file_results = search_text_files(folder_to_search, sentence_to_find, [ext for ext in extensions if ext != '.pdf'])
        
        # Search PDF files
        pdf_file_results = search_pdfs(folder_to_search, sentence_to_find)

        # Combine results
        all_results = text_file_results + pdf_file_results

        if all_results:
            print("\n--- Files containing the sentence (click to open) ---\n")
            # Sort results for better readability (e.g., by file path, then line number)
            all_results.sort(key=lambda x: (x['file_path'], x.get('page_number', 0), x['line_number']))

            for item in all_results:
                f_path = item['file_path']
                line_num = item['line_number']
                page_info = f" (Page {item['page_number']})" if 'page_number' in item else ""

                _, file_extension = os.path.splitext(f_path)
                color_code = COLOR_MAP.get(file_extension.lower(), '37')

                 # Apply color to the visible text part of the hyperlink
                colored_f_path = f"\033[{color_code}m{f_path}{RESET_COLOR}"

                # Generate OSC 8 hyperlink for Kitty terminal
                encoded_path = urllib.parse.quote(f_path)
                hyperlink = f"\x1b]8;;file://{encoded_path}\x1b\\{colored_f_path}\x1b]8;;\\"
                print(hyperlink)
            print(f"\nFound the sentence in {len(all_results)} files.")
        else:
            print("\nNo files found containing the specified sentence.")
