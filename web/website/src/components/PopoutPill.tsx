/**
 * PopoutPill — "Open in new window ↗" launcher shared by the example demos.
 *
 * Opens the target in a minimal popup window (not a tab) so the app sits
 * beside the docs. Modern browsers force a slim origin bar on popups, so
 * the window is minimal-chrome but never fully chromeless.
 */

import styles from "./PopoutPill.module.css";

/** Open a demo app in a centered popup window sized to the screen. The
 *  shared window name reuses one popup across demos instead of piling up
 *  windows as the reader hops between examples. */
export function openAppWindow(url: string): void {
  const width = Math.round(Math.min(1280, window.screen.availWidth * 0.62));
  const height = Math.round(Math.min(1000, window.screen.availHeight * 0.88));
  const left = Math.max(0, Math.round((window.screen.availWidth - width) / 2));
  const top = Math.max(0, Math.round((window.screen.availHeight - height) / 2));
  window.open(
    url,
    "fhir4ds-demo-app",
    `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
  );
}

export default function PopoutPill({
  url,
  onBeforeOpen,
}: {
  url: string;
  /** Runs synchronously before the window opens (e.g. the scheduling demo
   *  writes its live connection list for the popup to inherit). */
  onBeforeOpen?: () => void;
}) {
  return (
    <div className={styles.row}>
      <button
        className={styles.btn}
        onClick={() => {
          onBeforeOpen?.();
          openAppWindow(url);
        }}
      >
        Open in new window ↗
      </button>
    </div>
  );
}
