# Four-player protocol smoke test

- Protocol: `2.1`
- Seats: A Mishra, B Zimone/Dina, C Mishra, D Zimone/Dina
- Initial pending principal: `pilot:A`
- After A declares a mulligan, the next principal is `pilot:B`.
  This demonstrates turn-order declarations rather than concurrent declarations.
- Pilot A still has seven cards until every player in the round has declared;
  redraws are applied together after the last declaration.
- Bootstrap estimate: 1549 tokens
- Repeated live-decision delta: 269 tokens
- A's declaration delta: 108 tokens
- Client reducer hash after the final packet: `1309ba4d4e1883ea453e`

The demo intentionally stops before B declares. It tests protocol routing,
least-privilege seat projection, turn-order mulligan input, hash-checked patches,
and token measurement without requiring card semantics.
