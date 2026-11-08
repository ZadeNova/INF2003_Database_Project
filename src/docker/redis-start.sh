#!/bin/sh
set -eu
# Redis for the cache and the rate limits. The ACL is written here, from the environment, so the password never
# appears on a command line or in `ps`; only its SHA-256 reaches the (read-only) file. The environment variable that
# carries it into the container is visible to `docker inspect`, as the other services' passwords are.
# The default user is off. The application user may use only the commands the application needs, on keys that
# start with "mercer": no FLUSHALL, CONFIG, KEYS or other dangerous command. Commands that run inside the Lua scripts
# are listed too, because Redis checks them against the same user.
ACL=/tmp/users.acl
rm -f "$ACL" # a restart keeps /tmp; root may not overwrite a file owned by redis in a sticky directory
HASH=$(printf %s "$REDIS_PASSWORD" | sha256sum | cut -d' ' -f1)
{
  echo "user default off"
  echo "user mercer on #$HASH ~mercer* -@all +ping +select +get +set +del +unlink +pexpire +pttl +scan +time" \
    "+zadd +zcard +zrange +zremrangebyscore +eval +evalsha +script|load +script|exists +client|setinfo +client|setname"
} > "$ACL"
chown redis:redis "$ACL"
chmod 400 "$ACL"

# No persistence: every key is a cache entry or a counter with an expiry, so Redis can be lost without losing data.
# `volatile-lru` evicts only keys that have an expiry, and the 64 MB cap keeps a flood of keys from using the host.
exec docker-entrypoint.sh redis-server --aclfile "$ACL" --protected-mode no --maxmemory 64mb \
  --maxmemory-policy volatile-lru --save "" --appendonly no
