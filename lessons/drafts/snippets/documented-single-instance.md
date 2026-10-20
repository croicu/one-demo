# Snippet: documented single instance

Demo step 4 ("adjust"). Paste into a draft lesson whose review scan flags code that is documented as
running once fleet-wide. Two parts; the ID `H-DOC` can't collide with the IDs the teacher picks.

**1. Under `## Harmless when`, add:**

- **H-DOC. The code documents that it runs as a single instance.** A `///` doc comment on the method,
  its class, or a base class it derives from states that this code runs once fleet-wide (one replica,
  one host, a singleton job). A base class's comment covers every class derived from it. The comment
  is the evidence and must be cited.

**2. Under `## Decision`, add as the first rule:**

1. H-DOC holds → clear (H-DOC)
