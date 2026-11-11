// "The database says no" (backlog #38), MongoDB half: the validators and the unique index refuse bad documents.
// Runs as the application's readWrite user. Every insert below is refused, so nothing is written; the final
// cleanup only removes the test id in case a validator was ever loosened.
// Run (from the repository root, with the stack up); the script is copied into the container and run as a file, and the
// password is read from the container's environment, never typed or shown:
//   docker compose exec -T mongo sh -c 'cat > /tmp/says_no.js && mongosh --quiet --username="$MONGO_APP_USER" --password="$MONGO_APP_PASSWORD" --authenticationDatabase admin "$MONGO_DB" /tmp/says_no.js' < scripts/demo/database_says_no.js

function ruleBroken(e) {
  // The first failed $jsonSchema rule, as "field: reason (value)".
  const rules = e.errInfo && e.errInfo.details && e.errInfo.details.schemaRulesNotSatisfied;
  const prop = rules && rules[0] && rules[0].propertiesNotSatisfied && rules[0].propertiesNotSatisfied[0];
  if (!prop) return "";
  const d = prop.details[0];
  return prop.propertyName + ": " + d.reason + " (" + JSON.stringify(d.specifiedAs) + ")";
}

function attempt(title, fn) {
  print("\n" + title);
  try {
    fn();
    print("   ACCEPTED (unexpected)");
  } catch (e) {
    print("   REFUSED: " + String(e.errmsg || e.message).split("\n")[0].replace(/ to execute command.*$/, "").slice(0, 150));
    const rule = ruleBroken(e);
    if (rule) print("   rule broken: " + rule);
  }
}

print("connected as " + db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUsers[0].user + " to " + db.getName());

attempt("1. A product specification must have the documented shape ($jsonSchema validator)", () =>
  db.product_specs.insertOne({ _id: NumberLong("900000001"), description: 42 }));

attempt("2. A review score must be an integer from 1 to 5", () => {
  const r = db.reviews.findOne({}, { _id: 0 });
  r.order_line_id = NumberLong("900000001");
  r.score = 6;
  db.reviews.insertOne(r);
});

attempt("3. One review per order line: a second review of the same line hits the unique index", () => {
  const r = db.reviews.findOne({}, { _id: 0 });
  db.reviews.insertOne(r);
});

attempt("4. The latest-reviews subset embedded in a specification holds at most five reviews", () => {
  const s = db.product_specs.findOne({ "latest_reviews.4": { $exists: true } });
  db.product_specs.updateOne({ _id: s._id }, { $push: { latest_reviews: s.latest_reviews[0] } });
});

attempt("5. The application user has readWrite on its own database only: reading the admin users is refused", () =>
  db.getSiblingDB("admin").getUsers());

const leftover =
  db.product_specs.deleteOne({ _id: NumberLong("900000001") }).deletedCount +
  db.reviews.deleteOne({ order_line_id: NumberLong("900000001") }).deletedCount;
print("\nDocuments written by this script: " + leftover);
