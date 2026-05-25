const baseUrl = process.env.SC_WORKER_URL || "http://localhost:8787";

const routes = [
  "/api/health",
  "/api/bootstrap",
  "/api/members",
  "/api/schedule",
  "/api/settings",
  "/api/availability",
  "/api/transactions",
  "/api/wallboard_display",
  "/api/member_dashboard",
];

let failures = 0;

for (const route of routes) {
  const url = `${baseUrl}${route}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      failures += 1;
      console.error(`${route} -> HTTP ${response.status}`);
      continue;
    }
    const payload = await response.json();
    console.log(`${route} -> ${response.status} (${Object.keys(payload).join(", ")})`);
  } catch (error) {
    failures += 1;
    console.error(`${route} -> ${error.message}`);
  }
}

if (failures > 0) {
  process.exitCode = 1;
}
