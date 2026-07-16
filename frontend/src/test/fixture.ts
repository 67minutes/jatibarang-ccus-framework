import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Resolve a repo-relative fixture path. Vitest runs with the frontend directory
 * as cwd, and jsdom's `import.meta.url` is not a file:// URL, so we anchor on
 * cwd rather than the module URL.
 */
export function readFixture(relativeToFrontend: string): string {
  return readFileSync(resolve(process.cwd(), relativeToFrontend), "utf8");
}
