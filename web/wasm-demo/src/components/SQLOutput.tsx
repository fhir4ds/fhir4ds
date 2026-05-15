interface SQLOutputProps {
  value: string;
}

export function SQLOutput({ value }: SQLOutputProps) {
  const lines = value.split("\n");

  return (
    <div className="sql-viewer" data-testid="sql-output-viewer">
      <div className="sql-viewer-scroll" role="region" aria-label="Generated SQL">
        <code className="sql-viewer-code">
          {lines.map((line, index) => (
            <span className="sql-viewer-line" key={index}>
              <span className="sql-viewer-line-number">{index + 1}</span>
              <span className="sql-viewer-line-text">{line || " "}</span>
            </span>
          ))}
        </code>
      </div>
    </div>
  );
}
