from pypdf import PdfReader
from pathlib import Path
files = [Path(r'C:\Users\ian chel\Documents\GitHub\Project Resilience Alpha\docs\dossier\Workshop2026-M2-G2-Dossier.pdf'), Path(r'C:\Users\ian chel\Downloads\Prez.pdf')]
for f in files:
    reader = PdfReader(str(f))
    print(f'\n### {f.name} pages={len(reader.pages)}')
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or '').replace('\n', ' | ')
        print(f'[PAGE {i}] {text[:5000]}')
