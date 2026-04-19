package org.fhir4ds.benchmark;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.parser.IParser;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Resource;
import org.hl7.fhir.r4.model.ValueSet;
import org.opencds.cqf.cql.engine.runtime.Code;
import org.opencds.cqf.cql.engine.terminology.CodeSystemInfo;
import org.opencds.cqf.cql.engine.terminology.TerminologyProvider;
import org.opencds.cqf.cql.engine.terminology.ValueSetInfo;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/**
 * Terminology provider that loads pre-expanded ValueSets from FHIR Bundle files.
 */
public class LocalTerminologyProvider implements TerminologyProvider {

    /** Shared FHIR context — creating one is expensive (full classpath scan). */
    private static final FhirContext SHARED_FHIR_CONTEXT = FhirContext.forR4();

    private final Map<String, Set<Code>> valueSetCodes = new HashMap<>();
    private final FhirContext fhirContext;
    private final IParser jsonParser;

    public LocalTerminologyProvider() {
        this.fhirContext = SHARED_FHIR_CONTEXT;
        this.jsonParser = fhirContext.newJsonParser().setPrettyPrint(false);
    }

    public void loadValueSetBundle(Path bundleFile) throws IOException {
        String json = Files.readString(bundleFile);
        Bundle bundle = jsonParser.parseResource(Bundle.class, json);
        for (Bundle.BundleEntryComponent entry : bundle.getEntry()) {
            Resource resource = entry.getResource();
            if (resource instanceof ValueSet) {
                ValueSet vs = (ValueSet) resource;
                String url = vs.getUrl();
                if (url == null) continue;
                Set<Code> codes = valueSetCodes.computeIfAbsent(url, k -> new HashSet<>());
                if (vs.getExpansion() != null && vs.getExpansion().getContains() != null) {
                    for (ValueSet.ValueSetExpansionContainsComponent contains : vs.getExpansion().getContains()) {
                        Code code = new Code();
                        code.setSystem(contains.getSystem());
                        code.setCode(contains.getCode());
                        code.setDisplay(contains.getDisplay());
                        codes.add(code);
                    }
                }
            }
        }
    }

    public void loadFromDirectory(Path dir, String filePattern) throws IOException {
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, filePattern)) {
            for (Path file : stream) {
                loadValueSetBundle(file);
            }
        }
    }

    @Override
    public boolean in(Code code, ValueSetInfo valueSetInfo) {
        Iterable<Code> expanded = expand(valueSetInfo);
        for (Code c : expanded) {
            if (c.getCode() != null && c.getCode().equals(code.getCode())
                && c.getSystem() != null && c.getSystem().equals(code.getSystem())) {
                return true;
            }
        }
        return false;
    }

    @Override
    public Iterable<Code> expand(ValueSetInfo valueSetInfo) {
        String url = valueSetInfo.getId();
        Set<Code> codes = valueSetCodes.get(url);
        return codes != null ? codes : Collections.emptyList();
    }

    @Override
    public Code lookup(Code code, CodeSystemInfo codeSystemInfo) {
        return code;
    }
}
