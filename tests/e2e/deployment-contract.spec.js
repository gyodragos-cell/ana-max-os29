import { expect, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = process.cwd();
const site = resolve(root, "site/portfolio");
const workflow = readFileSync(resolve(root, ".github/workflows/static.yml"), "utf8");

function approvedPublishedPages() {
  const copyCommand = workflow.split(/\r?\n/).find((line) =>
    line.trim().startsWith("cp site/portfolio/index.html")
  );
  expect(copyCommand, "GitHub Pages must stage explicit, reviewed HTML files").toBeTruthy();
  const staged = new Set(
    [...copyCommand.matchAll(/site\/portfolio\/([\w-]+\.html)/g)].map((m) => m[1])
  );
  return staged;
}

test("the GitHub Pages artifact actually includes the new public explainer", () => {
  const staged = approvedPublishedPages();
  expect(staged.has("start-here.html")).toBe(true);
  expect(workflow).toContain("test -s _site/start-here.html");
  expect(existsSync(resolve(site, "start-here.html"))).toBe(true);
});

test("every local HTML page linked from a published page is deployed too", () => {
  const staged = approvedPublishedPages();
  expect(staged.size).toBeGreaterThanOrEqual(5);
  for (const file of staged) {
    const absolute = resolve(site, file);
    expect(existsSync(absolute), "missing approved source " + file).toBe(true);
    const html = readFileSync(absolute, "utf8");
    const links = [...html.matchAll(/href=["']\.\/([^"'#?]+\.html)(?:#[^"']*)?["']/g)]
      .map((match) => match[1]);
    for (const linkedFile of links) {
      expect(staged.has(linkedFile),
        file + " links to " + linkedFile + ", but the Pages artifact omits it"
      ).toBe(true);
    }
  }
});

test("deployment copies only explicit public HTML, never private lab directories", () => {
  const staged = approvedPublishedPages();
  expect([...staged].sort()).toEqual([
    "core.html", "cv.html", "index.html", "live.html", "start-here.html"
  ]);
  const copyCommand = workflow.split(/\r?\n/).find((line) =>
    line.trim().startsWith("cp site/portfolio/index.html")
  );
  expect(copyCommand).not.toMatch(/-r\b|\.\.\/|\*|private|memory|logs|\.db/i);
});
