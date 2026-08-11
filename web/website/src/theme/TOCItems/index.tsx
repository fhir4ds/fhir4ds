import React from "react";
import TOCItems from "@theme-original/TOCItems";

// Per-page short-label map for the right-side table of contents. Keys are
// the auto-generated anchor IDs of the markdown H2s on the bulk-publish
// page; values are the short labels shown in the ToC. The visible page
// headings stay long ("Connect to a Bulk Publish endpoint") — only the ToC
// link text is shortened so the ToC reads as a scannable step list:
// Connect / Explore / Translate / Query / Production.
//
// IDs not in this map pass through unchanged, so other docs pages are
// unaffected.
const SHORT_LABELS: Record<string, string> = {
  "connect-to-a-bulk-publish-endpoint": "Connect",
  "browse-the-raw-published-fhir-resources": "Explore",
  "from-viewdefinition-to-a-flat-queryable-table": "Translate",
  "filter-the-materialized-table-with-plain-sql": "Query",
  "the-same-engine-as-a-patient-facing-app": "Production",
};

interface TypedTOCItem {
  id: string;
  value: string;
  level: number;
  children?: TypedTOCItem[];
}

function shorten(item: TypedTOCItem): TypedTOCItem {
  const short = SHORT_LABELS[item.id];
  return short ? { ...item, value: short } : item;
}

export default function TOCItemsWrapper(
  props: React.ComponentProps<typeof TOCItems>,
): React.JSX.Element {
  const toc = props.toc?.map(shorten);
  return <TOCItems {...props} toc={toc} />;
}
