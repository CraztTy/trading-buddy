/**
 * How long does `import('@playwright/test')` take? Run: npm run test:e2e:diag-import
 * If this alone takes minutes, the stall is package load / AV, not your tests.
 */
const t0 = Date.now();
console.log("[diag] starting import @playwright/test …");
await import("@playwright/test");
console.log(`[diag] import done in ${Date.now() - t0} ms`);
