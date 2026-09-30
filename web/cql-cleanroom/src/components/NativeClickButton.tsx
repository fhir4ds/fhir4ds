import { useEffect, useRef, type ReactNode } from "react";

/**
 * Native-click menu action button.
 *
 * React 18's delegated event system does not dispatch synthetic click
 * events to menu items that mount INSIDE a nested flyout when the whole
 * app renders into a Shadow DOM web component (the <cql-cleanroom>
 * website embed): the native click reaches the element (verified with
 * element.onclick instrumentation) but React's root-delegated listener
 * never invokes the JSX onClick handler. Top-level menu buttons
 * (mounted at initial render) work; hover-mounted flyout items do not.
 *
 * This button binds a REAL element-level listener via ref
 * (bubbling phase, non-captured — the parent menu's close-on-click
 * logic still observes the same event), so the action fires in both
 * the standalone app and the shadow-DOM embed.
 */
export function NativeClickButton({
  onClick,
  testId,
  children,
  title,
  className = "dropdown-item",
}: {
  onClick: () => void;
  testId?: string;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  const ref = useRef<HTMLButtonElement | null>(null);
  const handler = useRef(onClick);
  handler.current = onClick;
  useEffect(() => {
    const btn = ref.current;
    if (!btn) return;
    const run = () => handler.current();
    btn.addEventListener("click", run);
    return () => btn.removeEventListener("click", run);
  }, []);
  return (
    <button
      ref={ref}
      className={className}
      data-testid={testId}
      title={title}
      type="button"
    >
      {children}
    </button>
  );
}
