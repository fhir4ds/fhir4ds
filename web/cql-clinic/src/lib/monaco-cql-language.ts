/**
 * CQL language support for Monaco Editor (ported from cql-code-clinic).
 * Based on CQL Language Specification v1.5.4.
 *
 * - Monarch tokenizer (keywords, quantities, DateTime literals, strings)
 * - cql-light / cql-dark themes
 * - Completion provider (keywords, types, built-ins, snippets)
 * - Hover documentation provider
 */

import type * as MonacoEditor from "monaco-editor";

type Monaco = typeof MonacoEditor;

// CQL Language Configuration
export const CQL_LANGUAGE_CONFIG = {
  comments: {
    lineComment: "//",
    blockComment: ["/*", "*/"],
  },
  brackets: [
    ["{", "}"],
    ["[", "]"],
    ["(", ")"],
  ],
  autoClosingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "(", close: ")" },
    { open: '"', close: '"', notIn: ["string"] },
    { open: "'", close: "'", notIn: ["string", "comment"] },
  ],
  surroundingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "(", close: ")" },
    { open: '"', close: '"' },
    { open: "'", close: "'" },
  ],
};

// CQL Keywords and Operators
const CQL_KEYWORDS = [
  // Declaration Keywords
  "library", "using", "include", "public", "private",
  "parameter", "default", "define", "context",
  "codesystem", "valueset", "code", "concept",

  // Control Flow
  "if", "then", "else", "case", "when", "end",

  // Logical Operators
  "and", "or", "xor", "not", "implies",

  // Comparison Operators
  "is", "as", "between", "in", "contains", "properly",
  "includes", "included", "during", "overlaps", "starts", "ends",
  "meets", "same", "union", "intersect", "except",

  // Quantifiers
  "exists", "all", "any", "some",

  // Temporal Keywords
  "year", "years", "month", "months", "week", "weeks",
  "day", "days", "hour", "hours", "minute", "minutes",
  "second", "seconds", "millisecond", "milliseconds",
  "before", "after", "on", "at",

  // Type Keywords
  "cast", "convert", "flatten", "expand", "collapse",

  // Aggregate Keywords
  "distinct", "return", "sort", "by", "asc", "ascending",
  "desc", "descending", "where", "with", "without",
  "such", "that", "from",

  // Special Keywords
  "null", "true", "false",
];

const CQL_CONTEXT_TYPES = [
  "Unfiltered", "Patient", "Practitioner", "RelatedPerson",
  "Population", "Encounter",
];

const CQL_DATA_TYPES = [
  // Primitive Types
  "Boolean", "Integer", "Long", "Decimal", "String",
  "DateTime", "Date", "Time",

  // Clinical Types
  "Quantity", "Ratio", "Code", "Concept", "CodeSystem", "ValueSet",

  // Structured Types
  "Tuple", "List", "Interval", "Choice",

  // Clinical Data Types (FHIR)
  "Patient", "Encounter", "Observation", "Condition", "Procedure",
  "MedicationRequest", "MedicationStatement", "DiagnosticReport",
  "AllergyIntolerance", "Immunization", "CarePlan", "Goal",
];

const CQL_BUILT_IN_FUNCTIONS = [
  // Math Functions
  "Abs", "Add", "Ceiling", "Divide", "Exp", "Floor", "Log", "Max", "Min",
  "Modulo", "Multiply", "Negate", "Power", "Predecessor", "Round", "Subtract",
  "Successor", "Truncate",

  // String Functions
  "Combine", "Concatenate", "EndsWith", "Equal", "Equivalent", "Indexer",
  "LastPositionOf", "Length", "Lower", "Matches", "PositionOf", "ReplaceMatches",
  "Split", "StartsWith", "Substring", "Upper",

  // Date/Time Functions
  "After", "Before", "DateTime", "DateFrom", "DateTimeComponentFrom",
  "DifferenceBetween", "DurationBetween", "Now", "SameAs", "SameOrAfter",
  "SameOrBefore", "TimeFrom", "TimezoneFrom", "TimezoneOffsetFrom", "Today",
  "ToDateTime", "ToTime",

  // List Functions
  "AllTrue", "AnyTrue", "Avg", "Count", "Distinct", "Exists", "Filter",
  "First", "Flatten", "GeometricMean", "IndexOf", "Last", "PopulationStdDev",
  "PopulationVariance", "Product", "Select", "SingletonFrom", "Skip",
  "StdDev", "Sum", "Take", "Union", "Variance",

  // Clinical Functions
  "AgeInYears", "AgeInMonths", "AgeInDays", "CalculateAge", "CalculateAgeAt",
];

// Comprehensive Monarch Tokenizer for CQL
export const CQL_MONARCH_LANGUAGE = {
  defaultToken: "invalid",
  tokenPostfix: ".cql",

  keywords: CQL_KEYWORDS,
  contextTypes: CQL_CONTEXT_TYPES,
  dataTypes: CQL_DATA_TYPES,
  builtInFunctions: CQL_BUILT_IN_FUNCTIONS,

  operators: [
    "=", "!=", "<>", "<", "<=", ">", ">=", "~", "!~",
    "+", "-", "*", "/", "^", "mod", "div",
    "and", "or", "xor", "implies", "not",
    "is", "as", "between", "in", "contains",
  ],

  symbols: /[=><!~?:&|+\-*\/\^%]+/,
  escapes: /\\(?:[abfnrtv\\"']|x[0-9A-Fa-f]{1,4}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})/,

  tokenizer: {
    root: [
      // CQL identifiers and keywords
      [
        /[a-zA-Z_$][\w$]*/,
        {
          cases: {
            "@keywords": "keyword",
            "@contextTypes": "type.context",
            "@dataTypes": "type.primitive",
            "@builtInFunctions": "predefined.function",
            "@default": "identifier",
          },
        },
      ],

      // Library and include statements
      [/(library|using|include)\s+([a-zA-Z_$][\w$.]*)/, ["keyword", "string.library"]],

      // Quoted identifiers
      [/"([^"\\]|\\.)*"/, "identifier.quoted"],

      // Numbers
      [/\d*\.\d+([eE][\-+]?\d+)?[fFdD]?/, "number.float"],
      [/\d+([eE][\-+]?\d+)?[fFdD]?/, "number.integer"],

      // Quantities with units
      [/\d+(\.\d+)?\s*'[^']*'/, "number.quantity"],

      // Date/Time literals
      [
        /@\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d{3})?([+-]\d{2}:\d{2}|Z)?)?/,
        "string.datetime",
      ],

      // Strings
      [/'([^'\\]|\\.)*$/, "string.invalid"],
      [/'/, "string", "@string_single"],
      [/"([^"\\]|\\.)*$/, "string.invalid"],
      [/"/, "string", "@string_double"],

      // Comments
      [/\/\*/, "comment", "@comment"],
      [/\/\/.*$/, "comment"],

      // Operators
      [
        /@symbols/,
        {
          cases: {
            "@operators": "operator",
            "@default": "",
          },
        },
      ],

      // Delimiters
      [/[{}()\[\]]/, "@brackets"],
      [/[<>](?!@symbols)/, "@brackets"],
      [/[,.]/, "delimiter"],
      [/[;:]/, "delimiter.semicolon"],

      // Whitespace
      { include: "@whitespace" },
    ],

    string_single: [
      [/[^\\']+/, "string"],
      [/@escapes/, "string.escape"],
      [/\\./, "string.escape.invalid"],
      [/'/, "string", "@pop"],
    ],

    string_double: [
      [/[^\\"]+/, "string"],
      [/@escapes/, "string.escape"],
      [/\\./, "string.escape.invalid"],
      [/"/, "string", "@pop"],
    ],

    comment: [
      [/[^\/*]+/, "comment"],
      [/\/\*/, "comment", "@push"],
      [/\*\//, "comment", "@pop"],
      [/[\/*]/, "comment"],
    ],

    whitespace: [
      [/[ \t\r\n]+/, "white"],
      [/\/\*/, "comment", "@comment"],
      [/\/\/.*$/, "comment"],
    ],
  },
};

// CQL Language Theme
export const CQL_THEME = {
  base: "vs",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "0000ff", fontStyle: "bold" },
    { token: "type.context", foreground: "267f99", fontStyle: "bold" },
    { token: "type.primitive", foreground: "267f99" },
    { token: "predefined.function", foreground: "795e26" },
    { token: "identifier.quoted", foreground: "001080" },
    { token: "number.float", foreground: "098658" },
    { token: "number.integer", foreground: "098658" },
    { token: "number.quantity", foreground: "098658", fontStyle: "italic" },
    { token: "string.datetime", foreground: "a31515", fontStyle: "italic" },
    { token: "string.library", foreground: "a31515", fontStyle: "underline" },
    { token: "comment", foreground: "008000", fontStyle: "italic" },
    { token: "operator", foreground: "000000" },
  ],
  colors: {},
};

// CQL Dark Theme
export const CQL_DARK_THEME = {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "569cd6", fontStyle: "bold" },
    { token: "type.context", foreground: "4ec9b0", fontStyle: "bold" },
    { token: "type.primitive", foreground: "4ec9b0" },
    { token: "predefined.function", foreground: "dcdcaa" },
    { token: "identifier.quoted", foreground: "9cdcfe" },
    { token: "number.float", foreground: "b5cea8" },
    { token: "number.integer", foreground: "b5cea8" },
    { token: "number.quantity", foreground: "b5cea8", fontStyle: "italic" },
    { token: "string.datetime", foreground: "ce9178", fontStyle: "italic" },
    { token: "string.library", foreground: "ce9178", fontStyle: "underline" },
    { token: "comment", foreground: "6a9955", fontStyle: "italic" },
    { token: "operator", foreground: "d4d4d4" },
  ],
  colors: {},
};

// CQL Completion Item Provider
export const createCQLCompletionProvider = (monaco: Monaco) => ({
  provideCompletionItems: (model: any, position: any) => {
    const word = model.getWordUntilPosition(position);
    const range = {
      startLineNumber: position.lineNumber,
      endLineNumber: position.lineNumber,
      startColumn: word.startColumn,
      endColumn: word.endColumn,
    };

    const suggestions = [
      ...CQL_KEYWORDS.map((keyword) => ({
        label: keyword,
        kind: monaco.languages.CompletionItemKind.Keyword,
        insertText: keyword,
        range: range,
        detail: "CQL Keyword",
      })),
      ...CQL_DATA_TYPES.map((type) => ({
        label: type,
        kind: monaco.languages.CompletionItemKind.Class,
        insertText: type,
        range: range,
        detail: "CQL Data Type",
      })),
      ...CQL_BUILT_IN_FUNCTIONS.map((func) => ({
        label: func,
        kind: monaco.languages.CompletionItemKind.Function,
        insertText: `${func}($1)`,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range: range,
        detail: "CQL Built-in Function",
        documentation: `Built-in CQL function: ${func}`,
      })),
      {
        label: "define-expression",
        kind: monaco.languages.CompletionItemKind.Snippet,
        insertText: 'define "${1:ExpressionName}":\n\t${2:expression}',
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range: range,
        detail: "Define Expression",
        documentation: "Define a new CQL expression",
      },
      {
        label: "library-header",
        kind: monaco.languages.CompletionItemKind.Snippet,
        insertText:
          "library ${1:LibraryName} version '${2:1.0.0}'\n\nusing FHIR version '${3:4.0.1}'\n\n${4}",
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range: range,
        detail: "Library Header",
        documentation: "Standard CQL library header",
      },
    ];

    return { suggestions };
  },
});

// CQL Hover Provider
export const createCQLHoverProvider = (monaco: Monaco) => ({
  provideHover: (model: any, position: any) => {
    const word = model.getWordAtPosition(position);
    if (!word) return;

    const { word: hoveredWord } = word;

    const documentation = getCQLDocumentation(hoveredWord);
    if (documentation) {
      return {
        range: new monaco.Range(
          position.lineNumber,
          word.startColumn,
          position.lineNumber,
          word.endColumn,
        ),
        contents: [{ value: `**${hoveredWord}**` }, { value: documentation }],
      };
    }

    return null;
  },
});

// CQL Documentation lookup
function getCQLDocumentation(word: string): string | undefined {
  const docs: Record<string, string> = {
    // Keywords
    define: "Defines a named expression that can be referenced elsewhere in the library.",
    library: "Declares the name and version of a CQL library.",
    using: "Specifies a data model to be used by the library.",
    include: "Includes another library and makes its public expressions available.",
    parameter: "Declares a parameter that can be provided when the library is evaluated.",
    context: "Specifies the context for expression evaluation (Patient, Population, etc.).",

    // Functions
    Count: "Returns the number of elements in a list.",
    Sum: "Returns the sum of numeric elements in a list.",
    Avg: "Returns the average of numeric elements in a list.",
    Max: "Returns the maximum value from a list.",
    Min: "Returns the minimum value from a list.",
    AgeInYears: "Calculates the age in years based on birth date.",
    Now: "Returns the current date and time.",
    Today: "Returns the current date.",

    // Data Types
    Patient: "Context that evaluates expressions for individual patients.",
    Encounter: "Represents a healthcare encounter.",
    Observation: "Represents an observation or measurement.",
    Condition: "Represents a clinical condition or diagnosis.",
    DateTime: "Represents a point in time with date and time components.",
    Quantity: "Represents a quantity with a numeric value and unit.",
    Population: "Context that evaluates expressions across a population.",
    Unfiltered: "Context that provides access to all data without patient-level filtering.",
  };

  return docs[word];
}

// Register CQL language with Monaco
export function registerCQLLanguage(monaco: Monaco): void {
  monaco.languages.register({ id: "cql" });
  monaco.languages.setLanguageConfiguration("cql", CQL_LANGUAGE_CONFIG as any);
  monaco.languages.setMonarchTokensProvider("cql", CQL_MONARCH_LANGUAGE as any);
  monaco.editor.defineTheme("cql-light", CQL_THEME as any);
  monaco.editor.defineTheme("cql-dark", CQL_DARK_THEME as any);
  monaco.languages.registerCompletionItemProvider("cql", createCQLCompletionProvider(monaco) as any);
  monaco.languages.registerHoverProvider("cql", createCQLHoverProvider(monaco) as any);
}
