/**
 * Write plain text to the system clipboard.
 * Falls back to `document.execCommand("copy")` when `navigator.clipboard` is unavailable
 * (e.g. non-secure context or older browsers).
 * @param {string} text
 */
export async function writeClipboardText(text) {
  const t = String(text ?? "");
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(t);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = t;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}
