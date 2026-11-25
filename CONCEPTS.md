# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound captures and refreshes learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Identity
The stable name a service keeps across restarts and page loads, made of the kind of thing that runs it and that thing's own name. It stays the same when the service's ports or its display name change.

A service registered by a name that matches nothing discovered has a manual identity: nothing is found listening for it, so it has no way to be reached except the link it was given.

## Annotation
What the household has chosen to say about one Identity, such as its display name, description or whether it is hidden. Discovery finds services; Annotations only describe them, so removing one does not remove a running service from the page. A service with a manual Identity is the exception: it is listed only because of its Annotation.

Whether a service is hidden can be left unchosen, which is different from choosing to show it: an unchosen service follows the default, and noise is hidden by default.

## Registration
A service's own request to be described, which is recorded as an Annotation on the Identity its name matches. Services may register again at any time, and a service does not need to register to be listed.

## Held registration
A Registration set aside for review because it carries a different value for something the household set on the page. Page edits win, so nothing it disagrees with is applied until someone accepts it.

Each Identity has at most one, and a newer one replaces it. It goes away when it is accepted or dismissed, when the conflict ends, or when its Annotation is removed.
