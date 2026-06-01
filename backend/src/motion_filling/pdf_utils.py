from pathlib import Path
import shutil
import subprocess
import threading

_libreoffice_lock = threading.Lock()


def find_soffice() -> str | None:
    """Find soffice executable, checking PATH and common macOS locations."""
    soffice = shutil.which("soffice")
    if soffice:
        return soffice
    fallback_paths = [
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for path in fallback_paths:
        if Path(path).exists():
            return path
    return None


def convert_to_pdf_libreoffice(docx_path: Path, out_dir: Path) -> Path | None:
    """Convert DOCX to PDF using LibreOffice. Uses lock to prevent concurrent conversion issues."""
    soffice_path = find_soffice()
    if not soffice_path:
        print("WARNING: soffice not found in PATH or standard locations")
        return None

    with _libreoffice_lock:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [soffice_path, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            pdf_path = out_dir / docx_path.with_suffix(".pdf").name
            if pdf_path.exists():
                return pdf_path
            alt_pdf_path = docx_path.with_suffix(".pdf")
            if alt_pdf_path.exists():
                return alt_pdf_path
            print(f"WARNING: PDF conversion completed but output file not found: {pdf_path}")
            print(f"LibreOffice output: {result.stdout}")
            return None
        except subprocess.CalledProcessError as e:
            print(f"ERROR: LibreOffice conversion failed: {e}")
            print(f"Return code: {e.returncode}")
            print(f"Output: {e.stdout}")
            print(f"Error: {e.stderr}")
            return None
        except Exception as e:
            print(f"ERROR: Unexpected error during PDF conversion: {e}")
            return None
