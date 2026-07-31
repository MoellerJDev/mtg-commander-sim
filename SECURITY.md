# Security policy

## Reporting

Report vulnerabilities privately through the repository's GitHub Security
Advisory interface. Do not open a public issue containing a capability,
checkpoint, opposing hand, library order, pilot memory, provider credential, or
reproduction record with hidden information.

Include the affected commit, impact, minimal reproduction, and whether any
private game artifact was exposed. Rotate any real credential or bearer
capability before sharing a sanitized report.

## Security-sensitive boundaries

The following are treated as security defects:

- bypassing fixed-seat capability or principal checks
- exposing another seat's hidden zones, memory, packets, or choices
- exposing authoritative checkpoints through a pilot tool
- allowing pilots or a parent coordinator to mutate state outside legal actions
- accepting forged provider, model, thread, or seat identity
- persisting live capabilities in tracked fixtures
- path traversal from a seat-scoped tool into analyst or run artifacts

Custom-agent instructions are not an operating-system sandbox. The fixed-seat
tool and projection layers enforce the application boundary; use an isolated,
read-only workspace when filesystem isolation must also be demonstrated.

## Supported version

Only the current development line receives security fixes. The repository is
public, but the project remains experimental and has not undergone an
independent security audit.
