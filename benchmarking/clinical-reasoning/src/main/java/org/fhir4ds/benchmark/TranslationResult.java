package org.fhir4ds.benchmark;

/**
 * Result of CQL to ELM translation with timing information.
 *
 * NOTE: This is a stub implementation for benchmark infrastructure.
 * The Library type should be org.cqframework.cql.elm.execution.Library
 * once the proper Maven dependencies are added.
 */
public class TranslationResult {
    private final Object library; // Should be org.cqframework.cql.elm.execution.Library
    private final double translationTimeMs;
    private final String errorMessage;

    public TranslationResult(Object library, double translationTimeMs) {
        this.library = library;
        this.translationTimeMs = translationTimeMs;
        this.errorMessage = null;
    }

    public TranslationResult(String errorMessage) {
        this.library = null;
        this.translationTimeMs = 0;
        this.errorMessage = errorMessage;
    }

    public Object getLibrary() {
        return library;
    }

    public double getTranslationTimeMs() {
        return translationTimeMs;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public boolean isSuccess() {
        return errorMessage == null;
    }
}