"""
validate.py  (a development check, used by tests/check.py; not part of the converter)

Checks a .docx against the parts of the OOXML schema Word actually enforces.

Word rejects or silently "repairs" files whose elements appear out of
sequence. LibreOffice, Google Docs and most viewers do not, which is why a
document can look perfect everywhere except the one place it matters.

    python md_to_docx/tests/validate.py out.docx

Exits non-zero if anything is wrong. Standard library only.
"""

from __future__ import annotations

import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def local(tag):
    return tag.split("}")[-1]


def q(name):
    return "{%s}%s" % (W, name)


# --------------------------------------------------------------------------- #
# schema sequences (ECMA-376). Order matters; membership does not.
# --------------------------------------------------------------------------- #
ORDER = {
    "pPr": (
        "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr "
        "suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap "
        "overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd "
        "snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap "
        "jc textDirection textAlignment textboxTightWrap outlineLvl divId "
        "cnfStyle rPr sectPr pPrChange"
    ).split(),
    "rPr": (
        "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow "
        "emboss imprint noProof snapToGrid vanish webHidden color spacing w kern "
        "position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em "
        "lang eastAsianLayout specVanish oMath rPrChange"
    ).split(),
    # The one that bites: suff comes BEFORE lvlText, lvlJc comes AFTER it.
    "lvl": ("start numFmt lvlRestart pStyle isLgl suff lvlText lvlPicBulletId " "legacy lvlJc pPr rPr").split(),
    "abstractNum": ("nsid multiLevelType tmpl name styleLink numStyleLink lvl").split(),
    "num": "abstractNumId lvlOverride".split(),
    "sectPr": (
        "headerReference footerReference footnotePr endnotePr type pgSz pgMar "
        "paperSrc pgBorders lnNumType pgNumType cols formProt vAlign noEndnote "
        "titlePg textDirection bidi rtlGutter docGrid printerSettings "
        "sectPrChange"
    ).split(),
    "settings": (
        "writeProtection view zoom removePersonalInformation removeDateAndTime "
        "doNotDisplayPageBoundaries displayBackgroundShape "
        "printPostScriptOverText printFractionalCharacterWidth printFormsData "
        "embedTrueTypeFonts embedSystemFonts saveSubsetFonts saveFormsData "
        "mirrorMargins alignBordersAndEdges bordersDoNotSurroundHeader "
        "bordersDoNotSurroundFooter gutterAtTop hideSpellingErrors "
        "hideGrammaticalErrors activeWritingStyle proofState formsDesign "
        "attachedTemplate linkStyles stylePaneFormatFilter stylePaneSortMethod "
        "documentType mailMerge revisionView trackChanges doNotTrackMoves "
        "doNotTrackFormatting documentProtection autoFormatOverride "
        "styleLockTheme styleLockQFSet defaultTabStop autoHyphenation "
        "consecutiveHyphenLimit hyphenationZone doNotHyphenateCaps showEnvelope "
        "summaryLength clickAndTypeStyle defaultTableStyle evenAndOddHeaders "
        "bookFoldRevPrinting bookFoldPrinting bookFoldPrintingSheets "
        "drawingGridHorizontalSpacing drawingGridVerticalSpacing "
        "displayHorizontalDrawingGridEvery displayVerticalDrawingGridEvery "
        "doNotUseMarginsForDrawingGridOrigin drawingGridHorizontalOrigin "
        "drawingGridVerticalOrigin doNotShadeFormData noPunctuationKerning "
        "characterSpacingControl printTwoOnOne strictFirstAndLastChars "
        "noLineBreaksAfter noLineBreaksBefore savePreviewPicture "
        "doNotValidateAgainstSchema saveInvalidXml ignoreMixedContent "
        "alwaysShowPlaceholderText doNotDemarcateInvalidXml saveXmlDataOnly "
        "useXSLTWhenSaving saveThroughXslt showXMLTags "
        "alwaysMergeEmptyNamespace updateFields hdrShapeDefaults footnotePr "
        "endnotePr compat docVars rsids mathPr uiCompat97To2003 attachedSchema "
        "themeFontLang clrSchemeMapping doNotIncludeSubdocsInStats "
        "doNotAutoCompressPictures forceUpgrade captions readModeInkLockDown "
        "smartTagType schemaLibrary shapeDefaults doNotEmbedSmartTags "
        "decimalSymbol listSeparator"
    ).split(),
    "numbering": ("numPicBullet abstractNum num numIdMacAtCleanup").split(),
}


def check_order(element, sequence_name, path, problems):
    order = ORDER[sequence_name]
    last_rank, last_name = -1, None
    for child in element:
        name = local(child.tag)
        if name not in order:
            continue
        rank = order.index(name)
        if rank < last_rank:
            problems.append("%s: <w:%s> appears after <w:%s>; schema requires it before" % (path, name, last_name))
        last_rank, last_name = rank, name


def check_paragraphs(root, part, problems):
    for index, paragraph in enumerate(root.iter(q("p"))):
        children = list(paragraph)
        if not children:
            continue
        names = [local(c.tag) for c in children]
        if "pPr" in names and names[0] != "pPr":
            problems.append(
                "%s p[%d]: <w:pPr> is child #%d; Word requires it FIRST "
                "(found <w:%s> before it)" % (part, index, names.index("pPr"), names[0])
            )
        ppr = paragraph.find(q("pPr"))
        if ppr is not None:
            check_order(ppr, "pPr", "%s p[%d]/pPr" % (part, index), problems)
            rpr = ppr.find(q("rPr"))
            if rpr is not None:
                check_order(rpr, "rPr", "%s p[%d]/pPr/rPr" % (part, index), problems)
        for run in paragraph.iter(q("r")):
            rpr = run.find(q("rPr"))
            if rpr is not None:
                check_order(rpr, "rPr", "%s p[%d]/r/rPr" % (part, index), problems)


def check_fields(root, part, problems):
    """A field needs begin / instrText / separate? / end, and Word wants each
    part in its own run."""
    for index, paragraph in enumerate(root.iter(q("p"))):
        depth = 0
        for run in paragraph.iter(q("r")):
            kinds = [local(c.tag) for c in run]
            fld = [c.get(q("fldCharType")) for c in run if local(c.tag) == "fldChar"]
            if len([k for k in kinds if k in ("fldChar", "instrText")]) > 1:
                problems.append(
                    "%s p[%d]: one run holds several field parts (%s); Word "
                    "wants one part per run" % (part, index, ",".join(kinds))
                )
            for kind in fld:
                if kind == "begin":
                    depth += 1
                elif kind == "end":
                    depth -= 1
        if depth != 0:
            problems.append("%s p[%d]: unbalanced field (begin/end mismatch)" % (part, index))


def check_bookmarks(root, part, problems):
    starts, ends = {}, set()
    for element in root.iter():
        name = local(element.tag)
        if name == "bookmarkStart":
            bid = element.get(q("id"))
            if bid in starts:
                problems.append("%s: duplicate bookmark id %s" % (part, bid))
            starts[bid] = element.get(q("name"))
        elif name == "bookmarkEnd":
            ends.add(element.get(q("id")))
    for bid, bname in starts.items():
        if bid not in ends:
            problems.append("%s: bookmark %r has no bookmarkEnd" % (part, bname))

    names = set(starts.values())
    counts = Counter(starts.values())
    for bname, n in counts.items():
        if n > 1:
            problems.append("%s: bookmark name %r defined %d times" % (part, bname, n))

    for link in root.iter(q("hyperlink")):
        anchor = link.get(q("anchor"))
        if anchor and anchor not in names:
            problems.append("%s: hyperlink anchor %r has no bookmark" % (part, anchor))

    refs = set()
    for instr in root.iter(q("instrText")):
        text = (instr.text or "").strip()
        if text.upper().startswith("PAGEREF"):
            refs.add(text.split()[1])
    for ref in refs:
        if ref not in names:
            problems.append("%s: PAGEREF target %r has no bookmark" % (part, ref))
    return names, refs


def check_numbering(root, problems):
    if root is None:
        return
    check_order(root, "numbering", "numbering.xml", problems)

    seen_num = False
    for child in root:
        name = local(child.tag)
        if name == "num":
            seen_num = True
        elif name == "abstractNum" and seen_num:
            problems.append("numbering.xml: <w:abstractNum> after <w:num>; all abstract " "definitions must come first")

    abstract_ids = set()
    for definition in root.findall(q("abstractNum")):
        abstract_ids.add(definition.get(q("abstractNumId")))
        check_order(definition, "abstractNum", "abstractNum[%s]" % definition.get(q("abstractNumId")), problems)
        for lvl in definition.findall(q("lvl")):
            check_order(
                lvl,
                "lvl",
                "abstractNum[%s]/lvl[%s]" % (definition.get(q("abstractNumId")), lvl.get(q("ilvl"))),
                problems,
            )

    for instance in root.findall(q("num")):
        check_order(instance, "num", "num[%s]" % instance.get(q("numId")), problems)
        target = instance.find(q("abstractNumId"))
        if target is not None and target.get(q("val")) not in abstract_ids:
            problems.append(
                "numbering.xml: num %s points at missing "
                "abstractNum %s" % (instance.get(q("numId")), target.get(q("val")))
            )


def check_num_refs(doc_root, numbering_root, problems):
    if numbering_root is None:
        return
    defined = {n.get(q("numId")) for n in numbering_root.findall(q("num"))}
    for numpr in doc_root.iter(q("numPr")):
        num_id = numpr.find(q("numId"))
        if num_id is not None and num_id.get(q("val")) not in defined:
            problems.append("document.xml: numPr references undefined numId %s" % num_id.get(q("val")))


def check_sections(root, problems):
    for index, sect in enumerate(root.iter(q("sectPr"))):
        check_order(sect, "sectPr", "sectPr[%d]" % index, problems)


def check_settings(root, problems):
    if root is None:
        return
    check_order(root, "settings", "settings.xml", problems)


def validate(path):
    problems = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()

        doc = ET.fromstring(zf.read("word/document.xml"))
        check_paragraphs(doc, "document.xml", problems)
        check_fields(doc, "document.xml", problems)
        marks, refs = check_bookmarks(doc, "document.xml", problems)
        check_sections(doc, problems)

        numbering = ET.fromstring(zf.read("word/numbering.xml")) if "word/numbering.xml" in names else None
        check_numbering(numbering, problems)
        check_num_refs(doc, numbering, problems)

        settings = ET.fromstring(zf.read("word/settings.xml")) if "word/settings.xml" in names else None
        check_settings(settings, problems)

        for name in names:
            base = name.rsplit("/", 1)[-1]
            if base.startswith(("header", "footer")) and name.endswith(".xml"):
                part = ET.fromstring(zf.read(name))
                check_paragraphs(part, base, problems)
                check_fields(part, base, problems)

        summary = {
            "bookmarks": len(marks),
            "pagerefs": len(refs),
            "update_on_open": settings is not None and settings.find(q("updateFields")) is not None,
        }
    return problems, summary


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    target = args[0] if args else "out.docx"
    problems, summary = validate(target)

    print("validating %s" % target)
    print(
        "  bookmarks: %d, PAGEREF targets: %d, update-fields-on-open: %s"
        % (summary["bookmarks"], summary["pagerefs"], summary["update_on_open"])
    )
    if not problems:
        print("\nOK: no schema-order or reference problems found.")
        return 0
    print("\n%d problem(s):" % len(problems))
    for line in problems[:60]:
        print("  " + line)
    if len(problems) > 60:
        print("  ... and %d more" % (len(problems) - 60))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
