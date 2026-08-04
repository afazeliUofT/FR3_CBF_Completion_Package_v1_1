# Reproducibility and Source Scope

## Frozen scientific evidence

The package includes the final fresh-holdout archive and the seed-44052 completion archive, each with basename-only SHA-256 sidecars. These are sufficient to regenerate the new SA.509 frozen-action sensitivity and to verify the final holdout bindings.

## Metadata repair policy

The corrected `patched_inputs/` files are separate from the immutable executed campaign package. They repair documentation and unused static sensitivity accounting only. The frozen campaign inputs and result hashes are not rewritten.

## External standards

The manuscript cites the official standards, while this package includes the project's source records, hashes, and validation audits rather than redistributing every external copyrighted PDF. The principal external sources are:

- Recommendation ITU-R SA.1027-6 (08/2019), Table 1;
- Recommendation ITU-R SA.509-3 (12/2013);
- Recommendation ITU-R P.452-18 and ITU-R SG3 validation examples v18.0;
- 3GPP TR 38.901 and ETSI TR 138 901 V19.4.0;
- Sionna 2.0.1 documentation and source release;
- ISED SRSP-307.7;
- NRCan MRDEM source records already retained in the wider project archive.

## Reproduction levels

- **Level 1, package audit:** hashes, metadata, citations, LaTeX compilation, and frozen-action sensitivity; local CPU only.
- **Level 2, scientific rerun:** use the previously frozen job package and cluster environment; not required for this revision.
- **Level 3, regulatory certification:** not claimed and not supplied by this research package.
