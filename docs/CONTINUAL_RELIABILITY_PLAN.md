# Continual harness failure accounting and resume

The user's nine requested changes are the specification. Keep all model calls
on Codex, run only offline tests, and preserve official grading and isolation.

- [x] Require explicit models, dates, research schema/language, and configurable limits.
- [x] Grade failed tasks with official empty submissions; count their scores in every aggregate.
- [x] Persist stream/task/refinement progress; stop on refinement/rollback/finish failures and resume the same lineage.
- [x] Record every fetch attempt/failure, dropped hit, discarded proposal and skipped delete.
- [x] Replace implicit report selection with explicit base commits and safe unseen-task ancestry.
- [x] Update documentation, review integration, run the full offline suite and capture complete output.

Resume takes an explicit run id. The manifest fixes configuration, ordered task
identities, starting commit and lineage. Completed tasks are never rerun.
Durable research/grading/finish phases prevent a refinement retry from repeating
research or grading. Refinement proposals and individual edit identities are
persisted before application; replay recognizes already committed edits.
An interrupted worker is an observed failure, not a fresh research attempt.
It receives an official empty-submission grade. If even that grader cannot
complete, the stream remains interrupted with a visible error until resume.

Interfaces: config supplies required runtime limits; CLI passes base/resume and
explicit research fields to orchestration; adapters provide canonical empty
submissions; completed report rows always contain official finite scores.
Only research artifacts and self-check enter Session/Refiner. Grade checkpoint
state stays in reports. Audit logs preserve discarded work and failed attempts.

Review focus: interruption between commit and checkpoint; duplicate refinement
or outcome application; failure in the final worker turn; grading failure and
empty grading retry; no-learning branch restoration; incompatible resume config,
changed tasks, unsafe bases, and discarded evidence under concurrent requests.
