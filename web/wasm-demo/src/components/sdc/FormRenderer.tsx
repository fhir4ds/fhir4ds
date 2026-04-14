/**
 * Recursive form renderer: maps Questionnaire.item[] to HTML form controls.
 *
 * Supports: group, display, string, text, integer, decimal, date, boolean, choice.
 * Nested groups render with visual hierarchy (fieldset + indent).
 */
import type {
  QuestionnaireItem,
  QuestionnaireResponse,
  QuestionnaireResponseAnswer,
  AnswerOption,
} from "../../lib/sdc-types";
import { getAnswer } from "../../lib/sdc-engine";
import { getCalculatedExpression } from "../../lib/sdc-types";

interface FormRendererProps {
  items: QuestionnaireItem[];
  response: QuestionnaireResponse;
  onAnswer: (linkId: string, answer: QuestionnaireResponseAnswer | null) => void;
  calcErrors: Record<string, string>;
  depth?: number;
}

export function FormRenderer({
  items,
  response,
  onAnswer,
  calcErrors,
  depth = 0,
}: FormRendererProps) {
  return (
    <div className={`sdc-form-items ${depth > 0 ? "sdc-form-nested" : ""}`}>
      {items.map((item) => (
        <FormItem
          key={item.linkId}
          item={item}
          response={response}
          onAnswer={onAnswer}
          calcErrors={calcErrors}
          depth={depth}
        />
      ))}
    </div>
  );
}

interface FormItemProps {
  item: QuestionnaireItem;
  response: QuestionnaireResponse;
  onAnswer: (linkId: string, answer: QuestionnaireResponseAnswer | null) => void;
  calcErrors: Record<string, string>;
  depth: number;
}

function FormItem({ item, response, onAnswer, calcErrors, depth }: FormItemProps) {
  const isCalculated = !!getCalculatedExpression(item);
  const calcError = calcErrors[item.linkId];
  const isReadOnly = item.readOnly || isCalculated;

  if (item.type === "display") {
    return (
      <div className="sdc-field sdc-field-display">
        <p className="sdc-display-text">{item.text}</p>
      </div>
    );
  }

  if (item.type === "group") {
    return (
      <fieldset className={`sdc-group sdc-group-depth-${Math.min(depth, 3)}`}>
        <legend className="sdc-group-legend">{item.text}</legend>
        {item.item && (
          <FormRenderer
            items={item.item}
            response={response}
            onAnswer={onAnswer}
            calcErrors={calcErrors}
            depth={depth + 1}
          />
        )}
      </fieldset>
    );
  }

  const answer = getAnswer(response, item.linkId);

  return (
    <div className={`sdc-field ${isCalculated ? "sdc-field-calculated" : ""}`}>
      <label className="sdc-label" htmlFor={`sdc-${item.linkId}`}>
        {item.text}
        {item.required && <span className="sdc-required">*</span>}
        {isCalculated && <span className="sdc-calc-badge">⚡ Calculated</span>}
      </label>

      {calcError && (
        <div className="sdc-field-error">
          <span className="sdc-field-error-icon">⚠</span>
          {calcError}
        </div>
      )}

      <FieldInput
        item={item}
        answer={answer}
        onAnswer={onAnswer}
        isReadOnly={isReadOnly}
      />
    </div>
  );
}

interface FieldInputProps {
  item: QuestionnaireItem;
  answer: QuestionnaireResponseAnswer | undefined;
  onAnswer: (linkId: string, answer: QuestionnaireResponseAnswer | null) => void;
  isReadOnly: boolean;
}

function FieldInput({ item, answer, onAnswer, isReadOnly }: FieldInputProps) {
  const { linkId, type } = item;
  const inputId = `sdc-${linkId}`;

  switch (type) {
    case "string":
    case "text":
      return (
        <input
          id={inputId}
          type="text"
          className="sdc-input"
          value={answer?.valueString ?? ""}
          readOnly={isReadOnly}
          onChange={(e) =>
            onAnswer(linkId, e.target.value ? { valueString: e.target.value } : null)
          }
        />
      );

    case "integer":
      return (
        <input
          id={inputId}
          type="number"
          className="sdc-input sdc-input-number"
          step="1"
          value={answer?.valueInteger ?? ""}
          readOnly={isReadOnly}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            onAnswer(linkId, isNaN(v) ? null : { valueInteger: v });
          }}
        />
      );

    case "decimal":
      return (
        <input
          id={inputId}
          type="number"
          className="sdc-input sdc-input-number"
          step="any"
          value={answer?.valueDecimal ?? ""}
          readOnly={isReadOnly}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            onAnswer(linkId, isNaN(v) ? null : { valueDecimal: v });
          }}
        />
      );

    case "date":
      return (
        <input
          id={inputId}
          type="date"
          className="sdc-input"
          value={answer?.valueDate ?? ""}
          readOnly={isReadOnly}
          onChange={(e) =>
            onAnswer(linkId, e.target.value ? { valueDate: e.target.value } : null)
          }
        />
      );

    case "boolean":
      return (
        <label className="sdc-checkbox-label">
          <input
            id={inputId}
            type="checkbox"
            className="sdc-checkbox"
            checked={answer?.valueBoolean ?? false}
            disabled={isReadOnly}
            onChange={(e) => onAnswer(linkId, { valueBoolean: e.target.checked })}
          />
          <span className="sdc-checkbox-text">Yes</span>
        </label>
      );

    case "choice":
      return <ChoiceInput item={item} answer={answer} onAnswer={onAnswer} isReadOnly={isReadOnly} />;

    default:
      return (
        <span className="sdc-unsupported">
          Unsupported type: {type}
        </span>
      );
  }
}

interface ChoiceInputProps {
  item: QuestionnaireItem;
  answer: QuestionnaireResponseAnswer | undefined;
  onAnswer: (linkId: string, answer: QuestionnaireResponseAnswer | null) => void;
  isReadOnly: boolean;
}

function ChoiceInput({ item, answer, onAnswer, isReadOnly }: ChoiceInputProps) {
  const options = item.answerOption ?? [];
  const selectedCode = answer?.valueCoding?.code ?? answer?.valueString ?? "";

  // Use radio buttons for ≤5 options, select for more
  if (options.length <= 5) {
    return (
      <div className="sdc-radio-group" role="radiogroup" aria-label={item.text}>
        {options.map((opt) => {
          const optVal = optionValue(opt);
          const optLabel = optionLabel(opt);
          return (
            <label key={optVal} className="sdc-radio-label">
              <input
                type="radio"
                className="sdc-radio"
                name={`sdc-${item.linkId}`}
                value={optVal}
                checked={selectedCode === optVal}
                disabled={isReadOnly}
                onChange={() =>
                  onAnswer(item.linkId, {
                    valueCoding: { code: optVal, display: optLabel },
                  })
                }
              />
              <span className="sdc-radio-text">{optLabel}</span>
            </label>
          );
        })}
      </div>
    );
  }

  return (
    <select
      id={`sdc-${item.linkId}`}
      className="sdc-select"
      value={selectedCode}
      disabled={isReadOnly}
      onChange={(e) => {
        const opt = options.find((o) => optionValue(o) === e.target.value);
        if (opt) {
          onAnswer(item.linkId, {
            valueCoding: {
              code: optionValue(opt),
              display: optionLabel(opt),
            },
          });
        } else {
          onAnswer(item.linkId, null);
        }
      }}
    >
      <option value="">— Select —</option>
      {options.map((opt) => (
        <option key={optionValue(opt)} value={optionValue(opt)}>
          {optionLabel(opt)}
        </option>
      ))}
    </select>
  );
}

function optionValue(opt: AnswerOption): string {
  if (opt.valueCoding) return opt.valueCoding.code;
  if (opt.valueString) return opt.valueString;
  if (opt.valueInteger !== undefined) return String(opt.valueInteger);
  return "";
}

function optionLabel(opt: AnswerOption): string {
  if (opt.valueCoding?.display) return opt.valueCoding.display;
  return optionValue(opt);
}
