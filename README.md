# Doccano Tagging QA Demo (2 mini-workflows)

This bundle gives you a local Doccano instance + two mock datasets:

1) **Tag QA** (Text Classification)
   - Review each *proposed tag* for a specific chunk + document context.
   - Click **YES / NO / UNSURE**.

2) **Alias / Canonicalization QA** (Sequence-to-Sequence)
   - Review a suggested alias pair (Term A vs Term B) + contexts.
   - Type the preferred canonical string in the OUTPUT box:
     - `NO_ALIAS` (if they’re not the same concept)
     - `Term A` (if A is canonical)
     - `Term B` (if B is canonical)
     - or a unified canonical (e.g., `Department of Defense (DoD)`)

---

## 0) Prereqs
- Docker Desktop (or Docker Engine) with `docker compose` available.

---

## 1) Start Doccano

From this folder:

```bash
./scripts/up.sh
```

Open the UI:
- http://localhost:8000
- username: `admin`
- password: `password`

(These are set in `docker-compose.yml` and are safe to change locally.)

---

## 2) Create the Projects

### A) Tag QA project (Text Classification)
1. Click **Create** (top left)
2. Name: `Tag QA`
3. Project type: **Text Classification**
4. Save

Add labels:
- `YES`
- `NO`
- `UNSURE`

Import dataset:
- Left nav **Dataset** → **Actions** → **Import Dataset**
- Choose **JSONL**
- Upload: `data/tag_qa.jsonl`

Annotate:
- Left nav **Annotate**
- Click one of the 3 labels per item.

### B) Alias QA project (Sequence-to-Sequence)
1. Click **Create**
2. Name: `Alias QA`
3. Project type: **Sequence to Sequence**
4. Save

Import dataset:
- **Dataset** → **Actions** → **Import Dataset**
- Choose **JSONL**
- Upload: `data/alias_qa.jsonl`

Annotate:
- Left nav **Annotate**
- For each item, type your canonical choice in the **OUTPUT** box
  (use the rules embedded in the text).

---

## 3) Export results
For each project:
- **Dataset** → **Actions** → **Export Dataset**
- Pick an export format (JSONL is typically easiest).

---

## 4) Regenerate the JSONL from the CSVs (optional)
If you edit the mock CSVs and want new import files:

```bash
python ./scripts/prepare_datasets.py
```

---

## Notes / Known limitations of this quick demo
- Doccano is great at discrete labels (YES/NO/UNSURE). For “unified canonical strings”, the easiest way
  to capture free-text is a **Sequence-to-Sequence** project (that’s why Alias QA is set up that way).
