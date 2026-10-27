#!/bin/bash
set -eu
export MONGOSH_DISABLE_TELEMETRY=1
# Single-node replica set rs0 with authentication (a replica set is needed for transactions). The keyfile is
# generated here, into a named volume, because a bind-mounted file cannot be chmod 400 on Windows.
KEY=/keyfile/mongo.key
if [ ! -s "$KEY" ]; then
  openssl rand -base64 756 > "$KEY"
fi
chown mongodb:mongodb "$KEY"
chmod 400 "$KEY"

# Runs beside mongod. On the first start the localhost exception allows rs.initiate and the first user without
# credentials; afterwards the root user is used. Every step is safe to repeat.
initialise() {
  until mongosh --quiet --norc --eval 'db.hello().ok' >/dev/null 2>&1; do sleep 1; done
  if ! mongosh --quiet --norc --username="$MONGO_ROOT_USER" --password="$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
      --eval 'rs.status().ok' >/dev/null 2>&1; then
    mongosh --quiet --norc --eval 'rs.initiate({_id: "rs0", members: [{_id: 0, host: "bench-mongo:27017"}]})'
    until mongosh --quiet --norc --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)' >/dev/null 2>&1; do sleep 1; done
    mongosh --quiet --norc --eval 'db.getSiblingDB("admin").createUser({
      user: process.env.MONGO_ROOT_USER, pwd: process.env.MONGO_ROOT_PASSWORD, roles: ["root"]})'
  fi
  # The benchmark user: readWrite on bench only.
  mongosh --quiet --norc --username="$MONGO_ROOT_USER" --password="$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval '
    const admin = db.getSiblingDB("admin");
    if (!admin.getUser(process.env.MONGO_APP_USER)) {
      admin.createUser({user: process.env.MONGO_APP_USER, pwd: process.env.MONGO_APP_PASSWORD, roles: [
        {role: "readWrite", db: "bench"}]});
    }'
  echo "MongoDB replica set rs0 and users are ready."
}
initialise &

exec gosu mongodb mongod --wiredTigerCacheSizeGB 0.75 --replSet rs0 --keyFile "$KEY" --bind_ip_all
