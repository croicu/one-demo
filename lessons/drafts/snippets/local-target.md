# Snippet: local target

Demo step 4 ("adjust"). Paste into a draft lesson whose review scan flags code that retries a target on
the same host. The incident can't teach this: it was about a shared server and never mentions local
ones. Two parts; the ID `H-LOCAL` can't collide with the IDs the teacher picks.

**1. Under `## Harmless when`, add:**

- **H-LOCAL. The retried target is local to the host.** The call goes to a loopback address
  (`localhost`, `127.0.0.1`, `::1`), a local file or device, or an in-process resource. Each host talks
  to its own copy of the target, so failures can't synchronize callers across a fleet, however many
  hosts run the code. The line naming the target is the evidence and must be cited.

**2. Under `## Decision`, add as the first rule:**

1. H-LOCAL holds → clear (H-LOCAL)
