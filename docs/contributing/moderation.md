# Moderating discussions

Generic forum rules are already covered by the
[Code of Conduct](../../CODE_OF_CONDUCT.md), and factual challenges to a
published result go through [the dispute process](../disputes.md). This page is
for the part neither covers: the things that go wrong in the discussions of a
*benchmark* project specifically, and what a moderator should do about each.

A leaderboard attracts a particular kind of trouble. Most of it is not
misconduct and cannot be handled by a conduct policy — it is ordinary people
being confidently wrong about numbers, or companies doing their job.

## The rule behind all the others

**Moderate claims, not conclusions.** Someone arguing that a result is wrong is
doing the project's work, however bluntly. Someone asserting a number with no
run behind it is not, however politely.

That distinction is the whole of this page. A moderator who reverses it — who
removes a rude but correct correction and leaves a courteous fabrication —
makes the discussions worse than having none.

## What actually comes up

### Numbers with no run behind them

*"I get 140 tok/s on this card."*

Not misconduct, and usually not even wrong. It is also unusable: no model, no
quantization, no context length, no power state, no idea whether the machine
was doing anything else.

**Do:** ask for the result file, and link
[the quickstart](../getting-started/quickstart.md). One command produces
something the project can actually use.
**Do not:** delete it. It is a contribution waiting to happen, and deleting it
teaches everyone watching that participating is risky.
**Do:** correct it if it is being *cited*. An unsourced figure repeated three
times becomes a fact.

### Vendor marketing

Vendors are welcome — that is stated in the Code of Conduct, and their
engineers are often the most useful people in a thread. What is not welcome is
a benchmark claim from a vendor held to a lower evidence standard than one from
anybody else.

**Do:** apply exactly the rule above. A vendor figure needs a result file like
any other.
**Do:** ask for disclosure when a participant works for a company whose
hardware is under discussion, and leave the comment up once disclosed.
**Do not:** remove criticism of a vendor because the vendor complained.
Published findings stand as measured, and pressure to alter them is itself a
Code of Conduct matter.

### Hardware tribalism

*"AMD is trash", "you only tested NVIDIA because you're paid by them".*

The first is noise. The second is an accusation of fraud, and it deserves a
straight answer rather than a deletion: the tested-hardware table says exactly
what has been run, and
[docs/hardware-needed.md](../hardware-needed.md) says what has not and why.

**Do:** answer once, with the link. Lock the thread if it repeats.
**Do not:** argue. Nobody reading is persuaded by the fourth reply.

### Reopening a settled dispute

The dispute process ends in a decision with a reason. Someone will not like it.

**Do:** point at the decision. A dispute can be reopened by *new evidence*,
which means a measurement, not a restatement.
**Do:** lock the thread once that is said and ignored.

### Support questions that are really bug reports

Long threads about a failing run belong in an issue where they can be tracked
and closed.

**Do:** convert it, keep the link, and say why.

## Actions, and when each is right

| Action | When | Say why |
|---|---|---|
| Reply | Almost always | — |
| Convert to issue | A bug or a feature request in disguise | Yes |
| Lock | The point has been made and the thread is repeating | Yes, in a final comment |
| Hide as off-topic | Genuinely unrelated, no information lost | Yes |
| Delete | Doxxing, spam, or malware links | Not publicly |
| Block | Repeated conduct violations after a warning | To the person |

**Say why, in the thread, every time except deletion.** Moderation nobody can
see the reason for is indistinguishable from moderation with no reason, and
this project's entire argument is that it shows its working.

Deletion is the exception because restating the content is the harm.

## Who moderates

Maintainers, per [GOVERNANCE.md](../../GOVERNANCE.md). A moderator with a stake
in the outcome — their own result under discussion, their own employer's
hardware — should hand the thread to another maintainer and say so publicly.
Where nobody else is available, act and disclose the conflict in the same
comment.

## Recording it

Lock and delete actions on threads about published results go in the same log
as disputes, with the thread link and one line of reason. The point is not
bureaucracy: it is that a pattern of quietly removing inconvenient threads is
invisible to everyone except the person doing it, and a log makes it visible to
them too.

Replies, conversions and off-topic hides need no record. The thread is the
record.
