/**
 * One line after test discovery (ASCII for Windows consoles).
 * @implements {import("@playwright/test/reporter").Reporter}
 */
export default class EarlyReporter {
  onBegin(_config, suite) {
    const n = suite.allTests().length;
    process.stdout.write(
      `[playwright] EarlyReporter.onBegin: ${n} test(s), preparing browser...\n`
    );
  }
}
