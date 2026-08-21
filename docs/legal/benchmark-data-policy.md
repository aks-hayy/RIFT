# Benchmark Data Policy

RIFT separates benchmark evidence from metadata and local measurements.

Every imported benchmark record must retain its source identifier, source URL
or snapshot provenance, benchmark family, task, metric, normalized value,
observation time, model revision, artifact relation, confidence, and
redistribution status. RIFT never averages unrelated benchmark families as if
they were one universal accuracy score.

External leaderboard data is opt-in and must arrive through a permitted,
signed snapshot or an operator-supplied import. Unsigned snapshots are
fail-closed as trusted evidence. RIFT stores provenance and derived scores; it
does not republish source datasets or claim ownership of external evaluations.

Published scores are labelled `PUBLISHED`; repository metadata is
`ESTIMATED`; RIFT-run measurements are `MEASURED_LOCAL`; unavailable or
unsupported choices are `BLOCKED`. A local finalist verification is a bounded
deployment smoke/benchmark, not a universal quality claim.
