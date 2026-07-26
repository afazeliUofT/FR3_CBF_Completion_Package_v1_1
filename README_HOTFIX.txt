FR3 CBF v1.1 — TAFL detailed pair audit hotfix

Adds:
  scripts/03_1_audit_tafl_auth_freq_pairs.py

Purpose:
  Read-only second-stage audit of auth_number + frequency groups.
  It classifies exact one-TX/one-RX groups, Point-to-Point service/subservice,
  fully authorized status, GTA receivers, fade-margin availability, and
  ambiguous groups. It never creates final paired_fs_links.csv.

Reviewed script SHA-256:
  c03ab0e5afb5bde926df3fdbb1cc4c991d3a8197bf57017410d4cf9c5992e627
