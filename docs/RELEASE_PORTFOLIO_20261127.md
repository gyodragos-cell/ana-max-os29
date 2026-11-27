# ANA MAX OS29 - Public Tower Control V2 (November 27, 2026)

**Same memory. Independent reasoning. Shared evidence.**

This dated portfolio release replaces the legacy OS-22 download as the current public starting point. It packages the public OS29 source and the browser-only Tower Control V2 demonstration. It is not a release of the private PC1313 laboratory or a complete local AI operating system.

## Start here

- [Interactive Tower Control V2](https://gyodragos-cell.github.io/ana-max-os29/live.html): 11 views, an illustrative OS28 tool catalog, sample services, mission handoff, evidence and four-terminal supervision.
- [Two AI agents. One real bug.](https://gyodragos-cell.github.io/ana-max-os29/wow.html): historical evidence of a collaborative cosine similarity repair.
- [Plain-language walkthrough](https://gyodragos-cell.github.io/ana-max-os29/start-here.html)
- [Installable OS29 Core v0.1.0](https://github.com/gyodragos-cell/ana-max-os29-core/releases/tag/v0.1.0): separate portable release.

## Verification and scope

The public portfolio source at commit 6dfe13c5 passed 44 Python tests and 20 Playwright tests in an independently extracted source archive on Windows. The post-merge Python, browser and Pages workflows passed. The release workflow repeats the public checks before publishing.

The November 22 private laboratory experiment reported 433 passing tests, seven targeted regressions and 50 randomized sets of 12 vectors. Local Qwen2.5-Coder 7B contributed a partial patch; GPT-6 corrected one mathematical expression and verified the combined repair. Those historical results are not the current public test counts or evidence of an autonomous repair by Qwen alone.

The public Tower is static HTML/CSS/JavaScript with simulated controls, historical screenshots and explicitly labeled evidence. It does not operate a visitor's PC, start local services, connect to PC1313 or access private memory. Experimental ONNX retrieval is not shipped as the public Core's retrieval engine. Experience Transfer and controlled with/without-memory benchmarks remain research objectives.

## Use the public source

Python 3.11 or later. From this release's extracted source directory:

```sh
python -m venv .venv
```

On Windows activate with `.venv\Scripts\activate` (Command Prompt); on POSIX use `source .venv/bin/activate`. Then:

```sh
python -m pip install -e ".[test]"
python -m pytest -q
python -m os29.cli --help
```

To preview the static site locally:

```sh
python -m http.server 4173 --bind 127.0.0.1 --directory site/portfolio
```

Open http://127.0.0.1:4173/ . To use the portable Core instead, follow its own release instructions linked above.

No private databases, raw operator logs, credentials or local model weights are included. The old tag `v22.0.0` remains historical and is not the recommended installation.
