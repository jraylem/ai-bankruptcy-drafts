/**
 * Convert coverage-summary.json into a markdown report and print to stdout.
 * Used by the test-agt CI job to append the report to $GITHUB_STEP_SUMMARY.
 *
 * Usage: node scripts/coverage-summary.cjs > $GITHUB_STEP_SUMMARY
 */

const fs = require('fs');
const path = require('path');

const SUMMARY_FILE = path.join(process.cwd(), 'coverage', 'coverage-summary.json');

if (!fs.existsSync(SUMMARY_FILE)) {
  process.stderr.write(`coverage-summary.json missing at ${SUMMARY_FILE}\n`);
  process.exit(0);
}

const data = JSON.parse(fs.readFileSync(SUMMARY_FILE, 'utf8'));
const cwd = process.cwd().replace(/\\/g, '/');

const fmt = (m) => `${m.pct.toFixed(1)}% (${m.covered}/${m.total})`;
const total = data.total;

const out = [
  '## Coverage Report (studio scope)',
  '',
  '| Metric | Coverage |',
  '|---|---|',
  `| Statements | ${fmt(total.statements)} |`,
  `| Branches | ${fmt(total.branches)} |`,
  `| Functions | ${fmt(total.functions)} |`,
  `| Lines | ${fmt(total.lines)} |`,
  '',
  '<details><summary>Per-file breakdown (sorted by lowest line coverage)</summary>',
  '',
  '| File | Stmts | Branches | Funcs | Lines |',
  '|---|---:|---:|---:|---:|',
];

const rows = Object.keys(data)
  .filter((k) => k !== 'total')
  .map((abs) => {
    const rel = abs.replace(/\\/g, '/').replace(cwd + '/', '');
    return { rel, m: data[abs] };
  })
  .sort((a, b) => a.m.lines.pct - b.m.lines.pct);

for (const { rel, m } of rows) {
  out.push(
    `| \`${rel}\` | ${m.statements.pct.toFixed(1)}% | ${m.branches.pct.toFixed(1)}% | ${m.functions.pct.toFixed(1)}% | ${m.lines.pct.toFixed(1)}% |`,
  );
}

out.push('', '</details>', '');
process.stdout.write(out.join('\n'));
