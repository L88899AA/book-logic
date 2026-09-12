# Security and privacy

This is a local CLI, not a network service. It does not run a generation API, upload books, automatically fetch models, or execute commands from documents. Parsing untrusted PDFs is not a sandbox: use OS restrictions and do not feed hostile files to a privileged process. Inputs are capped at 200 MiB; this does not bound all parser decompression memory.

The Skill treats document text, metadata, extracted materials and search results as data, not instructions. Source sanitization and exact quote matching are not proofs against prompt injection or semantic mistakes. A host using a remote AI still processes selected source passages remotely.

Sources, model paths, transcripts, submissions and indexes are private. Do not put a personal library inside a public repository unless its files have been individually reviewed. The source package includes only runtime, Skill, and documentation; use the distribution checker, then review git history and staged files separately.

Report suspected vulnerabilities through a private contact channel provided by the repository maintainer. If no private channel is available, request one without disclosing exploit details or sensitive inputs in a public issue. Reports should include affected versions, impact, reproduction steps, and a synthetic or sanitized sample; never attach private books or credentials.
