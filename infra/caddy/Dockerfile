# Caddy with the rate-limit module, built on the server via docker compose.
#
# The official caddy image carries no rate limiting, so the binary has to be
# recompiled with github.com/mholt/caddy-ratelimit. Both the Caddy version
# and the module commit are pinned: the module is third party and an
# unpinned build is not reproducible. Builder and runtime must be the exact
# same Caddy version.
#
# The pinned module commit is newer than tag v0.1.0 because ipv6_prefix
# (used by the render zone in the Caddyfile) landed after that tag.
#
# Bumping: change the Caddy version in both FROM lines together, and
# RATELIMIT_VERSION to a commit sha or tag from the module repo.

FROM caddy:2.11.4-builder AS builder

ARG RATELIMIT_VERSION=5625512f24f6f59d6f64fb3aafe5eecff0b286db
RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit@${RATELIMIT_VERSION}

FROM caddy:2.11.4-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
