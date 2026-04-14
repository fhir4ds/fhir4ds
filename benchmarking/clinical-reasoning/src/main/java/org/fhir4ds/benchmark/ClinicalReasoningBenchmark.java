package org.fhir4ds.benchmark;

import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import org.hl7.fhir.r4.model.*;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.*;

@Command(name = "clinical-reasoning-benchmark",
        mixinStandardHelpOptions = true,
        description = "Benchmark clinical-reasoning CQL engine against FHIR4DS")
public class ClinicalReasoningBenchmark implements Runnable {

    @Option(names = {"--measure-dir"}, description = "Directory containing measure test data", required = true)
    private Path measureDir;

    @Option(names = {"--cql-dir"}, description = "Directory containing CQL files", required = true)
    private Path cqlDir;

    @Option(names = {"--valueset-dir"}, description = "Directory containing ValueSet definitions", required = true)
    private Path valuesetDir;

    @Option(names = {"--valueset-bundle-dir"}, description = "Directory containing per-measure ValueSet bundles")
    private Path valuesetBundleDir;

    @Option(names = {"--period-start"}, description = "Measurement period start (yyyy-MM-dd)", required = true)
    private String periodStart;

    @Option(names = {"--period-end"}, description = "Measurement period end (yyyy-MM-dd)", required = true)
    private String periodEnd;

    @Option(names = {"--output"}, description = "Output JSON file path", required = true)
    private Path outputPath;

    @Option(names = {"--warmup"}, description = "Number of warmup iterations", defaultValue = "0")
    private int warmupIterations;

    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();

    @Override
    public void run() {
        try {
            System.out.println("Clinical Reasoning Benchmark");
            System.out.println("============================");
            System.out.println("Measure Dir: " + measureDir);
            System.out.println("CQL Dir: " + cqlDir);
            System.out.println("ValueSet Dir: " + valuesetDir);
            System.out.println("Period: " + periodStart + " to " + periodEnd);
            System.out.println("Output: " + outputPath);
            System.out.println("Warmup: " + warmupIterations);
            System.out.println();

            // Find all measure directories
            List<Path> measureDirectories = findMeasureDirectories();
            System.out.println("Found " + measureDirectories.size() + " measures to benchmark");

            // Process each measure
            List<MeasureBenchmarkResult> allResults = new ArrayList<>();

            for (Path measurePath : measureDirectories) {
                String measureId = measurePath.getFileName().toString();
                System.out.println("\nBenchmarking measure: " + measureId);

                try {
                    MeasureBenchmarkResult result = benchmarkMeasure(measurePath);
                    allResults.add(result);
                    System.out.println("  Completed: " + result.getSummary().getSuccess_count() +
                                     "/" + result.getSummary().getPatient_count() + " patients, " +
                                     "avg " + String.format("%.2f", result.getSummary().getAvg_patient_ms()) + "ms");
                } catch (Exception e) {
                    String errMsg = e.getClass().getName() + ": " + e.getMessage();
                    System.err.println("  Error benchmarking " + measureId + ": " + errMsg);
                    allResults.add(new MeasureBenchmarkResult(measureId, null, null,
                        Collections.emptyList(), new MeasureSummary(0, 0, 0, 0, 0), errMsg));
                } catch (Throwable t) {
                    String errMsg = t.getClass().getName() + ": " + t.getMessage();
                    System.err.println("  Fatal error benchmarking " + measureId + ": " + errMsg);
                    allResults.add(new MeasureBenchmarkResult(measureId, null, null,
                        Collections.emptyList(), new MeasureSummary(0, 0, 0, 0, 0), errMsg));
                }
            }

            // Write combined results
            writeResults(allResults);

            System.out.println("\nBenchmark completed. Results written to: " + outputPath);

        } catch (Exception e) {
            System.err.println("Benchmark failed: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    private List<Path> findMeasureDirectories() throws IOException {
        List<Path> measures = new ArrayList<>();

        try (var stream = Files.list(measureDir)) {
            stream.filter(Files::isDirectory)
                  .filter(dir -> !dir.getFileName().toString().startsWith("."))
                  .forEach(measures::add);
        }

        return measures.stream()
                       .sorted()
                       .collect(Collectors.toList());
    }

    private MeasureBenchmarkResult benchmarkMeasure(Path measurePath) throws IOException {
        String measureId = measurePath.getFileName().toString();
        String measureName = measureId; // TODO: Extract from measure metadata if available

        // Find CQL file
        Path cqlFile = findCqlFile(measureId);
        if (cqlFile == null) {
            throw new RuntimeException("CQL file not found for measure: " + measureId);
        }

        String cqlText = Files.readString(cqlFile);

        // Initialize evaluator
        CqlEvaluator evaluator = new CqlEvaluator(List.of(cqlDir));

        // Load ValueSet bundles for this measure if available
        if (valuesetBundleDir != null) {
            LocalTerminologyProvider terminologyProvider = new LocalTerminologyProvider();
            Path bundleDir = valuesetBundleDir.resolve(measureId)
                .resolve(measureId + "-files");
            String glob = "valuesets-" + measureId + "-bundle.json";
            try {
                terminologyProvider.loadFromDirectory(bundleDir, glob);
                evaluator.setTerminologyProvider(terminologyProvider);
                System.out.println("  Loaded ValueSet terminology");
            } catch (Exception e) {
                System.out.println("  Warning: Could not load ValueSets from " + bundleDir + ": " + e.getMessage());
            }
        }

        // Warmup iterations
        for (int i = 0; i < warmupIterations; i++) {
            evaluator.translate(cqlText);
        }

        // Translate CQL to ELM
        TranslationResult translation = evaluator.translate(cqlText);
        if (!translation.isSuccess()) {
            throw new RuntimeException("CQL translation failed: " + translation.getErrorMessage());
        }

        // Load test data
        List<Path> patientDirectories = findPatientDirectories(measurePath);
        System.out.println("  Found " + patientDirectories.size() + " test patients");

        // Evaluate each patient
        List<PatientResult> patientResults = new ArrayList<>();
        int successCount = 0;
        int errorCount = 0;
        double totalPatientTimeMs = 0;

        for (Path patientDir : patientDirectories) {
            String patientId = patientDir.getFileName().toString();

            try {
                NdjsonDataProvider dataProvider = new NdjsonDataProvider();

                // Load patient data
                if (patientDir.toString().contains("bundle")) {
                    // Load bundle files
                    try (var files = Files.list(patientDir)) {
                        files.filter(f -> f.toString().endsWith("bundle.json"))
                             .forEach(f -> {
                                 try {
                                     dataProvider.loadBundleFile(f);
                                 } catch (IOException e) {
                                     throw new UncheckedIOException(e);
                                 }
                             });
                    }
                } else {
                    // Load individual resource files
                    dataProvider.loadPatientDirectory(patientDir);
                }

                // Set up parameters (measurement period)
                Map<String, Object> parameters = new HashMap<>();
                parameters.put("Measurement Period Start", periodStart);
                parameters.put("Measurement Period End", periodEnd);

                // Evaluate
                EvaluationResult evalResult = evaluator.evaluate(
                    translation.getLibrary(),
                    dataProvider,
                    patientId,
                    parameters
                );

                if (evalResult.isSuccess()) {
                    successCount++;
                    totalPatientTimeMs += evalResult.getExecutionTimeMs();
                } else {
                    errorCount++;
                    if (evalResult.getErrorMessage() != null) {
                        System.err.println("    Patient " + patientId + " error: " + evalResult.getErrorMessage());
                    }
                }

                patientResults.add(new PatientResult(
                    patientId,
                    evalResult.getExecutionTimeMs(),
                    evalResult.getStatus()
                ));

            } catch (Exception e) {
                errorCount++;
                patientResults.add(new PatientResult(patientId, 0, "error: " + e.getMessage()));
                System.err.println("    Error evaluating patient " + patientId + ": " + e.getMessage());
            }
        }

        // Calculate summary
        MeasureSummary summary = new MeasureSummary(
            patientDirectories.size(),
            successCount,
            errorCount,
            patientDirectories.size() > 0 ? totalPatientTimeMs / patientDirectories.size() : 0,
            totalPatientTimeMs
        );

        return new MeasureBenchmarkResult(
            measureId,
            measureName,
            new TimingInfo(translation.getTranslationTimeMs(), totalPatientTimeMs),
            patientResults,
            summary
        );
    }

    private Path findCqlFile(String measureId) throws IOException {
        // 1. Exact/contains match in the CQL dir
        try (var stream = Files.list(cqlDir)) {
            var match = stream
                .filter(f -> f.getFileName().toString().contains(measureId))
                .filter(f -> f.toString().endsWith(".cql"))
                .findFirst();
            if (match.isPresent()) return match.get();
        }

        // 2. Strip leading CMS{digits} prefix and retry (e.g. CMS157OncologyPain → OncologyPain)
        String stripped = measureId.replaceFirst("^CMS\\d+", "");
        if (!stripped.equals(measureId) && !stripped.isEmpty()) {
            try (var stream = Files.list(cqlDir)) {
                var match = stream
                    .filter(f -> f.getFileName().toString().contains(stripped))
                    .filter(f -> f.toString().endsWith(".cql"))
                    .findFirst();
                if (match.isPresent()) return match.get();
            }
        }

        // 3. Look in the bundles directory: bundles/measure/{measureId}/{measureId}-files/{measureId}.cql
        if (valuesetBundleDir != null) {
            Path bundleCql = valuesetBundleDir.resolve(measureId)
                .resolve(measureId + "-files")
                .resolve(measureId + ".cql");
            if (Files.exists(bundleCql)) return bundleCql;
        }

        return null;
    }

    private List<Path> findPatientDirectories(Path measurePath) throws IOException {
        List<Path> patientDirs = new ArrayList<>();

        try (var stream = Files.walk(measurePath, 2)) {
            stream.filter(Files::isDirectory)
                  .filter(dir -> !dir.equals(measurePath))
                  .filter(dir -> dir.getFileName().toString().matches(
                      "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|.*bundle.*"))
                  .forEach(patientDirs::add);
        }

        return patientDirs.stream()
                         .sorted()
                         .collect(Collectors.toList());
    }

    private void writeResults(List<MeasureBenchmarkResult> results) throws IOException {
        // Create parent directories if needed
        Files.createDirectories(outputPath.getParent());

        // Write as JSON
        String json = gson.toJson(results);
        Files.writeString(outputPath, json);
    }

    public static void main(String[] args) {
        int exitCode = new CommandLine(new ClinicalReasoningBenchmark()).execute(args);
        System.exit(exitCode);
    }

    // Result classes for JSON serialization
    public static class MeasureBenchmarkResult {
        private final String measure_id;
        private final String measure_name;
        private final TimingInfo timings;
        private final List<PatientResult> patients;
        private final MeasureSummary summary;
        private final String error;

        public MeasureBenchmarkResult(String measure_id, String measure_name,
                                     TimingInfo timings, List<PatientResult> patients,
                                     MeasureSummary summary) {
            this(measure_id, measure_name, timings, patients, summary, null);
        }

        public MeasureBenchmarkResult(String measure_id, String measure_name,
                                     TimingInfo timings, List<PatientResult> patients,
                                     MeasureSummary summary, String error) {
            this.measure_id = measure_id;
            this.measure_name = measure_name;
            this.timings = timings;
            this.patients = patients;
            this.summary = summary;
            this.error = error;
        }

        public String getMeasure_id() { return measure_id; }
        public String getMeasure_name() { return measure_name; }
        public TimingInfo getTimings() { return timings; }
        public List<PatientResult> getPatients() { return patients; }
        public MeasureSummary getSummary() { return summary; }
        public String getError() { return error; }
    }

    public static class TimingInfo {
        private final double translation_ms;
        private final double total_execution_ms;

        public TimingInfo(double translation_ms, double total_execution_ms) {
            this.translation_ms = translation_ms;
            this.total_execution_ms = total_execution_ms;
        }

        public double getTranslation_ms() { return translation_ms; }
        public double getTotal_execution_ms() { return total_execution_ms; }
    }

    public static class PatientResult {
        private final String id;
        private final double elapsed_ms;
        private final String status;

        public PatientResult(String id, double elapsed_ms, String status) {
            this.id = id;
            this.elapsed_ms = elapsed_ms;
            this.status = status;
        }

        public String getId() { return id; }
        public double getElapsed_ms() { return elapsed_ms; }
        public String getStatus() { return status; }
    }

    public static class MeasureSummary {
        private final int patient_count;
        private final int success_count;
        private final int error_count;
        private final double avg_patient_ms;
        private final double total_execution_ms;

        public MeasureSummary(int patient_count, int success_count, int error_count,
                             double avg_patient_ms, double total_execution_ms) {
            this.patient_count = patient_count;
            this.success_count = success_count;
            this.error_count = error_count;
            this.avg_patient_ms = avg_patient_ms;
            this.total_execution_ms = total_execution_ms;
        }

        public int getPatient_count() { return patient_count; }
        public int getSuccess_count() { return success_count; }
        public int getError_count() { return error_count; }
        public double getAvg_patient_ms() { return avg_patient_ms; }
        public double getTotal_execution_ms() { return total_execution_ms; }
    }
}