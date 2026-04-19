package org.fhir4ds.benchmark;

import java.util.Map;

public class EvaluationResult {
    private final String patientId;
    private final double executionTimeMs;
    private final Map<String, Object> results;
    private final String errorMessage;
    private final String status;

    public EvaluationResult(String patientId, double executionTimeMs, Map<String, Object> results) {
        this.patientId = patientId;
        this.executionTimeMs = executionTimeMs;
        this.results = results;
        this.errorMessage = null;
        this.status = "success";
    }

    public EvaluationResult(String patientId, String errorMessage) {
        this.patientId = patientId;
        this.executionTimeMs = 0;
        this.results = null;
        this.errorMessage = errorMessage;
        this.status = "error";
    }

    public String getPatientId() {
        return patientId;
    }

    public double getExecutionTimeMs() {
        return executionTimeMs;
    }

    public Map<String, Object> getResults() {
        return results;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public String getStatus() {
        return status;
    }

    public boolean isSuccess() {
        return "success".equals(status);
    }
}