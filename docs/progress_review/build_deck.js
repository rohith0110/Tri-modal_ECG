// Builds TriECG_Progress_Review.pptx. Numbers: R2 trimodal-results, pulled 2026-11-06.
// Run: NODE_PATH=<dir with pptxgenjs> node build_deck.js <out.pptx> <apply_theme.js path>
const pptxgen = require("pptxgenjs");
const path = require("path");
const OUT = process.argv[2] || path.join(__dirname, "TriECG_Progress_Review.pptx");
const APPLY = process.argv[3];

const THEME = {
  name: "TriECG",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1F2A", lt1: "FFFFFF", dk2: "14213D", lt2: "EEF2F7",
    accent1: "E63946", accent2: "2A9D8F", accent3: "457B9D",
    accent4: "F4A261", accent5: "8D99AE", accent6: "A8DADC",
    hlink: "457B9D", folHlink: "8D99AE",
  },
};
const H = THEME.colors; // hex, for hex-only options
const SIG = H.accent1, IMG = H.accent2, TXT = H.accent3;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "TriECG-Truth: Progress Review";
pres.author = "TriECG-Truth team";
const C = pres.SchemeColor;

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "DARK",
  background: { color: H.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.55, w: 8.8, h: 1.0,
      fontSize: 40, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.6, w: 8.8, h: 0.6,
      fontSize: 18, color: H.accent6, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.5, 0.5, 0.5, 0.5],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9.0, h: 0.7,
      fontSize: 26, bold: true, color: C.text2, fontFace: THEME.headFontFace, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "TriECG-Truth  ·  Progress review", options: { x: 0.5, y: 5.22, w: 5, h: 0.25, fontSize: 9, color: H.accent5, margin: 0 } } },
  ],
  slideNumber: { x: 9.1, y: 5.22, w: 0.4, h: 0.25, fontSize: 9, color: H.accent5, align: "right" },
});

// ---------- helpers ----------
function heartbeat(slide, x, y, w, h, color, width) {
  // one ECG-like beat repeated: flat, P bump, QRS spike, T bump
  const beat = [[0, .5], [.10, .5], [.14, .44], [.18, .5], [.24, .5], [.26, .58], [.30, .05], [.34, .85], [.37, .5], [.48, .5], [.55, .38], [.62, .5], [1, .5]];
  const n = 3, pts = [];
  for (let b = 0; b < n; b++) beat.forEach(([px, py], i) => {
    if (b > 0 && i === 0) return;
    pts.push({ x: ((b + px) / n) * w, y: py * h });
  });
  slide.addShape(pres.shapes.CUSTOM_GEOMETRY, { x, y, w, h, points: pts, line: { color, width }, objectName: "heartbeat" });
}
function badge(slide, x, y, d, letter, fill, name) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: name + " badge" });
  slide.addText(letter, { x, y, w: d, h: d, align: "center", valign: "middle", fontSize: d * 26, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: name + " letter" });
}
function card(slide, x, y, w, h, name, fill) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill || H.lt2 }, line: { color: fill || H.lt2 }, objectName: name });
}
function takeaway(slide, text, y) {
  slide.addText(text, { x: 0.5, y: y || 4.62, w: 9.0, h: 0.45, fontSize: 14, italic: true, color: C.text2, margin: 0, isTextBox: true, objectName: "takeaway" });
}
const axisFont = { catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent5, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, dataLabelFontSize: 9, legendFontSize: 11,
  valGridLine: { color: "DDE3EA", size: 0.5 }, catGridLine: { style: "none" } };

// ================= 1. Title =================
pres.addSection({ title: "Intro" });
let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Intro" });
heartbeat(s, 0.6, 0.55, 4.2, 0.8, H.accent1, 2.5);
s.addText("TriECG-Truth", { placeholder: "title" });
s.addText("A tri-modal ECG benchmark: signal, image and report", { placeholder: "body" });
s.addText([
  { text: "B.Tech 4-1 Project  ·  Progress Review", options: { bold: true, breakLine: true } },
  { text: "Anshika Mishra  ·  Banoth Rohith Rathod  ·  Aditya Goyal", options: { breakLine: true } },
  { text: "Guide: Dr. Neeraj Choudhary  ·  Department of CSE, Mahindra University" },
], { x: 0.6, y: 3.7, w: 8.8, h: 1.0, fontSize: 13, color: C.background1, margin: 0, paraSpaceAfter: 4, isTextBox: true, objectName: "team" });
s.addNotes("Introduce the team and the one-line idea: one ECG, three ways of looking at it, and a benchmark that tests all three together.");

// ================= 2. Problem =================
pres.addSection({ title: "Problem" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Problem" });
s.addText("One ECG, three views, but models use only one", { placeholder: "title" });
const views = [
  ["S", SIG, "Signal", "The raw 10-second voltage trace from 12 leads"],
  ["I", IMG, "Image", "The printed or scanned chart a doctor reads"],
  ["T", TXT, "Report", "The written interpretation that comes with it"],
];
views.forEach(([L, col, head, body], i) => {
  const x = 0.5 + i * 3.05;
  card(s, x, 1.2, 2.85, 1.55, head + " card");
  badge(s, x + 0.2, 1.38, 0.5, L, col, head);
  s.addText(head, { x: x + 0.85, y: 1.38, w: 1.9, h: 0.5, fontSize: 17, bold: true, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  s.addText(body, { x: x + 0.2, y: 1.98, w: 2.5, h: 0.7, fontSize: 13, color: C.text1, valign: "top", margin: 0, isTextBox: true });
});
s.addText([
  { text: "The gap: ", options: { bold: true, color: H.accent1 } },
  { text: "most ECG AI uses one view. No shared benchmark tests all three on the same patients, or checks whether they agree.", options: { breakLine: true } },
  { text: "Our goal: ", options: { bold: true, color: H.accent2 } },
  { text: "build that benchmark: a clean dataset, 12 tasks, trained baseline models and a fair way to compare them." },
], { x: 0.5, y: 3.1, w: 9.0, h: 1.5, fontSize: 15, color: C.text1, margin: 0, paraSpaceAfter: 10, valign: "top", isTextBox: true, objectName: "gap and goal" });
s.addNotes("Signal, image and report describe the same heartbeat. Real hospitals have all three, but research models usually take just one. Nobody has a common test that covers all three together, so we built one.");

// ================= 3. Dataset =================
pres.addSection({ title: "Work completed" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Work completed" });
s.addText("Phase 1 (done): we built and audited the dataset", { placeholder: "title" });
const stats = [["800,035", "ECGs"], ["161,352", "patients"], ["93.6 %", "pass quality checks"], ["3", "views per ECG"]];
stats.forEach(([n, l], i) => {
  const x = 0.5 + i * 2.3;
  card(s, x, 1.2, 2.1, 1.5, l + " stat");
  s.addText(n, { x, y: 1.3, w: 2.1, h: 0.8, fontSize: 32, bold: true, color: i % 2 ? C.accent2 : C.accent1, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText(l, { x, y: 2.1, w: 2.1, h: 0.45, fontSize: 13, color: C.text1, align: "center", valign: "top", margin: 0, isTextBox: true });
});
s.addText([
  { text: "Source: MIMIC-IV-ECG, linked to the patients' hospital records (MIMIC-IV)", options: { bullet: true, breakLine: true } },
  { text: "Split by patient: 70 % train / 10 % validation / 20 % test, no patient in two splits", options: { bullet: true, breakLine: true } },
  { text: "Every image and report generated or matched for each signal, with quality tiers", options: { bullet: true, breakLine: true } },
  { text: "All audits pass: leakage, duplicates, splits, linkage, missing data", options: { bullet: true } },
], { x: 0.5, y: 3.0, w: 9.0, h: 1.9, fontSize: 14, color: C.text1, margin: 0, paraSpaceAfter: 6, valign: "top", isTextBox: true, objectName: "dataset facts" });
s.addNotes("749,112 of the 800,035 ECGs pass quality checks. The patient-level split matters: if the same patient appears in train and test, scores look better than they really are.");

// ================= 4. Tasks =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Work completed" });
s.addText("12 benchmark tasks in two tracks", { placeholder: "title" });
const trackA = [["A1", "Diagnose 5 heart conditions"], ["A2", "Estimate heart rate and intervals"], ["A3", "Predict abnormal lab results"],
  ["A4", "Locate each heartbeat and QRS"], ["A5", "Check signal, image and report match"], ["A6", "Predict death and readmission risk"]];
const trackB = [["B1", "Estimate heart rate and intervals"], ["B2", "Same, on noisy signals"], ["B3", "Find when events occur in 10 s"],
  ["B4", "Check signal, image and report match"], ["B5", "Spot reports that were altered"], ["B6", "Matching, graded by difficulty"]];
[[trackA, "Track A: linked to hospital records", H.accent1, 0.5], [trackB, "Track B: the ECG on its own", H.accent2, 5.1]].forEach(([rows, head, col, x]) => {
  s.addText(head, { x, y: 1.1, w: 4.4, h: 0.4, fontSize: 15, bold: true, color: col, margin: 0, isTextBox: true });
  rows.forEach(([id, t], i) => {
    const y = 1.6 + i * 0.52;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 0.6, h: 0.4, rectRadius: 0.06, fill: { color: col }, line: { color: col }, objectName: id + " tag" });
    s.addText(id, { x, y, w: 0.6, h: 0.4, fontSize: 13, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addText(t, { x: x + 0.75, y, w: 3.65, h: 0.4, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  });
});
s.addNotes("Track A needs the hospital record (diagnoses, labs, outcomes). Track B only needs the ECG itself, so it can be used anywhere. Together they test diagnosis, measurement, timing, robustness and whether the three views agree.");

// ================= 5. Method =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Work completed" });
s.addText("Every model is trained and tested the same way", { placeholder: "title" });
const steps = [
  ["1", "Models", "Signal: ResNet-18\nImage: ResNet-50\nText: TF-IDF, BioClinicalBERT\nFusion: all three"],
  ["2", "3 seeds", "Each setup trained three times with different random starts"],
  ["3", "Test set", "Scored only on the held-out 20 % test patients"],
  ["4", "95 % intervals", "Bootstrap confidence intervals on every score"],
];
steps.forEach(([n, head, body], i) => {
  const x = 0.5 + i * 2.3;
  card(s, x, 1.2, 2.1, 2.3, head + " step");
  badge(s, x + 0.15, 1.35, 0.45, n, H.dk2, "step " + n);
  s.addText(head, { x: x + 0.7, y: 1.35, w: 1.35, h: 0.45, fontSize: 15, bold: true, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  s.addText(body, { x: x + 0.15, y: 1.95, w: 1.85, h: 1.7, fontSize: 12.5, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  if (i < 3) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.12, y: 2.36, w: 0.16, h: 0.22, fill: { color: H.accent5 }, line: { color: H.accent5 }, objectName: "arrow" });
});
s.addText([
  { text: "104 model setups × 3 seeds = 312 training runs", options: { bold: true, breakLine: true } },
  { text: "Run on the university DGX (NVIDIA A100 GPUs), across three accounts in parallel" },
], { x: 0.5, y: 4.0, w: 9.0, h: 0.8, fontSize: 14, color: C.text2, margin: 0, paraSpaceAfter: 4, isTextBox: true, objectName: "run count" });
s.addNotes("Three seeds show how much a score moves by chance. Confidence intervals tell us when one model is really better than another and when the gap is just noise.");

// ================= 6. Progress =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Work completed" });
s.addText("159 of 312 training runs done", { placeholder: "title" });
const groups = [
  ["Text models", 36, 36], ["12-lead images", 15, 15], ["Lead-II signals", 78, 78], ["Lead-II images", 9, 15],
  ["Scan-like image sweeps", 18, 30], ["Fusion (all three views)", 3, 66], ["12-lead signals", 0, 30],
  ["Robustness re-training", 0, 30], ["Final evaluation", 0, 12],
];
const labels = groups.map(g => g[0]).reverse();
s.addChart(pres.charts.BAR, [
  { name: "Done", labels, values: groups.map(g => g[1]).reverse() },
  { name: "To do", labels, values: groups.map(g => g[2] - g[1]).reverse() },
], { x: 0.4, y: 1.05, w: 6.3, h: 3.95, barDir: "bar", barGrouping: "stacked", chartColors: [H.accent2, "D5DCE5"],
  showLegend: true, legendPos: "t", showValue: true, dataLabelPosition: "ctr", dataLabelFormatCode: "0;;;", dataLabelColor: H.dk1, barGapWidthPct: 45,
  valAxisMaxVal: 80, valAxisMajorUnit: 20, ...axisFont, objectName: "runs by group" });
const side = [["159", "runs finished"], ["~1,300", "GPU-hours so far"], ["6 / 12", "tasks with test-set scores"]];
side.forEach(([n, l], i) => {
  const y = 1.15 + i * 1.25;
  card(s, 7.0, y, 2.5, 1.05, l);
  s.addText(n, { x: 7.0, y: y + 0.08, w: 2.5, h: 0.55, fontSize: 24, bold: true, color: C.accent1, align: "center", margin: 0, isTextBox: true });
  s.addText(l, { x: 7.0, y: y + 0.62, w: 2.5, h: 0.35, fontSize: 12, color: C.text1, align: "center", margin: 0, isTextBox: true });
});
s.addNotes("Text, 12-lead image and Lead-II signal models are complete. The big remaining block is fusion: models that see all three views at once. Those are the heart of the benchmark and also the slowest to train.");

// ================= 7. Engineering =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Work completed" });
s.addText("Problems we hit and how we solved them", { placeholder: "title" });
const probs = [
  ["~400 GB of data, 46 GB of space per account", "Split the training data into pieces; training cycles through them so only two sit on disk at once"],
  ["Signals too big to copy", "Stored at half size (16-bit). Proved this moves scores less than changing the random seed does"],
  ["Jobs stop at the 7-day limit", "Every run saves checkpoints and resumes on its own in a chain of follow-up jobs"],
  ["Bugs that could corrupt results", "Self-checks before each run caught a wrong model, missing test files and a data-piece mismatch for fusion"],
];
probs.forEach(([p, f], i) => {
  const col = i % 2, row = Math.floor(i / 2);
  const x = 0.5 + col * 4.6, y = 1.25 + row * 1.7;
  card(s, x, y, 4.4, 1.45, "problem " + (i + 1));
  s.addText(p, { x: x + 0.2, y: y + 0.15, w: 4.0, h: 0.5, fontSize: 14, bold: true, color: C.accent1, valign: "top", margin: 0, isTextBox: true });
  s.addText(f, { x: x + 0.2, y: y + 0.6, w: 4.0, h: 0.9, fontSize: 13, color: C.text1, valign: "top", margin: 0, isTextBox: true });
});
s.addNotes("These are the reasons the runs take time. Each fix is tested before it touches real results; the data-piece mismatch, for example, was caught and fixed before any fusion results were produced.");

// ================= 8. A1 =================
pres.addSection({ title: "Results" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("A1 diagnosis: ECG models beat the written report", { placeholder: "title" });
const a1lab = ["Atrial fib.", "Heart failure", "Conduction", "Heart attack (AMI)", "Ventricular arrhythmia"];
s.addChart(pres.charts.BAR, [
  { name: "Signal (Lead II)", labels: a1lab, values: [0.862, 0.810, 0.815, 0.753, 0.739] },
  { name: "Image (12-lead)", labels: a1lab, values: [0.841, 0.814, 0.802, 0.777, 0.742] },
  { name: "Report text (BioClinicalBERT)", labels: a1lab, values: [0.829, 0.777, 0.799, 0.737, 0.711] },
], { x: 0.4, y: 1.0, w: 9.2, h: 3.5, barDir: "col", barGrouping: "clustered", chartColors: [SIG, IMG, TXT],
  showLegend: true, legendPos: "t", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelColor: H.dk1,
  valAxisMinVal: 0.5, valAxisMaxVal: 0.9, valAxisMajorUnit: 0.1, valAxisLabelFormatCode: "0.0", barGapWidthPct: 60,
  showValAxisTitle: true, valAxisTitle: "AUROC (0.5 = guessing, 1 = perfect)", valAxisTitleColor: H.accent5, valAxisTitleFontSize: 10, valAxisTitleFontFace: "+mn-lt",
  ...axisFont, objectName: "A1 AUROC" });
takeaway(s, "ECG signal or image wins on all five conditions. Atrial fibrillation is easiest; ventricular arrhythmia hardest. Test set: 75,187 ECGs, mean of 3 seeds.");
s.addNotes("AUROC: the chance the model ranks a sick patient above a healthy one. Signal and image are close to each other and both beat the report text, which tells us the raw ECG holds information the written report leaves out.");

// ================= 9. A6 =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("A6 risk: the ECG predicts death, not readmission", { placeholder: "title" });
const a6lab = ["Death in 30 days", "Death in 90 days", "Readmitted in 30 days", "Readmitted in 90 days"];
s.addChart(pres.charts.BAR, [
  { name: "Image (12-lead)", labels: a6lab, values: [0.770, 0.742, 0.539, 0.543] },
  { name: "Report text (BioClinicalBERT)", labels: a6lab, values: [0.715, 0.690, 0.529, 0.534] },
], { x: 0.4, y: 1.0, w: 6.0, h: 3.5, barDir: "col", barGrouping: "clustered", chartColors: [IMG, TXT],
  showLegend: true, legendPos: "t", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelColor: H.dk1,
  valAxisMinVal: 0.5, valAxisMaxVal: 0.85, valAxisMajorUnit: 0.1, valAxisLabelFormatCode: "0.0", barGapWidthPct: 60,
  ...axisFont, objectName: "A6 AUROC" });
card(s, 6.7, 1.15, 2.8, 1.5, "mortality note");
s.addText([{ text: "0.77", options: { bold: true, fontSize: 28, color: H.accent2, breakLine: true } },
  { text: "AUROC for 30-day death from the ECG image alone", options: { fontSize: 12 } }],
  { x: 6.85, y: 1.2, w: 2.5, h: 1.4, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
card(s, 6.7, 2.85, 2.8, 1.5, "readmission note");
s.addText([{ text: "~0.54", options: { bold: true, fontSize: 28, color: H.accent5, breakLine: true } },
  { text: "Readmission is barely above guessing for every model", options: { fontSize: 12 } }],
  { x: 6.85, y: 2.9, w: 2.5, h: 1.4, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
takeaway(s, "Readmission depends on things an ECG cannot see (discharge, follow-up care). Test set: 84,348 ECGs, AUROC, mean of 3 seeds.");
s.addNotes("The ECG carries a real death-risk signal. Readmission is driven by social and care factors, so a near-chance score is an honest finding, not a bug.");

// ================= 10. More results =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Three more test-set findings", { placeholder: "title" });
const more = [
  ["0.98", "B5: altered reports", "Text models spot reports where a number (heart rate, QRS, PR, axis) was changed", H.accent2],
  ["0.32", "A3: lab results", "Predicting abnormal labs from the report is hard: modest scores across 7 labs × 5 time windows", H.accent4],
  ["0.50", "A5 / B4: do views match?", "A report alone cannot tell if it belongs to an ECG: pure guessing. This is the floor fusion must beat", H.accent1],
];
more.forEach(([n, head, body, col], i) => {
  const x = 0.5 + i * 3.05;
  card(s, x, 1.15, 2.85, 3.0, head);
  s.addText(n, { x, y: 1.3, w: 2.85, h: 0.85, fontSize: 40, bold: true, color: col, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText(head, { x: x + 0.2, y: 2.2, w: 2.45, h: 0.45, fontSize: 15, bold: true, color: C.text1, align: "center", margin: 0, isTextBox: true });
  s.addText(body, { x: x + 0.2, y: 2.7, w: 2.45, h: 1.6, fontSize: 13, color: C.text1, valign: "top", margin: 0, isTextBox: true });
});
takeaway(s, "B5 and A5/B4: AUROC. A3: macro AUPRC. Both text models (TF-IDF and BioClinicalBERT) score within 0.01 of each other on all three.");
s.addNotes("B5: AUROC 0.983 (BERT), 0.982 (TF-IDF). A3: macro AUPRC 0.32 for both text models. A5/B4: text-only AUROC 0.50 by design. The image model scores ~0.75 on A5/B4, but scan-like images in the test set are always matches, so that score is probably a shortcut. We are checking it before reporting it.");

// ================= 11. Validation =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Early signs from signal-only tasks (validation set)", { placeholder: "title" });
const vlab = ["A2 measurements", "B1 measurements", "B2 under noise", "A4 heartbeat location", "B3 event timing"];
s.addChart(pres.charts.BAR, [
  { name: "Raw signal", labels: vlab, values: [0.873, 0.912, 0.903, 0.800, 0.798] },
  { name: "Preprocessed signal", labels: vlab, values: [0.848, 0.867, 0.866, 0.830, 0.819] },
], { x: 0.4, y: 1.0, w: 9.2, h: 3.5, barDir: "col", barGrouping: "clustered", chartColors: [SIG, "F2A2A8"],
  showLegend: true, legendPos: "t", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelColor: H.dk1,
  valAxisMinVal: 0.5, valAxisMaxVal: 1.0, valAxisMajorUnit: 0.1, valAxisLabelFormatCode: "0.0", barGapWidthPct: 60,
  ...axisFont, objectName: "signal validation" });
takeaway(s, "Signal models read heart rate and intervals well, and keep their score when trained with noise (B2). Validation scores; final test scores still to come.");
s.addNotes("Metrics: A2/B1/B2 macro AUPRC averaged over heart-rate, QRS and QTc bins; A4 R-peak F1 within 10 ms; B3 mean IoU. B2 shown is the noise-augmented training regime. Best epoch, mean of 3 seeds, Lead II.");

// ================= 12. Next steps =================
pres.addSection({ title: "Next steps" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Next steps" });
s.addText("Next steps", { placeholder: "title" });
const nexts = [
  ["Finish the remaining 153 runs", "Mostly fusion models, the main comparison of the benchmark"],
  ["Test-set scores for all 12 tasks", "Same 95 % intervals as the results shown today"],
  ["Classical baselines and statistical tests", "Is each model really better than a simple method, and than each other?"],
  ["Final audits", "Leakage, calibration and reproducibility checks before release"],
  ["Write the benchmark paper", "Dataset, tasks, results and the released code"],
];
nexts.forEach(([h, b], i) => {
  const y = 1.1 + i * 0.75;
  badge(s, 0.5, y + 0.05, 0.5, String(i + 1), i === 0 ? H.accent1 : H.dk2, "next " + (i + 1));
  s.addText(h, { x: 1.2, y, w: 8.3, h: 0.32, fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true });
  s.addText(b, { x: 1.2, y: y + 0.32, w: 8.3, h: 0.3, fontSize: 13, color: C.text2, margin: 0, isTextBox: true });
});
s.addNotes("Fusion runs are the priority: they answer the main question: does combining signal, image and report beat any single view?");

// ================= 13. Thanks =================
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Next steps" });
heartbeat(s, 0.6, 0.55, 4.2, 0.8, H.accent1, 2.5);
s.addText("Thank you", { placeholder: "title" });
s.addText("Questions?", { placeholder: "body" });
s.addText("Code: github.com/rohith0110/Tri-modal_ECG", { x: 0.6, y: 3.9, w: 8.8, h: 0.4, fontSize: 13, color: C.background1, margin: 0, isTextBox: true, objectName: "repo link",
  hyperlink: { url: "https://github.com/rohith0110/Tri-modal_ECG" } });

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (APPLY) { const { applyTheme } = require(APPLY); await applyTheme(OUT, THEME); }
  console.log("wrote", OUT);
})();
