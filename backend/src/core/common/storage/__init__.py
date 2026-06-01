"""Storage layer — three persistence paradigms used by the agentic pipeline.

The folder mixes three different storage technologies on purpose; each is
single-purpose and small enough that splitting them into separate sibling
folders would be over-engineering.

  - **`database/`** (subpackage) — relational state via SQLAlchemy: cases,
    templates, attorney roster, reference data, and other authored entities.
    Repositories live in `database/repositories/`; ORM models in
    `database/models.py`. This is the most-touched of the three.
  - **`r2.py`** (single-file module) — Cloudflare R2 (S3-compatible) blob
    storage for binary artifacts: docx templates, generated docx, supporting
    PDFs, petition PDFs. Async boto3 wrapper exposing a singleton
    `r2_service`.
  - **`vectorstore.py`** (single-file module) — pgvector wrapper for
    similarity search. Per-case `case_file` / `gmail` / `courtdrive`
    collections drive the case-vector source params.

Asymmetry note: `database/` is a subpackage because it has many files;
`r2.py` and `vectorstore.py` are single files because they expose one
service each. Idiomatic Python — promote a module to a package only when
it has internal structure worth splitting.
"""
