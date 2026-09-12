# Third-party notices

Book Logic code and original synthetic examples are MIT-licensed. This does not license users' source documents, derivative collections, or model weights.

## Required runtime dependencies

- **pypdf**: BSD-3-Clause. https://github.com/py-pdf/pypdf/blob/main/LICENSE
- **jsonschema**: MIT. https://github.com/python-jsonschema/jsonschema/blob/main/COPYING
- SQLite is supplied by Python's runtime. https://www.sqlite.org/copyright.html

Dependencies are installed separately and retain their own copyright and license files. Transitive dependencies must be included in the release environment's dependency review; do not represent this list as an exhaustive software bill of materials.

## Optional semantic dependencies

NumPy, Sentence Transformers, PyTorch, Transformers and their dependencies retain their respective licenses. Model weights are not distributed. Users must review the license and model card of the weights they select independently of the runtime's license.

## Design acknowledgement

The staged extraction and on-demand navigation design was informed by book-to-skill: https://github.com/virgiliojr94/book-to-skill . No upstream implementation or Skill template is bundled.

Before a public release, audit the built wheel/sdist and the chosen dependency lock, preserve required notices, and review any later copied third-party code individually.
