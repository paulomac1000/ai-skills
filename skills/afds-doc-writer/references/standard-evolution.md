# Evolving AFDS

A proposed mandatory rule needs:

- a documented failure it prevents,
- at least three representative examples,
- a machine check when feasible,
- mutation cases that prove the check catches the failure,
- retrieval or task-completion evidence when the rule affects document shape,
- an ablation showing the rule contributes independently,
- a migration and rollback plan.

Stop iterating when two consecutive benchmark rounds improve the primary score by less than 0.5 percentage points and introduce no new high-severity defect detection. Record the stopping criterion in the benchmark report.
