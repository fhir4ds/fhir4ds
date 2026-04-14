/**
 * TypeScript declarations for the <fhir4ds-demo> custom element.
 * Allows JSX usage without "Property does not exist on type JSX.IntrinsicElements".
 */

declare namespace JSX {
  interface IntrinsicElements {
    "fhir4ds-demo": React.DetailedHTMLProps<
      React.HTMLAttributes<HTMLElement> & {
        scenario?: string;
        height?: string;
        "redirect-uri"?: string;
      },
      HTMLElement
    >;
  }
}
