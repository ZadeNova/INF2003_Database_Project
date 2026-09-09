// Command bench runs the database performance harness.
//
// It talks to Postgres and MongoDB directly rather than through the FastAPI layer,
// so the numbers measure the database engines and not web-framework overhead.
package main

func main() {
	// TODO: parse flags (target db, workload, iterations, concurrency), dial both
	// databases, run the selected workload, print the report.
}
