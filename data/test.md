from docx import Document
from docx.oxml.ns import qn

doc = Document('your_problem_doc.docx')
np = doc.part.numbering_part.element

# numId -> abstractNumId mapping
print("numId -> abstractNumId:")
for num in np.findall(qn('w:num')):
    nid = num.get(qn('w:numId'))
    ref = num.find(qn('w:abstractNumId'))
    aid = ref.get(qn('w:val')) if ref is not None else 'none'
    overrides = num.findall(qn('w:lvlOverride'))
    print(f'  numId={nid} -> abstractNumId={aid}, overrides={len(overrides)}')

# Check which numIds are actually used by paragraphs
from collections import Counter
used = Counter()
for p in doc.paragraphs:
    ppr = p._p.find(qn('w:pPr'))
    if ppr is None: continue
    npr = ppr.find(qn('w:numPr'))
    if npr is None: continue
    nid_el = npr.find(qn('w:numId'))
    ilvl_el = npr.find(qn('w:ilvl'))
    if nid_el is None or ilvl_el is None: continue
    used[(nid_el.get(qn('w:val')), ilvl_el.get(qn('w:val')))] += 1

print("\nnumId,ilvl usage counts:")
for (nid, ilvl), count in sorted(used.items()):
    print(f'  numId={nid}, ilvl={ilvl}: {count} paragraphs')
