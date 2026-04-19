package org.fhir4ds.benchmark;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.parser.IParser;
import org.hl7.fhir.instance.model.api.IBaseResource;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.DomainResource;
import org.hl7.fhir.r4.model.Patient;
import org.hl7.fhir.r4.model.Resource;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

/**
 * Zero-overhead FHIR data provider that reads resources directly from the filesystem.
 * Loads JSON resource files from patient test directories and indexes them by
 * patient ID and resource type for fast per-patient lookup.
 */
public class NdjsonDataProvider {

    /** Shared FHIR context — creating one is expensive (full classpath scan). */
    private static final FhirContext SHARED_FHIR_CONTEXT = FhirContext.forR4();

    private final FhirContext fhirContext;
    private final IParser jsonParser;
    // patientId -> resourceType -> list of resources
    private final Map<String, Map<String, List<IBaseResource>>> dataByPatient = new HashMap<>();
    private String currentPatientId;

    public NdjsonDataProvider() {
        this.fhirContext = SHARED_FHIR_CONTEXT;
        this.jsonParser = fhirContext.newJsonParser().setPrettyPrint(false);
    }

    /**
     * Load all resources from a patient directory.
     * Scans all .json files and parses each as a FHIR resource.
     */
    public void loadPatientDirectory(Path patientDir) throws IOException {
        String patientId = patientDir.getFileName().toString();
        List<IBaseResource> allResources = new ArrayList<>();

        try (Stream<Path> files = Files.list(patientDir)) {
            files.filter(f -> f.toString().endsWith(".json"))
                 .filter(f -> !f.getFileName().toString().startsWith("."))
                 .forEach(f -> {
                     try {
                         String jsonText = Files.readString(f);
                         IBaseResource resource = parseResource(jsonText);
                         if (resource != null) {
                             allResources.add(resource);
                         }
                     } catch (Exception e) {
                         System.err.println("  Warning: Failed to parse " + f.getFileName() + ": " + e.getMessage());
                     }
                 });
        }

        // Extract patient ID from Patient resource if present
        for (IBaseResource r : allResources) {
            if (r instanceof Patient) {
                patientId = r.getIdElement().getIdPart();
                break;
            }
        }

        // Index resources by type
        for (IBaseResource resource : allResources) {
            String resourceType = fhirContext.getResourceType(resource);
            dataByPatient.computeIfAbsent(patientId, k -> new HashMap<>())
                         .computeIfAbsent(resourceType, k -> new ArrayList<>())
                         .add(resource);
        }

        currentPatientId = patientId;
    }

    /**
     * Load resources from a bundle file.
     * Extracts entries and indexes them by patient ID.
     */
    public void loadBundleFile(Path bundleFile) throws IOException {
        String jsonText = Files.readString(bundleFile);
        IBaseResource parsed = parseResource(jsonText);
        if (parsed instanceof Bundle) {
            Bundle bundle = (Bundle) parsed;
            String patientId = null;
            List<IBaseResource> resources = new ArrayList<>();

            for (Bundle.BundleEntryComponent entry : bundle.getEntry()) {
                Resource resource = entry.getResource();
                if (resource instanceof Patient && patientId == null) {
                    patientId = resource.getIdElement().getIdPart();
                }
                String resourceType = resource.getResourceType().name();
                resources.add(resource);
            }

            if (patientId == null) {
                patientId = bundleFile.getParent().getFileName().toString();
            }

            for (IBaseResource resource : resources) {
                String resourceType = fhirContext.getResourceType(resource);
                dataByPatient.computeIfAbsent(patientId, k -> new HashMap<>())
                             .computeIfAbsent(resourceType, k -> new ArrayList<>())
                             .add(resource);
            }
        }
    }

    /**
     * Load from an NDJSON file (one JSON resource per line).
     */
    public void loadNdjsonFile(Path ndjsonFile) throws IOException {
        List<String> lines = Files.readAllLines(ndjsonFile);
        for (String line : lines) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            IBaseResource resource = parseResource(line);
            if (resource == null) continue;

            String resourceType = fhirContext.getResourceType(resource);
            String patientId = extractPatientId(resource);

            dataByPatient.computeIfAbsent(patientId, k -> new HashMap<>())
                         .computeIfAbsent(resourceType, k -> new ArrayList<>())
                         .add(resource);
        }
    }

    /**
     * Get all resources for a patient, organized by resource type.
     */
    public Map<String, List<IBaseResource>> getResourcesForPatient(String patientId) {
        return dataByPatient.getOrDefault(patientId, Collections.emptyMap());
    }

    /**
     * Get resources of a specific type for a patient.
     */
    @SuppressWarnings("unchecked")
    public <T extends IBaseResource> List<T> getResourcesForPatient(String patientId, Class<T> resourceType) {
        String typeName = fhirContext.getResourceType(resourceType);
        Map<String, List<IBaseResource>> patientData = dataByPatient.get(patientId);
        if (patientData == null) return Collections.emptyList();
        List<IBaseResource> resources = patientData.get(typeName);
        if (resources == null) return Collections.emptyList();
        List<T> result = new ArrayList<>();
        for (IBaseResource r : resources) {
            if (resourceType.isInstance(r)) {
                result.add((T) r);
            }
        }
        return result;
    }

    /**
     * Get all patient IDs.
     */
    public Set<String> getPatientIds() {
        return Collections.unmodifiableSet(dataByPatient.keySet());
    }

    /**
     * Get the most recently loaded patient ID.
     */
    public String getCurrentPatientId() {
        return currentPatientId;
    }

    /**
     * Get total resource count across all patients.
     */
    public int getTotalResourceCount() {
        return dataByPatient.values().stream()
            .flatMap(m -> m.values().stream())
            .mapToInt(List::size)
            .sum();
    }

    /**
     * Clear all loaded data.
     */
    public void clear() {
        dataByPatient.clear();
        currentPatientId = null;
    }

    /**
     * Check if any data has been loaded.
     */
    public boolean hasData() {
        return !dataByPatient.isEmpty();
    }

    public FhirContext getFhirContext() {
        return fhirContext;
    }

    private IBaseResource parseResource(String jsonText) {
        try {
            return jsonParser.parseResource(jsonText);
        } catch (Exception e) {
            return null;
        }
    }

    private String extractPatientId(IBaseResource resource) {
        if (resource instanceof Patient) {
            return resource.getIdElement().getIdPart();
        }
        // For non-Patient resources, try to extract subject.reference
        if (resource instanceof DomainResource) {
            DomainResource dr = (DomainResource) resource;
            // Use resource ID as fallback, prefixed with resource type
            return resource.getIdElement().getIdPart();
        }
        return resource.getIdElement().getIdPart();
    }
}
