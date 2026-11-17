"""Build an editable Word draft from the research manuscript."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path(__file__).parent / "thesis.docx")
parser.add_argument("--branch", default="research/2026-11-17-results")
args = parser.parse_args()
md = Path(__file__).resolve().with_name("THESIS_RU.md")
repo = md.parents[2]
text = md.read_text()
def public_link(m):
    target = m[2]
    if target.startswith(('http:', 'https:', '#')): return m[0]
    p = (md.parent / target).resolve()
    url = f"https://github.com/tarma3v/correlated_prediction_markets/blob/{args.branch}/{p.relative_to(repo).as_posix()}"
    return f"[{m[1]}]({url})"
text = re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', public_link, text)
# Pandoc otherwise uses the physical dimensions encoded in each source PNG.
text = re.sub(r"^(!\[.+?\]\(.+?\))$", r"\1{width=15.5cm}", text, flags=re.M)
dst = args.output.resolve()
dst.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "thesis.md"
    src.write_text(text)
    subprocess.run(["pandoc", str(src), "--resource-path=" + str(md.parent), "-o", str(dst)], check=True)
doc=Document(dst)
sec=doc.sections[0]
sec.page_width=Cm(21); sec.page_height=Cm(29.7)
sec.left_margin=Cm(2.5);sec.right_margin=Cm(2.2)
sec.top_margin=Cm(2.15);sec.bottom_margin=Cm(2.15)
sec.footer_distance=Cm(0.9);sec.header_distance=Cm(0.8)
normal=doc.styles['Normal']
normal.font.name='Georgia';normal.font.size=Pt(10.5)
normal.paragraph_format.line_spacing=1.22
normal.paragraph_format.space_after=Pt(6)
for style in ['Body Text','First Paragraph','Compact']:
    if style in doc.styles:
        doc.styles[style].base_style=normal
for name,size in [('Title',24),('Heading 2',17),('Heading 3',13)]:
    st=doc.styles[name];st.font.name='Arial';st.font.size=Pt(size);st.font.bold=True
    st.font.color.rgb=RGBColor.from_string('182C32' if name!='Title' else '000000')
    st.paragraph_format.keep_with_next=True;st.paragraph_format.space_before=Pt(14);st.paragraph_format.space_after=Pt(7)
doc.paragraphs[0].style='Title'
for t in doc.tables:
    for i,row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        if i==0: row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        for cell in row.cells:
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E1EBE9' if i==0 else ('F4F7F6' if i%2==0 else 'FFFFFF'))
            cell._tc.get_or_add_tcPr().append(shade)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(3);p.paragraph_format.space_before=Pt(3);p.paragraph_format.line_spacing=1.0
                for r in p.runs:r.font.name='Arial';r.font.size=Pt(9);r.bold=(i==0)
fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=fp.add_run('А. Тармаев     •     ');r.font.size=Pt(9)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');fp._p.append(field)
doc.core_properties.author='Александр Тармаев';doc.core_properties.title=doc.paragraphs[0].text
doc.save(dst)
